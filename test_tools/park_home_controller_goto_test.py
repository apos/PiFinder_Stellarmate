#!/usr/bin/env python3
"""Park is park, a hand controller GoTo over USB is a GoTo, and a mount with its own alignment is never synced on its own.

    python3 test_tools/park_home_controller_goto_test.py [path/to/indi_pifinder_mount_bridge]

Own indiserver (port 7696, own HOME) with the Bridge, the stand-in OnStep INDI driver in its USB (serial) mode, a stand-in
controller on 127.0.0.1:9999 that records what is written to it, a Telescope Simulator standing in for the PiFinder device and a
stand-in PiFinder web server (port 7691). The test plays the hand controller through the stand-in driver (position, Busy, the
status the real driver reads with :GU#). Nothing real is touched.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
sys.path.insert(0, HERE)
import indi_client  # noqa: E402
import bridge_late_mount_test as late  # noqa: E402
import onstep_usb_alignment_test as usb  # noqa: E402
from mount_model_check import lst_hours  # noqa: E402

PORT, WEB = 7696, 7691
BRIDGE, MOUNT, PIFINDER = usb.BRIDGE, usb.MOUNT, usb.PIFINDER
# ":GU#" answers; HOMING and HOME as measured on a real OnStep 10.14a (2026-11-28).
FREE, PARKING, PARKED, HOMING, HOME = "nNp/Eo060", "nI/Eo060", "nNP/Eo060", "npha/EW060", "nNpHa/Eo060"


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    usb.controller()
    web = ThreadingHTTPServer(("127.0.0.1", WEB), usb.PiFinder)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-park-goto-") as tmp:
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
            return usb.WRITES.count(":CM#")

        def target():
            e = (read(MOUNT, "TARGET_EOD_COORD") or {}).get("elements", {})
            return round(float(e.get("DEC", 0)), 3)

        def control(**elements):
            indi_client.set_text(MOUNT, "TEST_CONTROL", elements, port=PORT)

        def move(dec, off=0.5, **more):
            """The mount reports `dec` on the meridian; PiFinder sees `off` degrees beside it."""
            ra = lst_hours(8.45)
            usb.SEEN["ra"], usb.SEEN["dec"] = ra, dec + off
            control(RA="%.6f" % ra, DEC="%.6f" % dec, **more)

        def slew(start, end, off=0.5, during=None, after=None):
            """A slew the controller does itself: Busy over several positions, then standing at `end`."""
            if during:
                control(FLAGS=during)
            for step in (0.25, 0.5, 0.75):
                move(start + (end - start) * step, off, BUSY="1")
                time.sleep(2)
            move(end, off, BUSY="0")
            if after:
                control(FLAGS=after)

        def coupling(mode):
            indi_client.set_switch(BRIDGE, "BRIDGE_MODE", mode, port=PORT)

        results, messages = [], []

        def count(part):
            return sum(part in m for m in messages)

        def check(name, ok, text=""):
            results.append(ok)
            print("%s %s %s" % ("ok  " if ok else "FAIL", name, text), flush=True)

        def left_alone(name, action, seconds=30):
            """`action` must lead to no Sync, no GoTo and no new Push-To."""
            before = syncs(), target(), count("the new Push-To"), count("taken as a GoTo")
            action()
            time.sleep(seconds)
            after = syncs(), target(), count("the new Push-To"), count("taken as a GoTo")
            check(name, before == after, "(Syncs, GoTo target Dec, adopted, followed: %s -> %s)" % (before, after))

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            command("start %s" % os.path.join(HERE, "fake_onstep_indi_driver.py"))
            if not until(lambda: read(PIFINDER, "CONNECTION"), 20) or not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("drivers did not appear")
            if read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"] != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            late.PORT = PORT
            indi_client.set_switch(PIFINDER, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(2)
            move(60.0, off=0.0)
            indi_client.set_switch(BRIDGE, "CONNECTION", "CONNECT", port=PORT)
            time.sleep(5)
            coupling("MODE_GOTO_FORWARD")
            time.sleep(15)

            before = syncs()
            slew(60.0, 66.0)
            followed = until(lambda: abs(target() - 66.0) < 0.01, 60)
            check("1 a controller GoTo is followed: synced and sent there again", followed and syncs() > before,
                  "(target Dec %s, Syncs %d)" % (target(), syncs() - before))
            usb.SEEN["dec"] = 66.0  # the refine arrived
            time.sleep(20)

            adopted, gotos = count("the new Push-To"), count("taken as a GoTo")
            before = syncs()
            move(63.0)  # direction buttons: no Busy
            ok = until(lambda: count("the new Push-To") > adopted and syncs() > before, 60)
            time.sleep(10)
            check("2 a movement with the direction buttons is taken over, not driven back",
                  ok and count("taken as a GoTo") == gotos and abs(target() - 66.0) < 0.01, "(target Dec %s)" % target())

            left_alone("3 parking from the controller: nothing synced, followed or taken over",
                       lambda: slew(63.0, 80.0, during=PARKING, after=PARKED))
            left_alone("4 unparked and standing: still nothing", lambda: control(FLAGS=FREE), 25)
            left_alone("5 going home from the controller", lambda: slew(80.0, 85.0, during=HOMING, after=HOME))
            left_alone("6 switching the coupling on while at home does not sync",
                       lambda: (coupling("MODE_OFF"), time.sleep(4), coupling("MODE_GOTO_FORWARD")), 20)

            adopted, before = count("the new Push-To"), syncs()
            control(FLAGS=FREE)
            time.sleep(6)
            move(70.0)  # away from home with the direction buttons
            check("7 leaving home with the direction buttons is taken over again",
                  until(lambda: count("the new Push-To") > adopted and syncs() > before, 60))
            time.sleep(10)

            left_alone("8 a way home stopped half way", lambda: slew(70.0, 76.0, during=HOMING, after=FREE))

            indi_client.set_switch(BRIDGE, "MOUNT_OWN_ALIGNMENT", "OWN_ALIGNMENT_ON", port=PORT)
            time.sleep(4)
            before = syncs()
            move(64.0)
            offered = until(lambda: (read(BRIDGE, "MOUNT_SYNC_OFFER") or {}).get("state") == "Alert", 60)
            time.sleep(15)
            check("9 own alignment: a movement is not synced, the Sync is offered", offered and syncs() == before,
                  "(offered %s, Syncs %d)" % (offered, syncs() - before))
            coupling("MODE_OFF")
            time.sleep(4)
            coupling("MODE_AUTO_CORRECT")
            time.sleep(25)
            coupling("MODE_GOTO_FORWARD")
            time.sleep(15)
            check("10 own alignment: switching the coupling and Auto-correct sync nothing", syncs() == before,
                  "(Syncs %d)" % (syncs() - before))
            indi_client.set_switch(BRIDGE, "MANUAL_TRIGGER", "TRIGGER_SYNC_NOW", port=PORT)
            check("11 own alignment: the Sync on request still works", until(lambda: syncs() > before, 20))
            time.sleep(8)
            before = syncs()
            slew(64.0, 58.0)
            check("12 own alignment: a GoTo somebody asks for is still refined",
                  until(lambda: abs(target() - 58.0) < 0.01 and syncs() > before, 60), "(target Dec %s)" % target())
            with open(config) as f:
                saved = f.read()
            check("13 the setting is saved per mount", "OWN_ALIGNMENT_MOUNTS" in saved and MOUNT in saved.split("OWN_ALIGNMENT_MOUNTS")[-1])
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
