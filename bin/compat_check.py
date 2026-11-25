#!/usr/bin/env python3
"""Compatibility check: does what PFSM built still fit the system it runs on?

A SMOS update (or a plain package update) can move things PFSM depends on without PFSM noticing: the Python the venv was
built on, the INDI library the PFSM drivers were built against, libcamera, KStars' internal D-Bus actions. This looks at each of
them and says what is wrong and what to do, before it shows up as a camera that does not start or a driver that does not load.

    python3 bin/compat_check.py [--json] [--strict]

Exit status: 1 when a check FAILS (a thing is broken now), 0 otherwise; --strict also exits 1 on a warning.
Read-only: it changes nothing. Standard library only, so it also runs where the venv is the thing that is broken.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"
SEVERITY = {OK: 0, UNKNOWN: 1, WARN: 2, FAIL: 3}

# libcamera major.minor the camera setup was tested with (restore_after_smos_update.sh pins python-libcamera 0.7.0 as well).
EXPECTED_LIBCAMERA = "0.7"
PFSM_DRIVERS = ["indi_pifinder_lx200", "indi_pifinder_mount_bridge", "indi_pifinder_simulator", "indi_lx200_OnStep"]
KSTARS_CLOCK_ACTION = "/kstars/MainWindow_1/actions/clock_realtime"
REINSTALL = "Run Install or Update in the Control Center."


def default_runner(cmd, timeout=10, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout + p.stderr)


class Context:
    """Where things are, and how to run a command: both replaceable in tests."""

    def __init__(self, home=None, pfsm_dir=None, runner=default_runner, bin_dir="/usr/bin", system_python="/usr/bin/python3"):
        self.home = Path(home or os.path.expanduser("~"))
        self.pfsm_dir = Path(pfsm_dir or Path(__file__).resolve().parent.parent)
        self.pifinder_dir = self.home / "PiFinder"
        self.venv = self.pifinder_dir / "python" / ".venv"
        self.stamp = self.home / ".pfsm" / "driver_build.json"
        self.run = runner
        self.bin_dir = Path(bin_dir)
        self.system_python = system_python


def result(check_id, title, status, detail, action=""):
    return {"id": check_id, "title": title, "status": status, "detail": detail, "action": action}


def _mm(version: str):
    m = re.match(r"(\d+)\.(\d+)", version or "")
    return f"{m.group(1)}.{m.group(2)}" if m else None


def check_venv(ctx: Context):
    title = "PiFinder's Python environment"
    cfg = ctx.venv / "pyvenv.cfg"
    if not cfg.exists():
        return result("venv", title, FAIL, f"{ctx.venv} does not exist.", REINSTALL)
    code = "import sys;print('%d.%d.%d' % sys.version_info[:3])"
    rc, out = ctx.run([str(ctx.venv / "bin" / "python"), "-c", code])
    if rc != 0:
        return result("venv", title, FAIL,
                      "The venv's Python does not start (the interpreter it was built on is probably gone after a system update).",
                      "Move ~/PiFinder/python/.venv away and run Install or Update; it creates the venv again.")
    venv_version = out.strip()
    rc, out = ctx.run([ctx.system_python, "-c", code])
    system_version = out.strip() if rc == 0 else None
    if system_version and _mm(system_version) != _mm(venv_version):
        return result("venv", title, WARN,
                      f"The venv runs on Python {venv_version}, the system now has {system_version}. It works while the old interpreter stays, "
                      "but the next system update can remove it.",
                      "Plan a rebuild of the venv: move ~/PiFinder/python/.venv away and run Install or Update.")
    return result("venv", title, OK, f"Python {venv_version}" + (f" (system {system_version})" if system_version else ""))


def _installed_version(ctx: Context, package: str):
    rc, out = ctx.run(["pacman", "-Q", package])
    if rc != 0:
        return None
    parts = out.split()
    return parts[1] if len(parts) >= 2 else None


def check_drivers(ctx: Context):
    title = "PFSM INDI drivers"
    present = [d for d in PFSM_DRIVERS if (ctx.bin_dir / d).exists()]
    if not present:
        return result("drivers", title, UNKNOWN, "No PFSM driver is installed on this device.")
    broken = {}
    for d in present:
        rc, out = ctx.run(["ldd", str(ctx.bin_dir / d)])
        missing = [line.split("=>")[0].strip() for line in out.splitlines() if "not found" in line]
        if rc != 0 and not missing:
            missing = ["ldd failed"]
        if missing:
            broken[d] = missing
    if broken:
        text = "; ".join(f"{d}: {', '.join(m)}" for d, m in broken.items())
        return result("drivers", title, FAIL, f"A library is missing: {text}.",
                      "The drivers must be built again against the installed libindi. " + REINSTALL)
    installed = _installed_version(ctx, "libindi")
    built = None
    if ctx.stamp.exists():
        try:
            built = json.loads(ctx.stamp.read_text()).get("libindi")
        except (OSError, ValueError):
            built = None
    if installed and built and built.split("-")[0] != installed.split("-")[0]:
        return result("drivers", title, WARN,
                      f"The drivers were built against libindi {built}, the system now has {installed}. They load, but a changed library can break them silently.",
                      "Build them again. " + REINSTALL)
    note = "" if built else " (the build's libindi version is not recorded yet; the next setup records it)"
    return result("drivers", title, OK, f"{len(present)} drivers link to the installed libindi {installed or '?'}{note}.")


def check_libcamera(ctx: Context):
    title = "Camera libraries"
    lib = _installed_version(ctx, "libcamera")
    py = _installed_version(ctx, "python-libcamera")
    if not lib and not py:
        return result("libcamera", title, UNKNOWN, "libcamera is not installed (no camera on this device).")
    wrong = [f"{n} {v}" for n, v in (("libcamera", lib), ("python-libcamera", py)) if v and _mm(v) != EXPECTED_LIBCAMERA]
    if wrong:
        return result("libcamera", title, WARN,
                      f"{', '.join(wrong)}; the camera was tested with {EXPECTED_LIBCAMERA}.x. A changed major version can stop PiFinder's camera.",
                      "Check the camera with Test Hardware before an observing night; see the libcamera notes in bin/restore_after_smos_update.sh.")
    return result("libcamera", title, OK, f"libcamera {lib}, python-libcamera {py}.")


def check_kstars(ctx: Context):
    title = "KStars clock action"
    env = dict(os.environ)
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")
    rc, _ = ctx.run(["qdbus6", "org.kde.kstars", KSTARS_CLOCK_ACTION], env=env)
    if rc == 0:
        return result("kstars", title, OK, "KStars answers on the D-Bus action the mount-clock correction uses.")
    running, _ = ctx.run(["pgrep", "-x", "kstars"])
    if running != 0:
        return result("kstars", title, UNKNOWN, "KStars is not running, so its D-Bus action cannot be checked.")
    return result("kstars", title, WARN,
                  f"KStars runs, but {KSTARS_CLOCK_ACTION} does not answer (a KStars update may have renamed it). "
                  "The automatic mount-clock correction and the button Set mount time now will not work.",
                  "The clock strip in the Control Center still warns when the mount's clock is wrong; the code in server.py needs the new action name.")


def check_pifinder(ctx: Context):
    title = "Installed PiFinder"
    version_file = ctx.pfsm_dir / "version.txt"
    if not (ctx.pifinder_dir / ".git").exists():
        return result("pifinder", title, FAIL, f"{ctx.pifinder_dir} is not a PiFinder checkout.", REINSTALL)
    pinned = "v" + version_file.read_text().strip() if version_file.exists() else None
    rc, out = ctx.run(["git", "-C", str(ctx.pifinder_dir), "describe", "--tags", "--exact-match"])
    installed = out.strip() if rc == 0 else None
    rejects = sorted(p.name for p in (ctx.pifinder_dir / "python").rglob("*.rej") if ".venv" not in p.parts)
    if rejects:
        return result("pifinder", title, FAIL, f"A patch did not fully apply: {', '.join(rejects[:5])}.",
                      "Regenerate the patch (test_tools/patch_drift_check.py shows which) and run Install or Update.")
    if pinned and installed != pinned:
        return result("pifinder", title, WARN, f"Installed {installed or 'an untagged state'}, but this PFSM pins {pinned}.", REINSTALL)
    return result("pifinder", title, OK, f"PiFinder {installed or '?'}, patches applied without rejects.")


CHECKS = [check_venv, check_drivers, check_libcamera, check_kstars, check_pifinder]


def run_checks(ctx: Context):
    results = []
    for fn in CHECKS:
        try:
            results.append(fn(ctx))
        except Exception as exc:  # a broken check must never hide the others
            results.append(result(fn.__name__.replace("check_", ""), fn.__name__, UNKNOWN, f"The check itself failed: {exc}"))
    worst = max((r["status"] for r in results), key=lambda s: SEVERITY[s])
    return {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": worst, "checks": results}


MARK = {OK: "ok  ", WARN: "WARN", FAIL: "FAIL", UNKNOWN: "n/a "}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="also exit 1 on a warning")
    args = ap.parse_args(argv)
    report = run_checks(Context())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Compatibility check")
        for r in report["checks"]:
            print(f"  [{MARK[r['status']]}] {r['title']}: {r['detail']}")
            if r["action"] and r["status"] in (WARN, FAIL):
                print(f"          -> {r['action']}")
    if report["status"] == FAIL or (args.strict and report["status"] == WARN):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
