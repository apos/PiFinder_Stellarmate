# Concept: Upstream INDI driver packaging (indi-3rdparty submission)

> **Status: concept — not yet decided/implemented.** Not yet filed as a GitHub issue. Captures the
> initial discussion of how to make the `PiFinder LX200` / `PiFinder Mount Bridge` drivers buildable
> by the official INDI project itself, instead of only via this repo's own build scripts — kept as
> "considerations to act on later" rather than a committed plan (same style as
> [`simulation_fidelity_and_pifinder_orientation.md`](simulation_fidelity_and_pifinder_orientation.md)).

## 1. Context

This repo currently ships two custom INDI telescope drivers (`indi_pifinder_lx200`,
`indi_pifinder_mount_bridge`), built and installed entirely by this repo's own scripts
(`bin/build_indi_driver.sh`, `bin/build_indi_bridge.sh`), linking against the already-installed
system `libindi`. See [`Readme_PiFinder_LX200.md` — Code, Deployment &
Strategy](../../Readme_PiFinder_LX200.md#code-deployment--strategy) for that architecture, and
`docs/concepts/indi_driver_singleton_guard.md`'s sibling design note (basic-memory
`pifinder-stellarmate/00008`/`00012`) for how the drivers got to their current standalone,
minimal-footprint shape.

This document is about a different, upstream-facing question: whether/how to make these drivers
part of the **official INDI project** itself, so they build automatically as part of INDI's own
release, CI, and packaging pipeline — rather than only ever being buildable by cloning this repo.
[Issue #347](https://github.com/apos/PiFinder_Stellarmate/issues/347) already raised one concrete
motivating case (a Flatpak-KStars user currently can't get these drivers without a system install);
a merged indi-3rdparty submission is the actual prerequisite for that.

**Explicitly out of scope here**: further driver *development*. The driver's own architecture
(decoupled position + generic INDI Sync, no mount-specific protocol) is a separate, already-settled
question — this document is purely about how the existing, working driver code gets *built and
distributed* by someone other than this repo.

## 2. Which upstream repo: `indilib/indi` vs `indilib/indi-3rdparty`

- **`indilib/indi`** (core): the base INDI framework/library plus only the small set of drivers the
  INDI core team maintains directly long-term. High bar for inclusion — not the right target for a
  single vendor-/project-specific device driver like this one.
- **`indilib/indi-3rdparty`**: hosts exactly this class of driver — individually optional,
  community/vendor-maintained device drivers, each in its own subdirectory with its own small
  `CMakeLists.txt` + `driver.xml.in`, selected via a top-level CMake option flag, and built/packaged
  (Debian PPA, Arch AUR, macOS Homebrew tap, the Flatpak KStars catalog from #347) by INDI's own CI.

Our current driver's shape — standalone CMake target, `pkg_check_modules(INDI REQUIRED libindi)`,
linking `indidriver`/`indilx200`, its own `driver.xml.in` (see
[`indi_pifinder/CMakeLists.txt`](../../indi_pifinder/CMakeLists.txt)) — already matches an
indi-3rdparty driver almost exactly.

**Leaning**: `indilib/indi-3rdparty`, not core.

## 3. Local dev bench

Because the driver only needs the already-installed `libindi` headers/`.so` files (no full INDI
source build — see basic-memory `00008`/`00012`), a native build on any of the platforms below takes
seconds; there is no case for cross-compiling the driver itself.

- **Pi4 (StellarMate OS, arm64, real hardware)**: the existing, already end-to-end-verified dev/test
  target (KStars, SkySafari, live EQ5/OnStepX). Keep as the primary bench — it's the only one
  verified against real hardware.
- **x86 UTM (StellarMate VM)**: a cheap, independent architecture smoke test (arm64 vs. x86_64)
  before opening the upstream PR — not a substitute for Pi4 verification.
  [Issue #454](https://github.com/apos/PiFinder_Stellarmate/issues/454) (cmake currently broken
  there, blocking all INDI driver rebuilds) would need fixing first.
- **Mac**: only relevant to also verify the driver builds via indilib's own macOS path (the
  `indilib/indi-3rdparty` Homebrew tap), since indi-3rdparty's own CI builds on macOS too — a
  Mac-only build failure would otherwise only surface after the PR is already open. Not needed for
  Linux/StellarMate correctness.
- **Cross-compile**: not needed — each platform builds the same tiny, single-`.cpp` driver natively
  in seconds.

## 4. How to submit upstream

This would be a genuine third-party upstream PR (against `indilib/indi-3rdparty`, not this repo) —
basic-memory's general upstream-PR discipline (`basic-memory/00018_bm-upstream-pr-strategy`) applies
in full: isolated worktree/clone of indi-3rdparty's own target branch (never our own patched
checkout), baseline verification against their current tree, a real build+test before claiming it
works, one logical change per PR, PR body drafted and shown for approval before `gh pr create`,
tracked in basic-memory once opened.

Concretely: fork `indilib/indi-3rdparty`, add a new top-level driver directory (e.g.
`indi-pifinder/`) containing our `CMakeLists.txt` + `.cpp`/`.h` + `driver.xml.in`, and wire it into
their top-level `CMakeLists.txt` via a `WITH_PIFINDER`-style option — **not yet confirmed**: this
needs reading indi-3rdparty's own `CONTRIBUTING`/README, or an existing small merged driver PR, as
the concrete template before drafting ours.

## 5. Open questions / next steps

- Read indi-3rdparty's actual, current contribution conventions (their own docs, or an example
  merged PR adding a comparably small driver) before drafting anything — not yet done.
- Decide whether to submit `PiFinder LX200` and `PiFinder Mount Bridge` together or as two separate,
  sequential PRs (mirrors the existing "two separate drivers" design decision — most likely two
  PRs).
- Fix #454 (broken cmake on `stellarmate-utm`) before relying on that box as the x86 dev-bench check.
- Relation to #347: a merged indi-3rdparty PR is the actual prerequisite for that issue's
  Flatpak-catalog goal — worth cross-linking once this concept has its own issue.
- No GitHub issue filed for this concept yet — open one once a direction is confirmed with the user.
