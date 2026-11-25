"""Clock checks for the Control Center (issue: wrong clocks make the Sky and the mount look wrong).

What can be seen from here, and what cannot:
  * The Pi's own clock: the Sky Position Panel and the Mount Bridge compute altitudes from it
    (driver: time(nullptr)). Visible: NTP state from systemd-timedatectl.
  * The clock last given to the mount (its INDI TIME_UTC). Visible, compared with the Pi's clock.
  * The simulation clock of a KStars on ANOTHER computer: not part of INDI, cannot be read.
    That is why the Sky shows the time it is computed for, so the user can compare.

evaluate() is a pure function so the thresholds and the debounce can be tested without a Pi.
"""
import datetime
import subprocess
import threading
import time

# Same figure as server._MOUNT_TIME_STALE_THRESHOLD_SEC: the watchdog corrects a mount clock that is
# older than this by itself (through the KStars on the Pi). Only a difference that is still there
# afterwards is worth a warning.
MOUNT_SKEW_THRESHOLD_SEC = 600.0
# A condition must last this long before it is shown: gives the automatic correction (and the NTP
# sync right after a boot) time to fix it first, and keeps a single odd reading from flashing a banner.
DEBOUNCE_SEC = 60.0
_NTP_CACHE_SEC = 30.0

_lock = threading.Lock()
_first_seen = {}          # kind -> time.time() of the first reading in the current streak
_ntp_cache = (0.0, None)  # (read at, value)
_tz_cache = (0.0, None)


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


def evaluate(now_utc, mount_utc, ntp_synced, now_mono, first_seen=None):
    """The status the page needs.

    now_utc / mount_utc: aware datetimes (mount_utc None when there is no mount or no reading).
    ntp_synced: True / False / None (unknown).
    now_mono: a monotonic-ish seconds value for the debounce.
    first_seen: dict kind -> start of the current streak; updated in place, so the caller keeps it
    between calls (the module-level one is used when it is None).
    """
    seen = _first_seen if first_seen is None else first_seen
    skew = None if mount_utc is None else (now_utc - mount_utc).total_seconds()
    conditions = {
        "mount_clock": skew is not None and abs(skew) > MOUNT_SKEW_THRESHOLD_SEC,
        "pi_clock": ntp_synced is False,
    }
    warn = {}
    for kind, active in conditions.items():
        if not active:
            seen.pop(kind, None)
            warn[kind] = False
            continue
        start = seen.setdefault(kind, now_mono)
        warn[kind] = (now_mono - start) >= DEBOUNCE_SEC
    return {
        "pi_time_utc": now_utc.isoformat(),
        "mount_time_utc": None if mount_utc is None else mount_utc.isoformat(),
        "mount_skew_sec": skew,
        "ntp_synced": ntp_synced,
        "mount_clock_warn": warn["mount_clock"],
        "pi_clock_warn": warn["pi_clock"],
    }


def status(mount_time_text):
    """evaluate() with the real clocks. mount_time_text is the mount's TIME_UTC string or None."""
    ntp = ntp_synchronized()
    tz = timezone_name()
    with _lock:  # the HTTP server is threaded; the debounce state is shared
        result = evaluate(
            datetime.datetime.now(datetime.timezone.utc),
            parse_utc(mount_time_text),
            ntp,
            time.monotonic(),
        )
    result["timezone"] = tz
    return result
