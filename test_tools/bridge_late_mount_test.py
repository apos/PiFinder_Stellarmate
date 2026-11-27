#!/usr/bin/env python3
"""The Mount Bridge must bind a mount that appears after it connected, and bind it again after the mount driver was restarted.

    python3 test_tools/bridge_late_mount_test.py [path/to/indi_pifinder_mount_bridge]

Runs its own indiserver (port 7699, its own HOME) with the Bridge and two Telescope Simulators, one of them standing in for the
PiFinder device. The running system and PiFinder are not touched (the Bridge is given an unreachable PiFinder host).

Why: libindi only asks again, on a reconnect, for devices it already received once. A mount that was not there at the first
connection was never asked for again - the Bridge stayed blind until its process was restarted (found 2026-11-27, 11 minutes).
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gui_installer"))
import indi_client  # noqa: E402

PORT = 7699


def write_config(home):
    """The Bridge reads these before its first connection: without them it would connect to the RUNNING indiserver on port 7624."""
    texts = {"BRIDGE_SETTINGS": {"INDISERVER_HOST": "localhost", "INDISERVER_PORT": str(PORT), "PIFINDER_HTTP_HOST": "pifinder.invalid"},
             "ACTIVE_DEVICES": {"ACTIVE_PIFINDER": "PiFinder LX200", "ACTIVE_MOUNT": "Telescope Simulator"}}
    lines = ["<INDIDriver>"]
    for vector, values in texts.items():
        lines.append('<newTextVector device="PiFinder Mount Bridge" name="%s">' % vector)
        lines += ['<oneText name="%s">%s</oneText>' % item for item in values.items()]
        lines.append("</newTextVector>")
    lines.append('<newSwitchVector device="PiFinder Mount Bridge" name="BRIDGE_MODE">')
    lines += ['<oneSwitch name="%s">%s</oneSwitch>' % (n, "On" if n == "MODE_OFF" else "Off")
              for n in ("MODE_OFF", "MODE_VERIFY_ALERT", "MODE_AUTO_CORRECT", "MODE_GOTO_FORWARD")]
    lines += ["</newSwitchVector>", "</INDIDriver>"]
    os.mkdir(os.path.join(home, ".indi"))
    with open(os.path.join(home, ".indi", "PiFinder Mount Bridge_config.xml"), "w") as f:
        f.write("\n".join(lines))
BRIDGE, MOUNT, PIFINDER = "PiFinder Mount Bridge", "Telescope Simulator", "PiFinder LX200"


def collect_messages(messages):
    """The Bridge's own log messages (INDI <message>), for the report of a failure."""
    deadline = time.time() + 20
    while True:
        try:
            sock = socket.create_connection(("127.0.0.1", PORT), timeout=2)
            break
        except OSError:
            if time.time() > deadline:
                return
            time.sleep(0.5)
    sock.sendall(b'<getProperties version="1.7"/>\n')
    sock.settimeout(None)
    buf = ""
    while True:
        try:
            data = sock.recv(65536)
        except OSError:
            return
        if not data:
            return
        buf += data.decode(errors="replace")
        found = list(re.finditer(r'(?:<message |<set\w+Vector )[^>]*device="PiFinder Mount Bridge"[^>]*message="([^"]*)"', buf))
        messages.extend("%s %s" % (time.strftime("%H:%M:%S"), m.group(1)) for m in found)
        buf = buf[found[-1].end():] if found else buf[-4000:]


def main(argv):
    binary = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "indi_pifinder_bridge", "build",
                                                               "indi_pifinder_mount_bridge"))
    with tempfile.TemporaryDirectory(prefix="bridge-late-mount-") as tmp:
        fifo = os.path.join(tmp, "fifo")
        os.mkfifo(fifo)
        write_config(tmp)
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

        def known_dec():
            p = read(BRIDGE, "LAST_KNOWN_MOUNT_POS")
            values = list(p["elements"].values()) if p and p.get("state") == "Ok" else None
            return float(values[1]) if values else None

        def move_mount(dec):
            indi_client.set_switch(MOUNT, "ON_COORD_SET", "TRACK", port=PORT)
            indi_client.set_number(MOUNT, "EQUATORIAL_EOD_COORD", {"RA": 5.0, "DEC": dec}, port=PORT)

        def follows():
            """The Bridge's own record of the mount's position matches where the mount is, away from where it started."""
            mount = read(MOUNT, "EQUATORIAL_EOD_COORD")
            if not mount or mount.get("state") == "Busy" or known_dec() is None:
                return False
            dec = float(mount["elements"]["DEC"])
            return dec < 80 and abs(known_dec() - dec) < 1

        results, messages = [], []
        threading.Thread(target=collect_messages, args=(messages,), daemon=True).start()
        try:
            command('start %s -n "%s"' % (binary, BRIDGE))
            command('start indi_simulator_telescope -n "%s"' % PIFINDER)
            connect(PIFINDER)
            if not until(lambda: read(BRIDGE, "CONNECTION"), 20):
                raise SystemExit("the Bridge did not start")
            if not until(lambda: read(BRIDGE, "BRIDGE_SETTINGS"), 20):
                raise SystemExit("the Bridge has no settings")
            used = read(BRIDGE, "BRIDGE_SETTINGS")["elements"]["INDISERVER_PORT"]
            if used != str(PORT):
                raise SystemExit("refused: the test Bridge would connect to port %s" % used)
            connect(BRIDGE)
            time.sleep(25)                                  # connected without a mount: the first retries pass
            command('start indi_simulator_telescope -n "%s"' % MOUNT)
            connect(MOUNT)
            time.sleep(3)
            move_mount(30.0)
            ok = until(follows, 90)
            print("   mount %s | the Bridge's record %s" % ((read(MOUNT, "EQUATORIAL_EOD_COORD") or {}).get("elements"), known_dec()))
            results.append(("a mount that appears 25 s after the Bridge connected is read", ok))

            command('stop indi_simulator_telescope -n "%s"' % MOUNT)
            time.sleep(8)
            command('start indi_simulator_telescope -n "%s"' % MOUNT)
            connect(MOUNT)
            time.sleep(3)
            move_mount(55.0)
            ok = until(follows, 90)
            print("   mount %s | the Bridge's record %s" % ((read(MOUNT, "EQUATORIAL_EOD_COORD") or {}).get("elements"), known_dec()))
            results.append(("after the mount driver was restarted it is read again", ok))
        finally:
            os.close(pipe)
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not all(ok for _, ok in results):
            print("\n".join(messages[-16:]) or "(no messages from the Bridge)")
        for name, ok in results:
            print("%s %s" % ("ok  " if ok else "FAIL", name))
        return 0 if results and all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
