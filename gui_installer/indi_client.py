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
import xml.parsers.expat
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7624
DEFAULT_TIMEOUT = 3.0

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
        sock.settimeout(timeout)
        request = (
            f'<getProperties version="1.7" device="{device}"/>'
            if device
            else '<getProperties version="1.7"/>'
        )
        sock.sendall(request.encode())
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                parser.Parse(chunk, False)
        except socket.timeout:
            pass  # expected: indiserver keeps the connection open, we only read the initial burst
        except xml.parsers.expat.ExpatError as e:
            raise INDIClientError(f"Malformed INDI XML from indiserver: {e}") from e
    finally:
        sock.close()

    return result


def mount_bridge_status(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """
    Phase 1 read-only snapshot of "PiFinder Mount Bridge"'s relevant
    properties (see docs/concepts/mount_bridge_web_integration.md §4 for the
    verified property reference this maps to). Returns a dict with:
      - "running": bool - whether the device answered at all
      - "active_pifinder"/"active_mount": str - ACTIVE_DEVICES elements
      - "coupling_mode": str or None - whichever BRIDGE_MODE element is "On"
      - "drift_arcmin": float or None - current DRIFT_STATUS reading
    All fields besides "running" are None if the device isn't running/known.
    """
    props = get_properties(device="PiFinder Mount Bridge", host=host, port=port, timeout=timeout)
    device_props = props.get("PiFinder Mount Bridge")
    if not device_props:
        return {
            "running": False,
            "active_pifinder": None,
            "active_mount": None,
            "coupling_mode": None,
            "drift_arcmin": None,
        }

    active_devices = device_props.get("ACTIVE_DEVICES", {}).get("elements", {})
    bridge_mode = device_props.get("BRIDGE_MODE", {}).get("elements", {})
    drift_status = device_props.get("DRIFT_STATUS", {}).get("elements", {})

    coupling_mode = next((name for name, val in bridge_mode.items() if val == "On"), None)
    drift_raw = drift_status.get("DRIFT_ARCMIN")

    return {
        "running": True,
        "active_pifinder": active_devices.get("ACTIVE_PIFINDER") or None,
        "active_mount": active_devices.get("ACTIVE_MOUNT") or None,
        "coupling_mode": coupling_mode,
        "drift_arcmin": float(drift_raw) if drift_raw not in (None, "") else None,
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
    mount_bridge_web_integration.md's explicit non-goal."""
    set_switch(device, "CONNECTION", "CONNECT", host, port, timeout)


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
