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
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8624
DEFAULT_TIMEOUT = 5.0

PIFINDER_LX200_LABEL = "PiFinder LX200"
PIFINDER_BRIDGE_LABEL = "PiFinder Mount Bridge"
PIFINDER_SIMULATOR_LABEL = "PiFinder Simulator"


class WebManagerError(Exception):
    """Raised for connection/HTTP failures talking to the Web Manager."""


def _q(profile: str) -> str:
    """URL-encodes a profile name for use as a path segment. Profile names
    are free text (e.g. "Simulation PFSM" has a space) - found live: an
    unencoded space in the request path meant a profile with a space in its
    name silently failed to start via /api/server/start/{profile}, while
    "Simulators" (no special characters) had worked fine by coincidence."""
    return urllib.parse.quote(profile, safe="")


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
    result = _request("GET", f"/api/profiles/{_q(profile)}/labels", host, port, timeout) or []
    return [d["label"] for d in result if "label" in d]


def set_profile_drivers(
    profile: str, labels: list, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT, remote_specs: Optional[list] = None,
) -> None:
    """Full replace of a profile's driver list - see module docstring.

    remote_specs: remote-driver entries as "Label@host:port" strings. Format
    verified live (2026-07-28) against the real StellarMate Web Manager: a
    remote entry is `{"remote": "Label@host:port"}` WITHOUT a "label" key -
    an entry carrying both keys (the shape the OpenAPI ProfileDriver schema
    suggests) is silently stored as a plain LOCAL driver instead, and the
    remote spec is lost. Also verified: the profile's remote field is fully
    replaced by every POST (posting without any remote entry clears it),
    unlike local labels whose removal needs the delete-and-recreate
    workaround (module docstring)."""
    body = [{"label": label} for label in labels]
    for spec in remote_specs or []:
        body.append({"remote": spec})
    _request("POST", f"/api/profiles/{_q(profile)}/drivers", host, port, timeout, body=body)


def get_remote_drivers(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> list:
    """The profile's remote-driver specs as a list of "Label@host:port"
    strings (GET /api/profiles/{p}/remote returns them as one comma-joined
    string; empty string = none - verified live 2026-07-28). Note that
    remote entries ALSO show up in get_profile_labels() as plain labels, so
    labels alone cannot distinguish local from remote - this is the only
    endpoint that can."""
    raw = _request("GET", f"/api/profiles/{_q(profile)}/remote", host, port, timeout)
    if not raw or not isinstance(raw, str):
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _get_profile_meta(profile: str, host: str, port: int, timeout: float) -> dict:
    for p in list_profiles(host, port, timeout):
        if p.get("name") == profile:
            return p
    raise WebManagerError(f"Profile '{profile}' not found")


def _recreate_profile_with_drivers(
    profile: str, labels: list, meta: dict, host: str, port: int, timeout: float,
    remote_specs: Optional[list] = None,
) -> None:
    """Deletes and recreates a profile (same name/port/autostart/autoconnect/
    driver_source) with exactly the given driver list. Used for driver
    *removal* only - see the module docstring for why the plain replace
    endpoint isn't reliable for that specific case."""
    _request("DELETE", f"/api/profiles/{_q(profile)}", host, port, timeout)
    _request("POST", f"/api/profiles/{_q(profile)}", host, port, timeout)
    _request(
        "PUT", f"/api/profiles/{_q(profile)}", host, port, timeout,
        body={
            "port": meta.get("port"),
            "autostart": bool(meta.get("autostart")),
            "autoconnect": bool(meta.get("autoconnect")),
            "driver_source": meta.get("driver_source") or "system",
        },
    )
    if labels or remote_specs:
        set_profile_drivers(profile, labels, host, port, timeout, remote_specs=remote_specs)


def _set_driver_membership(profile: str, label: str, present: bool, host: str, port: int, timeout: float) -> None:
    current = get_profile_labels(profile, host, port, timeout)
    is_present = label in current
    if present == is_present:
        return  # already in the desired state, no-op
    # get_profile_labels() includes remote entries as plain labels too (see
    # its own docstring) - re-posting them bare, without remote_specs, loses
    # the remote spec entirely (silently downgrades a remote PiFinder LX200
    # to a broken local entry). Found live (2026-07-29): adding Mount Bridge
    # via this function after a remote PiFinder LX200 was already configured
    # wiped the Remote Drivers field. Fetch and always carry remote_specs
    # through, on both the add and remove paths.
    remote_specs = get_remote_drivers(profile, host, port, timeout)
    remote_labels = {s.split("@", 1)[0] for s in remote_specs}
    local_labels = [l for l in current if l not in remote_labels]
    if present:
        # Adding is reliable via the plain replace endpoint - verified live.
        set_profile_drivers(profile, local_labels + [label], host, port, timeout, remote_specs=remote_specs)
    else:
        # Removing is not reliable via the plain replace endpoint for this
        # specific driver - see module docstring. Delete-and-recreate
        # instead.
        meta = _get_profile_meta(profile, host, port, timeout)
        new_labels = [d for d in local_labels if d != label]
        _recreate_profile_with_drivers(profile, new_labels, meta, host, port, timeout, remote_specs=remote_specs)


def set_pifinder_lx200(
    profile: str, present: bool, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Adds/removes only 'PiFinder LX200' - every other driver in the profile is left untouched."""
    set_pifinder_lx200_state(profile, "local" if present else "absent", host=host, port=port, timeout=timeout)


def set_pifinder_lx200_state(
    profile: str, state: str, remote: Optional[str] = None,
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Puts the profile's 'PiFinder LX200' entry into exactly one of three
    states - see docs/concepts/remote_indi_coupling_split_host.md (R-CH1):

    - "absent": no PiFinder LX200 at all (local or remote)
    - "local":  runs as a local driver on this device (classic setup)
    - "remote": proxied from another device's indiserver; `remote` is that
      device's "host:port" (the caller normalizes/validates it)

    Whatever entry exists before (either kind) is replaced - the UI never
    needs, and this never creates, a profile with both a local and a remote
    PiFinder LX200 at once. Every other driver (local or remote) in the
    profile is left untouched. Removal of a local label still needs the
    delete-and-recreate workaround (module docstring); the remote field
    itself is reliably replaced by a plain POST (verified live 2026-07-28).
    """
    if state not in ("absent", "local", "remote"):
        raise ValueError(f"invalid state '{state}'")
    if state == "remote" and not remote:
        raise ValueError("state 'remote' requires a host:port")
    labels = get_profile_labels(profile, host, port, timeout)
    remote_specs = get_remote_drivers(profile, host, port, timeout)
    remote_labels = {s.split("@", 1)[0] for s in remote_specs}
    # Labels include remote entries too (see get_remote_drivers()) - split
    # them apart so each side can be reassembled explicitly.
    local_labels = [l for l in labels if l not in remote_labels]

    other_locals = [l for l in local_labels if l != PIFINDER_LX200_LABEL]
    other_remotes = [s for s in remote_specs if not s.startswith(PIFINDER_LX200_LABEL + "@")]
    had_local = PIFINDER_LX200_LABEL in local_labels
    had_remote = len(other_remotes) != len(remote_specs)

    new_locals = other_locals + ([PIFINDER_LX200_LABEL] if state == "local" else [])
    new_remotes = other_remotes + ([f"{PIFINDER_LX200_LABEL}@{remote}"] if state == "remote" else [])

    # Removing needs the delete-and-recreate workaround in BOTH directions:
    # a local label for the known reason (module docstring), and a remote
    # entry because clearing it via plain POST leaves its label lingering in
    # the labels list (verified live 2026-07-28) - which pifinder_driver_
    # status() would then misread as a LOCAL PiFinder LX200 still present.
    if (had_local and state != "local") or (had_remote and state != "remote"):
        meta = _get_profile_meta(profile, host, port, timeout)
        _recreate_profile_with_drivers(profile, new_locals, meta, host, port, timeout, remote_specs=new_remotes)
    else:
        set_profile_drivers(profile, new_locals, host, port, timeout, remote_specs=new_remotes)


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
    _request("POST", f"/api/server/start/{_q(profile)}", host, port, timeout, body=[])


def stop_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> None:
    _request("POST", "/api/server/stop", host, port, timeout, body=[])


def pifinder_driver_status(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """PiFinder driver membership for the given profile:

    - has_lx200: PiFinder LX200 is in the profile at all (local OR remote -
      what coupling-readiness cares about, either kind works for the bridge)
    - lx200_remote: "host:port" if it's a remote entry, None if local/absent
      (labels alone can't tell - see get_remote_drivers())
    - has_bridge: PiFinder Mount Bridge in the profile (always local)
    """
    labels = get_profile_labels(profile, host, port, timeout)
    remote_specs = get_remote_drivers(profile, host, port, timeout)
    lx200_remote = next(
        (s.split("@", 1)[1] for s in remote_specs if s.startswith(PIFINDER_LX200_LABEL + "@")), None
    )
    return {
        "has_lx200": PIFINDER_LX200_LABEL in labels or lx200_remote is not None,
        "lx200_remote": lx200_remote,
        "has_bridge": PIFINDER_BRIDGE_LABEL in labels,
    }


def driver_families(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """{label: family} for every driver in Web Manager's own catalog (GET
    /api/drivers) - e.g. "Telescopes", "CCDs", "Auxiliary". This is the
    *installed driver catalog*, a different thing from a running device's
    own INDI properties (which don't self-declare a device class) - an
    earlier version of this module's docstring said device-class detection
    wasn't possible at all, which was wrong: it's not possible from a
    running device's properties, but the catalog this project already
    queries elsewhere (server.py's startup driver-registration check) has
    had this all along. Verified live: 96 of 285 catalog entries are
    family "Telescopes"."""
    result = _request("GET", "/api/drivers", host, port, timeout) or []
    return {d.get("label"): d.get("family") for d in result}


def other_profile_drivers(
    profile: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> list:
    """Phase 3 (UC5): every driver label in the profile except the PiFinder
    ones - candidates for "which one is the mount", queried live rather than
    hardcoded. Each entry also flags is_telescope (family == "Telescopes"
    per driver_families() above) so the caller can auto-select an
    unambiguous single candidate instead of always asking the user.

    Known exceptions: "PiFinder LX200" and "PiFinder Simulator" are *also*
    family "Telescopes" (both implement INDI::Telescope - the former to
    emulate an LX200 mount, the latter as a settable PiFinder-side "sky
    truth" for testing, see basic-memory pifinder-stellarmate/00092) -
    already excluded above by label, same as PiFinder Mount Bridge, so this
    needs no special case for either. Found live (2026-08-07): before
    PIFINDER_SIMULATOR_LABEL was added here, "PiFinder Simulator" showed up
    as a selectable mount candidate even though it's the opposite role - the
    PiFinder-side truth source, never the thing being corrected.

    Two residual cases this can't resolve on its own: (a) more than one
    Telescope-family driver in the profile (e.g. a Telescope Simulator
    alongside the user's real mount) - can't tell which is genuinely in use;
    (b) a driver mislabeled by its own INDI skeleton file (family is
    whatever the driver author declared, not independently verified). Both
    fall back to manual selection - see is_telescope's only caller,
    status_page.html's mount-dropdown logic."""
    labels = get_profile_labels(profile, host, port, timeout)
    families = driver_families(host, port, timeout)
    return [
        {"label": label, "is_telescope": families.get(label) == "Telescopes"}
        for label in labels
        if label not in (PIFINDER_LX200_LABEL, PIFINDER_BRIDGE_LABEL, PIFINDER_SIMULATOR_LABEL)
    ]
