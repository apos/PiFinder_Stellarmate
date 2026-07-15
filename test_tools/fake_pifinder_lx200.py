#!/usr/bin/env python3
"""Fake PiFinder LX200 server for testing indi_pifinder / the mount bridge.

Speaks the small LX200 subset PiFinder's real pos_server.py exposes
(":GR#" / ":GD#") on its own port, so it's a drop-in stand-in for PiFinder's
serial/TCP connection during driver and bridge development. Doesn't touch
PiFinder or the real pos_server.py (port 4030) at all.

Runs a looping demo session in Lyra: Vega -> Sheliak -> Sulafat -> M57 (Ring
Nebula, which sits almost exactly between Sheliak and Sulafat) -- two star
hops followed by a slew onto a deep-sky object, repeated forever so it can
sit running for an extended bridge test session.
"""

import argparse
import logging
import socket
import threading
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fake_pifinder")

DEFAULT_PORT = 4031
STEP_INTERVAL = 0.5  # seconds between position updates while hopping/slewing

# (name, RA hours J2000, Dec degrees J2000, dwell seconds, transition seconds from previous waypoint)
WAYPOINTS = [
    ("Vega (alpha Lyr)", 18 + 36 / 60 + 56.3 / 3600, 38 + 47 / 60 + 1 / 3600, 8, 0),
    ("Sheliak (beta Lyr)", 18 + 50 / 60 + 4.8 / 3600, 33 + 21 / 60 + 46 / 3600, 6, 6),
    ("Sulafat (gamma Lyr)", 18 + 58 / 60 + 56.6 / 3600, 32 + 41 / 60 + 22 / 3600, 6, 6),
    ("M57 Ring Nebula", 18 + 53 / 60 + 35.1 / 3600, 33 + 1 / 60 + 45 / 3600, 15, 4),
]


class SharedPosition:
    def __init__(self, ra_hours: float, dec_deg: float) -> None:
        self._lock = threading.Lock()
        self._ra_hours = ra_hours
        self._dec_deg = dec_deg

    def set(self, ra_hours: float, dec_deg: float) -> None:
        with self._lock:
            self._ra_hours = ra_hours
            self._dec_deg = dec_deg

    def get(self) -> tuple[float, float]:
        with self._lock:
            return self._ra_hours, self._dec_deg


def format_ra(ra_hours: float) -> str:
    ra_hours %= 24
    hh = int(ra_hours)
    rem = (ra_hours - hh) * 60
    mm = int(rem)
    ss = int(round((rem - mm) * 60))
    if ss == 60:
        ss = 0
        mm += 1
    if mm == 60:
        mm = 0
        hh += 1
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def format_dec(dec_deg: float) -> str:
    sign = "+" if dec_deg >= 0 else "-"
    dec_deg = abs(dec_deg)
    dd = int(dec_deg)
    rem = (dec_deg - dd) * 60
    mm = int(rem)
    ss = int(round((rem - mm) * 60))
    if ss == 60:
        ss = 0
        mm += 1
    if mm == 60:
        mm = 0
        dd += 1
    return f"{sign}{dd:02d}*{mm:02d}'{ss:02d}"


def run_tour(position: SharedPosition) -> None:
    name, ra, dec, dwell, _ = WAYPOINTS[0]
    position.set(ra, dec)
    log.info("Starting at %s (%s %s)", name, format_ra(ra), format_dec(dec))
    time.sleep(dwell)
    while True:
        for i in range(1, len(WAYPOINTS)):
            prev_name = WAYPOINTS[i - 1][0]
            name, ra, dec, dwell, transition = WAYPOINTS[i]
            start_ra, start_dec = position.get()
            log.info("Hopping from %s to %s (%.0fs)", prev_name, name, transition)
            steps = max(int(transition / STEP_INTERVAL), 1)
            for step in range(1, steps + 1):
                frac = step / steps
                position.set(
                    start_ra + (ra - start_ra) * frac,
                    start_dec + (dec - start_dec) * frac,
                )
                time.sleep(STEP_INTERVAL)
            log.info("Arrived at %s (%s %s), dwelling %ss", name, format_ra(ra), format_dec(dec), dwell)
            time.sleep(dwell)
        log.info("Tour complete, looping back to start")


def handle_command(cmd: str, position: SharedPosition) -> str:
    if cmd == ":GR#":
        ra_hours, _ = position.get()
        return format_ra(ra_hours) + "#"
    if cmd == ":GD#":
        _, dec_deg = position.get()
        return format_dec(dec_deg) + "#"
    if cmd.startswith(":Sr") or cmd.startswith(":Sd"):
        log.info("Received push-to/GoTo target command: %s", cmd)
        return "1"
    if not cmd.startswith(":") or cmd == "#":
        # indi_pifinder sends commands with a leading '#' (e.g. "#:GR#"),
        # which splits into an empty/bogus token before the real ":GR#".
        # Don't answer those - a spurious ack here lands in front of the
        # real response and corrupts the client's read.
        log.debug("Ignoring non-command token %r", cmd)
        return ""
    # Anything else (Sync/handshake probes etc.): ack harmlessly so a client
    # waiting on a response doesn't hang.
    log.debug("Unhandled command %r, acking", cmd)
    return "1"


def handle_client(conn: socket.socket, position: SharedPosition) -> None:
    buf = b""
    with conn:
        conn.settimeout(30)
        while True:
            try:
                chunk = conn.recv(1024)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            while b"#" in buf:
                raw_cmd, buf = buf.split(b"#", 1)
                cmd = raw_cmd.decode(errors="replace") + "#"
                response = handle_command(cmd, position)
                if response:
                    conn.sendall(response.encode())


def serve(position: SharedPosition, port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", port))
    server.listen(1)
    log.info("Fake PiFinder LX200 server listening on port %d", port)
    while True:
        conn, addr = server.accept()
        log.info("Client connected from %s", addr)
        handle_client(conn, position)
        log.info("Client disconnected")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    position = SharedPosition(WAYPOINTS[0][1], WAYPOINTS[0][2])
    threading.Thread(target=run_tour, args=(position,), daemon=True).start()
    serve(position, args.port)


if __name__ == "__main__":
    main()
