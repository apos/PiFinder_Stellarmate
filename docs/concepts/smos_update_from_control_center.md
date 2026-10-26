# Guarded SMOS Update from the Control Center — Concept

> **Status: concept — Phase 0 (read-only state script) implemented, Phases 1–3 not started.**
> No tracking issue yet. Decision of the maintainer (2026-10-26): the SMOS update should be started
> from a Control Center button instead of the SMOS app, because it is the only way to rule out an
> unguarded reboot.
>
> Builds on what already exists and does **not** replace it: the post-update notice + restore button
> (#552, [Readme_ControlCenter.md](../../Readme_ControlCenter.md)), the guard unit for a wiped
> Control Center (`bin/smos_update_guard.py`), `restore_after_smos_update.sh` and the pre-reboot hook
> `smos-pre-reboot-fix.service` (#561, #566). Those react *after* an update somebody else started;
> this concept lets the Control Center run the update itself, in a fixed order, with a check in
> front of the reboot. Companion: [first_time_setup_wizard.md](first_time_setup_wizard.md) (the
> "returning user" case, §1) and [setup_indi_only_install_mode.md](setup_indi_only_install_mode.md).

## 1. Basic Functionality (Overview)

### 1.1 The problem

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

### 1.2 What SMOS itself offers (verified 2026-10-26, SMOS 2.4.0, UTM)

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

### 1.3 What is not known yet

These must be answered on a real delta update (UTM first, then the Pi 4) before Phase 2 is built;
this document does not guess them:

- Does `delta/apply` only *stage* the new system, or does it also reboot by itself?
- Which `state` values does `delta/status` report, and what exactly does `pending_reboot` mean?
- Which route does the app use to reboot afterwards, and does it end in `systemctl reboot` (so the
  hook runs)? `POST /api/system/reboot` exists; its implementation is not readable (the updater is
  obfuscated).
- The body of `delta/rollback`, and whether a rollback needs its own reboot gate.
- How stable the routes are across SMOS versions (the Web Manager is closed source).

## 2. Goals and non-goals

**Goals**

1. A SMOS update can be started from the Control Center, and **the reboot is never offered before a
   check of the staged system passed** (§4.4).
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

## 3. State recorded before and after (Phase 0, implemented)

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

## 4. The guarded flow (Phases 1–3)

### 4.1 Preflight (read-only, blocks fail-closed)

Before *Update* is enabled: take a snapshot (§3) and check

| Check | Blocks when |
|---|---|
| `delta/status` | `state` is not idle, or `pending_reboot` is already true |
| free space on `/` | below the size SMOS reports (`size_mb` of `delta/check`) plus margin |
| boot layout | root label is `SM_ROOT_NVM`/`SM_ROOT_NVE` and the hook is not installed and enabled |
| role | a mount is connected and tracking, or Ekos has a running capture session (warn first, user decides) |
| rescue path | NVMe/USB-booted Pi without SD card: warn, user must acknowledge (the card is the only way back) |
| API | the update routes are missing from `/openapi.json` (feature detection, §6) |

### 4.2 Start

The user picks *check*, sees the changelog and size (from `delta/check` and `delta/changelogs`), confirms
in a dialog, and the Control Center calls `POST /api/software/delta/apply` (or, for a package-level
upgrade, `GET /api/software/upgrade` with the update type that `upgradable` listed). Never both, never
without the dialog, never from a poller. The calls go to `127.0.0.1:8624` only.

### 4.3 Watch

The existing run machinery (terminal pane, progress bar) polls `delta/status` or `software/progress` and
shows them. If the Control Center restarts or the system goes away, the guard unit and the snapshot on
disk carry the state (§4.6).

### 4.4 The gate in front of the reboot (delta update only)

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

### 4.5 After the reboot

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

### 4.6 Failure matrix

| Fails at | State of the system | What happens |
|---|---|---|
| Preflight | untouched | the button stays off, the reason is shown |
| `delta/apply` or while watching | possibly a half-staged system, the running one untouched | show the SMOS message, offer `delta/status`, `delta/cleanup`, `delta/rollback`; never reboot |
| Gate (§4.4) red | staged system not trustworthy, running one untouched | no reboot button; roll back or leave |
| Reboot does not come up | depends on the gate | fallback entry (UTM/Pi: previous system) or SD/adapter procedure, as before |
| Restore fails after the reboot | new root, PFSM missing | the guard page stays, shows the log, and keeps the *Run post-update restore* button |
| Control Center restarts mid-run | unchanged | the marker file and the snapshot on disk say where the run stood |

### 4.7 Software upgrade (package level)

Simpler: no new root, no reboot gate. After it, take a snapshot, `compare`, and re-check the things that
depend on versions (`indi-firmware` and `udevmanager` take effect at the next boot; a new KStars Flatpak
changes the D-Bus API the Control Center uses and the `userdb.sqlite` it reads — see §5).

## 5. Risks

- **The update API is unauthenticated and the upgrade route is a GET.** Any host on the LAN can start a
  upgrade by opening a URL. That is SMOS's design, not PFSM's; the Control Center only calls it on
  `127.0.0.1` and behind its own PAM login. Worth telling the SMOS maintainers.
- **Closed source.** The updater and Web Manager are obfuscated; behaviour can change with any SMOS
  release. The Control Center must detect the routes it needs (§6) and fall back to "start the update in the
  SMOS app, PFSM will check afterwards" when they are missing.
- **KStars changes with every upgrade** (3.8.4 → 3.8.5 on 2026-10-26). The Control Center talks to
  `org.kde.kstars.Ekos` over D-Bus and reads `userdb.sqlite`. The after-update report should name the KStars
  version and re-run the *KStars Link* step.
- **Two update paths.** A user who also updates in the SMOS app is covered only by the hook and the
  notice card; that is accepted.

## 6. Interface and UI

- A card **SMOS update** in the *Install or Update* tile: *up to date* / *update available (type, size,
  changelog)* / *running* / *ready to reboot (checks passed)* / *blocked (reason)*. Buttons *Check*,
  *Update* (confirm), *Reboot now* (confirm, only when green), *Roll back*.
- The existing yellow card *SMOS was updated* stays for updates started elsewhere.
- Feature detection: the card is shown only if `GET /openapi.json` of the Web Manager lists the routes of
  §1.2; otherwise it says that the update is done in the SMOS app and offers the state script.
- Control Center endpoints (all behind the existing PAM check): `GET /api/smos_update/check`,
  `POST /api/smos_update/start`, `GET /api/smos_update/status`, `POST /api/smos_update/reboot`. None of
  them forwards an arbitrary path to the Web Manager.

## 7. Test plan

1. **Phase 0 (done on the UTM):** snapshot twice, compare; synthetic good/bad cases.
2. **Phase 0 on the Pi 4:** the same, read-only, once the script reaches the device through the normal
   update (no hand copy). Records the real `cmdline.txt`/`fstab` labels (`SM_ROOT_NVM`).
3. **UTM, real delta update** (a snapshot of the VM exists): needs a delta update to be offered. Answers the
   questions in §1.3, with the Control Center only watching.
4. **Pi 4 with a working SD card,** `BOOT_ORDER=0x614` (USB first, so the SD does *not* catch a failed
   NVMe boot by itself: unplug the USB adapter): update from the app first, with the Phase-0 comparison
   around it; only then Phase 2 from the Control Center.
5. Acceptance: no reboot offered while the gate is red; restore runs unattended; the report shows no
   boot-critical change; `compare` exits 0.

A delta update is only offered when SMOS publishes one (the releases so far are bi-monthly; 2.4.0 came on
5 October 2026). Without one, a test needs `delta/rollback` to 2.3.0 followed by `delta/apply`; the hook is not
installed on 2.3.0, so the setup update must run there first.

## 8. Phases

| Phase | Content | State |
|---|---|---|
| 0 | `bin/smos_update_state.py snapshot/compare` | implemented |
| 1 | Preflight and the gate as a read-only report in the Control Center (after an update started in the app, tells whether the staged system looks bootable) | not started |
| 2 | *Update* and *Reboot now* buttons, the guarded flow of §4.2–4.4 | not started, blocked on §1.3 |
| 3 | Unattended restore and the after-update report (§4.5) | not started |

## 9. Open questions

1. §1.3, all of it.
2. Where the marker file lives so that the guard sees it after a root reset (`/home/stellarmate/PiFinder_Stellarmate`, like
   `.smos_version_restored`, is the obvious place).
3. Whether `POST /api/system/reboot` or `systemctl reboot` is the right reboot; the hook only helps for the latter.
4. Whether the update type of a software upgrade may be chosen by the user or always "all".
