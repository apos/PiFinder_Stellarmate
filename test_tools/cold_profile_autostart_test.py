#!/usr/bin/env python3
"""The Control Center starts a stopped Web Manager profile only after it has been stopped for a while.

    python3 test_tools/cold_profile_autostart_test.py

A profile restart from Ekos or the SMOS app is "stop, then start": starting in that gap put every driver into indiserver twice.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import server  # noqa: E402


class ColdProfileTest(unittest.TestCase):
    def setUp(self):
        self.running, self.started, self.clock = False, [], [1000.0]
        self.saved = (server.webmanager_client.server_status, server._cold_profile_retrier, server.time.monotonic,
                      server._note_active_profile, server._last_known_active_profile)
        server.webmanager_client.server_status = lambda: {"running": self.running, "active_profile": "P" if self.running else ""}
        test = self

        class Now:
            def trigger(self, fn):
                test.started.append(test.clock[0])
        server._cold_profile_retrier = Now()
        server.time.monotonic = lambda: self.clock[0]
        server._note_active_profile = lambda name: None
        server._last_known_active_profile = "P"
        server._maintenance_mode_since = None
        server._profile_switch_in_progress = False
        server._cold_profile_idle_since = None
        server._cold_profile_start_gave_up = False
        server._cold_profile_start_cooldown_until = 0.0

    def tearDown(self):
        (server.webmanager_client.server_status, server._cold_profile_retrier, server.time.monotonic, server._note_active_profile,
         server._last_known_active_profile) = self.saved

    def tick(self, seconds):
        for _ in range(int(seconds // 5)):
            self.clock[0] += 5
            server._autostart_cold_profile()

    def test_a_restart_gap_does_not_start_the_profile(self):
        self.tick(20)           # stopped for 20 s: a restart from Ekos is on its way
        self.running = True
        self.tick(10)
        self.assertEqual(self.started, [])

    def test_each_stop_is_timed_on_its_own(self):
        self.tick(20)
        self.running = True
        self.tick(5)
        self.running = False
        self.tick(20)
        self.assertEqual(self.started, [])

    def test_a_profile_that_stays_stopped_is_started(self):
        self.tick(45)
        self.assertTrue(self.started)
        self.assertGreaterEqual(self.started[0] - 1005.0, server._COLD_PROFILE_MIN_IDLE_SEC)


if __name__ == "__main__":
    unittest.main()
