#!/usr/bin/env python3
"""Check 3.5 of the Mount Bridge readiness watchdog: a Bridge that is connected but never bound to its mount and PiFinder is found and
healed (server._BridgeBindingTracker, indi_client.bridge_binding_state).

    python3 test_tools/bridge_binding_test.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402
import server  # noqa: E402


def tracker():
    return server._BridgeBindingTracker()


class Tracker(unittest.TestCase):
    def test_a_bound_bridge_is_never_healed(self):
        t = tracker()
        for now in (0.0, 60.0, 600.0):
            self.assertFalse(t.may_heal("Ok", now))
        self.assertFalse(t.may_heal("Alert", 900.0), "Alert is the mount below the horizon: it did read the mount")

    def test_idle_must_last_before_it_counts(self):
        t = tracker()
        self.assertFalse(t.may_heal("Idle", 0.0))
        self.assertFalse(t.may_heal("Idle", t.UNBOUND_AFTER_S - 1))
        self.assertTrue(t.may_heal("Idle", t.UNBOUND_AFTER_S))

    def test_any_sign_of_life_restarts_the_count(self):
        t = tracker()
        t.may_heal("Idle", 0.0)
        t.may_heal("Ok", 30.0)
        self.assertFalse(t.may_heal("Idle", 40.0), "the count began again at 40 s")
        self.assertTrue(t.may_heal("Idle", 40.0 + t.UNBOUND_AFTER_S))

    def test_an_unknown_state_is_not_a_verdict(self):
        t = tracker()
        t.may_heal("Idle", 0.0)
        self.assertEqual(t.unbound_for(None, 500.0), 0.0)
        self.assertFalse(t.may_heal(None, 500.0))

    def test_a_heal_waits_before_the_next_and_is_bounded(self):
        t = tracker()
        now = 0.0
        done = 0
        while now < t.WINDOW_S:
            t.may_heal("Idle", now)
            now += t.UNBOUND_AFTER_S
            if now < t.WINDOW_S and t.may_heal("Idle", now):
                t.healed(now)
                done += 1
            now += 1.0
        self.assertEqual(done, t.MAX_PER_WINDOW, "never more than MAX_PER_WINDOW within the window")

    def test_the_window_forgets_old_heals(self):
        t = tracker()
        for i in range(t.MAX_PER_WINDOW):
            t.heals.append(i * t.MIN_GAP_S)
        t.may_heal("Idle", 0.0)
        self.assertFalse(t.may_heal("Idle", t.UNBOUND_AFTER_S + 1), "still inside the window")
        later = t.WINDOW_S + 200.0
        t.may_heal("Idle", later)
        self.assertTrue(t.may_heal("Idle", later + t.UNBOUND_AFTER_S))


class BindingState(unittest.TestCase):
    def setUp(self):
        self._saved = indi_client.get_properties

    def tearDown(self):
        indi_client.get_properties = self._saved

    def test_the_state_of_the_horizon_property_is_returned(self):
        for st in ("Idle", "Ok", "Alert"):
            indi_client.get_properties = lambda st=st, **kw: {"PiFinder Mount Bridge": {"MOUNT_HORIZON_STATUS": {"state": st, "elements": {}}}}
            self.assertEqual(indi_client.bridge_binding_state(), st)

    def test_no_property_is_none(self):
        indi_client.get_properties = lambda **kw: {"PiFinder Mount Bridge": {}}
        self.assertIsNone(indi_client.bridge_binding_state())
        indi_client.get_properties = lambda **kw: {}
        self.assertIsNone(indi_client.bridge_binding_state())


if __name__ == "__main__":
    unittest.main(verbosity=1)
