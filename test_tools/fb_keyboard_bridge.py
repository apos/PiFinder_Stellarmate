#!/usr/bin/env python3
"""
Bridges a plain USB/wireless keyboard or numpad (any evdev keyboard device)
to PiFinder's Remote API (POST /api/key) - for controlling PiFinder without
physical keypad/HAT hardware attached. Meant to be run alongside
test_tools/fb_screen_mirror.py for a fully hardware-independent dev/test
setup (e.g. Fake Mode + a small SPI screen + a plain keypad).

Deliberately decoupled from PiFinder's own code: reads raw evdev key events
(works with or without an X11/desktop session - PiFinder's own
`--keyboard local` mode needs X11 via pynput, this doesn't), and only talks
to the same stable, hardware-independent /api/key endpoint already used by
pf_remote.py and the Setup GUI.

Tuned for a numpad-only device (e.g. LogiLink ID0120) with no dedicated
arrow keys, per the confirmed physical layout:

    NumLock off:  4=LEFT  8=UP  6=RIGHT  2=DOWN   +=PLUS  -=MINUS  Enter=SQUARE
    NumLock on:   4/8/6/2 are plain digits (for catalog-number entry etc.)
                  +/-/Enter unchanged either way
    Backspace/Delete: always LEFT (a second, convenient "back" key)
    1/3/5/7/9/0, /, *: always plain digits / unused

NumLock doesn't change the raw evdev keycode a genuine numpad key reports
(that only happens at a higher, keymap/text-input layer we deliberately
bypass) - so this script tracks NumLock state itself (seeded from the
device's current LED state at startup, then toggled on every NumLock
keypress) to decide how to interpret KP_4/KP_8/KP_6/KP_2 dynamically.

Also matches keyboard_pi.py's real-hardware behavior:
- Holding UP/DOWN repeats the short press every ~1s (fast list scrolling).
- Holding LEFT/RIGHT/SQUARE for >1s sends the LNG_* variant once instead
  (LNG_LEFT = "back to top menu").
- Holding Enter/SQUARE while pressing another mapped key sends that key's
  ALT_* variant (only ALT_0/ALT_PLUS/ALT_MINUS/ALT_LEFT/UP/DOWN/RIGHT exist
  on real hardware either).

Requires the `evdev` package - not part of PiFinder's own requirements,
install once into PiFinder's venv:
    /home/stellarmate/PiFinder/python/.venv/bin/pip install evdev

Usage:
    fb_keyboard_bridge.py [--device /dev/input/eventN] [--base-url URL]
If --device is omitted, auto-detects the first device that looks like a
keyboard/numpad (has KEY_ENTER and at least KEY_KP1) - skips the Waveshare
touchscreen and the power button, which also show up as input devices.
"""
import argparse
import json
import sys
import urllib.request
from io import BytesIO
from threading import Timer

import evdev
from evdev import ecodes
from PIL import Image

DEFAULT_PORTS = [80, 8080, 8081]
LONG_PRESS_SECONDS = 1.0
REPEAT_SECONDS = 1.0

SQUARE_KEYS = {ecodes.KEY_ENTER, ecodes.KEY_KPENTER}
FIXED_NAV = {  # always LEFT/etc regardless of NumLock
    ecodes.KEY_BACKSPACE: "LEFT",
    ecodes.KEY_DELETE: "LEFT",
    ecodes.KEY_LEFT: "LEFT",
    ecodes.KEY_RIGHT: "RIGHT",
    ecodes.KEY_UP: "UP",
    ecodes.KEY_DOWN: "DOWN",
}
FIXED_BTN = {
    ecodes.KEY_KPPLUS: "PLUS",
    ecodes.KEY_KPMINUS: "MINUS",
}
NUMPAD_NAV_WHEN_NUMLOCK_OFF = {
    ecodes.KEY_KP4: "LEFT",
    ecodes.KEY_KP8: "UP",
    ecodes.KEY_KP6: "RIGHT",
    ecodes.KEY_KP2: "DOWN",
}
DUAL_KEY_DIGIT_VALUE = {ecodes.KEY_KP4: 4, ecodes.KEY_KP8: 8, ecodes.KEY_KP6: 6, ecodes.KEY_KP2: 2}
ALWAYS_DIGIT = {
    ecodes.KEY_KP0: 0, ecodes.KEY_KP1: 1, ecodes.KEY_KP3: 3,
    ecodes.KEY_KP5: 5, ecodes.KEY_KP7: 7, ecodes.KEY_KP9: 9,
    ecodes.KEY_0: 0, ecodes.KEY_1: 1, ecodes.KEY_2: 2, ecodes.KEY_3: 3, ecodes.KEY_4: 4,
    ecodes.KEY_5: 5, ecodes.KEY_6: 6, ecodes.KEY_7: 7, ecodes.KEY_8: 8, ecodes.KEY_9: 9,
}
NAV_LONG = {"LEFT": "LNG_LEFT", "RIGHT": "LNG_RIGHT"}  # UP/DOWN repeat instead, see REPEAT below
REPEAT_VALUES = {"UP", "DOWN"}
NAV_ALT = {"LEFT": "ALT_LEFT", "RIGHT": "ALT_RIGHT", "UP": "ALT_UP", "DOWN": "ALT_DOWN"}


def classify(code, numlock_on):
    """Returns (kind, value) or None to ignore. kind is one of:
    "numlock", "square", "nav", "btn", "digit"."""
    if code == ecodes.KEY_NUMLOCK:
        return ("numlock", None)
    if code in SQUARE_KEYS:
        return ("square", None)
    if code in FIXED_NAV:
        return ("nav", FIXED_NAV[code])
    if code in FIXED_BTN:
        return ("btn", FIXED_BTN[code])
    if code in NUMPAD_NAV_WHEN_NUMLOCK_OFF:
        if numlock_on:
            return ("digit", DUAL_KEY_DIGIT_VALUE[code])
        return ("nav", NUMPAD_NAV_WHEN_NUMLOCK_OFF[code])
    if code in ALWAYS_DIGIT:
        return ("digit", ALWAYS_DIGIT[code])
    return None


def find_base_url(explicit):
    if explicit:
        return explicit.rstrip("/")
    for port in DEFAULT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{url}/image", timeout=2) as resp:
                # Same nginx-dashboard-on-port-80 trap as fb_screen_mirror.py -
                # verify it's actually an image, not just a 200 status.
                Image.open(BytesIO(resp.read())).verify()
            return url
        except Exception:
            continue
    return None


def find_keyboard_device(explicit):
    if explicit:
        return evdev.InputDevice(explicit)
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_ENTER in caps and (ecodes.KEY_KP1 in caps or ecodes.KEY_A in caps):
            return dev
    return None


def send_key(base_url, button):
    body = json.dumps({"button": button}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/key", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=2)
        print(f"-> {button}")
    except Exception as e:
        print(f"send_key({button!r}) failed: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default=None, help="e.g. /dev/input/event0 - auto-detected if omitted")
    ap.add_argument("--base-url", default=None, help="e.g. http://127.0.0.1:8081 - auto-probed if omitted")
    args = ap.parse_args()

    dev = find_keyboard_device(args.device)
    if dev is None:
        print("No keyboard/numpad-like input device found.", file=sys.stderr)
        sys.exit(1)
    print(f"Keyboard: {dev.name} ({dev.path})")

    numlock_on = ecodes.LED_NUML in dev.leds()
    print(f"NumLock currently: {'ON (4/8/6/2 = digits)' if numlock_on else 'OFF (4/8/6/2 = arrows)'}")

    base_url = find_base_url(args.base_url)
    if base_url is None:
        print("No PiFinder instance reachable on 80/8080/8081 yet - will keep trying as keys come in.", file=sys.stderr)
    else:
        print(f"Sending to {base_url}/api/key")

    square_held = False
    active = {}       # keycode -> (kind, value) snapshotted at key-down
    hold_timers = {}  # keycode -> Timer
    # Set by fire_hold() itself (the timer thread) the instant a long-press/
    # hold action is sent, *before* any network I/O - the key-up handler
    # (main thread) only ever reads/clears this, never infers "did it fire"
    # from hold_timers bookkeeping. Using hold_timers for both jobs raced:
    # fire_hold() pops itself out of hold_timers right as it fires, so by the
    # time key-up ran `hold_timers.pop(code, None)` it could already be gone,
    # making key-up think the long-press *hadn't* fired and send a spurious
    # extra short press on release - which, for SQUARE, immediately closed
    # the marking menu it had just opened (key_square() pops the marking
    # menu stack). Found live: the menu opened correctly but vanished the
    # instant the key was released.
    fired_codes = set()

    def get_base_url():
        nonlocal base_url
        if base_url is None:
            base_url = find_base_url(args.base_url)
        return base_url

    def fire_hold(code, kind, value):
        url = get_base_url()
        if url is None:
            return
        if kind == "nav" and value in REPEAT_VALUES:
            send_key(url, value)
            t = Timer(REPEAT_SECONDS, fire_hold, args=(code, kind, value))
            t.daemon = True
            t.start()
            hold_timers[code] = t
        elif kind == "nav":
            fired_codes.add(code)
            send_key(url, NAV_LONG[value])
        elif kind == "square":
            fired_codes.add(code)
            send_key(url, "LNG_SQUARE")

    print("Listening for key presses (Ctrl-C to stop)...")
    for event in dev.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        code = event.code

        if event.value == 1:  # key down
            c = classify(code, numlock_on)
            if c is None:
                continue
            kind, value = c
            if kind == "numlock":
                numlock_on = not numlock_on
                print(f"NumLock toggled: {'ON (4/8/6/2 = digits)' if numlock_on else 'OFF (4/8/6/2 = arrows)'}")
                continue
            active[code] = c
            if kind == "square":
                square_held = True
            elif square_held:
                # Part of a SQUARE+<key> ALT combo - don't arm a
                # long-press/repeat timer, that's only for a plain press.
                continue
            if kind in ("nav", "square"):
                t = Timer(LONG_PRESS_SECONDS, fire_hold, args=(code, kind, value))
                t.daemon = True
                t.start()
                hold_timers[code] = t

        elif event.value == 0:  # key up
            c = active.pop(code, None)
            if c is None:
                continue
            kind, value = c
            timer = hold_timers.pop(code, None)
            if timer is not None:
                timer.cancel()  # no-op if it already fired
            fired = code in fired_codes
            fired_codes.discard(code)

            if kind == "square":
                square_held = False
                if not fired:
                    url = get_base_url()
                    if url:
                        send_key(url, "SQUARE")
                continue

            if fired and value not in REPEAT_VALUES:
                # Long-press already sent its LNG_* action - don't also send
                # the short action (matches keyboard_pi.py's hold_sent logic).
                continue

            url = get_base_url()
            if url is None:
                continue

            if kind == "nav":
                send_key(url, NAV_ALT[value] if square_held else value)
            elif kind == "btn":
                send_key(url, ("ALT_" + value) if square_held else value)
            elif kind == "digit":
                if square_held and value == 0:
                    send_key(url, "ALT_0")
                else:
                    send_key(url, value)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
