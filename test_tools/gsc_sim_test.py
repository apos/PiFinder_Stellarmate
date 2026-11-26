#!/usr/bin/env python3
"""gui_installer/gsc_sim.py: start/stop of the GSC sky simulation, against a temporary directory and a harmless child process.

    python3 test_tools/gsc_sim_test.py
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import gsc_sim as g  # noqa: E402

CHILD = """import signal, sys, time
signal.signal(signal.SIGINT, lambda *a: (print('restored', flush=True), sys.exit(0)))
time.sleep(60)
"""


class FakeIndi:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def disconnect_device(self, device):
        if self.fail:
            raise RuntimeError("no such device")
        self.calls.append(("disconnect", device))

    def connect_device(self, device):
        self.calls.append(("connect", device))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(g, k) for k in ("STATE_PATH", "LOG_PATH", "ORIGINAL_IMAGE_BACKUP", "FOLLOW_SCRIPT", "PF_PYTHON",
                                                 "PF_TEST_IMAGE", "PF_REPO", "GSC_DATA", "set_test_mode", "pifinder_status", "FOLLOWER_MARK")}
        g.STATE_PATH, g.LOG_PATH = self.tmp / "state.json", self.tmp / "log"
        g.ORIGINAL_IMAGE_BACKUP = self.tmp / "orig.png"
        (self.tmp / "images").mkdir()
        g.PF_REPO = self.tmp / "repo"   # not a git checkout: the picture on disk is the fallback
        g.PF_TEST_IMAGE = self.tmp / "images" / "pifinder_debug_02.png"
        g.PF_TEST_IMAGE.write_bytes(b"original")
        g.FOLLOW_SCRIPT = self.tmp / "child_sky_follow.py"   # the name carries the mark the liveness check looks for
        g.FOLLOW_SCRIPT.write_text(CHILD)
        g.PF_PYTHON = Path(sys.executable)
        g.GSC_DATA = str(self.tmp)
        g.FOLLOWER_MARK = "child_sky_follow.py"
        self.test_mode = {"on": False}
        g.pifinder_status = lambda: {"debug_solve": self.test_mode["on"], "solution": {"solve_source": "CAM"}}

        def set_mode(want):
            self.test_mode["on"] = want
            return want
        g.set_test_mode = set_mode
        self.have_gsc = g.shutil.which(g.GSC_BINARY) or Path("/usr/local/bin/gsc").exists()

    def tearDown(self):
        try:
            g.stop()
        except Exception:
            pass
        for k, v in self.saved.items():
            setattr(g, k, v)


class BuildCommand(Base):
    def test_typical_landing_error(self):
        cmd = g.build_command("typical", "Telescope Simulator", "/x/orig.png")
        self.assertIn("--goto-error-east", cmd)
        self.assertEqual(cmd[cmd.index("--goto-error-east") + 1], "8.0")
        self.assertEqual(cmd[cmd.index("--goto-error-north") + 1], "-5.0")
        self.assertEqual(cmd[cmd.index("--device") + 1], "Telescope Simulator")
        self.assertEqual(cmd[cmd.index("--restore") + 1], "/x/orig.png")

    def test_a_perfect_mount_has_no_landing_error(self):
        self.assertNotIn("--goto-error-east", g.build_command("off"))

    def test_unknown_landing_is_refused(self):
        with self.assertRaises(ValueError):
            g.build_command("huge")


class Availability(Base):
    def test_missing_pieces_are_named(self):
        g.FOLLOW_SCRIPT = self.tmp / "nope.py"
        self.assertIn("follower script", g.availability()[1])
        g.FOLLOW_SCRIPT = self.tmp / "child_sky_follow.py"
        g.PF_PYTHON = self.tmp / "nopython"
        self.assertIn("PiFinder is not installed", g.availability()[1])

    def test_a_missing_picture_folder_is_named(self):
        g.PF_TEST_IMAGE = self.tmp / "nodir" / "x.png"
        self.assertIn("test picture folder", g.availability()[1])


class StartStop(Base):
    def setUp(self):
        super().setUp()
        if not self.have_gsc:
            self.skipTest("gsc is not installed here")

    def test_start_then_stop_cleans_up(self):
        indi = FakeIndi()
        started = g.start("typical", "Telescope Simulator", indi=indi, popen=lambda cmd, **kw: subprocess.Popen(
            [sys.executable, str(g.FOLLOW_SCRIPT)], **kw))
        self.assertTrue(started["ok"], started)
        self.assertTrue(started["running"])
        self.assertTrue(self.test_mode["on"], "Test Mode is switched on")
        self.assertEqual(indi.calls, [("disconnect", "PiFinder Simulator")])
        self.assertEqual(g.status()["landing"], "typical")
        self.assertEqual(g.ORIGINAL_IMAGE_BACKUP.read_bytes(), b"original", "the original picture is backed up")
        stopped = g.stop(indi=indi, wait=5)
        self.assertFalse(stopped["running"])
        self.assertFalse(self.test_mode["on"], "Test Mode was off before, so it is switched off again")
        self.assertEqual(indi.calls[-1], ("connect", "PiFinder Simulator"), "the old device is connected again")
        self.assertFalse(g.STATE_PATH.exists())

    def test_test_mode_that_was_already_on_stays_on(self):
        self.test_mode["on"] = True
        g.start("off", indi=None, popen=lambda cmd, **kw: subprocess.Popen([sys.executable, str(g.FOLLOW_SCRIPT)], **kw))
        g.stop(wait=5)
        self.assertTrue(self.test_mode["on"])

    def test_a_second_start_does_not_start_a_second_follower(self):
        popen = lambda cmd, **kw: subprocess.Popen([sys.executable, str(g.FOLLOW_SCRIPT)], **kw)  # noqa: E731
        first = g.start("off", popen=popen)
        pid = g.read_state()["pid"]
        second = g.start("off", popen=popen)
        self.assertEqual(g.read_state()["pid"], pid)
        self.assertTrue(second["warnings"])
        self.assertTrue(first["running"])

    def test_a_missing_old_device_is_only_a_warning(self):
        started = g.start("off", indi=FakeIndi(fail=True), popen=lambda cmd, **kw: subprocess.Popen(
            [sys.executable, str(g.FOLLOW_SCRIPT)], **kw))
        self.assertTrue(started["ok"])
        self.assertTrue(any("left alone" in w for w in started["warnings"]))
        self.assertFalse(g.read_state()["old_simulator_disconnected"])

    def test_the_original_comes_from_git_not_from_a_leftover_frame(self):
        repo = self.tmp / "gitrepo"
        (repo / "test_images").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "test_images" / "pifinder_debug_02.png").write_bytes(b"the real original")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"], check=True)
        (repo / "test_images" / "pifinder_debug_02.png").write_bytes(b"a simulated frame left behind")
        g.PF_REPO = repo
        g.PF_TEST_IMAGE = repo / "test_images" / "pifinder_debug_02.png"
        g.ORIGINAL_IMAGE_BACKUP.write_bytes(b"stale backup")
        g._back_up_original_image()
        self.assertEqual(g.ORIGINAL_IMAGE_BACKUP.read_bytes(), b"the real original")

    def test_stop_without_a_running_simulation_is_harmless(self):
        out = g.stop()
        self.assertFalse(out["running"])

    def test_a_stale_state_file_is_not_running(self):
        g.write_state({"pid": 2 ** 22 + 12345})
        self.assertFalse(g.status()["running"])


class StatusShape(Base):
    def test_status_lists_the_landing_choices(self):
        ids = [x["id"] for x in g.status()["landings"]]
        self.assertEqual(ids, ["off", "typical", "large"])

    def test_not_running_has_no_details(self):
        s = g.status()
        self.assertFalse(s["running"])
        self.assertIsNone(s["landing"])
        self.assertIsNone(s["solve_source"])


if __name__ == "__main__":
    unittest.main()
