#!/usr/bin/env python3
"""Feed the "PiFinder Simulator" INDI device's position into PiFinder as a
fixed "sky truth", for testing Mount Bridge's Auto-correct/Verify-Alert
modes without a real mount or clear sky (see basic-memory
pifinder-stellarmate/00164).

Reads indi_pifinder_simulator/"PiFinder Simulator"'s EQUATORIAL_EOD_COORD on
every poll and POSTs it to PiFinder's own /api/fake_solve endpoint - even
when the value hasn't changed, so PiFinder's last_solve_success timestamp
stays fresh (exactly like a real camera re-solving the same star field every
cycle) instead of going stale and getting gated out by Mount Bridge's
SOLVE_FRESHNESS check.

Two independent devices are meant to be active at once during a simulated
test session: the real Telescope Simulator (the "mount", deliberately synced
right or wrong) and this device's target, "PiFinder Simulator" (the
independent PiFinder truth). This script is the missing link between the
two - PiFinder's own /api/fake_solve already exists, "PiFinder Simulator"
already exists as an INDI device; this just polls one and injects into the
other.

Uses the indi_getprop CLI (already relied on elsewhere in this project for
INDI diagnostics) rather than a full INDI client library, for a small,
dependency-free tool.
"""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request

DEFAULT_DEVICE = "PiFinder Simulator"
DEFAULT_INTERVAL = 2.0


def read_ra_dec(host: str, port: int, device: str, timeout: float) -> tuple[float, float] | None:
    """Returns (ra_hours, dec_deg) or None if the device isn't connected/available."""
    try:
        out = subprocess.run(
            ["indi_getprop", "-h", host, "-p", str(port), "-t", str(timeout),
             f"{device}.EQUATORIAL_EOD_COORD.RA", f"{device}.EQUATORIAL_EOD_COORD.DEC"],
            capture_output=True, text=True, timeout=timeout + 2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"indi_getprop failed: {e}")
        return None

    ra = dec = None
    for line in out.stdout.splitlines():
        if line.endswith(".RA") or ".RA=" in line:
            ra = float(line.rsplit("=", 1)[1])
        elif ".DEC=" in line:
            dec = float(line.rsplit("=", 1)[1])
    if ra is None or dec is None:
        return None
    return ra, dec


def inject_fake_solve(host: str, port: int, ra_deg: float, dec_deg: float, timeout: float) -> bool:
    body = json.dumps({"ra": ra_deg, "dec": dec_deg}).encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/api/fake_solve",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"fake_solve POST failed: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--indi-host", default="localhost")
    parser.add_argument("--indi-port", type=int, default=7624)
    parser.add_argument("--indi-device", default=DEFAULT_DEVICE)
    parser.add_argument("--pifinder-host", default="localhost")
    parser.add_argument("--pifinder-port", type=int, default=8080)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                         help="Seconds between injections (default: %(default)s)")
    args = parser.parse_args()

    print(f"Polling '{args.indi_device}' on {args.indi_host}:{args.indi_port}, "
          f"injecting into PiFinder at {args.pifinder_host}:{args.pifinder_port} "
          f"every {args.interval}s. Ctrl-C to stop.")

    while True:
        start = time.monotonic()
        pos = read_ra_dec(args.indi_host, args.indi_port, args.indi_device, timeout=3.0)
        if pos is None:
            print("No position available yet (device not connected?) - retrying.")
        else:
            ra_hours, dec_deg = pos
            ra_deg = ra_hours * 15.0
            ok = inject_fake_solve(args.pifinder_host, args.pifinder_port, ra_deg, dec_deg, timeout=3.0)
            status = "OK" if ok else "FAILED"
            print(f"[{time.strftime('%H:%M:%S')}] RA {ra_hours:.4f}h / DEC {dec_deg:.4f} deg -> fake_solve: {status}")

        elapsed = time.monotonic() - start
        time.sleep(max(0.0, args.interval - elapsed))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
