#!/usr/bin/env python3
"""Live test: Push-To and last GoTo around a Multi-Point Alignment. MOVES THE MOUNT - Telescope Simulator only.

    ~/PiFinder/python/.venv/bin/python test_tools/mpa_hold_target_test.py --move

Needs the same setup as mount_goto_refine_test.py (running Full Simulation, Mount Bridge in the GoTo coupling, simulated sky).

1. A GoTo sets the last GoTo (TARGET_STATUS) and the Push-To (ORIGINAL_TARGET).
2. Multi-Point Alignment (2 points): both stay, the Bridge drives nowhere on its own while it runs, and a point only counts
   when the mount took its Sync (the Telescope Simulator ignores one close to a point it already has).
3. Afterwards: "Waiting for the next GoTo", nothing moves; a manual Sync starts nothing.
4. "Send Push-To to PiFinder": the mount stays where it is.
5. "Goto Push-To": the scope returns there.
6. Stopped alignment: the same - both unchanged, nothing moves; the next GoTo is followed again.

Exit 0 = every check passed.
"""
import argparse
import sys
import time

import mount_goto_refine_test as t
from mount_model_check import separation_deg

AWAY = 1.0 / 60   # degrees: "the same place"


def target():
    v = t.numbers(t.BRIDGE, "TARGET_STATUS")
    return v["RA"], v["DEC"]


def hold():
    v = t.numbers(t.BRIDGE, "ORIGINAL_TARGET")
    return v["RA"], v["DEC"]


def slewing():
    return t.read(t.MOUNT, "EQUATORIAL_EOD_COORD").get("state") == "Busy"


def watch_still(run, seconds):
    """Watches; returns the times (s) at which the mount was seen slewing."""
    seen = []

    def note():
        if slewing():
            seen.append(round(time.time() - run.t0))
        return False

    run.watch(seconds, note)
    return seen


def alignment(run, stop_after=None):
    """Runs a Multi-Point Alignment; returns (final state, phases seen, targets seen)."""
    t.indi_client.set_switch(t.BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_START")
    start, targets = time.time(), []
    del run.phases[:]
    while time.time() - start < 240:
        run.watch(2)
        targets.append(target())
        state = t.read(t.BRIDGE, "MULTI_POINT_ALIGN").get("state")
        if stop_after and time.time() - start > stop_after:
            t.indi_client.set_switch(t.BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_STOP")
            run.say("alignment stopped")
            run.watch(3)
            return "stopped", list(run.phases), targets
        if state in ("Ok", "Alert") and time.time() - start > 6:
            return state, list(run.phases), targets
    return "timeout", list(run.phases), targets


def goto(ra, dec):
    run = t.Run()
    t.send_coords(t.MOUNT, "SLEW", ra, dec)
    return run.watch(150, lambda: t.phase() == "ON_TARGET" and len(run.phases) > 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--move", action="store_true")
    args = ap.parse_args(argv)
    if not args.move:
        ap.error("this moves the mount: --move")
    drivers = t.indi_client.get_properties(timeout=15)
    mounts = [d for d, p in drivers.items() if "TELESCOPE_PARK" in p or "ON_COORD_SET" in p and d != t.PIFINDER]
    if any(d != t.MOUNT for d in mounts):
        sys.exit("refused: not only the Telescope Simulator (%s)" % ", ".join(mounts))
    threshold = t.numbers(t.BRIDGE, "DRIFT_THRESHOLD")
    threshold = next(iter(threshold.values()))
    config = t.read(t.BRIDGE, "ALIGN_CONFIG")["elements"]
    t.indi_client.set_number(t.BRIDGE, "ALIGN_CONFIG", {**config, "POINT_COUNT": 2})
    results = []
    check = lambda name, ok, text: results.append(t.check(name, ok, text))
    try:
        ra, dec = t.targets()[0]
        check("1 goto", goto(ra, dec) and separation_deg(*target(), ra, dec) < AWAY, "on target, Target set")
        target0, hold0 = target(), hold()

        points = lambda: next(iter(t.numbers(t.MOUNT, "ALIGNMENT_POINTSET_SIZE").values()))
        before_points = points()
        run = t.Run()
        state, phases, seen = alignment(run)
        synced = int(t.numbers(t.BRIDGE, "ALIGN_PROGRESS")["POINT_SYNCED"])
        taken = int(points() - before_points)
        # A model point added is not the same as the mount reporting the position (the simulator fits all its points), so only
        # the run's own verdict is checked against its count; both numbers are shown.
        check("2 counted syncs", 0 <= synced <= 2 and (synced > 0) == (state == "Ok"),
              "counted %d of 2 as reported by the mount, the simulator added %d model point(s), state %s" % (synced, taken, state))
        moved_target = max(separation_deg(*x, *target0) for x in seen) * 60
        check("2 alignment", state in ("Ok", "Alert") and "ALIGNING" in phases and moved_target < 1
              and separation_deg(*hold(), *hold0) < AWAY,
              "state %s, phases %s, last GoTo moved %.1f', Push-To moved %.1f'" %
              (state, phases, moved_target, separation_deg(*hold(), *hold0) * 60))

        end = t.mount_position()
        away = separation_deg(*end, *hold0) * 60
        run = t.Run()
        slews = watch_still(run, 40)
        t.indi_client.set_switch(t.BRIDGE, "MANUAL_TRIGGER", "TRIGGER_SYNC_NOW")
        run.say("manual Sync mount from PiFinder")
        slews += watch_still(run, 30)
        expected = "WAITING" if away > threshold else "HOLDING"
        check("3 afterwards", not slews and t.phase() == expected and separation_deg(*target(), *target0) < AWAY and not run.asked,
              "%.0f' from the Push-To: phase %s (expected %s), slewing at %s, asked %s" %
              (away, t.phase(), expected, slews or "never", run.asked))

        before = t.mount_position()
        run = t.Run()
        t.indi_client.trigger_align_held()
        run.say("Send Push-To to PiFinder")
        slews = watch_still(run, 30)
        moved = separation_deg(*before, *t.mount_position()) * 60
        check("4 align pifinder", not slews and moved < threshold and separation_deg(*hold(), *hold0) < AWAY,
              "mount moved %.1f', slewing at %s, phase %s" % (moved, slews or "never", t.phase()))

        run = t.Run()
        t.indi_client.trigger_goto_held()
        run.say("Goto Push-To")
        arrived = run.watch(150, lambda: t.phase() == "ON_TARGET" and not slewing())
        off = separation_deg(*t.mount_position(), ra, dec) * 60   # the Hold position is the GoTo of step 1 (here in JNow)
        check("5 goto hold", arrived and off <= 2 * threshold and separation_deg(*target(), ra, dec) < AWAY,
              "phase %s, mount %.1f' from the Push-To" % (t.phase(), off))

        target1, hold1 = target(), hold()
        run = t.Run()
        state, phases, seen = alignment(run, stop_after=8)
        run = t.Run()
        slews = watch_still(run, 45)
        moved_target = max(separation_deg(*x, *target1) for x in seen + [target()]) * 60
        check("6 stopped", not [s for s in slews if s > 3] and moved_target < 1 and not run.asked,
              "slewing after the stop at %s, last GoTo moved %.1f', Push-To moved %.1f', phase %s" %
              (slews or "never", moved_target, separation_deg(*hold(), *hold1) * 60, t.phase()))
        # PiFinder cannot solve every simulated star field (found 2026-11-28, RA 6.67 h Dec +30): that is no verdict about the
        # Bridge, so such a field is left for the next one - and said.
        for ra, dec in t.targets()[1:]:
            ok = goto(ra, dec)
            age = t.solve_age()
            if ok or (age is not None and age < 20):
                break
            print("   PiFinder cannot solve the field at RA %.2f h Dec %.0f (last solve %s s ago): trying another one" %
                  (ra, dec, "?" if age is None else int(age)), flush=True)
        off = separation_deg(*t.mount_position(), ra, dec) * 60
        check("6 next goto", ok and off <= 2 * threshold and separation_deg(*target(), ra, dec) < AWAY
              and separation_deg(*hold(), ra, dec) < 1,   # ORIGINAL_TARGET is J2000: some 20' of precession away
              "followed: phase %s, mount %.1f' from it" % (t.phase(), off))
    finally:
        t.indi_client.set_number(t.BRIDGE, "ALIGN_CONFIG", config)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
