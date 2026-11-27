#!/usr/bin/env python3
"""Run one Ekos capture & solve and record what happens when: Ekos' align status and log, camera exposures, mount movement,
the Mount Bridge's hold. MAY MOVE THE MOUNT (action slew/sync) - simulator profile only.

    ~/PiFinder/python/.venv/bin/python test_tools/ekos_align_probe.py --action nothing|sync|slew [--goto-offset DEG] [--seconds N]

--goto-offset sends a GoTo to the mount first and solves after it (like the StellarMate app's GO, which also sets the action
"slew"), that many degrees south of the current position.
Ends with a summary: the longest quiet gap (nothing exposing, moving or solving) between the first and the last activity.
Refuses unless every mount and camera on the INDI server is a simulator.
"""
import argparse
import os
import re
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402
from mount_model_check import lst_hours  # noqa: E402

ACTIONS = {"sync": 0, "slew": 1, "nothing": 2}
STATES = ["idle", "complete", "failed", "aborted", "progress", "successful", "syncing", "slewing", "rotating", "suspended"]
BUSY = {4, 6, 7, 8, 9}
ALIGN = ["qdbus6", "org.kde.kstars", "/KStars/Ekos/Align"]


def align(member, *args):
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/%d/bus" % os.getuid())
    r = subprocess.run(ALIGN + ["org.kde.kstars.Ekos.Align." + member] + [str(a) for a in args], env=env, capture_output=True,
                       text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or member)
    return r.stdout.strip()


class Indi(threading.Thread):
    """Keeps the latest state of every property, from one connection."""

    def __init__(self):
        super().__init__(daemon=True)
        self.states, self.on = {}, {}
        self.sock = socket.create_connection(("127.0.0.1", 7624), timeout=5)
        self.sock.sendall(b'<getProperties version="1.7"/>\n')
        self.sock.settimeout(None)

    def run(self):
        buf = ""
        vector = re.compile(r"<(?:def|set)(Number|Switch)Vector\b([^>]*)>(.*?)</(?:def|set)\1Vector>", re.S)
        while True:
            data = self.sock.recv(65536)
            if not data:
                return
            buf += data.decode(errors="replace")
            last = 0
            for m in vector.finditer(buf):
                last = m.end()
                dev = re.search(r'device="([^"]*)"', m.group(2))
                name = re.search(r'name="([^"]*)"', m.group(2))
                state = re.search(r'state="([^"]*)"', m.group(2))
                if not dev or not name:
                    continue
                key = (dev.group(1), name.group(1))
                if state:
                    self.states[key] = state.group(1)
                if m.group(1) == "Switch":
                    self.on[key] = re.findall(r'name="([^"]*)"[^>]*>\s*On\s*<', m.group(3))
            buf = buf[last:] if last else buf[-200000:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--action", choices=sorted(ACTIONS), required=True)
    ap.add_argument("--goto-offset", type=float, default=None)
    ap.add_argument("--goto-high", action="store_true", help="GoTo to a position high in the sky first")
    ap.add_argument("--seconds", type=float, default=120)
    args = ap.parse_args(argv)
    drivers = indi_client.get_properties(timeout=15)
    real = sorted(d for d, p in drivers.items() if ("CCD_EXPOSURE" in p or "EQUATORIAL_EOD_COORD" in p)
                  and "Simulator" not in d and d != "PiFinder LX200")
    if real:
        sys.exit("refused: not a simulator profile (%s)" % ", ".join(real))
    camera = align("camera")
    indi = Indi()
    indi.start()
    time.sleep(2)
    mount = "Telescope Simulator"
    log_before = set(align("logText").split("\n"))
    t0 = time.time()
    say = lambda text: print("%6.1f s  %s" % (time.time() - t0, text), flush=True)
    align("setSolverAction", ACTIONS[args.action])
    if args.goto_offset is not None or args.goto_high:
        pos = indi_client.get_properties(device=mount, timeout=8, stop_after={"EQUATORIAL_EOD_COORD"})[mount]
        ra = float(pos["EQUATORIAL_EOD_COORD"]["elements"]["RA"])
        if args.goto_high:
            lon = float(indi_client.get_properties(device=mount, timeout=8, stop_after={"GEOGRAPHIC_COORD"})[mount]
                        ["GEOGRAPHIC_COORD"]["elements"]["LONG"])
            ra, dec = (lst_hours(lon) - 1.0) % 24, 45.0
        else:
            dec = float(pos["EQUATORIAL_EOD_COORD"]["elements"]["DEC"]) - args.goto_offset
        indi_client.set_switch(mount, "ON_COORD_SET", "SLEW")
        indi.sock.sendall(('<newNumberVector device="%s" name="EQUATORIAL_EOD_COORD"><oneNumber name="RA">%.6f</oneNumber>'
                           '<oneNumber name="DEC">%.6f</oneNumber></newNumberVector>\n' % (mount, ra, dec)).encode())
        say("GoTo sent: RA %.4f h, Dec %.3f" % (ra, dec))
        time.sleep(2)
        while indi.states.get((mount, "EQUATORIAL_EOD_COORD")) == "Busy" and time.time() - t0 < 90:
            time.sleep(0.3)
        say("slew finished")
        time.sleep(2.7)   # the StellarMate app's GO sends its solve about 3 s after the slew (KStars log, 2026-11-27)
    say("capture & solve, action %s, camera %s: %s" % (args.action, camera, align("captureAndSolve")))
    shown, seen_log, samples = None, set(log_before), []
    quiet_since = None
    while time.time() - t0 < args.seconds:
        status = int(align("status"))
        exposing = indi.states.get((camera, "CCD_EXPOSURE")) == "Busy"
        moving = (indi.states.get((mount, "EQUATORIAL_EOD_COORD")) == "Busy"
                  or bool(indi.on.get((mount, "TELESCOPE_MOTION_NS"))) or bool(indi.on.get((mount, "TELESCOPE_MOTION_WE"))))
        held = "HOLD_ON" in indi.on.get(("PiFinder Mount Bridge", "EXTERNAL_HOLD"), [])
        new = [line for line in align("logText").split("\n") if line and line not in seen_log]
        seen_log.update(new)
        for line in reversed(new):
            say("  Ekos: " + line[20:150])
        now = (status, exposing, moving, held)
        if now != shown:
            shown = now
            say("align %-10s | camera %s | mount %s | bridge %s" % (
                STATES[status], "exposing" if exposing else "-", "moving" if moving else "-", "paused" if held else "-"))
        samples.append((time.time() - t0, status in BUSY or exposing or moving or bool(new), held))
        if samples[-1][1] or held:
            quiet_since = None
        quiet_since = quiet_since or (None if samples[-1][1] or held else time.time())
        if quiet_since and time.time() - quiet_since > 25 and any(s[1] for s in samples):
            break
        time.sleep(0.3)
    active = [t for t, a, _ in samples if a]
    gaps = [b - a for a, b in zip(active, active[1:])]
    print("summary: activity from %.1f to %.1f s, longest quiet gap in between %.1f s" % (
        active[0] if active else -1, active[-1] if active else -1, max(gaps) if gaps else 0))
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/%d/bus" % os.getuid())
    result = subprocess.run(["qdbus6", "--literal"] + ALIGN[1:] + ["org.kde.kstars.Ekos.Align.getSolutionResult"], env=env,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    print("solution result: %s | final align status %s" % (result.replace("\n", " ")[:120], STATES[int(align("status"))]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
