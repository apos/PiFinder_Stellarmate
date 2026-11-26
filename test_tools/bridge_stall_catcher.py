#!/usr/bin/env python3
"""Catch a stall of the Mount Bridge (#385): probe it through indiserver every second, time PiFinder's web API next to it, and at the
first failed probe record what the Bridge and indiserver do (strace -tt -f, 10 s) and who is busy. One capture, then it stops.

    python3 test_tools/bridge_stall_catcher.py [MINUTES]      output: ~/bridge_stalls/
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

OUT = os.path.expanduser("~/bridge_stalls")
MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 60
os.makedirs(OUT, exist_ok=True)


def pid_of(pattern):
    r = subprocess.run(["pgrep", "-f", pattern, "-o"], capture_output=True, text=True)
    return int(r.stdout.split()[0]) if r.stdout.split() else None


def probe(device, timeout=3.0):
    t0 = time.time()
    try:
        s = socket.create_connection(("127.0.0.1", 7624), timeout=timeout)
        s.sendall(('<getProperties version="1.7" device="%s"/>\n' % device).encode())
        s.settimeout(timeout)
        ok = bool(s.recv(4096))
        s.close()
        return ok, time.time() - t0
    except Exception:
        return False, time.time() - t0


def pifinder_latency():
    t0 = time.time()
    try:
        urllib.request.urlopen("http://127.0.0.1:8080/api/status", timeout=10).read(100)
        return time.time() - t0
    except Exception:
        return -1.0


log = open(os.path.join(OUT, "probe.log"), "a", buffering=1)
print(time.strftime("%T"), "probing the Mount Bridge for %.0f min" % MINUTES, flush=True)
end = time.time() + MINUTES * 60
while time.time() < end:
    ok, dt = probe("PiFinder Mount Bridge")
    pf = pifinder_latency()
    load = open("/proc/loadavg").read().split()[0]
    log.write("%s bridge %s %.2fs | pifinder api %.2fs | load %s\n" % (time.strftime("%T"), "ok" if ok else "SILENT", dt, pf, load))
    if not ok:
        stamp = time.strftime("%H%M%S")
        bridge, srv = pid_of("^indi_pifinder_mount_bridge"), pid_of("indiserver -u /tmp/indiserver[0-9]+ -p 7624")
        others = {d: probe(d)[0] for d in ("PiFinder LX200", "LX200 OnStep")}
        print(time.strftime("%T"), "STALL: bridge pid", bridge, "indiserver", srv, "others answer:", others, "-> capture", stamp, flush=True)
        with open("%s/%s.info" % (OUT, stamp), "w") as f:
            f.write("others answer: %s\npifinder api latency: %.2f\n" % (others, pf))
            f.write(subprocess.run(["top", "-b", "-n", "1", "-H", "-w", "160"], capture_output=True, text=True).stdout[:3500])
            f.write(subprocess.run(["ss", "-tnp", "state", "established", "( sport = :7624 )"], capture_output=True, text=True).stdout)
        cmd = ["sudo", "-n", "timeout", "10", "strace", "-f", "-tt", "-s", "100", "-o", "%s/%s.strace" % (OUT, stamp)]
        for p in (bridge, srv):
            if p:
                cmd += ["-p", str(p)]
        subprocess.run(cmd)
        print(time.strftime("%T"), "captured", stamp, flush=True)
        break
    time.sleep(max(0.0, 1.0 - dt))
print(time.strftime("%T"), "done", flush=True)
