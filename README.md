# PiFinder on Stellarmate

*[Deutsche Version](README_de.md)*

![PiFinder mounted on a telescope under the night sky](docs/images/readme/PiFinder.jpg)

## Summary

This project installs, patches, and integrates the [PiFinder](https://www.pifinder.io/)
plate-solving push-to system into a [StellarMate](https://www.stellarmate.com/) setup, so a single
Raspberry Pi runs PiFinder's plate-solving and object-finding **alongside** StellarMate for
astrophotography, EAA, and full equipment control. The setup script automates the whole process.

**The building blocks, and why:**

- **Raspberry Pi** — the platform both PiFinder and StellarMate already target.
- **PiFinder** — a Python-based push-to solver with a **global-shutter camera** (clean plate-solves
  even while the mount is moving). Open source in both hardware and software, which is what makes
  integrating it feasible at all: the setup patches it in place instead of forking it.
- **StellarMate** — a well-maintained community project with an open-source core and a strong app
  ecosystem (StellarMate App, KStars/Ekos, INDI Web Manager) for driving a full imaging rig.
- **INDI** — the glue between the two. Both sides already speak it: PiFinder exposes its solved
  position as an INDI telescope, and the optional **Mount Bridge** couples that to any
  INDI-supported motorised mount — no mount-specific protocol, no custom code per mount.

> ### ⚠️ **Disclaimer**
>
> * This is a community project and is not officially affiliated with PiFinder or Stellarmate.
> * Use these scripts at your own risk. The author is not responsible for any damage to your hardware or software.
> * This process has been tested with the PiFinder version specified in `version.txt`.

> ### ✅ **Current Pinned Versions**
>
> * Pinned to **PiFinder 2.6.3** on **StellarMate OS 2.3.0** (Arch Linux) via `version.txt` /
>   `pifinder_stellarmate_setup.sh` — a fixed release tag, not the upstream `release` branch's moving
>   HEAD. Fully tested on Pi 4, Pi 5, and the x86 dev/simulator host —
>   [Version Compatibility](#version-compatibility) has the details.
> * **Pi 5 keyboard ⚠️** — a Geekworm X1203 UPS shield shares GPIO 16 with keypad column 0 (keys
>   7/4/1/LEFT), disabling that column. Hardware conflict between the two add-on boards, only with
>   that shield attached; a [numpad bridge](Readme_KeyboardBridge.md) sidesteps it.
> * **INDI integration** — standalone LX200 driver + optional Mount Bridge coupling, verified
>   end-to-end against a real Skywatcher EQ5 / OnStepX mount. See
>   [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md).
> * **Control Center** — installs/updates, hardware checklist, Real / Full-Simulation / Fake-Mode
>   switching, the Mount Bridge, and Reboot/Shutdown, in one local web page. See
>   [Readme_ControlCenter.md](Readme_ControlCenter.md); shipped changes in [CHANGELOG.md](CHANGELOG.md).

---

## Quick Start

**1. Browser install (recommended)**

```bash
git clone https://github.com/apos/PiFinder_Stellarmate.git
cd PiFinder_Stellarmate
bash gui_installer/launch_setup_gui.sh
```

Then open the page in a browser — on the Pi itself, or from any other device on the same network
(no desktop session on the Pi required). See [Setup GUI / Control Center](#setup-gui--control-center-recommended) for details.

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_full_page.png"><img src="docs/images/readme/cc_full_page.png" width="460"></a><br>
<sub>The Control Center, opened from any browser on the network — no desktop session on the Pi needed (Full Simulation shown)</sub>
</td>
</tr>
</table>

**2. Terminal install**

```bash
git clone https://github.com/apos/PiFinder_Stellarmate.git
cd PiFinder_Stellarmate
./pifinder_stellarmate_setup.sh
```

Full details: [Installation](#installation).

---

## Key Features & Changes

This setup modifies the stock PiFinder installation to better integrate with Stellarmate:

*   **Automated Installation:** A single script handles downloading the correct PiFinder version, creating a Python virtual environment, installing dependencies, and applying all necessary patches.
*   **INDI Integration for KStars/Ekos & SkySafari:** A standalone `PiFinder LX200` INDI driver reports PiFinder's solved position and forwards GoTo requests as push-to targets. An optional `PiFinder Mount Bridge` driver can couple that position to any real INDI mount driver (verify/alert, auto-correct on drift, or full event-driven GoTo-forwarding). Built directly against system `libindi` — no INDI source checkout, no full INDI build. Built and installed automatically by the main setup script — see [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md) for the technical reference and illustrated setup instructions (Web Manager profile, INDI Control Panel, KStars/Ekos, SkySafari).
*   **Stellarmate GPS Integration:** PiFinder is configured to use Stellarmate/KStars as its GPS source, removing the need for a separate GPS module on the PiFinder.
*   **Network Management Disabled:** All network configuration options (WiFi Mode, AP/Client switching) have been removed from the PiFinder's OLED menu and Web Interface. This prevents conflicts, as Stellarmate is responsible for all network management.
*   **Robust Patching:** Changes are applied using `diff` patches, making the process more reliable and easier to maintain than manual file edits.
*   **Compatibility:** The scripts are designed for Raspberry Pi 4 and Pi 5 running Stellarmate OS (Arch Linux). Both are fully supported — see the version banner above for the current per-Pi status.
*   **Comprehensive IP Address Display:** The web interface and the device's OLED status screen now show all available non-localhost IP addresses, providing better network visibility.
*   **Dynamic User:** The web interface authentication is patched to use the current system user (e.g., `stellarmate`) instead of a hardcoded default.
*   **Password-Protected Setup GUI:** `gui_installer/`'s webserver (destructive reinstall/update/reboot actions) now requires the same system-user password as PiFinder's own Remote login, checked via PAM — no separate password to remember.

## Hardware Requirements

### Raspberry Pi 4 *(works for basic tasks)*

| Component | Requirement |
|---|---|
| RAM | ≥ 4 GB (absolute minimum — 2 GB not possible) |
| Storage | USB 3.0 NVMe HAT (**mandatory** — SD card is not sufficient) |
| Power | Power HAT ≥ 5 A (**mandatory** — USB power is not enough) |

### Raspberry Pi 5 *(recommended)*

| Component | Requirement |
|---|---|
| RAM | > 4 GB (≥ 8 GB recommended) |
| Storage | NVMe HAT with PCIe (**mandatory** — SD card is not sufficient) |
| Power | Power HAT ≥ 5 A (**mandatory** — USB-C PD 5 A may work) |

> **Note on Camera (Pi 5):** The Pi 5 uses a **15-pin FFC CSI connector**, while Pi 4 uses 22-pin. A cable adapter is required to connect the PiFinder camera module to a Pi 5.

---

## Installation

The setup process is designed to be straightforward. It will guide you through a fresh installation or updating an existing one.

### Prerequisites

*   A Raspberry Pi 4 or Pi 5 with PiFinder hardware (hat, screen, camera, etc.).
*   Stellarmate OS 2.3.0 (Arch Linux) installed and running — the setup script warns (but proceeds) if your SMOS version differs from this tested pin.
*   Basic familiarity with the Linux command line.

### Setup Steps

1.  **Enable Hardware Interfaces:**
    SPI and I2C are enabled automatically by the setup script via `/boot/config.txt`. No manual step required on Stellarmate OS (Arch Linux). `raspi-config` is not available on this platform.

2.  **Clone the Repository:**
    Open a terminal on your Stellarmate device and clone this repository:
    ```bash
    git clone https://github.com/apos/PiFinder_Stellarmate.git
    cd PiFinder_Stellarmate
    ```

3.  **Run the Setup Script:**
    Execute the main setup script. It will detect if a PiFinder installation exists and give you options.
    ```bash
    ./pifinder_stellarmate_setup.sh
    ```

    *   **If no PiFinder is found:** The script will clone the official PiFinder repository and apply all the necessary patches.
    *   **If PiFinder is found:** You will be prompted to either:
        *   **1. Reinstall from scratch:** This will completely delete the existing PiFinder directory and perform a fresh installation.
        *   **2. Update:** This will reset your local PiFinder to this project's pinned release tag (see `version.txt`) and re-apply all patches.

4.  **Python Virtual Environment (First Run Only):**
    The first time you run the script on a fresh system, it will stop after creating a Python virtual environment (`.venv`). You must activate it manually and re-run the script to complete the installation of dependencies. The script will provide the exact commands to run, which will look like this:
    ```bash
    source /home/stellarmate/PiFinder/python/.venv/bin/activate
    ./pifinder_stellarmate_setup.sh
    ```
    After this, the installation will complete, the PiFinder services will be started, and the
    PiFinder LX200 + Mount Bridge INDI drivers will be built and installed automatically — see
    [Using the INDI Driver](#using-the-indi-driver) below for what that gives you and how to set
    up the Web Manager profile.

### Setup GUI / Control Center (recommended)

Rather than watching raw terminal output, `gui_installer/` provides a small local web page — the
**PiFinder on Stellarmate Control Center** — that runs the same setup script with a live status view
in the browser (Reinstall / Update / Reset / Uninstall as buttons, each confirming first), and then
doubles as an ongoing dashboard: the hardware checklist, Real / Full-Simulation / Fake-Mode
switching, the INDI **Mount Bridge** (Coupling presets, one-shot sync actions, guided setup), and
Reboot / Shutdown.

Full documentation — architecture, every tile, the Mount Bridge sync workflows, the API surface — is
in **[Readme_ControlCenter.md](Readme_ControlCenter.md)** ([Deutsche Version](Readme_ControlCenter_de.md)).

```bash
bash gui_installer/launch_setup_gui.sh          # start (idempotent; prints its URLs)
bash gui_installer/launch_setup_gui.sh --shutdown-webserver   # stop
```

Open `http://<pi-address>:8765` — any username, password = your `stellarmate` system password. Or
copy/symlink `PiFinder Setup.desktop` into `~/Desktop/` for a clickable icon.

> **Developing without a Pi?** [Readme_UTM_dev_X86.md](Readme_UTM_dev_X86.md) turns an x86 StellarMate
> OS image (UTM VM on a Mac) into a full control-host + simulator dev machine — the Control Center,
> the setup scripts, and the Mount Bridge coupling logic run against the **PiFinder Simulator** and
> **Injected Solve** ([Readme_PiFinder_Simulator.md](Readme_PiFinder_Simulator.md)), no hardware
> needed.

<table>
<tr>
<td align="center" width="50%">
<a href="docs/images/readme/cc_install_running.png"><img src="docs/images/readme/cc_install_running.png" width="380"></a><br>
<sub>Install or Update: a 10-step progress bar, a per-phase checklist, and the setup script's live terminal output in one tile</sub>
</td>
<td align="center" width="50%">
<a href="docs/images/readme/cc_mode_tile.png"><img src="docs/images/readme/cc_mode_tile.png" width="380"></a><br>
<sub>Simulation, Test and Power: Synthetic Solve, the direct-against-hardware checklist, and collapsible service/power actions</sub>
</td>
</tr>
<tr>
<td align="center" width="50%">
<a href="docs/images/readme/cc_mount_bridge_baseline.png"><img src="docs/images/readme/cc_mount_bridge_baseline.png" width="380"></a><br>
<sub>The PiFinder tile: OLED mirror and quick keys, the Cam/Solve/IMU/GPS badges, and the Mount Bridge connection diagram (drift, altitude, coupling)</sub>
</td>
<td align="center" width="50%">
<a href="docs/images/readme/cc_mount_bridge_coupling.png"><img src="docs/images/readme/cc_mount_bridge_coupling.png" width="380"></a><br>
<sub>The INDI Mount Bridge tile: Quick Actions, the Coupling presets, and the guided setup checklist (collapsed)</sub>
</td>
</tr>
</table>

## After Installation: PiFinder's "PFSM" Page

Once PiFinder is up, its own website (`/remote`, password `smate` by default) gets a new
**"PFSM"** nav entry (`/smos`). It's the on-device companion to the two manual steps below,
ordered by how often you actually need them:

1. **PFSM Control Center status/control** — shows whether `gui_installer/`'s webserver is
   currently running, with a Start button when it isn't, so you can relaunch it (e.g. to update
   PiFinder later) without opening a terminal. Reachable-at links for the Control Center itself
   are listed too.
2. **Web Manager setup (one-time)** — collapsed by default (it's only needed once per install);
   expand it for the same screenshot as [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md) plus
   direct links to the Web Manager for every IP this Pi has, so you don't have to hunt down the
   port (`8624`) yourself.

This page requires no login (same reasoning as PiFinder's own home page — it needs to work right
after a fresh boot) and is meant to be the first thing you check after a fresh install, an update,
or a reboot.

<p align="center">
<a href="docs/images/pfinder_lx200/webmanager_profile.png"><img src="docs/images/pfinder_lx200/webmanager_profile.png" width="380"></a><br>
<sub>Web Manager setup step (expanded): StellarMate Web Manager profile with the PiFinder LX200 and PiFinder Mount Bridge drivers running</sub>
</p>

## Using the INDI Driver

`pifinder_stellarmate_setup.sh` builds and installs both INDI drivers for you (stopping any
already-running instance first, then restarting the StellarMate Web Manager so the new/updated
drivers show up in its catalog). You only need to run the build scripts yourself when you want to
rebuild just the drivers without rerunning the whole setup (e.g. after pulling a driver-only code
change):

```bash
cd ~/PiFinder_Stellarmate
bash bin/build_indi_driver.sh     # PiFinder LX200
bash bin/build_indi_bridge.sh     # PiFinder Mount Bridge (optional, only if you have a real mount)
```

<a href="docs/images/pfinder_lx200/indi_control_panel_tabs_PiFinder_LX200_main.png"><img src="docs/images/pfinder_lx200/indi_control_panel_tabs_PiFinder_LX200_main.png" width="380"></a><br>
<sub>PiFinder LX200's own INDI Control Panel tab, connected and reporting a live solved position</sub>

For the full setup walkthrough (StellarMate Web Manager profile, INDI Control Panel, KStars/Ekos
Remote mode, SkySafari), the complete LX200 command/property reference, and an explanation of the
code and deployment strategy, see **[Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md)**.

## SMOS Updates

Stellarmate OS uses BTRFS snapshot resets to apply updates. This wipes the root partition, which removes all manually installed packages and configuration (pacman repos, systemd services, swap, etc.). The `/home` partition survives intact.

After every SMOS update, run the restore script:

```bash
bash ~/PiFinder_Stellarmate/bin/restore_after_smos_update.sh
sudo reboot
```

This restores everything PiFinder needs: pacman repos, system packages, hardware groups, udev rules, `/boot/config.txt` overlays, swapfile, and systemd services.

### Syncing basic-memory / Claude context to Nextcloud

> **This is a maintainer-specific workflow, not a general PiFinder_Stellarmate setup step.** It
> only applies if you personally use [basic-memory](https://github.com/basicmachines-co/basic-memory)
> for Claude session context and already have your own Nextcloud WebDAV remote configured — most
> users won't have either and can skip this section entirely; it has no effect on PiFinder itself.

For those who do, the post-update script can also sync that local Claude AI memory/context to
Nextcloud:

```bash
bash ~/PiFinder_Stellarmate/bin/smos-post-update.sh --sync-memory
```

> **Note:** `rclone` is installed automatically by `restore_after_smos_update.sh`. The Nextcloud remote must be pre-configured in `~/.config/rclone/rclone.conf` (remote name: `nextcloud`, WebDAV).

## Version Compatibility

The single source of truth for which PiFinder / StellarMate OS / Raspberry Pi combinations this
project has been tested against. Other docs in this repo link here rather than repeating it.

| PiFinder | SMOS | Pi 4 | Pi 5 | UTM x86 (dev / simulator) |
|---|---|---|---|---|
| 2.6.3 | 2.3.0 | ✅ fully tested | ✅ fully tested | ✅ tested — install, Control Center, Mount Bridge vs. the PiFinder Simulator (no real plate-solving; see [Readme_UTM_dev_X86.md](Readme_UTM_dev_X86.md)) |
| 2.6.0 | 2.2.1 | ✅ fully tested | ✅ GPS/Web UI/OLED confirmed, ⚠️ keyboard partially unusable with a Geekworm X1203 UPS attached (GPIO 16 conflict, see banner above) — camera adapter cable pending | — |
| 2.6.0 | 2.1.1 | ✅ tested | ⚠️ not re-verified since the OLED fix (hardware-based, so expected to carry over — see 2.2.1 row) | — |
| 2.5.1 | 2.1.1 | ✅ tested | — | — |

## Roadmap

Tracked, prioritized work — issues, test cases, next steps — lives in the
**[GitHub Project](https://github.com/users/apos/projects/15)**
([roadmap view](https://github.com/users/apos/projects/15/views/4)). Shipped changes are in
**[CHANGELOG.md](CHANGELOG.md)**. The direction:

**Version 2.x — consolidate what exists**

- Harden and test the current feature set end-to-end (Mount Bridge coupling, Full Simulation, the
  Control Center) — the bulk of this is already in `CHANGELOG.md`'s `[Unreleased]` section.
- Contribute selected changes back upstream to [PiFinder](https://github.com/brickbots/PiFinder)
  (which patches — still to be decided).
- A guiding watcher (dithering / lost-star detection during imaging) — issue already open.

**Version 3.x — integrate**

- Deeper StellarMate integration, in coordination with the SMOS project.
- Surface the essential actions directly in the PiFinder app UI instead of only a link to the
  Control Center — mainly the Quick Actions, Coupling mode, INDI setup, Multi-Point Alignment, and
  Test Hardware.
- A "real" simulator — plate-solving against the GSC catalog rather than an injected position.

## Uninstallation

A script is provided to safely remove the PiFinder installation and services.

```bash
~/PiFinder_Stellarmate/bin/uninstall_pifinder_stellarmate.sh
```

This stops and disables every systemd unit this project installs (`pifinder`, `pifinder_splash`,
`pifinder-setup`, `pifinder-fake-mode-autostart`, `pifinder-control-center`,
`pifinder-numpad-bridge`), removes the PiFinder LX200 / Mount Bridge INDI drivers (binaries and
their `drivers.xml` catalog entries), removes the `/dev/gpiomem*` udev rule, unmasks
WirePlumber/PipeWire (masked during install to stop it from grabbing the camera), removes the Pi 5
`lgpio` build artifacts, and deletes the `~/PiFinder` directory. It will not remove the
`~/PiFinder_data` directory or the `PiFinder_Stellarmate` repository itself (delete those manually
if you want them gone too — the script prints the exact command). It also leaves a few genuinely
shared pieces of system config in place on purpose (the `/boot/config.txt` SPI/I2C/overlay lines,
the `python-libcamera` pacman version pin, and the hardware group memberships added to your user) —
the script prints what those are and why, in case you want to remove them by hand too.

The Control Center's own **Uninstall** button (see
[Setup GUI / Control Center](#setup-gui--control-center-recommended) above) runs this same script
with a `--selfmove` flag instead, which additionally deletes this `~/PiFinder_Stellarmate` checkout
itself - the terminal invocation above deliberately does not, so it's safe to run from within the
repo it's uninstalling.

## See Also

*   **[Readme_ControlCenter.md](Readme_ControlCenter.md)** — full Control Center documentation: architecture, design principles, feature walkthrough, Mount Bridge & Sync workflows, API reference. ([Deutsche Version](Readme_ControlCenter_de.md))
*   **[Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md)** — the INDI layer: illustrated setup guide, LX200 command/property reference, code and deployment strategy. ([Deutsche Version](Readme_PiFinder_LX200_de.md))
*   **[Readme_KeyboardBridge.md](Readme_KeyboardBridge.md)** — the numpad-as-keypad bridge: architecture, key mapping, self-healing design. ([Deutsche Version](Readme_KeyboardBridge_de.md))
*   **[Readme_UTM_dev_X86.md](Readme_UTM_dev_X86.md)** — set up an x86 StellarMate OS VM (UTM on a Mac) as a hardware-free control-host + simulator dev machine. ([Deutsche Version](Readme_UTM_dev_X86_de.md))
*   **[Readme_PiFinder_Simulator.md](Readme_PiFinder_Simulator.md)** — the PiFinder Simulator / Injected Solve, for testing the Mount Bridge without a real mount or clear sky.
*   **[Readme_design_decisions.md](Readme_design_decisions.md)** — condensed summary of the key design decisions. ([Deutsche Version](Readme_design_decisions_de.md))
*   **[CHANGELOG.md](CHANGELOG.md)** — release history · **[GitHub Project](https://github.com/users/apos/projects/15)** — tracked roadmap.
*   **[bin/README_compile_indi.md](bin/README_compile_indi.md)** — quick build reference for the PiFinder LX200 driver.
*   **[CONTRIBUTING.md](CONTRIBUTING.md)** — submodule setup after cloning, running the shell-script test suite.
---

<p align="center">
  <img src="docs/images/logo/PiFinder-Stellarmate_Wortmarke_Positiv_fuer-hellen-hg.png" alt="PiFinder StellarMate" width="300"><br>
  © github.com/apos 2026<br>
  <em>Unofficial community project, not affiliated with StellarMate or PiFinder.</em>
</p>

<p align="center">
  <a href="https://www.youtube.com/heyapos" target="_blank" rel="noopener"><img src="docs/images/readme/HeyApos_Wortmarke_logo_thumb.png" alt="HeyApos" height="60"></a>
  &nbsp;&nbsp;
  <a href="https://avvp.de" target="_blank" rel="noopener"><img src="docs/images/readme/avvp_2019_logo_wortmarke_pos_Transparent.png" alt="AVVP" height="60"></a>
</p>
