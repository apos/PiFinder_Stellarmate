#!/usr/bin/env python3
"""The Control Center's side of the time and location check (server._clock_check, _clock_fix_mount) with stand-ins.

    python3 test_tools/clock_server_test.py
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import clock_status  # noqa: E402
import indi_client  # noqa: E402
import server  # noqa: E402

HOME = (49.4776, 8.4508)
M = "Telescope Simulator"


class Mount:
    """Just the INDI calls the check uses."""

    def __init__(self, slewing=False, ignore=False, align=None, after=None):
        self.after = after   # the position it reports once something was written
        self.props = {"EQUATORIAL_EOD_COORD": {"state": "Busy" if slewing else "Ok", "elements": {"RA": "5.0", "DEC": "40.0"}},
                      "GEOGRAPHIC_COORD": {"state": "Ok", "elements": {"LAT": "40.0", "LONG": "8.0", "ELEV": "100"}},
                      "TIME_UTC": {"state": "Ok", "elements": {"UTC": "2026-01-01T00:00:00", "OFFSET": "1.00"}}}
        if align:
            self.props["Align Process"] = {"elements": {"6": align[0], "7": align[1]}}
        self.ignore, self.sent = ignore, []

    def get_properties(self, device=None, **kwargs):
        return {M: self.props} if device == M else {}

    def set_number(self, device, name, values, **kwargs):
        self.sent.append(name)
        if self.after:
            self.props["EQUATORIAL_EOD_COORD"]["elements"] = dict(self.after)
        if not self.ignore:
            self.props[name]["elements"] = {k: str(v) for k, v in values.items()}

    set_text = set_number


class Server(unittest.TestCase):
    def setUp(self):
        self.saved = {(module, name): getattr(module, name) for module, name in (
            (indi_client, "get_properties"), (indi_client, "set_number"), (indi_client, "set_text"),
            (indi_client, "active_mount_name"), (clock_status, "read_kstars"), (clock_status, "ntp_synchronized"),
            (server, "_pifinder_status_snapshot"), (server.time, "sleep"))}
        self.kstars = {"location": HOME, "offset": 1.0, "elevation": 0.0, "realtime": True}
        clock_status.read_kstars = lambda *a: self.kstars
        clock_status.ntp_synchronized = lambda *a: True
        server._pifinder_status_snapshot = lambda **kwargs: None
        server.time.sleep = lambda seconds: None
        self.use(Mount())

    def use(self, mount):
        self.mount = mount
        indi_client.get_properties, indi_client.set_number, indi_client.set_text = mount.get_properties, mount.set_number, mount.set_text
        indi_client.active_mount_name = lambda **kwargs: M

    def tearDown(self):
        for (module, name), value in self.saved.items():
            setattr(module, name, value)

    def test_check(self):
        result = server._clock_check(True)
        self.assertTrue(result["can_set_mount"])
        self.assertEqual(len(result["current"]), 1)
        self.assertIn("location", result["current"][0])
        self.assertIn("timezone", result)

    def test_fix_sends_and_verifies(self):
        result = server._clock_fix_mount()
        self.assertTrue(result["success"], result["steps"])
        self.assertEqual(self.mount.sent, ["GEOGRAPHIC_COORD", "TIME_UTC"])
        self.assertAlmostEqual(float(self.mount.props["GEOGRAPHIC_COORD"]["elements"]["LAT"]), HOME[0])
        self.assertEqual(server._clock_check(True)["current"], [])

    def test_what_the_change_did_to_the_position_is_said(self):
        self.use(Mount(after={"RA": "5.0127", "DEC": "40.0"}))      # 9' further, as the simulator with sync points
        result = server._clock_fix_mount()
        self.assertTrue(result["success"], result["steps"])
        self.assertIn("9' from before - sync or align", result["steps"][-1]["text"])
        self.use(Mount(after={"RA": "21", "DEC": "nan"}))
        result = server._clock_fix_mount()
        self.assertFalse(result["success"])
        self.assertIn("no longer reports a position", result["steps"][-1]["text"])

    def test_a_mount_that_does_not_take_it_is_reported(self):
        self.use(Mount(ignore=True))
        result = server._clock_fix_mount()
        self.assertFalse(result["success"])
        self.assertEqual([s["ok"] for s in result["steps"]][-3:-1], [False, False])

    def test_nothing_is_sent_when_it_must_not(self):
        for mount, kstars in ((Mount(slewing=True), self.kstars), (Mount(align=("1", "3")), self.kstars),
                              (Mount(), None), (Mount(), dict(self.kstars, realtime=False))):
            self.use(mount)
            clock_status.read_kstars = lambda *a, k=kstars: k
            result = server._clock_fix_mount()
            self.assertFalse(result["success"])
            self.assertEqual(mount.sent, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
