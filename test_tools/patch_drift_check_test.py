"""Tests for patch_drift_check.py on a small fake PiFinder repo and a fake PFSM directory:  python3 test_tools/patch_drift_check_test.py"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import patch_drift_check as pdc  # noqa: E402

BASE = "".join(f"line {i}\n" for i in range(1, 21))


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def make_diff(path_label, old_text, new_text, tmp):
    a, b = Path(tmp) / "a", Path(tmp) / "b"
    a.write_text(old_text)
    b.write_text(new_text)
    out = subprocess.run(["diff", "-u", "--label", path_label + ".orig", "--label", path_label, str(a), str(b)],
                         capture_output=True, text=True).stdout
    return out


class DriftCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "PiFinder"
        self.pfsm = Path(self.tmp) / "pfsm"
        (self.repo / "python").mkdir(parents=True)
        (self.pfsm / "bin").mkdir(parents=True)
        (self.pfsm / "diffs").mkdir()
        (self.pfsm / "version.txt").write_text("1.0.0\n")
        run(["git", "init", "-q"], self.repo)
        run(["git", "config", "user.email", "t@t"], self.repo)
        run(["git", "config", "user.name", "t"], self.repo)
        self.commit("python/a.py", BASE, "v1.0.0")
        # v1.1.0: lines inserted above the patch's anchor -> only an offset
        self.commit("python/a.py", "new top 1\nnew top 2\n" + BASE, "v1.1.0")
        # v2.0.0: the lines the patch is anchored to are rewritten -> FAIL
        self.commit("python/a.py", BASE.replace("line 10\n", "totally different\n").replace("line 11\n", "also different\n")
                    .replace("line 9\n", "changed 9\n").replace("line 12\n", "changed 12\n"), "v2.0.0")
        # v2.1.0: the change is already in the file (upstreamed)
        self.commit("python/a.py", BASE.replace("line 10\n", "line 10 patched\n"), "v2.1.0")
        (self.pfsm / "bin" / "functions.sh").write_text(
            'pifinder_dir="/x/PiFinder"\n'
            'a_py="${pifinder_dir}/python/a.py"\n'
            'gone_py="${pifinder_dir}/python/gone.py"\n'
            'venv_py="/home/u/venv/lib/skyfield/x.py"\n')
        (self.pfsm / "bin" / "patch_PiFinder_installation_files.sh").write_text(
            'apply_patch_or_warn "$a_py" "${pifinder_stellarmate_dir}/diffs/a_py.diff"\n'
            'apply_patch_or_warn "$gone_py" "${pifinder_stellarmate_dir}/diffs/gone_py.diff"\n'
            'apply_patch_or_warn "$venv_py" "${pifinder_stellarmate_dir}/diffs/venv_py.diff"\n'
            'apply_patch_or_warn "${pifinder_dir}/python/new_test.py" \\\n    "${pifinder_stellarmate_dir}/diffs/new_test_py.diff"\n'
            'apply_patch_or_warn "$index_tpl" "${pifinder_stellarmate_dir}/diffs/index_tpl.diff"\n')
        (self.pfsm / "diffs" / "a_py.diff").write_text(make_diff("python/a.py", BASE, BASE.replace("line 10\n", "line 10 patched\n"), self.tmp))
        (self.pfsm / "diffs" / "gone_py.diff").write_text(make_diff("python/gone.py", BASE, BASE + "x\n", self.tmp))
        (self.pfsm / "diffs" / "venv_py.diff").write_text(make_diff("x.py", BASE, BASE + "y\n", self.tmp))
        (self.pfsm / "diffs" / "new_test_py.diff").write_text(make_diff("python/new_test.py", "", "def t():\n    pass\n", self.tmp))
        (self.pfsm / "diffs" / "index_tpl.diff").write_text(make_diff("python/views/index.tpl", BASE, BASE + "z\n", self.tmp))

    def commit(self, rel, text, tag):
        (self.repo / rel).write_text(text)
        run(["git", "add", "-A"], self.repo)
        run(["git", "commit", "-q", "-m", tag], self.repo)
        run(["git", "tag", tag], self.repo)

    def results(self, tag):
        targets = pdc.read_targets(self.pfsm)
        return {name: st for name, st, _ in pdc.check_tag(self.repo, self.pfsm, tag, targets)}

    def test_targets_are_read_from_the_patch_script(self):
        t = {n: rel for n, rel, _ in pdc.read_targets(self.pfsm)}
        self.assertEqual(t["a_py.diff"], "python/a.py")
        self.assertIsNone(t["venv_py.diff"])               # outside the PiFinder checkout
        self.assertEqual(t["new_test_py.diff"], "python/new_test.py")   # target and diff on two lines
        self.assertIsNone(t["index_tpl.diff"])             # variable not defined in functions.sh: unresolved, not guessed

    def test_clean_offset_fail_upstreamed(self):
        self.assertEqual(self.results("v1.0.0")["a_py.diff"], pdc.CLEAN)
        self.assertEqual(self.results("v1.1.0")["a_py.diff"], pdc.OFFSET)
        self.assertEqual(self.results("v2.0.0")["a_py.diff"], pdc.FAIL)
        self.assertEqual(self.results("v2.1.0")["a_py.diff"], pdc.UPSTREAMED)

    def test_missing_new_file_and_outside(self):
        r = self.results("v1.0.0")
        self.assertEqual(r["gone_py.diff"], pdc.MISSING)
        self.assertEqual(r["new_test_py.diff"], pdc.NEWFILE)
        self.assertEqual(r["venv_py.diff"], "-")

    def test_exit_status_follows_the_pinned_tag(self):
        def main(*a):
            with redirect_stdout(io.StringIO()):
                return pdc.main(["--repo", str(self.repo), "--pfsm-dir", str(self.pfsm), *a])
        self.assertEqual(main("v2.0.0"), 0)                # a failing tag that is not the pinned one: information only
        self.assertEqual(main("v2.0.0", "--strict"), 1)
        self.assertEqual(main("v1.0.0"), 1)                # the pinned tag has a MISSING file (gone.py)
        self.assertEqual(main("v9.9.9"), 2)                # unknown tag


if __name__ == "__main__":
    unittest.main(verbosity=1)
