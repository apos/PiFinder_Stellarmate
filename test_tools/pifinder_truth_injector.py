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

PiFinder's own port (2026-09-06, basic-memory pifinder-stellarmate/00118):
by default this now auto-detects PiFinder's port the same way
gui_installer/server.py's _pifinder_status_snapshot() and
status_page.html's piFinderProbeUrls() do, instead of assuming a fixed
8080. Found live: PiFinder's web server prefers port 80 and only falls
back to 8080 if 80 is already taken - a truth injector hardcoded to one of
the two can silently POST into the void for an entire session if PiFinder
happened to come up on the other one, which looked like "the injector
isn't reactivating fake_solve_active after a PiFinder restart" but was
really just POSTs never reaching PiFinder at all.
"""

import argparse
import json
import time
import urllib.error
import urllib.request

from pifinder_indi_polling import read_ra_dec

DEFAULT_DEVICE = "PiFinder Simulator"
DEFAULT_INTERVAL = 2.0
# Same fallback order as gui_installer/server.py's _pifinder_status_snapshot()
# and status_page.html's piFinderProbeUrls(): 80/8080 for the real
# pifinder.service (with its historical port-80-busy fallback), 8081 for
# test_tools/fake_mode.sh's fake-hardware instance (FAKE_MODE_PORT in
# server.py).
CANDIDATE_PORTS = (80, 8080, 8081)


def resolve_pifinder_port(host: str, candidates=CANDIDATE_PORTS, timeout: float = 3.0) -> int | None:
    """Probes PiFinder's own /api/status on each candidate port in order,
    returns the first one that answers, or None if none do."""
    for port in candidates:
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=timeout):
                return port
        except Exception:
            continue
    return None


def read_fake_solve_active(host: str, port: int, timeout: float) -> bool | None:
    """Returns PiFinder's current fake_solve_active flag, or None if
    /api/status couldn't be read at all - kept distinct from "read fine,
    flag is false" so a POST-ok-but-state-didn't-change case is visible
    instead of looking identical to a plain read failure."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=timeout) as resp:
            return bool(json.loads(resp.read()).get("fake_solve_active", False))
    except Exception:
        return None


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
    # NOT "localhost": found live on the Pi5 (2026-09-06) that "localhost" can
    # resolve to ::1 first, which StellarMate's own nginx also listens on for
    # port 80 - a request there gets a connection reset from the wrong
    # service instead of a clean refusal from the right one, defeating the
    # port auto-detection below. gui_installer/server.py's
    # _pifinder_status_snapshot() already avoids this the same way; PiFinder
    # itself only ever binds IPv4 (0.0.0.0), so 127.0.0.1 is always correct.
    parser.add_argument("--pifinder-host", default="127.0.0.1")
    parser.add_argument("--pifinder-port", type=int, default=None,
                         help="Fixed PiFinder port to use for the whole run. Default: "
                              f"auto-detect via an /api/status probe over {CANDIDATE_PORTS} "
                              "(same fallback PiFinder's own web server and the Control "
                              "Center use), re-probed automatically whenever the current "
                              "port stops answering - e.g. after a PiFinder restart.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                         help="Seconds between injections (default: %(default)s)")
    args = parser.parse_args()

    fixed_port = args.pifinder_port
    current_port = fixed_port

    port_desc = str(fixed_port) if fixed_port else f"auto-detect {CANDIDATE_PORTS}"
    print(f"Polling '{args.indi_device}' on {args.indi_host}:{args.indi_port}, "
          f"injecting into PiFinder at {args.pifinder_host}:{port_desc} "
          f"every {args.interval}s. Ctrl-C to stop.")

    while True:
        start = time.monotonic()

        if current_port is None:
            current_port = resolve_pifinder_port(args.pifinder_host)
            if current_port is None:
                print(f"PiFinder not reachable on any of {CANDIDATE_PORTS} - retrying.")
                elapsed = time.monotonic() - start
                time.sleep(max(0.0, args.interval - elapsed))
                continue
            print(f"PiFinder found on port {current_port}.")

        pos = read_ra_dec(args.indi_host, args.indi_port, args.indi_device, timeout=3.0)
        if pos is None:
            print("No position available yet (device not connected?) - retrying.")
        else:
            ra_hours, dec_deg = pos
            ra_deg = ra_hours * 15.0
            ok = inject_fake_solve(args.pifinder_host, current_port, ra_deg, dec_deg, timeout=3.0)
            if not ok:
                status = "POST FAILED"
                if fixed_port is None:
                    # Port may have changed underneath us (e.g. PiFinder
                    # restarted and came up on the other one this time) -
                    # drop it so the next iteration re-probes instead of
                    # hammering a dead port forever.
                    current_port = None
            else:
                active = read_fake_solve_active(args.pifinder_host, current_port, timeout=3.0)
                if active is True:
                    status = "OK"
                elif active is False:
                    status = "POST OK BUT fake_solve_active STILL FALSE"
                else:
                    status = "POST OK BUT VERIFY READ FAILED"
            print(f"[{time.strftime('%H:%M:%S')}] RA {ra_hours:.4f}h / DEC {dec_deg:.4f} deg "
                  f"-> port {current_port or '?'}: {status}")

        elapsed = time.monotonic() - start
        time.sleep(max(0.0, args.interval - elapsed))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
