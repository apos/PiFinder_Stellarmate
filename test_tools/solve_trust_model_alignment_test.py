#!/usr/bin/env python3
"""Uncertain plate solves are not used (#697), and a Sync counts on a mount that fits a model through its points (#702).

    python3 test_tools/solve_trust_model_alignment_test.py [path/to/indi_pifinder_mount_bridge]

Own indiserver (port 7692, own HOME) with the Bridge, two Telescope Simulators (the mount with the "SVD Math Plugin", and one
standing in for the PiFinder device) and a stand-in PiFinder web server (port 7689) whose solves carry the probability the test
chooses. Nothing real is touched.
"""
import json
import os
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
import gsc_sim  # noqa: E402
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402
from mount_model_check import lst_hours  # noqa: E402
from pifinder_sky_follow import jnow_to_j2000  # noqa: E402

PORT, WEB = 7692, 7689
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "Telescope Simulator", "PiFinder LX200"
LAT, LON = 49.5, 8.45
RIGHT, WRONG = 2e-148, 7e-6          # a right and the wrong solve seen on 2026-11-28
SEEN = {"ra": 0.0, "dec": 50.0, "prob": RIGHT}   # what PiFinder's camera sees, JNow hours / degrees


def stars(count):
    """Candidates around the meridian, well above the horizon."""
    now = lst_hours(LON)
    places = ((1.0, 55), (-1.0, 45), (0.3, 70), (-0.5, 35), (1.5, 40), (-1.5, 60), (0.0, 50), (0.8, 30))
    return [{"ra": ((now - h) % 24) * 15.0, "dec": float(d), "name": "Star %d" % (i + 1)} for i, (h, d) in enumerate(places[:count])]


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
        if "nearby_bright_stars" in self.path:
            count = int(parse_qs(urlparse(self.path).query).get("count", ["4"])[0])
            return self.answer({"candidates": stars(count)})
        ra, dec = jnow_to_j2000(SEEN["ra"] * 15.0, SEEN["dec"])
        now = time.time() - 0.3
        self.answer({"solution": {"solve_source": "CAM", "last_solve_success": now, "last_solve_attempt": now, "RA": ra, "Dec": dec,
                                  "Matches": 26 if SEEN["prob"] == WRONG else 108, "Prob": SEEN["prob"]}, "location": {}})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.answer({})


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    web = ThreadingHTTPServer(("127.0.0.1", WEB), PiFinder)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-trust-") as tmp:
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

        def number(device, name, element):
            return float((read(device, name) or {}).get("elements", {}).get(element, "nan"))

        def until(what, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if what():
                    return True
                time.sleep(1)
            return False

        def switch(device, name, element):
            indi_client.set_switch(device, name, element, port=PORT)

        results, messages = [], []

        def count(part):
            return sum(part in m for m in messages)

        def check(name, ok, text=""):
            results.append(ok)
            print("%s %s %s" % ("ok  " if ok else "FAIL", name, text), flush=True)

        def position():
            e = (read(MOUNT, "EQUATORIAL_EOD_COORD") or {}).get("elements", {})
            return float(e.get("RA", "nan")), float(e.get("DEC", "nan"))

        def goto(ra, dec):
            switch(MOUNT, "ON_COORD_SET", "SLEW")
            indi_client.set_number(MOUNT, "EQUATORIAL_EOD_COORD", {"RA": ra, "DEC": dec}, port=PORT)
            time.sleep(2)
            until(lambda: (read(MOUNT, "EQUATORIAL_EOD_COORD") or {}).get("state") != "Busy", 60)

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            command('start indi_simulator_telescope -n "%s"' % MOUNT)
            if not until(lambda: read(MOUNT, "CONNECTION"), 20) or not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("drivers did not appear")
            if read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            switch(PIFINDER, "CONNECTION", "CONNECT")
            switch(MOUNT, "CONNECTION", "CONNECT")
            time.sleep(3)
            indi_client.set_number(MOUNT, "GEOGRAPHIC_COORD", {"LAT": LAT, "LONG": LON, "ELEV": 100}, port=PORT)
            indi_client.set_text(MOUNT, "TIME_UTC", {"UTC": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "OFFSET": "0"},
                                 port=PORT)
            time.sleep(1)
            for prop, element in gsc_sim.SIMULATOR_MODEL_SWITCHES:
                switch(MOUNT, prop, element)
                time.sleep(1)
            start = (lst_hours(LON) - 0.2) % 24
            goto(start, 50.0)
            SEEN.update(ra=position()[0], dec=position()[1])
            switch(BRIDGE, "CONNECTION", "CONNECT")
            time.sleep(5)
            switch(BRIDGE, "CORRECTION_ACTION", "ACTION_SYNC")

            def seen_beside(prob):
                ra, dec = position()
                SEEN.update(ra=ra, dec=dec + 0.5, prob=prob)

            seen_beside(WRONG)
            before = position()
            switch(BRIDGE, "BRIDGE_MODE", "MODE_AUTO_CORRECT")
            time.sleep(25)
            check("1 an uncertain solve moves nothing: no Sync, and the Bridge says why",
                  count("sent SYNC to mount") == 0 and abs(position()[1] - before[1]) < 0.05 and count("plate solve is not used") >= 1,
                  "(Dec %.3f -> %.3f, syncs %d)" % (before[1], position()[1], count("sent SYNC to mount")))
            SEEN["prob"] = RIGHT
            check("2 a certain solve is used", until(lambda: count("sent SYNC to mount") >= 1, 30))
            switch(BRIDGE, "BRIDGE_MODE", "MODE_OFF")
            time.sleep(3)
            limit = read(BRIDGE, "SOLVE_CERTAINTY")
            if limit:
                indi_client.set_number(BRIDGE, "SOLVE_CERTAINTY", {"MIN_DIGITS": 0}, port=PORT)
                time.sleep(2)
            syncs = count("sent SYNC to mount")
            seen_beside(WRONG)
            switch(BRIDGE, "BRIDGE_MODE", "MODE_AUTO_CORRECT")
            check("3 with the limit at 0 every solve is taken", bool(limit) and until(lambda: count("sent SYNC to mount") > syncs, 30))
            switch(BRIDGE, "BRIDGE_MODE", "MODE_OFF")
            if limit:
                indi_client.set_number(BRIDGE, "SOLVE_CERTAINTY", {"MIN_DIGITS": 8}, port=PORT)
            with open(config) as f:
                check("4 the limit is saved", "SOLVE_CERTAINTY" in f.read())

            # Multi-Point Alignment: PiFinder sees the scope beside every GoTo target, differently each time, so the model cannot
            # pass through all points and report each of them.
            for prop, element in gsc_sim.SIMULATOR_MODEL_SWITCHES:
                switch(MOUNT, prop, element)
                time.sleep(1)
            SEEN["prob"] = RIGHT
            offsets = (0.25, -0.30, 0.20, -0.15, 0.30)
            stop = threading.Event()

            def camera():
                seen = []
                while not stop.is_set():
                    e = (read(MOUNT, "TARGET_EOD_COORD") or {}).get("elements", {})
                    if e:
                        target = (round(float(e["RA"]), 3), round(float(e["DEC"]), 3))
                        if target not in seen:
                            seen.append(target)
                        SEEN.update(ra=target[0], dec=target[1] + offsets[(len(seen) - 1) % len(offsets)])
                    time.sleep(0.5)

            threading.Thread(target=camera, daemon=True).start()
            config_now = (read(BRIDGE, "ALIGN_CONFIG") or {}).get("elements", {})
            indi_client.set_number(BRIDGE, "ALIGN_CONFIG", {**config_now, "POINT_COUNT": 3, "RADIUS_DEG": 90}, port=PORT)
            time.sleep(1)
            points = number(MOUNT, "ALIGNMENT_POINTSET_SIZE", "ALIGNMENT_POINTSET_SIZE")
            switch(BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_START")
            time.sleep(5)
            until(lambda: (read(BRIDGE, "MULTI_POINT_ALIGN") or {}).get("state") in ("Ok", "Alert"), 240)
            stop.set()
            counted = number(BRIDGE, "ALIGN_PROGRESS", "POINT_SYNCED")
            added = number(MOUNT, "ALIGNMENT_POINTSET_SIZE", "ALIGNMENT_POINTSET_SIZE") - points
            check("5 every point the mount took into its model counts", counted == 3 and added >= 3,
                  "(counted %.0f, the mount added %.0f)" % (counted, added))
            check("6 and the Bridge says so when the mount reports another position", count("alignment model") >= 1,
                  "(%d)" % count("alignment model"))
        finally:
            if not results or not all(results):
                print("\n".join(messages[-60:]))
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
