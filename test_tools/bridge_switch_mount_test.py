#!/usr/bin/env python3
"""Changing the active mount while the Mount Bridge is connected binds the new mount (#662, #216).

    python3 test_tools/bridge_switch_mount_test.py [path/to/indi_pifinder_mount_bridge]

Own indiserver (port 7695, own HOME) with the Bridge and three Telescope Simulators (one stands in for the PiFinder device).
The running system and PiFinder are not touched.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
sys.path.insert(0, HERE)
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402

PORT = 7695
BRIDGE, PIFINDER, FIRST, SECOND = "PiFinder Mount Bridge", "PiFinder LX200", "Telescope Simulator", "Second Mount"


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-switch-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        late.write_config(tmp)
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
                time.sleep(1)
            return False

        def connect(device):
            if not until(lambda: read(device, "CONNECTION"), 20):
                raise SystemExit("driver %s did not appear" % device)
            indi_client.set_switch(device, "CONNECTION", "CONNECT", port=PORT)

        def move(device, dec):
            indi_client.set_switch(device, "ON_COORD_SET", "TRACK", port=PORT)
            indi_client.set_number(device, "EQUATORIAL_EOD_COORD", {"RA": 5.0, "DEC": dec}, port=PORT)

        def follows(device):
            mount = read(device, "EQUATORIAL_EOD_COORD")
            known = read(BRIDGE, "LAST_KNOWN_MOUNT_POS")
            if not mount or mount.get("state") == "Busy" or not known or known.get("state") != "Ok":
                return False
            dec = float(mount["elements"]["DEC"])
            return dec < 80 and abs(float(list(known["elements"].values())[1]) - dec) < 1

        results, messages = [], []
        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()

        def check(name, ok):
            results.append(ok)
            print("%s %s" % ("ok  " if ok else "FAIL", name), flush=True)

        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            for device in (PIFINDER, FIRST, SECOND):
                command('start indi_simulator_telescope -n "%s"' % device)
            for device in (PIFINDER, FIRST, SECOND):
                connect(device)
            if not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("the Bridge has no settings")
            if read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            connect(BRIDGE)
            time.sleep(3)
            move(FIRST, 30.0)
            check("the first mount is read", until(lambda: follows(FIRST), 90))
            for round_, (target, dec) in enumerate(((SECOND, 55.0), (FIRST, 15.0)), 1):
                indi_client.set_text(BRIDGE, "ACTIVE_DEVICES", {"ACTIVE_MOUNT": target}, port=PORT)
                time.sleep(5)
                move(target, dec)
                check("switch %d while connected: \"%s\" is read" % (round_, target), until(lambda: follows(target), 60))
                binding = read(BRIDGE, "BRIDGE_BINDING") or {}
                check("switch %d: the Bridge reports that it reads its devices" % round_, binding.get("state") == "Ok")
        finally:
            os.close(pipe)
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not all(results):
            print("\n".join(messages[-20:]))
        return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
