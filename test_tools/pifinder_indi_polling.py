"""Small, dependency-free INDI polling primitives shared by this directory's
test tools (pifinder_truth_injector.py, pifinder_imu_injector.py) - kept as
plain functions around the indi_getprop CLI, same reasoning as each script's
own docstring: no full INDI client library needed for what these do.

PersistentIndiClient (2026-09-26) is the preferred way to poll repeatedly.
Live-testing on the Pi5 found pifinder_imu_injector.py's uncapped,
subprocess-per-tick loop (2x indi_getprop fork+connect per iteration, no
sleep) contributing real, continuous load to indiserver - implicated in
Issue #385 (indiserver periodic unresponsiveness / unbounded memory growth
under a slow-consuming client; see basic-memory pifinder-stellarmate,
2026-09-26 Pi5 session, indiserver -m/backlog findings). The read_ra_dec()/
is_mount_busy()/read_property() functions below still work and are kept for
any one-off/low-frequency use, but a tight polling loop should use
PersistentIndiClient instead: one long-lived socket, no process fork and no
fresh TCP handshake per read.
"""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
import xml.parsers.expat


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


def read_property(host: str, port: int, device: str, prop: str, element: str, timeout: float) -> str | None:
    """Single-element convenience wrapper (e.g. a switch or text property) -
    returns the raw string value, or None if unavailable."""
    try:
        out = subprocess.run(
            ["indi_getprop", "-h", host, "-p", str(port), "-t", str(timeout), "-1",
             f"{device}.{prop}.{element}"],
            capture_output=True, text=True, timeout=timeout + 2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"indi_getprop failed: {e}")
        return None
    value = out.stdout.strip()
    return value or None


def is_mount_busy(host: str, port: int, device: str, timeout: float) -> bool | None:
    """True/False, or None if the state couldn't be read."""
    state = read_property(host, port, device, "EQUATORIAL_EOD_COORD", "_STATE", timeout)
    if state is None:
        return None
    return state == "Busy"


class PersistentIndiClient:
    """One long-lived INDI socket, reused across many reads instead of
    spawning a fresh indi_getprop process (and a fresh TCP handshake) per
    read. Each call sends a device+property-scoped <getProperties/> over the
    already-open socket and incrementally parses just that one reply -
    avoids subscribing to (and having to filter out) every other device's
    traffic. Reconnects transparently (once per call) on any socket error,
    so a dropped connection (indiserver restart, network hiccup) self-heals
    on the next call instead of wedging the caller's loop forever.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _connect(self, timeout: float) -> socket.socket:
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        sock.settimeout(timeout)
        return sock

    def _query_vector(self, device: str, prop: str, timeout: float) -> dict | None:
        """Sends a scoped getProperties for device.prop over the persistent
        socket and returns {"state": str, "elements": {name: text}} for the
        first matching def/set*Vector reply, or None on timeout/error (and
        drops the socket so the next call reconnects fresh)."""
        request = f"<getProperties version='1.7' device='{device}' name='{prop}'/>\n".encode()

        result: dict = {}
        found: dict = {}  # small mutable box the nested callbacks close over
        element_tags = {"oneNumber", "defNumber", "oneSwitch", "defSwitch", "oneText", "defText"}

        def start_element(name, attrs):
            if name.endswith("Vector"):
                if attrs.get("device") == device and attrs.get("name") == prop:
                    result["state"] = attrs.get("state")
                    result["elements"] = {}
                    found["in_vector"] = True
                    found["current_element"] = None
            elif found.get("in_vector") and name in element_tags:
                found["current_element"] = attrs.get("name")
                result["elements"].setdefault(found["current_element"], "")

        def char_data(data):
            if found.get("in_vector") and found.get("current_element"):
                result["elements"][found["current_element"]] += data

        def end_element(name):
            if name.endswith("Vector") and found.get("in_vector"):
                found["done"] = True
            elif found.get("in_vector"):
                found["current_element"] = None

        try:
            if self._sock is None:
                self._sock = self._connect(timeout)
            self._sock.settimeout(timeout)
            self._sock.sendall(request)

            parser = xml.parsers.expat.ParserCreate()
            parser.StartElementHandler = start_element
            parser.CharacterDataHandler = char_data
            parser.EndElementHandler = end_element

            deadline = time.monotonic() + timeout
            while not found.get("done"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._sock.settimeout(remaining)
                chunk = self._sock.recv(65536)
                if not chunk:
                    raise ConnectionError("indiserver closed the connection")
                parser.Parse(chunk, False)
        except (OSError, xml.parsers.expat.ExpatError):
            self.close()
            return None

        if "elements" not in result:
            return None
        return {"state": result.get("state"), "elements": result["elements"]}

    def read_ra_dec(self, device: str, timeout: float = 3.0) -> tuple[float, float] | None:
        vec = self._query_vector(device, "EQUATORIAL_EOD_COORD", timeout)
        if vec is None:
            return None
        elements = vec["elements"]
        try:
            ra = float(elements["RA"])
            dec = float(elements["DEC"])
        except (KeyError, ValueError):
            return None
        return ra, dec

    def is_busy(self, device: str, timeout: float = 1.0) -> bool | None:
        vec = self._query_vector(device, "EQUATORIAL_EOD_COORD", timeout)
        if vec is None:
            return None
        return vec.get("state") == "Busy"


def pick_safe_target(pifinder_host: str, pifinder_port: int, min_altitude: float = 20.0,
                      timeout: float = 5.0) -> tuple[float, float, str] | None:
    """Pick a real, currently-above-horizon bright star via PiFinder's own
    /api/nearby_bright_stars (already altitude-filtered server-side using
    PiFinder's own GPS location/time - the same endpoint Mount Bridge's own
    Multi-Point Alignment uses, see mount_bridge_multistar_alignment.md §4.2
    and pifinder_mount_bridge.cpp's httpGetNearbyBrightStars()).

    Direct user feedback (2026-09-01): test/simulation coordinates picked by
    hand (or a fixed compiled-in default) can land below the horizon - real
    hardware would try to slew there regardless, risking the mount or OTA.
    Any test tool or simulated device picking a target - including this
    directory's own scripts - must go through this instead of inventing a
    coordinate.

    Returns (ra_hours, dec_deg, name) for the brightest candidate, or None if
    none are currently above min_altitude or the request failed.
    """
    url = f"http://{pifinder_host}:{pifinder_port}/api/nearby_bright_stars?radius=180&count=1&min_altitude={min_altitude}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"pick_safe_target: /api/nearby_bright_stars failed: {e}")
        return None
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    c = candidates[0]
    return c["ra"] / 15.0, c["dec"], c.get("name", "?")
