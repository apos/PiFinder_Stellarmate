# Changelog

All notable changes to this project are documented in this file. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Comprehensive IP address display**: the Web UI home page and the OLED status screen now show
  every non-loopback IPv4 address (WiFi, wired LAN, WireGuard/VPN, etc.) instead of just the one
  address the OS happens to pick for outbound traffic. Implemented via a new `Network.all_ips()`
  in `sys_utils.py` (with a `sys_utils_fake.py` stub for testing), wired through `ui/status.py`
  (OLED, reusing the existing per-row horizontal scroller for overflow) and `server.py` (Web UI).

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
