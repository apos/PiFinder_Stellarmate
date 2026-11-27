#!/usr/bin/env python3
"""The Control Center reconnects "PiFinder LX200" after a PiFinder restart - also when it was restarted together with PiFinder.

    python3 test_tools/lx200_reconnect_test.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import server  # noqa: E402


class ReconnectTest(unittest.TestCase):
    def setUp(self):
        self.calls, self.failing, self.start = [], False, 100
        self.saved = (server._pifinder_service_start_monotonic, server._pifinder_lx200_link_failing,
                      server._pifinder_lx200_reconnect_retrier, server._mb_log)
        calls = self.calls

        class Now:
            def trigger(self, fn):
                calls.append("reconnect")
                return True
        server._pifinder_service_start_monotonic = lambda: self.start
        server._pifinder_lx200_link_failing = lambda: self.failing
        server._pifinder_lx200_reconnect_retrier = Now()
        server._mb_log = lambda line: None
        server._maintenance_mode_since = None
        server._pifinder_lx200_healed_for_start = None
        self.status = {"active_pifinder": "PiFinder LX200", "pifinder_connected": True}

    def tearDown(self):
        (server._pifinder_service_start_monotonic, server._pifinder_lx200_link_failing,
         server._pifinder_lx200_reconnect_retrier, server._mb_log) = self.saved

    def tick(self):
        server._pifinder_lx200_auto_reconnect(self.status)

    def test_healthy_at_start_is_left_alone(self):
        self.tick()
        self.tick()
        self.assertEqual(self.calls, [])

    def test_dead_link_at_start_is_reconnected(self):
        self.failing = True
        self.tick()
        self.assertEqual(self.calls, ["reconnect"])

    def test_a_later_restart_is_reconnected(self):
        self.tick()
        self.start = 200
        self.tick()
        self.assertEqual(self.calls, ["reconnect"])


if __name__ == "__main__":
    unittest.main()
