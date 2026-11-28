#!/usr/bin/env python3
"""Which mount type does an INDI OnStep driver binary report for a controller answering :GXEM# with N? (#227)

    python3 test_tools/onstep_mount_type_check.py <indi_lx200generic binary> fake:<N>
    python3 test_tools/onstep_mount_type_check.py <indi_lx200generic binary> <controller address> <port>

Expected for the patched build (bin/build_indi_onstep_fix.sh --build-only): 1 = EQ_GEM, 2 = EQ_FORK, 3 = ALTAZ; the stock
driver says EQ_GEM for all three (INDI 2.2.5). Own indiserver (port 7691, own HOME); a real controller is only read.
"""
import os, socket, subprocess, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "gui_installer"), HERE]
import indi_client as c
binary, where = os.path.abspath(sys.argv[1]), sys.argv[2]
host, port = (("127.0.0.1", 9991) if where.startswith("fake:") else (where, int(sys.argv[3])))
if where.startswith("fake:"):
    answers = {":GVP#": "On-Step#", ":GVN#": "10.14a#", ":GXEM#": where.split(":")[1] + "#", ":GU#": "nNpHa/Eo030#",
               ":GR#": "12:00:00#", ":GD#": "+45*00:00#", ":A?#": "900#", ":GVD#": "01/01/26#", ":GVT#": "00:00:00#"}
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind((host, port)); srv.listen(4)
    def serve(cl):
        buf = ""
        while True:
            try: d = cl.recv(256)
            except OSError: return
            if not d: return
            buf += d.decode(errors="replace")
            if "\x06" in buf: cl.sendall(b"P"); buf = buf.replace("\x06", "")
            while "#" in buf:
                cmd, buf = buf.split("#", 1); cl.sendall(answers.get(cmd + "#", "0#").encode())
    def accept():
        while True:
            cl, _ = srv.accept(); threading.Thread(target=serve, args=(cl,), daemon=True).start()
    threading.Thread(target=accept, daemon=True).start()
P, M = 7691, "LX200 OnStep"
with tempfile.TemporaryDirectory(prefix="mounttype-") as tmp:
    link = os.path.join(tmp, "indi_lx200_OnStep"); os.symlink(binary, link)
    server = subprocess.Popen(["indiserver", "-p", str(P), "-u", os.path.join(tmp, "sock"), link], env=dict(os.environ, HOME=tmp),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import bridge_late_mount_test as late
    messages = []; late.PORT = P
    threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
    def read(n):
        try: return c.get_properties(device=M, port=P, timeout=5, stop_after={n}).get(M, {}).get(n)
        except c.INDIClientError: return None
    try:
        for _ in range(30):
            if read("CONNECTION_MODE"): break
            time.sleep(1)
        c.set_switch(M, "CONNECTION_MODE", "CONNECTION_TCP", port=P); time.sleep(1)
        c.set_text(M, "DEVICE_ADDRESS", {"ADDRESS": host, "PORT": str(port)}, port=P); time.sleep(1)
        c.set_switch(M, "CONNECTION", "CONNECT", port=P)
        t = None
        for _ in range(60):
            t = read("TELESCOPE_MOUNT_TYPE")
            if t and (read("CONNECTION") or {}).get("state") == "Ok": break
            time.sleep(1)
        time.sleep(12); t = read("TELESCOPE_MOUNT_TYPE")
        print("  ", [m[-120:] for m in messages if "ount type" in m or "GXEM" in m or "German" in m][:4])
        print("connected", (read("CONNECTION") or {}).get("state"), "| mount type", [k for k, v in (t or {}).get("elements", {}).items() if v == "On"])
    finally:
        server.terminate(); server.wait(10)
