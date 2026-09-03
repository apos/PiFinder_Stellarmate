"""Deterministic root-cause reproduction for the recurring "mount lands at/
near RA0/Dec0" bug (basic-memory pifinder-stellarmate/00107 §9). Simulates
the exact user action that most recently triggered it: rapid, repeated
manual tracking on/off toggling (each Mount-Bridge-driven correction
re-enables tracking as a side effect of ON_COORD_SET=TRACK - see §6 - a real
user immediately toggles it back off to keep testing drift, not waiting for
a fixed cadence). Randomized delay between toggles (per direct user
instruction 2026-09-03) so this isn't just hammering the exact same fixed-
interval pattern every cycle, which could itself mask or artificially
produce a different failure mode than an actual human would.

Watches Mount Bridge's own state every second throughout and immediately
dumps full context (all indicators + a live tail of the instrumented
LOGF_WARN this session added at the Fall-4 revert site) the moment anything
suspicious appears (drift blowing up, a position landing within a couple of
arcmin of RA0/Dec0, or a horizon-safety refusal in the log) - the goal is to
catch the EXACT tick where a bad value first enters the system, not just
notice the aftermath.
"""

import random
import subprocess
import sys
import time

MSG_LOG = "/tmp/claude-1000/-home-stellarmate/4395e939-5e43-4a6d-aa71-a40f6119ea5a/scratchpad/mount_bridge_messages_run3.log"


def indi_get(prop: str) -> str:
    out = subprocess.run(["indi_getprop", "-t", "3", "-1", prop], capture_output=True, text=True, timeout=5)
    return out.stdout.strip()


def indi_set(prop_value: str):
    try:
        subprocess.run(["indi_setprop", "-t", "8", prop_value], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"  (indi_set timed out: {prop_value})")


def near_zero(ra_h, dec_d, tol_arcmin=5.0) -> bool:
    try:
        return abs(float(ra_h)) * 60 <= tol_arcmin and abs(float(dec_d)) * 60 <= tol_arcmin
    except (TypeError, ValueError):
        return False


def snapshot():
    return {
        "t": time.strftime("%H:%M:%S"),
        "track_on": indi_get("Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_ON"),
        "mount_ra": indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.RA"),
        "mount_dec": indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD.DEC"),
        "mount_state": indi_get("Telescope Simulator.EQUATORIAL_EOD_COORD._STATE"),
        "drift": indi_get("PiFinder Mount Bridge.DRIFT_STATUS.DRIFT_ARCMIN"),
        "orig_drift": indi_get("PiFinder Mount Bridge.ORIGINAL_TARGET_DRIFT.DRIFT_ARCMIN"),
    }


def dump_context(reason):
    print(f"\n!!! SUSPICIOUS STATE DETECTED: {reason} !!!")
    s = snapshot()
    for k, v in s.items():
        print(f"  {k}: {v}")
    print("--- last 20 lines of Mount Bridge message log ---")
    try:
        out = subprocess.run(["tail", "-20", MSG_LOG], capture_output=True, text=True, timeout=5)
        print(out.stdout)
    except Exception as e:
        print(f"(log read failed: {e})")


def main(cycles=25):
    print(f"Starting tracking on/off stress test - {cycles} cycles, randomized delays.")
    for i in range(cycles):
        indi_set("Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_OFF=On")
        off_wait = random.uniform(2.0, 9.0)
        time.sleep(off_wait)

        s = snapshot()
        print(f"[{i+1}/{cycles}] {s['t']} off_wait={off_wait:.1f}s track_on={s['track_on']} "
              f"drift={s['drift']} orig_drift={s['orig_drift']} mount=({s['mount_ra']},{s['mount_dec']})")

        if near_zero(s["mount_ra"], s["mount_dec"]):
            dump_context(f"mount position near RA0/Dec0 after cycle {i+1}")
            return
        try:
            if float(s["drift"]) > 500 or float(s["orig_drift"]) > 500:
                dump_context(f"drift indicator blew up after cycle {i+1}")
                return
        except (TypeError, ValueError):
            pass

        indi_set("Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_ON=On")
        on_wait = random.uniform(1.0, 6.0)
        time.sleep(on_wait)

        s = snapshot()
        print(f"           {s['t']} on_wait={on_wait:.1f}s track_on={s['track_on']} "
              f"drift={s['drift']} orig_drift={s['orig_drift']} mount=({s['mount_ra']},{s['mount_dec']})")

        if near_zero(s["mount_ra"], s["mount_dec"]):
            dump_context(f"mount position near RA0/Dec0 after cycle {i+1} (on-phase)")
            return
        try:
            if float(s["drift"]) > 500 or float(s["orig_drift"]) > 500:
                dump_context(f"drift indicator blew up after cycle {i+1} (on-phase)")
                return
        except (TypeError, ValueError):
            pass

    print("\nCompleted all cycles without reproducing the issue.")
    dump_context("final state after full run (for the record)")


if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    main(cycles)
