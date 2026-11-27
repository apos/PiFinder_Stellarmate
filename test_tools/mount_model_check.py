#!/usr/bin/env python3
"""Live check: does the mount arrive where it is sent, also after a Sync? MOVES THE MOUNT - run only on purpose.

    python3 test_tools/mount_model_check.py --move [--device "Telescope Simulator"] [--sync]

Sends GoTos to positions high above the horizon and compares the position the mount reports with the one it was sent to. --sync adds a
Sync far from the current position in between (Telescope Simulator only: it changes the mount's alignment model). Exit 0 = every GoTo
arrived within 1 degree. Switch the Mount Bridge's coupling off first, otherwise the Bridge moves the mount as well.
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402

LIMIT_DEG = 1.0


def lst_hours(longitude_deg):
    jd = time.time() / 86400 + 2440587.5
    return ((280.46061837 + 360.98564736629 * (jd - 2451545) + longitude_deg) % 360) / 15


def separation_deg(ra1, dec1, ra2, dec2):
    a, b, d = math.radians(dec1), math.radians(dec2), math.radians((ra1 - ra2) * 15)
    return math.degrees(math.acos(max(-1.0, min(1.0, math.sin(a) * math.sin(b) + math.cos(a) * math.cos(b) * math.cos(d)))))


class Mount:
    def __init__(self, device):
        self.device = device

    def read(self, name):
        return indi_client.get_properties(device=self.device, timeout=8, stop_after={name}).get(self.device, {}).get(name, {})

    def position(self):
        v = self.read("EQUATORIAL_EOD_COORD")
        return float(v["elements"]["RA"]), float(v["elements"]["DEC"]), v.get("state")

    def command(self, kind, ra, dec, wait_s=120):
        indi_client.set_switch(self.device, "ON_COORD_SET", kind)
        message = ('<newNumberVector device="%s" name="EQUATORIAL_EOD_COORD"><oneNumber name="RA">%.6f</oneNumber>'
                   '<oneNumber name="DEC">%.6f</oneNumber></newNumberVector>\\n') % (self.device, ra, dec)
        with socket.create_connection(("127.0.0.1", 7624), timeout=5) as sock:
            sock.sendall(message.encode())
            time.sleep(2)
        end = time.time() + wait_s
        while self.position()[2] == "Busy" and time.time() < end:
            time.sleep(1)
        return self.position()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\\n")[0])
    ap.add_argument("--move", action="store_true", help="required: this moves the mount")
    ap.add_argument("--device", default="Telescope Simulator")
    ap.add_argument("--sync", action="store_true", help="also Sync far away in between (Telescope Simulator only)")
    args = ap.parse_args(argv)
    if not args.move:
        ap.error("this moves the mount; pass --move")
    if args.sync and args.device != "Telescope Simulator":
        ap.error("--sync changes the alignment model and is only allowed on the Telescope Simulator")
    mount = Mount(args.device)
    geo = mount.read("GEOGRAPHIC_COORD").get("elements", {})
    lst = lst_hours(float(geo.get("LONG", 0)))
    failed = 0
    for number, (offset, dec) in enumerate(((-1.0, 45.0), (1.0, 30.0), (-2.0, 60.0))):
        if args.sync and number == 1:
            mount.command("SYNC", (lst + 3.0) % 24, 10.0)
            print("synced far away")
        ra = (lst + offset) % 24
        r = mount.command("TRACK", ra, dec)
        missed = separation_deg(ra, dec, r[0], r[1])
        ok = missed <= LIMIT_DEG
        failed += not ok
        print("%s GoTo RA %.4f h Dec %.1f -> mount RA %.4f h Dec %.2f: %.2f deg off" % ("ok  " if ok else "FAIL", ra, dec, r[0], r[1], missed))
    points = mount.read("ALIGNMENT_POINTSET_SIZE").get("elements", {}).get("ALIGNMENT_POINTSET_SIZE")
    print("alignment points: %s" % (points if points is not None else "no alignment subsystem"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
