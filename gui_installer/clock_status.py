"""Time and location cross-check for the Control Center: KStars, the mount, PiFinder and this Pi.

KStars is the reference (the StellarMate app sets it, and it is meant to set the mount). What can be seen from here:
  * KStars (the one on this Pi, over D-Bus): its location and time zone, and whether its clock runs in real time. Its time is
    not readable; in real time it is the Pi's clock.
  * The mount's INDI properties GEOGRAPHIC_COORD and TIME_UTC. TIME_UTC is the value that was last SET (at connect, by KStars
    or by this page) - it does not run on. It says something about the clock only if we saw it being set (a first version
    compared it with "now" and reported a 5 hour error that did not exist, 2026-11-28).
  * An OnStep on the network answers with its own clock and site (read-only commands).
  * PiFinder's location and time (/api/status), this Pi's clock, time zone and NTP state.
  * The simulation clock of a KStars on ANOTHER computer cannot be read; the Sky shows the time it is computed for.

evaluate() is a pure function, so thresholds and debounce can be tested without a Pi.
"""
import datetime
import json
import math
import os
import socket
import subprocess
import threading
import time

MOUNT_SKEW_THRESHOLD_SEC = 600.0     # a value we saw being set (we look every 20 s, drivers publish late)
REAL_CLOCK_THRESHOLD_SEC = 120.0     # a clock that was read from the device
LOCATION_THRESHOLD_KM = 1.0
ONSTEP_LOCATION_THRESHOLD_KM = 3.0   # OnStep reports its site in whole arc minutes
OFFSET_THRESHOLD_H = 0.01
OBSERVATION_MAX_GAP_SEC = 90.0       # a change seen after a longer blind spell says nothing about when it happened
# A condition must last this long before it is shown: gives the start of a profile (KStars sets the mount) and the NTP sync
# after a boot their time, and keeps a single odd reading from opening the notice.
DEBOUNCE_SEC = 60.0
_NTP_CACHE_SEC = 30.0

_lock = threading.Lock()
_first_seen = {}          # problem kind -> time of the first reading in the current streak
_ntp_cache = (0.0, None)  # (read at, value)
_tz_cache = (0.0, None)


class TimeObservations:
    """When did a mount's TIME_UTC change? Only a change seen between two close looks tells anything about the clock."""

    def __init__(self):
        self.last = {}   # device -> (value, monotonic of the look)
        self.seen = {}   # device -> (value, UTC time at which it was seen to be set)
        self.lock = threading.Lock()

    def observe(self, device, value, now_utc, now_mono):
        with self.lock:
            previous = self.last.get(device)
            self.last[device] = (value, now_mono)
            if previous is None or now_mono - previous[1] > OBSERVATION_MAX_GAP_SEC:
                return
            if value and value != previous[0]:
                self.seen[device] = (value, now_utc)

    def set_now(self, device, value, now_utc, now_mono):
        """A value this program has just written and read back."""
        with self.lock:
            self.last[device] = (value, now_mono)
            self.seen[device] = (value, now_utc)

    def seen_at(self, device, value):
        with self.lock:
            entry = self.seen.get(device)
        return entry[1] if entry and entry[0] == value else None


observations = TimeObservations()


def parse_utc(text):
    """INDI's TIME_UTC string as an aware datetime, or None."""
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def east_longitude(longitude):
    """-180..180, east positive (INDI counts 0..360)."""
    return (longitude + 180.0) % 360.0 - 180.0


def location(latitude, longitude):
    latitude, longitude = number(latitude), number(longitude)
    if latitude is None or longitude is None or (abs(latitude) < 1e-6 and abs(longitude) < 1e-6):
        return None  # 0/0 is what an unset property says
    return (latitude, east_longitude(longitude))


def distance_km(a, b):
    la1, lo1, la2, lo2 = (math.radians(v) for v in (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(min(1.0, h)))


def _timedatectl(prop):
    try:
        out = subprocess.run(["timedatectl", "show", "-p", prop, "--value"],
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def ntp_synchronized(now=None):
    """True/False from systemd, None when it cannot be told (no timedatectl): never a warning then."""
    global _ntp_cache
    now = time.time() if now is None else now
    with _lock:
        if now - _ntp_cache[0] < _NTP_CACHE_SEC:
            return _ntp_cache[1]
    raw = _timedatectl("NTPSynchronized")
    value = None if raw is None else raw.lower() == "yes"
    with _lock:
        _ntp_cache = (now, value)
    return value


def timezone_name():
    """IANA name such as Europe/Berlin, or None."""
    global _tz_cache
    now = time.time()
    with _lock:
        if now - _tz_cache[0] < 3600.0 and _tz_cache[1] is not None:
            return _tz_cache[1]
    value = _timedatectl("Timezone")
    with _lock:
        _tz_cache = (now, value)
    return value


def pi_offset_hours():
    return datetime.datetime.now().astimezone().utcoffset().total_seconds() / 3600.0


def read_kstars(run=subprocess.run):
    """{"location": (lat, lon), "offset": hours, "elevation": m, "realtime": bool|None, "name": str} of the KStars on this Pi,
    None when it does not answer."""
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/%d/bus" % os.getuid())

    def ask(member):
        out = run(["qdbus6", "org.kde.kstars", "/KStars", "org.kde.kstars." + member], env=env, capture_output=True,
                  text=True, timeout=5)
        return json.loads(out.stdout) if out.returncode == 0 else None

    try:
        place = ask("location")
        if not place:
            return None
        result = {"location": location(place.get("latitude"), place.get("longitude")), "offset": number(place.get("tz")),
                  "elevation": number(place.get("elevation")) or 0.0, "name": place.get("name") or "", "realtime": None}
        states = ask("getToggleableActionStates")
        if isinstance(states, dict) and "clock_realtime" in states:
            result["realtime"] = bool(states["clock_realtime"])
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return None


def parse_onstep(replies):
    """OnStep's answers to :GX80# (UT) :GX81# (UT date) :Gt# :Gg# (west positive), or None."""
    try:
        h, m, s = (int(float(v)) for v in replies[":GX80#"].split(":"))
        month, day, year = (int(v) for v in replies[":GX81#"].split("/"))
        utc = datetime.datetime(2000 + year, month, day, h, m, s, tzinfo=datetime.timezone.utc)

        def degrees(text):
            sign = -1.0 if text.startswith("-") else 1.0
            parts = text.lstrip("+-").replace(":", "*").split("*")
            return sign * sum(float(p) / 60 ** i for i, p in enumerate(parts))

        return {"utc": utc, "location": location(degrees(replies[":Gt#"]), -degrees(replies[":Gg#"]))}
    except (KeyError, ValueError):
        return None


def read_onstep(host, driver_port, ports=(9996, 9997, 9998), connect=socket.create_connection):
    """The controller's own clock and site over a command port the INDI driver does not use. Read-only commands."""
    for port in ports:
        if port == driver_port:
            continue
        try:
            with connect((host, port), timeout=3) as link:
                link.settimeout(3)
                replies = {}
                for command in (":GX80#", ":GX81#", ":Gt#", ":Gg#"):
                    link.sendall(command.encode())
                    answer = b""
                    while not answer.endswith(b"#"):
                        data = link.recv(32)
                        if not data:
                            break
                        answer += data
                    replies[command] = answer.decode(errors="replace").rstrip("#")
        except OSError:
            continue
        result = parse_onstep(replies)
        if result:
            return result
    return None


def _span(seconds):
    minutes = round(abs(seconds) / 60)
    if minutes < 60:
        return "%d min" % minutes
    if minutes < 48 * 60:
        return "%d h %d min" % (minutes // 60, minutes % 60) if minutes % 60 else "%d h" % (minutes // 60)
    return "%d days" % round(minutes / 1440)


def _offset(hours):
    sign = "+" if hours >= 0 else "-"
    return "UTC%s%d:%02d" % (sign, int(abs(hours)), round(abs(hours) * 60) % 60)


def compare(inputs):
    """(rows for the table, problems [(kind, text)], mount skew in seconds or None).

    inputs: now (aware datetime), pi_offset (h), ntp (bool|None), kstars (read_kstars() or None), mount (None or {device,
    time_utc, offset, location, seen_utc, real}), pifinder (None or {location, utc})."""
    now, pi_offset = inputs["now"], inputs["pi_offset"]
    kstars, mount, pifinder = inputs.get("kstars"), inputs.get("mount"), inputs.get("pifinder")
    rows, problems, skew = [], [], None
    reference = kstars.get("location") if kstars else None

    def row(source, **values):
        entry = {"source": source, "time_utc": None, "note": "", "offset": None, "location": None, "wrong": []}
        entry.update(values)
        rows.append(entry)
        return entry

    def problem(entry, field, kind, text):
        entry["wrong"].append(field)
        problems.append((kind, text))

    def place(entry, kind, what, value, limit=LOCATION_THRESHOLD_KM):
        if reference and value and distance_km(reference, value) > limit:
            km = distance_km(reference, value)
            problem(entry, "location", kind, "%s is %s km from KStars' location." % (what, "%.0f" % km if km >= 10 else "%.1f" % km))

    if kstars:
        realtime = kstars.get("realtime")
        entry = row("KStars (reference)", time_utc=now if realtime else None, offset=kstars.get("offset"), location=reference,
                    note="" if realtime else "its clock is not on real time" if realtime is False else "clock state unknown")
        if realtime is False:
            problem(entry, "time", "kstars_clock", "KStars runs a simulated time. Switch it to real time (Time, Set Time to Now).")
        if kstars.get("offset") is not None and abs(kstars["offset"] - pi_offset) > OFFSET_THRESHOLD_H:
            problem(entry, "offset", "kstars_offset", "KStars works with %s, this Pi's time zone is %s now." %
                    (_offset(kstars["offset"]), _offset(pi_offset)))
    else:
        row("KStars (reference)", note="not reachable on this Pi: the location cannot be checked")

    if mount:
        real, value, seen = mount.get("real"), mount.get("time_utc"), mount.get("seen_utc")
        entry = row("Mount (%s)" % mount.get("device"), offset=mount.get("offset"), location=mount.get("location"))
        if real:
            skew = (now - real["utc"]).total_seconds()
            entry.update(time_utc=real["utc"], note="read from the mount")
            if abs(skew) > REAL_CLOCK_THRESHOLD_SEC:
                problem(entry, "time", "mount_time", "The mount's own clock is %s %s." %
                        (_span(skew), "behind" if skew > 0 else "ahead"))
        elif value:
            entry.update(time_utc=value, note="last time set on it (it does not run on)")
            if seen:
                skew = (seen - value).total_seconds()
                if abs(skew) > MOUNT_SKEW_THRESHOLD_SEC:
                    problem(entry, "time", "mount_time", "The time set on the mount was %s %s when it was set." %
                            (_span(skew), "behind" if skew > 0 else "ahead"))
        else:
            entry["note"] = "no time reported"
        if mount.get("offset") is not None and abs(mount["offset"] - pi_offset) > OFFSET_THRESHOLD_H:
            problem(entry, "offset", "mount_offset", "The mount has %s, this Pi's time zone is %s now." %
                    (_offset(mount["offset"]), _offset(pi_offset)))
        place(entry, "mount_location", "The mount's location (INDI)", mount.get("location"))
        if real and real.get("location") and "location" not in entry["wrong"]:
            place(entry, "mount_site", "The site stored in the mount", real["location"], ONSTEP_LOCATION_THRESHOLD_KM)

    if pifinder:
        entry = row("PiFinder", time_utc=pifinder.get("utc"), location=pifinder.get("location"))
        place(entry, "pifinder_location", "PiFinder's location", pifinder.get("location"))
        if pifinder.get("utc") and abs((now - pifinder["utc"]).total_seconds()) > REAL_CLOCK_THRESHOLD_SEC:
            difference = (now - pifinder["utc"]).total_seconds()
            problem(entry, "time", "pifinder_time", "PiFinder's clock is %s %s." %
                    (_span(difference), "behind" if difference > 0 else "ahead"))

    row("This Pi", time_utc=now, offset=pi_offset,
        note="not NTP-synced" if inputs.get("ntp") is False else "NTP-synced" if inputs.get("ntp") else "")
    return rows, problems, skew


def evaluate(inputs, now_mono, first_seen=None, immediately=False):
    """The status the page needs. A problem counts once it lasted DEBOUNCE_SEC (at once when the user asked: `immediately`).
    first_seen: dict kind -> start of the current streak, updated in place (the module's own when None)."""
    seen = _first_seen if first_seen is None else first_seen
    rows, problems, skew = compare(inputs)
    active = {kind for kind, _ in problems}
    if inputs.get("ntp") is False:
        active.add("pi_clock")
    for kind in list(seen):
        if kind not in active:
            del seen[kind]
    for kind in active:
        seen.setdefault(kind, now_mono)
    shown = {kind for kind in active if immediately or now_mono - seen[kind] >= DEBOUNCE_SEC}
    kstars, mount = inputs.get("kstars"), inputs.get("mount")
    for entry in rows:
        entry["time_utc"] = entry["time_utc"].isoformat() if entry["time_utc"] else None
    listed = [text for kind, text in problems if kind in shown]
    return {
        "pi_time_utc": inputs["now"].isoformat(),
        "ntp_synced": inputs.get("ntp"),
        "pi_clock_warn": "pi_clock" in shown,
        "mismatch": bool(listed),                           # lasted long enough: open the notice
        "current": [text for _, text in problems],          # what is wrong right now: the content of an open notice
        "mount_warn": any(kind.startswith("mount") for kind in shown),
        "problems": listed,
        "rows": rows,
        "mount_skew_sec": skew,
        "mount_device": mount.get("device") if mount else None,
        "can_set_mount": bool(mount and kstars and kstars.get("location") and kstars.get("realtime") is not False),
    }
