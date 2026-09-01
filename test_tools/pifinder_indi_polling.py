"""Small, dependency-free INDI polling primitives shared by this directory's
test tools (pifinder_truth_injector.py, pifinder_imu_injector.py) - kept as
plain functions around the indi_getprop CLI, same reasoning as each script's
own docstring: no full INDI client library needed for what these do.
"""

import subprocess


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
