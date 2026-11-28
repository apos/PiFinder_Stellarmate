#!/usr/bin/env python3
"""The drivers ask PiFinder on port 8080 first, then 80.

    python3 test_tools/driver_port_order_test.py

On StellarMate port 80 is nginx in front of EkosLive: it answers PiFinder's addresses with pages that are not PiFinder (basic-memory
00225). Port 80 stays as the fallback for a PiFinder on its own operating system.
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
URL = re.compile(r'"(?:http://127\.0\.0\.1)?(:8080)?(/api/[a-z_]+)')


class PortOrderTest(unittest.TestCase):
    def test_every_request_tries_8080_before_80(self):
        pairs, wrong = 0, []
        for path in sorted(p for d in REPO.glob("indi_pifinder*") for p in d.glob("*.cpp")):
            text = path.read_text()
            hits = [m for m in URL.finditer(text) if not text[text.rfind("\n", 0, m.start()) + 1:m.start()].lstrip().startswith("//")]
            for first, second in zip(hits[0::2], hits[1::2]):
                pairs += 1
                if not (first.group(1) and not second.group(1) and first.group(2) == second.group(2)):
                    wrong.append("%s:%d %s" % (path.name, text.count("\n", 0, first.start()) + 1, first.group(2)))
            self.assertEqual(len(hits) % 2, 0, "%s: a PiFinder request with only one port" % path.name)
        self.assertGreater(pairs, 10)
        self.assertEqual(wrong, [])

    def test_port_80_only_when_nothing_listens_on_8080(self):
        for name, path in (("bridge", "indi_pifinder_bridge/pifinder_mount_bridge.cpp"), ("lx200", "indi_pifinder/lx200_pifinder.cpp"),
                           ("simulator", "indi_pifinder_simulator/pifinder_simulator.cpp")):
            text = (REPO / path).read_text()
            hits = [m for m in URL.finditer(text) if not text[text.rfind("\n", 0, m.start()) + 1:m.start()].lstrip().startswith("//")]
            self.assertIn("CURLE_COULDNT_CONNECT", text)
            if name == "simulator":     # one loop over both ports: it leaves the loop unless the connection was refused
                self.assertIn("if (res != CURLE_OK && res != CURLE_COULDNT_CONNECT)", text)
                continue
            guards = len(re.findall(r"&& nothingOn8080\(\)|nothingOn8080\(\) &&", text))
            self.assertEqual(guards, len(hits) // 2, "%s: every request on port 80 is guarded" % name)


if __name__ == "__main__":
    unittest.main()
