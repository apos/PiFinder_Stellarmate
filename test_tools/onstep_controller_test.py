#!/usr/bin/env python3
"""The Mount Bridge reads GoTos and alignments from an OnStep controller (#658).

    python3 test_tools/onstep_controller_test.py [path/to/indi_pifinder_mount_bridge]

Runs its own indiserver (port 7698, its own HOME) with the Bridge, a Telescope Simulator standing in for the PiFinder device,
a stand-in "LX200 OnStep" INDI driver (fake_onstep_indi_driver.py, configured for TCP port 9999) and a stand-in controller on
127.0.0.1:9998 that answers the LX200 get commands. The running system, PiFinder and any real controller are not touched. Any
command that would change something at the controller fails the test.
"""
import os
import socket
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

PORT = 7698
CONTROLLER_PORT = 9998   # the Bridge uses another port than the driver's (9999)
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "LX200 OnStep", "PiFinder LX200"
READ_ONLY = {":GU#", ":Gr#", ":Gd#", ":GR#", ":GD#", ":A?#"}


def hms(hours):
    s = round(hours * 3600) % 86400
    return "%02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def dms(degrees):
    s = round(abs(degrees) * 3600)
    return "%s%02d*%02d:%02d" % ("-" if degrees < 0 else "+", s // 3600, s // 60 % 60, s % 60)


class Controller(threading.Thread):
    """The state a test sets, answered like OnStep does."""

    def __init__(self):
        super().__init__(daemon=True)
        self.target, self.position = (1.0, 10.0), (1.0, 10.0)
        self.slewing, self.parking, self.align = False, False, "900"
        self.asked, self.forbidden = 0, []
        self.stray = False   # answer the next status with a lone "0", as the real controller once did
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", CONTROLLER_PORT))
        self.server.listen(4)

    def run(self):
        while True:
            client, _ = self.server.accept()
            threading.Thread(target=self.serve, args=(client,), daemon=True).start()

    def serve(self, client):
        buf = ""
        while True:
            data = client.recv(256)
            if not data:
                return
            buf += data.decode(errors="replace")
            while "#" in buf:
                command, buf = buf.split("#", 1)
                command += "#"
                if command not in READ_ONLY:
                    self.forbidden.append(command)
                    continue
                self.asked += 1
                if command == ":GU#" and self.stray:
                    self.stray = False
                    client.sendall(b"0#")
                    continue
                answer = {":GU#": ("npI/EW000" if self.parking else "np/EW000") if self.slewing else "nNp/EW000", ":Gr#": hms(self.target[0]),
                          ":Gd#": dms(self.target[1]), ":GR#": hms(self.position[0]), ":GD#": dms(self.position[1]),
                          ":A?#": self.align}[command]
                client.sendall((answer + "#").encode())

    def goto(self, ra, dec, seconds=4):
        """As the hand controller does it: target first, then the slew."""
        self.target = (ra, dec)
        self.slewing = True
        time.sleep(seconds)
        self.position = (ra, dec)
        self.slewing = False


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    controller = Controller()
    controller.start()
    late.PORT = PORT
    with tempfile.TemporaryDirectory(prefix="bridge-onstep-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        late.write_config(tmp)
        config = os.path.join(tmp, ".indi", "PiFinder Mount Bridge_config.xml")
        with open(config) as f:
            text = f.read().replace('"ACTIVE_MOUNT">Telescope Simulator<', '"ACTIVE_MOUNT">%s<' % MOUNT)
        with open(config, "w") as f:
            f.write(text)
        env = dict(os.environ, HOME=tmp)
        env.pop("INDICONFIG", None)
        log = open(os.path.join(tmp, "indiserver.log"), "w")
        server = subprocess.Popen(["indiserver", "-p", str(PORT), "-f", fifo, "-u", os.path.join(tmp, "sock")], env=env,
                                  stdout=log, stderr=log)
        pipe = os.open(fifo, os.O_RDWR)

        def command(line):
            os.write(pipe, (line + "\n").encode())

        def read(device, name):
            try:
                return indi_client.get_properties(device=device, port=PORT, timeout=6, stop_after={name}).get(device, {}).get(name)
            except indi_client.INDIClientError:
                return None

        def element(device, name, key):
            return (read(device, name) or {}).get("elements", {}).get(key)

        def until(what, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if what():
                    return True
                time.sleep(1)
            return False

        def target_is(ra, dec, source):
            values = (read(BRIDGE, "TARGET_STATUS") or {}).get("elements", {})
            return (bool(values) and abs(float(values["RA"]) - ra) < 0.001 and abs(float(values["DEC"]) - dec) < 0.02
                    and element(BRIDGE, "TARGET_STATUS_SOURCE", "SOURCE") == source)

        def connect(device):
            if not until(lambda: read(device, "CONNECTION"), 20):
                raise SystemExit("driver %s did not appear" % device)
            indi_client.set_switch(device, "CONNECTION", "CONNECT", port=PORT)

        results, messages = [], []

        def count(text):
            return sum(text in m for m in messages)

        def check(name, ok):
            results.append((name, ok))
            print("%s %s" % ("ok  " if ok else "FAIL", name), flush=True)

        threading.Thread(target=late.collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            command("start %s" % os.path.join(HERE, "fake_onstep_indi_driver.py"))
            connect(PIFINDER)
            if not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("the Bridge has no settings")
            if element(BRIDGE, "BRIDGE_SETTINGS", "INDISERVER_PORT") != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to the running indiserver")
            connect(BRIDGE)
            indi_client.set_switch(BRIDGE, "BRIDGE_MODE", "MODE_GOTO_FORWARD", port=PORT)
            check("the Bridge reads the controller on another port than the driver's",
                  until(lambda: (read(BRIDGE, "ONSTEP_WATCH") or {}).get("state") == "Ok", 40)
                  and element(BRIDGE, "ONSTEP_WATCH", "STATUS") == "reading 127.0.0.1:%d" % CONTROLLER_PORT)
            time.sleep(15)    # past the "just connected" window
            followed = "GoTo started on the OnStep controller"
            check("what the controller already holds is no GoTo", count(followed) == 0)

            controller.goto(5.5, 22.25)
            check("a GoTo on the hand controller becomes the Target and the Hold position",
                  until(lambda: target_is(5.5, 22.25, "OnStep controller"), 15) and count(followed) == 1)

            controller.stray = True
            time.sleep(6)
            check("a stray answer is not read as a slew", count(followed) == 1)

            controller.target = controller.position = (6.5, 30.0)    # a Sync: target and position jump, no slew
            time.sleep(10)
            check("a Sync on the controller is no GoTo", count(followed) == 1 and target_is(5.5, 22.25, "OnStep controller"))

            controller.position = (6.6, 31.0)                        # moved by hand, then "GoTo the same object" again
            time.sleep(6)
            controller.goto(6.5, 30.0)
            check("a GoTo to the object already set is followed", until(lambda: target_is(6.5, 30.0, "OnStep controller"), 15)
                  and count(followed) == 2)

            indi_client.set_switch(MOUNT, "ON_COORD_SET", "SLEW", port=PORT)
            indi_client.set_number(MOUNT, "EQUATORIAL_EOD_COORD", {"RA": 8.0, "DEC": 15.0}, port=PORT)
            controller.goto(8.0, 15.0)                               # the same GoTo as the controller sees it
            time.sleep(6)
            check("a GoTo that came through INDI is not counted twice", count(followed) == 2 and target_is(8.0, 15.0, "Mount"))

            controller.parking = True
            controller.goto(9.0, 60.0)                               # the park position, with a target of its own
            controller.parking = False
            time.sleep(6)
            check("parking is no GoTo", count(followed) == 2 and target_is(8.0, 15.0, "Mount"))

            controller.align = "913"
            check("an alignment on the controller is shown",
                  until(lambda: element(BRIDGE, "POSITIONING_PHASE", "PHASE") == "ALIGNING", 10))
            controller.goto(10.0, 40.0)
            time.sleep(6)
            check("its GoTos are not followed and are no Target", target_is(8.0, 15.0, "Mount")
                  and count("An alignment is running on the OnStep controller") == 1)
            controller.align = "900"
            check("afterwards the Bridge leaves the mount alone",
                  until(lambda: count("Alignment ended") == 1, 10)
                  and element(BRIDGE, "POSITIONING_PHASE", "PHASE") != "ALIGNING")
            controller.goto(11.0, 25.0)
            check("the next GoTo is followed again", until(lambda: target_is(11.0, 25.0, "OnStep controller"), 15))
            check("only get commands were sent to the controller (%d questions)" % controller.asked,
                  controller.asked > 100 and not controller.forbidden)
        finally:
            os.close(pipe)
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not all(ok for _, ok in results):
            print("\n".join(messages[-30:]) or "(no messages from the Bridge)")
        return 0 if results and all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
