"""Thresholds and debounce of gui_installer/clock_status.py, no Pi needed:  python3 test_tools/clock_status_test.py"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gui_installer"))
import clock_status as cs  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 25, 20, 58, 27, tzinfo=UTC)
failed = 0


def ok(cond, msg):
    global failed
    print(("ok:   " if cond else "FAIL: ") + msg)
    failed += 0 if cond else 1


def run(mount_offset_sec, ntp, t, seen):
    mount = None if mount_offset_sec is None else NOW - datetime.timedelta(seconds=mount_offset_sec)
    return cs.evaluate(NOW, mount, ntp, t, seen)


seen = {}
r = run(100, True, 0, seen)
ok(not r["mount_clock_warn"] and not r["pi_clock_warn"], "small skew and NTP synced: no warning")
ok(abs(r["mount_skew_sec"] - 100) < 1e-6, "skew = Pi clock minus mount clock (positive: mount behind)")

seen = {}
r = run(3 * 3600, True, 0, seen)
ok(not r["mount_clock_warn"], "a big skew is not shown at once (the automatic correction gets its time)")
r = run(3 * 3600, True, cs.DEBOUNCE_SEC - 1, seen)
ok(not r["mount_clock_warn"], "still not shown just before the debounce time")
r = run(3 * 3600, True, cs.DEBOUNCE_SEC, seen)
ok(r["mount_clock_warn"], "shown once it lasted the debounce time")
r = run(60, True, cs.DEBOUNCE_SEC + 10, seen)
ok(not r["mount_clock_warn"], "gone as soon as the skew is fixed")
r = run(3 * 3600, True, cs.DEBOUNCE_SEC + 20, seen)
ok(not r["mount_clock_warn"], "a new streak starts the debounce again")

seen = {}
run(-3 * 3600, True, 0, seen)
r = run(-3 * 3600, True, cs.DEBOUNCE_SEC, seen)
ok(r["mount_clock_warn"], "a mount ahead of the Pi counts too")

seen = {}
r = run(cs.MOUNT_SKEW_THRESHOLD_SEC, True, 0, seen)
r = run(cs.MOUNT_SKEW_THRESHOLD_SEC, True, 1000, seen)
ok(not r["mount_clock_warn"], "exactly at the threshold is still fine")

seen = {}
r = run(None, True, 0, seen)
r = run(None, True, 1000, seen)
ok(not r["mount_clock_warn"] and r["mount_skew_sec"] is None, "no mount reading: no warning")

seen = {}
run(0, False, 0, seen)
r = run(0, False, cs.DEBOUNCE_SEC, seen)
ok(r["pi_clock_warn"] and not r["mount_clock_warn"], "NTP not synchronised, after the debounce: Pi warning")
seen = {}
run(0, None, 0, seen)
r = run(0, None, 1000, seen)
ok(not r["pi_clock_warn"], "NTP state unknown: never a warning")

ok(cs.parse_utc("2026-11-25T20:52:22+00:00") == datetime.datetime(2026, 11, 25, 20, 52, 22, tzinfo=UTC), "TIME_UTC string parsed")
ok(cs.parse_utc("2026-11-25T20:52:22").tzinfo is not None, "a string without offset is taken as UTC")
ok(cs.parse_utc("") is None and cs.parse_utc("garbage") is None and cs.parse_utc(None) is None, "bad input gives None")

if failed:
    print(f"{failed} failed")
    sys.exit(1)
print("all ok")
