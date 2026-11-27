#!/usr/bin/env python3
"""A stand-in for the INDI "LX200 OnStep" mount driver, for onstep_controller_test.py: just the properties the Mount Bridge reads.

indiserver starts it like any driver. Its connection settings say "OnStep over TCP at 127.0.0.1, port 9999"; a GoTo or Sync sent
to it is answered like the real driver does (new target on a GoTo), nothing else happens.
"""
import sys
import xml.etree.ElementTree as ET

DEVICE = "LX200 OnStep"


def out(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def vector(kind, name, elements, state="Ok", verb="def"):
    one = {"Number": "Number", "Text": "Text", "Switch": "Switch"}[kind]
    tag = "def" if verb == "def" else "one"
    extra = ""
    if verb == "def":
        extra = ' label="%s" group="Main Control" perm="rw"' % name
        if kind == "Switch":
            extra += ' rule="OneOfMany"'
    body = []
    for key, value in elements.items():
        fmt = ' format="%.8f" min="-90" max="360" step="0"' if kind == "Number" and verb == "def" else ""
        body.append('<%s%s name="%s"%s>%s</%s%s>' % (tag, one, key, fmt, value, tag, one))
    out('<%s%sVector device="%s" name="%s" state="%s"%s>%s</%s%sVector>' % (verb, kind, DEVICE, name, state, extra, "".join(body),
                                                                           verb, kind))


position = {"RA": 1.0, "DEC": 10.0}
on_coord = {"TRACK": "Off", "SLEW": "On", "SYNC": "Off"}


def define():
    vector("Switch", "CONNECTION", {"CONNECT": "On", "DISCONNECT": "Off"})
    vector("Text", "DRIVER_INFO", {"DRIVER_NAME": DEVICE, "DRIVER_EXEC": "indi_lx200_OnStep", "DRIVER_VERSION": "1.0",
                                   "DRIVER_INTERFACE": "5"})
    vector("Switch", "CONNECTION_MODE", {"CONNECTION_SERIAL": "Off", "CONNECTION_TCP": "On"})
    vector("Text", "DEVICE_ADDRESS", {"ADDRESS": "127.0.0.1", "PORT": "9999"})
    vector("Switch", "ON_COORD_SET", on_coord)
    vector("Number", "EQUATORIAL_EOD_COORD", position)
    vector("Number", "TARGET_EOD_COORD", position, state="Idle")


buf = ""
for line in sys.stdin:
    buf += line
    try:
        root = ET.fromstring("<r>%s</r>" % buf)
    except ET.ParseError:
        continue
    buf = ""
    for item in root:
        if item.tag == "getProperties":
            if item.get("device") in (None, DEVICE):
                define()
        elif item.get("device") == DEVICE and item.get("name") == "ON_COORD_SET":
            chosen = [e.get("name") for e in item if (e.text or "").strip() == "On"]
            if chosen:
                on_coord.update({k: "On" if k == chosen[0] else "Off" for k in on_coord})
                vector("Switch", "ON_COORD_SET", on_coord, verb="set")
        elif item.get("device") == DEVICE and item.get("name") == "EQUATORIAL_EOD_COORD":
            position.update({e.get("name"): float(e.text) for e in item})
            if on_coord["SYNC"] != "On":
                vector("Number", "TARGET_EOD_COORD", position, state="Idle", verb="set")
            vector("Number", "EQUATORIAL_EOD_COORD", position, verb="set")
