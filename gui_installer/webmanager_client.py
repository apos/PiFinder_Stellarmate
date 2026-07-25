#!/usr/bin/env python3
"""
Minimal client for the INDI Web Manager's own REST API (default
127.0.0.1:8624) - stdlib only (`urllib.request`), no new dependency.
Framework-agnostic like `indi_client.py` (no `http.server`/`bottle` import),
for the same portability reason - see
docs/concepts/mount_bridge_web_integration.md's Portability Strategy.

Covers Phase 2 of that concept (profile driver add/remove for PiFinder LX200
/ PiFinder Mount Bridge) plus the small amount of profile-listing/server-
status groundwork that needs. Not a general Web Manager client - only the
endpoints this feature actually uses.

Endpoint behavior verified live against a real, running Web Manager
instance on 2026-07-20/25 (not assumed from documentation):

- `POST /api/profiles/{name}/drivers` is a **full replace**, not additive -
  confirmed both by reading the open-source reference implementation this
  is based on (github.com/knro/indiwebmanager, `Database.save_profile_drivers()`:
  `DELETE FROM driver WHERE profile=?` followed by inserting exactly the
  given list) and by a clean live test (posting a strict subset of an
  existing profile's drivers correctly removed the excluded one). An
  earlier, less careful live test had suggested this was additive - that
  was wrong; trust this note over that one if the two are ever found to
  disagree elsewhere in this codebase's comments/history.
- This means both "add a driver" and "remove a driver" are the same
  read-modify-write operation: fetch the profile's current driver labels,
  add/remove the one label that matters, POST the full resulting list back.
- **StellarMate-specific quirk, found and reproduced live (2026-07-25), not
  present in the open-source reference's logic**: once "PiFinder LX200" (and
  presumably "PiFinder Mount Bridge" - not separately confirmed, treated the
  same defensively) has been part of a profile, a later `POST .../drivers`
  call that excludes it does **not** actually remove it - reproduced 3
  times from a guaranteed-clean profile (delete + recreate immediately
  before each attempt), while removing a stock driver (e.g. "Focuser
  Simulator") the same way works correctly every time. Root cause unknown -
  `stellarmatewebmanager` is a closed, PyArmor-obfuscated fork of
  `knro/indiwebmanager`, not something this project can debug by reading
  its source. Worked around here by never trying to remove a single driver
  in place: removal instead deletes the whole profile and recreates it
  (same name, same port/autostart/autoconnect/driver_source, fetched first)
  with the trimmed driver list from scratch. Heavier than the endpoint this
  was meant to use, but reliable - verified live.
"""
import json
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8624
DEFAULT_TIMEOUT = 5.0

PIFINDER_LX200_LABEL = "PiFinder LX200"
PIFINDER_BRIDGE_LABEL = "PiFinder Mount Bridge"


class WebManagerError(Exception):
    """Raised for connection/HTTP failures talking to the Web Manager."""


def _request(method: str, path: str, host: str, port: int, timeout: float, body=None):
    url = f"http://{host}:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.URLError as e:
        raise WebManagerError(f"{method} {path} failed: {e}") from e
    except json.JSONDecodeError as e:
        raise WebManagerError(f"{method} {path} returned non-JSON: {e}") from e


def list_profiles(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> list:
    """Every profile's {id, name, port, autostart, autoconnect, driver_source}."""
    return _request("GET", "/api/profiles/", host, port, timeout) or []


def get_profile_labels(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> list:
    """Current driver labels (e.g. ["Telescope Simulator", ...]) for a profile."""
    result = _request("GET", f"/api/profiles/{profile}/labels", host, port, timeout) or []
    return [d["label"] for d in result if "label" in d]


def set_profile_drivers(
    profile: str, labels: list, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Full replace of a profile's driver list - see module docstring."""
    _request(
        "POST", f"/api/profiles/{profile}/drivers", host, port, timeout,
        body=[{"label": label} for label in labels],
    )


def _get_profile_meta(profile: str, host: str, port: int, timeout: float) -> dict:
    for p in list_profiles(host, port, timeout):
        if p.get("name") == profile:
            return p
    raise WebManagerError(f"Profile '{profile}' not found")


def _recreate_profile_with_drivers(
    profile: str, labels: list, meta: dict, host: str, port: int, timeout: float
) -> None:
    """Deletes and recreates a profile (same name/port/autostart/autoconnect/
    driver_source) with exactly the given driver list. Used for driver
    *removal* only - see the module docstring for why the plain replace
    endpoint isn't reliable for that specific case."""
    _request("DELETE", f"/api/profiles/{profile}", host, port, timeout)
    _request("POST", f"/api/profiles/{profile}", host, port, timeout)
    _request(
        "PUT", f"/api/profiles/{profile}", host, port, timeout,
        body={
            "port": meta.get("port"),
            "autostart": bool(meta.get("autostart")),
            "autoconnect": bool(meta.get("autoconnect")),
            "driver_source": meta.get("driver_source") or "system",
        },
    )
    if labels:
        set_profile_drivers(profile, labels, host, port, timeout)


def _set_driver_membership(profile: str, label: str, present: bool, host: str, port: int, timeout: float) -> None:
    current = get_profile_labels(profile, host, port, timeout)
    is_present = label in current
    if present == is_present:
        return  # already in the desired state, no-op
    if present:
        # Adding is reliable via the plain replace endpoint - verified live.
        set_profile_drivers(profile, current + [label], host, port, timeout)
    else:
        # Removing is not reliable via the plain replace endpoint for this
        # specific driver - see module docstring. Delete-and-recreate
        # instead.
        meta = _get_profile_meta(profile, host, port, timeout)
        new_labels = [d for d in current if d != label]
        _recreate_profile_with_drivers(profile, new_labels, meta, host, port, timeout)


def set_pifinder_lx200(
    profile: str, present: bool, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Adds/removes only 'PiFinder LX200' - every other driver in the profile is left untouched."""
    _set_driver_membership(profile, PIFINDER_LX200_LABEL, present, host, port, timeout)


def set_pifinder_bridge(
    profile: str, present: bool, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Adds/removes only 'PiFinder Mount Bridge' - every other driver in the profile is left untouched."""
    _set_driver_membership(profile, PIFINDER_BRIDGE_LABEL, present, host, port, timeout)


def server_status(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """{"running": bool, "active_profile": str}."""
    result = _request("GET", "/api/server/status", host, port, timeout) or []
    if not result:
        return {"running": False, "active_profile": None}
    entry = result[0]
    return {
        "running": str(entry.get("status")) == "True",
        "active_profile": entry.get("active_profile") or None,
    }


def start_server(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    _request("POST", f"/api/server/start/{profile}", host, port, timeout, body=[])


def stop_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> None:
    _request("POST", "/api/server/stop", host, port, timeout, body=[])


def pifinder_driver_status(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """{"has_lx200": bool, "has_bridge": bool} for the given profile."""
    labels = get_profile_labels(profile, host, port, timeout)
    return {
        "has_lx200": PIFINDER_LX200_LABEL in labels,
        "has_bridge": PIFINDER_BRIDGE_LABEL in labels,
    }
