# PiFinder Stellarmate Control Center Documentation

*[Deutsche Version](Readme_ControlCenter_de.md)*

> ### ✅ Built & verified against
>
> * Pure Python **stdlib** (`http.server`) backend — no framework, no external web dependency
> * Live-tested end-to-end: fresh install, reinstall, update, reboot-persistence, Fake/Real Mode
>   switching, all hardware toggles
> * No PiFinder-version-specific code — talks to PiFinder only through its stable `/api/*` Remote
>   API. For the tested PiFinder / StellarMate OS / Pi combinations, see the
>   [Version Compatibility table in README.md](README.md#version-compatibility).

This document covers the **PiFinder Stellarmate Control Center** (`gui_installer/`) — the local web
application that installs, updates, monitors, and controls this project's PiFinder integration. It
started as a thin wrapper around the setup script's terminal output and grew into this project's
primary operational surface. Companion to the main [README.md](README.md), which covers the base
PiFinder-on-StellarMate installation this tool manages, and to
[Readme_KeyboardBridge.md](Readme_KeyboardBridge.md), whose toggle button lives here.

---

## Table of Contents

1. [Basic Functionality (Overview)](#basic-functionality-overview)
2. [Design Principles](#design-principles)
3. [Status Badges & Colours](#status-badges--colours)
4. [Architecture](#architecture)
5. [Feature Walkthrough](#feature-walkthrough)
6. [Installation & Illustrated Guide](#installation--illustrated-guide)
7. [Mount Bridge & Sync Workflows](#mount-bridge--sync-workflows)
8. [Technical Reference: API Surface](#technical-reference-api-surface)
9. [Persistence & Process Model](#persistence--process-model)
10. [Authentication & Security Model](#authentication--security-model)
11. [Known Limitations & Troubleshooting](#known-limitations--troubleshooting)
12. [Development & Testing](#development--testing)
13. [Roadmap](#roadmap)
14. [Version Compatibility](#version-compatibility)

---

## Basic Functionality (Overview)

The Control Center exists because a StellarMate-managed PiFinder install has operational needs a
plain terminal session doesn't serve well: watching a long install run from a phone while standing
at the telescope, switching between a hardware-free "Fake Mode" and the real service for
development, checking whether the camera/IMU/GPS are actually detected independent of what
PiFinder's own software believes, and rebooting/shutting down the Pi without SSH.

It runs as a small, dependency-free Python web server (`gui_installer/server.py` +
`gui_installer/status_page.html`) reachable at `http://<pi-address>:8765`, deliberately kept **stdlib
only** — its job includes bootstrapping the very venv/pip environment PiFinder itself needs, so it
cannot depend on anything that environment would provide.

```mermaid
flowchart TB
    subgraph Browser
        UI["status_page.html<br/>(polls every 1-2s)"]
    end
    subgraph "Pi (port 8765)"
        Server["server.py<br/>(http.server, stdlib only)"]
        Setup["pifinder_stellarmate_setup.sh<br/>(subprocess, streamed)"]
        FakeMode["test_tools/fake_mode.sh"]
    end
    subgraph "System"
        Systemd["systemd units<br/>(pifinder, pifinder-control-center,<br/>pifinder-numpad-bridge, ...)"]
        HW["Raw hardware checks<br/>(rpicam-hello, I2C scan, gpsd query)"]
        PF["PiFinder's own API<br/>(:80/:8080 real, :8081 fake)"]
    end
    UI <--> Server
    Server --> Setup
    Server --> FakeMode
    Server --> Systemd
    Server --> HW
    Server -.proxy.-> PF
```

---

## Design Principles

Established and enforced over multiple UI-polish rounds this project went through — a global
principle this project's UI now follows:

1. **One consistent status-row pattern everywhere.** Every status line is `<dot> Label: status`, in
   that order, with no exceptions — an inconsistency here (one row reading `status <dot>` instead)
   was flagged and fixed specifically because it broke this rule.
2. **Traffic-light semantics, not emoji.** Four states — white (unknown/checking), green (fully
   functional), yellow (running but degraded, e.g. hardware missing), red (failed/not running) — as
   a colored dot, not an emoji, so the same visual language reads correctly regardless of font/OS
   emoji rendering.
3. **Verify against real, independent state — never trust "the process is alive."** `pifinder.service`
   can report `systemctl is-active` = true even with a fully crashed camera subprocess (a known
   PiFinder architecture quirk, see [Feature Walkthrough](#hardware-checklist)). Every status check
   in this tool that matters for a "is this actually usable" answer checks the real, underlying
   signal (raw hardware probes, actual HTTP reachability with response verification, settle-checked
   process state) rather than a single process-alive bit.
4. **Confirm before anything destructive or hard to reverse.** Reinstall, Update, Reboot, and
   Shutdown all require an explicit confirmation dialog — and that dialog gets *more* insistent
   (stronger wording) if another run is already in progress, rather than firing immediately on
   click.
5. **Context-aware labels over generic ones.** "PiFinder is running, but not functional" always
   names *which* hardware is missing (camera, IMU, or both) rather than a fixed, potentially
   misleading generic label.

---

## Status Badges & Colours

### The colour language

Every indicator on the page — the icon badges in the PiFinder tile, the dots on status lines, the
Mount Bridge diagram — uses the same four states:

| | Meaning |
|---|---|
| ⚪ **white / neutral** | Unknown — not checked yet, or the check couldn't reach its target. Pulses faintly while a check is in flight. |
| 🟢 **green** | Confirmed good / working. |
| 🟡 **yellow** | Running, but degraded or not fully there — hardware missing, no GPS fix yet, a value past its threshold. |
| 🔴 **red** | Failed, not running, or a value outside a safe range. |

Colours always come from a real, independent check (a hardware probe, an HTTP response actually
verified, a settle-checked process state), never from "the process is alive" — see
[Design Principles](#design-principles). The
[Mount Bridge & Sync Workflows](#mount-bridge--sync-workflows) section shows the badge row in
context.

### PiFinder tile — the badge row

`Cam` / `Solve` / `IMU` / `GPS` mirror the **Hardware test and details** checklist rows exactly (see
[Feature Walkthrough → Hardware Checklist](#hardware-checklist)) — the badge and its detail row
always agree.

**`Cam`** — is a camera detected and actually usable? (`rpicam-hello --list-cameras`, run through
PiFinder's own venv)

| | State | Meaning |
|---|---|---|
| ⚪ | `checking…` / `unknown (…)` | The test hasn't run yet this session, or the probe tool isn't available on this host (e.g. no `rpicam-hello` on x86). |
| 🟢 | `functional` | A real capture succeeded. |
| 🔴 | `not detected` / `error (…)` | No camera found, or the capture/driver failed (the detail row names which). A crashed camera subprocess shows here even while `pifinder.service` still reports "active". |

**`Solve`** — is PiFinder's plate-solver currently producing a position? (from PiFinder's own
`solve_source`; independent of Solve Simulation, which only substitutes test images)

| | State | Meaning |
|---|---|---|
| ⚪ | `unknown` | No data from PiFinder yet. |
| 🟢 | `solving` | The camera is currently solving successfully (no age limit — this is a different question from Mount Bridge's own "fresh enough to correct from" check, its 5 s Solve Freshness setting). |
| 🟡 | `no fresh solve yet – estimating from IMU` | No recent camera solve; the position is being dead-reckoned from the IMU. Pulses. |
| 🔴 | `no star match – normal indoors/no sky view` | The last solve attempt found no stars (expected without a clear sky — not a hardware fault). |
| 🔴 | `not real – see Injected Solve below` | An **Injected Solve** is active, so the reported position is not backed by a real plate-solve. |

**`Injected`** — a chip that appears docked onto `Solve`'s right edge **only while Injected Solve
(Dead Reckoning) is active** — a manually seeded RA/Dec (Synthetic Solve, Re-seed from mount, Set
position, or Sync). Its presence *is* the signal; there is no colour scale. Whenever it shows,
`Solve` is red. See [Mount Bridge & Sync Workflows → Synthetic Solve vs. a manual one-shot
seed](#synthetic-solve-vs-a-manual-one-shot-seed).

**`IMU`** — is the BNO055 orientation sensor wired up? (raw I²C bus scan for its address, run through
PiFinder's venv)

| | State | Meaning |
|---|---|---|
| ⚪ | `checking…` / `unknown (…)` | The test hasn't run yet this session, or the probe tool isn't available on this host (e.g. no `rpicam-hello` on x86). |
| 🟢 | `functional` | The chip answered on the I²C bus. |
| 🔴 | `not detected` / `error (…)` | Nothing at the BNO055 address, or the read errored. |

**`GPS`** — what does PiFinder's own GPS handling currently report? (queried from PiFinder, not
re-implemented here)

| | State | Meaning |
|---|---|---|
| ⚪ | `not reachable` | PiFinder isn't answering — Real or Fake Mode must be running to read GPS status. |
| 🟢 | `locked` | A position fix is held (detail row shows lat/lon, timezone, last fix time, source). |
| 🟡 | `no fix yet` | The receiver is present and reachable but hasn't acquired a fix. |

**`PiFinder`** (shows a value such as `Right / Equatorial`) — PiFinder's own **Mount Type** +
**PiFinder Type** settings, which feed its IMU dead-reckoning. Shown whenever PiFinder hardware is
reachable, independent of Mount Bridge.

| | State | Meaning |
|---|---|---|
| ⚪ | value shown, neutral | PiFinder is reachable but Mount Bridge can't yet verify the type against a connected INDI mount. |
| 🟢 | value shown, green | Mount Bridge verified it — PiFinder's Mount Type matches the connected mount. Colours this badge and the Mount icon's type line in the diagram together. |
| 🔴 | value shown, red | Mismatch between PiFinder's Mount Type and the connected mount — the dead-reckoning math would be wrong. (PiFinder Type itself can't be auto-checked; judge it against your actual rig.) |

### Mount Bridge diagram

The connection diagram (`PiFinder ↔ Bridge ↔ Mount`) sits directly under the badge row.

**The three node icons** — each shows whether that device's INDI `CONNECTION` is up:

| | Meaning |
|---|---|
| ⚪ | Not linked / state unknown. |
| 🟢 | Connected. |
| 🔴 | Loaded but disconnected. |

The dotted arrows between the nodes show what the Bridge is *doing* (reading only, about to
correct, forwarding a GoTo) — not a traffic-light.

**`Drift`** (the value between the Bridge and Mount icons) — the angular distance between PiFinder's
solved position and the mount's reported position, in arcminutes (shown as `1° 5'` past 60').

| | State | Meaning |
|---|---|---|
| — | *hidden* | No coupling mode is actively watching, or the Bridge isn't connected. |
| 🟢 | ≤ Threshold | Within the drift Threshold you've set (default 5′). |
| 🟡 | > Threshold | Past the Threshold — Verify/Alert warns, an Auto-correct mode acts. |
| 🔴 | ≥ 30′ (≈ 0.5°) | Past a generic "probably outside the eyepiece field of view" limit (a full-moon diameter — not a measurement of your actual optics). |

The number **freezes at its last value while the mount is below the horizon** — it isn't recomputed
there — and resumes when the mount is back above it.

**`Alt`** — the mount's own altitude, recomputed every driver tick from its reported position.

| | State | Meaning |
|---|---|---|
| — | *hidden* | No altitude reading yet (older driver build, or mount not connected). |
| 🟢 | above margin | Above the horizon safety margin. |
| 🔴 | at/below margin | At or below the horizon — the mount won't accept a Sync or GoTo there; a recovery card appears with **Sync mount from PiFinder** / **Goto Home Position**. |

Below the diagram, a one-line **coupling status** — a dot (⚪ not coupled yet · 🟢 watching / holding
· 🟡 or 🔴 drift past threshold) plus words, with a `Details` expander for the full explanation.

### Status-line dots

The `<dot> Label: status` lines throughout the page use the same four colours: `PiFinder is
running` (🟢) vs `not detected` (🔴); `Normal (NN% CPU)` (🟢) vs a busy Pi (🟡/🔴, a heads-up that
PiFinder's own position server may briefly lag); the INDI Mount Bridge status line (🟢 connected ·
⚪ `(unconfirmed)` while a status check is momentarily out).

---

## Architecture

Two logical halves, sharing one HTTP server and one page:

- **Install/Update orchestration** — runs `pifinder_stellarmate_setup.sh --action=<reinstall|update|
  cancel>` as a subprocess, streams its stdout into a rolling buffer the frontend polls (`/log`,
  `/state`), and parses two kinds of markers the script itself emits into that same stream:
  `###PHASE### <label>` (drives the 10-step progress bar — tracks the *furthest* phase reached, so
  the venv-bootstrap self-restart mid-run doesn't make progress appear to jump backwards) and
  `###REBOOT_NEEDED### true|false` (drives the conditional Reboot button — only shown if this run
  actually touched `/boot/config.txt`, since that's the only case that needs one).
- **Live status/control** — a family of independent, on-demand checks and toggles (mode switch,
  hardware checklist, Solve Simulation, LCD overlay, numpad bridge, power actions), each backed by
  its own small, focused function in `server.py`. None of these depend on an install/update run being
  in progress or complete; they're always live once the server itself is running.

Both halves are served by the same single-threaded-per-request `ThreadingHTTPServer` — long-running
actions (an install run, a mode switch, waiting out a reboot) are always dispatched to a background
`threading.Thread`, so the HTTP server itself never blocks waiting for them; the frontend polls for
progress instead of holding a request open.

---

## Feature Walkthrough

### Setup / Install / Update

Drives `pifinder_stellarmate_setup.sh` through its `--action=` flag instead of interactive terminal
prompts (including the venv-bootstrap two-pass self-restart, which the script otherwise expects a
human to sit through). A 10-step progress bar and checklist track phase markers from the script; a
Reboot button appears only when actually needed.

### Reset / Uninstall

Two destructive actions, deliberately grouped by actual scope rather than by when they were built —
each sits next to the other action(s) that touch the same thing:

- **Reset** (in the **PiFinder** group, next to Reinstall/Update - all three only ever touch
  `~/PiFinder`): briefly stops `pifinder.service`/`pifinder_splash.service`/`pifinder-setup.service`
  so they're not running against a half-deleted venv, then wipes `~/PiFinder`'s own Python virtual
  environment and build state (`POST /reset`, streamed via `GET /api/reset_log`). Does **not**
  disable/remove those services or touch INDI drivers/udev rules - they stay installed, just
  stopped until the next setup run or reboot.
- **Uninstall** (in its own **PiFinder Stellarmate** group): stops, disables, and removes every
  systemd unit this project installs, removes the INDI drivers, and deletes both `~/PiFinder` **and**
  this `~/PiFinder_Stellarmate` checkout itself (`POST /uninstall`, streamed via
  `GET /api/uninstall_log`) - the only action here that also removes the Control Center's own
  directory and unit. Runs via `bin/uninstall_pifinder_stellarmate.sh --selfmove`, which copies
  itself to `/tmp` first so the deletion of its own source tree doesn't kill the running process
  mid-uninstall; a deliberate small pause between each systemd unit stop gives the frontend's poll
  loop (`GET /api/uninstall_log`, 200ms) a real chance to show each step before the connection drops
  (without it, 6 unit stops complete in under a second - too fast to show each step).

Both confirm dialogs spell out the exact scope before acting - see
[help.html#install-update](gui_installer/help.html) (Reset) and
[help.html#uninstall](gui_installer/help.html) (Uninstall) for the same explanations surfaced in-app.

### Fake/Real Mode Switch

A dedicated tile shows whether PiFinder is currently running for real (`pifinder.service`) or as a
hardware-free instance for dev/testing (`test_tools/fake_mode.sh`, port 8081), with a one-click
switch. The switch doesn't trust the launched process's exit code alone — it **settle-checks** the
actual target state (up to 8 seconds, polling every second) before declaring success, since
`systemctl start`/`pf_remote.py launch` both return as soon as the process is *spawned*, not once
it's actually reachable.

### Hardware Checklist

Checks camera, IMU, and GPS **directly against the hardware**, independent of what PiFinder's own
software believes:

| Check | Method | Why not just ask PiFinder |
|---|---|---|
| Camera | `rpicam-hello --list-cameras` | `pifinder.service` can report "active" with a fully crashed camera subprocess — the rest of the app (web server, GPS, IMU) keeps running regardless, a known upstream architecture quirk. |
| IMU | Raw I2C bus scan for the BNO055's address (`0x28`/`0x29`), run through PiFinder's own venv (needs `board`/`adafruit_bno055`) | Same reasoning — a software-level "IMU ok" isn't independent evidence the chip is actually wired up. |
| GPS | Direct query to `gpsd`'s own `DEVICES` report over its native protocol (port 2947) | `gpsd` is a shared, concurrent-safe daemon — safe to query alongside PiFinder's own connection to it, and reports the receiver's *presence*, independent of whether a fix has been acquired yet. |

Keyboard is deliberately **not** included in this live checklist (checking it needs PiFinder
stopped, since it needs exclusive GPIO access) — the row instead points at
`test_tools/keypad_gpio_matrix_test.py` for a manual, PiFinder-stopped check.

### Solve Simulation

A direct toggle for PiFinder's own "Tools → Test Mode" (canned test images substituted for the
camera, for exercising plate-solve UI without sky access) via `POST /api/debug_solve` — proxied
through this server rather than fetched directly from the browser (PiFinder's own API doesn't set
CORS headers, and this way the toggle works regardless of which port PiFinder actually landed on).
Built specifically because driving this via simulated keypresses (`/api/key` menu navigation) proved
unreliable — keypresses could be silently dropped, leaving the menu cursor stuck.

### Hardware / Peripherals: External SPI LCD & Numpad Bridge

Two independent toggles for hardware-free dev/test peripherals:

- **External SPI LCD** — enables/disables a Waveshare 3.5" LCD's device-tree overlay in
  `/boot/config.txt` and reboots (Pi firmware overlays only apply at boot; there's no live-toggle
  path). Needs the same GPIO lines a real HAT's OLED/keypad use, so the two can never be active
  simultaneously. Once active, `pifinder-fake-mode-autostart.service` brings up Fake Mode plus both
  LCD bridges automatically on every boot.
- **Numpad Bridge** — see [Readme_KeyboardBridge.md](Readme_KeyboardBridge.md) for the bridge
  itself. This toggle just drives `pifinder-numpad-bridge.service`'s enabled-state (`systemctl
  enable/disable --now`).

### Power Actions

Always-visible Reboot/Shutdown buttons (`sudo reboot`/`sudo poweroff`), each with its own
confirmation dialog that becomes more insistent if an install/update or mode switch is currently in
progress. Distinct from the "Close Setup" action, which only stops this web server's own process
(and persists that as `pifinder-control-center.service`'s disabled state, so it doesn't silently
restart on the next boot either).

---

## Installation & Illustrated Guide

Installed and kept up to date automatically by `pifinder_stellarmate_setup.sh` — nothing to do
manually on a normal install. To launch it directly:

```bash
bash gui_installer/launch_setup_gui.sh
```

Then open `http://<pi-address>:8765` in a browser — on the Pi itself, or from any other device on
the same network (no desktop session on the Pi required; the server binds `0.0.0.0`). Any username
works; the password is the `stellarmate` system account's password (see
[Authentication & Security Model](#authentication--security-model)).

### The page at a glance

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_full_page.png"><img src="docs/images/readme/cc_full_page.png" width="500"></a><br>
<sub>The whole page (Full Simulation shown here). Top to bottom: the <strong>PiFinder</strong> tile (OLED mirror, quick keys, the Cam/Solve/IMU/GPS badge row, and — directly under it — the Mount Bridge connection diagram), the <strong>INDI Mount Bridge</strong> tile, <strong>Simulation, Test and Power</strong>, and <strong>Install or Update</strong> at the bottom. Every tile heading collapses; the state is remembered per browser.</sub>
</td>
</tr>
</table>

The three status tiles are covered elsewhere — the PiFinder badge row and the Mount Bridge diagram
in [Mount Bridge & Sync Workflows](#mount-bridge--sync-workflows), the hardware checklist and mode
switches in [Feature Walkthrough](#feature-walkthrough). The rest of this section is the one tile
that section doesn't reach: **Install or Update**.

### Installing or updating

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_install_idle.png"><img src="docs/images/readme/cc_install_idle.png" width="640"></a><br>
<sub>The idle tile when an install already exists. <strong>PFSM Source Branch</strong> picks which branch of <em>this project's own scripts</em> a run uses (not PiFinder itself); the ↻ re-checks what is actually on disk. The three PiFinder actions and a separate <strong>Uninstall</strong>.</sub>
</td>
</tr>
</table>

- **Reinstall from scratch** — deletes `~/PiFinder` entirely, clones a fresh copy of the official
  `release` branch at the pinned version, then re-applies every StellarMate patch. Confirm dialog:
  *Reinstall from scratch? This permanently deletes the existing ~/PiFinder directory and everything
  in it.*
- **Update** — `git reset --hard` + `pull` on the existing `~/PiFinder` to the pinned version, then
  re-applies the patches, keeping the directory. Confirm dialog: *Update? This runs `git reset
  --hard` on ~/PiFinder, discarding any local changes there.*
- **Reset** — stops the PiFinder services and wipes only `~/PiFinder`'s Python venv and build state;
  services, INDI drivers, udev rules, data and config are untouched. Use it to get a clean slate for
  a re-run without losing anything else.
- **Uninstall** — in its own group because it acts on much more: removes every systemd unit, the
  INDI drivers, `~/PiFinder`, **and this `~/PiFinder_Stellarmate` checkout itself** (the Control
  Center stops working once it starts). See
  [Reset / Uninstall](#reset--uninstall) and [help.html#uninstall](gui_installer/help.html).

Reinstall, Update, Reboot and Shutdown all confirm first, and the dialog gets *more* insistent if a
run is already in progress rather than firing immediately.

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_install_running.png"><img src="docs/images/readme/cc_install_running.png" width="640"></a><br>
<sub>A run in progress: a 10-step progress bar, a per-phase checklist (green check = done, striped = current), and the setup script's live terminal output streamed straight into the tile.</sub>
</td>
</tr>
</table>

The progress bar tracks the *furthest* phase reached, so the venv-bootstrap self-restart mid-run
doesn't make progress appear to jump backwards. A **Reboot Now** button appears **only** when this
run actually changed `/boot/config.txt` (the only case that needs one). When the run finishes, the
Control Center restarts itself once to load any new code, then returns to the idle state above; the
full summary — versions, timings, any warnings — is written to
`~/PiFinder_Stellarmate/.gui_setup.log`.

Running elsewhere: `INDI-only` (checkbox) installs just the INDI build dependencies and both INDI
drivers — no clone, no venv, no catalog — for a separate control host coupled to a PiFinder over the
network (see [help.html#indi-only-mode](gui_installer/help.html)).

---

## Mount Bridge & Sync Workflows

The Control Center's **INDI Mount Bridge** area couples PiFinder's own plate-solved sky position to a
telescope mount, through the `PiFinder Mount Bridge` INDI driver — so the everyday "is my mount still
where PiFinder thinks it is, and fix it if not" workflow doesn't need the separate INDI Control
Panel. The driver, the coupling modes, and the split-host variants are covered in full in
[Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md); this section is a picture walkthrough of the
Control Center surface for it — reading the tiles, and the **sync-based** recovery flows that make up
day-to-day use.

> **All screenshots below are from Full Simulation mode** (a simulated PiFinder plus a simulated
> mount — INDI's own `Telescope Simulator`, presented as mount type `EQ_GEM`), not real hardware.
> The layout, badges, and buttons are identical on a real setup; only the device name and the
> numbers differ. Coordinate GoTos aren't meaningful in this simulation setup, so the walkthroughs
> stay on sync-based recovery — the one exception is **Goto Home Position**, which is a native OnStep
> reference-position command, not a coordinate GoTo.

### Reading the tiles

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_mount_bridge_baseline.png"><img src="docs/images/readme/cc_mount_bridge_baseline.png" width="620"></a><br>
<sub>Baseline reading (Full Simulation): PiFinder badge row, the Mount Bridge connection diagram, and the coupling status line — the top of the page, nothing expanded.</sub>
</td>
</tr>
</table>

Two things to read here, top to bottom:

- **The PiFinder badge row** — `Cam` / `Solve` / `Injected` / `IMU` / `GPS` and the screen-orientation
  badge, each in the page's four-state colour language (white = unknown, green = ok, yellow =
  degraded, red = failed). In the shot, `Solve` is red (no real camera solve indoors) but `Injected`
  is green — the position PiFinder is reporting is a *synthetic* one (see
  [Synthetic Solve vs. a manual one-shot seed](#synthetic-solve-vs-a-manual-one-shot-seed) below).
- **The Mount Bridge diagram** — `PiFinder ↔ Bridge ↔ Mount`, with two readouts wedged between the
  Bridge and Mount icons:
  - **Drift** — the angular distance between PiFinder's solved position and the mount's reported
    position, in arcminutes (shown as `1° 5'` past 60'). Green within your Threshold, yellow past it,
    red past ~0.5°. Only shown while a coupling mode is actively watching.
  - **Alt** — the mount's own altitude, recomputed every driver tick from its reported position.
    Turns red at or below the horizon safety margin.
  - Below the diagram, a one-line coupling status (`Watching for drift` · `verify alert (drift
    0.2')`) — a coloured dot plus words for the same state, with a `Details` expander so the row
    doesn't change height as the text changes.

This diagram and the drift/alt readouts live in the **PiFinder** tile (directly under the badge row)
because they're pure status; the `INDI Mount Bridge` section further down is where the *actions* are.

### "PiFinder's simulated position isn't related to the mount"

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_mount_bridge_sim_mismatch.png"><img src="docs/images/readme/cc_mount_bridge_sim_mismatch.png" width="620"></a><br>
<sub>Full Simulation startup notice: PiFinder's simulated sky position was seeded independently of the mount, so any agreement between them is coincidental until you tie them together.</sub>
</td>
</tr>
</table>

In Full Simulation the simulated PiFinder and the simulated mount each pick a start position on
their own. When the Mount Bridge driver starts and finds it had nothing better to go on than its
compiled-in fallback, it raises this amber card once: the drift number may *look* fine at a glance
(it's a real star, after all), but Verify/Alert and Sync-from-PiFinder don't actually mean anything
relative to the mount yet. The card offers the two ways to make them mean something — pick whichever
matches which side you trust:

| Button | What it does | Use when |
|---|---|---|
| **Re-seed from mount** | Reads the mount's current position and injects *that* as PiFinder's position. | The mount is where you want to be; PiFinder's (simulated) solve is the odd one out. |
| **Sync mount from PiFinder** | Syncs the mount to whatever PiFinder currently shows — an instant position update, no slew. | PiFinder's position is correct (a real solve, or one you deliberately set) and the mount's belief is wrong — e.g. after moving the mount by hand. |

Either one, once it genuinely succeeds, clears the card. This is the most-exercised flow of the
whole Mount Bridge surface: the same **Sync mount from PiFinder** button also appears in Quick
Actions and in the drift banner, and does the same thing everywhere — a one-shot sync to PiFinder's
*currently visible* position, with no freshness check, regardless of the coupling mode.

### Mount below the horizon

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_mount_bridge_below_horizon.png"><img src="docs/images/readme/cc_mount_bridge_below_horizon.png" width="620"></a><br>
<sub>Full Simulation: the mount's reported position is below the horizon — the <code>Alt</code> badge is red and a recovery card appears with the two ways out.</sub>
</td>
</tr>
</table>

When the mount's own reported position drops to or below the horizon safety margin, the `Alt` badge
turns red and this recovery card appears. No software toggle helps here — the driver won't let a
Sync or GoTo through to a below-horizon target anyway — so the card offers only the two real ways
out:

- **Sync mount from PiFinder** — if PiFinder's *own* position is above the horizon (which it often
  is: the disagreement is the whole point), this succeeds and corrects the mount's belief with no
  physical motion.
- **Goto Home Position** — sends the mount to its native OnStep home/reference position. This is a
  firmware reference command, not a coordinate GoTo, so it works even when a coordinate GoTo would
  be refused.

The drift figure freezes at its last value while this is showing — it isn't recomputed while the
mount is below the horizon, since it wouldn't mean anything.

### Choosing a Coupling mode

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_mount_bridge_coupling.png"><img src="docs/images/readme/cc_mount_bridge_coupling.png" width="620"></a><br>
<sub>The <code>INDI Mount Bridge</code> section (Full Simulation): Quick Actions on top, the Coupling presets below, and the one-time Settings collapsed at the bottom.</sub>
</td>
</tr>
</table>

The section splits into what you use every session and what you set once:

- **Quick Actions** — the one-shot buttons: **Sync mount from PiFinder** (above), **Align to Held
  Target** and **Goto Held Target** (correct PiFinder's or the mount's belief about the held target
  — need an active coupling mode), and **Stop movement** (emergency stop; also sets Coupling to Off
  so nothing re-triggers). **Threshold** (arcmin) is how far off before Verify/Alert warns or an
  Auto-correct mode acts. **Decouple** sets Coupling back to Off.
- **Coupling presets** — pick one:
  - **Verify/Alert only** — watches the drift, never moves the mount. The passive "is my mount still
    aligned?" check for astrophotography.
  - **Auto-correct (Sync)** — same watching, but once drift passes the Threshold it syncs the mount
    to PiFinder's position (instant, no slew — works on any mount). The push-to-by-hand-then-correct
    workflow.
  - **GoTo** — physically slews; holds whichever target was most recently set from either side.
    Needs a real Goto-capable mount, so it isn't exercised in this simulation setup.
- **Settings** (collapsed) — Role, hardware mode, and the numbered setup checklist. One-time
  per-session configuration, kept out of the everyday flow.

Clicking a preset before the numbered setup steps are all green doesn't fail — it runs the setup
first (Autoconnect), then applies the mode you clicked.

### Synthetic Solve vs. a manual one-shot seed

Both feed PiFinder a position it didn't plate-solve, for exercising everything downstream of a solve
(the Mount Bridge, the UI) without sky access — but they're different tools:

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_synthetic_solve.png"><img src="docs/images/readme/cc_synthetic_solve.png" width="480"></a><br>
<sub>Synthetic Solve (in <em>Simulation, Test and Power</em>): one toggle, kept alive by a background watchdog.</sub>
</td>
</tr>
</table>

**Synthetic Solve** *continuously* feeds PiFinder the simulated mount's position (via
`test_tools/pifinder_truth_injector.py`), so PiFinder and the simulated mount track together as one
moves. One toggle, one dot; a watchdog restarts the feed if it dies. This is the normal Full
Simulation "there is a sky" switch. It drives the green `Injected` badge in the PiFinder tile.

<table>
<tr>
<td align="center">
<a href="docs/images/readme/cc_mount_bridge_manual_seed.png"><img src="docs/images/readme/cc_mount_bridge_manual_seed.png" width="620"></a><br>
<sub>Manual one-shot seed (Full Simulation), inside Quick Actions: <code>Re-seed from mount</code>, <code>Set position</code>, and a direct RA/Dec entry.</sub>
</td>
</tr>
</table>

**Manual one-shot seed** (collapsed inside Quick Actions) injects a *single* position and stops:
**Re-seed from mount** reads the mount's current position once, **Set position** takes a literal
RA/Dec (JNow, degrees), and either turns the injection on if it wasn't. PiFinder's normal IMU
dead-reckoning tracks from that anchor exactly as it would from a real solve. Use this to place
PiFinder at one known spot — e.g. to set up the disagreement for a Sync test — rather than have it
follow the mount. `Turn off` returns PiFinder to real camera solving. Deliberately *not* reflected
in the Synthetic Solve dot, to keep that one signal simple.

---

## Technical Reference: API Surface

All routes served by `gui_installer/server.py`. `Auth` = requires HTTP Basic Auth against the
`stellarmate` system account (see [Authentication & Security Model](#authentication--security-model)).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | ✅ | The page itself |
| GET | `/state` | — | Install/update run status (polled by the frontend) |
| GET | `/log` | — | Streamed install/update terminal output |
| POST | `/start?action=fresh\|reinstall\|update\|cancel` | ✅ | Start a setup-script run |
| POST | `/reset` | ✅ | Start a Reset run (`~/PiFinder` venv/build only) |
| GET | `/api/reset_log?position=N` | ✅ | Incremental Reset output |
| POST | `/uninstall` | ✅ | Start an Uninstall run (removes everything, incl. this checkout) |
| GET | `/api/uninstall_log?position=N` | — | Incremental Uninstall output (exempt like `/state`/`/log` - see below) |
| GET | `/page_version` | — | Content hash of `status_page.html`, used for the "reload now" stale-tab banner |
| POST | `/reboot` | ✅ | Reboot the Pi |
| POST | `/shutdown` | — | Stop *this web server* (not the Pi) |
| POST | `/poweroff` | ✅ | Power off the Pi |
| GET | `/api/pifinder_mode` | ✅ | Current Fake/Real/none mode + any in-flight switch status |
| POST | `/api/pifinder_mode?action=enable_fake\|disable_fake` | ✅ | Trigger a mode switch |
| GET | `/api/pifinder_mode_log?position=N` | ✅ | Incremental mode-switch script output |
| GET | `/api/hardware_status` | ✅ | Camera/IMU/GPS presence (raw hardware checks) |
| GET | `/api/debug_solve?port=N` | ✅ | Proxy: PiFinder's own Solve Simulation state |
| POST | `/api/debug_solve?port=N` | ✅ | Proxy: toggle PiFinder's own Solve Simulation |
| GET | `/api/display_bridge` | ✅ | Whether the LCD overlay is currently active |
| POST | `/api/display_bridge?action=start\|stop` | ✅ | Toggle the LCD overlay (triggers a reboot) |
| GET | `/api/keyboard_bridge` | ✅ | Whether the numpad bridge service is running |
| POST | `/api/keyboard_bridge?action=start\|stop` | ✅ | Toggle the numpad bridge |
| GET | `/pifinder.jpg`, `/avvp_logo.png`, `/heyapos_logo.png`, `/pifinder_welcome.png` | ✅ | Static assets |

`/state`, `/log`, `/shutdown`, `/page_version`, and `/api/uninstall_log` are deliberately auth-exempt.
PiFinder's own unauthenticated "INDI Drivers" page cross-origin-polls `/state`/`/log` to show "Setup
is running" without a login prompt, and cross-origin requests never carry this page's cached Basic
Auth credentials anyway, so `/shutdown` (non-destructive to the Pi itself — it only stops this GUI's
server) has to stay open for that same cross-origin button to work. `/api/uninstall_log` specifically
skips the PAM check inside `_require_auth()` for latency reasons: this server stops its own systemd
unit partway through an Uninstall run, so a slower, authenticated poll has a worse chance of
completing at all before the connection drops.

---

## Persistence & Process Model

| Component | Persistence mechanism |
|---|---|
| Control Center itself | `pifinder-control-center.service` — `systemctl enable/disable --now`, toggled by the "Close Setup"/launch actions |
| Install/update runs | One-shot subprocess per run, no persistence needed (either finishes or is cancelled) |
| Fake/Real Mode | `test_tools/fake_mode.sh` manages `pifinder.service` (systemd) vs. a `pf_remote.py`-launched fake instance |
| External SPI LCD | `/boot/config.txt` overlay line — persists across reboots by definition (firmware-level) |
| Numpad Bridge | `pifinder-numpad-bridge.service` — same enable/disable pattern as the Control Center itself |

The recurring pattern across every toggle in this tool: **systemd's own enabled-state is the single
source of truth for "should this be on after a reboot,"** never a flag file or an in-memory variable
in `server.py`. This was arrived at after two separate incidents where a plain tracked subprocess
(`Popen`) failed to survive a reinstall or a reboot — once when a hardware-free Fake Mode instance
survived a `rm -rf` unnoticed and kept running stale code, and once with the numpad bridge's
original design.

---

## Authentication & Security Model

- The page itself and every state-changing action require **HTTP Basic Auth against the
  `stellarmate` system account's real password**, verified via PAM (`pam_auth.py`) — the same
  account and mechanism PiFinder's own Remote login checks, so there's exactly one password to
  remember for both.
- `/state`, `/log`, `/shutdown` are intentionally open (see the API table above) — none of the three
  can do anything destructive to the Pi itself.
- Failed logins are rate-limited per client IP: 5 *confirmed wrong-password* attempts within 30
  seconds locks that IP out until the window elapses, and a semaphore caps concurrent PAM calls at
  2 regardless of outcome (this page's own ~15 concurrent polls on load could otherwise
  starve the GIL with password-hashing work, or trip the lockout purely from the resulting race —
  neither is a real attack). This is a basic guard against casual brute-forcing, not a substitute
  for keeping the server off an untrusted network.
- The server binds `0.0.0.0` (reachable from any device on the LAN, not just the Pi), so this
  should never be exposed beyond a trusted home/observatory network regardless of the above.
- CORS (`Access-Control-Allow-Origin: *`) is only set on the auth-exempt JSON routes, specifically to
  let PiFinder's own "PFSM" page (a different origin/port) read them via `fetch()` —
  widening CORS to the authenticated routes would defeat the purpose of requiring auth at all.

---

## Known Limitations & Troubleshooting

- **No camera/IMU on Pi 5 with certain UPS shields**: unrelated to this tool itself, but surfaces
  through its hardware checklist — the Geekworm X1203/GPIO 16 conflict (see the compatibility banner
  in the main [README.md](README.md)), which the checklist will correctly report as "keyboard"
  hardware-affected (not camera/IMU/GPS, which this checklist covers).
- **A crashed camera subprocess can leave `pifinder.service` reporting "active."** This is exactly
  why the hardware checklist exists and checks raw hardware rather than trusting `systemctl
  is-active` — see [Design Principles](#design-principles) point 3.
- **The page's cached JS/HTML can go stale across an update** if a browser tab was left open through
  a Control-Center-updating run — `Cache-Control: no-store, must-revalidate` is set specifically to
  minimize this, but a hard refresh after any update is still the safest first troubleshooting step
  if a button seems to reference a route that no longer exists.
- **`/boot/config.txt` overlay changes require a reboot** — there is no live-toggle path for Pi
  firmware overlays; the LCD toggle's reboot is not optional, not a bug.

---

## Development & Testing

- `test_tools/fake_mode.sh start`/`stop` can be exercised directly, independent of the Control
  Center's own tile, for scripting/automation.
- The `pifinder-remote` Claude Code skill's `pf_remote.py` (`.claude/skills/pifinder-remote/`) is
  what `fake_mode.sh` uses under the hood to launch a fake-hardware instance.
- No automated test suite exists for `gui_installer/` yet (see Roadmap) — all verification
  to date has been live, manual, end-to-end testing against real installs/reinstalls/reboots.

---

## Roadmap

The project-wide direction (v2.x / v3.x) is in the main [README.md](README.md#roadmap). Tracked,
prioritized work — including Control-Center-specific items — lives in the
[GitHub Project](https://github.com/users/apos/projects/15) ([roadmap
view](https://github.com/users/apos/projects/15/views/4)); shipped changes are in
[CHANGELOG.md](CHANGELOG.md).

---

## Version Compatibility

The PiFinder / StellarMate OS / Pi test matrix is maintained in one place — the
[Version Compatibility table in the main README.md](README.md#version-compatibility).

The Control Center itself has no PiFinder-version-specific code paths — it only ever talks to
PiFinder through its stable `/api/*` Remote API and to the system through `systemctl`/raw hardware
probes, both independent of the installed PiFinder version.

## See Also

- [Readme_KeyboardBridge.md](Readme_KeyboardBridge.md) — the numpad-as-keypad bridge this tool's
  "Turn Numpad On/Off" button controls.
- [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md) — the INDI integration layer, whose "INDI
  Drivers" page links back to this Control Center.
- [README.md](README.md) — base PiFinder-on-StellarMate installation, the version matrix, and the
  project roadmap.
- [Readme_design_decisions.md](Readme_design_decisions.md) — condensed rationale behind the key
  design decisions across the project.

---

<p align="center">
  <img src="docs/images/logo/PiFinder-Stellarmate_Wortmarke_Positiv_fuer-hellen-hg.png" alt="PiFinder StellarMate" width="300"><br>
  © github.com/apos 2026<br>
  <em>Unofficial community project, not affiliated with StellarMate or PiFinder.</em>
</p>
