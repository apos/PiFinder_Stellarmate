#!/usr/bin/env python3
"""The "Mount not responding" check of the Control Center (server._MountSilenceTracker): a tracking mount that stands still is not silent.

    python3 test_tools/mount_silence_test.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402
import server  # noqa: E402

COORDS = ("0.28111", "6.9797")


def tracker():
    return server._MountSilenceTracker()


class Silence(unittest.TestCase):
    def test_a_tracking_mount_that_stands_still_is_not_silent(self):
        t = tracker()
        t.update("LX200 OnStep", True, COORDS, now=0.0, coord_state="Ok")
        out = t.update("LX200 OnStep", True, COORDS, now=600.0, coord_state="Ok")
        self.assertFalse(out["silent"], "ten minutes of the same position on a healthy, tracking mount")

    def test_a_driver_that_cannot_read_the_mount_is_silent(self):
        t = tracker()
        t.update("LX200 OnStep", True, COORDS, now=0.0, coord_state="Alert")
        out = t.update("LX200 OnStep", True, COORDS, now=61.0, coord_state="Alert")
        self.assertTrue(out["silent"])
        self.assertEqual(out["silent_for_s"], 61)

    def test_not_silent_before_the_debounce_even_with_alert(self):
        t = tracker()
        t.update("LX200 OnStep", True, COORDS, now=0.0, coord_state="Alert")
        self.assertFalse(t.update("LX200 OnStep", True, COORDS, now=30.0, coord_state="Alert")["silent"])

    def test_busy_and_idle_are_not_silence(self):
        for state in ("Busy", "Idle", "Ok"):
            t = tracker()
            t.update("LX200 OnStep", True, COORDS, now=0.0, coord_state=state)
            self.assertFalse(t.update("LX200 OnStep", True, COORDS, now=300.0, coord_state=state)["silent"], state)

    def test_a_driver_without_a_state_keeps_the_old_rule(self):
        t = tracker()
        t.update("Some Mount", True, COORDS, now=0.0)
        self.assertTrue(t.update("Some Mount", True, COORDS, now=120.0)["silent"])

    def test_moving_coordinates_restart_the_count(self):
        t = tracker()
        t.update("LX200 OnStep", True, COORDS, now=0.0, coord_state="Alert")
        t.update("LX200 OnStep", True, ("0.28200", "6.9797"), now=50.0, coord_state="Alert")
        self.assertFalse(t.update("LX200 OnStep", True, ("0.28200", "6.9797"), now=100.0, coord_state="Alert")["silent"])

    def test_simulators_are_exempt(self):
        t = tracker()
        t.update("Telescope Simulator", True, COORDS, now=0.0, coord_state="Alert")
        self.assertFalse(t.update("Telescope Simulator", True, COORDS, now=900.0, coord_state="Alert")["silent"])

    def test_a_mount_that_is_not_connected_is_never_silent(self):
        t = tracker()
        self.assertFalse(t.update("LX200 OnStep", False, COORDS, now=900.0, coord_state="Alert")["silent"])


class ReadMountState(unittest.TestCase):
    def setUp(self):
        self._saved = indi_client.get_properties

    def tearDown(self):
        indi_client.get_properties = self._saved

    def test_the_coordinate_state_is_returned(self):
        indi_client.get_properties = lambda **kw: {"LX200 OnStep": {"EQUATORIAL_EOD_COORD": {"state": "Alert", "elements": {"RA": "1", "DEC": "2"}}}}
        s = indi_client.read_mount_state("LX200 OnStep")
        self.assertEqual(s["coord_state"], "Alert")
        self.assertEqual(s["coords"], ("1", "2"))

    def test_no_coordinates_means_no_state(self):
        indi_client.get_properties = lambda **kw: {"LX200 OnStep": {}}
        s = indi_client.read_mount_state("LX200 OnStep")
        self.assertIsNone(s["coord_state"])
        self.assertIsNone(s["coords"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
