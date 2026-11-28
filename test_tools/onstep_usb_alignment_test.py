#!/usr/bin/env python3
"""An alignment on an OnStep connected over USB: the Mount Bridge sees it through the INDI driver and syncs nothing.

    python3 test_tools/onstep_usb_alignment_test.py [path/to/indi_pifinder_mount_bridge]

OnStep counts every Sync during an alignment as "this star is centred". Own indiserver (port 7693, own HOME) with the Bridge,
the stand-in OnStep INDI driver in its USB (serial) mode, a stand-in controller on 127.0.0.1:9999 that records what is written
to it, a Telescope Simulator standing in for the PiFinder device and a stand-in PiFinder web server (port 7690). Nothing real
is touched.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
sys.path.insert(0, HERE)
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402
from mount_model_check import lst_hours  # noqa: E402
from pifinder_sky_follow import jnow_to_j2000  # noqa: E402

PORT, WEB = 7693, 7690
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "LX200 OnStep", "PiFinder LX200"
SEEN = {"ra": 0.0, "dec": 60.0}   # what PiFinder's camera sees, JNow hours / degrees
WRITES = []


def controller():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 9999))
    server.listen(8)

    def serve():
        while True:
            client, _ = server.accept()
            WRITES.append(client.recv(64).decode(errors="replace"))
            client.sendall(b"1#")
            client.close()

    threading.Thread(target=serve, daemon=True).start()


class PiFinder(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        ra, dec = jnow_to_j2000(SEEN["ra"] * 15.0, SEEN["dec"])
        now = time.time() - 0.3
        self.answer({"solution": {"solve_source": "CAM", "last_solve_success": now, "last_solve_attempt": now,
                                  "RA": ra, "Dec": dec}, "location": {}})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.answer({})


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    controller()
    web = ThreadingHTTPServer(("127.0.0.1", WEB), PiFinder)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-usb-align-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        late.write_config(tmp)
        config = os.path.join(tmp, ".indi", "PiFinder Mount Bridge_config.xml")
        with open(config) as f:
            text = f.read().replace('"ACTIVE_MOUNT">Telescope Simulator<', '"ACTIVE_MOUNT">%s<' % MOUNT)
        with open(config, "w") as f:
            f.write(text.replace(">pifinder.invalid<", ">127.0.0.1:%d/x<" % WEB))
        server = subprocess.Popen(["indiserver", "-p", str(PORT), "-f", fifo, "-u", os.path.join(tmp, "sock")],
                                  env=dict(os.environ, HOME=tmp, FAKE_ONSTEP_CONNECTION="serial"),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pipe = os.open(fifo, os.O_RDWR)

        def command(line):
            os.write(pipe, (line + "\n").encode())

        def read(device, name):
            try:
                return indi_client.get_properties(device=device, port=PORT, timeout=6, stop_after={name}).get(device, {}).get(name)
            except indi_client.INDIClientError:
                return None

        def until(what, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if what():
                    return True
                time.sleep(1)
            return False

        def syncs():
            return WRITES.count(":CM#")

        def alignment(star, stars):
            indi_client.set_text(MOUNT, "TEST_CONTROL", {"STAR": star, "STARS": stars}, port=PORT)

        def hand_move(dec, off=0.5):
            """The hand controller moves the mount; PiFinder then sees `off` degrees beside what the mount reports."""
            ra = lst_hours(8.45)
            SEEN["ra"], SEEN["dec"] = ra, dec + off
            indi_client.set_text(MOUNT, "TEST_CONTROL", {"RA": "%.6f" % ra, "DEC": "%.6f" % dec}, port=PORT)

        def coupling(mode):
            indi_client.set_switch(BRIDGE, "BRIDGE_MODE", mode, port=PORT)

        results, messages = [], []

        def count(part):
            return sum(part in m for m in messages)

        def check(name, ok, text=""):
            results.append(ok)
            print("%s %s %s" % ("ok  " if ok else "FAIL", name, text), flush=True)

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            command("start %s" % os.path.join(HERE, "fake_onstep_indi_driver.py"))
            if not until(lambda: read(PIFINDER, "CONNECTION"), 20) or not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("drivers did not appear")
            if read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            indi_client.set_switch(PIFINDER, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(2)
            hand_move(60.0, off=0.0)
            indi_client.set_switch(BRIDGE, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(5)
            check("the controller is not read directly (USB)", (read(BRIDGE, "ONSTEP_ALIGNMENT") or {}).get("state") != "Ok")
            coupling("MODE_GOTO_FORWARD")
            time.sleep(12)

            before = syncs()
            hand_move(63.0)
            check("1 without an alignment a hand movement is followed by a Sync", until(lambda: syncs() > before, 60),
                  "(syncs %d)" % (syncs() - before))
            time.sleep(8)

            alignment("1", "3")
            seen = until(lambda: count("alignment is running on the OnStep controller") >= 1, 15)
            before = syncs()
            time.sleep(3)
            hand_move(57.0)
            time.sleep(35)
            check("2 during a controller alignment a movement is not synced", seen and syncs() == before,
                  "(seen %s, syncs %d)" % (seen, syncs() - before))

            coupling("MODE_OFF")
            time.sleep(4)
            coupling("MODE_GOTO_FORWARD")
            time.sleep(15)
            check("3 switching the coupling on does not sync", syncs() == before, "(syncs %d)" % (syncs() - before))

            indi_client.set_switch(BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_START", port=PORT)
            time.sleep(10)
            check("4 Multi-Point Alignment is refused meanwhile", syncs() == before and count("finish or abort it there first") == 1,
                  "(syncs %d)" % (syncs() - before))

            alignment("4", "3")
            ended = until(lambda: count("Alignment ended") >= 1, 15)
            time.sleep(25)
            check("5 after the alignment nothing is synced on its own", ended and syncs() == before,
                  "(ended %s, syncs %d)" % (ended, syncs() - before))
        finally:
            if not results or not all(results):
                print("\n".join(messages[-30:]))
            os.close(pipe)
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
            web.shutdown()
        return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
