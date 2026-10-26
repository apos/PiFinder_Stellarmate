# PFSM Lifecycle: install, update, upgrade, post-update and quality checks — Concept

> **Status: concept.** Phase 0 of the SMOS-update part (the read-only state script) is implemented; everything else
> here describes **what exists today** (verified against the code on 2026-10-26) and **what is missing**. No tracking
> issue yet. Decision of the maintainer (2026-10-26): the SMOS update should be started from a Control Center
> button, and the many threads of the setup (installation, update, upgrade, post-update, the PiFinder patch system,
> versioning, Python requirements, checks after an installation) need **one place where they come together**.
>
> **How to read this document.** Chapters 1–6 are the *map and contract* of the lifecycle: what each stage does, which
> file owns it, what must be true afterwards, how that is checked. Chapter 7 is the detailed concept for the one
> stage that is new: running the SMOS update from the Control Center. Chapters 8–10 are the rules for where
> documentation lives, the phases and the open questions. What is *verified* and what is a *proposal* is marked.
>
> Companions: [setup_indi_only_install_mode.md](setup_indi_only_install_mode.md) (the `--mode=indi_only` path, implemented),
> [setup_script_test_suite.md](setup_script_test_suite.md) (the bats suite, partly implemented),
> [first_time_setup_wizard.md](first_time_setup_wizard.md) (the "returning user" case), the post-update notice and restore
> (#552, [Readme_ControlCenter.md](../../Readme_ControlCenter.md)), and the pre-reboot hook (#561, #566).

## 1. Basic Functionality (Overview)

PFSM is installed on top of an existing StellarMate OS (SMOS) by **one script**,
`pifinder_stellarmate_setup.sh` (about 1300 lines, nine phases), which the Control Center runs through its
Install-or-Update tile and which can also be run by hand. Around it sit:

- a **patch system** that turns the stock PiFinder release into the PFSM variant (30 diff files in `diffs/`, applied
  by `bin/patch_PiFinder_installation_files.sh`, plus two patches applied to packages inside the Python venv);
- **pins** for the versions PFSM is tested against (PiFinder, SMOS, a few system and Python packages);
- **post-SMOS-update** machinery (`bin/restore_after_smos_update.sh`, `bin/smos-post-update.sh`, the pre-reboot hook,
  the guard unit, the notice card);
- **tests**: a small bats suite for pure logic, a loop-device test for the post-update script, and live tests on the devices.

The problem this concept addresses is not that one of these is broken. It is that **no single document says how they
fit together**, and the facts are spread over this repository and about twenty notes of the maintainer's notebook.
Two examples of what that costs, both found while writing this chapter:

- The PiFinder pin is set in the setup script, **written to `version.txt` by that same script on every run**, and
  then **read back from `version.txt` by the patch script** to decide which diffs apply. `version.txt` is therefore an
  output *and* an input; nothing in the repository says so outside code comments.
- The three post-checkout copy lists (files from `src_pifinder/` into the PiFinder checkout) appear **three times** in
  the setup script (fresh install, reinstall, update). Adding a file in one place and not the others is easy.

## 2. The lifecycle stages (verified 2026-10-26)

| Stage | Entry point | Does | Verified result today |
|---|---|---|---|
| **S0 Prepare** | `bin/self_update.sh`, `bin/switch_branch.sh`, top of the setup script | updates the PFSM checkout itself, optionally switches branch (`--branch`), reads the pins, checks the SMOS version through the Web Manager API (`/api/info/version`) | informational only: a newer PiFinder upstream or a different SMOS version warns but never blocks; a scripted run proceeds, a terminal run asks |
| **S1 Install / reinstall / update PiFinder** | phase "Cloning or updating PiFinder" | `--action=reinstall` deletes and re-clones the pinned tag; `--action=update` fetches tags, `git reset --hard`, checks out the pinned tag; `--action=reset`/`uninstall` hand over to `bin/uninstall_pifinder_stellarmate.sh` | aborts on a failed clone or fetch and on a checkout without `version.txt`; `--mode=indi_only` skips the whole PiFinder part |
| **S2 Patch** | `bin/patch_PiFinder_installation_files.sh`, then patches after `pip` | see chapter 4 | a failed hunk becomes a "CRITICAL WARNING", the run continues |
| **S3 System packages and Python** | phases "Installing system packages", "Creating Python venv", "Installing Python requirements" | pacman packages (with SMOS's Atomic Updates protection unlocked and relocked), swapfile, venv, `pip install -r requirements.txt`, then the pins of chapter 5 | the venv is rebuilt if the system Python changed (typical after a SMOS update) |
| **S4 Hardware, services, drivers** | phases "Setting up hardware access", "Configuring hardware & services", "Building INDI drivers" | groups (`spi gpio i2c kmem input`), udev rule, `config.txt` overlays per Pi model, systemd units, the post-update guard and hook, the three INDI drivers | a missing group aborts the run; `config.txt` change sets `###REBOOT_NEEDED###` |
| **S5 SMOS update and post-update** | `bin/restore_after_smos_update.sh`, `bin/smos-post-update.sh`, `bin/smos_update_guard.py`, the notice card | restores what a new SMOS root wipes, then runs the S1–S4 update path again | recorded in `.smos_version_restored` only after a **clean** run; chapter 7 |
| **S6 Quality check** | end of the setup script | prints a summary of versions and the collected warnings, probes the Control Center on port 8777 | **there is no functional check** (chapter 6) |
| **S7 Reset / uninstall** | `bin/uninstall_pifinder_stellarmate.sh` (also `--reset`, `--selfmove`) | removes units, drivers, `~/PiFinder` (and, for uninstall, the PFSM checkout) | — |

Every stage reports through the same channel: `###PHASE###` markers drive the Control Center's progress bar,
`add_warning()` collects problems into `.setup_warnings`, and the run ends with a CRITICAL-WARNINGS block. A run with
warnings does **not** count as restored against the current SMOS version, so the post-update notice stays until a clean
run.

## 3. Versioning and compatibility

**Where each fact lives today.**

| Fact | Source | Used by | Maintained |
|---|---|---|---|
| PiFinder version that is installed | `pifinder_stellarmate_version_stable` (setup script) | clone/checkout tag; written to `version.txt` | by hand, on a bump |
| PiFinder version "actually tested" | `pifinder_stellarmate_version_testing` (2.6.1) | **nothing**: defined, not read by any script (checked with `grep`) | by hand, stale in practice |
| SMOS version tested against | `smos_version_stable` (2.4.0) | the SMOS check at the start | by hand |
| the older SMOS version | `smos_version_testing` (2.3.0) | **nothing**: defined, not read by any script | by hand, stale in practice |
| PiFinder version seen by the patch script | `version.txt` (written by the setup script) | `should_apply_patch` per diff | generated |
| Which combinations were tested on which Pi | the table in `README.md#version-compatibility` | readers | by hand |
| Pinned packages | see chapter 5 | the setup script | by hand, in code and comments |

Each diff is applied only if three conditions match: the PiFinder version, the Pi model (`P4`, `P5`) and the OS
(`should_apply_patch`; `general` means "any"). A new PiFinder release therefore needs, in this order: the pin bumped,
the diffs checked against the new files (a failing hunk is reported, not hidden), the matrix updated after a real test
on the devices. **This order is not written down anywhere as a procedure** — it is spread over comments and notes.

**Proposal (not built).** One manifest file in the repository (`versions.env` or similar) holding the pins; the setup
script, the patch script, the README matrix check and the self-check of chapter 8 read it; `version.txt` is then a
copy for compatibility. This removes the input/output ambiguity and makes "what do we test against" one file.

## 4. The PiFinder patch system

Two layers, both reported through `add_warning()`:

1. **Diffs against the PiFinder checkout** — `diffs/*.diff` (30 files), applied by
   `bin/patch_PiFinder_installation_files.sh` through `apply_patch_or_warn()` (28 calls). Each is guarded by the
   version/Pi/OS match. After `patch -N`, a leftover `.rej` file makes the failure visible as a CRITICAL WARNING instead of
   staying silent (this was added after two unnoticed hunk failures in 2026-07).
2. **Patches inside the venv after `pip install`** — `skyfield` (`starlib.py` for numpy 2, `keplerlib.py` for batch comet
   propagation) and `picamera2` (`drm_preview.py`, `pykms` is not available on Arch). Each patch is skipped when its
   marker is already present, and reported when it fails.

Files that are *copied* instead of patched (`gps_stellarmate.py`, `smos.html`, images, the `pifinder-remote` skill) come
from `src_pifinder/`.

The invariant is: **a clean run means every patch applied or was already applied**; anything else is a warning that
stops the SMOS version from being recorded. The weak point is drift against upstream: patches are tied to a PiFinder
version and, for the venv, to a package version (hence the `picamera2==0.3.37` pin below).

## 5. Python and package requirements

| What | How it is pinned or handled | Why |
|---|---|---|
| PiFinder's `requirements.txt` | installed with `pip` (`nice`/`ionice`, `CXX=g++ CC=gcc`) | the CXX override works around a build-farm path in Arch ARM's Python |
| `bin/requirements_additional.txt` | `aiohttp picamera2 RPi.GPIO spidev aiofiles evdev`, merged in by the patch script | PFSM's own additions, so a venv rebuild keeps them |
| `picamera2` | `pip install picamera2==0.3.37` after the requirements | the `drm_preview.py` diff matches this version |
| `skyfield` | pinned to 1.50 in PiFinder's requirements; two defensive patches | the batch-comet bug appeared in 1.51 |
| `python-libinput` | 0.1.0, built from source with a `sed` patch for the removed `imp` module | not installable otherwise on Python 3.12+ |
| `python-libcamera` | 0.7.0 from `packages/` (aarch64 only), `IgnorePkg` in `pacman.conf` | newer libcamera uses pybind11 `smart_holder`, which breaks `picamera2` from pip; skipped on x86 |
| Pi 5 GPIO | `lgpio` and `rpi-lgpio` from `packages/`, real `RPi.GPIO` removed first | whichever installs last wins on disk; the order made the OLED dark once |
| venv | deleted and rebuilt if the venv Python differs from the system Python | typical after a SMOS update |
| Hipparcos catalog | three download URLs, then a bundled `src_pifinder/astro_data/hip_main.dat.gz` | the download source is not reliable |

## 6. What is missing (verified gaps)

1. **No functional check after installation or update.** The run ends with a summary of versions, the warnings, and a
   probe whether the Control Center answers. Nothing asks the questions that matter: does `pifinder.service` run, does
   PiFinder's own API answer, are the three INDI drivers in the catalog and loadable, are all patches applied, do the
   venv packages import, does the hardware answer (on a Pi)? The Control Center's "Test Hardware" does part of this, but only on
   demand and only for the hardware. This is the largest gap; chapter 8 proposes the check.
2. **The post-checkout copy lists exist three times** (fresh install, reinstall, update) in the setup script.
3. **The version pins have no single source**, and two of them (`*_testing`) are dead variables (chapter 3).
4. **The update path for a new PiFinder version is not written down as a procedure** (chapter 3).
5. **Documentation is spread** over this repository and a maintainer notebook with no entry point (chapter 9).
6. **SMOS updates started outside PFSM are only reacted to** (the notice card, the hook); chapter 7 closes this for updates
   started from the Control Center.

## 7. SMOS update from the Control Center

Detailed concept for stage S5. The material below was written first and is kept as it stands, renumbered.

### 7.1 Overview of the SMOS update problem

#### 7.1.1 The problem

A SMOS update started in the SMOS Tools app runs without any knowledge of PFSM. Two things went
wrong or can go wrong:

1. **An unbootable device.** SMOS 2.3.0 → 2.4.0 rewrote the boot configuration of a Pi 4 that boots
   from NVMe to `root=LABEL=SM_ROOT`; the disk is labelled `SM_ROOT_NVM`, so the device never booted
   again (#561). The hook `smos-pre-reboot-fix.service` now corrects the staged system at shutdown, but it
   only helps if the update ends in a reboot that goes through `systemctl reboot`. Nobody has seen it
   work on a real device yet.
2. **A manual, easily forgotten restore.** After a system-image update the root is new: Control Center
   unit, INDI drivers, hardware groups, `gh`, `rclone` and WireGuard are gone. A yellow card offers
   *Run post-update restore*, but somebody has to click it, and the order *update → reboot →
   restore* is left to the user.

#### 7.1.2 What SMOS itself offers (verified 2026-10-26, SMOS 2.4.0, UTM)

The Web Manager (`stellarmatewebmanager`, port 8624, no login, listens on all interfaces) carries the
update API — the same one the Tools app uses. Its OpenAPI document (`/openapi.json`) shows two
**different** mechanisms:

| | Software upgrade | Delta update |
|---|---|---|
| Check | `GET /api/software/upgradable` | `GET /api/software/delta/check` |
| Start | `GET /api/software/upgrade[?update_type=…]` | `POST /api/software/delta/apply` `{"target_version": "…"}` |
| Progress | `GET /api/software/progress` | `GET /api/software/delta/status` (`state`, `pending_reboot`, `previous_version`) |
| Other | `GET /api/software/release` (stable/beta), `/release/progress` | `/delta/changelogs`, `/delta/subvolumes`, `POST /delta/rollback`, `POST /delta/cleanup` |
| Effect | SMOS packages (`smos` repo) and the KStars Flatpak change **in the running system** | a new `@system-X.Y.Z` subvolume (plus `@snapshot-…`); reboot into it |

Observed: the update run from the app on 2026-10-26 was a *software upgrade* (`stellarmateupdater`,
`stellarmateudevmanager`, `indi-firmware`, KStars 3.8.4 → 3.8.5); no new subvolume, the root stayed,
nothing of PFSM was lost. Only a *delta update* replaces the root. `GET /api/software/upgrade` is a
GET with a side effect: it **starts** an upgrade. Everything read-only is listed in
`bin/smos_update_state.py` (`API_READS`); nothing else may be called from a status script.

#### 7.1.3 What is not known yet

These must be answered on a real delta update (UTM first, then the Pi 4) before Phases 3 and 4 of chapter 10 are built;
this document does not guess them:

- Does `delta/apply` only *stage* the new system, or does it also reboot by itself?
- Which `state` values does `delta/status` report, and what exactly does `pending_reboot` mean?
- Which route does the app use to reboot afterwards, and does it end in `systemctl reboot` (so the
  hook runs)? `POST /api/system/reboot` exists; its implementation is not readable (the updater is
  obfuscated).
- The body of `delta/rollback`, and whether a rollback needs its own reboot gate.
- How stable the routes are across SMOS versions (the Web Manager is closed source).

### 7.2 Goals and non-goals

**Goals**

1. A SMOS update can be started from the Control Center, and **the reboot is never offered before a
   check of the staged system passed** (§7.4.4).
2. After the reboot the restore runs by itself and the result is compared with the state before.
3. One read-only tool records the state before and after and says what changed, whoever started the
   update (the Control Center or the app). This is Phase 0 and exists.
4. The existing hook and notice card stay as the second line of defence for updates started
   elsewhere.

**Non-goals**

- No reboot without a confirmation of the user, ever.
- No change to what SMOS does inside an update, no use of SMOS internals beyond the documented routes.
- No attempt to repair a device that does not boot (that stays the SD-card / adapter procedure of
  `bin/smos-post-update.sh`).
- The SMOS app keeps working; nothing here forbids using it.

### 7.3 State recorded before and after (Phase 0, implemented)

`bin/smos_update_state.py` (stdlib only):

```
smos_update_state.py snapshot [--out FILE]    JSON under ~/.cache/pifinder_stellarmate/smos_update_state/
smos_update_state.py compare A.json B.json    what changed; exit 1 if something boot-critical changed
smos_update_state.py latest                   path of the newest snapshot
```

The snapshot lives in `/home`, so a root reset does not remove it. It records the SMOS version, the
running kernel, `/proc/cmdline` (split into `root`, `rootflags`, …), the `LABEL=` lines of `fstab`,
the label of the root device, the Pi `cmdline.txt` or the systemd-boot entries, the btrfs
subvolumes, free space, the versions of the packages that matter, the KStars Flatpak version, the
state of the relevant units, the PFSM git head and `.smos_version_restored`, and the answers of the
six read-only API routes.

`compare` sorts differences into three groups:

- **Boot-critical** (`cmdline.root`, `fstab.labels`, `root_device.label`, `boot_entries.labels`): an
  update must not change these by itself. A change returns exit code 1.
- **Expected after a system-image update** (`cmdline.rootflags`, `cmdline.initrd`, the new version):
  the new `subvol=`.
- **Other**, listed without judgement.

Tested on the UTM: two snapshots in a row differ in nothing; edited copies that imitate a good delta
update and the 2.4.0 Pi 4 failure (`root=LABEL=SM_ROOT`, labels in `fstab`) are classified as
expected and as boot-critical. These are *synthetic* cases; the script has not seen a real delta
update or a Pi 4 yet.

### 7.4 The guarded flow (Phases 3 and 4 of chapter 10)

#### 7.4.1 Preflight (read-only, blocks fail-closed)

Before *Update* is enabled: take a snapshot (§7.3) and check

| Check | Blocks when |
|---|---|
| `delta/status` | `state` is not idle, or `pending_reboot` is already true |
| free space on `/` | below the size SMOS reports (`size_mb` of `delta/check`) plus margin |
| boot layout | root label is `SM_ROOT_NVM`/`SM_ROOT_NVE` and the hook is not installed and enabled |
| role | a mount is connected and tracking, or Ekos has a running capture session (warn first, user decides) |
| rescue path | NVMe/USB-booted Pi without SD card: warn, user must acknowledge (the card is the only way back) |
| API | the update routes are missing from `/openapi.json` (feature detection, §7.6) |

#### 7.4.2 Start

The user picks *check*, sees the changelog and size (from `delta/check` and `delta/changelogs`), confirms
in a dialog, and the Control Center calls `POST /api/software/delta/apply` (or, for a package-level
upgrade, `GET /api/software/upgrade` with the update type that `upgradable` listed). Never both, never
without the dialog, never from a poller. The calls go to `127.0.0.1:8624` only.

#### 7.4.3 Watch

The existing run machinery (terminal pane, progress bar) polls `delta/status` or `software/progress` and
shows them. If the Control Center restarts or the system goes away, the guard unit and the snapshot on
disk carry the state (§7.4.6).

#### 7.4.4 The gate in front of the reboot (delta update only)

When the update is staged (`pending_reboot`), the Control Center runs
`bin/smos-post-update.sh --pre-reboot` itself, the same code the hook runs — idempotent, so the hook
at shutdown finds nothing left to do — and then **verifies the staged system** instead of trusting it:

1. the new `@system-X` subvolume exists and holds `linux` and `initrd`;
2. the boot configuration that will be used (Pi `cmdline.txt`, or the systemd-boot entry of the new
   version) names the right root: no `LABEL=` that the root disk does not carry, a `subvol=` that points
   at the new subvolume;
3. `fstab` of the staged system has the same property;
4. the previous system stays bootable as a fallback (`@system-<old>` and its entry still present).

All green → the button **Reboot now** appears (confirmation dialog, then `systemctl reboot`, so the hook
is the second layer). Any red → no reboot button, the reason is shown, and the options are *check again*,
*roll back* (`delta/rollback`), or *leave it* (the running system is untouched until a reboot).

#### 7.4.5 After the reboot

The guard unit (a user unit in `/home`, it survives the root reset) takes the page while the Control Center
is gone. If the update was started by the Control Center (a marker file records the target version),
it runs the restore **by itself** instead of waiting for the button; for an update started elsewhere
the yellow card stays as today. Then:

1. `restore_after_smos_update.sh` (which ends in the setup's non-interactive update);
2. device-specific repairs that a new root removes: WireGuard unit, `tsc=reliable` on the UTM
   (`bin/utm_fix_utm_apple_silicon_host_pause_issues.sh`), the display drop-in on a VM (since #575 part
   of the restore);
3. a second snapshot, `compare` with the first, and a one-page report: version, what changed, what is
   boot-critical, what the Control Center repaired.

#### 7.4.6 Failure matrix

| Fails at | State of the system | What happens |
|---|---|---|
| Preflight | untouched | the button stays off, the reason is shown |
| `delta/apply` or while watching | possibly a half-staged system, the running one untouched | show the SMOS message, offer `delta/status`, `delta/cleanup`, `delta/rollback`; never reboot |
| Gate (§7.4.4) red | staged system not trustworthy, running one untouched | no reboot button; roll back or leave |
| Reboot does not come up | depends on the gate | fallback entry (UTM/Pi: previous system) or SD/adapter procedure, as before |
| Restore fails after the reboot | new root, PFSM missing | the guard page stays, shows the log, and keeps the *Run post-update restore* button |
| Control Center restarts mid-run | unchanged | the marker file and the snapshot on disk say where the run stood |

#### 7.4.7 Software upgrade (package level)

Simpler: no new root, no reboot gate. After it, take a snapshot, `compare`, and re-check the things that
depend on versions (`indi-firmware` and `udevmanager` take effect at the next boot; a new KStars Flatpak
changes the D-Bus API the Control Center uses and the `userdb.sqlite` it reads — see §7.5).

### 7.5 Risks

- **The update API is unauthenticated and the upgrade route is a GET.** Any host on the LAN can start a
  upgrade by opening a URL. That is SMOS's design, not PFSM's; the Control Center only calls it on
  `127.0.0.1` and behind its own PAM login. Worth telling the SMOS maintainers.
- **Closed source.** The updater and Web Manager are obfuscated; behaviour can change with any SMOS
  release. The Control Center must detect the routes it needs (§7.6) and fall back to "start the update in the
  SMOS app, PFSM will check afterwards" when they are missing.
- **KStars changes with every upgrade** (3.8.4 → 3.8.5 on 2026-10-26). The Control Center talks to
  `org.kde.kstars.Ekos` over D-Bus and reads `userdb.sqlite`. The after-update report should name the KStars
  version and re-run the *KStars Link* step.
- **Two update paths.** A user who also updates in the SMOS app is covered only by the hook and the
  notice card; that is accepted.

### 7.6 Interface and UI

- A card **SMOS update** in the *Install or Update* tile: *up to date* / *update available (type, size,
  changelog)* / *running* / *ready to reboot (checks passed)* / *blocked (reason)*. Buttons *Check*,
  *Update* (confirm), *Reboot now* (confirm, only when green), *Roll back*.
- The existing yellow card *SMOS was updated* stays for updates started elsewhere.
- Feature detection: the card is shown only if `GET /openapi.json` of the Web Manager lists the routes of
  §7.1.2; otherwise it says that the update is done in the SMOS app and offers the state script.
- Control Center endpoints (all behind the existing PAM check): `GET /api/smos_update/check`,
  `POST /api/smos_update/start`, `GET /api/smos_update/status`, `POST /api/smos_update/reboot`. None of
  them forwards an arbitrary path to the Web Manager.

### 7.7 Test plan

1. **Phase 0 (done on the UTM):** snapshot twice, compare; synthetic good/bad cases.
2. **Phase 0 on the Pi 4:** the same, read-only, once the script reaches the device through the normal
   update (no hand copy). Records the real `cmdline.txt`/`fstab` labels (`SM_ROOT_NVM`).
3. **UTM, real delta update** (a snapshot of the VM exists): needs a delta update to be offered. Answers the
   questions in §7.1.3, with the Control Center only watching.
4. **Pi 4 with a working SD card,** `BOOT_ORDER=0x614` (USB first, so the SD does *not* catch a failed
   NVMe boot by itself: unplug the USB adapter): update from the app first, with the Phase-0 comparison
   around it; only then the Control Center flow (Phase 4 of chapter 10).
5. Acceptance: no reboot offered while the gate is red; restore runs unattended; the report shows no
   boot-critical change; `compare` exits 0.

A delta update is only offered when SMOS publishes one (the releases so far are bi-monthly; 2.4.0 came on
5 October 2026). Without one, a test needs `delta/rollback` to 2.3.0 followed by `delta/apply`; the hook is not
installed on 2.3.0, so the setup update must run there first.

## 8. A common quality check after every stage (proposal)

One script in the repository, say `bin/pfsm_selfcheck.sh`, run by **the end of the setup script, the end of the restore
and a Control Center button**, so that "the functionality is ensured" is something executed and not only described.
Checks, each with *ok / warning / failed* and a one-line reason (read-only, no side effects):

| Area | Check |
|---|---|
| Services | `pifinder`, `pifinder-control-center` active; `smos-pre-reboot-fix` enabled on NVMe/USB-booted Pis |
| Control Center | `/state` answers on 8777 |
| PiFinder | its own API answers (`/api/status`); on a Pi: the hardware status of camera, IMU, GPS (read, not Test Hardware's captures) |
| INDI | the three drivers are in the catalog and their binaries exist; the Web Manager answers on 8624; the selected profile contains the PiFinder drivers (read through the Web Manager's API, not by changing it) |
| Patches | no `*.rej` files in the PiFinder checkout; the markers of the venv patches are present |
| Versions | PiFinder tag matches the pin; SMOS version against the tested pin (warning only); the pinned packages of chapter 5 match |
| Update state | `.smos_version_restored` equals the running SMOS version |

Output: human lines plus a JSON file next to the snapshots of `bin/smos_update_state.py`, exit code 0/1 by "any failed". The
setup keeps its CRITICAL-WARNINGS logic; the self-check adds what that logic cannot see. Phase 1 of chapter 10.

## 9. Where documentation lives (rule)

**One home for every fact; everything else links.** The split follows audience and lifetime, not topic:

| Place | Holds | Why |
|---|---|---|
| **This repository** (`docs/concepts/`, the readmes, the code and its comments, the tests) | the *contract*: stages, invariants, who owns what, how it is checked; the user-visible procedure (README "SMOS Updates", the Control Center) | reviewed together with the code, readable without the maintainer's notebook, changes slowly |
| **The maintainer's notebook** (`basic-memory`) | the *runbook and history*: step-by-step operating procedure per device, test campaigns, incident notes, session start-ups, decisions in progress; **one entry note** ("lifecycle map") that lists every stage with its Git owner and its notes | fast-moving, device-specific, not for users |
| **The code** | the self-check (chapter 8), the version manifest (chapter 3), the tests | a document can drift, an executed check cannot |

Anything a **user** needs in order to update safely (what to run, what to expect, what to do when it fails) belongs in the
README and the Control Center, never only in the notebook.

## 10. Phases and open questions

| Phase | Content | State |
|---|---|---|
| 0 | `bin/smos_update_state.py snapshot/compare` (chapter 7.3) | implemented |
| 1 | the self-check of chapter 8, run at the end of setup and restore, with a Control Center button | not started |
| 2 | one manifest for the version pins (chapter 3); one copy list instead of three (chapter 6) | not started |
| 3 | the Control Center's guarded SMOS update (chapter 7): preflight and gate as a read-only report first | not started, blocked on §7.1.3 |
| 4 | the guarded update with *Update* and *Reboot now* buttons and an unattended restore | not started |

Open questions:

1. The unknowns of §7.1.3 (what `delta/apply` does, which states it reports, whether the reboot route runs the hook).
2. Whether the self-check should also run from the post-update guard page when the Control Center is gone.
3. Who owns the "new PiFinder version" procedure: a short checklist in this repository (proposal) or only in the notebook.
4. Whether `version.txt` can be dropped once a manifest exists (the patch script and `src_pifinder/pifinder_setup.sh` read it today).
5. Where the marker file for a Control-Center-started update lives so that the guard sees it after a root reset
   (`/home/stellarmate/PiFinder_Stellarmate`, like `.smos_version_restored`, is the obvious place).
6. Whether `POST /api/system/reboot` or `systemctl reboot` is the right reboot for the guarded update; the hook only helps for the latter.
7. Whether the update type of a software upgrade may be chosen by the user or is always "all".
