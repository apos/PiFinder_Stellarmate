#!/usr/bin/env python3
"""
Minimal, framework-agnostic INDI protocol client - stdlib only (`socket` +
`xml.parsers.expat`), no `PyIndi`. Deliberately narrow: only understands the
handful of message shapes this project's Mount Bridge web integration needs
(see docs/concepts/mount_bridge_web_integration.md) - not a general-purpose
INDI client. A wider client means more protocol surface that has to be
gotten right for no benefit here.

Framework-agnostic on purpose: no `http.server`/`bottle` import anywhere in
this module. The Control Center (`gui_installer/server.py`) is the first
caller, but the same module is meant to be reusable, unchanged, by PiFinder's
own bottle-based web interface later (see the concept doc's Portability
Strategy) - only a thin route-layer adapter should differ between the two.

Protocol note: indiserver streams a continuous sequence of sibling top-level
XML elements (<defTextVector>, <defSwitchVector>, ...), not one well-formed
document with a single root. A strict single-document parser like
xml.parsers.expat rejects a second top-level element with "junk after
document element" once the first one closes. Worked around here by feeding
the parser a synthetic, never-closed wrapper root (<indiwrapper>) before any
real data - everything indiserver actually sends is then treated as (nested)
children of that root, which expat never complains about since it's never
closed. This is the standard workaround for parsing INDI's wire protocol
with a strict incremental XML parser; verified live against a real
`indiserver` (Simulators profile, `Telescope Simulator`'s `CONNECTION`
property and 25 others) before being written here as this module.
"""
import socket
import time
import xml.parsers.expat
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7624

# Named timeout tiers, consolidated here instead of scattered ad hoc literals
# across server.py/indi_client.py (each value already existed somewhere before
# this - this only gives them one shared name and place, not new numbers).
# Pick the tier that matches *why* a call is timed the way it is, not just
# "whatever number happened to work":
DEFAULT_TIMEOUT = 3.0        # interactive: a user just clicked something and is watching for a result
TIMEOUT_BACKGROUND_POLL = 7.0        # passive, periodic UI polling - indiserver occasionally answers slowly
                                      # under load, and flapping the UI over that is worse than a slow number
                                      # (see /api/mount_bridge_status's own long-standing comment)
DEVICE_TIMEOUT_BACKGROUND_POLL = 3.0  # the extra per-device lookups nested inside that same background poll
TIMEOUT_FAST_POLL = 2.0        # tight-cadence, best-effort readouts where a single miss just skips one
                                # update (e.g. mount_bridge_drift()) - never gates a button's enabled state
TIMEOUT_QUICK_RETRY = 1.0      # short-lived polling loop with its own retry/backoff already built around it
                                # (e.g. waiting for a just-restarted driver to answer) - a slow individual
                                # attempt should fail fast so the loop can just try again

_VECTOR_TAGS = {
    "defTextVector": "text",
    "defSwitchVector": "switch",
    "defNumberVector": "number",
}
_ELEMENT_TAGS = {"defText", "defSwitch", "defNumber"}


class INDIClientError(Exception):
    """Raised for connection/protocol failures talking to indiserver."""


def get_properties(
    device: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """
    Opens a short-lived connection to indiserver, sends getProperties for
    the given device (or every device if None), and collects every
    def*Vector element sent back within the read timeout.

    Returns {device_name: {property_name: {"type": "text"|"switch"|"number",
    "state": <IPS state string>, "elements": {element_name: value}}}}.

    A single getProperties round-trip only returns each property's current
    *definition* (defXxxVector) - indiserver sends the live values as part
    of that same definition for properties that already have a value, which
    is all this read-only status feature needs (Phase 1). It does not need
    to distinguish a fresh define from a later update (setXxxVector) since
    it never keeps the connection open long enough to see one.
    """
    result: dict = {}
    current: dict = {}

    def start_element(name, attrs):
        if name in _VECTOR_TAGS:
            current.clear()
            current["device"] = attrs.get("device")
            current["property"] = attrs.get("name")
            current["type"] = _VECTOR_TAGS[name]
            current["state"] = attrs.get("state")
            current["elements"] = {}
            current["_active"] = None
        elif name in _ELEMENT_TAGS and current:
            if "elements" not in current:
                # Reproduced live against real indiserver traffic (see
                # basic-memory pifinder-stellarmate note on this bug): a
                # def{Text,Switch,Number} element occasionally arrives while
                # `current` still holds a stale, non-empty leftover from
                # elsewhere in the stream without an "elements" key (exact
                # trigger not fully pinned down - intermittent, ~1 in 10-50
                # queries against an actively-polling device). Crashing the
                # whole read (and thus the HTTP request calling it) on a
                # single unexpected element is worse than dropping that one
                # element - every other property still parses fine.
                return
            current["_active"] = attrs.get("name")
            current["elements"][current["_active"]] = ""

    def char_data(data):
        if current.get("_active"):
            current["elements"][current["_active"]] += data

    def end_element(name):
        if name in _VECTOR_TAGS:
            dev = current.get("device")
            prop = current.get("property")
            if dev and prop:
                for key in current["elements"]:
                    current["elements"][key] = current["elements"][key].strip()
                result.setdefault(dev, {})[prop] = {
                    "type": current["type"],
                    "state": current["state"],
                    "elements": current["elements"],
                }
            current.clear()
        elif name in _ELEMENT_TAGS:
            current["_active"] = None

    parser = xml.parsers.expat.ParserCreate()
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.CharacterDataHandler = char_data
    parser.Parse(b"<indiwrapper>", False)

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise INDIClientError(f"Could not connect to indiserver at {host}:{port}: {e}") from e

    try:
        request = (
            f'<getProperties version="1.7" device="{device}"/>'
            if device
            else '<getProperties version="1.7"/>'
        )
        sock.sendall(request.encode())
        # Hard wall-clock deadline for the whole read, NOT "stop after N
        # seconds of silence" - a *connected* device (the normal case once
        # Phase 3 has run) keeps the connection continuously busy with
        # periodic setXxxVector updates (e.g. a connected mount broadcasting
        # its coordinates), which never produces a quiet gap for a
        # silence-based read loop to stop on. Found live: a single
        # get_properties() call against an already-connected "Telescope
        # Simulator" hung indefinitely under the old silence-based version
        # of this function - fixed by capping total read time instead,
        # regardless of how much traffic keeps arriving.
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                parser.Parse(chunk, False)
        except xml.parsers.expat.ExpatError as e:
            raise INDIClientError(f"Malformed INDI XML from indiserver: {e}") from e
        except OSError as e:
            # sendall()/recv() can also fail after connect() succeeded (e.g.
            # ConnectionResetError if indiserver restarts mid-read while a
            # profile's driver list changes) - only socket.timeout above is
            # a normal/expected outcome, everything else here means the
            # caller got an empty/partial result for the wrong reason and
            # should see why, not silently read as "device not loaded".
            raise INDIClientError(f"Lost connection to indiserver while reading: {e}") from e
    finally:
        sock.close()

    return result


def _connection_state(device_props: Optional[dict]) -> Optional[bool]:
    """True/False from a device's own CONNECTION.CONNECT, None if that
    property isn't defined at all (device not loaded, or never queried)."""
    if not device_props:
        return None
    conn = device_props.get("CONNECTION")
    if not conn:
        return None
    return conn["elements"].get("CONNECT") == "On"


def mount_bridge_status(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
    device_timeout: float = 1.5,
) -> dict:
    """
    Read-only snapshot of "PiFinder Mount Bridge"'s relevant properties (see
    docs/concepts/mount_bridge_web_integration.md §4 for the verified
    property reference this maps to), plus each linked device's own
    connection state - used for the Control Center's connection diagram.
    Returns a dict with:
      - "running": bool - whether Mount Bridge answered at all
      - "bridge_connected": bool or None - Mount Bridge's own CONNECTION state
      - "active_pifinder"/"active_mount": str or None - ACTIVE_DEVICES elements
      - "pifinder_connected"/"mount_connected": bool or None - the linked
        devices' own CONNECTION state (None if not set/queryable yet)
      - "coupling_mode": str or None - whichever BRIDGE_MODE element is "On"
      - "correction_action": "sync"/"goto"/None - whichever CORRECTION_ACTION
        element is "On", normalized to set_coupling_mode()'s own short-form
        vocabulary - only meaningful when coupling_mode is MODE_AUTO_CORRECT
      - "drift_arcmin": float or None - current DRIFT_STATUS reading
      - "drift_threshold": float or None - current DRIFT_THRESHOLD reading -
        added 2026-08-06: status_page.html's own Threshold input field had
        no way to ever learn the driver's actual current value (a page
        reload always showed its hardcoded HTML default, 5, regardless of
        what was really set) - found live to cause the field showing a
        stale value that a later coupling-preset click would then push,
        silently overwriting a real, different threshold the driver
        already had.
      - "settings_host"/"settings_port": str or None - BRIDGE_SETTINGS'
        own INDISERVER_HOST/PORT, i.e. where the *driver itself* thinks
        indiserver is - not necessarily this function's own host/port args
      - "settings_correct": bool - settings_host/port actually match this
        function's own host/port (treating "localhost"/"127.0.0.1" as the
        same thing - the driver's own default is the string "localhost")
        *and* active_pifinder is exactly "PiFinder LX200" (its own fixed
        default) - a quick "is Mount Bridge pointed at the right things"
        sanity check, surfaced in the tile per user request rather than
        only being visible via the INDI Control Panel.
      - "mount_web_ip": str or None - the mount device's own DEVICE_ADDRESS.
        ADDRESS, i.e. the IP the mount driver itself connects to, but only
        when CONNECTION_MODE says that connection is CONNECTION_TCP (a
        serial/USB-connected mount has no IP at all here). This is the same
        IP the mount's own onboard web UI listens on (OnStep's WiFi module
        serves both its LX200 command port and its web interface from the
        same address) - added 2026-08-09 for the Control Center's "open all
        the important links at once" button, no separate INDI round-trip
        needed since mt_props below already has the mount's full property
        set from the connection-state lookup just above it.
    All fields besides "running" are None (or False for settings_correct)
    if the device isn't running/known. `device_timeout` is shorter than
    `timeout` for the two extra per-device lookups (kept modest since this
    function is polled regularly - see status_page.html's
    refreshMountBridgeStatus()).
    """
    props = get_properties(device="PiFinder Mount Bridge", host=host, port=port, timeout=timeout)
    device_props = props.get("PiFinder Mount Bridge")
    if not device_props:
        return {
            "running": False,
            "bridge_connected": None,
            "active_pifinder": None,
            "active_mount": None,
            "pifinder_connected": None,
            "mount_connected": None,
            "coupling_mode": None,
            "correction_action": None,
            "drift_arcmin": None,
            "drift_threshold": None,
            "settings_host": None,
            "settings_port": None,
            "settings_correct": False,
            "target_source": None,
            "mount_reject_active": False,
            "mount_reject_message": None,
            "mount_web_ip": None,
            "mount_type_raw": None,
            "pifinder_mount_type": None,
            "pifinder_screen_direction": None,
            "orientation_state": None,
            "align_radius": None,
            "align_count": None,
            "align_min_altitude": None,
        }

    active_devices = device_props.get("ACTIVE_DEVICES", {}).get("elements", {})
    bridge_mode = device_props.get("BRIDGE_MODE", {}).get("elements", {})
    drift_status_prop = device_props.get("DRIFT_STATUS", {})
    drift_status = drift_status_prop.get("elements", {})
    drift_threshold_elements = device_props.get("DRIFT_THRESHOLD", {}).get("elements", {})
    align_config_elements = device_props.get("ALIGN_CONFIG", {}).get("elements", {})
    bridge_settings = device_props.get("BRIDGE_SETTINGS", {}).get("elements", {})

    coupling_mode = next((name for name, val in bridge_mode.items() if val == "On"), None)
    # #178 unified GoTo button: read-only "who does the held target come
    # from" badge (TARGET_SOURCE_PIFINDER/TARGET_SOURCE_MOUNT) - see
    # docs/concepts/mount_bridge_reposition_detection.md.
    target_source_elements = device_props.get("TARGET_SOURCE", {}).get("elements", {})
    target_source_raw = next((name for name, val in target_source_elements.items() if val == "On"), None)
    target_source = {"TARGET_SOURCE_PIFINDER": "pifinder", "TARGET_SOURCE_MOUNT": "mount"}.get(target_source_raw)
    # Mount refused a Goto/Sync outright (elevation/cable-wrap/axis limit) -
    # distinct from ordinary drift, see MOUNT_REJECT's own comment in
    # pifinder_mount_bridge.cpp. IPS_ALERT means still active.
    mount_reject_prop = device_props.get("MOUNT_REJECT", {})
    mount_reject_active = mount_reject_prop.get("state") == "Alert"
    mount_reject_message = mount_reject_prop.get("elements", {}).get("MESSAGE") or None
    correction_action_elements = device_props.get("CORRECTION_ACTION", {}).get("elements", {})
    correction_action_raw = next((name for name, val in correction_action_elements.items() if val == "On"), None)
    correction_action = {"ACTION_SYNC": "sync", "ACTION_GOTO": "goto"}.get(correction_action_raw)
    drift_raw = drift_status.get("DRIFT_ARCMIN")
    drift_threshold_raw = drift_threshold_elements.get("THRESHOLD_ARCMIN")
    active_pifinder = active_devices.get("ACTIVE_PIFINDER") or None
    active_mount = active_devices.get("ACTIVE_MOUNT") or None
    settings_host = bridge_settings.get("INDISERVER_HOST") or None
    settings_port = bridge_settings.get("INDISERVER_PORT") or None
    # "localhost" and "127.0.0.1" are the same thing here (the driver's own
    # default is the string "localhost") - comparing by string alone would
    # flag a perfectly fine setup as wrong.
    settings_correct = (
        settings_host in ("localhost", "127.0.0.1")
        and settings_port == str(port)
        and active_pifinder == "PiFinder LX200"
    )

    pifinder_connected = None
    if active_pifinder:
        pf_props = get_properties(device=active_pifinder, host=host, port=port, timeout=device_timeout)
        pifinder_connected = _connection_state(pf_props.get(active_pifinder))

    mount_connected = None
    mount_web_ip = None
    mount_type_raw = None
    if active_mount:
        mt_props = get_properties(device=active_mount, host=host, port=port, timeout=device_timeout)
        mt_device_props = mt_props.get(active_mount)
        mount_connected = _connection_state(mt_device_props)
        if mt_device_props:
            mount_connection_mode = mt_device_props.get("CONNECTION_MODE", {}).get("elements", {})
            if mount_connection_mode.get("CONNECTION_TCP") == "On":
                mount_web_ip = mt_device_props.get("DEVICE_ADDRESS", {}).get("elements", {}).get("ADDRESS") or None
            # TELESCOPE_MOUNT_TYPE - standard INDI::Telescope switch, whichever
            # element is "On" (MOUNT_ALTAZ/MOUNT_EQ_FORK/MOUNT_EQ_GEM). Reused
            # for the "Mount" orientation badge (2026-08-09) - already fetched
            # above for the connection-state check, no extra INDI round-trip.
            mount_type_elements = mt_device_props.get("TELESCOPE_MOUNT_TYPE", {}).get("elements", {})
            mount_type_raw = next((name for name, val in mount_type_elements.items() if val == "On"), None)

    # PiFinder's own Mount Type/PiFinder Type status, pushed by the driver's
    # own syncOrientationStatus() (PIFINDER_ORIENTATION property) - see
    # docs/concepts/simulation_fidelity_and_pifinder_orientation.md §6.
    orientation_elements = device_props.get("PIFINDER_ORIENTATION", {}).get("elements", {})
    orientation_prop = device_props.get("PIFINDER_ORIENTATION", {})

    return {
        "running": True,
        "bridge_connected": _connection_state(device_props),
        "active_pifinder": active_pifinder,
        "active_mount": active_mount,
        "pifinder_connected": pifinder_connected,
        "mount_connected": mount_connected,
        "coupling_mode": coupling_mode,
        "correction_action": correction_action,
        # See mount_bridge_drift()'s matching field for why this exists.
        "drift_state": drift_status_prop.get("state"),
        "drift_arcmin": float(drift_raw) if drift_raw not in (None, "") else None,
        "drift_threshold": float(drift_threshold_raw) if drift_threshold_raw not in (None, "") else None,
        "settings_host": settings_host,
        "settings_port": settings_port,
        "settings_correct": settings_correct,
        "target_source": target_source,
        "mount_reject_active": mount_reject_active,
        "mount_reject_message": mount_reject_message,
        "mount_web_ip": mount_web_ip,
        "mount_type_raw": mount_type_raw,
        "pifinder_mount_type": orientation_elements.get("MOUNT_TYPE") or None,
        "pifinder_screen_direction": orientation_elements.get("SCREEN_DIRECTION") or None,
        "orientation_state": orientation_prop.get("state"),
        # #191/#217: pre-fills the Multi-Point Alignment config fields on
        # load, same reasoning as drift_threshold above - without this a
        # page reload always showed the HTML defaults regardless of what
        # was actually saved/set on the driver.
        "align_radius": float(align_config_elements["RADIUS_DEG"]) if align_config_elements.get("RADIUS_DEG") not in (None, "") else None,
        "align_count": float(align_config_elements["POINT_COUNT"]) if align_config_elements.get("POINT_COUNT") not in (None, "") else None,
        "align_min_altitude": float(align_config_elements["MIN_ALTITUDE_DEG"]) if align_config_elements.get("MIN_ALTITUDE_DEG") not in (None, "") else None,
    }


def mount_bridge_drift(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = TIMEOUT_FAST_POLL,
) -> dict:
    """
    Lightweight companion to mount_bridge_status(): only "PiFinder Mount
    Bridge"'s own properties (coupling_mode/correction_action/drift_arcmin),
    no per-device CONNECTION lookups for the linked PiFinder/mount - those
    don't change fast enough to be worth polling on a tight cadence, and
    skipping them keeps this call cheap enough to run every few seconds.
    Added because the drift readout felt "sluggish" tied to the 20s
    connection-status poll (see status_page.html's refreshMbDrift(), kept
    entirely separate from refreshMountBridgeStatus()'s miss-streak/
    unconfirmed-gate logic - a low default timeout here is fine precisely
    because a miss just skips one number update, unlike a miss on the
    connection-status poll which affects button-gating).
    Returns {"running": bool, "coupling_mode": str or None,
    "correction_action": "sync"/"goto"/None, "drift_arcmin": float or None}.
    """
    props = get_properties(device="PiFinder Mount Bridge", host=host, port=port, timeout=timeout)
    device_props = props.get("PiFinder Mount Bridge")
    if not device_props:
        return {
            "running": False,
            "coupling_mode": None,
            "correction_action": None,
            "drift_arcmin": None,
            "mount_reject_active": False,
            "mount_reject_message": None,
            "align_state": None,
            "align_point_index": None,
            "align_point_count": None,
            "align_point_synced": None,
            "align_radius": None,
            "align_count": None,
            "align_min_altitude": None,
        }

    bridge_mode = device_props.get("BRIDGE_MODE", {}).get("elements", {})
    drift_status_prop = device_props.get("DRIFT_STATUS", {})
    drift_status = drift_status_prop.get("elements", {})
    coupling_mode = next((name for name, val in bridge_mode.items() if val == "On"), None)
    correction_action_elements = device_props.get("CORRECTION_ACTION", {}).get("elements", {})
    correction_action_raw = next((name for name, val in correction_action_elements.items() if val == "On"), None)
    correction_action = {"ACTION_SYNC": "sync", "ACTION_GOTO": "goto"}.get(correction_action_raw)
    drift_raw = drift_status.get("DRIFT_ARCMIN")
    mount_reject_prop = device_props.get("MOUNT_REJECT", {})
    mount_reject_active = mount_reject_prop.get("state") == "Alert"
    mount_reject_message = mount_reject_prop.get("elements", {}).get("MESSAGE") or None

    # #191/#217: Multi-Point Alignment's own coarse state (MULTI_POINT_ALIGN
    # itself has no numeric elements worth reading - it's a Start/Stop
    # switch pair, "align_state" here is its *vector* state Idle/Busy/Ok/
    # Alert) plus ALIGN_PROGRESS's poll-friendly point-by-point numbers -
    # added alongside drift/coupling_mode in this same fast-poll companion
    # (not mount_bridge_status()) because progress changes on the same
    # multi-second cadence as drift while a sequence is running.
    align_state = device_props.get("MULTI_POINT_ALIGN", {}).get("state")
    align_progress = device_props.get("ALIGN_PROGRESS", {}).get("elements", {})
    # #191/#217: found live (2026-08-10, direct feedback - "die Werte werden
    # immer wieder auf Default gesetzt") that relying solely on
    # mount_bridge_status() (gated behind role/wmServerRunning checks in the
    # frontend, 20s cadence) left the config fields stuck on their HTML
    # defaults whenever that slower poll's own gating didn't fire for
    # whatever reason - added here too, on the same always-on fast poll the
    # Threshold/drift fields already trust, so reading them back is as
    # reliable as everything else on this row.
    align_config_elements = device_props.get("ALIGN_CONFIG", {}).get("elements", {})

    def _int_or_none(raw):
        return int(float(raw)) if raw not in (None, "") else None

    return {
        "running": True,
        "coupling_mode": coupling_mode,
        "correction_action": correction_action,
        "mount_reject_active": mount_reject_active,
        "mount_reject_message": mount_reject_message,
        # DRIFT_STATUS's own INDI state (Ok/Busy/Alert/Idle) - in
        # MODE_AUTO_CORRECT specifically, the driver sets Busy while
        # actually sending a correction vs. Alert when drift exceeds the
        # threshold but is gated by #79's solve-freshness check (still
        # "wrong", just not something the driver will act on yet). Exposed
        # so the GUI can tell those two apart instead of assuming "exceeded
        # threshold" always means "correcting now" - found live (2026-08-05)
        # showing "Correcting the mount now" while the driver silently
        # skipped every attempt because PiFinder's last solve was minutes
        # old.
        "drift_state": drift_status_prop.get("state"),
        "drift_arcmin": float(drift_raw) if drift_raw not in (None, "") else None,
        "align_state": align_state,
        "align_point_index": _int_or_none(align_progress.get("POINT_INDEX")),
        "align_point_count": _int_or_none(align_progress.get("POINT_COUNT")),
        "align_point_synced": _int_or_none(align_progress.get("POINT_SYNCED")),
        "align_radius": float(align_config_elements["RADIUS_DEG"]) if align_config_elements.get("RADIUS_DEG") not in (None, "") else None,
        "align_count": float(align_config_elements["POINT_COUNT"]) if align_config_elements.get("POINT_COUNT") not in (None, "") else None,
        "align_min_altitude": float(align_config_elements["MIN_ALTITUDE_DEG"]) if align_config_elements.get("MIN_ALTITUDE_DEG") not in (None, "") else None,
    }


def _send(message: str, host: str, port: int, timeout: float) -> None:
    """Fire-and-forget: opens a fresh connection, sends one message, closes.
    indiserver doesn't reply to a new*Vector with a synchronous ack - the
    driver processes it and broadcasts an updated def/setXxxVector to every
    connected client afterward, which a caller can pick up with a follow-up
    get_properties() call if it needs to confirm the change took effect
    (see mount_bridge_status(), used exactly that way elsewhere in this
    module)."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise INDIClientError(f"Could not connect to indiserver at {host}:{port}: {e}") from e
    try:
        sock.sendall(message.encode())
    except OSError as e:
        raise INDIClientError(f"Lost connection to indiserver while sending: {e}") from e
    finally:
        sock.close()


def set_switch(
    device: str,
    vector_name: str,
    on_element: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Sets a one-of-many INDI switch vector (e.g. CONNECTION, BRIDGE_MODE)
    so that exactly `on_element` is On. Reads the vector's current element
    list first and sends every other element explicitly as Off in the same
    message, rather than relying on the driver to infer it - this is the
    same explicit-every-element form verified live while testing Phase 1's
    CONNECTION.CONNECT trigger.

    Raises INDIClientError if the device/vector isn't currently defined
    (e.g. a vector that, like BRIDGE_MODE, only exists once the device is
    already connected - see mount_bridge_status()'s own docstring note)."""
    props = get_properties(device=device, host=host, port=port, timeout=timeout)
    vector = props.get(device, {}).get(vector_name)
    if not vector:
        raise INDIClientError(
            f"{device}: property {vector_name!r} not currently defined "
            "(device may not be connected yet, or the name is wrong)"
        )
    elements = list(vector["elements"].keys())
    if on_element not in elements:
        raise INDIClientError(f"{device}.{vector_name}: unknown element {on_element!r} (known: {elements})")

    lines = [f'<newSwitchVector device="{_xml_escape(device)}" name="{_xml_escape(vector_name)}">']
    for el in elements:
        state = "On" if el == on_element else "Off"
        lines.append(f'<oneSwitch name="{_xml_escape(el)}">{state}</oneSwitch>')
    lines.append("</newSwitchVector>")
    _send("\n".join(lines), host, port, timeout)


def set_text(
    device: str,
    vector_name: str,
    values: dict,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Sets one or more elements of an INDI text vector. `values` is
    {element_name: new_value} - elements not included are left untouched by
    the driver (confirmed for ACTIVE_DEVICES specifically by reading
    pifinder_mount_bridge.cpp's ISNewText(): IUUpdateText() only updates the
    named elements it's given), so a caller only needs to include the
    element(s) it actually wants to change."""
    lines = [f'<newTextVector device="{_xml_escape(device)}" name="{_xml_escape(vector_name)}">']
    for element, value in values.items():
        lines.append(f'<oneText name="{_xml_escape(element)}">{_xml_escape(str(value))}</oneText>')
    lines.append("</newTextVector>")
    _send("\n".join(lines), host, port, timeout)


def connect_device(
    device: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Triggers the standard INDI CONNECTION.CONNECT switch - present on
    every INDI driver, so this works generically for PiFinder LX200, PiFinder
    Mount Bridge, or the user's own mount driver alike. Only sends the
    trigger; connection *parameters* (serial port, baud, TCP host) are the
    user's own responsibility, already configured and saved through some
    other INDI client before this runs - see docs/concepts/
    mount_bridge_web_integration.md's explicit non-goal.

    Exception: "PiFinder LX200" itself (see ensure_pifinder_lx200_tcp()
    below) - its connection target is this project's own pos_server.py, a
    fixed constant on every PFSM install, not user/hardware-specific like a
    real mount's serial port - so that one is set automatically rather than
    left to the user."""
    set_switch(device, "CONNECTION", "CONNECT", host, port, timeout)


def disconnect_device(
    device: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> None:
    """Triggers the standard INDI CONNECTION.DISCONNECT switch - the
    opposite of connect_device(), same generic applicability."""
    set_switch(device, "CONNECTION", "DISCONNECT", host, port, timeout)


PIFINDER_LX200_TCP_HOST = "127.0.0.1"
PIFINDER_LX200_TCP_PORT = "4030"  # pos_server.py's fixed LX200 port - see Readme_PiFinder_LX200.md


def ensure_pifinder_lx200_tcp(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT,
    check_timeout: float = 1.5,
) -> None:
    """Forces "PiFinder LX200"'s own connection onto TCP 127.0.0.1:4030
    (pos_server.py) rather than the INDI/LX200Telescope base class's default
    of a serial port. Found live (2026-07-25): left at its default, this
    driver competes for the same physical USB-serial adapter as the user's
    real mount driver (e.g. "LX200 OnStep"), and whichever connects first
    locks the other out ("already used by another driver or process") -
    confirmed with only one USB-serial adapter (lsusb: one CH340) actually
    present. Unlike a real mount's connection, this one is always the same
    fixed value on every PFSM install - not something to make the user
    remember to configure by hand, per Readme_PiFinder_LX200.md's own setup
    instructions (Connection Mode: TCP, 127.0.0.1:4030).

    Idempotent and safe to call every time before connecting: no-ops if
    already on TCP with the right address (this first check is the only
    slow part if the device happens to already be connected and broadcasting
    - see get_properties()'s own docstring on why an active device's query
    takes close to the full timeout - everything after an actual change is
    needed uses the shorter `check_timeout` instead, since a disconnected/
    reconfiguring device goes quiet quickly). INDI conventionally only
    accepts connection-parameter changes while disconnected, so this
    disconnects first if needed and leaves the device disconnected - the
    caller (see server.py's /api/mount_bridge_connect) does the actual
    CONNECT afterwards."""
    props = get_properties(device="PiFinder LX200", host=host, port=port, timeout=timeout)
    device_props = props.get("PiFinder LX200")
    if not device_props:
        raise INDIClientError("PiFinder LX200: not currently defined (not loaded in the running profile)")

    mode = device_props.get("CONNECTION_MODE", {}).get("elements", {})
    address = device_props.get("DEVICE_ADDRESS", {}).get("elements", {})
    already_correct = (
        mode.get("CONNECTION_TCP") == "On"
        and address.get("ADDRESS") == PIFINDER_LX200_TCP_HOST
        and address.get("PORT") == PIFINDER_LX200_TCP_PORT
    )
    if already_correct:
        return

    if _connection_state(device_props):
        set_switch("PiFinder LX200", "CONNECTION", "DISCONNECT", host, port, check_timeout)

    set_switch("PiFinder LX200", "CONNECTION_MODE", "CONNECTION_TCP", host, port, check_timeout)

    # DEVICE_ADDRESS is only defined by the driver once CONNECTION_TCP has
    # actually been processed (same "properties only exist once triggered"
    # pattern as Mount Bridge's own BRIDGE_MODE-derived properties) - poll
    # briefly rather than assume the switch above has already taken effect
    # by the time this runs.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        check = get_properties(device="PiFinder LX200", host=host, port=port, timeout=check_timeout)
        if "DEVICE_ADDRESS" in check.get("PiFinder LX200", {}):
            break
        time.sleep(0.2)
    else:
        raise INDIClientError("PiFinder LX200: DEVICE_ADDRESS did not appear after switching to TCP mode")

    set_text(
        "PiFinder LX200", "DEVICE_ADDRESS",
        {"ADDRESS": PIFINDER_LX200_TCP_HOST, "PORT": PIFINDER_LX200_TCP_PORT},
        host, port, check_timeout,
    )


def set_mount_bridge_active_devices(
    pifinder_device: str,
    mount_device: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Sets PiFinder Mount Bridge's ACTIVE_DEVICES (ACTIVE_PIFINDER +
    ACTIVE_MOUNT) in one call. `pifinder_device` is normally always
    "PiFinder LX200" (the driver's own default) - passed explicitly rather
    than hardcoded so a caller can confirm/re-assert it rather than assume."""
    set_text(
        "PiFinder Mount Bridge",
        "ACTIVE_DEVICES",
        {"ACTIVE_PIFINDER": pifinder_device, "ACTIVE_MOUNT": mount_device},
        host, port, timeout,
    )


def set_number(
    device: str,
    vector_name: str,
    values: dict,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Sets one or more elements of an INDI number vector. `values` is
    {element_name: float} - like set_text(), elements not included are left
    untouched by the driver."""
    lines = [f'<newNumberVector device="{_xml_escape(device)}" name="{_xml_escape(vector_name)}">']
    for element, value in values.items():
        lines.append(f'<oneNumber name="{_xml_escape(element)}">{value}</oneNumber>')
    lines.append("</newNumberVector>")
    _send("\n".join(lines), host, port, timeout)


# Phase 4: the three Coupling-mode presets. See docs/concepts/
# mount_bridge_web_integration.md §4 for the verified reference table this
# maps to - which mode needs DRIFT_THRESHOLD/CORRECTION_ACTION and which
# doesn't (MODE_GOTO_FORWARD needs neither, confirmed against
# pifinder_mount_bridge.cpp's TimerHit()).
COUPLING_MODES = {"MODE_OFF", "MODE_VERIFY_ALERT", "MODE_AUTO_CORRECT", "MODE_GOTO_FORWARD"}
DRIFT_THRESHOLD_DEFAULT = 5.0  # matches the driver's own IUFillNumber default
CORRECTION_ACTION_DEFAULT = "sync"  # matches the driver's own default (ACTION_SYNC is ISS_ON)


def set_drift_threshold(
    drift_threshold: float,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Standalone DRIFT_THRESHOLD write, split out of set_coupling_mode()
    below so the Control Center can push a changed threshold live while
    Verify/Alert or Auto-correct is already active, without re-asserting
    BRIDGE_MODE (which set_coupling_mode() would also do) - added because
    the threshold input field previously only ever reached the driver via
    a coupling-preset button click, so editing it while a mode was already
    running silently had no effect (found live, 2026-07-29)."""
    set_number(
        "PiFinder Mount Bridge", "DRIFT_THRESHOLD",
        {"THRESHOLD_ARCMIN": drift_threshold},
        host, port, timeout,
    )


def set_coupling_mode(
    mode: str,
    drift_threshold: Optional[float] = None,
    correction_action: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Sets PiFinder Mount Bridge's Coupling mode (BRIDGE_MODE) plus exactly
    the supporting properties that mode actually uses:
      - MODE_VERIFY_ALERT: DRIFT_THRESHOLD only
      - MODE_AUTO_CORRECT: DRIFT_THRESHOLD + CORRECTION_ACTION
      - MODE_GOTO_FORWARD: neither (both args silently ignored if given)
    `correction_action` is "sync" or "goto" (matching the driver's own
    Sync/Goto-Track choice). Supporting properties are set *before*
    BRIDGE_MODE itself, so there's no window where coupling is already
    active with stale threshold/action values still in effect."""
    if mode not in COUPLING_MODES:
        raise INDIClientError(f"Unknown coupling mode {mode!r} (expected one of {COUPLING_MODES})")

    if mode in ("MODE_VERIFY_ALERT", "MODE_AUTO_CORRECT"):
        set_drift_threshold(
            drift_threshold if drift_threshold is not None else DRIFT_THRESHOLD_DEFAULT,
            host, port, timeout,
        )
    if mode == "MODE_AUTO_CORRECT":
        action = correction_action or CORRECTION_ACTION_DEFAULT
        element = "ACTION_GOTO" if action == "goto" else "ACTION_SYNC"
        set_switch("PiFinder Mount Bridge", "CORRECTION_ACTION", element, host, port, timeout)

    set_switch("PiFinder Mount Bridge", "BRIDGE_MODE", mode, host, port, timeout)


def trigger_manual_sync(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """One-shot: syncs the mount to PiFinder's current solved position right
    now (MANUAL_TRIGGER's TRIGGER_SYNC_NOW element) - works regardless of
    which Coupling mode (or Off) is active. Useful after moving the mount by
    hand (no Goto involved at all), where none of the Coupling presets would
    otherwise react."""
    set_switch("PiFinder Mount Bridge", "MANUAL_TRIGGER", "TRIGGER_SYNC_NOW", host, port, timeout)


def trigger_abort_mount(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Emergency stop: sends TELESCOPE_ABORT_MOTION to the active mount right
    now (ABORT_MOUNT's ABORT_MOUNT_NOW element) - works regardless of which
    Coupling mode (or Off) is active, and independent of whether PiFinder's
    own side is ready/available. See #179."""
    set_switch("PiFinder Mount Bridge", "ABORT_MOUNT", "ABORT_MOUNT_NOW", host, port, timeout)


def trigger_multipoint_align_start(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Starts a #191 Multi-Point Alignment sequence (MULTI_POINT_ALIGN's
    ALIGN_START element): fetches fresh candidate points from PiFinder's own
    /api/nearby_bright_stars and works through them one at a time (Goto,
    wait for arrival, wait for a fresh PiFinder solve, Sync). Independent of
    Coupling mode - works whether Coupling is Off or any other preset."""
    set_switch("PiFinder Mount Bridge", "MULTI_POINT_ALIGN", "ALIGN_START", host, port, timeout)


def trigger_multipoint_align_stop(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Aborts an in-progress #191 Multi-Point Alignment sequence
    (MULTI_POINT_ALIGN's ALIGN_STOP element) - reuses the same ABORT_MOUNT
    path as the emergency-stop button, so any current mount motion also
    stops immediately, not just the sequence's own bookkeeping."""
    set_switch("PiFinder Mount Bridge", "MULTI_POINT_ALIGN", "ALIGN_STOP", host, port, timeout)
