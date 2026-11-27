#!/usr/bin/env python3
"""The Mount Bridge is held during an Ekos alignment, and PiFinder is aligned only when Ekos solved AND synced the mount.

    python3 test_tools/alignment_hold_test.py

Ekos, the Mount Bridge and PiFinder are replaced by stand-ins: nothing is sent anywhere.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import server  # noqa: E402

IDLE, COMPLETE, FAILED, ABORTED, PROGRESS, SUCCESSFUL, SYNCING, SLEWING = range(8)


class AlignmentHoldTest(unittest.TestCase):
    def setUp(self):
        self.guide, self.align, self.syncs, self.mode = 0, IDLE, 0, "MODE_GOTO_FORWARD"
        self.clock = [1000.0]
        self.calls = []     # ("hold", on, reason) and ("align",) in the order they happened
        names = ("_ekos_guide_status", "_ekos_align_status", "_pifinder_align_from_mount", "_mb_log")
        self.saved = {n: getattr(server, n) for n in names}
        indi = ("set_mount_bridge_external_hold", "mount_bridge_hold_syncs", "mount_bridge_drift")
        self.saved_indi = {n: getattr(server.indi_client, n) for n in indi}
        self.saved_time = server.time.monotonic
        server._ekos_guide_status = lambda: self.guide
        server._ekos_align_status = lambda: self.align
        server._pifinder_align_from_mount = lambda port: self.calls.append(("align",)) or {"success": True}
        server._mb_log = lambda line: None
        server.indi_client.set_mount_bridge_external_hold = lambda on, reason="": self.calls.append(("hold", on, reason))
        server.indi_client.mount_bridge_hold_syncs = lambda: self.syncs
        server.indi_client.mount_bridge_drift = lambda: {"coupling_mode": self.mode, "align_state": "Idle", "external_hold": False}
        server.time.monotonic = lambda: self.clock[0]
        server._guiding_hold_active = False
        server._guiding_hold_idle_since = None
        server._guiding_hold_supported = True
        server._guiding_hold_adopted_initial_state = True
        server._guiding_hold_seen = False
        server._align_hold_seen = False

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(server, name, value)
        for name, value in self.saved_indi.items():
            setattr(server.indi_client, name, value)
        server.time.monotonic = self.saved_time

    def run_for(self, seconds):
        for _ in range(int(seconds // 3)):
            self.clock[0] += 3
            server._guiding_hold_watchdog_tick()

    def held(self):
        return server._guiding_hold_active

    def test_solve_and_sync_aligns_pifinder_while_still_held(self):
        self.align = PROGRESS
        self.run_for(6)
        self.assertTrue(self.held())
        self.assertTrue(self.calls[0][2].startswith("alignment"))
        self.align, self.syncs = COMPLETE, 1
        self.run_for(24)
        self.assertEqual(self.calls[1:], [("align",), ("hold", False, "alignment ended: solved")])

    def test_action_nothing_aligns_nothing(self):
        self.align = PROGRESS
        self.run_for(6)
        self.align = SUCCESSFUL      # solved, no mount command
        self.run_for(60)
        self.assertTrue(self.held(), "successful is not the end yet")
        self.run_for(90)
        self.assertEqual(self.calls[1:], [("hold", False, "alignment ended: solved")])

    def test_failed_solve_aligns_nothing(self):
        self.align = PROGRESS
        self.run_for(6)
        self.align, self.syncs = FAILED, 1
        self.run_for(24)
        self.assertEqual(self.calls[1:], [("hold", False, "alignment ended: not solved")])

    def test_polar_alignment_gap_keeps_the_hold(self):
        self.align = PROGRESS
        self.run_for(6)
        self.align = SUCCESSFUL      # mount is turned to the next position
        self.run_for(45)
        self.align = SLEWING
        self.run_for(30)
        self.assertEqual(len(self.calls), 1)
        self.align = ABORTED         # the user ends the refresh stage
        self.run_for(24)
        self.assertEqual(self.calls[1:], [("hold", False, "alignment ended: not solved")])

    def test_guiding_alone_is_unchanged(self):
        self.guide = 12
        self.run_for(6)
        self.assertTrue(self.calls[0][2].startswith("guiding"))
        self.guide = 0
        self.run_for(24)
        self.assertEqual(self.calls[1:], [("hold", False, "")])

    def test_coupling_off_aligns_nothing(self):
        self.mode = "MODE_OFF"
        self.align = PROGRESS
        self.run_for(6)
        self.align, self.syncs = COMPLETE, 1
        self.run_for(24)
        self.assertNotIn(("align",), self.calls)

    def test_guiding_still_active_keeps_the_hold_after_an_alignment(self):
        self.guide, self.align = 12, PROGRESS
        self.run_for(6)
        self.align = COMPLETE
        self.run_for(60)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
