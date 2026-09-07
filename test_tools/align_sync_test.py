#!/usr/bin/env python3
"""
Isolated test for PiFinder_Stellarmate #313 - "Sync mount on a confirmed
PiFinder Align, regardless of Coupling mode" (docs/concepts/
mount_bridge_sync_on_pifinder_align.md).

Verifies the *Mount Bridge side* of the feature without needing a real sky
or the ability to drive PiFinder's on-device Align UI: it serves a mock
PiFinder /api/status on :8080 whose ``last_align_time`` / ``last_align_ra`` /
``last_align_dec`` fields this tool controls, then watches - over raw INDI
XML on :7624, same as multipoint_alignment_trace.py - whether the running
``PiFinder Mount Bridge`` driver Syncs the linked mount to the injected
Align position.

WHAT IT CHECKS
  1. A newly-appearing Align (last_align_time increases) -> the mount's
     EQUATORIAL_EOD_COORD jumps to (last_align_ra, last_align_dec) within a
     couple of poll cycles, with TELESCOPE state staying Ok (a Sync, never
     Busy/a slew).
  2. Coupling = Off  -> NO reaction (must stay decoupled).
  3. Coupling = Verify/Alert only -> DOES react (owner decision 2026-09-08),
     and the driver log carries the "Verify/Alert ... one exception" INFO
     line.
  4. Re-serving the same last_align_time -> no second Sync (dedup).

PREREQUISITES (run these first, by hand - this tool does not touch services)
  * The #313 build is installed: rebuilt indi_pifinder_mount_bridge, and
    PiFinder patched with the new /api/status fields (only relevant for the
    real end-to-end test; this tool mocks /api/status so it is not needed
    here).
  * ``sudo systemctl stop pifinder.service`` - frees :8080 for the mock and
    stops the real /api/status from racing it. (The Mount Bridge loses its
    real position source meanwhile; that is fine, this test only exercises
    the Align-sync path.)
  * A Full-Simulation INDI profile running with ``PiFinder Mount Bridge``
    linked to a mount (Telescope Simulator). Ekos/Web Manager as usual.

USAGE
    sudo systemctl stop pifinder.service
    python3 test_tools/align_sync_test.py
    python3 test_tools/align_sync_test.py --mount "Telescope Simulator"
    # afterwards:
    sudo systemctl start pifinder.service
"""

import argparse
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MOUNT_BRIDGE = "PiFinder Mount Bridge"

# A complete, plausible /api/status body. The Align fields are rewritten
# live by _MockStatus; everything else is static and only there so the
# driver's other /api/status readers don't choke.
_BASE_STATUS = {
    "power_state": 1,
    "solve_state": True,
    "camera_type": "imx296",
    "debug_solve": False,
    "fake_solve_active": True,
    "last_align_time": None,
    "last_align_ra": None,
    "last_align_dec": None,
    "location": {"lat": 48.2, "lon": 16.4, "altitude": 170.0, "timezone": "Europe/Vienna"},
    "solution": {
        "solve_source": "CAM",
        "last_solve_success": time.time(),
        "RA": 83.0,
        "Dec": -5.0,
    },
    "datetime": {"utc": None, "local": None},
    "imu": None,
    "sqm": None,
    "software_version": "align-sync-test",
}


class _MockStatus:
    """Thread-safe holder for the mutable Align fields + a fresh solve ts."""

    def __init__(self):
        self._lock = threading.Lock()
        self._align = {"last_align_time": None, "last_align_ra": None, "last_align_dec": None}

    def set_align(self, ra, dec):
        with self._lock:
            self._align = {
                "last_align_time": time.time(),
                "last_align_ra": float(ra),
                "last_align_dec": float(dec),
            }

    def body(self):
        with self._lock:
            d = dict(_BASE_STATUS)
            d.update(self._align)
            d["solution"] = dict(_BASE_STATUS["solution"], last_solve_success=time.time())
            return json.dumps(d).encode()


def _serve(mock, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.rstrip("/") != "/api/status":
                self.send_response(404)
                self.end_headers()
                return
            b = mock.body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# --------------------------------------------------------------------------
# Minimal raw-INDI reader (no PyIndi dependency, matching the other tools)
# --------------------------------------------------------------------------
def indi_snapshot(mount, host="127.0.0.1", port=7624, settle=2.5):
    """Return (ra_hours, dec_deg, scope_state) for `mount`, or (None, None, None)."""
    try:
        s = socket.create_connection((host, port), timeout=4)
    except OSError as e:
        print(f"  ! cannot reach indiserver {host}:{port}: {e}")
        return (None, None, None)
    s.settimeout(settle)
    s.sendall(f'<getProperties version="1.7" device="{mount}"/>'.encode())
    buf = b""
    deadline = time.time() + settle
    while time.time() < deadline:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
    s.close()
    text = buf.decode(errors="replace")
    ra = _num(text, "RA")
    dec = _num(text, "DEC")
    state = None
    for tag in ("setNumberVector", "defNumberVector"):
        i = text.rfind(f'<{tag} device="{mount}" name="EQUATORIAL_EOD_COORD"')
        if i != -1:
            seg = text[i : i + 400]
            for st in ("Busy", "Ok", "Alert", "Idle"):
                if f'state="{st}"' in seg:
                    state = st
                    break
            break
    return (ra, dec, state)


def _num(text, elem):
    key = f'name="{elem}"'
    i = text.rfind(key)
    if i == -1:
        return None
    j = text.find(">", i)
    k = text.find("<", j)
    if j == -1 or k == -1:
        return None
    try:
        return float(text[j + 1 : k].strip())
    except ValueError:
        return None


def _wait_for(mount, want_ra_deg, want_dec_deg, timeout=15.0, tol_deg=0.6):
    """Poll until the mount reports ~ (want_ra_deg, want_dec_deg). The driver
    converts J2000->JNow, so allow ~0.5deg of precession slack on top of the
    Sync's own rounding. Returns (reached, saw_busy, last_snapshot)."""
    saw_busy = False
    end = time.time() + timeout
    last = (None, None, None)
    while time.time() < end:
        ra_h, dec_d, state = indi_snapshot(mount, settle=1.0)
        last = (ra_h, dec_d, state)
        if state == "Busy":
            saw_busy = True
        if ra_h is not None and dec_d is not None:
            if abs(ra_h * 15.0 - want_ra_deg) < tol_deg and abs(dec_d - want_dec_deg) < tol_deg:
                return (True, saw_busy, last)
        time.sleep(1.0)
    return (False, saw_busy, last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mount", default="Telescope Simulator", help="linked mount device name")
    ap.add_argument("--port", type=int, default=8080, help="mock /api/status port")
    ap.add_argument("--ra", type=float, default=82.5, help="Align RA to inject, DEGREES J2000 (as /api/status reports it)")
    ap.add_argument("--dec", type=float, default=-5.4, help="Align Dec to inject, DEGREES J2000")
    args = ap.parse_args()

    try:
        probe = socket.create_connection(("127.0.0.1", args.port), timeout=1)
        probe.close()
        print(f"! port {args.port} is already in use - stop pifinder.service first.")
        sys.exit(2)
    except OSError:
        pass

    mock = _MockStatus()
    _serve(mock, args.port)
    print(f"mock /api/status on :{args.port}  (Align fields null until injected)")
    print(f"watching mount '{args.mount}' via INDI :7624\n")

    ra0, dec0, _ = indi_snapshot(args.mount)
    if ra0 is None:
        print("! could not read the mount's EQUATORIAL_EOD_COORD - is the Full-Sim profile up")
        print("  and 'PiFinder Mount Bridge' linked to the mount? Aborting.")
        sys.exit(1)
    print(f"mount starts at RA={ra0 * 15.0:.3f}deg ({ra0:.4f}h) Dec={dec0:.3f}deg")
    print(
        "Set the Coupling mode you want to test in the Control Center / INDI panel, then press "
        "Enter here to inject an Align.\n"
        "  expected: Off -> no move | any other mode -> Sync to the injected position, state stays Ok"
    )
    input("  [Enter] to inject Align > ")

    mock.set_align(args.ra, args.dec)
    print(f"injected Align: RA={args.ra:.3f}deg Dec={args.dec:.3f}deg J2000  ({time.strftime('%H:%M:%S')})")

    reached, saw_busy, last = _wait_for(args.mount, args.ra, args.dec)
    ra1, dec1, state1 = last
    print(f"\nafter ~12s: RA={ra1}h Dec={dec1}deg state={state1}  saw_busy={saw_busy}")
    if reached and not saw_busy:
        print("RESULT: mount Synced to the Align position, no slew (state never Busy).  [expected for any mode != Off]")
    elif reached and saw_busy:
        print("RESULT: mount reached the position but went Busy - that is a GoTo, not a Sync.  [BUG]")
    else:
        print("RESULT: mount did NOT move to the Align position.  [expected ONLY for Coupling = Off]")

    print(
        "\nAlso check the driver log (KStars INDI log, or journalctl on the indi service):\n"
        "  - any mode != Off:      'PiFinder Align confirmed - Synced mount to ...'\n"
        "  - Verify/Alert only:    ... '(Verify/Alert normally never writes the mount; ...)'\n"
        "  - press Enter again with the SAME injection still standing: NO second Sync line (dedup)."
    )
    input("  [Enter] to exit > ")


if __name__ == "__main__":
    main()
