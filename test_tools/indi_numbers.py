"""Print the number vectors of the given INDI devices (raw INDI client).

    ~/PiFinder/python/.venv/bin/python test_tools/indi_numbers.py "PiFinder Mount Bridge" "Telescope Simulator"
"""
import socket, sys, time
sys.path.insert(0, "/home/stellarmate/PiFinder_Stellarmate/test_tools")
import pifinder_sky_follow as f
devs = sys.argv[1:] or ["PiFinder Mount Bridge"]
s = socket.create_connection(("localhost", 7624), timeout=5)
for d in devs:
    s.sendall(f'<getProperties version="1.7" device="{d}"/>'.encode())
s.settimeout(1.0)
buf = ""; end = time.time() + 4; seen = {}
while time.time() < end:
    try:
        chunk = s.recv(65536)
    except socket.timeout:
        continue
    if not chunk: break
    buf += chunk.decode("utf-8", "replace")
    vecs, buf = f.parse_number_vectors(buf)
    for dev, name, state, vals in vecs:
        seen[(dev, name)] = (state, vals)
for (dev, name), (state, vals) in sorted(seen.items()):
    if any(k in name for k in ("DRIFT", "EQUATORIAL_EOD", "LAST_KNOWN", "THRESHOLD", "FRESH")):
        print(f"{dev} | {name} [{state}] {vals}")
