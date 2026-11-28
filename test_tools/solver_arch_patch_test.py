#!/usr/bin/env python3
"""PiFinder's solver must not start a cedar-detect-server built for another processor (#234).

    python3 test_tools/solver_arch_patch_test.py

Applies the solver.py step of bin/patch_PiFinder_installation_files.sh to the pristine file of the installed PiFinder checkout (in a
temporary directory) and runs the patched program search with a faked processor type. Skipped without a PiFinder checkout.
"""
import ast
import os
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIFINDER = Path.home() / "PiFinder"


class SolverArchPatch(unittest.TestCase):
    def setUp(self):
        got = subprocess.run(["git", "-C", str(PIFINDER), "show", "HEAD:python/PiFinder/solver.py"], capture_output=True, text=True)
        if got.returncode != 0:
            self.skipTest("no PiFinder checkout")
        self.tmp = Path(tempfile.mkdtemp(prefix="solver-patch-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        solver = self.tmp / "solver.py"
        solver.write_text(got.stdout)
        script = (REPO / "bin/patch_PiFinder_installation_files.sh").read_text()
        step = script[script.index("# Patch solver.py"):script.index('show_diff_if_changed "$solver_py"', script.index("# Patch solver.py"))]
        body = step[step.index("    if grep -q 'sys.path.append"):step.rindex("else")]
        for _ in range(2):   # a second run must change nothing more
            subprocess.run(["bash", "-eu", "-c", body], env=dict(os.environ, solver_py=str(solver)), check=True)
        self.source = solver.read_text()
        ast.parse(self.source)

    def search(self, machine, on_path=None):
        function = next(n for n in ast.walk(ast.parse(self.source)) if isinstance(n, ast.FunctionDef) and n.name == "_find_server_binary")
        function.decorator_list = []
        module = ast.Module(body=[function], type_ignores=[])
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        for name in ("cedar-detect-server-aarch64", "cedar-detect-server-arm64"):
            (bindir / name).write_text("")
            (bindir / name).chmod(0o755)
        names = {"platform": types.SimpleNamespace(machine=lambda: machine), "utils": types.SimpleNamespace(pifinder_dir=self.tmp),
                 "os": os, "shutil": types.SimpleNamespace(which=lambda _: on_path)}
        exec(compile(module, "solver", "exec"), names)
        found = names["_find_server_binary"]()
        return None if found is None else os.path.basename(str(found))

    def test_arm_still_gets_its_program(self):
        self.assertEqual(self.search("aarch64"), "cedar-detect-server-aarch64")

    def test_x86_gets_none_so_the_solver_uses_its_own_star_finder(self):
        self.assertIsNone(self.search("x86_64"))

    def test_x86_still_uses_a_matching_program_on_the_path(self):
        self.assertEqual(self.search("x86_64", on_path="/usr/bin/cedar-detect-server"), "cedar-detect-server")


if __name__ == "__main__":
    unittest.main()
