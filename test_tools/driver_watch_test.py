#!/usr/bin/env python3
"""No PFSM driver may filter a watched device down to single properties.

    python3 test_tools/driver_watch_test.py

libindi's watchProperty() makes the client drop every other property and every message of that device for good, across reconnects
(found 2026-11-27: after one binding retry the Mount Bridge never saw PiFinder's target again and forwarded no GoTo).
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent


class NoPropertyFilterTest(unittest.TestCase):
    def test_no_driver_calls_watch_property(self):
        hits = []
        for path in sorted(p for d in REPO.glob("indi_pifinder*") for p in d.glob("*.cpp")):
            for number, line in enumerate(path.read_text().split("\n"), 1):
                if re.search(r"\bwatchProperty\s*\(", line.split("//")[0]):
                    hits.append("%s:%d" % (path.name, number))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
