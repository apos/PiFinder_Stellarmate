#!/usr/bin/env python3
"""One line per second while the mount is tested: the mount's position/state/motion switches, the Bridge's drift, PiFinder's solve.

    ~/PiFinder/python/.venv/bin/python test_tools/onstep_watch.py ["LX200 OnStep" [SECONDS]]
"""
import json
import os
import socket
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_follow as f  # noqa: E402

DEV = sys.argv[1] if len(sys.argv) > 1 else "LX200 OnStep"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 1200
BR = "PiFinder Mount Bridge"
s = socket.create_connection(("localhost", 7624), timeout=5)
for d in (DEV, BR):
    s.sendall(f'<getProperties version="1.7" device="{d}"/>'.encode())
s.settimeout(0.5)
num, sw, buf = {}, {}, ""


def pump(sec):
    global buf
    end = time.time() + sec
    while time.time() < end:
        try:
            c = s.recv(65536)
        except socket.timeout:
            continue
        if not c:
            return
        buf += c.decode("utf-8", "replace")
        vecs, buf = f.parse_number_vectors(buf)
        for dev, name, state, vals in vecs:
            num[(dev, name)] = (state, vals)
        try:
            svs, _ = f.parse_switch_vectors(buf)
            for dev, name, state, vals in svs:
                sw[(dev, name)] = (state, vals)
        except Exception:
            pass


def solve():
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/status", timeout=3).read())
        x = d.get("solution") or {}
        return "%s %s %s" % (x.get("solve_source"), None if x.get("RA") is None else round(x["RA"], 3), None if x.get("Dec") is None else round(x["Dec"], 3))
    except Exception:
        return "pf?"


print(time.strftime("%T"), "watching", DEV, flush=True)
end = time.time() + SECONDS
while time.time() < end:
    pump(1.0)
    st, v = num.get((DEV, "EQUATORIAL_EOD_COORD"), (None, {}))
    mot = {k: [n for n, on in sw.get((DEV, k), (None, {}))[1].items() if on] for k in ("TELESCOPE_MOTION_NS", "TELESCOPE_MOTION_WE", "TELESCOPE_TRACK_STATE")}
    drift = num.get((BR, "DRIFT_STATUS"), (None, {}))[1].get("DRIFT_ARCMIN")
    print("%s %-5s RA %.5f Dec %+.4f | %s | drift %s | solve %s" % (
        time.strftime("%T"), st, v.get("RA", -1), v.get("DEC", -1),
        " ".join("%s=%s" % (k.replace("TELESCOPE_", ""), ",".join(x) or "-") for k, x in mot.items()), drift, solve()), flush=True)
