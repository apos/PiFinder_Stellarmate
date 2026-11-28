#!/usr/bin/env python3
"""An INDI driver's stdout is its protocol stream: every libcurl request in a PFSM driver must set a write function (issue #385).

    python3 test_tools/driver_stdout_test.py
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted(p for d in REPO.glob("indi_pifinder*") for p in d.glob("*.cpp"))


class CurlWritesNowhereNearStdoutTest(unittest.TestCase):
    def test_there_are_driver_sources_with_requests(self):
        self.assertTrue(any("curl_easy_init()" in p.read_text() for p in SOURCES))

    def test_every_request_sets_a_write_function(self):
        missing = []
        for path in SOURCES:
            text = path.read_text()
            # one request = from curl_easy_init() to the curl_easy_perform() that follows it
            for match in re.finditer(r"curl_easy_init\(\)(.*?)curl_easy_perform\(", text, re.S):
                if "CURLOPT_WRITEFUNCTION" not in match.group(1):
                    missing.append("%s:%d" % (path.relative_to(REPO), text.count("\n", 0, match.start()) + 1))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
