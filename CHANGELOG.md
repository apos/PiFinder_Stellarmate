# Changelog

All notable changes to this project are documented in this file. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

### Removed

- **"Software Upd" from the OLED Tools menu**: PiFinder's own update mechanism isn't compatible
  with a StellarMate-managed install (it would pull code the Stellarmate patches then have to be
  reapplied to) and could leave the install in a broken state. Removed until there's a proper
  update strategy that accounts for this (tracked as a low-priority follow-up).

### Fixed

- The Installation Summary always reported `picamera2: unknown` — it read the package's
  `__version__` attribute, which `picamera2` doesn't define. Now reads the version via
  `importlib.metadata.version()` instead.
- `pifinder_stellarmate_setup.sh` unconditionally told the user to reboot at the end of every run,
  even though the only step that actually requires one is a `/boot/config.txt` overlay change
  (Pi firmware overlays only apply at boot) — everything else (code, services, INDI drivers) is
  already restarted live. Now tracks whether `config.txt` was actually modified this run and only
  suggests a reboot when it was. The setup GUI's Reboot button follows the same signal (a new
  `###REBOOT_NEEDED###` marker) instead of showing up after every successful run regardless.

### Changed

- `pifinder_stellarmate_setup.sh` now builds and installs the PiFinder LX200 and Mount Bridge
  INDI drivers automatically (stopping any already-running instance first, then restarting the
  StellarMate Web Manager so the catalog is up to date). Previously this was a fully separate,
  manual step (`bin/build_indi_driver.sh` / `bin/build_indi_bridge.sh`) — those scripts still
  exist for rebuilding just the drivers without rerunning the whole setup.

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
