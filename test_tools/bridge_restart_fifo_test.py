#!/usr/bin/env python3
"""The Mount Bridge is restarted through the FIFO of the indiserver it runs on, not blindly through /tmp/indiFIFO.

    python3 test_tools/bridge_restart_fifo_test.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client  # noqa: E402


class FifoTest(unittest.TestCase):
    def fake_proc(self, parent_cmdline):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "100"))
        os.makedirs(os.path.join(tmp.name, "50"))
        with open(os.path.join(tmp.name, "100", "status"), "w") as f:
            f.write("Name:\tindi_pifinder_m\nPPid:\t50\n")
        with open(os.path.join(tmp.name, "50", "cmdline"), "wb") as f:
            f.write(parent_cmdline)
        return tmp.name

    def test_the_second_server_of_a_mixed_profile(self):
        proc = self.fake_proc(b"indiserver\0-p\x0020001\0-f\0/tmp/indiFIFO_system\0")
        self.assertEqual(indi_client.mount_bridge_fifo_path([100], proc), "/tmp/indiFIFO_system")

    def test_default_without_a_running_bridge_or_server(self):
        self.assertEqual(indi_client.mount_bridge_fifo_path([], "/proc"), "/tmp/indiFIFO")
        proc = self.fake_proc(b"bash\0-f\0/tmp/other\0")
        self.assertEqual(indi_client.mount_bridge_fifo_path([100], proc), "/tmp/indiFIFO")


if __name__ == "__main__":
    unittest.main()
