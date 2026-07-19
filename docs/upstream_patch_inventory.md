# Patch Inventory: PiFinder_Stellarmate vs. upstream PiFinder

This document inventories every patch this project applies to a stock PiFinder installation —
both the tracked `diffs/*.diff` files (applied via `bin/patch_PiFinder_installation_files.sh`) and
the setup-script actions that aren't expressed as diffs at all (dependency version pins, GPIO/udev
setup, `/boot/config.txt` overlay selection, third-party package patches).

Each patch is placed in exactly one of four categories:

1. **[Potentially relevant to upstream PiFinder](#1-potentially-relevant-to-upstream-pifinder)** —
   fixes a real bug or adds a generically useful feature that isn't StellarMate-specific. See
   [`docs/upstream_pr_templates.md`](upstream_pr_templates.md) for ready-to-file PR text for each.
2. **[StellarMate/SMOS-only](#2-stellarmatesmos-only-not-relevant-upstream)** — only makes sense in
   a StellarMate-managed install; not proposed upstream.
3. **[Third-party dependency workarounds](#3-third-party-dependency-workarounds-wrong-upstream-target)**
   — patches a *different* project's installed package (picamera2, skyfield), not PiFinder's own
   code at all. Wrong repo to file an issue against.
4. **[Raspberry Pi 5 compatibility](#4-raspberry-pi-5-compatibility-in-detail)** — everything that
   exists purely to make a 2.6.0-era PiFinder run on a Pi 5's RP1 SoC. Treated in detail per
   request, since it spans several files and two separate scripts (install-time and boot-time).

A quick note on mechanics: `bin/patch_PiFinder_installation_files.sh` runs once per
install/update/reinstall, right after the fresh PiFinder checkout lands, and conditionally applies
each `diffs/*.diff` via `apply_patch_or_warn` (an ordinary `patch` wrapper) gated by
`should_apply_patch <pifinder-version> <pi-model> <os>`. A handful of third-party patches (picamera2,
skyfield) are applied later, from inside `pifinder_stellarmate_setup.sh` itself, once those packages
actually exist in the freshly-created venv.

---

## 1. Potentially relevant to upstream PiFinder

### 1.1 Reliable Test Mode toggle + status readback (`debug_solve`)

**Files**: `diffs/state_py.diff`, `diffs/camera_interface_py.diff`, `diffs/main_py.diff` (the
`toggle_debug_solve` case only), `diffs/api_extensions_py.diff`.

PiFinder's own "Tools → Test Mode" (`callbacks.activate_debug()`) substitutes a canned image for
live camera capture, useful for testing plate-solve UI without pointing at the sky. Two things were
missing before this patch set: **triggering** it reliably, and **reading back** whether it's
currently on.

- Triggering only worked by simulating the menu-navigation keypresses via `/api/key` — demonstrably
  unreliable (keypresses get dropped, the menu cursor can get stuck on the wrong item).
- The on/off state (`debug`) was a bare local variable inside `camera_interface.py`'s capture loop,
  never exposed anywhere.

The fix adds a proper state variable (`SharedStateObj.debug_solve()`/`set_debug_solve()` in
`state.py`), a direct trigger path (`ui_command == "toggle_debug_solve"` in `main.py`, itself
reachable via a new `POST /api/debug_solve` in `api_extensions.py`, which also adds `debug_solve` to
`GET /api/status`), and syncs the existing `if command == "debug":` handler in
`camera_interface.py` to keep the new state variable current.

**Why upstream-relevant**: general capability gap (no reliable way to drive or observe Test Mode
via the API), not a StellarMate-specific need — any automation, testing harness, or third-party
integration hitting PiFinder's HTTP API would want this.

**Known upstream complication**: while preparing this for a PR, `camera_interface.py` on
`brickbots/PiFinder`'s `main` branch was found to be **missing the `if command == "debug":` handler
entirely** — `activate_debug()` still sends the `"debug"` command, but nothing on `main` processes
it any more (only the GPS/date-faking and the console message still work). This looks like a
pre-existing upstream regression, unrelated to anything in this project, and would need its own
bugfix PR *before* the feature PR that depends on it makes sense. See
[`docs/upstream_pr_templates.md`](upstream_pr_templates.md) PR 1 and PR 2, and basic-memory
`pifinder-stellarmate/00022` for the original investigation. **This finding is from 2026-07-19 and
has not been re-verified against the current `main` tip** — re-check before opening PR 1.

### 1.2 Camera-process resilience: fall back to the debug camera instead of crashing

**Files**: `diffs/camera_pi_py.diff`, `diffs/camera_interface_py.diff` (the `initial_debug`
parameter).

If no camera is physically attached, `Picamera2()` raises during `CameraPI.__init__()`. Uncaught,
this crashes the *entire* camera subprocess before it ever reaches the shared image-capture loop —
which takes every other command on that process's queue down with it, Test Mode toggle included
(it's just another command on the same queue; a dead process can't be "toggled into" debug mode,
since it has to already be alive to receive the toggle at all).

The fix wraps `CameraPI(exposure_time)` in a try/except and falls back to `CameraDebug(exposure_time)`
on failure, and adds an `initial_debug` parameter to `get_image_loop()` so the fallback path seeds
the *same* state variable the Test Mode toggle uses (see 1.1) instead of leaving it to drift out of
sync — an actual bug caught live during testing (toggling "off" while running on the fallback camera
left the internal capture-loop state still effectively "on" underneath a UI that said "off").

**Why upstream-relevant**: this is arguably the single most useful fix in this whole set for anyone
running PiFinder hardware-optional (bench testing, a unit with a temporarily disconnected/broken
camera, CI). Right now a missing camera doesn't degrade gracefully — it silently kills a whole
subsystem. Depends on 1.1's `debug_solve` state existing, so it's proposed as a separate,
dependent PR rather than folded into it. See `docs/upstream_pr_templates.md` PR 3.

### 1.3 Comprehensive IP address display (`all_ips()`)

**Files**: `diffs/sys_utils_py.diff`, `diffs/sys_utils_fake_py.diff`, `diffs/status_py.diff`,
the `ip=", ".join(self.network.all_ips())` line in `diffs/server_py.diff`.

The Web UI home page and OLED status screen only ever showed the one IPv4 address the OS happens to
pick for outbound traffic (`Network.local_ip()`, effectively "whichever route the kernel would use
to reach the internet"). On any host with more than one active interface — WiFi *and* wired
Ethernet, or a WireGuard/VPN tunnel — every other address was invisible, even though the web UI is
just as reachable on those. `Network.all_ips()` (parses `ip -4 -o addr show`) returns every
non-loopback address instead; wired through the OLED status row (reusing its existing horizontal
scroller for overflow) and the Web UI's home page.

**Why upstream-relevant**: generically useful anywhere PiFinder might be reached over more than one
network path — a common setup for anyone using a wired connection to a laptop alongside WiFi to a
phone, independent of StellarMate.

### 1.4 WDS/extended-catalog background loader CPU throttling

**File**: `diffs/catalogs_py.diff`.

The deferred background loader for the WDS (double-star) and extended catalogs runs `os.nice(15)`
on its worker thread and doubles its inter-batch yield from 50ms to 100ms.

**Why upstream-relevant**: straightforward robustness fix — a background catalog load competing at
normal priority against the UI/solve loop can cause visible UI stutter on slower hardware (this was
observed during testing on both Pi 4 and Pi 5); lowering its scheduling priority and giving it more
frequent, longer yields is a pure quality-of-life improvement with no behavioral downside.

### 1.5 `PIFINDER_WEB_PORT` environment override

**File**: the `run()` method portion of `diffs/server_py.diff`.

An opt-in env var (`PIFINDER_WEB_PORT`) that, if set, makes the web server bind that exact port
instead of the existing 80-then-8080 auto-detection. Completely inert when unset — the existing
behavior is untouched.

**Why upstream-relevant**: small, low-risk convenience for anyone wanting to run a second PiFinder
instance in parallel with a real one (e.g. for dev/testing, exactly why this project needed it — see
`test_tools/fake_mode.sh`), without needing to patch the source to do it.

### 1.6 Not proposed, flagged for awareness: GPS-location update condition removed

**File**: `diffs/main_py.diff` (the hunk removing the `location.error_in_m == 0 or
float(gps_content["error_in_m"]) < float(location.error_in_m)` condition).

Upstream only accepts a new GPS fix as the active location if its reported error is smaller than the
currently-held one (`error_in_m` improving). This project's patch removes that condition entirely,
so any new non-config/non-manual GPS content now updates the location unconditionally. This was
carried along with the `debug_solve`/main.py changes; **no note in this session's history documents
why it was made**, and it changes real location-tracking behavior, not just a StellarMate
integration point. Flagging it here rather than in the PR templates — this needs its actual
rationale reconstructed (or the removal re-justified against a specific StellarMate GPS behavior)
before it's fit to propose upstream, or even to keep long-term without a comment explaining it.

---

## 2. StellarMate/SMOS-only (not relevant upstream)

These only make sense because this project runs *inside* a StellarMate-managed install, sitting
next to StellarMate's own web manager, GPS, and mount-control stack. None of them are proposed
upstream.

- **Network-Setup menu removal / INDI Drivers nav** — `diffs/base_html.diff`, `diffs/header_tpl.diff`,
  `diffs/index_html.diff`, `diffs/index_tpl.diff`. PiFinder's own network-configuration UI is
  removed from the nav (StellarMate's Web Manager already owns networking on this device — two
  independent WiFi/AP configuration UIs on the same box would conflict), replaced with a link to
  the new `/smos` "INDI Drivers" page.
- **`menu_structure.py`** (`diffs/menu_structure_py.diff`), three unrelated changes bundled in one
  diff:
  - **"WiFi Mode" removed** from the OLED Tools menu — same reasoning as the web nav change above:
    StellarMate owns networking, a second independent AP/Client toggle on the device itself would
    fight it.
  - **"Stellarmate" added as a GPS-type option** — wires up `gps_stellarmate.py` (see below) as a
    selectable source, alongside the existing `gpsd`/`ublox` options.
  - **"Software Upd" removed** from the OLED Tools menu — PiFinder's own self-update mechanism
    would pull code that the StellarMate patch layer then needs reapplying to, and could leave the
    install in a broken, half-patched state. Removed until there's a proper update strategy that
    accounts for the patch layer (tracked as a low-priority follow-up). This is the change the user
    specifically cited as the canonical "StellarMate-only" example.
- **`gps_stellarmate.py`** (whole new file, `src_pifinder/python/PiFinder/gps_stellarmate.py`,
  copied in on every install/update — not a diff, since it doesn't exist upstream at all): a GPS
  backend that reads location from StellarMate/KStars' own GPS integration instead of a
  directly-attached `gpsd`/UBlox receiver. Only meaningful when co-installed with StellarMate.
- **`config.json`/`default_config.json` `gps_type` default → `"stellarmate"`** — plain `sed`
  replacement in the setup script (not a diff), pointing fresh installs at the module above by
  default.
- **`/smos` route, `POST /api/setup_gui/start`, `POST /api/set_mount_type`** — all in
  `diffs/server_py.diff`. `/smos` renders the "INDI Drivers" page pointing at this project's own
  driver-installation instructions; `api_start_setup_gui` launches this project's Control Center
  from a button on that page; `/api/set_mount_type` is the loopback-only endpoint the PiFinder LX200
  Mount Bridge INDI driver calls to keep PiFinder's own Alt/Az-vs-EQ setting in sync with whichever
  real INDI mount is currently connected. All three only exist because of the INDI/StellarMate
  integration this project builds.
- **Login/password-change username, `"pifinder"` → `"stellarmate"`** — also in
  `diffs/server_py.diff` (`verify_password`/`change_password` call sites). This is a StellarMate
  deployment convention (the shared account name used across the whole SMOS environment, not a
  generic feature), so it's kept as SMOS-only rather than proposed as an upstream
  configurable-username feature — though see the PR templates doc for a lighter-weight
  generic-username alternative that *would* be worth proposing if there's appetite for it.

---

## 3. Third-party dependency workarounds (wrong upstream target)

These patch a package PiFinder *depends on*, not PiFinder's own source — filing them against
`brickbots/PiFinder` would be the wrong repository even though `bin/patch_PiFinder_installation_files.sh`
happens to apply them as part of the same install run.

- **`diffs/drm_preview_smos.diff`** — patches `picamera2`'s own installed
  `previews/drm_preview.py` (site-packages, not PiFinder's code) to tolerate `pykms` being
  unavailable (not packaged for Arch/SMOS). Belongs against `picamera2` if reported anywhere, not
  PiFinder.
- **`diffs/starlib_numpy2_smos.diff`** — patches `skyfield`'s own installed `starlib.py` for a
  numpy 2.0 `isnan`-on-object-dtype incompatibility.
- **`diffs/keplerlib_batch_propagate_smos.diff`** — patches `skyfield`'s own installed
  `keplerlib.py`: batch-propagating more than one comet to a single shared observation time drops a
  dimension in `propagate()`'s output shape (`"cannot reshape array of size 3*N into shape (3,)"`),
  which PiFinder's `comets.py` `_calc_comets_vectorized()` hits directly. **Already reported
  upstream** — `skyfielders/python-skyfield` PR #1138 — so no new report is needed here; this patch
  is a defensive no-op in the current setup anyway, since `requirements.txt` is now pinned to
  `skyfield==1.50`, which predates the regression (introduced in 1.51). It only activates if
  skyfield ever ends up unpinned to something newer again.
- **`tetra3/main.py`: `np.math.factorial` → `math.factorial`** (plain `sed` in the setup script, no
  tracked diff file) — `np.math` was removed in numpy 2.0. `tetra3` is PiFinder's own vendored
  solver submodule (`brickbots/PiFinder`'s `tetra3` fork of `cedar-solve`), so this one *could* be
  upstream-relevant, but against the `tetra3` submodule's own repo, not `PiFinder` itself — out of
  scope for the PR templates in this pass, noted here for completeness.
- **`diffs/keyboard_pi_smos.diff`** — see [§4.6](#46-python-libinput-010-manual-install) below;
  categorized as SMOS/Arch-specific as a whole, since it migrates to a newer python-libinput API
  surface (0.1.0) than what upstream PiFinder's `requirements.txt` pins at all. The one-line root
  cause inside it (`KeyboardEvent.get_key()` returns a plain `enum.Enum`, not `IntEnum`, so
  `int(key)` must become `key.value`) isn't reproducible against upstream's pinned dependency
  version either, so there's nothing to file against `PiFinder` for it.

---

## 4. Raspberry Pi 5 compatibility, in detail

The Pi 5 uses a completely different SoC for GPIO (**RP1**, a separate southbridge chip — the Pi 4
and earlier used GPIO integrated directly into the BCM2711/predecessors). This breaks several
assumptions baked into both PiFinder's own code and its dependencies. Everything below exists solely
to bridge that gap; none of it does anything on a Pi 4.

### 4.1 `/dev/gpiomem0`–`gpiomem4` udev rule

**Where**: `pifinder_stellarmate_setup.sh`, "Setting up hardware access" phase.

Pi 4 exposes a single `/dev/gpiomem` device under one shared `gpiomem` udev subsystem. Pi 5's RP1
exposes **five** numbered nodes, `/dev/gpiomem0` through `/dev/gpiomem4`, each registered under its
**own individually-numbered** subsystem (`gpiomem0`, `gpiomem1`, ...) rather than one shared
`gpiomem` subsystem. A naive udev rule written for Pi 4 (`SUBSYSTEM=="gpiomem"`) silently matches
nothing on a Pi 5 — the nodes stay at their default `root:root 0600`, invisible to a non-root user.

Fixed with a wildcarded rule instead:

```
SUBSYSTEM=="gpiomem*", KERNEL=="gpiomem*", GROUP="gpio", MODE="0660"
```

reloaded and applied via `udevadm trigger --subsystem-match='gpiomem*'` — a **single glob argument**
turned out to matter here: passing each subsystem name as its own separate `--subsystem-match` flag
was verified live to leave some of the five nodes at their old, wrong permissions, while the single
glob argument reaches all of them in one trigger.

Worth noting: this rule is currently **defensive rather than load-bearing** in practice. PiFinder's
actual Pi 5 GPIO access goes through `/dev/gpiochip*` via `rpi-lgpio`/`lgpio` (§4.2), which is
already reachable through the pre-existing `uucp` group membership `stellarmate` has — `gpiomem*`
access isn't actually on that path. The rule is kept so `/dev/gpiomem*` does what its name implies
on both Pi models regardless, not because anything currently depends on it.

### 4.2 `lgpio` + `rpi-lgpio`: the actual Pi 5 GPIO compatibility layer

**Where**: `pifinder_stellarmate_setup.sh` ("Installing Python requirements" phase, `[Pi5]` block)
and, separately, `bin/pifinder_pre_start.sh` (boot-time re-verification — see §4.3 for why this
exists in two places).

`RPi.GPIO`, the library PiFinder's own hardware code (`keyboard_pi.py`, `displays.py`) is written
against, has **no knowledge of the RP1 chip at all** — it simply doesn't support Pi 5. Rather than
rewriting PiFinder's GPIO calls, this project installs **`rpi-lgpio`**, a drop-in package that
exposes the exact same `RPi.GPIO` import surface but implements it on top of **`lgpio`**, a C
library (from `github.com/joan2937/lg`) that does understand RP1's `/dev/gpiochip*` interface.
`import RPi.GPIO as GPIO` in PiFinder's code keeps working completely unmodified — the substitution
happens entirely at the package level, not in PiFinder's source.

Setup sequence (`[Pi5]`-gated, `hw_model` grep on `/proc/device-tree/model`):

1. Install `swig` (pacman) — a build dependency for `lgpio`'s Python bindings.
2. Clone `https://github.com/joan2937/lg` to `~/lgpio-src` (only if not already present).
3. Build and install `liblgpio.so` (`make` + `sudo make install` + `ldconfig`), skipped if
   `/usr/local/lib/liblgpio.so` already exists.
4. Install the `rpi-lgpio` + `lgpio` Python packages — preferring pre-built wheels from this
   project's own `packages/` directory (`pip install --no-index --find-links=packages/`, no
   internet needed) and falling back to PyPI only if those aren't present.

### 4.3 Why the same lgpio setup exists a second time, at boot

**Where**: `bin/pifinder_pre_start.sh`, run as `ExecStartPre` under `pifinder.service` (as root, on
every service start — i.e. every boot).

StellarMate OS uses a BTRFS-snapshot-based update mechanism that can **wipe `/usr/local/lib`** —
exactly where `liblgpio.so` from §4.2 lives — on an OS update, without necessarily removing the
already-`pip install`ed `rpi-lgpio`/`lgpio` *Python* packages (those live in the venv, a different
filesystem location). The result, if unhandled: `import RPi.GPIO` succeeds (the Python package is
still there), but every actual GPIO call fails at the C-library level, since `liblgpio.so` is gone —
a much more confusing failure mode than a clean import error.

`pifinder_pre_start.sh` re-verifies and, if necessary, **rebuilds** `liblgpio.so` on every single
service start, cheaply:

- Ensures `/usr/local/lib` is still in `ldconfig`'s search path (`/etc/ld.so.conf.d/local.conf` — also
  lost on a BTRFS reset).
- If `liblgpio.so` is missing, rebuilds it directly with `gcc` from the *already-cloned* source at
  `~/lgpio-src` (which lives under `/home`, and survives a BTRFS reset) — no `swig`, no `make
  install`, no internet needed for this path, just a straight compile-and-link of the already-known
  `.c` files, `install`ed to `/usr/local/lib` and `ldconfig`'d.
- Separately re-installs `rpi-lgpio`/`lgpio` into the venv (from the local `packages/` wheels, no
  internet) if `import RPi.GPIO` isn't importable at all.

This same script also masks `wireplumber`/`pipewire` (they grab the camera's `/dev/video0` and leave
the sensor in a broken I2C state) and removes `pipewire-libcamera` — both for the same underlying
reason: StellarMate's BTRFS snapshot restore can silently re-enable/reinstall things that were
already dealt with once, so anything that must survive a snapshot reset needs to be re-checked at
every boot, not just once at install time.

### 4.4 `/boot/config.txt` overlay differences between Pi 4 and Pi 5

**Where**: `pifinder_stellarmate_setup.sh`, `/boot/config.txt` phase, branching on the same
`hw_model` detection used throughout.

Both models get `dtparam=spi=on`, `dtparam=i2c_arm=on`, `dtparam=i2c_arm_baudrate=10000`,
`dtoverlay=pwm,pin=13,func=4` (PWM on GPIO13), and `dtoverlay=imx296` (the camera sensor), but differ
on two overlays:

| | Pi 4 | Pi 5 |
|---|---|---|
| Extra PWM overlay | — | `dtoverlay=pwm-2chan` |
| UART3 | `dtoverlay=uart3` | **deliberately omitted** |

- **`pwm-2chan`** is Pi-5-only because a single-channel `pwm` overlay alone doesn't cover the pin
  PiFinder needs there on RP1's pin mapping the way it does on BCM2711 — the 2-channel overlay is
  needed to get the same GPIO13 PWM output. (Conversely, `pwm-2chan` is deliberately **not** added
  on Pi 4, where it would remap PWM to GPIO19 instead of GPIO13 — an explicit inline warning in the
  script flags this so it doesn't get "simplified" into a shared code path by mistake.)
- **`uart3` is Pi-5-specific poison**: on Pi 4/BCM2711, `dtoverlay=uart3` puts UART3 on GPIO4/5, with
  no conflict. On Pi 5/RP1, the *same* overlay instead occupies **GPIO9**, which is also
  **SPI0-MISO** — enabling it would silently break SPI, which the OLED display and keypad both
  depend on. So it's included for Pi 4 and *explicitly excluded* for Pi 5, with a `TODO` left in the
  script noting that a Pi 5-specific, SPI-safe UART pin pair still needs to be identified for GPS
  dongles that need a UART rather than USB.

### 4.5 `displays.py` / `keyboard_pi.py` GPIO patches — Bookworm-only, not part of the SMOS/Arch story

**Where**: `bin/patch_PiFinder_installation_files.sh`, the "Patch displays.py for Pi5 SPI GPIO" and
"Patch keyboard_pi.py for Pi 5" blocks.

Worth flagging explicitly since these look Pi-5-relevant at a glance but **are not part of how Pi 5
actually works under SMOS today**: both are gated `should_apply_patch "2.3.0" "P5" "bookworm"` —
i.e. only apply on a Debian/Raspberry Pi OS ("bookworm") install, never on Arch/SMOS
(`current_os` reports `arch` there). They look like an earlier, Debian-targeted attempt at Pi 5 GPIO
compatibility (stubbing out `RPi.GPIO` calls entirely in `keyboard_pi.py`, and switching
`displays.py`'s SPI serial setup to `noop()`/port 10) that predates the `rpi-lgpio` drop-in approach
in §4.2, which supersedes it for the environment this project actually targets. They're harmless
dead code for SMOS (the `bookworm` gate means they never fire), kept presumably in case a
Debian-based Pi 5 install is ever supported again — but anyone reading the patch script expecting to
find "the" Pi 5 GPIO fix here would be looking in the wrong place; the real one is §4.2's
`rpi-lgpio`/`lgpio` install, which needs no source-level patch to PiFinder at all.

### 4.6 python-libinput 0.1.0 manual install

**Where**: `pifinder_stellarmate_setup.sh`, right after the main `requirements.txt` install;
`diffs/keyboard_pi_smos.diff` for the corresponding source-level API migration.

Not Pi-5-specific on its own (it's a Python-3.12+/Arch packaging issue — Arch ships a newer Python
than upstream PiFinder's `requirements.txt` was written against), but part of the same "get a
modern Arch/Pi-5-era stack running a 2.6.0-era PiFinder" story, so included here for completeness:
upstream's pinned `python-libinput==0.3.0a0` isn't installable at all (that pre-release isn't
published), and the next viable version, 0.1.0, ships a `setup.py` that imports the `imp` module —
removed in Python 3.12. The setup script downloads 0.1.0's source directly, patches its `setup.py`
in place (`sed`, swapping the removed `imp.load_source` for an `importlib.util`-based equivalent),
and installs from the patched source tree; `requirements.txt` itself gets `python-libinput`
commented out so a subsequent `pip install -r requirements.txt` doesn't try to reinstall the
unpatched, broken version over it.

`diffs/keyboard_pi_smos.diff` is the corresponding source patch for the resulting API surface
change: 0.1.0's `KeyboardEvent.get_key()` returns a plain `enum.Enum`
(`libinput.evcodes.Key`), not an `IntEnum` the way upstream's pinned version presumably does —
`int(key)` raises `TypeError` on every single keypress; fixed by reading `.value` instead. This bug
was self-inflicted (introduced by this project's own API-migration patch, not present upstream), so
it's not something to report anywhere — it only exists because this project moved to a newer
python-libinput than upstream uses at all.

---

## Housekeeping: stale patch file

`diffs/gps_menu.diff` is **not referenced anywhere** in `bin/patch_PiFinder_installation_files.sh`
— grepping the script for its filename returns nothing. It appears to be an earlier, malformed
attempt at the GPS-menu-option change that `diffs/menu_structure_py.diff` now handles correctly
(the old file's hunk has mismatched/duplicated brace lines and wouldn't apply cleanly even if it
were wired in). Safe to delete as a cleanup item; not otherwise blocking anything.
