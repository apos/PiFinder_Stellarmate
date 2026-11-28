# Contributing

## Branch model

Two branches:

- **`main`** — releases only: `dev` is merged into it with a pull request titled "Cut vX.Y.Z: ...", tagged and published as a
  GitHub release. This is what a normal installation tracks.
- **`dev`** — all development. Feature and fix branches start from `dev`, go back with a pull request and are deleted with the
  merge. After a release `dev` is fast-forwarded to `main`.

A PiFinder or StellarMate OS version bump (anything that moves `pifinder_stellarmate_version_stable` / `smos_version_stable`) is
done the same way, on its own short-lived branch from `dev`. Before it is merged: the patches apply, the INDI drivers build, and
a full `bin/simulate_fresh_install.sh --mode=fresh`, `pifinder_stellarmate_setup.sh` and a cold boot pass (see
`Readme_UTM_dev_X86.md` for doing that on an x86 dev VM). There is no separate `alpha` branch.

## Tests

`bash test_tools/run_regression.sh` is the project's regression run; what it covers and how to use it:
[test_tools/README.md](test_tools/README.md). Run it (at least the offline group) before every pull request, and `all --move`
before a release.

## Issue labels for the code concerned

An issue that concerns code outside this project says whose, with one or more of:

| Label | Concerns |
|---|---|
| `PiFinder` | PiFinder's own code, including this project's patches to it |
| `INDI` | upstream INDI code: libindi, indiserver, upstream drivers |
| `OnStep` | OnStep code: the controller's behaviour or the INDI OnStep driver |
| `SMOS` | StellarMate OS code: OS updates, StellarMate app, its web services |

There is no label for this project's own code: that is almost every issue. Several labels on one issue are fine.

## After cloning: initialize submodules

This repo vendors some dev/test tooling as git submodules (e.g. `bin/tests/vendor/bats-core`)
instead of requiring a global install on every machine that works on it. A plain `git clone` does
**not** pull submodule contents - run this once per fresh clone or worktree:

```bash
git submodule update --init --recursive
```

Skipping this step is the most common reason something that "should just work" (like the test
suite below) instead fails with a missing-file or command-not-found error.

## Running the shell-script test suite

`pifinder_stellarmate_setup.sh` and its `bin/*.sh` helpers have a `bats-core` unit-test suite
covering their pure logic (version comparison, argument parsing, OS detection) - not real
side effects like an actual `git clone`, package install, or systemd service, which stay
live-tested instead.

```bash
./bin/tests/run_all.sh
```

Runs in a couple of seconds, no root/network/real Pi required. Output is standard TAP format
(`ok`/`not ok` per test case) - a failure points at the exact assertion that didn't hold.

To run a single test file directly instead of the whole suite:

```bash
bin/tests/vendor/bats-core/bin/bats bin/tests/test_version_compare.bats
```

If `run_all.sh` reports the vendored `bats` binary is missing, you skipped the submodule-init step
above - it prints the exact command to fix it.

## Adding new tests

New pure-logic functions extracted from the setup script (or its `bin/*.sh` helpers) should come
with `.bats` tests in the same change, not as a follow-up.
