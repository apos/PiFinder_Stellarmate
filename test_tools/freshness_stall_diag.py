"""High-resolution diagnostic for the "Mount Bridge reacts very late to
drift" complaint (2026-09-03 live test, tracking-off/2' threshold). Polls
every ~0.3s (much tighter than the 2s Mount Bridge tick / drift_test_logger's
1s cadence) so a multi-tick freshness-gate stall can actually be caught in
the act instead of just seeing "frozen for ~19s" after the fact.

Three independent signals, same poll loop:
  - PiFinder's own /api/status: solve_source + last_solve_success age -
    exactly what httpGetPiFinderFreshCamPosition() itself gates on.
  - PiFinder Mount Bridge's own published DRIFT_STATUS/CORRECTION_AGE -
    what the driver is actually doing/showing.
  - Telescope Simulator's raw EQUATORIAL_EOD_COORD - ground truth of
    whether/how much the mount is actually moving.
"""

import csv
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pifinder_indi_polling import read_property, read_ra_dec  # noqa: E402

HOST = "127.0.0.1"
PORT = 7624
TIMEOUT = 1.5
INTERVAL_SEC = 0.3

OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/claude-1000/-home-stellarmate/4395e939-5e43-4a6d-aa71-a40f6119ea5a/scratchpad/freshness_stall_diag.csv"
)

FIELDS = [
    "t", "elapsed_s",
    "http_status_ok", "http_latency_ms", "solve_source", "solve_age_s",
    "telsim_ra_h", "telsim_dec_d", "telsim_state",
    "bridge_drift_arcmin", "bridge_drift_state", "bridge_correction_age_s",
]


def sample():
    row = {}
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(f"http://{HOST}:8080/api/status", timeout=TIMEOUT) as r:
            import json
            d = json.load(r)
        row["http_status_ok"] = True
        row["http_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        sol = d["solution"]
        row["solve_source"] = sol.get("solve_source")
        lss = sol.get("last_solve_success")
        row["solve_age_s"] = round(time.time() - lss, 2) if lss else None
    except Exception as e:
        row["http_status_ok"] = False
        row["http_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        row["solve_source"] = f"ERR:{e}"
        row["solve_age_s"] = None

    ra_ts, dec_ts = read_ra_dec(HOST, PORT, "Telescope Simulator", TIMEOUT) or (None, None)
    row["telsim_ra_h"] = ra_ts
    row["telsim_dec_d"] = dec_ts
    row["telsim_state"] = read_property(HOST, PORT, "Telescope Simulator", "EQUATORIAL_EOD_COORD", "_STATE", TIMEOUT)
    row["bridge_drift_arcmin"] = read_property(HOST, PORT, "PiFinder Mount Bridge", "DRIFT_STATUS", "DRIFT_ARCMIN", TIMEOUT)
    row["bridge_drift_state"] = read_property(HOST, PORT, "PiFinder Mount Bridge", "DRIFT_STATUS", "_STATE", TIMEOUT)
    row["bridge_correction_age_s"] = read_property(HOST, PORT, "PiFinder Mount Bridge", "CORRECTION_AGE", "AGE_SEC", TIMEOUT)
    return row


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    print(f"Logging to {OUT_PATH} every {INTERVAL_SEC}s - Ctrl+C to stop")
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        f.flush()
        while True:
            row = sample()
            row["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            row["elapsed_s"] = round(time.monotonic() - start, 2)
            writer.writerow(row)
            f.flush()
            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
