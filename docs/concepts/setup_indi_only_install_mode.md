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
| **Flatpak / Snap** | Excluded *for this purpose*: they are application-distribution formats, not a source of the `-dev` headers needed to **compile** the drivers. They could matter for a different, later problem — shipping **prebuilt driver binaries** (cf. [`indi_upstream_packaging.md`](indi_upstream_packaging.md), #464). |
| **Ansible `package` module** | The most established answer to exactly this abstraction problem, but adopting it means Python + Ansible as a new installer dependency and a move to the declarative playbook model — a bigger step than a handful of packages justifies. |
| **Nix as the unified layer** (installable beside pacman/apt on any distro, identical `nixpkgs` names everywhere) | Strategically interesting given the NixOS direction, but introduces its own bootstrap dependency. **Recorded as a later option, not adopted now.** |
| **A full OS-abstraction framework** | Rejected: the dispatch table follows the same extension pattern as Ansible's module list without taking on Ansible. |

Recommendation implemented: a small, own dispatch table (pacman/apt/nix).

## 3. Nix / NixOS

Nix gets its own section because it differs in kind from pacman/apt:

- **Imperative vs. declarative.** `os_install_packages` uses `nix profile install nixpkgs#<pkg>` — the
  *imperative* interface. On **NixOS**, the idiomatic model is the system's own *declarative*
  configuration (`configuration.nix` / flakes), where imperatively installed profile packages are
  discouraged. Which approach fits PiFinder v4 is **open**.
- **Unverified package availability.** `libindi-dev:nix` maps to `libindi` and
  `build-tools:nix` to an empty entry (nix builds normally get a C toolchain via `stdenv`; whether an
  explicit package is needed is unchecked). Neither has been checked against the real nixpkgs package
  search.
- **No test hardware** for NixOS yet.

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
- **nix: design-verified only**, same warning — and the open points of §3.
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
(upstream driver packaging) · [`indi_upstream_packaging.md`](indi_upstream_packaging.md).
