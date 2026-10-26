#!/usr/bin/env python3
"""Read-only before/after comparison for a SMOS update.

  smos_update_state.py snapshot [--out FILE]   record the current state (JSON)
  smos_update_state.py compare A.json B.json   show what changed between two snapshots
  smos_update_state.py latest                  print the path of the newest snapshot

Nothing here changes the system. The SMOS update API of the Web Manager (port
8624) is only ever asked the questions listed in API_READS below - never
`GET /api/software/upgrade`, which is a GET that STARTS an upgrade (see
docs/concepts/lifecycle_install_update_upgrade.md (chapter 7)). Items that need root (boot
entries, btrfs subvolumes) are read with `sudo -n` and simply left out when
sudo would prompt.

`compare` exits 1 when something boot-critical changed in a way an update must
not cause (the kernel `root=` argument, a `LABEL=` line that names a label the
root disk does not carry); a new `subvol=` after a delta update is expected.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path.home() / ".cache" / "pifinder_stellarmate" / "smos_update_state"
API = "http://127.0.0.1:8624"

# The ONLY routes this script may call. All are plain questions.
API_READS = (
    "/api/software/version",
    "/api/software/release",
    "/api/software/upgradable",
    "/api/software/delta/status",
    "/api/software/delta/check",
    "/api/software/delta/subvolumes",
)

PACKAGES = (
    "smoscore", "stellarmatetools", "stellarmateupdater", "stellarmatewebmanager",
    "stellarmatenetworkmanager", "stellarmateudevmanager", "libindi", "indi-firmware",
    "ekoslive", "linux", "systemd", "python", "flatpak", "openssh",
)
SYSTEM_UNITS = (
    "pifinder-control-center", "pifinder", "smos-pre-reboot-fix", "sddm",
    "display-setup", "wg-nethserver-client",
)
USER_UNITS = ("stellarmatewebmanager", "org.kde.kstars", "pifinder-smos-update-guard")

# Keys whose change is expected after a delta update (a new system subvolume).
# Keys that differ on every run and say nothing about the system.
NOISE = ("taken", "api.upgradable.last_check")
EXPECTED_CHANGE = ("cmdline.rootflags", "cmdline.initrd", "api.version.version")
# Keys that must not change by themselves.
BOOT_CRITICAL = ("cmdline.root", "fstab.labels", "root_device.label", "boot_entries.labels")


def _run(cmd, timeout=15, any_exit=False):
    """stdout of the command, None if it failed. `any_exit` keeps the output of
    commands that signal a state with their exit code (systemctl is-active)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if (r.returncode == 0 or (any_exit and r.stdout.strip())) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def api_get(path):
    if path not in API_READS:
        raise ValueError(f"refusing to call {path}: not a read-only question")
    try:
        with urllib.request.urlopen(API + path, timeout=15) as resp:
            body = json.loads(resp.read())
        return body.get("payload", body)
    except Exception as e:  # unreachable Web Manager is a finding, not a crash
        return {"error": str(e)}


def parse_cmdline(text):
    out = {}
    for tok in (text or "").split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    out["flags"] = sorted(t for t in (text or "").split() if "=" not in t)
    return out


def collect():
    s = {"taken": datetime.datetime.now().isoformat(timespec="seconds")}
    s["smos_version"] = _read("/etc/stellarmate/version")
    s["model"] = _read("/etc/stellarmate/model") or _read("/proc/device-tree/model")
    s["kernel_running"] = os.uname().release
    cmd = _read("/proc/cmdline")
    s["cmdline"] = parse_cmdline(cmd)

    s["api"] = {p.rsplit("/api/software/", 1)[1].replace("/", "."): api_get(p) for p in API_READS}

    # fstab: only the LABEL= lines matter for the boot-label problem (#561)
    fstab = _read("/etc/fstab") or ""
    s["fstab"] = {"labels": sorted(l.split()[0] for l in fstab.splitlines()
                                   if l.strip().startswith("LABEL="))}
    src = _run(["findmnt", "-no", "SOURCE", "/"])
    label = _run(["lsblk", "-no", "LABEL", src.split("[")[0]]) if src else None
    s["root_device"] = {"source": src, "label": label}

    # Boot configuration: Pi (cmdline.txt) or systemd-boot entries (x86)
    entries = {}
    for p in ("/boot/cmdline.txt", "/boot/firmware/cmdline.txt"):
        t = _read(p)
        if t:
            entries[p] = t
    listing = _run(["sudo", "-n", "ls", "/efi/loader/entries"])
    for name in (listing or "").split():
        t = _run(["sudo", "-n", "cat", f"/efi/loader/entries/{name}"])
        if t:
            entries[name] = t
    s["boot_entries"] = {
        "files": {k: {"options": (re.search(r"^options\s+(.*)$", v, re.M).group(1)
                                  if re.search(r"^options\s+(.*)$", v, re.M) else v)}
                  for k, v in entries.items()},
        "labels": sorted({m for v in entries.values() for m in re.findall(r"LABEL=\S+", v)}),
    }
    s["boot_default"] = (_run(["sudo", "-n", "cat", "/efi/loader/loader.conf"]) or "").replace("\n", "; ")

    sv = _run(["sudo", "-n", "btrfs", "subvolume", "list", "/"])
    s["subvolumes"] = sorted(re.findall(r"path (@[^\s]+)$", sv or "", re.M))
    s["disk_free_root_gb"] = None
    df = _run(["df", "-BG", "--output=avail", "/"])
    if df:
        m = re.search(r"(\d+)G", df)
        s["disk_free_root_gb"] = int(m.group(1)) if m else None

    pk = {}
    out = _run(["pacman", "-Q"]) or ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in PACKAGES:
            pk[parts[0]] = parts[1]
    s["packages"] = pk
    fp = _run(["flatpak", "list", "--columns=application,version"]) or ""
    s["kstars_flatpak"] = next((l.split()[-1] for l in fp.splitlines() if "org.kde.kstars" in l), None)

    s["system_units"] = {u: {"active": _run(["systemctl", "is-active", u], any_exit=True) or "unknown",
                             "enabled": _run(["systemctl", "is-enabled", u], any_exit=True) or "unknown"}
                         for u in SYSTEM_UNITS}
    s["user_units"] = {u: _run(["systemctl", "--user", "is-active", u], any_exit=True) or "unknown" for u in USER_UNITS}
    s["pfsm"] = {
        "version_restored": _read(REPO_ROOT / ".smos_version_restored"),
        "git_head": _run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"]),
        "hook_is_symlink": (Path.home() / "bin" / "smos-post-update.sh").is_symlink(),
    }
    return s


def flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = d
    return out


def compare(a, b):
    fa, fb = flatten(a), flatten(b)
    keys = sorted(set(fa) | set(fb))
    critical, expected, other = [], [], []
    for k in keys:
        if k in NOISE or fa.get(k) == fb.get(k):
            continue
        row = (k, fa.get(k), fb.get(k))
        if any(k == c or k.startswith(c + ".") for c in BOOT_CRITICAL):
            critical.append(row)
        elif any(k == e or k.startswith(e + ".") for e in EXPECTED_CHANGE):
            expected.append(row)
        else:
            other.append(row)
    return critical, expected, other


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--out")
    cp = sub.add_parser("compare")
    cp.add_argument("a")
    cp.add_argument("b")
    sub.add_parser("latest")
    args = ap.parse_args(argv)

    if args.cmd == "latest":
        files = sorted(STATE_DIR.glob("*.json"))
        print(files[-1] if files else "")
        return 0
    if args.cmd == "snapshot":
        state = collect()
        out = Path(args.out) if args.out else STATE_DIR / (datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        print(out)
        return 0
    a, b = (json.loads(Path(p).read_text()) for p in (args.a, args.b))
    critical, expected, other = compare(a, b)

    def show(title, rows, mark):
        if not rows:
            return
        print(f"\n{title}")
        for k, x, y in rows:
            print(f"  {mark} {k}: {x!r} -> {y!r}")

    print(f"Vergleich {a.get('taken')}  ->  {b.get('taken')}")
    show("BOOT-KRITISCH (darf ein Update nicht von selbst aendern):", critical, "!!")
    show("Erwartet bei einem Systemabbild-Update:", expected, "  ")
    show("Sonstige Aenderungen:", other, "  ")
    if not (critical or expected or other):
        print("\nKeine Unterschiede.")
    print(f"\nErgebnis: {'BOOT-KRITISCH' if critical else 'ok'} "
          f"({len(critical)} kritisch, {len(expected)} erwartet, {len(other)} sonstige)")
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
