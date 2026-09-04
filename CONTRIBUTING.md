# Contributing

## Branch model

Three branches, each a stricter guarantee than the last:

- **`main`** — release cuts only, fast-forwarded from `dev` on an explicit release. Lags behind
  active development; this is what a production install should track.
- **`dev`** — active development, targeting the PiFinder/SMOS versions currently pinned in
  `pifinder_stellarmate_setup.sh` (`pifinder_stellarmate_version_stable`/`smos_version_stable`,
  see `version.txt`). All regular feature/fix PRs branch off `dev` and PR back into it. Anyone
  testing `dev` should never hit a surprise PiFinder/SMOS version jump - only the features/fixes
  building on top of the already-pinned versions.
- **`alpha`** — integration branch for a PiFinder or SMOS version bump (i.e. any change that moves
  `pifinder_stellarmate_version_stable`/`smos_version_stable` forward), branched off `dev`. Work
  happens directly on `alpha` rather than spawning its own feature branches off it - it exists to
  absorb one specific upgrade's churn, not to become a second parallel development track. While
  it's in flight, merge `dev` into `alpha` regularly (not just once at the end) so fixes landing on
  `dev` in the meantime aren't lost or left to collide in one big merge later. Once the version bump
  works (patches apply, both INDI drivers build, and a full `bin/simulate_fresh_install.sh
  --mode=fresh` + `pifinder_stellarmate_setup.sh` + cold-boot reboot passes cleanly - see
  `Readme_UTM_dev_X86.md` for how to run that on an x86 dev VM), merge `alpha` into `dev` promptly
  and delete it. `alpha` is meant to be short-lived per upgrade, not a standing branch that outlives
  the version bump it was created for.

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
