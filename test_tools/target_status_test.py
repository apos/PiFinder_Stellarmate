#!/usr/bin/env python3
"""indi_client._target_status(): the Mount Bridge's TARGET_STATUS as the Control Center reads it.

    python3 test_tools/target_status_test.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402


def props(state="Ok", ra="13.7135", dec="28.32", offset="9.35", age="4", source="Mount"):
    return {
        "TARGET_STATUS": {"state": state, "elements": {"RA": ra, "DEC": dec, "OFFSET_ARCMIN": offset, "AGE_SEC": age}},
        "TARGET_STATUS_SOURCE": {"state": state, "elements": {"SOURCE": source}},
    }


class TargetStatus(unittest.TestCase):
    def test_ok(self):
        t = indi_client._target_status(props())
        self.assertEqual(t, {"ra": 13.7135, "dec": 28.32, "offset_arcmin": 9.35, "age_sec": 4.0, "source": "Mount", "fresh": True})

    def test_busy_is_a_target_without_a_fresh_offset(self):
        t = indi_client._target_status(props(state="Busy"))
        self.assertFalse(t["fresh"])
        self.assertEqual(t["source"], "Mount")

    def test_no_target(self):
        self.assertIsNone(indi_client._target_status(props(state="Idle")))
        self.assertIsNone(indi_client._target_status({}))  # an older driver without the property

    def test_zero_zero_is_no_target(self):
        self.assertIsNone(indi_client._target_status(props(ra="0", dec="0")))

    def test_unreadable_values(self):
        self.assertIsNone(indi_client._target_status(props(offset="n/a")))

    def test_empty_source_is_none(self):
        self.assertIsNone(indi_client._target_status(props(source=""))["source"])

    def test_part_of_the_sky_panel_data(self):
        dev = props()
        dev["OBSERVER_LOCATION"] = {"state": "Ok", "elements": {"LAT": "49.4", "LONG": "8.6"}}
        sky = indi_client._sky_panel_data(dev)
        self.assertEqual(sky["target"]["offset_arcmin"], 9.35)


def positioning(phase="REFINING", **o):
    el = {"ATTEMPT": "1", "ATTEMPTS_MAX": "3", "RESIDUAL_ARCMIN": "7.7", "ELAPSED_SEC": "16", "TO_GO_DEG": "0",
          "SOLVE_AGE_SEC": "0.4", "HANDS_OFF": "1"}
    el.update(o)
    return {"POSITIONING_STATUS": {"state": "Busy", "elements": el}, "POSITIONING_PHASE": {"state": "Busy", "elements": {"PHASE": phase}}}


class PositioningStatus(unittest.TestCase):
    def test_refining(self):
        p = indi_client._positioning_status(positioning())
        self.assertEqual(p, {"phase": "REFINING", "attempt": 1, "attempts_max": 3, "residual_arcmin": 7.7, "elapsed_sec": 16.0,
                             "to_go_deg": 0.0, "solve_age_sec": 0.4, "hands_off": True, "reason": ""})

    def test_hands_free_after_the_move(self):
        self.assertFalse(indi_client._positioning_status(positioning("ON_TARGET", HANDS_OFF="0"))["hands_off"])

    def test_unknown_solve_age_is_none(self):
        self.assertIsNone(indi_client._positioning_status(positioning(SOLVE_AGE_SEC="-1"))["solve_age_sec"])

    def test_older_driver_or_unreadable(self):
        self.assertIsNone(indi_client._positioning_status({}))
        self.assertIsNone(indi_client._positioning_status(positioning(ATTEMPT="x")))


if __name__ == "__main__":
    unittest.main()
