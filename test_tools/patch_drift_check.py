#!/usr/bin/env python3
"""Dry-run every PFSM patch against the pristine files of one or more PiFinder tags.

Why: a new PiFinder version moves the lines our diffs/*.diff are anchored to. The setup finds that out only when it runs
(a "Patch didn't fully apply" warning). This finds it beforehand, without touching any checkout, so it can run before a
pin change and from time to time against the newest upstream version as an early warning.

Which diff goes to which file is read from bin/patch_PiFinder_installation_files.sh (the `apply_patch_or_warn <target> <diff>`
lines) and bin/functions.sh (the variables used as targets), so the result is what the setup would really do, not a guess.
Targets outside the PiFinder checkout (the venv, the INDI driver source) cannot be checked here and are listed as such.

    python3 test_tools/patch_drift_check.py [--repo ~/PiFinder] [--fetch] [--strict] [TAG ...]

With no TAG: the pinned tag (version.txt), the newest upstream release tag and the newest beta tag.
Exit status 0 when the pinned tag is clean; 1 when a patch fails or its file is gone in the pinned tag (with --strict: in any tag).
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CLEAN, OFFSET, FUZZ, FAIL, MISSING, UPSTREAMED = "clean", "offset", "fuzz", "FAIL", "MISSING", "upstreamed"
NEWFILE, LEGACY = "new file", "legacy"
BAD = {FAIL, MISSING}
# Diffs the patch script applies only when the modern file is absent (PiFinder before 2.6.0 had .tpl instead of .html):
# a missing target in a current tag is expected for them, not drift.
LEGACY_FALLBACKS = {"index_tpl.diff", "header_tpl.diff"}


def read_targets(pfsm_dir: Path):
    """[(diff_name, relative_target_or_None, raw_target)] from the patch script; None = outside the PiFinder checkout."""
    functions = (pfsm_dir / "bin" / "functions.sh").read_text()
    script = (pfsm_dir / "bin" / "patch_PiFinder_installation_files.sh").read_text()
    variables = {}
    for name, value in re.findall(r'^(\w+)="([^"]*)"', functions, re.M):
        variables[name] = value
    prefix = "${pifinder_dir}/"

    def resolve(raw: str, depth: int = 0):
        raw = raw.strip()
        if depth > 5:
            return None
        m = re.fullmatch(r"\$\{?(\w+)\}?", raw)
        if m and m.group(1) in variables:
            return resolve(variables[m.group(1)], depth + 1)
        if raw.startswith(prefix):
            rest = raw[len(prefix):]
            return None if "$" in rest else rest
        return None

    text = script.replace("\\\n", " ")
    found = []
    for target, diff in re.findall(r'apply_patch_or_warn\s+("[^"]+"|\S+)\s+"[^"]*?/(diffs/[^"]+\.diff)"', text):
        target = target.strip('"')
        found.append((Path(diff).name, resolve(target), target))
    return found


def git(repo: Path, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def file_at_tag(repo: Path, tag: str, rel: str):
    r = subprocess.run(["git", "-C", str(repo), "show", f"{tag}:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def creates_file(diff: Path) -> bool:
    """A create-diff (our own new test files): its first hunk starts at line 0 of an empty original."""
    with diff.open() as handle:
        for line in handle:
            if line.startswith("@@"):
                return line.startswith("@@ -0,0 ")
    return False


def classify(output: str, returncode: int) -> str:
    if "Reversed (or previously applied)" in output or "Skipping patch" in output:
        return UPSTREAMED
    if "FAILED" in output or returncode not in (0,):
        return FAIL
    if re.search(r"with fuzz \d+", output):
        return FUZZ
    if "offset" in output:
        return OFFSET
    return CLEAN


def check_tag(repo: Path, pfsm_dir: Path, tag: str, targets):
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for diff_name, rel, raw in targets:
            if rel is None:
                results.append((diff_name, "-", "outside the PiFinder checkout (not checked)"))
                continue
            data = file_at_tag(repo, tag, rel)
            diff = pfsm_dir / "diffs" / diff_name
            work = Path(tmp) / "target"
            if work.exists():
                work.unlink()
            if data is None:
                if creates_file(diff):
                    with diff.open() as handle:
                        p = subprocess.run(["patch", "--dry-run", "-N", "--no-backup-if-mismatch", str(work)],
                                           stdin=handle, capture_output=True, text=True)
                    ok = p.returncode == 0 and "FAILED" not in p.stdout + p.stderr
                    results.append((diff_name, NEWFILE if ok else FAIL, f"{rel} (created by the patch)"))
                elif diff_name in LEGACY_FALLBACKS:
                    results.append((diff_name, LEGACY, f"{rel}: only used when the modern file is missing (PiFinder before 2.6.0)"))
                else:
                    results.append((diff_name, MISSING, f"{rel} does not exist in {tag} (renamed or removed upstream)"))
                continue
            work.write_bytes(data)
            with diff.open() as handle:
                p = subprocess.run(["patch", "--dry-run", "-N", "--no-backup-if-mismatch", str(work)],
                                   stdin=handle, capture_output=True, text=True)
            status = classify(p.stdout + p.stderr, p.returncode)
            results.append((diff_name, status, rel))
    return results


def default_tags(repo: Path, pfsm_dir: Path):
    pinned = "v" + (pfsm_dir / "version.txt").read_text().strip()
    tags = git(repo, "tag", "--sort=-v:refname").stdout.split()
    release = next((t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)), None)
    beta = next((t for t in tags if "beta" in t or "rc" in t), None)
    out = []
    for t in (pinned, release, beta):
        if t and t not in out:
            out.append(t)
    return pinned, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tags", nargs="*", help="PiFinder tags to check against")
    ap.add_argument("--repo", default=os.path.expanduser("~/PiFinder"), help="a PiFinder git checkout (default ~/PiFinder)")
    ap.add_argument("--pfsm-dir", default=str(Path(__file__).resolve().parent.parent), help="the PFSM repository (default: this one)")
    ap.add_argument("--fetch", action="store_true", help="git fetch --tags in the PiFinder checkout first")
    ap.add_argument("--strict", action="store_true", help="exit 1 on a failure in ANY checked tag, not only the pinned one")
    args = ap.parse_args(argv)

    repo, pfsm_dir = Path(args.repo), Path(args.pfsm_dir)
    if not (repo / ".git").exists():
        print(f"{repo} is not a git checkout of PiFinder", file=sys.stderr)
        return 2
    if args.fetch:
        git(repo, "fetch", "--tags", "--quiet")
    pinned, tags = default_tags(repo, pfsm_dir)
    if args.tags:
        tags = args.tags
    targets = read_targets(pfsm_dir)
    if not targets:
        print("no apply_patch_or_warn lines found: wrong --pfsm-dir?", file=sys.stderr)
        return 2

    exit_code = 0
    for tag in tags:
        if git(repo, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}", check=False).returncode != 0:
            print(f"{tag}: not found in {repo} (try --fetch)")
            exit_code = 2
            continue
        results = check_tag(repo, pfsm_dir, tag, targets)
        counts = {}
        for _, st, _ in results:
            counts[st] = counts.get(st, 0) + 1
        label = " (pinned)" if tag == pinned else ""
        summary = ", ".join(f"{counts[k]} {k}" for k in (CLEAN, OFFSET, FUZZ, NEWFILE, LEGACY, UPSTREAMED, FAIL, MISSING, "-") if k in counts)
        print(f"{tag}{label}: {summary.replace(' -', ' not checked')}")
        for name, st, info in results:
            if st in (FUZZ, UPSTREAMED) or st in BAD:
                print(f"    {st:10} {name}: {info}")
        if any(st in BAD for _, st, _ in results) and (tag == pinned or args.strict):
            exit_code = max(exit_code, 1)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
