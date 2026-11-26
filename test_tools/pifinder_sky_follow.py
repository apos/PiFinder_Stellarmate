#!/usr/bin/env python3
"""Keep PiFinder's Test Mode picture in step with a mount: the mount moves, the rendered sky moves with it.

Part of the realmode sky simulation (docs/concepts/pifinder_realmode_sky_simulation.md, issue #344). PiFinder's Test Mode
reads ~/PiFinder/test_images/pifinder_debug_02.png at every capture; this script watches the mount's position over INDI
and rewrites that file with a GSC star field for wherever the mount points. PiFinder's real solver then solves it.

    python3 test_tools/pifinder_sky_follow.py [--device "Telescope Simulator"] [--roll 0] [--fov 13.7]
    python3 test_tools/pifinder_sky_follow.py --slew-to 3.7867 24.12      # also send the mount there (JNow hours, degrees)

Turn Test Mode on in PiFinder (Tools > Test Mode, or POST /api/debug_solve). Stop with Ctrl-C; with --restore the original
test picture is put back then. Needs `gsc`, numpy and pillow (PiFinder's venv has both).
"""
import argparse
import datetime
import math
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_renderer as renderer  # noqa: E402

DEFAULT_IMAGE = os.path.expanduser("~/PiFinder/test_images/pifinder_debug_02.png")


# ---- JNow -> J2000 -------------------------------------------------------------------------------------------------

def julian_date(when=None):
    when = when or datetime.datetime.now(datetime.timezone.utc)
    return when.timestamp() / 86400.0 + 2440587.5


def _precession_angles(t):
    """IAU 1976 (Lieske) zeta, z, theta in radians for t Julian centuries from J2000."""
    arc = math.pi / (180.0 * 3600.0)
    zeta = (2306.2181 * t + 0.30188 * t ** 2 + 0.017998 * t ** 3) * arc
    z = (2306.2181 * t + 1.09468 * t ** 2 + 0.018203 * t ** 3) * arc
    theta = (2004.3109 * t - 0.42665 * t ** 2 - 0.041833 * t ** 3) * arc
    return zeta, z, theta


def _rotate(ra, dec, zeta, z, theta, inverse=False):
    if inverse:
        zeta, z, theta = -z, -zeta, -theta
    a = math.cos(dec) * math.sin(ra + zeta)
    b = math.cos(theta) * math.cos(dec) * math.cos(ra + zeta) - math.sin(theta) * math.sin(dec)
    c = math.sin(theta) * math.cos(dec) * math.cos(ra + zeta) + math.cos(theta) * math.sin(dec)
    return (math.atan2(a, b) + z) % (2 * math.pi), math.asin(max(-1.0, min(1.0, c)))


def j2000_to_jnow(ra_deg, dec_deg, jd=None):
    t = ((jd or julian_date()) - 2451545.0) / 36525.0
    ra, dec = _rotate(math.radians(ra_deg), math.radians(dec_deg), *_precession_angles(t))
    return math.degrees(ra), math.degrees(dec)


def jnow_to_j2000(ra_deg, dec_deg, jd=None):
    t = ((jd or julian_date()) - 2451545.0) / 36525.0
    ra, dec = _rotate(math.radians(ra_deg), math.radians(dec_deg), *_precession_angles(t), inverse=True)
    return math.degrees(ra), math.degrees(dec)


# ---- minimal INDI client -------------------------------------------------------------------------------------------

_NUMBER_VECTOR = re.compile(r"<(?:def|set)NumberVector\b([^>]*)>(.*?)</(?:def|set)NumberVector>", re.S)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_ONE_NUMBER = re.compile(r'<(?:def|one)Number\b([^>]*)>\s*([^<\s]+)\s*</(?:def|one)Number>', re.S)


def parse_number_vectors(buffer: str):
    """([(device, name, state, {element: float})], rest_of_buffer) for the complete number vectors in the text."""
    found = []
    end = 0
    for m in _NUMBER_VECTOR.finditer(buffer):
        attrs = dict(_ATTR.findall(m.group(1)))
        values = {}
        for one in _ONE_NUMBER.finditer(m.group(2)):
            name = dict(_ATTR.findall(one.group(1))).get("name")
            raw = one.group(2)
            try:
                values[name] = float(raw)
            except ValueError:
                parts = re.split(r"[:; ]", raw)  # sexagesimal "12:30:15"
                try:
                    sign = -1.0 if raw.strip().startswith("-") else 1.0
                    nums = [abs(float(p)) for p in parts if p]
                    values[name] = sign * sum(n / 60.0 ** i for i, n in enumerate(nums))
                except ValueError:
                    continue
        found.append((attrs.get("device"), attrs.get("name"), attrs.get("state"), values))
        end = m.end()
    return found, buffer[end:]


class MountWatcher(threading.Thread):
    """Follows EQUATORIAL_EOD_COORD of one INDI device; .position is (ra_hours, dec_deg, state) or None."""

    def __init__(self, device, host="localhost", port=7624):
        super().__init__(daemon=True)
        self.device, self.host, self.port = device, host, port
        self.position = None
        self.error = None
        self._sock = None

    def run(self):
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=10)
            self._sock.sendall(f'<getProperties version="1.7" device="{self.device}" name="EQUATORIAL_EOD_COORD"/>'.encode())
            self._sock.settimeout(None)
            buffer = ""
            while True:
                chunk = self._sock.recv(65536)
                if not chunk:
                    self.error = "INDI server closed the connection"
                    return
                buffer += chunk.decode("utf-8", "replace")
                vectors, buffer = parse_number_vectors(buffer)
                buffer = buffer[-200000:]
                for device, name, state, values in vectors:
                    if device == self.device and name == "EQUATORIAL_EOD_COORD" and "RA" in values and "DEC" in values:
                        self.position = (values["RA"], values["DEC"], state)
        except OSError as exc:
            self.error = str(exc)

    def slew(self, ra_hours, dec_deg):
        """Ask the mount to track to (JNow). Only used for self-tests; the simulator is the target."""
        msg = (f'<newSwitchVector device="{self.device}" name="ON_COORD_SET"><oneSwitch name="TRACK">On</oneSwitch></newSwitchVector>'
               f'<newNumberVector device="{self.device}" name="EQUATORIAL_EOD_COORD">'
               f'<oneNumber name="RA">{ra_hours:.6f}</oneNumber><oneNumber name="DEC">{dec_deg:.6f}</oneNumber></newNumberVector>')
        self._sock.sendall(msg.encode())


# ---- the loop ------------------------------------------------------------------------------------------------------

def angular_sep_deg(ra1, dec1, ra2, dec2):
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def write_atomically(frame, path):
    """PiFinder may read the file at any moment: never leave a half-written picture behind."""
    from PIL import Image
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(suffix=".png", dir=directory)
    os.close(fd)
    try:
        Image.fromarray(frame, "L").save(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def follow(args):
    watcher = MountWatcher(args.device, args.host, args.port)
    watcher.start()
    deadline = time.time() + 10
    while watcher.position is None and time.time() < deadline and watcher.error is None:
        time.sleep(0.1)
    if watcher.position is None:
        print(f"no position from '{args.device}' on {args.host}:{args.port}: {watcher.error or 'timeout'}", file=sys.stderr)
        return 2
    if args.slew_to:
        print(f"slewing '{args.device}' to RA {args.slew_to[0]} h, Dec {args.slew_to[1]} (JNow)")
        watcher.slew(*args.slew_to)

    last = None
    rendered = 0
    started = time.time()
    try:
        while args.duration is None or time.time() - started < args.duration:
            ra_h, dec, state = watcher.position
            ra_now = ra_h * 15.0
            ra2000, dec2000 = jnow_to_j2000(ra_now, dec)
            if last is None or angular_sep_deg(ra2000, dec2000, *last) >= args.min_move:
                t0 = time.time()
                frame, count = renderer.render_field(ra2000, dec2000, args.fov, args.roll, 512, args.faint_mag, False, args.seed)
                write_atomically(frame, args.image)
                last = (ra2000, dec2000)
                rendered += 1
                print(f"{time.strftime('%H:%M:%S')} mount {state:5} RA {ra_h:8.5f} h Dec {dec:+8.4f}  ->  J2000 {ra2000:8.4f} {dec2000:+8.4f}"
                      f"  ({count} stars, {time.time() - t0:.2f}s)", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if args.restore and os.path.exists(args.restore):
            shutil.copyfile(args.restore, args.image)
            print(f"restored {args.image} from {args.restore}")
    print(f"done, {rendered} pictures written")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default="Telescope Simulator", help="INDI device whose position is followed")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=7624)
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="PiFinder's Test Mode picture")
    ap.add_argument("--fov", type=float, default=13.7)
    ap.add_argument("--roll", type=float, default=0.0)
    ap.add_argument("--faint-mag", type=float, default=9.0)
    ap.add_argument("--seed", type=int, default=1, help="fixed noise seed: the same field gives the same picture")
    ap.add_argument("--interval", type=float, default=0.5, help="seconds between looks at the mount")
    ap.add_argument("--min-move", type=float, default=0.02, help="degrees the mount must move before a new picture")
    ap.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: until Ctrl-C)")
    ap.add_argument("--slew-to", nargs=2, type=float, metavar=("RA_H", "DEC"), help="send the mount to this JNow position first")
    ap.add_argument("--restore", metavar="PNG", help="put this picture back when the script ends")
    return follow(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
