"""Print the messages the PiFinder Mount Bridge sends to its INDI clients (its INFO / WARNING log), for N seconds.

    python3 test_tools/bridge_messages.py SECONDS [nodebug]

Without "nodebug" it also switches the driver's Debug on (and off again at the end). Use "nodebug" while testing the Bridge's behaviour:
the INFO lines already say what it decided ("forwarded Goto", "Arrival verified", "external control detected", "Reposition
confirmation timed out"). Used for the sky simulation tests (#344); a raw INDI client, no indi_getprop (which is heavy and, when
several run at once, can load the driver).
"""
import socket, sys, time, re
s = socket.create_connection(("127.0.0.1", 7624), timeout=5)
s.sendall(b'<getProperties version="1.7" device="PiFinder Mount Bridge"/>')
time.sleep(1)
if len(sys.argv) < 3: s.sendall(b"<newSwitchVector device=\"PiFinder Mount Bridge\" name=\"DEBUG\"><oneSwitch name=\"ENABLE\">On</oneSwitch></newSwitchVector>")
s.settimeout(1.0)
end = time.time() + float(sys.argv[1])
buf = ""
while time.time() < end:
    try:
        d = s.recv(65536)
    except socket.timeout:
        continue
    if not d:
        break
    buf += d.decode(errors="replace")
    for m in re.finditer(r'<message[^>]*message="([^"]*)"', buf):
        pass
    parts = buf.split("<message")
    buf = "<message" + parts[-1] if len(parts) > 1 else buf[-2000:]
    for p in parts[1:-1]:
        mm = re.search(r'timestamp="([^"]*)"[^>]*message="([^"]*)"|message="([^"]*)"', "<message" + p)
        if mm:
            print(time.strftime("%H:%M:%S"), (mm.group(2) or mm.group(3) or "")[:300], flush=True)
s.sendall(b'<newSwitchVector device="PiFinder Mount Bridge" name="DEBUG"><oneSwitch name="DISABLE">On</oneSwitch></newSwitchVector>')
