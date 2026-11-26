"""Print the named properties of the PiFinder Mount Bridge (raw INDI client, no indi_getprop).

    python3 test_tools/bridge_props.py OBSERVER_LOCATION BRIDGE_MODE DRIFT_STATUS
"""
import re
import socket
import sys
import time


def read(names, port=7624, device="PiFinder Mount Bridge", seconds=4):
    s = socket.create_connection(("localhost", port), timeout=5)
    s.sendall(('<getProperties version="1.7" device="%s"/>' % device).encode())
    s.settimeout(1)
    buf, end = "", time.time() + seconds
    while time.time() < end:
        try:
            c = s.recv(65536)
        except socket.timeout:
            continue
        if not c:
            break
        buf += c.decode("utf-8", "replace")
    out = {}
    for n in names:
        ms = list(re.finditer(r'<(?:def|set)(?:Number|Text|Switch)Vector\b(?:(?!</(?:def|set)(?:Number|Text|Switch)Vector>).)*?name="%s".*?'
                              r'</(?:def|set)(?:Number|Text|Switch)Vector>' % n, buf, re.S))
        if ms:
            t = re.sub(r"\s+", " ", ms[-1].group(0))
            out[n] = re.sub(r'(label|group|perm|timeout|format|min|max|step)="[^"]*"\s*', "", t)
    return out


if __name__ == "__main__":
    for name, text in read(sys.argv[1:]).items():
        print(name, "=>", text[:330])
