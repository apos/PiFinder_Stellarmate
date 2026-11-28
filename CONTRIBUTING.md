# Contributing

PiFinder_Stellarmate (PFSM) is an unofficial community project. It is not affiliated with StellarMate or PiFinder.

- [Where to ask and where to report](#where-to-ask-and-where-to-report)
- [Reporting an issue](#reporting-an-issue)
- [Developing](#developing): branches, tests, labels

## Where to ask and where to report

| You want to | Go to |
|---|---|
| report a bug in PFSM, ask for a feature | [Issues](https://github.com/apos/PiFinder_Stellarmate/issues), tracked on the [project board](https://github.com/users/apos/projects/15) |
| ask about StellarMate, KStars/Ekos on StellarMate | [StellarMate Discord](https://discord.gg/SbQsy9Ykh) |
| ask about PiFinder itself: hardware, building one, its software | [PiFinder Discord](https://discord.gg/wSPER2jt9) |
| report a bug in PiFinder itself (it also happens without PFSM) | [brickbots/PiFinder on GitHub](https://github.com/brickbots/PiFinder/) |

A bug that appears only on StellarMate with PFSM installed belongs here, not to PiFinder or StellarMate.

## Reporting an issue

**Only issues that follow these conventions are accepted.** An issue without the information below cannot be reproduced; it is
closed with a request to file it again, completely.

### Before you write

1. Search the [open and closed issues](https://github.com/apos/PiFinder_Stellarmate/issues?q=is%3Aissue). Add to an existing one
   instead of opening a second one.
2. Read "Status" in the [README](README.md): known limits are listed there.
3. Update to the latest release and try again.
4. One problem per issue.

### What an issue must contain

Use **New issue → Bug report**; the form asks for exactly this.

| Part | What to write |
|---|---|
| **Title** | what is wrong, where: "Mount Bridge: GoTo from KStars ends 20' off the object (OnStep, USB)". Not "does not work". |
| **Context** | what you wanted to do, indoors or under the sky, the role of the device (all-in-one, PiFinder client, Control host) |
| **Versions** | PFSM, PiFinder, StellarMate OS, INDI (commands below); Raspberry Pi model; mount and how it is connected (USB or network) |
| **Problem** | what happened, and what you expected instead |
| **Steps to reproduce** | numbered, one action per step, starting from a defined state; say how often it happens (always, sometimes, once) |
| **Logs** | the part around the failure, as text in a code block, with the time it happened |
| **Code or configuration** | if you ran a command or changed a file: the command and the change, in a code block |
| **Screenshots** | of the page or window that shows it; the whole message, not a cropped half |

Versions:

```bash
git -C ~/PiFinder_Stellarmate describe --tags
cat ~/PiFinder/version.txt
curl -s http://localhost:8624/api/info/version
pacman -Q libindi
```

Logs:

```bash
tail -n 200 ~/PiFinder_data/pifinder.log
journalctl -u pifinder -u pifinder-control-center --since "30 min ago" --no-pager
```

In the Control Center every terminal window has **Copy to clipboard**. The Mount Bridge's own messages are in its terminal in
the Mount Bridge tile.

**Before you post:** remove passwords, tokens, your home address and exact coordinates, and public IP addresses from logs and
screenshots. Issues are public.

### Code example

```text
Title: Mount Bridge: "Goto Push-To" stops 2 degrees short (Telescope Simulator)

Context      Control Center on a Pi 5, all-in-one role, indoors, "Real Hardware + GSC Simulation"
Versions     PFSM v3.0.0, PiFinder 2.6.4, StellarMate OS 2.4.0, INDI 2.2.5, Telescope Simulator
Problem      After "Goto Push-To" the mount stops 2 degrees from the blue cross. Expected: on the cross.
Reproduce    1. Coupling "GoTo"  2. GoTo M13 from KStars, wait for "On target"
             3. Move north with the direction buttons  4. Press "Goto Push-To"      -> 3 of 3 times
Log          (Mount Bridge terminal, 21:14)  [WARNING] Mount refused the correction ...
Screenshot   sky picture with the card under it
```

### Feature requests

Say who needs it and in which situation (at the telescope, at home, remote), what you do today instead, and what you would like
to happen, step by step.

### Pull requests

Open an issue first for anything beyond a small correction, so the direction is agreed. Pull requests go to **`dev`**, follow the
rules below, and say what was tested and what was not.

## Developing

### Branch model

Two branches:

- **`main`** — releases only: `dev` is merged into it with a pull request titled "Cut vX.Y.Z: ...", tagged and published as a
  GitHub release. This is what a normal installation tracks.
- **`dev`** — all development. Feature and fix branches start from `dev`, go back with a pull request and are deleted with the
  merge. After a release `dev` is fast-forwarded to `main`.

A PiFinder or StellarMate OS version bump (anything that moves `pifinder_stellarmate_version_stable` / `smos_version_stable`) is
done the same way, on its own short-lived branch from `dev`. Before it is merged: the patches apply, the INDI drivers build, and
a full `bin/simulate_fresh_install.sh --mode=fresh`, `pifinder_stellarmate_setup.sh` and a cold boot pass (see
`Readme_UTM_dev_X86.md` for doing that on an x86 dev VM). There is no separate `alpha` branch.

### Tests

`bash test_tools/run_regression.sh` is the project's regression run; what it covers and how to use it:
[test_tools/README.md](test_tools/README.md). Run it (at least the offline group) before every pull request, and `all --move`
before a release.

### Issue labels for the code concerned

An issue that concerns code outside this project says whose, with one or more of:

| Label | Concerns |
|---|---|
| `PiFinder` | PiFinder's own code, including this project's patches to it |
| `INDI` | upstream INDI code: libindi, indiserver, upstream drivers |
| `OnStep` | OnStep code: the controller's behaviour or the INDI OnStep driver |
| `SMOS` | StellarMate OS code: OS updates, StellarMate app, its web services |

There is no label for this project's own code: that is almost every issue. Several labels on one issue are fine.

### After cloning: initialize submodules

This repo vendors some dev/test tooling as git submodules (e.g. `bin/tests/vendor/bats-core`)
instead of requiring a global install on every machine that works on it. A plain `git clone` does
**not** pull submodule contents - run this once per fresh clone or worktree:

```bash
git submodule update --init --recursive
```

Skipping this step is the most common reason something that "should just work" (like the test
suite below) instead fails with a missing-file or command-not-found error.

### Running the shell-script test suite

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

### Adding new tests

New pure-logic functions extracted from the setup script (or its `bin/*.sh` helpers) should come
with `.bats` tests in the same change, not as a follow-up.
