# Concept: unit-test suite (bats-core) for the setup scripts

> **Status: partially implemented.** Tracked as
> [GitHub issue #62](https://github.com/apos/PiFinder_Stellarmate/issues/62) (closed 2026-08-02).
> A real bats-core suite exists in `bin/tests/`; the **argument-parsing / branch-picker** part, which
> originally motivated it, is still not covered (see §5).
>
> **Provenance:** the original of this document lived on the since-deleted branch
> `concept/remote-mount-bridge-and-setup-refactor` and never reached `main`/`dev`. This file is a
> **reconstruction** (2026-10-06) from the surviving sources: issue #62 and its comment, the
> basic-memory note `pifinder-stellarmate/00076`, the commit messages of `9853a35`, `f582b62`, `f2d3eb1`,
> the comments in `bin/tests/` and the header comments of `bin/version_compare.sh` / `bin/os_detect.sh`.
> Details of the original wording that are lost are not invented here.

## 1. Idea

A [`bats-core`](https://github.com/bats-core/bats-core) unit-test suite for the **pure logic** of
`pifinder_stellarmate_setup.sh` and `bin/*.sh`:

- version comparison,
- argument parsing,
- the OS / package-manager detection abstraction (see
  [`setup_indi_only_install_mode.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/setup_indi_only_install_mode.md)).

**Explicitly not** tested: real side effects — an actual `git clone`, a package install, systemd
operations. Those stay **live-tested on real hardware**, as this project already does well. A mock
for `pacman`/`systemd` would test the mock, not the machine.

## 2. Motivation

Two **silent-failure control-flow bugs**, both found live in the same session (2026-07-26):

1. a `git clone` whose exit code was never checked, so a failed clone carried on as if it had worked;
2. the branch picker silently ignoring `main`.

Neither needs hardware to catch — both are pure control-flow mistakes of exactly the kind cheap unit
tests catch. The concept sequences the suite **alongside #61**: the new OS-detection logic is the
ideal first customer — new, pure and testable from day one, instead of retrofitted.

## 3. Design principles

### 3.1 Test logic, not side effects — via a pure/impure split

The scripts are structured so that **decisions** are pure functions (no filesystem, command or network
access; the facts they decide on are passed in as arguments) and **facts/side effects** live in thin
impure wrappers that delegate every decision to the pure half. Example, `bin/os_detect.sh`:

| Pure (unit-tested) | Impure (live-tested) |
|---|---|
| `os_pick_package_manager`, `os_package_name`, `os_pacman_atomic_updates_enabled` | `os_detect_package_manager`, `os_pacman_check_atomic_updates`, `os_install_packages` |

Pure tests pass identically on any machine, regardless of what is installed there — which is the whole
point ("works without a real Pi").

### 3.2 Extract to make testable

Logic embedded in the big setup script is extracted into small sourceable files with no side effects
and no dependency on other script state, e.g. `version_gt()` / `version_eq()` →
`bin/version_compare.sh`. The main script then `source`s it. Extraction must be **behavior-identical**;
the first slice was verified by manual before/after calls and a real
`pifinder_stellarmate_setup.sh --action=cancel` run still printing the expected version-match line.

### 3.3 Vendored, not globally installed

bats-core is vendored as a **git submodule** (`bin/tests/vendor/bats-core`) — the same pattern as
PiFinder's own `tetra3` submodule. The first iteration installed bats-core to `~/.local/bin` on one Pi:
untracked, undocumented, and absent on any other clone — "works on my machine" for a suite meant to
run without special hardware. Caught live and fixed immediately (`f582b62`). General rule recorded in
basic-memory: vendor dev/test tooling instead of installing it globally.

Needs initialising once per fresh clone/worktree:

```bash
git submodule update --init bin/tests/vendor/bats-core
```

### 3.4 One documented entry point

`bin/tests/run_all.sh` runs every `*.bats` file in `bin/tests/` with the vendored binary and fails with
the init hint above if the submodule is missing. Contributor / CI dependency only — the setup script
itself never needs bats.

## 4. What exists

| File | Covers | Cases |
|---|---|---|
| `bin/tests/test_version_compare.bats` | `version_gt` / `version_eq` — incl. the numeric-vs-lexical two-digit-segment case (`1.10.0` vs `1.9.0`) and the exact call-site arguments of the real `setup.sh` regression from the originating session | 9 |
| `bin/tests/test_os_detect.bats` | the pure functions of `bin/os_detect.sh` (manager priority, package-name table incl. the nixpkgs `indilib` name, Atomic Updates state parsing) | 16 |

(25 cases in total, all passing as of 2026-10-06 via `bin/tests/run_all.sh`.)

History: `9853a35` (first slice — extract and test `version_gt`/`version_eq`, a zero-risk warm-up before
new logic), `f582b62` (vendor bats-core), `f2d3eb1` (`os_detect.sh` + its tests), `648235c` (Atomic
Updates handling).

## 5. Not covered yet

- **Argument parsing** — `--mode=indi_only|full`, `--action=`, `--branch=`, and the branch picker.
- Consequently the **two bugs that motivated the suite** (unchecked `git clone` exit code, branch
  picker ignoring `main`) are **not regression-tested yet**. This is why #62 was left open after the
  partial progress comment of 2026-07-29 and only closed on 2026-08-02.

Argument parsing currently sits inline in the setup script's top-level `for arg in "$@"` loop; per §3.2 it
would have to be extracted into a sourceable, side-effect-free function before it can be tested.

## 6. Deliberately out of scope

- Real package installs, `git clone`, systemd, hardware access (live-tested).
- The `gui_installer` Python code (its own testing is a separate question).
- Mocking `pacman`/`apt`/`nix` — see §1.

## 7. Related

#61 / [`setup_indi_only_install_mode.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/setup_indi_only_install_mode.md) (the OS-detection logic that
got tests from day one) · #60 / [`remote_indi_coupling_split_host.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/remote_indi_coupling_split_host.md).
