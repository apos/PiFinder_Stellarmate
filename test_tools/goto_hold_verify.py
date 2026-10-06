"""Correctly-precessed GoTo-hold verification - see docs/concepts/
coordinate_pipeline_reference.md's new section on manual test-harness
coordinate injection (2026-09-03). Every prior ad-hoc test this session used
a bare J2000 catalog RA/Dec written directly into Telescope Simulator's/
PiFinder Simulator's EQUATORIAL_EOD_COORD (both JNow) - a ~13-14' RA
precession-sized error, not a real bug. This script does it right and
reports all four indicators the use case actually needs:

  1. Original target (fixed, J2000) - recorded once at GoTo time.
  2. Mount vs PiFinder (Mount Bridge's own DRIFT_STATUS - necessary, not sufficient).
  3. Mount vs original target (precess mount JNow -> J2000 first).
  4. PiFinder vs original target (PiFinder's own /api/status is already J2000).

All four must stay under the configured threshold for the use case
("hold the GoTo'd target") to actually be satisfied - not just #2.
"""

import subprocess
import sys
import time
import urllib.request
import json

sys.path.insert(0, "/home/stellarmate/PiFinder/python/.venv/lib/python3.14/site-packages")
sys.path.insert(0, "/home/stellarmate/PiFinder/python/venv/lib/python3.14/site-packages")
from skyfield.api import load  # noqa: E402
from skyfield.positionlib import position_of_radec  # noqa: E402

_ts = load.timescale()


def j2000_to_jnow(ra_h: float, dec_d: float) -> tuple[float, float]:
    p = position_of_radec(ra_hours=ra_h, dec_degrees=dec_d, epoch=_ts.J2000)
    ra, dec, _ = p.radec(epoch=_ts.now())
    return ra.hours, dec.degrees


def sep_arcmin(ra1_h, dec1_d, ra2_h, dec2_d) -> float:
    import math
    ra1, dec1 = math.radians(ra1_h * 15), math.radians(dec1_d)
    ra2, dec2 = math.radians(ra2_h * 15), math.radians(dec2_d)
    cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1, min(1, cos_sep)))) * 60


def indi_get(prop: str) -> str:
    out = subprocess.run(["indi_getprop", "-t", "3", "-1", prop], capture_output=True, text=True, timeout=5)
    return out.stdout.strip()


def indi_set(prop_value: str):
    # Never let one slow/unresponsive property write take down the whole
    # test run (found live 2026-09-03: an ABORT_MOTION write hit exactly
    # the periodic transient indiserver/Mount Bridge slowness this project
    # has already documented - see basic-memory - and an uncaught
    # TimeoutExpired crashed the entire multi-target sequence over a single
    # command).
    try:
        subprocess.run(["indi_setprop", "-t", "8", prop_value], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"  (indi_set timed out: {prop_value})")


def pifinder_status():
    with urllib.request.urlopen("http://127.0.0.1:8080/api/status", timeout=3) as r:
        return json.load(r)


def goto(target_name: str, ra_j2000_h: float, dec_j2000_d: float):
    ra_jnow_h, dec_jnow_d = j2000_to_jnow(ra_j2000_h, dec_j2000_d)
    print(f"\n=== GoTo {target_name}: J2000 {ra_j2000_h:.4f}h/{dec_j2000_d:.4f} -> JNow {ra_jnow_h:.4f}h/{dec_jnow_d:.4f} ===")
    indi_set("Telescope Simulator.ON_COORD_SET.TRACK=On")
    indi_set(f"Telescope Simulator.EQUATORIAL_EOD_COORD.RA={ra_jnow_h};DEC={dec_jnow_d}")
    indi_set("PiFinder Simulator.ON_COORD_SET.SYNC=On")
    indi_set(f"PiFinder Simulator.EQUATORIAL_EOD_COORD.RA={ra_jnow_h};DEC={dec_jnow_d}")
    return ra_j2000_h, dec_j2000_d, ra_jnow_h, dec_jnow_d


def report(target_name, ra_j2000_h, dec_j2000_d):
    mount_ra_h = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.RA"))
    mount_dec_d = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.DEC"))
    mount_j2000_ra_h, mount_j2000_dec_d = _jnow_to_j2000(mount_ra_h, mount_dec_d)

    status = pifinder_status()
    sol = status["solution"]
    pf_ra_h = sol["RA"] / 15.0
    pf_dec_d = sol["Dec"]

    drift_mount_pifinder = float(indi_get("PiFinder Mount Bridge.DRIFT_STATUS.DRIFT_ARCMIN") or "nan")
    drift_original_indi = float(indi_get("PiFinder Mount Bridge.ORIGINAL_TARGET_DRIFT.DRIFT_ARCMIN") or "nan")

    ind2 = drift_mount_pifinder
    ind3 = sep_arcmin(mount_j2000_ra_h, mount_j2000_dec_d, ra_j2000_h, dec_j2000_d)
    ind4 = sep_arcmin(pf_ra_h, pf_dec_d, ra_j2000_h, dec_j2000_d)

    print(f"[{time.strftime('%H:%M:%S')}] target={target_name}")
    print(f"  (2) Mount vs PiFinder (Mount Bridge DRIFT_STATUS):      {ind2:.2f}'")
    print(f"  (3) Mount vs ORIGINAL target (script, J2000-corrected): {ind3:.2f}'")
    print(f"  (4) PiFinder vs ORIGINAL target (script):               {ind4:.2f}'")
    print(f"  (*) Mount Bridge's OWN ORIGINAL_TARGET_DRIFT indicator: {drift_original_indi:.2f}'")
    ok = all(v <= 2.0 for v in (ind2, ind3, ind4))
    print(f"  => {'PASS' if ok else 'FAIL'} (threshold 2.0')")
    return ind2, ind3, ind4


def _jnow_to_j2000(ra_h, dec_d):
    p = position_of_radec(ra_hours=ra_h, dec_degrees=dec_d, epoch=_ts.now())
    ra, dec, _ = p.radec(epoch=_ts.J2000)
    return ra.hours, dec.degrees


TARGETS = [
    ("Vega", 279.2250 / 15, 38.7833),
    ("Altair", 297.6750 / 15, 8.8667),
    ("Deneb", 310.3500 / 15, 45.2667),
    ("Alioth", 193.5000 / 15, 55.9500),
    ("Alkaid", 206.8750 / 15, 49.3000),
]

def wait_for_settle(target_ra_j2000_h=None, target_dec_j2000_d=None, max_wait_sec=60,
                     poll_interval=2.0, min_wait_sec=8.0):
    """Poll until Mount Bridge's own DRIFT_STATUS and ORIGINAL_TARGET_DRIFT
    both read below its configured threshold (or max_wait_sec elapses).

    Found live (2026-09-03): checking only "are both indicators below
    threshold right now" gave false-positive "settled" reads immediately
    after issuing a brand-new GoTo, before Mount Bridge's own tick (or
    truth_injector's 2s cycle) had even seen the new position once - both
    indicators were still reporting LEFTOVER state from before this GoTo
    was issued, which trivially passed. Two guards now: a mandatory
    min_wait_sec before the first check even happens, and - if a target is
    given - the mount's own live position must also actually be near it
    (not just "Mount Bridge's internal bookkeeping says OK"), so a stale
    read can't pass as "settled" just because the numbers happen to look
    fine."""
    time.sleep(min_wait_sec)
    threshold = float(indi_get("PiFinder Mount Bridge.DRIFT_THRESHOLD.THRESHOLD_ARCMIN") or "2.0")
    target_jnow = None
    if target_ra_j2000_h is not None:
        target_jnow = j2000_to_jnow(target_ra_j2000_h, target_dec_j2000_d)

    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        d1 = indi_get("PiFinder Mount Bridge.DRIFT_STATUS.DRIFT_ARCMIN")
        d2 = indi_get("PiFinder Mount Bridge.ORIGINAL_TARGET_DRIFT.DRIFT_ARCMIN")
        try:
            indicators_ok = float(d1) <= threshold and float(d2) <= threshold
        except (TypeError, ValueError):
            indicators_ok = False

        position_ok = True
        if indicators_ok and target_jnow is not None:
            mount_ra = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.RA"))
            mount_dec = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.DEC"))
            position_ok = sep_arcmin(mount_ra, mount_dec, target_jnow[0], target_jnow[1]) <= threshold

        if indicators_ok and position_ok:
            return True
        time.sleep(poll_interval)
    return False


def tracking_off_test(name, j2000_ra, j2000_dec, off_duration_sec=45):
    """Not a happy-path GoTo - turns tracking off on the currently-held
    target, lets real passive drift accumulate, then turns tracking back on
    (a correction re-engages it as a side effect - see ON_COORD_SET=TRACK)
    and waits for Mount Bridge to actually correct back. Reports all
    indicators both right after tracking-off (drift should be growing) and
    after the wait (should be back under threshold)."""
    print(f"\n=== Tracking OFF for {off_duration_sec}s (held target: {name}) ===")
    indi_set("Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_OFF=On")
    time.sleep(off_duration_sec)
    print(f"--- after {off_duration_sec}s tracking-off (before any correction) ---")
    report(name, j2000_ra, j2000_dec)
    settled = wait_for_settle(max_wait_sec=90)
    print(f"  (settled after re-enabling tracking via correction: {settled})")
    report(name, j2000_ra, j2000_dec)


def fullstop_test(name, j2000_ra, j2000_dec):
    """Not a happy-path GoTo - sends ABORT_MOTION right after issuing a
    GoTo, simulating a user hitting Stop/Abort. Telescope Simulator's own
    simulated slew completes near-instantly regardless of slew rate (found
    live 2026-09-03 - a genuine "mount stops short of target" scenario
    isn't reproducible with this particular simulator driver), so this
    mainly verifies Mount Bridge doesn't error/hang/misbehave when an abort
    lands on an already-arrived (or still-settling) mount, not that the
    mount is caught truly mid-flight."""
    print(f"\n=== Fullstop/Abort test (mid-GoTo to {name}) ===")
    indi_set("Telescope Simulator.ON_COORD_SET.TRACK=On")
    ra_jnow_h, dec_jnow_d = j2000_to_jnow(j2000_ra, j2000_dec)
    indi_set(f"Telescope Simulator.EQUATORIAL_EOD_COORD.RA={ra_jnow_h};DEC={dec_jnow_d}")
    indi_set("Telescope Simulator.ABORT_MOTION.ABORT=On")
    time.sleep(1)
    state = indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD._STATE")
    mount_ra = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.RA"))
    mount_dec = float(indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.DEC"))
    dist_from_target = sep_arcmin(mount_ra, mount_dec, ra_jnow_h, dec_jnow_d)
    print(f"  state={state} mount now {dist_from_target:.1f}' from the GoTo target (0' = slew completed anyway)")
    settled = wait_for_settle(max_wait_sec=60)
    print(f"  (Mount Bridge settled/recovered cleanly: {settled})")
    report(name, j2000_ra, j2000_dec)


if __name__ == "__main__":
    results = []
    for i, (name, j2000_ra, j2000_dec) in enumerate(TARGETS):
        goto(name, j2000_ra, j2000_dec)
        settled = wait_for_settle(j2000_ra, j2000_dec)
        print(f"  (settled: {settled})")
        ind2, ind3, ind4 = report(name, j2000_ra, j2000_dec)
        results.append((name, ind2, ind3, ind4))

        # Not happy-path: interleave a tracking-off drift test after the
        # 2nd target, and a fullstop/abort test after the 4th - realistic
        # user actions, not just a flat chain of successful GoTos.
        if i == 1:
            tracking_off_test(name, j2000_ra, j2000_dec)
        if i == 3:
            fullstop_test(name, j2000_ra, j2000_dec)
        time.sleep(1)

    print("\n=== Summary ===")
    for name, ind2, ind3, ind4 in results:
        ok = all(v <= 2.0 for v in (ind2, ind3, ind4))
        print(f"{name:10s} Mount-PiFinder={ind2:6.2f}'  Mount-Original={ind3:6.2f}'  PiFinder-Original={ind4:6.2f}'  {'PASS' if ok else 'FAIL'}")
