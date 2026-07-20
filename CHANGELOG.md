# Changelog

All notable changes to this project are documented in this file. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
