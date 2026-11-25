"""Tests for bin/compat_check.py with fake commands and a temporary home:  python3 test_tools/compat_check_test.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import compat_check as cc  # noqa: E402


class Fake:
    """A runner that answers by the start of the command; everything else fails."""

    def __init__(self, answers):
        self.answers = answers

    def __call__(self, cmd, timeout=10, env=None):
        for prefix, answer in self.answers.items():
            if " ".join(cmd).startswith(prefix):
                return answer
        return 1, ""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.pfsm = self.tmp / "pfsm"
        self.bin = self.tmp / "usrbin"
        for d in (self.home / "PiFinder" / "python" / ".venv", self.pfsm, self.bin):
            d.mkdir(parents=True)
        (self.pfsm / "version.txt").write_text("2.6.4\n")

    def ctx(self, answers):
        return cc.Context(home=self.home, pfsm_dir=self.pfsm, runner=Fake(answers), bin_dir=self.bin, system_python="/sys/python3")


class Venv(Base):
    def test_missing(self):
        self.assertEqual(cc.check_venv(self.ctx({}))["status"], cc.FAIL)

    def test_interpreter_gone(self):
        (self.home / "PiFinder/python/.venv/pyvenv.cfg").write_text("home = /usr/bin\n")
        r = cc.check_venv(self.ctx({}))
        self.assertEqual(r["status"], cc.FAIL)
        self.assertIn("run Install or Update", r["action"])

    def test_system_python_moved_on(self):
        (self.home / "PiFinder/python/.venv/pyvenv.cfg").write_text("home = /usr/bin\n")
        v = str(self.home / "PiFinder/python/.venv/bin/python")
        r = cc.check_venv(self.ctx({v: (0, "3.14.7\n"), "/sys/python3": (0, "3.15.0\n")}))
        self.assertEqual(r["status"], cc.WARN)

    def test_same_minor_is_fine(self):
        (self.home / "PiFinder/python/.venv/pyvenv.cfg").write_text("home = /usr/bin\n")
        v = str(self.home / "PiFinder/python/.venv/bin/python")
        self.assertEqual(cc.check_venv(self.ctx({v: (0, "3.14.6\n"), "/sys/python3": (0, "3.14.7\n")}))["status"], cc.OK)


class Drivers(Base):
    def install(self, *names):
        for n in names:
            (self.bin / n).write_text("")

    def test_none_installed(self):
        self.assertEqual(cc.check_drivers(self.ctx({}))["status"], cc.UNKNOWN)

    def test_missing_library(self):
        self.install("indi_pifinder_lx200")
        r = cc.check_drivers(self.ctx({"ldd": (0, "\tlibindidriver.so.2 => not found\n")}))
        self.assertEqual(r["status"], cc.FAIL)
        self.assertIn("libindidriver.so.2", r["detail"])

    def test_libindi_moved_since_the_build(self):
        self.install("indi_pifinder_lx200")
        (self.home / ".pfsm").mkdir()
        (self.home / ".pfsm/driver_build.json").write_text(json.dumps({"libindi": "2.2.5"}))
        r = cc.check_drivers(self.ctx({"ldd": (0, "libindidriver.so.2 => /usr/lib/x\n"), "pacman -Q libindi": (0, "libindi 2.3.0-1\n")}))
        self.assertEqual(r["status"], cc.WARN)

    def test_same_libindi_ok_even_with_new_pkgrel(self):
        self.install("indi_pifinder_lx200")
        (self.home / ".pfsm").mkdir()
        (self.home / ".pfsm/driver_build.json").write_text(json.dumps({"libindi": "2.2.5"}))
        r = cc.check_drivers(self.ctx({"ldd": (0, "libindidriver.so.2 => /usr/lib/x\n"), "pacman -Q libindi": (0, "libindi 2.2.5-2\n")}))
        self.assertEqual(r["status"], cc.OK)

    def test_no_stamp_yet_is_ok_but_says_so(self):
        self.install("indi_pifinder_lx200")
        r = cc.check_drivers(self.ctx({"ldd": (0, "libindidriver.so.2 => /usr/lib/x\n"), "pacman -Q libindi": (0, "libindi 2.2.5-1\n")}))
        self.assertEqual(r["status"], cc.OK)
        self.assertIn("not recorded yet", r["detail"])


class Others(Base):
    def test_libcamera(self):
        self.assertEqual(cc.check_libcamera(self.ctx({}))["status"], cc.UNKNOWN)
        self.assertEqual(cc.check_libcamera(self.ctx({"pacman -Q libcamera": (0, "libcamera 0.8.0-1\n")}))["status"], cc.WARN)
        ok = {"pacman -Q libcamera": (0, "libcamera 0.7.2-64\n"), "pacman -Q python-libcamera": (0, "python-libcamera 0.7.0-3\n")}
        self.assertEqual(cc.check_libcamera(self.ctx(ok))["status"], cc.OK)

    def test_kstars(self):
        self.assertEqual(cc.check_kstars(self.ctx({"qdbus6": (0, "property\n")}))["status"], cc.OK)
        self.assertEqual(cc.check_kstars(self.ctx({}))["status"], cc.UNKNOWN)                      # not running
        self.assertEqual(cc.check_kstars(self.ctx({"pgrep": (0, "123\n")}))["status"], cc.WARN)    # running, action gone

    def test_pifinder(self):
        pf = self.home / "PiFinder"
        self.assertEqual(cc.check_pifinder(self.ctx({}))["status"], cc.FAIL)                       # no .git
        (pf / ".git").mkdir()
        tag = {"git -C": (0, "v2.6.4\n")}
        self.assertEqual(cc.check_pifinder(self.ctx(tag))["status"], cc.OK)
        self.assertEqual(cc.check_pifinder(self.ctx({"git -C": (0, "v2.6.3\n")}))["status"], cc.WARN)
        (pf / "python").mkdir(exist_ok=True)
        (pf / "python" / "main.py.rej").write_text("")
        self.assertEqual(cc.check_pifinder(self.ctx(tag))["status"], cc.FAIL)


class Report(Base):
    def test_a_crashing_check_does_not_hide_the_others(self):
        def boom(ctx):
            raise RuntimeError("x")
        saved = cc.CHECKS
        cc.CHECKS = [boom, cc.check_libcamera]
        try:
            rep = cc.run_checks(self.ctx({}))
        finally:
            cc.CHECKS = saved
        self.assertEqual([c["status"] for c in rep["checks"]], [cc.UNKNOWN, cc.UNKNOWN])
        self.assertIn("The check itself failed", rep["checks"][0]["detail"])

    def test_worst_status_wins(self):
        saved = cc.CHECKS
        cc.CHECKS = [cc.check_venv, cc.check_libcamera]   # venv missing = FAIL, libcamera absent = UNKNOWN
        try:
            self.assertEqual(cc.run_checks(self.ctx({}))["status"], cc.FAIL)
        finally:
            cc.CHECKS = saved


if __name__ == "__main__":
    unittest.main(verbosity=1)
