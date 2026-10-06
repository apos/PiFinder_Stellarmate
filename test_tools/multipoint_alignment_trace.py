#!/usr/bin/env python3
"""
Traces Mount Bridge's Multi-Point Alignment (#191) end to end, straight
against raw INDI XML on port 7624 - deliberately NOT through the Control
Center or any Python wrapper module, so what's captured is exactly what
INDI/KStars itself would show (matches TC-PFSM-191-01's own requirement).

What it does, in order:
  1. Baseline trace (no alignment running) for --baseline-secs, to capture
     the starting-condition mismatch between PiFinder's reported position
     and the mount's actual position before anything is touched.
  2. Triggers MULTI_POINT_ALIGN Start, keeps tracing until the sequence
     reaches Ok/Alert or --timeout-secs elapses.
  3. If --test-abort is given, starts a second run and sends ALIGN_STOP
     partway through, to verify the sequence actually stops (mount position
     and MULTI_POINT_ALIGN state both stop changing afterward).

Every observation is timestamped and printed live AND collected into a
report printed at the end - the report is what should be pasted into the
TC/TE issue, not just "it worked"/"it didn't".

Usage:
    python3 test_tools/multipoint_alignment_trace.py
    python3 test_tools/multipoint_alignment_trace.py --test-abort
    python3 test_tools/multipoint_alignment_trace.py --host localhost --port 7624
"""

import argparse
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass, field


MOUNT_BRIDGE = "PiFinder Mount Bridge"
PIFINDER_DEV = "PiFinder LX200"


def connect(host: str, port: int) -> socket.socket:
    s = socket.create_connection((host, port), timeout=10)
    s.settimeout(2.0)
    return s


def get_properties(host: str, port: int, device: str, wait: float = 1.5) -> str:
    """One-shot getProperties for a single device - returns raw XML text."""
    s = connect(host, port)
    s.sendall(f'<getProperties version="1.7" device="{device}"/>'.encode())
    time.sleep(wait)
    buf = b""
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            chunk = s.recv(1 << 16)
            if not chunk:
                break
            buf += chunk
        except socket.timeout:
            break
    s.close()
    return buf.decode(errors="replace")


def get_num(text: str, vector: str, elem: str):
    m = re.search(
        r'<def(Number)Vector[^>]*name="' + vector + r'"[^>]*>(.*?)</def\1Vector>',
        text,
        re.S,
    )
    if not m:
        return None
    m2 = re.search(r'<def(?:Number)? name="' + elem + r'"[^>]*>\s*([\-0-9.eE]+)', m.group(2))
    return float(m2.group(1)) if m2 else None


def get_switch_state(text: str, vector: str):
    m = re.search(r'<def(Switch)Vector[^>]*name="' + vector + r'"[^>]*state="(\w+)"', text)
    return m.group(2) if m else None


def get_active_mount(mb_text: str):
    m = re.search(
        r'<defTextVector[^>]*name="ACTIVE_DEVICES"[^>]*>(.*?)</defTextVector>', mb_text, re.S
    )
    if not m:
        return None
    m2 = re.search(r'<defText name="ACTIVE_MOUNT"[^>]*>\s*([^\s<][^<]*)', m.group(1))
    return m2.group(1).strip() if m2 else None


def send_switch(host: str, port: int, device: str, vector: str, switch: str):
    s = connect(host, port)
    s.sendall(
        (
            f'<newSwitchVector device="{device}" name="{vector}">'
            f'<oneSwitch name="{switch}">On</oneSwitch></newSwitchVector>'
        ).encode()
    )
    time.sleep(1.5)
    s.close()


@dataclass
class Sample:
    t: float
    pifinder_ra: float
    pifinder_dec: float
    mount_name: str
    mount_ra: float
    mount_dec: float
    drift_arcmin: float
    drift_state: str
    align_state: str


@dataclass
class WireEvent:
    t: float
    line: str


class WireCapture:
    """Persistent raw-socket listener - captures every setNumberVector/
    message frame from the mount device and Mount Bridge for the duration
    of the run, so the actual sequence of commanded Goto targets can be
    reconstructed afterward (Mount Bridge's own LOG_INFO/WARN messages are
    NOT reliable in indiserver's own log for this driver - see
    basic-memory/pifinder-stellarmate/00089 - so this captures the wire
    traffic directly instead of trusting log lines)."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.events: list[WireEvent] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._start_time = time.time()

    def start(self):
        self._thread.start()
        time.sleep(0.5)  # let the connection establish before returning

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self):
        s = connect(self.host, self.port)
        s.sendall(f'<getProperties version="1.7" device="{MOUNT_BRIDGE}"/>'.encode())
        s.sendall(f'<getProperties version="1.7" device="{PIFINDER_DEV}"/>'.encode())
        buf = ""
        pattern = re.compile(r"<(setNumberVector|setSwitchVector|message)\b[^>]*(?:/>|>.*?</\1>)", re.S)
        while not self._stop.is_set():
            try:
                chunk = s.recv(1 << 16)
                if not chunk:
                    break
                buf += chunk.decode(errors="replace")
            except socket.timeout:
                continue
            # Consume complete top-level elements as they arrive, tracking
            # how far into buf we've successfully parsed - re-scanning from
            # position 0 on every recv() (the original bug here) re-matches
            # and re-appends every already-seen event again each time,
            # producing O(n^2) duplicate "events" for what's really a
            # handful of distinct ones. Only the trailing partial fragment
            # (an element split across two recv() calls) is kept for the
            # next iteration.
            last_end = 0
            for m in pattern.finditer(buf):
                frag = m.group(0)
                if MOUNT_BRIDGE in frag or PIFINDER_DEV in frag:
                    self.events.append(WireEvent(t=time.time() - self._start_time, line=frag))
                last_end = m.end()
            buf = buf[last_end:]
        s.close()


def take_sample(host: str, port: int, t0: float, mount_name: str) -> Sample:
    pf_text = get_properties(host, port, PIFINDER_DEV, wait=1.0)
    mount_text = get_properties(host, port, mount_name, wait=1.0)
    mb_text = get_properties(host, port, MOUNT_BRIDGE, wait=1.0)
    return Sample(
        t=time.time() - t0,
        pifinder_ra=get_num(pf_text, "EQUATORIAL_EOD_COORD", "RA"),
        pifinder_dec=get_num(pf_text, "EQUATORIAL_EOD_COORD", "DEC"),
        mount_name=mount_name,
        mount_ra=get_num(mount_text, "EQUATORIAL_EOD_COORD", "RA"),
        mount_dec=get_num(mount_text, "EQUATORIAL_EOD_COORD", "DEC"),
        drift_arcmin=get_num(mb_text, "DRIFT_STATUS", "DRIFT_ARCMIN"),
        drift_state=get_switch_state(mb_text, "DRIFT_STATUS") or "?",
        align_state=get_switch_state(mb_text, "MULTI_POINT_ALIGN") or "?",
    )


def fmt_sample(s: Sample) -> str:
    def f(v):
        return f"{v:.4f}" if v is not None else "?"

    return (
        f"t={s.t:6.1f}s  pifinder=({f(s.pifinder_ra)},{f(s.pifinder_dec)})  "
        f"{s.mount_name}=({f(s.mount_ra)},{f(s.mount_dec)})  "
        f"drift={f(s.drift_arcmin)}' [{s.drift_state}]  align={s.align_state}"
    )


def run_trace(host, port, baseline_secs, timeout_secs, poll_interval, test_abort, abort_after_secs):
    mb_text = get_properties(host, port, MOUNT_BRIDGE, wait=1.5)
    mount_name = get_active_mount(mb_text)
    if not mount_name:
        print("ERROR: could not read ACTIVE_MOUNT from PiFinder Mount Bridge - aborting.")
        sys.exit(1)
    print(f"ACTIVE_MOUNT = '{mount_name}'  (tracing this + '{PIFINDER_DEV}')\n")

    t0 = time.time()
    samples: list[Sample] = []
    wire = WireCapture(host, port)
    wire.start()

    print(f"--- Phase 1: baseline trace, {baseline_secs}s, no alignment running ---")
    deadline = time.time() + baseline_secs
    while time.time() < deadline:
        s = take_sample(host, port, t0, mount_name)
        samples.append(s)
        print(fmt_sample(s))
        time.sleep(poll_interval)

    print(f"\n--- Phase 2: MULTI_POINT_ALIGN Start ---")
    send_switch(host, port, MOUNT_BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_START")

    start_t = time.time()
    aborted_at = None
    deadline = start_t + timeout_secs
    while time.time() < deadline:
        s = take_sample(host, port, t0, mount_name)
        samples.append(s)
        print(fmt_sample(s))
        if test_abort and aborted_at is None and (time.time() - start_t) >= abort_after_secs:
            print(f"\n--- Phase 3: sending ALIGN_STOP at t={time.time() - t0:.1f}s ---")
            send_switch(host, port, MOUNT_BRIDGE, "MULTI_POINT_ALIGN", "ALIGN_STOP")
            aborted_at = time.time() - t0
        if s.align_state in ("Ok", "Alert") and (not test_abort or aborted_at is not None):
            print(f"\nMULTI_POINT_ALIGN reached terminal state '{s.align_state}' - stopping trace.")
            break
        time.sleep(poll_interval)

    wire.stop()
    return samples, wire.events, aborted_at, mount_name


def print_report(samples, wire_events, aborted_at, mount_name, test_abort):
    print("\n" + "=" * 78)
    print("REPORT")
    print("=" * 78)

    print(f"\n[1] Baseline (before Start) - PiFinder-vs-mount agreement:")
    pre_start = [s for s in samples if s.drift_arcmin is not None]
    if pre_start:
        first = pre_start[0]
        print(f"    First sample: drift={first.drift_arcmin:.1f}' [{first.drift_state}]")
        print(
            f"    -> Mount was {'NOT ' if first.drift_arcmin and first.drift_arcmin > 5 else ''}"
            f"pre-synced to PiFinder's reported position at trace start."
        )

    print(f"\n[2] Raw wire events captured ({len(wire_events)} total, "
          f"setNumberVector/setSwitchVector/message from {MOUNT_BRIDGE}/{PIFINDER_DEV}):")
    for e in wire_events:
        first_line = e.line.split("\n")[0][:160]
        print(f"    t={e.t:6.1f}s  {first_line}")

    print(f"\n[3] Mount position over time (from periodic samples):")
    last_pos = None
    for s in samples:
        pos = (s.mount_ra, s.mount_dec)
        if pos != last_pos:
            print(f"    t={s.t:6.1f}s  {mount_name} -> ({s.mount_ra}, {s.mount_dec})")
            last_pos = pos

    print(f"\n[4] MULTI_POINT_ALIGN state transitions:")
    last_state = None
    for s in samples:
        if s.align_state != last_state:
            print(f"    t={s.t:6.1f}s  align_state -> {s.align_state}")
            last_state = s.align_state

    if test_abort:
        print(f"\n[5] Abort test: ALIGN_STOP sent at t={aborted_at:.1f}s" if aborted_at else
              "\n[5] Abort test: never triggered (sequence finished before abort_after_secs)")
        if aborted_at is not None:
            after = [s for s in samples if s.t >= aborted_at]
            positions_after = {(s.mount_ra, s.mount_dec) for s in after}
            print(f"    Distinct mount positions after abort: {len(positions_after)}")
            print(f"    -> Mount {'DID NOT move further' if len(positions_after) <= 1 else 'KEPT MOVING'} "
                  f"after ALIGN_STOP.")
            states_after = {s.align_state for s in after}
            print(f"    align_state values seen after abort: {states_after}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=7624)
    ap.add_argument("--baseline-secs", type=float, default=15.0)
    ap.add_argument("--timeout-secs", type=float, default=180.0)
    ap.add_argument("--poll-interval", type=float, default=2.5)
    ap.add_argument("--test-abort", action="store_true", help="Send ALIGN_STOP partway through instead of letting the sequence finish.")
    ap.add_argument("--abort-after-secs", type=float, default=8.0, help="Seconds after Start to send ALIGN_STOP, if --test-abort.")
    args = ap.parse_args()

    samples, wire_events, aborted_at, mount_name = run_trace(
        args.host, args.port, args.baseline_secs, args.timeout_secs,
        args.poll_interval, args.test_abort, args.abort_after_secs,
    )
    print_report(samples, wire_events, aborted_at, mount_name, args.test_abort)


if __name__ == "__main__":
    main()
