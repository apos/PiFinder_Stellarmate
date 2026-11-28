#!/usr/bin/env python3
""""Coupling off" stops a slew the Mount Bridge started itself, and no other one (#231).

    python3 test_tools/bridge_off_stops_slew_test.py [path/to/indi_pifinder_mount_bridge]

Own indiserver (port 7694, own HOME) with the Bridge, a Telescope Simulator as mount, a second one standing in for the PiFinder
device and a stand-in PiFinder web server (port 7690) whose "camera" sees what the mount reports. The running system, PiFinder
and the Control Center (which would re-apply its own coupling choice) are not involved.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
sys.path.insert(0, HERE)
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402
from mount_model_check import lst_hours, separation_deg  # noqa: E402
from pifinder_sky_follow import jnow_to_j2000  # noqa: E402

PORT, WEB = 7694, 7690
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "Telescope Simulator", "PiFinder LX200"
LATITUDE, LONGITUDE = 49.5, 8.45
SEEN = {"ra": 0.0, "dec": 45.0}   # where the mount is, JNow hours / degrees
STARS = []


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
        if urlparse(self.path).path.endswith("api/nearby_bright_stars"):
            return self.answer({"candidates": STARS})
        ra, dec = jnow_to_j2000(SEEN["ra"] * 15.0, SEEN["dec"])   # degrees in, degrees out, as PiFinder reports
        now = time.time() - 0.3
        self.answer({"solution": {"solve_source": "CAM", "last_solve_success": now, "last_solve_attempt": now,
                                  "RA": ra, "Dec": dec}, "location": {}})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.answer({})


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    web = ThreadingHTTPServer(("127.0.0.1", WEB), PiFinder)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-off-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        late.write_config(tmp)
        config = os.path.join(tmp, ".indi", "PiFinder Mount Bridge_config.xml")
        with open(config) as f:
            text = f.read().replace(">pifinder.invalid<", ">127.0.0.1:%d/x<" % WEB)
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

        def until(what, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if what():
                    return True
                time.sleep(0.5)
            return False

        def position():
            e = read(MOUNT, "EQUATORIAL_EOD_COORD")["elements"]
            return float(e["RA"]), float(e["DEC"])

        def slewing():
            return (read(MOUNT, "EQUATORIAL_EOD_COORD") or {}).get("state") == "Busy"

        def follow():
            while server.poll() is None:
                try:
                    SEEN["ra"], SEEN["dec"] = position()
                except (TypeError, KeyError, ValueError):
                    pass
                time.sleep(0.3)

        def coords(device, kind, target):
            indi_client.set_switch(device, "ON_COORD_SET", kind, port=PORT)
            time.sleep(0.3)
            indi_client.set_number(device, "EQUATORIAL_EOD_COORD", {"RA": target[0], "DEC": target[1]}, port=PORT)

        def coupling(mode):
            indi_client.set_switch(BRIDGE, "BRIDGE_MODE", mode, port=PORT)

        def away(target):
            return separation_deg(*position(), *target)

        results, messages = [], []

        def check(name, ok, text=""):
            results.append(ok)
            print("%s %s %s" % ("ok  " if ok else "FAIL", name, text), flush=True)

        def stops():
            return sum("stop sent to the mount" in m and "Coupling off" in m for m in messages)

        def targets():
            lst = lst_hours(LONGITUDE)
            return [((lst - 3.0) % 24, 30.0), ((lst + 3.0) % 24, 30.0), ((lst - 0.5) % 24, 65.0), ((lst + 0.5) % 24, 20.0)]

        def furthest():
            return max(targets(), key=away)

        def arrive(target, seconds=120):
            return until(lambda: away(target) < 1 and not slewing(), seconds)

        def settle(target):
            arrive(target)
            time.sleep(25)   # let the Bridge verify and refine until it holds the target

        def off_during(target, name, own):
            if not until(slewing, 30):
                return check(name, False, "the mount never started to slew")
            time.sleep(3)
            left, before = away(target), stops()
            coupling("MODE_OFF")
            if own:
                stopped = until(lambda: not slewing(), 6)
                time.sleep(2)
                here = position()
                time.sleep(10)
                still = not slewing() and separation_deg(*here, *position()) < 0.2
                check(name, left > 5 and stopped and still and away(target) > 3 and stops() == before + 1,
                      "(%.0f deg to go at the switch, stopped %s, still %s, ends %.0f deg short, stop messages %d)" %
                      (left, stopped, still, away(target), stops() - before))
            else:
                arrived = arrive(target)
                check(name, left > 5 and arrived and stops() == before,
                      "(%.0f deg to go at the switch, arrived %s, stop messages %d)" % (left, arrived, stops() - before))

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            for device in (PIFINDER, MOUNT):
                command('start indi_simulator_telescope -n "%s"' % device)
            for device in (PIFINDER, MOUNT):
                if not until(lambda: read(device, "CONNECTION"), 20):
                    raise SystemExit("driver %s did not appear" % device)
                indi_client.set_switch(device, "CONNECTION", "CONNECT", port=PORT)
            until(lambda: read(MOUNT, "GEOGRAPHIC_COORD"), 20)
            indi_client.set_number(MOUNT, "GEOGRAPHIC_COORD", {"LAT": LATITUDE, "LONG": LONGITUDE, "ELEV": 100}, port=PORT)
            if not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("the Bridge has no settings")
            if read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            threading.Thread(target=follow, daemon=True).start()
            coords(MOUNT, "TRACK", targets()[2])
            arrive(targets()[2])
            indi_client.set_switch(BRIDGE, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(4)

            coupling("MODE_GOTO_FORWARD")
            time.sleep(6)
            goal = furthest()
            coords(PIFINDER, "TRACK", goal)
            off_during(goal, "1 a GoTo from PiFinder is stopped", own=True)

            coupling("MODE_GOTO_FORWARD")
            time.sleep(6)
            goal = furthest()
            coords(MOUNT, "SLEW", goal)
            off_during(goal, "2 a GoTo sent to the mount runs on", own=False)

            coupling("MODE_GOTO_FORWARD")
            time.sleep(6)
            coords(PIFINDER, "TRACK", furthest())
            until(slewing, 30)
            time.sleep(3)
            goal = furthest()
            coords(MOUNT, "SLEW", goal)   # somebody else takes over while the Bridge's own GoTo runs
            time.sleep(1)
            off_during(goal, "3 a GoTo that took over from the Bridge's runs on", own=False)

            coupling("MODE_GOTO_FORWARD")
            time.sleep(6)
            held = furthest()
            coords(PIFINDER, "TRACK", held)
            settle(held)
            before = stops()
            coupling("MODE_OFF")
            time.sleep(3)
            check("4 coupling off while the mount stands sends nothing", stops() == before and not slewing(),
                  "(stop messages added %d)" % (stops() - before))
            elsewhere = furthest()
            coords(MOUNT, "SLEW", elsewhere)
            arrive(elsewhere)
            time.sleep(8)
            indi_client.set_switch(BRIDGE, "MANUAL_TRIGGER", "TRIGGER_GOTO_HELD", port=PORT)
            off_during(held, "5 Goto Push-To is stopped by choosing Off again", own=True)

            coupling("MODE_GOTO_FORWARD")
            time.sleep(6)
            del STARS[:]
            STARS.extend({"ra": ra, "dec": dec, "name": "Star %d" % n}
                         for n, (ra, dec) in enumerate(jnow_to_j2000(h * 15.0, d) for h, d in targets()))
            before, start = stops(), position()
            indi_client.set_switch(BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_START", port=PORT)
            moving = until(slewing, 30)
            time.sleep(2)
            coupling("MODE_OFF")
            time.sleep(4)
            run_on = slewing() or separation_deg(*start, *position()) > 5
            check("6 a Multi-Point Alignment is not stopped by the coupling", moving and run_on and stops() == before
                  and (read(BRIDGE, "MULTI_POINT_ALIGN") or {}).get("state") == "Busy",
                  "(moving %s, still running %s)" % (moving, run_on))
            indi_client.set_switch(BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_STOP", port=PORT)
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
