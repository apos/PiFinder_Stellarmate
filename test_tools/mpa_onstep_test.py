#!/usr/bin/env python3
"""Multi-Point Alignment with an OnStep: a real alignment on the controller.

    python3 test_tools/mpa_onstep_test.py [path/to/indi_pifinder_mount_bridge]

Own indiserver (port 7698, own HOME) with the Bridge, the stand-in "LX200 OnStep" INDI driver, a stand-in controller (TCP 9998
read by the Bridge, TCP 9999 written by the driver) and a stand-in PiFinder web server (port 7690). Nothing real is touched.
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
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
sys.path.insert(0, HERE)
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402
import onstep_controller_test as base  # noqa: E402

PORT, WEB = 7698, 7690
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "LX200 OnStep", "PiFinder LX200"
STARS = [{"ra": 40.0 + 25 * i, "dec": 30.0 + 3 * i, "name": "Star %d" % (i + 1)} for i in range(14)]


class Controller(base.Controller):
    """Adds the write side: the alignment as OnStep runs it."""

    def __init__(self):
        super().__init__()
        self.writes, self.saved, self.ignore, self.refuse = [], 0, 0, 0
        self.driver = socket.socket()
        self.driver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.driver.bind(("127.0.0.1", 9999))
        self.driver.listen(8)
        threading.Thread(target=self.accept_driver, daemon=True).start()

    def accept_driver(self):
        while True:
            client, _ = self.driver.accept()
            command = client.recv(64).decode()
            self.writes.append(command)
            star, last = int(self.align[1]), int(self.align[2])
            if command.startswith(":A") and command[2].isdigit():
                self.align = "91%s" % command[2]
            elif command == ":CM#" and 0 < star <= last:
                if self.refuse:
                    self.refuse -= 1
                    self.align = "900"                 # OnStep ends the alignment when it refuses a star
                elif self.ignore:
                    self.ignore -= 1
                else:
                    self.align = "9%d%d" % (star + 1, last)
            elif command == ":AW#":
                self.saved += 1
            client.sendall(b"1#")
            client.close()


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
        url = urlparse(self.path)
        if url.path.endswith("api/nearby_bright_stars"):
            count = int(parse_qs(url.query).get("count", ["4"])[0])
            return self.answer({"candidates": STARS[:count]})
        now = time.time() - 0.3
        self.answer({"solution": {"solve_source": "CAM", "last_solve_success": now, "last_solve_attempt": now, "RA": 50.0,
                                  "Dec": 40.0}, "location": {}})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.answer({})


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    controller = Controller()
    controller.start()
    web = ThreadingHTTPServer(("127.0.0.1", WEB), PiFinder)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-mpa-onstep-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        late.write_config(tmp)
        config = os.path.join(tmp, ".indi", "PiFinder Mount Bridge_config.xml")
        with open(config) as f:
            text = f.read().replace('"ACTIVE_MOUNT">Telescope Simulator<', '"ACTIVE_MOUNT">%s<' % MOUNT)
        text = text.replace(">pifinder.invalid<", ">127.0.0.1:%d/x<" % WEB)
        with open(config, "w") as f:
            f.write(text)
        server = subprocess.Popen(["indiserver", "-p", str(PORT), "-f", fifo, "-u", os.path.join(tmp, "sock")],
                                  env=dict(os.environ, HOME=tmp), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pipe = os.open(fifo, os.O_RDWR)

        def command(line):
            os.write(pipe, (line + "\n").encode())

        def read(device, name):
            try:
                return indi_client.get_properties(device=device, port=PORT, timeout=6, stop_after={name}).get(device, {}).get(name)
            except indi_client.INDIClientError:
                return None

        def elements(name):
            return (read(BRIDGE, name) or {}).get("elements", {})

        def state(name):
            return (read(BRIDGE, name) or {}).get("state")

        def until(what, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if what():
                    return True
                time.sleep(1)
            return False

        results, messages = [], []

        def count(text):
            return sum(text in m for m in messages)

        def check(name, ok, text=""):
            results.append(ok)
            print("%s %s %s" % ("ok  " if ok else "FAIL", name, text), flush=True)

        def press(name, element):
            indi_client.set_switch(BRIDGE, name, element, port=PORT)

        def points(n):
            config = elements("ALIGN_CONFIG")
            indi_client.set_number(BRIDGE, "ALIGN_CONFIG", {**config, "POINT_COUNT": n}, port=PORT)
            time.sleep(1)

        def finished():
            return state("MULTI_POINT_ALIGN") in ("Ok", "Alert")

        def run_to_end(seconds=150):
            time.sleep(4)
            return until(finished, seconds)

        def synced():
            return int(float(elements("ALIGN_PROGRESS").get("POINT_SYNCED", -1)))

        def syncs():
            return controller.writes.count(":CM#")

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            command("start %s" % os.path.join(HERE, "fake_onstep_indi_driver.py"))
            if not until(lambda: read(PIFINDER, "CONNECTION"), 20) or not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("drivers did not appear")
            if elements("BRIDGE_SETTINGS")["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            indi_client.set_switch(PIFINDER, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(2)
            press("CONNECTION", "CONNECT")
            check("the controller is read", until(lambda: state("ONSTEP_ALIGNMENT") == "Ok", 40), str(elements("ONSTEP_ALIGNMENT")))

            points(3)
            press("MULTI_POINT_ALIGN", "ALIGN_START")
            ok = run_to_end()
            check("1 a run is an OnStep alignment with three stars", ok and state("MULTI_POINT_ALIGN") == "Ok" and synced() == 3
                  and controller.writes[:1] == [":A3#"] and syncs() == 3 and controller.align == "943",
                  "writes %s, controller %s, synced %d" % (controller.writes, controller.align, synced()))

            press("ALIGN_SAVE", "SAVE")
            check("2 Save to OnStep writes the model", until(lambda: controller.saved == 1, 10) and state("ALIGN_SAVE") == "Ok")

            del controller.writes[:]
            controller.ignore = 1
            press("MULTI_POINT_ALIGN", "ALIGN_START")
            ok = run_to_end()
            check("3 a star OnStep does not count is replaced by another one", ok and state("MULTI_POINT_ALIGN") == "Ok"
                  and synced() == 3 and syncs() == 4 and count("did not count star 1") == 1,
                  "syncs %d, synced %d" % (syncs(), synced()))

            del controller.writes[:]
            controller.refuse = 1
            press("MULTI_POINT_ALIGN", "ALIGN_START")
            ok = run_to_end()
            check("4 a refused star ends the run and says so", ok and state("MULTI_POINT_ALIGN") == "Alert" and synced() == 0
                  and syncs() == 1 and count("refused the star") == 1, "writes %s" % controller.writes)

            del controller.writes[:]
            press("MULTI_POINT_ALIGN", "ALIGN_START")
            until(lambda: synced() == 1, 60)
            press("MULTI_POINT_ALIGN", "ALIGN_STOP")
            time.sleep(4)
            waiting = controller.align
            press("ALIGN_SAVE", "SAVE")
            time.sleep(4)
            check("5 stopped: OnStep keeps waiting, Save is refused", waiting == "923" and controller.saved == 1
                  and state("ALIGN_SAVE") == "Alert", "controller %s, ALIGN_SAVE %s" % (waiting, state("ALIGN_SAVE")))
            del controller.writes[:]
            points(7)
            press("MULTI_POINT_ALIGN", "ALIGN_START")
            ok = run_to_end()
            check("6 Start again continues the same alignment", ok and state("MULTI_POINT_ALIGN") == "Ok" and synced() == 3
                  and syncs() == 2 and not any(w.startswith(":A") for w in controller.writes)
                  and count("continuing the alignment") == 1, "writes %s, synced %d" % (controller.writes, synced()))
            check("7 the Bridge's reading connection sent only get commands (%d questions)" % controller.asked, not controller.forbidden)
        finally:
            os.close(pipe)
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
            web.shutdown()
        if not all(results):
            print("\n".join(messages[-40:]))
        return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
