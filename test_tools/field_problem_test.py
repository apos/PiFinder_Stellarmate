#!/usr/bin/env python3
"""The live tests may leave a star field only when the simulated camera is at fault (#697), never to hide a Bridge fault.

    python3 test_tools/field_problem_test.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mount_goto_refine_test as t  # noqa: E402

TARGET = (8.3, 30.0)


def verdict(solution, mount=TARGET):
    t.solution = lambda: solution
    t.mount_position = lambda: mount
    return t.field_problem(*TARGET)


def solve(source="CAM", ra_deg=124.1, dec=30.1, age=1.0):
    return {"solve_source": source, "RA": ra_deg, "Dec": dec, "Matches": 26, "last_solve_success": time.time() - age}


CASES = [
    ("a good solve is no excuse", verdict(solve()) is None),
    ("no solve for a long time", "cannot solve" in (verdict(solve("CAM_FAILED", age=60)) or "")),
    ("a short gap is no excuse", verdict(solve("CAM_FAILED", age=5)) is None),
    ("a solve far from the mount", "wrongly" in (verdict(solve(ra_deg=276.8, dec=-51.4)) or "")),
    ("a mount that did not arrive is the Bridge's or the mount's matter", verdict(solve(ra_deg=276.8, dec=-51.4), (9.5, 30.0)) is None),
    ("PiFinder not answering is no field problem", verdict(None) is None),
]

if __name__ == "__main__":
    for name, ok in CASES:
        print("%s %s" % ("ok  " if ok else "FAIL", name))
    sys.exit(0 if all(ok for _, ok in CASES) else 1)
