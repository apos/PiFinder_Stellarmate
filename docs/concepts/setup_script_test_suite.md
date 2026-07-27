# Concept: A Unit-Test Suite for the Setup Script

## Status

**Concept - not implemented.** Written up after a design discussion (2026-07-26), prompted by the
upcoming setup-script refactor (`setup_indi_only_install_mode.md`) and by this project's own
history of exactly the class of bug unit tests would catch early: this session alone found and
fixed two silent-failure bugs in `pifinder_stellarmate_setup.sh` (a `git clone` with no exit-code
check leaving a broken install behind looking successful, and the branch picker silently ignoring
"main" on an existing checkout) - both were pure control-flow logic, not hardware-dependent.

## 1. Overview

`pifinder_stellarmate_setup.sh` and its `bin/*.sh` helpers mix two very different kinds of code:

- **Pure logic**: version comparison (`version_gt`/`version_eq`), argument parsing (`--action=`,
  `--branch=`, the new `--mode=` from the INDI-only concept), path construction, the new OS-detection
  abstraction. Fully testable in isolation, no real system access needed.
- **Real side effects**: actual `git clone`, package installation, systemd service management,
  hardware group changes. Testing these "for real" means running them against a real (or
  realistically faked) system - not a good fit for fast, isolated unit tests, and this project
  already has an established, working discipline for this instead: live testing on real hardware,
  documented as it happens (this entire session is an example of that discipline in action).

The concept here is narrow and deliberate: unit-test the first category, keep doing the second the
way this project already does it well. Trying to mock a full Arch/Debian system to unit-test `git
clone`/`pacman` calls would be a large, fragile effort for questionable benefit - better to keep
that class of behavior honest via the existing live-testing rounds.

## 2. Requirements

- **Extract testable functions**, don't test the script monolithically. Where logic is currently
  inline in the middle of a 500+ line script (e.g. `version_gt`/`version_eq` already *are* separate
  functions - good precedent to extend), keep pulling control-flow decisions into small, named,
  argument-in/output-out functions that don't touch the filesystem or network.
- **`bats-core`** as the test framework - the de facto standard for testing Bash, already widely
  used for exactly this kind of shell-script unit testing, no new language/tooling paradigm to learn.
- Tests must run **without root, without network, without a real Pi** - a contributor (or CI, if
  this project ever adds it) should be able to run the suite on any Linux box in seconds.
- Explicitly **not** in scope: testing that a real `git clone` succeeds, that `pacman`/`apt`
  actually installs a package, that a systemd service actually starts - those stay live-tested.

## 3. Architecture / Implementation Concept

```
python/tests/  <- existing pattern in PiFinder itself (pytest, smoke/unit/integration markers)
bin/tests/     <- new: bats-core tests for this project's own shell scripts
  test_version_compare.bats     # version_gt/version_eq
  test_arg_parsing.bats         # --action=/--branch=/--mode= parsing
  test_os_detect.bats           # new OS-abstraction functions from setup_indi_only_install_mode.md
```

- Each `.bats` file `source`s only the specific function(s) under test (e.g. just the version-
  compare block), never the whole setup script - keeps tests fast and avoids accidentally running
  real installs.
- A `nox`-style or plain `bash bin/tests/run_all.sh` entry point, consistent with PiFinder's own
  `nox -s unit_tests` convention already documented in its `CLAUDE.md` - familiar shape for anyone
  who already works in the PiFinder codebase.
- New logic introduced in future work (the OS-detection abstraction, the `--mode=` flag parsing)
  should ship *with* its own `.bats` tests in the same PR, not as a follow-up - cheapest time to
  write them is while the function is still fresh, and it forces the function itself to be written
  in a testable (pure, side-effect-free) shape from the start.

## 4. Design Principles

- **Test the decisions, not the world.** A unit test should answer "given these inputs, does this
  function decide correctly" - never "did this actually install a package on my machine."
- **No mocking arms race.** If a function is hard to unit-test without heavy mocking, that's a
  signal the function itself mixes logic and side effects and should be split, not a signal to
  invest in a bigger mocking framework.
- **Retrofit opportunistically, don't stop to backfill everything at once.** Add tests for existing
  functions (`version_gt`/`version_eq`) as a small first PR, then require new logic to come with
  tests going forward - don't block the INDI-only mode work on writing a complete historical test
  suite first.

## 5. Test Strategy (for the test suite itself)

- Success criterion: running the suite catches the *category* of bug this project already found
  live twice this session (a control-flow branch that silently does the wrong thing) - a good
  concrete validation exercise once the suite exists is writing a test that would have caught the
  "Install from: main" branch-picker bug retroactively, using it as the litmus test for "is this
  suite actually useful."

## 6. Known Risks / Open Questions

- **False sense of security**: unit tests covering only pure logic can't catch the actual bugs that
  matter most in practice (real git/package-manager/systemd failures) - must be communicated clearly
  so this isn't mistaken for "the setup script is now fully tested."
- **Maintenance overhead**: every refactor of a tested function needs its tests updated too - small
  but real ongoing cost, worth it mainly because a refactor (the INDI-only mode work) is happening
  anyway.
- **`bats-core` availability**: needs to be installed on whatever machine/CI runs the tests - not
  currently a dependency of this project at all; a small, one-time addition.

## 7. Effort & Priority

Low-to-moderate effort, and best sequenced *alongside* the `setup_indi_only_install_mode.md` work
rather than as its own separate initiative - the OS-detection abstraction that work introduces is
exactly the kind of brand-new, pure-logic surface that benefits most from tests written from day
one, cheaper than retrofitting.

## Related

[`setup_indi_only_install_mode.md`](setup_indi_only_install_mode.md) (the refactor this most
directly supports), basic-memory `pifinder-stellarmate/00072`/`00075` (the two live-found
control-flow bugs this session that motivate the concept).
