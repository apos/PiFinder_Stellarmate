"""One-off logger for a manual "turn tracking off, watch drift correction"
test session (2026-09-03, live user-driven test starting near beta
Trianguli). Polls the small set of INDI properties that matter for this -
PiFinder LX200's own reported position, PiFinder Simulator's position/target,
Telescope Simulator's position/target/track-state, and PiFinder Mount
Bridge's own DRIFT_STATUS/CORRECTION_AGE/TARGET_SOURCE_AGE - at a fixed
interval and writes one CSV row per sample, timestamped, so the whole episode
(tracking still on -> tracking off -> drift growing -> correction firing ->
tracking back on) can be reconstructed and plotted afterwards without having
to eyeball indi_getprop by hand while it's happening live.

Not a permanent test tool - ad hoc, deliberately not wired into
pifinder_indi_polling.py's shared primitives beyond reusing read_property/
read_ra_dec, since this is a one-shot diagnostic script for a single session,
not a piece of the standing Full-Simulation test rig.
"""

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pifinder_indi_polling import read_property, read_ra_dec  # noqa: E402

HOST = "127.0.0.1"
PORT = 7624
TIMEOUT = 2.0
INTERVAL_SEC = 1.0

OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/claude-1000/-home-stellarmate/4395e939-5e43-4a6d-aa71-a40f6119ea5a/scratchpad/drift_test_log.csv"
)

FIELDS = [
    "t", "elapsed_s",
    "lx200_ra_h", "lx200_dec_d",
    "pfsim_ra_h", "pfsim_dec_d", "pfsim_target_ra_h", "pfsim_target_dec_d",
    "telsim_ra_h", "telsim_dec_d", "telsim_state",
    "telsim_target_ra_h", "telsim_target_dec_d",
    "telsim_track_on", "telsim_track_off",
    "bridge_drift_arcmin", "bridge_drift_state",
    "bridge_correction_age_s", "bridge_target_source_age_s",
    "bridge_target_source",
]


def sample():
    ra_lx, dec_lx = read_ra_dec(HOST, PORT, "PiFinder LX200", TIMEOUT) or (None, None)
    ra_pf, dec_pf = read_ra_dec(HOST, PORT, "PiFinder Simulator", TIMEOUT) or (None, None)
    ra_ts, dec_ts = read_ra_dec(HOST, PORT, "Telescope Simulator", TIMEOUT) or (None, None)

    row = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lx200_ra_h": ra_lx, "lx200_dec_d": dec_lx,
        "pfsim_ra_h": ra_pf, "pfsim_dec_d": dec_pf,
        "pfsim_target_ra_h": read_property(HOST, PORT, "PiFinder Simulator", "TARGET_EOD_COORD", "RA", TIMEOUT),
        "pfsim_target_dec_d": read_property(HOST, PORT, "PiFinder Simulator", "TARGET_EOD_COORD", "DEC", TIMEOUT),
        "telsim_ra_h": ra_ts, "telsim_dec_d": dec_ts,
        "telsim_state": read_property(HOST, PORT, "Telescope Simulator", "EQUATORIAL_EOD_COORD", "_STATE", TIMEOUT),
        "telsim_target_ra_h": read_property(HOST, PORT, "Telescope Simulator", "TARGET_EOD_COORD", "RA", TIMEOUT),
        "telsim_target_dec_d": read_property(HOST, PORT, "Telescope Simulator", "TARGET_EOD_COORD", "DEC", TIMEOUT),
        "telsim_track_on": read_property(HOST, PORT, "Telescope Simulator", "TELESCOPE_TRACK_STATE", "TRACK_ON", TIMEOUT),
        "telsim_track_off": read_property(HOST, PORT, "Telescope Simulator", "TELESCOPE_TRACK_STATE", "TRACK_OFF", TIMEOUT),
        "bridge_drift_arcmin": read_property(HOST, PORT, "PiFinder Mount Bridge", "DRIFT_STATUS", "DRIFT_ARCMIN", TIMEOUT),
        "bridge_drift_state": read_property(HOST, PORT, "PiFinder Mount Bridge", "DRIFT_STATUS", "_STATE", TIMEOUT),
        "bridge_correction_age_s": read_property(HOST, PORT, "PiFinder Mount Bridge", "CORRECTION_AGE", "AGE_SEC", TIMEOUT),
        "bridge_target_source_age_s": read_property(HOST, PORT, "PiFinder Mount Bridge", "TARGET_SOURCE_AGE", "AGE_SEC", TIMEOUT),
        "bridge_target_source": (
            "MOUNT" if read_property(HOST, PORT, "PiFinder Mount Bridge", "TARGET_SOURCE", "TARGET_SOURCE_MOUNT", TIMEOUT) == "On"
            else ("PIFINDER" if read_property(HOST, PORT, "PiFinder Mount Bridge", "TARGET_SOURCE", "TARGET_SOURCE_PIFINDER", TIMEOUT) == "On" else "?")
        ),
    }
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
            row["elapsed_s"] = round(time.monotonic() - start, 1)
            writer.writerow(row)
            f.flush()
            print(
                f"[{row['elapsed_s']:>6.1f}s] telsim_track={row['telsim_track_on']}/{row['telsim_track_off']} "
                f"state={row['telsim_state']} drift={row['bridge_drift_arcmin']}' "
                f"corr_age={row['bridge_correction_age_s']}s src={row['bridge_target_source']}"
            )
            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
