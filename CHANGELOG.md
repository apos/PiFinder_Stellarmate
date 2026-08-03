# Changelog

All notable changes to this project are documented in this file. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Control Center: automatic recovery from #118's "PiFinder LX200" stale-connection bug. When
  `pifinder.service` restarts (deploy, crash-recovery, manual restart), the already-open TCP
  connection between the `LX200_PIFINDER` INDI driver and `pos_server.py` used to die silently -
  `CONNECTION` stayed `On` and the driver kept serving its last-known RA/Dec forever, with nothing
  surfacing the failure. A new background watchdog in `gui_installer/server.py`
  (`_pifinder_lx200_reconnect_watchdog()`) now detects the service restart (via
  `pifinder.service`'s own `ActiveEnterTimestampMonotonic`) and forces a fresh reconnect - the same
  fix already confirmed by hand via `indi_setprop`, now automatic and independent of whether the
  Control Center's web page is even open. Runs for the Control Center's whole lifetime, retrying
  every ~20s until PiFinder itself has finished restarting. An in-driver alternative (fixing this at
  the `LX200_PIFINDER` driver level directly) was attempted and found not to self-heal live; that
  approach is tracked separately for future investigation (#139).
- Control Center: the project's own logo (`docs/images/logo/PiFinder-Stellarmate_Wortmarke_Negativ_fuer-dunklen-hg.png`)
  now appears in the page footer alongside the existing HeyApos/AVVP logos, at the same height.
- Control Center: a new system load indicator (green "Normal"/red "High", next to the existing
  PiFinder-reachability row in Quick Links) - found live investigating #139 that a contended Pi
  (PiFinder's own solver worker pool, KStars, ...) can make `pos_server.py`'s LX200 socket genuinely
  unresponsive for several seconds without anything being actually broken; this at least makes that
  a visible, explained condition instead of unexplained slowness elsewhere on the page.
- `pifinder.service` now runs with `Nice=5`/`CPUWeight=50` - a coarse, PFSM-side mitigation for the
  same finding (favors the Control Center/`indiserver`/the OS itself under CPU contention, without
  capping PiFinder below full-core use whenever the CPU isn't actually contended). The more precise
  fix (capping/renicing PiFinder's own solver worker pool) is tracked upstream in #148.
- `indi_pifinder`: the LX200 driver now enables TCP keepalive on its connection to `pos_server.py`
  (a truly-dead peer is now detected within ~11s instead of relying only on read()/write() to
  eventually notice) and retries a slow (not dead) `:GR#`/`:GD#` read up to 3 times at a shorter
  2s timeout each, instead of blocking the whole polling cycle for one 5s attempt.

### Changed

- Timeout values used for the various background INDI polls (`gui_installer/indi_client.py`) are
  now named tiers (`TIMEOUT_BACKGROUND_POLL`, `TIMEOUT_FAST_POLL`, `TIMEOUT_QUICK_RETRY`, ...)
  instead of bare literals scattered across `server.py`/`indi_client.py` - no behavior change, just
  one shared place to see why a given call is timed the way it is.

- README.md/README_de.md's hero photo (`docs/images/readme/PiFinder.jpg`/`PiFinder_thumb.jpg`) replaced with a new
  real-world photo (with the project's wordmark composited in), converted from the uploaded PNG at
  `docs/images/logo/PiFinder-Stellarmate_final.png` - same file paths, so every existing reference picks it up
  automatically.

### Fixed

- The Control Center's static OLED-mirror placeholder (shown before the live `/image` probe
  succeeds) showed PiFinder's original full-color/blue splash image instead of the documented
  red-converted version matching real hardware's actual red-channel-only rendering (see
  `CHANGELOG.md`'s own `[1.3.1]` entry, which had never actually been implemented).
  `_pifinder_welcome_image_red()` (`gui_installer/server.py`) now generates and caches a red-tinted
  version (R=luminance, G=0, B=0 - the same mapping PiFinder's own `displays.py` uses for its real
  OLED) via PiFinder's own venv (has Pillow; the Control Center's system python3 doesn't),
  regenerating whenever the source is newer than the cache.

## [1.4.0] - 2026-08-02

### Added

- Reset and Uninstall are now first-class actions: menu options 4/5 in `pifinder_stellarmate_setup.sh`,
  plus matching buttons in the Control Center (`_do_reset()`/`_do_uninstall()`,
  `/reset`/`/uninstall` routes in `gui_installer/server.py`). Both stream their output live into the
  shared Terminal (Popen-based, like Install/Update/Test Hardware) instead of a single blocking
  call with a final alert box.
- The Control Center's "Solve" status now reflects a genuine, real plate-solve success/failure
  signal (`solve_source`/`last_solve_attempt`/`last_solve_success` from PiFinder's own
  `/api/status`), not just whether Solve Simulation is toggled on - a new "Solve" detail row plus
  ampel badge, separate from the existing "Solve Simulation" row/toggle.
- New "Decouple" button next to the Coupling status text - "Off" was previously only reachable via
  the raw INDI Control Panel, not from the Control Center's Mount Bridge tile.
- Stale-page detection: a new `GET /page_version` (content hash) plus a "Reload now" banner shown
  when an already-open browser tab's version no longer matches the server's - `Cache-Control:
  no-store` only protects a *new* page load, not a tab that was already open when the server
  changed underneath it.
- After a successful Install/Update/Reinstall (and the Control Center's own post-success restart),
  a one-time banner now shows that run's outcome (exit code, log) once, right after the reload -
  previously the self-restart silently discarded the visible result.
- New `GET /state` diagnostic fields exposing every mutex-guard flag
  (`mode_action_running`/`hwtest_running`/`reset_running`/`uninstall_running`) for troubleshooting
  "X is already in progress" conflicts.
- New Test Case GitHub issue template (testmanagement setup).

### Changed

- Reset/Uninstall's placement and grouping were reworked multiple times to match their actual
  scope, not their original build order: "PiFinder" (Reinstall/Update/Reset) is now separate from
  its own "PiFinder Stellarmate" group (Uninstall only, since it removes the whole checkout, not
  just the PiFinder installation).
- The Uninstall confirmation dialog now explicitly names `~/PiFinder_Stellarmate` and says
  "permanently offline, not just paused" - the previous generic wording didn't make clear that the
  repo checkout itself (not just PiFinder) gets removed.
- `bin/uninstall_pifinder_stellarmate.sh`'s stop/disable/remove loops now emit a progress line per
  unit (instead of one header per loop) and pause briefly between `systemctl stop` calls, so the
  Control Center's live output has a real chance to show more than 1-2 lines before the connection
  drops - all six units previously stopped within about a second, faster than the frontend's poll
  interval could keep up with (now tightened from 500ms to 200ms for the same reason).
- README.md/README_de.md/Readme_ControlCenter(.de).md now document the Reset/Uninstall feature,
  which had been entirely missing from all four.

### Fixed

- Adding or removing a Mount Bridge device silently wiped a remote PiFinder LX200 driver's
  configuration.
- `--reset` was silently running the full uninstall block first (missing gate on `$1`), making
  Reset functionally equivalent to Uninstall+Reset instead of just wiping the venv/build.
- The venv two-pass re-exec used a bare `$0`, breaking when the script was invoked as `bash
  pifinder_stellarmate_setup.sh` instead of `./pifinder_stellarmate_setup.sh`.
- A missing `try`/`finally` around four background-thread "is running" flags
  (`_run_hardware_test`, `_run_reset`, `_run_fake_mode_action`, the main install/update reader
  thread) meant an uncaught exception left the flag stuck `True` forever, permanently blocking
  every other mutex-guarded action with a misleading "already in progress" error.
- Uninstall's live-output connection dropped before the first poll ever landed, and separately
  before enough distinct log lines had a chance to render (see the stop-loop timing fix above).
- Uninstall triggered from the Control Center could kill its own systemd unit before ever reaching
  the code that removes `~/PiFinder_Stellarmate` itself, via two independent bugs in the
  `--selfmove` handoff path: a guard that didn't exclude `--selfmove`, and the `/tmp` copy step
  missing `functions.sh`/`os_detect.sh`, crashing under `set -u` on the unbound `pifinder_home`
  before the critical `rm -rf` calls.
- The setup script could leave the Control Center "enabled but stopped" after a non-rebooting run;
  the fix for that then over-corrected and could kill a Control-Center-driven run mid-flight via
  SIGPIPE - corrected to only auto-start when the service is both enabled *and* inactive.
- The Solve badge fix above initially read `solve_source`/`last_solve_attempt`/`last_solve_success`
  from the wrong (top-level, not nested under `solution`) JSON path, so it never actually left
  "unknown" regardless of real solve state - found live under a real night sky, re-verified after
  the fix.

## [1.3.1] - 2026-07-29

### Added

- Control Center: after a successful Install/Update run, the Control Center now restarts itself
  automatically so it serves whatever code the run just landed on. Previously only the setup
  script's own logic picked up a branch switch/self-update live (via `self_update.sh`'s existing
  re-exec) - the long-lived Control Center web server process itself (`gui_installer/server.py`)
  stayed on stale code until manually restarted or the Pi rebooted, even though the files on disk
  were already updated. The frontend shows a lock overlay ("Restarting the Control Center to load
  the new version...") for the duration, then reconnects and reloads automatically once the new
  process answers - no more silent staleness, and no confusing a deliberate restart with a crash.
  Note: a device's *first* update through this feature won't show it yet (the still-running old
  server doesn't know to restart itself) - it applies from the following update onward.
- Mount Bridge: a compact hardware status strip and the PiFinder Mode tile now distinguish "still
  starting" (pulsing yellow, within a 45s grace window) from a genuine "not detected" - PiFinder's
  multi-process design can show its live OLED UI before its own web server process is actually
  reachable yet, and a flat white "not detected" during that window read as broken.
- The static OLED-mirror placeholder (shown before the live `/image` probe succeeds) is now a
  pre-converted red version of PiFinder's own splash image, matching the warm red glow real
  hardware is always seen in, instead of the full-color/blue original.

### Changed

- **Consolidated every "still checking / result pending" indicator in the Control Center onto one
  pattern**: a forced-yellow pulsing dot (`.dot-unconfirmed`), extended to every place that
  previously used a different, uncoupled visual - a static white "checking…" dot (Mode status,
  Hardware Test rows, external Numpad/LCD rows), a dedicated one-time loading progress bar
  (`#mb-initial-load-banner`, now removed entirely), and button-text-only feedback with no dot/icon
  change (Coupling presets, Manual Sync, Link/Unlink Mount, Connect/Disconnect, external hardware
  toggles). The compact hardware ampel badges pulse in sync with their detail-row dot via the same
  mechanism. One implementation, one design rule, instead of several independently-grown ones for
  the same underlying situation.
- Mount Bridge status polling is now gated on the device's actual role (`deriveProfileRole()`) -
  only roles that use Mount Bridge poll and show "checking... (unconfirmed)"; a PiFinder-host
  device shows a calm "not used in this role" instead, and the whole diagram/caption (entirely
  derived from Mount Bridge's own state, unobtainable in this role) is hidden rather than showing a
  permanently red, misleading "not coupled" diagram.

## [1.3.0] - 2026-07-29

### Added

- `--mode=indi_only` for `pifinder_stellarmate_setup.sh` and the Control Center's Install tile
  ("INDI-only" checkbox): installs just the INDI build dependencies and the two PiFinder INDI
  drivers - no PiFinder clone/patch, no Python venv, no star catalog, no GPIO/udev setup. The
  existing `~/PiFinder` installation is never touched. For "control host" devices that couple to a
  PiFinder running elsewhere (see below). Verified end-to-end on two physical Pis.
- `bin/os_detect.sh`: package-manager abstraction (pacman/apt/nix dispatch table, pure/impure
  split, bats-tested) used by the INDI-only mode. On StellarMate, its pacman path temporarily
  disables StellarMate's own Atomic Updates protection via the official `atomic-updates.sh` toggle
  (identical `SigLevel` either way - the official path just adds a clean backup/restore cycle),
  self-heals the pacman keyring (resets after every SMOS update due to btrfs snapshot rotation),
  installs, and always relocks immediately afterward.
- Mount Bridge: **role cards** - the three setup variants (All-in-one: PiFinder hardware with
  mount / PiFinder host: PiFinder only, no mount / Control host: no PiFinder hardware, couples to
  remote PiFinder) as an explicit, prominent choice at the top of Setup checklist & diagnostics.
  Clicking a card reconfigures the selected profile to that role (confirm dialog; Control host
  asks for the PiFinder device's IP). A colored, always-visible "Role:" chip near the tile top
  states what the selected profile currently makes this device do, derived live from its actual
  driver entries. In the PiFinder-host role, everything mount-related is hidden and the device's
  own LAN IP is shown instead - exactly what the other device's Control host card asks for.
- Remote PiFinder support (INDI remote drivers): `PiFinder LX200` can now be in a profile as a
  remote entry (`label@host:port`) pointing at another device's indiserver - the split-host
  coupling from `docs/concepts/remote_indi_coupling_split_host.md`, verified live across two
  physical Pis (PiFinder host on one, Mount Bridge + mount on the other).
- `bin/build_and_install_indi_drivers.sh`: the INDI driver build/install sequence extracted out of
  the setup script's full flow, shared between full and INDI-only modes.
- Mount Bridge: a compact, always-visible hardware status strip (Camera/Solve/IMU/GPS) in the
  "PiFinder Mode, Test and Power" tile, styled like the Mount Bridge diagram's icon nodes. The
  previous always-visible Test Hardware button plus the four detailed status rows and "Optional
  external hardware" now live in a collapsed-by-default "Hardware test and details" section below
  it, so the tile leads with an at-a-glance summary instead of a wall of text.

### Changed

- The role model (a device has no role - the running profile has one) replaced two earlier,
  rejected designs along the way: a device-level role banner derived from install state, and a
  separate "PiFinder Host Setup" tile mirroring Mount Bridge state. One tile, three roles.
- Phase checklist in the Install tile is mode-aware: INDI-only runs show only their own three
  phases instead of falsely marking the full mode's ten as done.
- Mount Bridge status tile: a status-poll miss no longer blanks the diagram/coupling-mode/drift
  readout to a synthetic "off" state - it now keeps showing the last *confirmed* state, marked
  `(unconfirmed)` with a forced-yellow pulsing dot and a dimmed diagram, while only the interactive
  buttons (Link/Unlink, Connect/Disconnect, the four Coupling presets) get gated off, since those
  genuinely can't be confirmed safe to act on. Live testing showed the previous behavior (blanking
  everything on a miss) was actively misleading - the underlying coupling/correction never actually
  stops during these gaps, only the status *poll* occasionally does (see Fixed, and basic-memory
  `pifinder-stellarmate/00079`).
- Mount Bridge's drift readout now updates via its own lightweight, ungated poll every 2000ms
  (matching `indi_pifinder_mount_bridge`'s own internal `setDefaultPollingPeriod(2000)` - polling
  faster would just re-read the same unchanged value) instead of being tied to the slower, gated
  20s connection-status poll, where it could sit frozen for the length of an entire unconfirmed
  window - exactly when seeing whether an active correction is progressing matters most.

### Fixed

- Mount Bridge: changing the Threshold field while Verify/Alert or Auto-correct was already active
  silently had no effect on the driver - the field only ever reached it via a Coupling preset
  button click, even though the drift caption/badge (reading the same field) immediately looked
  like it had taken effect. The field now pushes a changed threshold to the driver live.

## [1.2.0] - 2026-07-26

### Added

- Control Center: a branch picker ("Install from") for Reinstall/Update - choose which
  `PiFinder_Stellarmate` branch (`main`/`dev`/other) a run uses, switched before self-update runs,
  with a manual refresh button and visible click feedback next to the current-branch hint.
- A "Run Again" button, replacing the earlier combined Cancel/Close-Setup flow.
- Mount Bridge: a persistent, tile-wide status line that stays visible for the entire duration of
  any in-flight action, regardless of which button triggered it.
- Mount Bridge: a "Manual: Sync mount from PiFinder" button - a one-shot sync to PiFinder's current
  solved position, works regardless of which Coupling preset (or none) is active. Covers the case
  none of the presets react to on their own: the mount being moved by hand with no Goto involved.
- Mount Bridge: a "Setup" button that runs the same profile/drivers/connect sequence Autoconnect
  triggers automatically when clicking a Coupling preset before setup is finished - without
  applying any preset at the end. Previously the only way to run that sequence was to click a
  preset and have setup start as a side effect, with no indication that would happen.

### Changed

- Install/Update flow simplified: removed the confusing Cancel button (Close Setup now shows
  directly), then removed Close Setup too since the webserver is meant to just keep running.
- Ekos-connected/not-connected wording matched to KStars' own two-step terminology (start the
  profile, then Connect Devices), later simplified further to name the active profile directly in
  both states instead of hedging on whether Ekos is using the same one.
- Coupling: split the combined Auto-correct Sync/Goto dropdown into two explicit preset buttons,
  then grouped all four presets into "Visual" vs "GoTo" categories matching how they're actually
  used, then removed the now-redundant "Coupling" label entirely.
- Mount Bridge tile reorganized into priority tiers - always-visible nighttime-observing
  essentials (diagram, drift, Coupling) vs collapsed setup/diagnostics (numbered checklist, Ekos
  status, bridge settings, log) - with the same collapsible pattern applied to Mode & Power
  (renamed to "PiFinder Mode, Test and Power", buttons regrouped by meaning) and Quick Links.
  Diagram icons enlarged and rescaled for visual consistency. Layout-shift (CLS) fixed for
  transient status banners (reserved height + opacity fade instead of popping in/out).
- Mount Bridge's setup checklist further grouped by where you'd actually go to do each step by
  hand - "INDI Web Manager" (Profile, KStars Link, Drivers) vs "Ekos / KStars" (Mount, an explicit
  Ekos-connected step, Connect) - instead of reading as a flat list where "Profile: running" could
  look like it contradicted "Ekos isn't connected yet" even though they're two independent systems.
- Goto-Forward's post-arrival check now iteratively refines instead of a single Sync: if PiFinder's
  solve after the mount finishes slewing is still outside Threshold, the mount is synced (correcting
  its model) and sent the Goto again, repeating up to 3 times before giving up and logging a warning.

### Fixed

- Branch picker preferred a stale prior selection over what's actually checked out on a fresh page
  load.
- Auto-correct (Goto & Track) repeatedly aborted the mount mid-slew: the Mount Bridge INDI driver
  re-issued a fresh Goto every 2s poll tick even while the mount was still slewing from the
  previous one, causing jerky movement and continuous "aborted" alerts/sound in KStars/SMOS.
- Control Center's "Install from: main" branch picker was silently ignored on an existing checkout
  sitting on another branch - the switch never happened, and whatever branch was already checked
  out stayed checked out regardless of the picker's selection.
- `pifinder_stellarmate_setup.sh`'s `git clone` (Reinstall) and `git reset --hard`+`git pull`
  (Update) had no exit-code check, so a failed/interrupted clone or update silently left a broken
  installation behind instead of aborting with a clear error.

## [1.1.0] - 2026-07-26

### Added

- **Mount Bridge web integration** (Control Center): folds the Mount Bridge "Coupling Dial" setup -
  previously split across the INDI Web Manager and the raw INDI Control Panel - into a single
  guided workflow in a new Mount Bridge tile, using PiFinder's own terminology ("Verify/Alert only",
  "Auto-correct on drift", "Goto-Forward") instead of raw INDI property names. Built on a new,
  minimal, framework-agnostic INDI client module (stdlib `socket`+`xml.etree` only - no
  `PyIndi`/compiled SWIG bindings), so the same module can later be ported into PiFinder's own
  bottle-based web interface with just a thin adapter layer. Highlights:
  - A numbered 1.-5. checklist (Profile / KStars Link / Drivers / Mount / Connect) with live
    done/busy indicators, each step's controls aligned to a shared column regardless of label length.
  - **Autoconnect**: clicking a Coupling preset before setup is finished drives the whole checklist
    automatically - starts the profile, adds drivers, waits for the mount link and for Ekos itself
    to connect in KStars, connects every device, then applies the chosen mode.
  - A hard gate requiring Ekos's own INDI connection (not just this tile's own connection) via a
    read-only D-Bus check (`org.kde.kstars.Ekos.indiStatus`) - a Coupling command otherwise doesn't
    reach the session actually being observed through.
  - Automatic mount-driver detection: if exactly one Telescope-family driver is present besides
    PiFinder's own two, it's auto-selected and auto-linked.
  - An icon-first connection diagram (PiFinder/Bridge/Mount), connection state shown via each icon's
    own color, with the drift readout at full size beside the Bridge icon.
  - Bridge settings/active-devices readout (host/port, which two devices are actually bridged)
    surfaced directly in the tile instead of requiring the INDI Control Panel.
  - The three Coupling presets as a large, full-width segmented control - the tile's actual central
    action - with Threshold/Correction as smaller secondary settings underneath.
  - A one-time loading indicator during initial page load, shown only until the tile's independent
    status checks have all reported at least once, not a persistent bar on later refreshes.
  - New `help.html` page, linked from every heading throughout the Control Center.
  Also fixed a real race: an internal auto-heal (restarting the profile when a device comes back
  "not currently defined") was silently dropping the Mount Bridge's own mount link as a side effect,
  since the restart respawns every driver process in the profile - now restores the link immediately
  afterward instead of relying on the next unrelated periodic poll.
  See `docs/concepts/mount_bridge_web_integration.md` and GitHub issue #38 for the full concept,
  phased plan, and design-decision history. Practical validation with a real mount over an actual
  observing session is still open, tracked in issues #42/#44/#45.
- **"Test Hardware" button (Control Center)**: runs a deeper functional check for Camera/IMU/GPS
  instead of the previous bare presence check, and classifies any failure as hardware, driver, or
  Python so it's clear at a glance whether this is a cable problem or a bug - both in the tile and
  in the shared Terminal output. Camera/IMU avoid touching the hardware directly while
  `pifinder.service` is already using it (would fight it for exclusive access, or race its own I2C
  polling) - reads its own live status and journal instead in that case, falling back to an isolated
  capture/read test only when PiFinder isn't running. GPS deliberately isn't a pass/fail test - it
  just surfaces PiFinder's own already-existing location data (lat/lon/altitude/timezone/lock).
  Also now runs automatically once on every Control Center start, not just on a manual click -
  waits for PiFinder's own web server to answer first (up to 120s) before running, since the two
  services have no startup ordering dependency between them and race independently at boot.
- **Full documentation for the Control Center and the Keyboard Bridge**: `Readme_ControlCenter.md`
  and `Readme_KeyboardBridge.md` (both with German translations), matching the depth and structure
  of the existing `Readme_PiFinder_LX200.md` — architecture diagrams, design principles, a full API
  reference, persistence/security model, known limitations, and a prioritized strategic roadmap for
  each. Intended as the canonical reference to link from GitHub issues instead of re-explaining
  either component's design from scratch every time.
- **Setup Wizard control + auto idle-shutdown**: card 3 on `/first-steps` shows whether the Setup
  GUI webserver is running and lets you start/stop it from the browser (no SSH needed) - status/stop
  via cross-origin fetches to its existing `/state`/`/shutdown` routes (now CORS-enabled), start via
  a new `POST /api/setup_gui/start` in `server.py` that spawns `launch_setup_gui.sh`. The Setup GUI
  webserver also now shuts itself down automatically after 60s of no requests at all, since it has
  no login and can trigger destructive actions.
- **"First Steps" page** (`/first-steps`, new nav link): a dedicated checklist for what to do right
  after a fresh install or a reboot, as two side-by-side cards. Card 1 lists every detected network
  address, each linking straight to the Remote page (default password `smate`) so PiFinder can be
  driven from a browser. Card 2 shows the bundled StellarMate Web Manager setup screenshot plus
  direct links to it on every detected address, with a pointer to the full
  `Readme_PiFinder_LX200.md` walkthrough for adding the PiFinder LX200 / Mount Bridge INDI drivers.
  All links open in a new tab. Lives in PiFinder's own webserver (unlike the ephemeral Setup GUI,
  it survives a reboot without needing to be manually relaunched) and needs no login, matching the
  Home page.
- **Automatic Mount Type sync**: the PiFinder Mount Bridge now reads the active INDI mount's own
  `TELESCOPE_MOUNT_TYPE` property (Alt/Az, EQ fork, or EQ GEM - every `INDI::Telescope`-derived
  driver exposes this) and pushes the matching value to PiFinder's own "Mount Type" setting via a
  new `POST /api/set_mount_type` endpoint in `server.py` (loopback-only, triggers PiFinder's
  existing `reload_config` live-reload mechanism - the same one every other web-UI setting change
  already uses). No more manually keeping PiFinder's own Alt/Az-vs-EQ setting in sync with
  whatever real mount is connected. Works independent of the bridge's coupling mode (including
  Off), only re-pushes on an actual change. Verified end-to-end against `indi_simulator_telescope`
  (both Alt/Az and EQ, live config.json update confirmed) — see basic-memory
  pifinder-stellarmate/00017.
- **Comprehensive IP address display**: the Web UI home page and the OLED status screen now show
  every non-loopback IPv4 address (WiFi, wired LAN, WireGuard/VPN, etc.) instead of just the one
  address the OS happens to pick for outbound traffic. Implemented via a new `Network.all_ips()`
  in `sys_utils.py` (with a `sys_utils_fake.py` stub for testing), wired through `ui/status.py`
  (OLED, reusing the existing per-row horizontal scroller for overflow) and `server.py` (Web UI).
- **Setup GUI** (`gui_installer/`): a small stdlib-only (`http.server`) local web page that runs
  `pifinder_stellarmate_setup.sh` with a live, auto-scrolling status view in the browser instead of
  a bare terminal, and drives the script through a new `--action=reinstall|update|cancel` flag so
  the existing-install choice and the venv-bootstrap two-pass restart are both handled without
  manual terminal input. Launch via `bash gui_installer/launch_setup_gui.sh` or the included
  `PiFinder Setup.desktop` icon. Non-interactive/terminal use of the setup script is unaffected —
  the new flag is entirely optional. Shows a 10-step progress bar and checklist driven by new
  `phase()` markers in the setup script (tracks the furthest phase reached, so the venv bootstrap's
  self-restart doesn't make progress appear to jump backwards), and offers a Reboot button once the
  run finishes successfully. Listens on all network interfaces (not just localhost) so it's also
  reachable from another device on the same LAN — there is no login, so don't expose this port
  beyond a trusted home/observatory network. The page also lists every non-loopback IP as a
  clickable link below the terminal, so it can be reopened from another device. Shows PiFinder's
  own OLED screen next to the header image - mirrors PiFinder's live `/image` endpoint once it's
  running, falling back to (and back to, if PiFinder stops responding) the static splash bitmap
  `~/PiFinder/images/welcome.png` otherwise. On success, also shows PiFinder's own web UI links
  (same IPs, whichever port - 80 or 8080 - was actually detected working) plus the default remote
  password, so there's a direct path from "setup finished" to "using PiFinder." The detection probe
  now retries indefinitely every 2s instead of giving up after one failed attempt (PiFinder can take
  a while to come back up after a restart), and doubles as the signal for a "Waiting for PiFinder to
  start…" progress indicator shown until it actually answers. A new Close Setup button (new
  `POST /shutdown` route) lets you stop the setup webserver itself once a run finishes without a
  reboot being required — if a reboot is needed, that button is shown instead, since rebooting
  takes the webserver down anyway.

- **Control Center: Fake/Real Mode switch tile**: the Setup GUI was renamed "Control Center" and
  gained a decoupled mode-status tile showing whether PiFinder is currently running for real
  (`pifinder.service`) or in a fake-hardware instance for dev/testing (`test_tools/fake_mode.sh`,
  `.claude/skills/pifinder-remote`'s `pf_remote.py`), with a one-click switch button between them.
  Status is a color dot (white/green/yellow/red) rather than emoji; Real Mode is shown degraded
  (yellow) rather than green if the camera or IMU hardware isn't actually detected, since
  `pifinder.service` can report "active" even with a crashed camera subprocess. A per-component
  hardware checklist (camera/IMU/GPS) checks each directly against the hardware
  (`rpicam-hello`/a raw I2C scan/a direct `gpsd` query), independent of what PiFinder's own software
  believes. Also added: a direct toggle for PiFinder's own "Tools → Test Mode" (`Solve Simulation`
  row, proxied via a new `POST /api/debug_solve` bridged through PiFinder's `ui_queue` - menu
  navigation via keyboard simulation was found to drop keypresses unreliably), and always-available
  "Reboot Pi"/"Shutdown Pi" buttons (a new `/poweroff` route alongside the existing conditional
  `/reboot`).
- **Hardware-free dev/test tooling** (`test_tools/`): `fake_mode.sh` toggles between the real
  systemd service and a fake-hardware instance; `keypad_gpio_matrix_test.py` is a raw GPIO
  diagnostic for the physical keypad, independent of PiFinder's own software; `fb_screen_mirror.py`
  and `fb_keyboard_bridge.py` let a small SPI display (e.g. Waveshare 3.5" LCD) and a plain
  USB/Bluetooth numpad stand in for the real OLED/keypad HAT entirely - the former mirrors
  PiFinder's `/api/screen` directly onto `/dev/fb1` (Pi 5 removed the DispmanX/`fbcp` path Waveshare's
  own instructions rely on), the latter bridges raw evdev key events to `/api/key`, replicating the
  real keypad's NumLock-aware digit/nav dual mapping, hold-to-repeat, long-press, and ALT-combo
  behavior. The Control Center's mode tile has a matching "Toggle Display" button that starts both
  together in Fake Mode, or just the screen mirror in Real Mode (a real HAT keypad needs exclusive
  GPIO the numpad bridge would otherwise compete for), and stops them automatically on every mode
  switch.
- **Self-update**: both entry points (`pifinder_stellarmate_setup.sh`,
  `gui_installer/launch_setup_gui.sh`) now `git pull` this repo itself before doing anything else, so
  a reinstall/update always runs the latest scripts/patches/GUI - not just whatever was checked out
  at initial clone time. Skips safely (not a failure) whenever the working tree isn't in a clean,
  fast-forwardable state, so in-progress local changes are never touched.
- **Waveshare LCD overlay is now reboot-toggleable from the Control Center**, instead of a fixed
  choice baked in at install time - flips the `dtoverlay`/framebuffer lines in `/boot/config.txt`
  (backed up first) and reboots. `pifinder-fake-mode-autostart.service` (new,
  `ConditionPathExists=/dev/fb1`) brings Fake Mode + the screen mirror up automatically on a boot
  where the LCD is active; `pifinder.service` itself now gets `ConditionPathExists=!/dev/fb1` so the
  two never race for the same framebuffer. The Control Center's own web UI persists across reboots
  the same way, via a new `pifinder-control-center.service` unit.
- **Numpad bridge is now its own independent, permanently-on toggle**: split out of the LCD tile
  into its own row and backed by a new `pifinder-numpad-bridge.service` (`Type=simple`,
  `Restart=always`, enabled/disabled via the Control Center's toggle button, same
  enable/disable-persists-across-reboots pattern as `pifinder-control-center.service`). Replaces the
  previous plain-`Popen`-in-the-server-process approach, which couldn't survive a reboot at all.
  `fb_keyboard_bridge.py` also self-heals across a Fake/Real Mode switch on its own now (drops its
  cached target URL on a failed send and re-probes on the next keypress) instead of needing to be
  externally stopped/restarted when the mode changes.
- **Numpad remapped to put navigation entirely off NumLock**: `NumLock` -> LEFT, `/` -> UP, `*` ->
  DOWN, `Backspace` -> RIGHT, with `0`-`9` always plain digits. Removes the previous
  NumLock-state-dependent dual mapping entirely - important for a wireless numpad, where there's no
  reliable way to see or set its NumLock LED remotely.
- **Camera process now falls back to the debug/synthetic camera instead of crashing** when no real
  camera hardware is detected (e.g. `Picamera2()` raising because nothing is physically attached).
  Previously an uncaught init failure crashed the whole camera subprocess before it ever reached the
  shared image loop, silently taking every other command on that process's queue down with it -
  including the "Solve Simulation" / Test Mode toggle, which is itself just another command on the
  same queue. A crashed process can't be toggled into debug mode; it has to already be running one
  to receive the toggle at all. This is also what Solve Simulation is actually *for* in the field
  (no camera attached), so the toggle now works in exactly the situation it exists to cover.

### Removed

- **"Software Upd" from the OLED Tools menu**: PiFinder's own update mechanism isn't compatible
  with a StellarMate-managed install (it would pull code the Stellarmate patches then have to be
  reapplied to) and could leave the install in a broken state. Removed until there's a proper
  update strategy that accounts for this (tracked as a low-priority follow-up).

### Fixed

- **Control Center login could reject a correct password**: `pam_auth.py`'s `verify_password()`
  called `pam_acct_mgmt()` after a successful `pam_authenticate()`, which always failed with a
  privilege error on this system regardless of the password - every login was silently rejected.
  Root-caused by comparing journal signatures of a deliberately-wrong password (fails cleanly at
  the `auth` phase) against real attempts (reached the `account` phase, proving the password was
  actually right). Fixed by dropping the `pam_acct_mgmt()` call; `verify_password()` now returns
  based on `pam_authenticate()` alone. Failed logins are also now rate-limited per client IP (5
  confirmed wrong-password attempts within 30 seconds locks that IP out, plus a semaphore capping
  concurrent PAM calls at 2) - a basic guard against casual brute-forcing, not a substitute for
  keeping the server off an untrusted network.
- **`pifinder.service` could crash right after a cold boot** with `PermissionError` on
  `/sys/class/pwm/pwmchip0/pwm1/enable`: exporting the PWM channel (keypad backlight) creates its
  sysfs entry root-owned, and the udev rule that makes it group-writable runs asynchronously -
  `HardwarePWM`'s own constructor already retries its `change_frequency()` call for exactly this
  race, but its `start()` call didn't. Now retries briefly there too, and `pifinder.service` itself
  gets `Restart=on-failure` as a second line of defense if a crash still slips through.
- **`launch_setup_gui.sh`'s self-update only fast-forwarded this repo's own git checkout, not the
  systemd units derived from it** - an install whose last full setup run predated a new/changed unit
  (e.g. `pifinder-control-center.service` above) failed outright with "Unit ... does not exist"
  instead of picking up the pulled code. Now syncs those three repo-owned unit files itself before
  starting.
- The Installation Summary always reported `picamera2: unknown` — it read the package's
  `__version__` attribute, which `picamera2` doesn't define. Now reads the version via
  `importlib.metadata.version()` instead.
- **Reinstall/update left stale state behind in two different ways**, both only reachable once Fake
  Mode dev/testing existed to expose them: (1) a running fake-hardware instance (no systemd unit)
  survived a reinstall's `rm -rf ~/PiFinder` unnoticed - Linux keeps already-open files/mmaps valid
  even after their directory entries are deleted, so it kept running on stale in-memory code instead
  of crashing. Now stopped explicitly before either the reinstall or update branch touches the
  directory. (2) `.claude/skills/pifinder-remote/scripts/pf_remote.py`'s own port-handling fixes
  (binds a fixed port instead of guessing across 80/8080, avoiding a collision with a real
  already-running service) lived inside that same deleted-and-recloned directory and, unlike every
  other PiFinder customization here, weren't tracked through the `diffs/*.diff` patch system - a
  reinstall silently reverted them. Now mirrored into this repo's own `src_pifinder/` and copied back
  in on every reinstall/update, the same way as `gps_stellarmate.py`/`smos.html`. Same root cause,
  same fix, for a hand-installed `evdev` (needed by `fb_keyboard_bridge.py` above) that a venv
  recreation silently dropped - added to `bin/requirements_additional.txt` so it's provisioned like
  every other extra dependency from now on.
- `pifinder_stellarmate_setup.sh` unconditionally told the user to reboot at the end of every run,
  even though the only step that actually requires one is a `/boot/config.txt` overlay change
  (Pi firmware overlays only apply at boot) — everything else (code, services, INDI drivers) is
  already restarted live. Now tracks whether `config.txt` was actually modified this run and only
  suggests a reboot when it was. The setup GUI's Reboot button follows the same signal (a new
  `###REBOOT_NEEDED###` marker) instead of showing up after every successful run regardless.
- **`keyboard_pi.py` crashed on every single keypress** once python-libinput was updated to 0.1.0:
  `KeyboardEvent.get_key()` now returns a plain `enum.Enum` (`libinput.evcodes.Key`) instead of an
  `IntEnum`, so the existing `int(key)` conversion raised `TypeError` on every event. Fixed by
  reading `.value` instead. This lived entirely inside the StellarMate-authored python-libinput
  API-migration patch itself, not in upstream PiFinder code.
- **Solve Simulation status display drifted out of sync with the real internal toggle state**, in
  two layered ways found back-to-back while testing the camera fallback above: (1) the automatic
  fallback engaged the debug camera without updating the *displayed* `debug_solve` flag, so the UI
  kept showing "off" while synthetic images were already being served; (2) after fixing that by
  setting the flag directly from the fallback path, the flag and the toggle handler's own internal
  state variable (the one that actually decides whether a canned test image gets loaded) could still
  be set independently and drift apart - e.g. clicking "off" while running on the fallback camera
  left the internal state effectively "on" underneath a UI that now said "off". Fixed by giving
  `get_image_loop()` an `initial_debug` parameter so the fallback path seeds the *same* state the
  toggle handler reads/writes, instead of poking the displayed flag separately from outside.
- The Control Center's hardware-status tile always said "camera" in its degraded-mode label, even
  when the IMU (or both) was the actual problem. Now names whichever piece of hardware is actually
  missing.
- The Setup GUI/Control Center's post-run "success" screen could show a stale StellarMate Web
  Manager restart status; fixed alongside adding an explicit warning before Reboot/Shutdown while an
  install/update run is still in progress.
- **`bin/uninstall_pifinder_stellarmate.sh` had drifted badly out of date** - it referenced a
  `pifinder_kstars_location_writer.service` that no longer gets installed by anything, while missing
  every systemd unit added since (`pifinder-setup`, `pifinder-fake-mode-autostart`,
  `pifinder-control-center`, `pifinder-numpad-bridge`), and never touched the PiFinder LX200/Mount
  Bridge INDI drivers, the `/dev/gpiomem*` udev rule, the WirePlumber/PipeWire masking, or the Pi 5
  `lgpio` build artifacts at all - all installed by `pifinder_stellarmate_setup.sh` but never
  reverted. Rewritten to cover all of it (deduplicated into shared functions so the three previously
  independently-drifting code paths - default run, `--run` after `--selfmove`, and future changes -
  can't silently diverge again the same way), and to explicitly print out what's deliberately left
  in place (`/boot/config.txt` overlay lines, the `python-libcamera` pacman pin, hardware group
  memberships) instead of silently doing nothing about them.

### Changed

- PiFinder's own `/smos` page nav entry renamed from "INDI Drivers" to "PFSM", and restructured to
  put the Control Center's own live status front and center (checked far more often day to day)
  with the one-time Web Manager setup steps collapsed into a click-to-expand section below, instead
  of the other way around.
- The Control Center now asks for confirmation before a destructive Reinstall/Update/Reboot/Shutdown
  action, instead of firing immediately on click.
- `pifinder_stellarmate_setup.sh` now builds and installs the PiFinder LX200 and Mount Bridge
  INDI drivers automatically (stopping any already-running instance first, then restarting the
  StellarMate Web Manager so the catalog is up to date). Previously this was a fully separate,
  manual step (`bin/build_indi_driver.sh` / `bin/build_indi_bridge.sh`) — those scripts still
  exist for rebuilding just the drivers without rerunning the whole setup.
- Control Center status rows now use a consistent dot-then-label-then-status layout throughout, and
  the Solve Simulation toggle moved out of the quick-links tile into the hardware-status tile,
  alongside the camera/IMU/GPS checks it's most related to. The hardware tile also now hides itself
  entirely while an install/update run is in progress, instead of showing stale/misleading status
  underneath the live log.
- `pifinder_stellarmate_setup.sh`'s smos.html now includes a Control Center screenshot alongside
  its existing setup instructions; `README.md`/`README_de.md` got a retaken, up-to-date setup
  screenshot plus the previously-missing INDI Drivers screenshots.
- **README accuracy fixes**: the "Syncing basic-memory / Claude context to Nextcloud" section now
  explicitly says this is a personal maintainer workflow (requires your own `basic-memory` setup and
  Nextcloud remote), not a general PiFinder_Stellarmate step — it previously read as if every user
  needed it. The Pi 5 compatibility banner and version table no longer claim the keyboard as fully
  working: on the test unit, a Geekworm X1203 UPS shield shares GPIO 16 with the keypad matrix's
  column 0, permanently disabling those keys (7/4/1/LEFT) — a real hardware conflict between the two
  boards, not a Pi 5 or software limitation, and specific to setups with that UPS shield attached.
  The Uninstallation section now describes everything the rewritten uninstall script actually
  covers (see Fixed, above) instead of the stale, narrower description.
- **`Readme_PiFinder_LX200.md`/`_de.md`: made the Web-Manager requirement much harder to miss.** The
  drivers only ever show up under the Web Manager's own "System INDI Drivers" catalog - Ekos has a
  completely separate driver catalog and can't see them at all, in any mode. This was previously
  only called out once, in Step 4; now repeated as its own warning box right at the top of the
  document and again inline in Step 2, both cross-linking to the full explanation. Step 2's
  screenshot also moved from an inline full-width image at the top of the section to the same
  click-to-enlarge gallery format used everywhere else in the doc, placed at the end of the section
  instead of before the instructions it illustrates. Step 5's SkySafari screenshot got the same
  treatment.

## [1.0.0] - 2026-07-16

**First tagged release.** Built and verified for **PiFinder 2.6.0** on **StellarMate OS 2.2.1**
(Arch Linux).

### Added

- **PiFinder LX200 INDI driver** (`indi_pifinder_lx200`): standalone INDI telescope driver reporting
  PiFinder's plate-solved position and forwarding GoTo requests as push-to targets to PiFinder's own
  LX200 server. Works with KStars/Ekos and SkySafari (via the stock `indi_skysafari` bridge).
- **PiFinder Mount Bridge** (`indi_pifinder_mount_bridge`): optional INDI auxiliary driver coupling
  PiFinder's position to any real INDI-supported motorized mount, speaking only generic INDI
  telescope properties (never a mount-specific protocol). Four coupling modes:
  - `Off` — no coupling.
  - `Verify/Alert only` — passively compares PiFinder vs. mount position, warns on disagreement.
  - `Auto-correct on drift` — same comparison, automatically Syncs or Goto/Tracks the mount when
    drift exceeds a configurable threshold.
  - `Goto-Forward` — event-driven: forwards a fresh PiFinder GoTo/push-to target immediately to the
    real mount, waits for the slew to finish, then verifies arrival via a fresh PiFinder solve and
    auto-corrects any residual with a Sync.
  - Plus a manual, mode-independent "Sync Now" / "Goto Now" one-shot trigger.
- **`Readme_PiFinder_LX200.md`** (also available in German as `Readme_PiFinder_LX200_de.md`): full
  documentation for the INDI/Mount-Bridge integration — illustrated setup guide (StellarMate Web
  Manager, INDI Control Panel, KStars/Ekos, SkySafari), complete LX200 command and INDI property
  reference, and an explanation of the code, deployment, and design strategy.
- This changelog.
- End-to-end verification against real hardware: a Skywatcher EQ5 with an OnStepX controller
  (`indi_lx200_OnStep` 1.27) — both Sync and GoTo forwarding confirmed with a real, visible slew.

### Changed

- Ported the PiFinder LX200 driver from the old `LX200Generic`-based fat-binary build (required a
  full `indi-source` checkout, ~13.5 MB binary, full-tree rebuild on every change) to a standalone
  build against the system `LX200Telescope` base class (no source checkout, ~80 KB binary, rebuilds
  in seconds). No longer conflicts with the `pacman`-owned `/usr/bin/indi_lx200generic`.
- Trimmed the PiFinder LX200 driver's capabilities to match what PiFinder actually has: GoTo +
  Abort only. Removed the inherited Park/Flip/tracking-rate-control/custom-alignment surface left
  over from the driver's original 10micron-mount heritage.
- The INDI driver(s) are a separate, manual build step (`bin/build_indi_driver.sh` /
  `bin/build_indi_bridge.sh`) — not part of the automated `pifinder_stellarmate_setup.sh` flow.

### Fixed

- Symlink name mismatch that prevented the (old) driver from loading under its expected name.
- 6–10 second lag on every position update, caused by `tty_read()` blocking for the full timeout
  instead of returning as soon as PiFinder's `#`-terminated LX200 response arrived; replaced with
  `tty_nread_section()`.
- A property-name collision introduced while building Goto-Forward: a custom `TARGET_EOD_COORD`
  property collided with the one `INDI::Telescope` already publishes automatically on every
  `Goto()`. Removed the redundant property; the Bridge now snoops the existing one.
- A pre-existing bug in the Mount Bridge where `ISGetProperties()` called `loadConfig()` on *every*
  client connection (including simple property queries), silently reverting the user's chosen
  Coupling mode back to the last-saved one whenever any client reconnected.

---

## Pre-1.0.0 (condensed history)

The project didn't maintain a changelog before v1.0.0. This section summarizes the major
milestones from the git history for context; see `git log` for full detail.

### PiFinder 2.6.0 / StellarMate OS 2.2.1

- Upgraded target PiFinder version to 2.6.0 (web template extension change `.tpl` → `.html`,
  `numpy-quaternion` unpinned for numpy 2.0 compatibility, patch version-gate updates).
- SMOS version pinning and compatibility checks (`smos_version_stable`) added to the setup script.
- `smos-post-update.sh` / `restore_after_smos_update.sh`: restore pacman repos, system packages,
  hardware groups, udev rules, `/boot/config.txt` overlays, swapfile, and systemd services after a
  StellarMate OS BTRFS-snapshot update (which wipes the root partition).

### Raspberry Pi 4 stability

- Fixed WirePlumber blocking the IMX296 camera (masked PipeWire/WirePlumber for camera stability).
- Fixed a WDS catalog out-of-memory kill via `os.nice()`, batch size, and yield-time tuning.
- Smart power-management sleep state machine (WARMUP → SLEEP → RETRY → SOLVED).
- Fixed GPS time being off by the local UTC offset (`datetime.now()` → `datetime.now(timezone.utc)`).
- Fixed a `numpy` 2.0 incompatibility in the bundled Tetra3 solver (`np.math.factorial` →
  `math.factorial`).

### Raspberry Pi 5 (partial support)

- `rpi-lgpio` support and a `uart3`/SPI0 overlay conflict fix (GPIO9 conflict on RP1).
- GPS and Web UI confirmed working.
- OLED display: not yet working — under investigation (SPI driver difference between Pi 5's
  `spi_dw_mmio` and Pi 4's `spi_bcm2835`).
- Camera requires a 15-pin FFC CSI adapter cable (Pi 5 uses a different connector than Pi 4).

### StellarMate-specific integration

- PiFinder configured to use StellarMate/KStars as its GPS and time source instead of a dedicated
  GPS module.
- Network configuration UI (WiFi mode, AP/Client switching) removed from PiFinder's own OLED menu
  and web interface — StellarMate owns all network management.
- Web interface IP display and authentication patched for StellarMate's dynamic user setup.
