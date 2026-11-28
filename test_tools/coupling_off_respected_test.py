#!/usr/bin/env python3
"""An Off chosen anywhere stays: the Control Center's self-healing never switches the coupling on again.

    python3 test_tools/coupling_off_respected_test.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import server  # noqa: E402

GOTO, OFF = "MODE_GOTO_FORWARD", "MODE_OFF"


class OffIsOff(unittest.TestCase):
    def setUp(self):
        self.saved, self.logged = [], []
        self.originals = (server._save_mount_bridge_desired_state, server._mb_log, server._mb_desired_coupling_mode)
        server._save_mount_bridge_desired_state = lambda: self.saved.append(server._mb_desired_coupling_mode)
        server._mb_log = self.logged.append
        server._mb_adopt_seen = (None, 0)

    def tearDown(self):
        server._save_mount_bridge_desired_state, server._mb_log, server._mb_desired_coupling_mode = self.originals

    def tick(self, mode):
        return server._adopt_external_off({"coupling_mode": mode})

    def test_an_off_from_elsewhere_becomes_the_choice(self):
        server._mb_desired_coupling_mode = GOTO
        self.assertFalse(self.tick(OFF), "one reading may be older than a choice just made on the page")
        self.assertTrue(self.tick(OFF))
        self.assertEqual(server._mb_desired_coupling_mode, OFF)
        self.assertEqual(self.saved, [OFF])
        self.assertEqual(len(self.logged), 1)

    def test_a_single_stale_reading_changes_nothing(self):
        server._mb_desired_coupling_mode = GOTO
        for mode in (OFF, GOTO, OFF, GOTO):
            self.assertFalse(self.tick(mode))
        self.assertEqual(server._mb_desired_coupling_mode, GOTO)

    def test_an_off_is_also_remembered_when_nothing_was_chosen_before(self):
        server._mb_desired_coupling_mode = None
        self.tick(OFF)
        self.assertTrue(self.tick(OFF))
        self.assertEqual(server._mb_desired_coupling_mode, OFF)

    def test_no_reading_is_no_off(self):
        server._mb_desired_coupling_mode = GOTO
        for _ in range(4):
            self.assertFalse(self.tick(None))
        self.assertEqual(server._mb_desired_coupling_mode, GOTO)

    def test_a_choice_after_an_off_is_kept_too(self):
        server._mb_desired_coupling_mode = OFF
        self.assertFalse(self.tick(GOTO))
        self.assertTrue(self.tick(GOTO))
        self.assertEqual(server._mb_desired_coupling_mode, GOTO)

    def test_the_repair_never_names_off_as_a_mismatch(self):
        source = open(server.__file__).read()
        self.assertIn('status.get("coupling_mode") not in (_mb_desired_coupling_mode, "MODE_OFF")', source)
        self.assertNotIn('status.get("coupling_mode") in ("MODE_OFF", None)', source)
        self.assertIn('if _mb_desired_coupling_mode == "MODE_OFF":\n        pass', source)


if __name__ == "__main__":
    unittest.main(verbosity=1)
