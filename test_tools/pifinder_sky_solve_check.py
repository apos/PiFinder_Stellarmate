#!/usr/bin/env python3
"""Solve a rendered frame with PiFinder's own solver library and compare with where it was rendered.

Run it with PiFinder's venv (it needs tetra3):

    ~/PiFinder/python/.venv/bin/python test_tools/pifinder_sky_solve_check.py --ra 56.75 --dec 24.12 [--roll 30] [--mirror]

It renders a field (pifinder_sky_renderer.py), finds the stars (tetra3's own centroiding, no server needed), solves against
PiFinder's pattern database and prints the difference in arcminutes. Does not touch the running PiFinder service.
"""
import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pifinder_sky_renderer as renderer  # noqa: E402

PF_PYTHON = os.path.expanduser("~/PiFinder/python")
PF_DB = os.path.expanduser("~/PiFinder/astro_data/pifinder_fov10-5_m7_hip.npz")


def angular_sep_arcmin(ra1, dec1, ra2, dec2):
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 60.0


def solve(frame, fov_estimate=None, fov_max_error=None):
    sys.path.insert(0, PF_PYTHON)
    import numpy as np
    import tetra3

    t3 = tetra3.Tetra3(PF_DB)
    centroids = tetra3.get_centroids_from_image(np.asarray(frame), sigma=2, min_area=3, max_area=100, max_returned=40)
    if hasattr(centroids, "shape") and len(centroids) == 0:
        return None, 0
    started = time.time()
    kwargs = {}
    if fov_estimate:
        kwargs["fov_estimate"], kwargs["fov_max_error"] = fov_estimate, fov_max_error
    result = t3.solve_from_centroids(centroids, frame.shape[::-1], match_max_error=0.005, solve_timeout=3000, **kwargs)
    result["_seconds"] = time.time() - started
    return result, len(centroids)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--fov", type=float, default=10.5)
    ap.add_argument("--roll", type=float, default=0.0)
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--faint-mag", type=float, default=9.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--save", help="also save the frame here")
    args = ap.parse_args(argv)

    frame, count = renderer.render_field(args.ra, args.dec, args.fov, args.roll, 512, args.faint_mag, args.mirror, args.seed)
    if args.save:
        from PIL import Image
        Image.fromarray(frame, "L").save(args.save)
    result, n_found = solve(frame)
    print(f"rendered {count} catalogue stars, tetra3 found {n_found} centroids")
    if not result or result.get("RA") is None:
        print("NO SOLVE")
        return 1
    sep = angular_sep_arcmin(args.ra, args.dec, result["RA"], result["Dec"])
    print(f"solved RA {result['RA']:.4f} Dec {result['Dec']:+.4f} roll {result.get('Roll')} fov {result.get('FOV')} "
          f"matches {result.get('Matches')} in {result['_seconds']:.2f}s")
    print(f"difference to the render centre: {sep:.2f} arcmin  (rendered roll {args.roll}, mirror {args.mirror})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
