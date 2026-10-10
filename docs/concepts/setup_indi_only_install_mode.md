# Concept: INDI-only install mode, one shared setup codebase

> **Status: implemented** (`--mode=indi_only`, released in v1.3.0). Tracked as
> [GitHub issue #61](https://github.com/apos/PiFinder_Stellarmate/issues/61) (closed). Serves
> [#60](https://github.com/apos/PiFinder_Stellarmate/issues/60) (PiFinder as a separate device, Mount
> Bridge on a remote Control host) as its primary motivation; sibling concept for the test side:
> [#62](https://github.com/apos/PiFinder_Stellarmate/issues/62).
>
> **Provenance:** the original of this document lived on the since-deleted branch
> `concept/remote-mount-bridge-and-setup-refactor` and never reached `main`/`dev`. This file is a
> **reconstruction** (2026-10-06) from the surviving sources: the issue #61 text and its two comments,
> the basic-memory note `pifinder-stellarmate/00076`, the commit messages of the implementing PRs
> (`f2d3eb1`, `228cfb0`, `4ecae05`, `b6b69b4`, `96f18e2`) and the header comments of
> `bin/os_detect.sh`. Where the original's exact wording or numbering is lost, this says so.

## 1. Overview

A new install mode, `--mode=indi_only`, for **both** entry points — `pifinder_stellarmate_setup.sh`
and the Control Center's Install tile (the "What is this device?" choice, formerly an "INDI-only"
checkbox). It installs only what a **Control host** needs:

- the INDI build dependencies (`cmake`, build tools, `libindi-dev`, `git`),
- the PiFinder INDI drivers (`PiFinder LX200`, `PiFinder Mount Bridge`, `PiFinder Simulator`),
- optionally the Control Center (the `indi_only` code path itself only installs packages and drivers; the
  Control Center is what launches it in the GUI case).

It skips everything PiFinder-hardware- or application-specific: the PiFinder clone/patch, the Python
venv, the star catalog, GPIO/udev setup and PiFinder's own systemd services. An existing `~/PiFinder`
is never touched.

**Why hardware/udev/GPIO is simply irrelevant here** (corrected after feedback on 2026-07-26): the
first draft framed this as "StellarMate-specific, must be ported per OS". That was wrong. In this
scenario **no PiFinder hardware is attached to the device at all**, so there is nothing to port — on
*any* OS. No boot-config work is needed either. Only two things remain, and both are OS-independent
in intent: compile the INDI drivers, and (optionally) run the Control Center.

### Target scenario

PiFinder is a standalone device; a **separate, more powerful machine** — StellarMate (Pi 5 or x86
StellarMateX), Astroberry, stock Ubuntu + KStars/Ekos — runs imaging and the mount and couples to the
PiFinder over the network via INDI's own remote-driver mechanism (see #60). The preference that shaped
this concept: **one shared setup codebase**, explicitly *not* a second installer to maintain.

## 2. Design decisions

### 2.1 One codebase, a mode flag

A `--mode=full|indi_only` flag next to the existing `--action=` / `--branch=` flags (default `full`,
behavior unchanged). The `indi_only` branch is self-contained and **exits before any `full`-mode code
runs**, so the already-tested full flow cannot regress. The alternative considered and rejected was a
separate installer for the Control-host case.

To avoid duplicating the driver build between the two modes, it was extracted into
`bin/build_and_install_indi_drivers.sh`, called by both. `build_indi_driver.sh` /
`build_indi_bridge.sh` themselves call no package manager (they assume `cmake` and `libindi` exist) and
needed no change.

### 2.2 Portability finding: the web app is already portable

`gui_installer/*.py` has **zero** PiFinder-specific or third-party imports (stdlib only). The
portability work therefore concerns **only the installer scripts**, not the Control Center web app.

### 2.3 A narrow package-manager abstraction — not an OS framework

Needed so the mode also runs on Astroberry / stock Debian / Ubuntu / NixOS, not just StellarMate (Arch).
Implemented as `bin/os_detect.sh`:

- **pacman, apt and Nix are planned from the start** — not apt-first with Arch bolted on afterwards.
  Arch/pacman remains the only path testable *today*, but the abstraction must not be
  Debian-centric by construction.
- **Nix is a real, near target, not speculation**: PiFinder v4 is to be NixOS-based (project owner's
  statement). See §3.
- A small **dispatch table** keyed by `generic-name:manager` (`os_package_name`), extensible by adding a
  row — and, for a genuinely new manager, a `case` in `os_install_packages`. The package *set* stays
  deliberately small (only what INDI-only mode needs).
- **Selection priority** `pacman > apt > nix` (`os_pick_package_manager`): a machine with several
  available (e.g. Nix on top of an apt distro) prefers its OS-native manager.
- **Pure/impure split**, driven by the test-suite concept (#62): pure decision functions
  (`os_pick_package_manager`, `os_package_name`, `os_pacman_atomic_updates_enabled`) have no
  filesystem/command access and are bats-tested regardless of the host; impure ones
  (`os_detect_package_manager`, `os_install_packages`, `os_pacman_*`) gather real facts or have real
  side effects and stay live-tested.

### 2.4 Not chosen, and why

| Option | Verdict |
|---|---|
| **Flatpak / Snap** | Excluded *for this purpose*: they are application-distribution formats, not a source of the `-dev` headers needed to **compile** the drivers. They could matter for a different, later problem — shipping **prebuilt driver binaries** (cf. [`indi_upstream_packaging.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/indi_upstream_packaging.md), #464). |
| **Ansible `package` module** | The most established answer to exactly this abstraction problem, but adopting it means Python + Ansible as a new installer dependency and a move to the declarative playbook model — a bigger step than a handful of packages justifies. |
| **Nix as the unified layer** (installable beside pacman/apt on any distro, identical `nixpkgs` names everywhere) | Strategically interesting given the NixOS direction, but introduces its own bootstrap dependency. **Recorded as a later option, not adopted now.** |
| **A full OS-abstraction framework** | Rejected: the dispatch table follows the same extension pattern as Ansible's module list without taking on Ansible. |

Recommendation implemented: a small, own dispatch table (pacman/apt/nix).

## 3. Nix / NixOS

Nix gets its own section because it differs in kind from pacman/apt — and because looking it up
against the real nixpkgs (2026-10-06) showed that the first, research-only dispatch table was **wrong
for Nix**. PiFinder v4 is to be NixOS-based, so this is a real target, not a speculative one.

### 3.1 What nixpkgs actually provides (verified against `NixOS/nixpkgs` master, 2026-10-06)

| Attribute | What it is |
|---|---|
| **`indilib`** | The INDI core library + `indiserver` (version **2.2.4.2** at lookup time; `pkgs/development/libraries/science/astronomy/indilib/default.nix`). `nativeBuildInputs = [ cmake pkg-config ]`; a single default output — no separate `dev` output, headers and libraries land in the same `$out`. |
| `indi-3rdparty` | An attribute *set*, one derivation per 3rd-party driver. |
| `indi-with-drivers` | `buildEnv` over `indilib` + a list of driver packages (`extraDrivers`); when drivers are given it wraps `indiserver` with `INDIPREFIX` set to the environment's `$out`, so `indiserver` finds exactly those drivers. |
| `indi-full` / `indi-full-nonfree` | `indi-with-drivers` with *all* free (resp. also non-free) 3rd-party drivers. |

**Consequence — a bug in the original table:** `os_package_name libindi-dev nix` maps to `libindi`, and
**no attribute `libindi` exists** in nixpkgs (neither in `all-packages.nix` nor as an alias). The correct
attribute is **`indilib`**; `nix profile install nixpkgs#libindi` would fail. (Fixed in `bin/os_detect.sh`
and covered by a test in `bin/tests/test_os_detect.bats`.) The other generic names are fine:
`cmake` and `git` exist under the same names; `build-tools` stays empty (see 3.3).

### 3.2 Imperative vs. declarative — what each means for this installer

| | Imperative (`nix profile install`, what `os_install_packages` does today) | Declarative NixOS (`configuration.nix` / flake) |
|---|---|---|
| Mental model | Mutates a user profile, like apt/pacman | The whole system, including `environment.systemPackages` and services, is a function of the config |
| Fit on NixOS | Works, but is the discouraged way to install system software there | The idiomatic way |
| Fit for a one-shot installer script | Natural: the script *does* something | Awkward: a script must not edit the user's NixOS configuration on its own |
| Compiling a driver | Needs `cmake`, `pkg-config`, `indilib` visible to the build — a plain profile install does **not** put `indilib` on `CMAKE_PREFIX_PATH` | A dev shell (`nix-shell` / `nix develop` with `mkShell`) sets this up through Nix's setup hooks |

So even "install the build dependencies, then run the existing build script" does not transfer 1:1:
the dependencies must be made visible to the build **inside a Nix environment**, not merely installed.

### 3.3 Toolchain

On NixOS a C/C++ toolchain comes from `stdenv` inside builds and dev shells (`mkShell` includes it);
there is no `build-essential`/`base-devel` equivalent to install system-wide. That is why
`build-tools:nix` is an **empty** entry — still unverified whether any explicit package is needed on a
bare `nix profile` (outside a dev shell) and, in particular, whether `gcc` would then have to be added.

### 3.4 The bigger problem: where the drivers end up

The existing driver build installs by **copying into the FHS** — `sudo cp … /usr/bin/indi_pifinder_lx200`
and a `sed -i` into `/usr/share/indi/drivers.xml` (`bin/build_indi_driver.sh`). On NixOS `/usr/bin` and
`/usr/share` are not a mutable, conventional prefix (NixOS keeps software in the immutable `/nix/store`;
general knowledge, not checked on a NixOS machine here). So on NixOS the build-script install step cannot
simply be reused. Two coherent routes:

1. **A Nix package for the drivers** — a derivation that builds the PiFinder LX200 / Mount Bridge /
   Simulator drivers against `indilib` and installs binary + driver XML into its `$out`, consumed through
   `indi-with-drivers.override { extraDrivers = [ … ]; }`. This is the NixOS-native result: the
   environment's `indiserver` wrapper (`INDIPREFIX`) then finds the drivers by construction, with no
   `/usr` edits and no `sudo`. It is a **declarative** install and belongs in the user's configuration
   (or a flake this project ships), not in an imperative script.
2. **Upstream the drivers** to INDI's `indi-3rdparty` ([#464](https://github.com/apos/PiFinder_Stellarmate/issues/464),
   [concept](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/indi_upstream_packaging.md)).
   nixpkgs' own `indi-full` is built from its `indi-3rdparty` set, so upstream drivers *could* reach NixOS
   users via nixpkgs — but only after nixpkgs's own `indi-3rdparty` expression picks them up, which is a
   separate step this project does not control.

Route 1 changes what "INDI-only install mode" means on Nix: not "a script that installs and builds", but
"a Nix expression/flake that provides the drivers". The same split — *package-manager abstraction for
apt/pacman, a different delivery mechanism for Nix* — is likely the honest design; forcing Nix through the
imperative path would fight the platform.

### 3.5 Open decisions and next steps

- ~~Fix the table~~ — done: `libindi-dev:nix` → `indilib` in `os_package_name`, with a unit test.
- **Decide the Nix delivery model:** imperative dev-shell around the existing scripts (works on any
  distro with Nix installed, but doesn't solve `/usr/bin` on NixOS) vs. a declarative driver package /
  flake (the NixOS-native answer, new artefact to maintain). Needs a real NixOS machine — none is
  available yet.
- **Whether PiFinder v4's NixOS image already ships INDI** and how its PiFinder-side software is packaged
  is **unknown** to this project; that decides whether the PiFinder-host side ([#37](https://github.com/apos/PiFinder_Stellarmate/issues/37),
  [#401](https://github.com/apos/PiFinder_Stellarmate/issues/401)) is a Nix package, a flake, or a `configuration.nix` snippet.
- **Nix as the unified layer** (the option recorded in §2.4) becomes more attractive precisely because of
  the NixOS direction — the decision in §2.4 (later, not now) should be revisited once PiFinder v4's
  packaging is known.

## 4. pacman specifics on StellarMate

On stock StellarMate, direct pacman access to `core`/`extra`/`alarm` — where `cmake`, `git`,
`libindi`, `base-devel` live — is blocked by design (StellarMate's **Atomic Updates** protection; only
its own `[smos]` repo stays reachable). The pacman path therefore:

1. checks whether StellarMate's tooling exists (`/etc/stellarmate/atomic-updates.sh`) and whether the
   protection is enabled (`/etc/stellarmate/.root-access-state`: absent ⇒ enabled, matching that
   script's own default);
2. if so, **temporarily disables** it via StellarMate's **official script** (the required `YES`
   confirmation is piped on purpose — asking interactively on every install would be the per-run
   nagging this mode exists to avoid);
3. runs `pacman-key --init` / `--populate` (the same remedy as StellarMate's factory-reset tooling;
   a no-op on a healthy keyring) and installs;
4. **always re-locks** right afterwards, success or failure.

**Why the official toggle instead of blocking or a homegrown `pacman.conf` edit** (decided 2026-07-28):
the first version refused and pointed at the manual command — overly cautious. StellarMate's own
`--disable` uses the identical `SigLevel = Optional TrustAll` for `core`/`extra`/`alarm` that a manual
edit would, so there is **no signature-verification difference** either way (StellarMate's own
choice). The real gain is a clean, StellarMate-tracked backup/restore cycle instead of a permanent,
untracked edit. Verified live: system restored to its exact prior locked state, no residue.

On plain Arch or any non-StellarMate distro the script is absent and this dance is skipped.

## 5. Implementation map

| Piece | Where |
|---|---|
| Mode flag, indi-only branch (exits before full-mode code), summary | `pifinder_stellarmate_setup.sh` (`--mode=`; `if [ "$MODE" = "indi_only" ]`) |
| Package-manager abstraction | `bin/os_detect.sh` |
| Shared driver build/install (+ Web Manager restart) | `bin/build_and_install_indi_drivers.sh` |
| GUI side: "What is this device?" choice, `mode=` query param on `/start`, `_start_run()` appends `--mode=` only when non-default | `gui_installer/server.py`, `gui_installer/help.html` (§ INDI-only) |
| Tests (pure functions only) | `bin/tests/test_os_detect.bats` (`run_all.sh`) |
| Pi-hardware-free machines (x86 Control host / simulator): `get_hw_model()` returns `""`, `config.txt` section skipped, hardware-gated patches generalised | `bin/functions.sh`, setup script, `bin/patch_PiFinder_installation_files.sh` (commit `96f18e2`) |

The scripts refer to this document's requirements as **R1–R3**; the original numbering is lost with the
original. By the commit history: **R1** = the `--mode=indi_only` flag, script and GUI side; **R2** = the
package-manager abstraction (`os_detect.sh`); **R3** is not identifiable from the surviving sources.

## 6. Verification status

- **pacman: live-verified end-to-end** on real StellarMate hardware (Pi 5): both drivers built and
  installed, Web Manager restarted, exit 0; Atomic Updates restored exactly. Later confirmed on two
  physical Pis as the install path for the Control host role (#60).
- **apt: design-verified only.** Implemented from the research in #37's draft howto and the
  remote-coupling concept; not run on real Debian/Ubuntu/Astroberry hardware. `os_install_packages`
  prints a "not yet live-verified" warning when it takes this path.
- **nix: design-verified only**, same warning — and the open points of §3, the package name is corrected to `indilib`, but nothing has run on NixOS.
- Unit tests cover the pure decision functions only; real package installs stay live-tested.

## 7. Known risks / open points

- **No Astroberry / Ubuntu / NixOS test hardware** — package names and repos are researched, not
  verified. This is the main reason the apt and nix paths carry the warning.
- **Nix packaging model** (imperative profile vs. declarative NixOS config) and the nixpkgs names for
  `libindi` and the toolchain — see §3.
- **The Control Center and `gui_installer/` still assume StellarMate's Web Manager** (REST on `:8624`,
  KStars/Ekos D-Bus). The installer abstraction in this document does **not** solve that; it is the
  subject of [#400](https://github.com/apos/PiFinder_Stellarmate/issues/400) (Control host on
  Astroberry / stock KStars-Ekos).
- **The PiFinder-host side is out of scope here.** A stock PiFinder (Debian-based, no StellarMate)
  still needs the drivers built and an `indiserver` hosting them, plus the `pos_server.py` safety patch:
  see [#37](https://github.com/apos/PiFinder_Stellarmate/issues/37) and
  [#401](https://github.com/apos/PiFinder_Stellarmate/issues/401). Whether a future NixOS-based
  PiFinder v4 changes that picture is open.
- INDI has no authentication; exposing the LX200 driver on the LAN is acceptable in a home/observatory
  network but should be documented, not silently assumed (carried over from the sibling
  remote-coupling concept).

## 8. Related

#60 (remote coupling, motivation) · #62 (test suite) · #37 (stock-Debian PiFinder howto) · #400 /
#401 / #416 (non-StellarMate Control host, stock-PiFinder safety patch, PiFinder-host role) · #464
(upstream driver packaging) · [`indi_upstream_packaging.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/indi_upstream_packaging.md).
