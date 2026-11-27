#!/usr/bin/env python3
"""Live test: a GoTo sent to the mount is refined like one sent to PiFinder. MOVES THE MOUNT - Telescope Simulator only.

    ~/PiFinder/python/.venv/bin/python test_tools/mount_goto_refine_test.py --move [--only goto,short,hand,stop,pifinder,bounded,hold,held,question]

Needs the running Full Simulation: Mount Bridge on the Telescope Simulator in the GoTo coupling and the simulated sky with a landing
error larger than the threshold ("typical"). Refuses any other mount.

goto      GoTo to the mount (Slew, as the StellarMate app's SLEW): PiFinder ends on the requested coordinates, no 45 s question.
short     The same for a GoTo of only half a degree.
hand      Direction button after arrival: the new position is kept, mount and PiFinder agree soon, no 45 s question.
stop      Stop during a GoTo to the mount: nothing drives on afterwards.
bounded   A target that cannot be reached (threshold set to 0.1' for this scenario): the attempts end, nothing moves any more.
hold      An alignment (the hold the Control Center sets): a Sync during it, then released as solved: the Bridge moves and syncs
          nothing afterwards; the next GoTo works again.
held      "Goto to Target" (the Control Center's button) from elsewhere: ends on the target, which stays the target.
question  The scope "bumped" (the simulated sky moves, the mount does not): a question, nothing moves for longer than the former
          45 s; "adopt" and "back to the target" both do what they say.
pifinder  GoTo to the PiFinder device (as KStars does on "PiFinder LX200"): unchanged, ends on target.

Exit 0 = every scenario passed.
(Alignment runs in Ekos are recorded with ekos_align_probe.py.)
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import gsc_sim  # noqa: E402
import indi_client  # noqa: E402
from mount_model_check import lst_hours, separation_deg  # noqa: E402

MOUNT = "Telescope Simulator"
BRIDGE = "PiFinder Mount Bridge"
PIFINDER = "PiFinder LX200"


def read(device, name):
    return indi_client.get_properties(device=device, timeout=8, stop_after={name}).get(device, {}).get(name, {})


def numbers(device, name):
    return {k: float(v) for k, v in read(device, name).get("elements", {}).items()}


def phase():
    return read(BRIDGE, "POSITIONING_PHASE").get("elements", {}).get("PHASE")


def asking():
    return read(BRIDGE, "REPOSITION_CONFIRM").get("state") == "Busy"


def drift_arcmin():
    return numbers(BRIDGE, "DRIFT_STATUS").get("DRIFT_ARCMIN")


def mount_position():
    v = numbers(MOUNT, "EQUATORIAL_EOD_COORD")
    return v["RA"], v["DEC"]


def pifinder_off_target_arcmin(ra, dec):
    """PiFinder's solved position against a target (JNow), as the Bridge reads it."""
    t = numbers(BRIDGE, "TARGET_STATUS")
    if not t or separation_deg(t["RA"], t["DEC"], ra, dec) > 1 / 60:
        return None
    return t["OFFSET_ARCMIN"]


def send_coords(device, kind, ra, dec):
    indi_client.set_switch(device, "ON_COORD_SET", kind)
    message = ('<newNumberVector device="%s" name="EQUATORIAL_EOD_COORD"><oneNumber name="RA">%.6f</oneNumber>'
               '<oneNumber name="DEC">%.6f</oneNumber></newNumberVector>\n') % (device, ra, dec)
    with socket.create_connection(("127.0.0.1", 7624), timeout=5) as sock:
        sock.sendall(message.encode())
        time.sleep(1)


class Run:
    """Polls the Bridge and notes every phase it went through and whether it ever asked the 45 s question."""

    def __init__(self):
        self.t0 = time.time()
        self.phases = []
        self.asked = False

    def say(self, text):
        print("  %5.1f s  %s" % (time.time() - self.t0, text), flush=True)

    def watch(self, seconds, done=None):
        end = time.time() + seconds
        while time.time() < end:
            p = phase()
            if not self.phases or self.phases[-1] != p:
                self.phases.append(p)
                self.say("phase %s | drift %.1f'" % (p, drift_arcmin() or 0))
            if asking() and not self.asked:
                self.asked = True
                self.say("45 s question asked")
            if done and done():
                return True
            time.sleep(1)
        return False


def targets():
    geo = numbers(MOUNT, "GEOGRAPHIC_COORD")
    lst = lst_hours(geo.get("LONG", 0))
    return [((lst - 1.0) % 24, 45.0), ((lst + 1.0) % 24, 30.0), ((lst - 2.0) % 24, 60.0), ((lst + 0.5) % 24, 20.0)]


def check(name, ok, text):
    print("%s %s: %s" % ("ok  " if ok else "FAIL", name, text), flush=True)
    return ok


def scenario_goto(threshold, name="goto", target=None):
    ra, dec = target or targets()[0]
    run = Run()
    send_coords(MOUNT, "SLEW", ra, dec)
    run.watch(150, lambda: phase() == "ON_TARGET" and len(run.phases) > 1)
    off = pifinder_off_target_arcmin(ra, dec)
    refined = "REFINING" in run.phases
    source = read(BRIDGE, "TARGET_SOURCE").get("elements", {}).get("TARGET_SOURCE_MOUNT")
    return check(name, phase() == "ON_TARGET" and off is not None and off <= threshold and not run.asked and source == "On",
                 "phase %s, PiFinder %s' from the target (limit %.0f'), refined %s, asked %s, source mount %s" %
                 (phase(), "?" if off is None else "%.1f" % off, threshold, refined, run.asked, source))


def scenario_short(threshold):
    ra, dec = mount_position()
    return scenario_goto(threshold, "short", (ra, dec - 0.5 if dec > 0 else dec + 0.5))


def scenario_hand(threshold):
    before = mount_position()
    run = Run()
    indi_client.set_switch(MOUNT, "TELESCOPE_SLEW_RATE", "3x")
    indi_client.set_switch(MOUNT, "TELESCOPE_MOTION_NS", "MOTION_NORTH")
    time.sleep(3)
    message = ('<newSwitchVector device="%s" name="TELESCOPE_MOTION_NS"><oneSwitch name="MOTION_NORTH">Off</oneSwitch>'
               '<oneSwitch name="MOTION_SOUTH">Off</oneSwitch></newSwitchVector>\n') % MOUNT
    with socket.create_connection(("127.0.0.1", 7624), timeout=5) as sock:
        sock.sendall(message.encode())
        time.sleep(1)
    released = mount_position()
    moved = separation_deg(before[0], before[1], released[0], released[1]) * 60
    run.say("button released, moved %.1f'" % moved)
    run.watch(60)
    after = mount_position()
    back = separation_deg(before[0], before[1], after[0], after[1]) * 60
    d = drift_arcmin()
    return check("hand", moved > 2 * threshold and back > moved / 2 and d is not None and d <= threshold and not run.asked,
                 "moved %.1f', 60 s later %.1f' from where it started (kept), mount-PiFinder %s', asked %s" %
                 (moved, back, "?" if d is None else "%.1f" % d, run.asked))


def scenario_stop(threshold):
    here = mount_position()
    ra, dec = max(targets(), key=lambda t: separation_deg(here[0], here[1], t[0], t[1]))
    run = Run()
    send_coords(MOUNT, "SLEW", ra, dec)
    run.watch(3)
    indi_client.set_switch(MOUNT, "TELESCOPE_ABORT_MOTION", "ABORT")
    run.say("stop sent, %.1f deg from the target" % separation_deg(*mount_position(), ra, dec))
    del run.phases[:]
    slews = []

    def note_slew():
        if read(MOUNT, "EQUATORIAL_EOD_COORD").get("state") == "Busy":
            slews.append(round(time.time() - run.t0))
        return False

    run.watch(3)   # the stop itself
    run.watch(60, note_slew)
    later = mount_position()
    short = separation_deg(later[0], later[1], ra, dec)
    driven = [p for p in run.phases if p in ("VERIFYING", "REFINING")]
    d = drift_arcmin()
    return check("stop", short > 1 and not slews and not driven and not run.asked and d is not None and d <= 2 * threshold,
                 "ends %.1f deg short of the target, mount slewing after the stop at %s, phases %s, mount-PiFinder %s', asked %s" %
                 (short, slews or "never", run.phases, "?" if d is None else "%.1f" % d, run.asked))


def scenario_pifinder(threshold):
    ra, dec = targets()[1]
    run = Run()
    send_coords(PIFINDER, "TRACK", ra, dec)
    run.watch(150, lambda: phase() == "ON_TARGET" and len(run.phases) > 1)
    off = pifinder_off_target_arcmin(ra, dec)
    return check("pifinder", phase() == "ON_TARGET" and off is not None and off <= threshold + 1 and not run.asked,
                 "phase %s, PiFinder %s' from the target, asked %s" % (phase(), "?" if off is None else "%.1f" % off, run.asked))


def scenario_bounded(threshold):
    ra, dec = targets()[2]
    run = Run()
    indi_client.set_number(BRIDGE, "DRIFT_THRESHOLD", {"THRESHOLD_ARCMIN": 0.1})
    try:
        send_coords(MOUNT, "SLEW", ra, dec)
        ended = run.watch(180, lambda: phase() in ("GAVE_UP", "OFF_TARGET"))
        slews = []

        def note_slew():
            if read(MOUNT, "EQUATORIAL_EOD_COORD").get("state") == "Busy":
                slews.append(round(time.time() - run.t0))
            return False

        run.watch(60, note_slew)
    finally:
        indi_client.set_number(BRIDGE, "DRIFT_THRESHOLD", {"THRESHOLD_ARCMIN": threshold})
    return check("bounded", ended and not slews and not run.asked,
                 "gave up: %s (phase %s), mount slewing in the 60 s after at %s" % (ended, phase(), slews or "never"))


def scenario_hold(threshold):
    ra, dec = mount_position()
    run = Run()
    indi_client.set_mount_bridge_external_hold(True, "alignment (live test)")
    try:
        time.sleep(4)
        send_coords(MOUNT, "SYNC", ra, dec - 0.5 if dec > 0 else dec + 0.5)   # what Ekos does after a solve
        time.sleep(5)
        seen = indi_client.mount_bridge_hold_syncs()
        before = mount_position()
    finally:
        indi_client.set_mount_bridge_external_hold(False, "alignment ended: solved")
    slews = []

    def note_slew():
        if read(MOUNT, "EQUATORIAL_EOD_COORD").get("state") == "Busy":
            slews.append(round(time.time() - run.t0))
        return False

    run.watch(60, note_slew)
    after = mount_position()
    changed = separation_deg(before[0], before[1], after[0], after[1]) * 60
    quiet = check("hold", seen >= 1 and not slews and changed < 3 and not run.asked,
                  "syncs seen during the hold %d, after the release: slewing at %s, mount position changed %.1f', asked %s" %
                  (seen, slews or "never", changed, run.asked))
    # the Sync above was deliberately wrong (0.5 degrees): it stays in the simulator's alignment model and later GoTos would land
    # beside their target for that reason alone
    gsc_sim.prepare_simulator_mount(MOUNT, indi_client)
    time.sleep(3)
    return scenario_goto(threshold, "hold, next GoTo") and quiet


def scenario_held(threshold):
    ra, dec = targets()[1]
    first = Run()
    send_coords(MOUNT, "SLEW", ra, dec)
    first.watch(150, lambda: phase() == "ON_TARGET" and len(first.phases) > 1)
    indi_client.set_mount_bridge_external_hold(True, "alignment (live test)")
    try:
        send_coords(MOUNT, "SLEW", ra, dec + 1.0)   # while held: the mount goes elsewhere, the target stays
        time.sleep(15)
    finally:
        indi_client.set_mount_bridge_external_hold(False, "alignment ended: solved")
    time.sleep(5)
    run = Run()
    indi_client.trigger_goto_held()
    run.watch(150, lambda: phase() == "ON_TARGET" and len(run.phases) > 1)
    run.watch(20)
    m = mount_position()
    off = separation_deg(m[0], m[1], ra, dec) * 60
    return check("held", phase() == "ON_TARGET" and off <= threshold + 1 and not run.asked,
                 "phase %s, mount %.1f' from the target after the button, asked %s" % (phase(), off, run.asked))


def bump(east, north):
    """The simulated sky (what PiFinder sees) moves against the mount's report: clutch slip."""
    with open(os.path.expanduser("~/.pfsm/gsc_sim_nudge.json"), "w") as f:
        f.write('{"east": %d, "north": %d}' % (east, north))


def quiet_for(run, seconds):
    slews = []

    def note():
        if read(MOUNT, "EQUATORIAL_EOD_COORD").get("state") == "Busy":
            slews.append(round(time.time() - run.t0))
        return False

    run.watch(seconds, note)
    return not slews


def scenario_question(threshold):
    ra, dec = targets()[0]
    results = []
    for answer in ("adopt", "back"):
        first = Run()
        send_coords(MOUNT, "SLEW", ra, dec)
        first.watch(150, lambda: phase() == "ON_TARGET" and len(first.phases) > 1)
        first.watch(8)
        before = mount_position()
        run = Run()
        bump(60, 0)
        asked = run.watch(60, asking)
        still = quiet_for(run, 60)          # longer than the former 45 s
        open_still = asking() and phase() == "CHECK_SCOPE"
        moved = separation_deg(before[0], before[1], *mount_position()) * 60
        results.append(check("question (%s): asked" % answer, asked and still and open_still and moved < 2,
                             "asked %s, nothing moved for 60 s %s, still open %s, mount moved %.1f'" % (asked, still, open_still, moved)))
        if answer == "adopt":
            indi_client.trigger_reposition_adopt()
            run.watch(30)
            d = drift_arcmin()
            moved = separation_deg(before[0], before[1], *mount_position()) * 60
            results.append(check("question: adopt", not asking() and d is not None and d <= threshold and 30 < moved < 90,
                                 "mount-PiFinder %s', mount now %.1f' from before (the bump was 60')" % (d and round(d, 1), moved)))
        else:
            indi_client.trigger_reposition_revert()
            run.watch(90, lambda: phase() == "ON_TARGET")
            off = pifinder_off_target_arcmin(ra, dec)
            results.append(check("question: back to the target", not asking() and phase() == "ON_TARGET",
                                 "phase %s, PiFinder %s' from the target" % (phase(), off and round(off, 1))))
    bump(60, 0)
    run = Run()
    run.watch(60, asking)
    send_coords(MOUNT, "SLEW", *targets()[1])
    run.watch(150, lambda: phase() == "ON_TARGET" and len(run.phases) > 1)
    results.append(check("question: a new GoTo withdraws it", not asking() and phase() == "ON_TARGET", "phase %s, asking %s" % (phase(), asking())))
    return all(results)


SCENARIOS = {"goto": scenario_goto, "short": scenario_short, "hand": scenario_hand, "stop": scenario_stop, "pifinder": scenario_pifinder, "bounded": scenario_bounded, "hold": scenario_hold, "held": scenario_held, "question": scenario_question}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--move", action="store_true", help="required: this moves the mount")
    ap.add_argument("--only", default=",".join(SCENARIOS))
    args = ap.parse_args(argv)
    if not args.move:
        ap.error("this moves the mount; pass --move")
    mount = read(BRIDGE, "ACTIVE_DEVICES").get("elements", {}).get("ACTIVE_MOUNT")
    if mount != MOUNT:
        sys.exit("refused: the Mount Bridge's mount is %r, this test only runs on the %s" % (mount, MOUNT))
    if read(BRIDGE, "BRIDGE_MODE").get("elements", {}).get("MODE_GOTO_FORWARD") != "On":
        sys.exit("refused: switch the Mount Bridge to the GoTo coupling first")
    threshold = numbers(BRIDGE, "DRIFT_THRESHOLD")["THRESHOLD_ARCMIN"]
    failed = 0
    for name in args.only.split(","):
        print("== %s" % name, flush=True)
        failed += not SCENARIOS[name](threshold)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
