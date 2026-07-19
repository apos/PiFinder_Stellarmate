#!/usr/bin/env python3
"""
Mirrors a running PiFinder instance's OLED screen (GET /api/screen, a 128x128
PNG) onto a local raw Linux framebuffer device - e.g. /dev/fb1, as created by
the Waveshare 3.5inch RPi LCD (B) dev/testing screen (see
pifinder_stellarmate_setup.sh's config.txt comment near "waveshare35b-v2").

Deliberately decoupled from PiFinder's own code: talks only to the same
stable, hardware-independent Remote API already used by pf_remote.py and the
Setup GUI's own OLED mirror (GET /api/screen). Works identically for Real
Mode or Fake Mode - whichever instance answers first - so it's equally
useful with or without the real HAT attached.

Run with PiFinder's own venv python (already has Pillow + numpy):
    /home/stellarmate/PiFinder/python/.venv/bin/python3 fb_screen_mirror.py

Usage:
    fb_screen_mirror.py [--fb /dev/fb1] [--rotate 0|90|180|270] [--base-url URL] [--interval 0.3]

If --base-url is not given, probes 127.0.0.1 on ports 80, 8080 (real
service + its port-80-busy fallback) and 8081 (fake_mode.sh's fake-hardware
instance), same candidates the Setup GUI's own OLED-mirror probe uses.
"""
import argparse
import sys
import time
import urllib.request
from io import BytesIO

import numpy as np
from PIL import Image

DEFAULT_PORTS = [80, 8080, 8081]


def find_base_url(explicit):
    if explicit:
        return explicit.rstrip("/")
    for port in DEFAULT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{url}/image", timeout=2) as resp:
                # StellarMate's own nginx dashboard squats on port 80 and
                # returns HTTP 200 with an HTML body for ANY path, including
                # /image - a status-code-only check would false-positive on
                # it. Actually decode the response as an image, the same
                # thing an <img> tag's onload/onerror implicitly checks.
                Image.open(BytesIO(resp.read())).verify()
            return url
        except Exception:
            continue
    return None


def fb_virtual_size(fb_path):
    idx = fb_path.rstrip("/").rsplit("fb", 1)[-1]
    with open(f"/sys/class/graphics/fb{idx}/virtual_size") as f:
        w, h = f.read().strip().split(",")
    return int(w), int(h)


def fit_and_rotate(img, fb_w, fb_h, rotate):
    if rotate:
        # PIL's own convention: positive angle = counter-clockwise ("left").
        img = img.rotate(rotate, expand=True)
    # Letterbox: scale to fit inside the framebuffer, preserve aspect ratio,
    # center on a black background - PiFinder's screen is square, most
    # small SPI panels aren't, so this avoids a distorted/stretched image.
    scale = min(fb_w / img.width, fb_h / img.height)
    new_w, new_h = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("RGB", (fb_w, fb_h), (0, 0, 0))
    canvas.paste(resized, ((fb_w - new_w) // 2, (fb_h - new_h) // 2))
    return canvas


def to_rgb565(img):
    """PIL RGB image -> little-endian RGB565 bytes, vectorized via numpy."""
    arr = np.asarray(img, dtype=np.uint16)
    r = (arr[:, :, 0] & 0xF8) << 8
    g = (arr[:, :, 1] & 0xFC) << 3
    b = arr[:, :, 2] >> 3
    packed = (r | g | b).astype("<u2")
    return packed.tobytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fb", default="/dev/fb1", help="framebuffer device (default: /dev/fb1)")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                     help="degrees counter-clockwise (\"left\"), default 0")
    ap.add_argument("--base-url", default=None, help="e.g. http://127.0.0.1:8081 - auto-probed if omitted")
    ap.add_argument("--interval", type=float, default=0.3, help="seconds between polls (default 0.3)")
    args = ap.parse_args()

    fb_w, fb_h = fb_virtual_size(args.fb)
    print(f"Framebuffer {args.fb}: {fb_w}x{fb_h}")

    base_url = args.base_url
    last_ok_frame = None

    while True:
        if base_url is None:
            base_url = find_base_url(None)
            if base_url is None:
                print("No PiFinder instance reachable on 80/8080/8081 - retrying...", file=sys.stderr)
                time.sleep(2)
                continue
            print(f"Mirroring {base_url}/image -> {args.fb}")

        try:
            with urllib.request.urlopen(f"{base_url}/image", timeout=2) as resp:
                img = Image.open(BytesIO(resp.read())).convert("RGB")
            frame = to_rgb565(fit_and_rotate(img, fb_w, fb_h, args.rotate))
            if frame != last_ok_frame:
                with open(args.fb, "wb") as f:
                    f.write(frame)
                last_ok_frame = frame
        except Exception as e:
            print(f"Lost connection to {base_url}: {e} - will re-probe", file=sys.stderr)
            base_url = None if args.base_url is None else args.base_url
            time.sleep(1)
            continue

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
