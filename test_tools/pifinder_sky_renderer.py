#!/usr/bin/env python3
"""Render a synthetic night-sky frame for PiFinder from the GSC star catalogue.

Part of the realmode sky simulation (docs/concepts/pifinder_realmode_sky_simulation.md, issue #344): a frame like this
stands in for the camera picture, so PiFinder's real solver (cedar-detect + cedar-solve) can run without a night sky.

    python3 test_tools/pifinder_sky_renderer.py --ra 56.75 --dec 24.12 --out /tmp/m45.png
    python3 test_tools/pifinder_sky_renderer.py --ra-hours 3.7867 --dec 24.12 --roll 30 --fov 12 --out /tmp/m45.png

Coordinates are J2000 degrees (RA may also be given in hours). Needs `gsc` on the PATH and the GSC data (GSCDAT, default
/usr/share/GSC) and numpy + pillow. The projection (gnomonic) and the star list call follow INDI's CCD simulator.

Orientation: north up, east to the LEFT for roll 0, as a camera sees the sky. `--roll` turns the field counter-clockwise
(degrees, position angle of the image's "up" direction measured from north towards east). `--mirror` flips it, for finding
out which parity PiFinder's solver wants.
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image

GSC_DEFAULT_DIR = "/usr/share/GSC"


def query_gsc(ra_deg, dec_deg, radius_arcmin, faint_mag, limit=6000, runner=None):
    """[(ra_deg, dec_deg, mag)] of real stars (GSC class 0) within the radius, brightest first.

    Same call INDI's simulator makes: gsc -c RA +DEC -r RADIUS -m 0 FAINT -n LIMIT
    """
    env = dict(os.environ)
    env.setdefault("GSCDAT", GSC_DEFAULT_DIR)
    cmd = ["gsc", "-c", "%8.6f" % ra_deg, "%+8.6f" % dec_deg, "-r", "%4.1f" % radius_arcmin,
           "-m", "0", "%4.2f" % faint_mag, "-n", str(limit)]
    if runner is None:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        if proc.returncode != 0 or "error" in proc.stdout.lower()[:200]:
            raise RuntimeError("gsc failed: " + (proc.stderr or proc.stdout)[:300])
        text = proc.stdout
    else:
        text = runner(cmd)
    return parse_gsc(text)


def parse_gsc(text):
    stars = []
    for line in text.splitlines():
        tok = line.split()
        if len(tok) < 8:
            continue
        try:
            ra, dec, mag, cls = float(tok[1]), float(tok[2]), float(tok[4]), int(tok[7])
        except ValueError:
            continue
        if cls != 0:  # 3 = non-stellar (galaxy, nebula): not a point source
            continue
        stars.append((ra, dec, mag))
    stars.sort(key=lambda s: s[2])
    return stars


def project(stars, ra0_deg, dec0_deg, fov_deg, size, roll_deg=0.0, mirror=False):
    """Pixel positions (x, y) and mags for the stars in front of the tangent plane, inside the frame.

    Gnomonic projection about (ra0, dec0). x grows to the right, y grows downwards, north is up and east is left at roll 0.
    """
    ra = np.radians([s[0] for s in stars])
    dec = np.radians([s[1] for s in stars])
    mag = np.array([s[2] for s in stars])
    a0, d0 = math.radians(ra0_deg), math.radians(dec0_deg)
    cosc = np.sin(d0) * np.sin(dec) + np.cos(d0) * np.cos(dec) * np.cos(ra - a0)
    front = cosc > 0
    xi = np.cos(dec) * np.sin(ra - a0) / np.where(front, cosc, 1)          # towards east
    eta = (np.cos(d0) * np.sin(dec) - np.sin(d0) * np.cos(dec) * np.cos(ra - a0)) / np.where(front, cosc, 1)  # towards north
    roll = math.radians(roll_deg)
    # image "up" points to position angle roll (from north towards east)
    right = -(xi * math.cos(roll) - eta * math.sin(roll))   # east is left
    up = xi * math.sin(roll) + eta * math.cos(roll)
    if mirror:
        right = -right
    scale = size / (2.0 * math.tan(math.radians(fov_deg) / 2.0))  # pixels per unit of tangent plane
    # array index i is the CENTRE of pixel i, so the frame centre lies half a pixel before index size/2
    centre = size / 2.0 - 0.5
    x = centre + right * scale
    y = centre - up * scale
    keep = front & (x > -8) & (x < size + 8) & (y > -8) & (y < size + 8)
    return x[keep], y[keep], mag[keep]


def render(x, y, mag, size=512, seeing_px=1.4, mag_saturation=6.0, bias=8.0, noise=2.5, seed=None):
    """Grayscale uint8 frame: a Gaussian per star on a noisy background."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size), dtype=np.float64)
    sigma = seeing_px / 2.355
    half = int(math.ceil(4 * sigma)) + 1
    offs = np.arange(-half, half + 1)
    for xs, ys, m in zip(x, y, mag):
        peak = 255.0 * 10 ** (-0.4 * (m - mag_saturation))
        cx, cy = int(round(xs)), int(round(ys))
        gx = np.exp(-((offs + cx - xs) ** 2) / (2 * sigma ** 2))
        gy = np.exp(-((offs + cy - ys) ** 2) / (2 * sigma ** 2))
        x0, x1 = cx - half, cx + half + 1
        y0, y1 = cy - half, cy + half + 1
        if x1 <= 0 or y1 <= 0 or x0 >= size or y0 >= size:
            continue
        patch = peak * np.outer(gy, gx)
        px0, py0 = max(x0, 0), max(y0, 0)
        px1, py1 = min(x1, size), min(y1, size)
        img[py0:py1, px0:px1] += patch[py0 - y0:py1 - y0, px0 - x0:px1 - x0]
    img += bias + rng.normal(0.0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def render_field(ra_deg, dec_deg, fov_deg=13.7, roll_deg=0.0, size=512, faint_mag=9.0, mirror=False, seed=None, runner=None):
    # radius: half the frame diagonal plus a margin, in arcminutes
    radius = fov_deg * 60.0 * math.sqrt(2) / 2.0 * 1.05
    stars = query_gsc(ra_deg, dec_deg, radius, faint_mag, runner=runner)
    x, y, mag = project(stars, ra_deg, dec_deg, fov_deg, size, roll_deg, mirror)
    return render(x, y, mag, size=size, seed=seed), len(x)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ra = ap.add_mutually_exclusive_group(required=True)
    ra.add_argument("--ra", type=float, help="right ascension J2000, degrees")
    ra.add_argument("--ra-hours", type=float, help="right ascension J2000, hours")
    ap.add_argument("--dec", type=float, required=True, help="declination J2000, degrees")
    ap.add_argument("--fov", type=float, default=13.7,
                    help="field of view across the frame, degrees (default 13.7 = imx296 with the 16 mm lens; PiFinder's solver gate rejects fields outside the real optics' window)")
    ap.add_argument("--roll", type=float, default=0.0, help="field rotation, degrees (default 0)")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--faint-mag", type=float, default=9.0)
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    ra_deg = args.ra if args.ra is not None else args.ra_hours * 15.0
    frame, count = render_field(ra_deg, args.dec, args.fov, args.roll, args.size, args.faint_mag, args.mirror, args.seed)
    Image.fromarray(frame, "L").save(args.out)
    print(f"{args.out}: {args.size}x{args.size}, {count} stars, centre RA {ra_deg:.4f} Dec {args.dec:+.4f}, fov {args.fov}, roll {args.roll}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
