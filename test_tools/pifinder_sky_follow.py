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
import signal
import socket
import sys
import json
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_renderer as renderer  # noqa: E402

DEFAULT_IMAGE = os.path.expanduser("~/PiFinder/test_images/pifinder_debug_02.png")
KEEP_AWAKE_URL = "http://127.0.0.1:8080/api/keep_awake"
KEEP_AWAKE_EVERY_SEC = 2.0


def keep_awake(url=KEEP_AWAKE_URL):
    """Tell PiFinder it is in use: the same call the Mount Bridge makes during a GoTo-Forward.

    PiFinder goes to sleep when nobody touches it and then takes a picture only every ~30 s; a slew would be solved at its
    start and its end only. One call counts for about 10 s, so it is repeated. Loopback only; changes no setting, and
    PiFinder falls back to its own sleep a few seconds after this script stops. True when PiFinder answered.
    """
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


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


_SWITCH_VECTOR = re.compile(r"<(?:set|def)SwitchVector\b([^>]*)>(.*?)</(?:set|def)SwitchVector>", re.S)
_ONE_SWITCH = re.compile(r"<one(?:Switch)\b([^>]*)>\s*(\w+)\s*</oneSwitch>|<def(?:Switch)\b([^>]*)>\s*(\w+)\s*</defSwitch>", re.S)


def parse_switch_vectors(buffer: str):
    """[(device, name, state, {switch: "On"/"Off"})] for the complete switch vectors in the text (set and def)."""
    found = []
    for m in _SWITCH_VECTOR.finditer(buffer):
        attrs = dict(_ATTR.findall(m.group(1)))
        values = {}
        for one in _ONE_SWITCH.finditer(m.group(2)):
            attr_text, raw = (one.group(1), one.group(2)) if one.group(1) is not None else (one.group(3), one.group(4))
            values[dict(_ATTR.findall(attr_text)).get("name")] = raw
        found.append((attrs.get("device"), attrs.get("name"), attrs.get("state"), values))
    return found


MOTION_PROPERTIES = ("TELESCOPE_MOTION_NS", "TELESCOPE_MOTION_WE")
MANUAL_SETTLE_SEC = 1.5  # after the last motion switch goes off, positions that were already on their way still count as motion


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
        # Every update arrives here, so a slew too short for a poll to catch is still seen: slew_count counts the starts
        # (state turns Busy), slew_from is where the mount reported itself just before the latest one.
        self.slew_count = 0
        self.slew_from = None
        self._last_idle = None
        self._prev_state = None
        # The hand controller (or any client) moving the mount by hand sets TELESCOPE_MOTION_NS/WE, not a slew: the scope really moves.
        self._motion = {}
        self._manual_until = 0.0

    def on_motion(self, name, values, now=None):
        """A TELESCOPE_MOTION_NS/WE update: while any direction is on, the mount moves by hand."""
        now = time.time() if now is None else now
        was = any(self._motion.values())
        self._motion[name] = any(v == "On" for v in values.values())
        if was and not any(self._motion.values()):
            self._manual_until = now + MANUAL_SETTLE_SEC

    def manual_active(self, now=None):
        now = time.time() if now is None else now
        return any(self._motion.values()) or now < self._manual_until

    def on_update(self, ra_hours, dec_deg, state):
        if state == "Busy" and self._prev_state != "Busy":
            self.slew_count += 1
            self.slew_from = self._last_idle
        if state != "Busy":
            self._last_idle = (ra_hours, dec_deg)
        self._prev_state = state
        self.position = (ra_hours, dec_deg, state)

    def run(self):
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=10)
            for prop in ("EQUATORIAL_EOD_COORD",) + MOTION_PROPERTIES:
                self._sock.sendall(f'<getProperties version="1.7" device="{self.device}" name="{prop}"/>'.encode())
            self._sock.settimeout(None)
            buffer = ""
            while True:
                chunk = self._sock.recv(65536)
                if not chunk:
                    self.error = "INDI server closed the connection"
                    return
                buffer += chunk.decode("utf-8", "replace")
                for device, name, _state, values in parse_switch_vectors(buffer):
                    if device == self.device and name in MOTION_PROPERTIES:
                        self.on_motion(name, values)
                vectors, buffer = parse_number_vectors(buffer)
                buffer = buffer[-200000:]
                for device, name, state, values in vectors:
                    if device == self.device and name == "EQUATORIAL_EOD_COORD" and "RA" in values and "DEC" in values:
                        self.on_update(values["RA"], values["DEC"], state)
        except OSError as exc:
            self.error = str(exc)

    def slew(self, ra_hours, dec_deg):
        """Ask the mount to track to (JNow). Only used for self-tests; the simulator is the target."""
        msg = (f'<newSwitchVector device="{self.device}" name="ON_COORD_SET"><oneSwitch name="TRACK">On</oneSwitch></newSwitchVector>'
               f'<newNumberVector device="{self.device}" name="EQUATORIAL_EOD_COORD">'
               f'<oneNumber name="RA">{ra_hours:.6f}</oneNumber><oneNumber name="DEC">{dec_deg:.6f}</oneNumber></newNumberVector>')
        self._sock.sendall(msg.encode())


# ---- the loop ------------------------------------------------------------------------------------------------------

def offset_position(ra_deg, dec_deg, east_arcmin, north_arcmin):
    """A sky position moved by a small east/north offset (the misalignment between what the mount says and where it points)."""
    dec = dec_deg + north_arcmin / 60.0
    ra = ra_deg + east_arcmin / 60.0 / max(math.cos(math.radians(dec_deg)), 1e-6)
    return ra % 360.0, max(-90.0, min(90.0, dec))


SYNC_JUMP_ARCMIN = 1.0


def east_north_arcmin(ra_deg, dec_deg, ra2_deg, dec2_deg):
    """(east, north) in arcminutes from the first position to the second (small angles)."""
    d_ra = (ra2_deg - ra_deg + 180.0) % 360.0 - 180.0
    return d_ra * math.cos(math.radians(dec_deg)) * 60.0, (dec2_deg - dec_deg) * 60.0


def absorb_sync(prev, cur, offset, manual=False):
    """A Sync moves only what the mount REPORTS; the real sky does not move. prev/cur: (ra_deg, dec_deg, state) of two looks
    at the mount; offset: (east, north) arcmin of the misalignment. Returns (new_offset, jump_arcmin_or_None).

    A jump of more than SYNC_JUMP_ARCMIN between two looks while the mount is not slewing in either of them is a Sync (a
    tracking mount moves a fraction of an arcminute between looks). The offset shrinks by that jump so that the rendered
    sky stays where it is.
    """
    if prev is None or prev[2] == "Busy" or cur[2] == "Busy" or manual:
        return offset, None  # moving (a slew, or the hand controller): the scope really moves, the sky follows it
    east, north = east_north_arcmin(prev[0], prev[1], cur[0], cur[1])
    jump = math.hypot(east, north)
    if jump <= SYNC_JUMP_ARCMIN:
        return offset, None
    return (offset[0] - east, offset[1] - north), jump


GOTO_ERROR_REF_DEG = 45.0   # the slew length the --goto-error-* values belong to
GOTO_ERROR_FLOOR = 0.05     # even a tiny slew lands this fraction of that error off (the mount is not perfect)
GOTO_ERROR_CAP = 1.5        # and a longer slew does not land more than this multiple off


def landing_error(goto_error, slew_deg, ref_deg=GOTO_ERROR_REF_DEG, floor=GOTO_ERROR_FLOOR):
    """(east, north) arcmin a finished GoTo lands off its target, or None for a perfect mount.

    goto_error is the error of a slew of ref_deg degrees. It grows with the length of the slew (a real mount points a short
    corrective slew much better than a long one), never below `floor` of it and never above GOTO_ERROR_CAP times it. An
    unknown slew length (None) counts as a reference slew.
    """
    if goto_error is None:
        return None
    factor = 1.0 if slew_deg is None or ref_deg <= 0 else max(floor, min(slew_deg / ref_deg, GOTO_ERROR_CAP))
    return (goto_error[0] * factor, goto_error[1] * factor)


NUDGE_FILE = os.path.expanduser("~/.pfsm/gsc_sim_nudge.json")


def take_nudge(path=NUDGE_FILE):
    """A one-off shift of the real sky against what the mount reports, as if the clutch slipped or the scope was bumped: the file
    {"east": arcmin, "north": arcmin} is read and removed. Returns (east, north) or None."""
    try:
        with open(path) as handle:
            data = json.load(handle)
        os.unlink(path)
        return float(data.get("east", 0.0)), float(data.get("north", 0.0))
    except (OSError, ValueError, TypeError, AttributeError):
        try:
            os.unlink(path)
        except OSError:
            pass
        return None


def read_target_pixel(config_path=os.path.expanduser("~/PiFinder_data/config.json")):
    """PiFinder's alignment point as (Y, X) in the 512x512 solve frame: the active telescope's, else the global one, else the centre."""
    try:
        cfg = json.load(open(config_path))
    except (OSError, ValueError):
        return (256.0, 256.0)

    def usable(v):
        return isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(n, (int, float)) for n in v)

    equipment = cfg.get("equipment") or {}
    scopes = equipment.get("telescopes") or []
    idx = equipment.get("active_telescope_index")
    if isinstance(idx, int) and 0 <= idx < len(scopes) and usable(scopes[idx].get("target_pixel")):
        return tuple(float(n) for n in scopes[idx]["target_pixel"])
    if usable(cfg.get("target_pixel")):
        return tuple(float(n) for n in cfg["target_pixel"])
    return (256.0, 256.0)


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


def file_signature(path):
    """(mtime_ns, size) of the picture, None when it is not there: what tells us somebody else replaced it."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def picture_replaced(path, written):
    """True when the file on disk is no longer the one this script wrote (an update or a git checkout put PiFinder's original
    picture back): the sky must be written again, even though the mount has not moved."""
    return written is not None and file_signature(path) != written


def reconnect(args, wait_sec, retry_sec=1.0):
    """A new watcher that has the mount's position, or None if INDI or the mount did not come back within wait_sec."""
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        watcher = MountWatcher(args.device, args.host, args.port)
        watcher.start()
        while watcher.position is None and watcher.error is None and watcher.is_alive() and time.time() < deadline:
            time.sleep(0.1)
        if watcher.position is not None and watcher.is_alive():
            return watcher
        if watcher._sock is not None:
            watcher._sock.close()
        time.sleep(retry_sec)
    return None


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

    target_yx = tuple(args.target_pixel) if args.target_pixel else read_target_pixel()
    # PiFinder's pixel p is the CENTRE of array index p - 0.5 (see the renderer); (Y, X) -> array (x, y)
    centre_xy = None if args.camera_centre else (target_yx[1] - 0.5, target_yx[0] - 0.5)
    print(f"alignment point (Y, X) = ({target_yx[0]:.1f}, {target_yx[1]:.1f}): "
          + ("ignored, the mount is rendered at the frame centre" if centre_xy is None else "the mount's position is rendered there")
          + f"; misalignment {args.misalign_east:+.1f}' east, {args.misalign_north:+.1f}' north", flush=True)
    offset = (args.misalign_east, args.misalign_north)
    goto_error = (args.goto_error_east, args.goto_error_north) if (args.goto_error_east or args.goto_error_north) else None
    seen_slews = watcher.slew_count
    prev_look = None
    last = None
    rendered = 0
    started = time.time()
    awake_at = 0.0
    awake_ok = None
    written = None
    lost = False
    settle_until = 0.0
    try:
        while args.duration is None or time.time() - started < args.duration:
            if not watcher.is_alive():
                # An INDI restart (profile stop/start) ends the connection. Going on would leave the picture frozen at the last position
                # while the page says the simulation runs: connect again. Only if INDI stays away, end - the Control Center's watchdog
                # then starts the simulation anew (gsc_sim.restore, which allows only a few restarts per ten minutes).
                print(f"{time.strftime('%H:%M:%S')} lost the connection to INDI ({watcher.error}): connecting again", flush=True)
                watcher = reconnect(args, args.reconnect_sec)
                if watcher is None:
                    lost = True
                    print(f"{time.strftime('%H:%M:%S')} INDI did not come back within {args.reconnect_sec:.0f} s: ending", flush=True)
                    break
                print(f"{time.strftime('%H:%M:%S')} connected again", flush=True)
                seen_slews, prev_look, last = watcher.slew_count, None, None
                # A restarted mount driver is a new session: no Sync history, and its position still jumps while it starts up. Taking
                # those jumps for Syncs moved the rendered sky by 180 degrees (found 2026-11-27, after an update).
                offset = (args.misalign_east, args.misalign_north)
                settle_until = time.time() + args.settle_sec
            if not args.no_keep_awake and time.time() - awake_at >= KEEP_AWAKE_EVERY_SEC:
                awake_at = time.time()
                ok = keep_awake(args.keep_awake_url)
                if ok != awake_ok:
                    print(f"{time.strftime('%H:%M:%S')} keep-awake: {'PiFinder answers' if ok else 'PiFinder does NOT answer (it may sleep between slew steps)'}", flush=True)
                    awake_ok = ok
            ra_h, dec, state = watcher.position
            ra_now = ra_h * 15.0
            ra2000, dec2000 = jnow_to_j2000(ra_now, dec)
            look = (ra2000, dec2000, state)
            jump = None
            if time.time() >= settle_until:
                offset, jump = absorb_sync(prev_look, look, offset, watcher.manual_active())
            prev_look = look
            nudge = take_nudge(args.nudge_file)
            if nudge is not None:
                offset = (offset[0] + nudge[0], offset[1] + nudge[1])
                print(f"{time.strftime('%H:%M:%S')} NUDGE: the real sky moved {nudge[0]:+.1f}' east, {nudge[1]:+.1f}' north against the mount's "
                      f"report (as if the clutch slipped) -> misalignment now {offset[0]:+.1f}' east, {offset[1]:+.1f}' north", flush=True)
                last = None
            slew_count, slew_from = watcher.slew_count, watcher.slew_from
            if slew_count > seen_slews and state != "Busy":
                # a slew started since the last look and the mount is still again: it has landed, however short it was
                seen_slews = slew_count
                slew_deg = angular_sep_deg(slew_from[0] * 15.0, slew_from[1], ra_now, dec) if slew_from else None
                error = landing_error(goto_error, slew_deg, args.goto_error_ref_deg, args.goto_error_floor)
                if error is not None:
                    offset = error
                    print(f"{time.strftime('%H:%M:%S')} GoTo finished ({'?' if slew_deg is None else f'{slew_deg:.2f}'} deg): the scope landed "
                          f"{offset[0]:+.1f}' east, {offset[1]:+.1f}' north of the target", flush=True)
                    last = None
            if jump is not None:
                print(f"{time.strftime('%H:%M:%S')} mount reports a SYNC of {jump:.1f}' -> misalignment now "
                      f"{offset[0]:+.1f}' east, {offset[1]:+.1f}' north (the sky itself did not move)", flush=True)
                last = None
            ra2000, dec2000 = offset_position(ra2000, dec2000, *offset)
            if picture_replaced(args.image, written):
                print(f"{time.strftime('%H:%M:%S')} the picture {args.image} was replaced by something else: writing the sky again", flush=True)
                last = None
            if last is None or angular_sep_deg(ra2000, dec2000, *last) >= args.min_move:
                t0 = time.time()
                frame, count = renderer.render_field(ra2000, dec2000, args.fov, args.roll, 512, args.faint_mag, False, args.seed, centre_xy=centre_xy)
                write_atomically(frame, args.image)
                written = file_signature(args.image)
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
    return 3 if lost else 0


def _stop_on_sigterm(signum, frame):
    raise KeyboardInterrupt  # the same clean exit as Ctrl-C: the original picture is put back


def main(argv=None):
    signal.signal(signal.SIGTERM, _stop_on_sigterm)  # stopped by the Control Center
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
    ap.add_argument("--reconnect-sec", type=float, default=180.0, help="how long to wait for INDI after it closed the connection")
    ap.add_argument("--settle-sec", type=float, default=20.0, help="after reconnecting, position jumps are not taken for Syncs this long")
    ap.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: until Ctrl-C)")
    ap.add_argument("--misalign-east", type=float, default=0.0, metavar="ARCMIN",
                    help="the real sky is this far EAST of where the mount says it points (simulated polar/cone error)")
    ap.add_argument("--misalign-north", type=float, default=0.0, metavar="ARCMIN", help="same, towards the north")
    ap.add_argument("--goto-error-east", type=float, default=0.0, metavar="ARCMIN",
                    help="a finished GoTo of --goto-error-ref-deg degrees lands the scope this far east of its target "
                         "(simulated pointing error); shorter slews land proportionally closer, longer ones farther")
    ap.add_argument("--goto-error-north", type=float, default=0.0, metavar="ARCMIN", help="same, towards the north")
    ap.add_argument("--goto-error-ref-deg", type=float, default=GOTO_ERROR_REF_DEG, metavar="DEG",
                    help="the slew length the --goto-error-* values belong to (0: every GoTo lands exactly that far off)")
    ap.add_argument("--goto-error-floor", type=float, default=GOTO_ERROR_FLOOR, metavar="FRACTION",
                    help="a very short slew still lands this fraction of the error off")
    ap.add_argument("--nudge-file", default=NUDGE_FILE, help="a JSON file {east, north} (arcmin) shifts the real sky once, as if the "
                    "clutch slipped (used for testing the Bridge's reaction to a disturbance)")
    ap.add_argument("--target-pixel", nargs=2, type=float, metavar=("Y", "X"),
                    help="PiFinder's alignment point (default: read from its config)")
    ap.add_argument("--camera-centre", action="store_true",
                    help="render the mount at the frame centre instead of at PiFinder's alignment point")
    ap.add_argument("--no-keep-awake", action="store_true", help="do not stop PiFinder from going to sleep while this runs")
    ap.add_argument("--keep-awake-url", default=KEEP_AWAKE_URL)
    ap.add_argument("--slew-to", nargs=2, type=float, metavar=("RA_H", "DEC"), help="send the mount to this JNow position first")
    ap.add_argument("--restore", metavar="PNG", help="put this picture back when the script ends")
    return follow(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
