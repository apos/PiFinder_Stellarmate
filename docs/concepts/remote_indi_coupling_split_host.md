# Concept: PiFinder as a Separate Device, Mount Bridge on a Remote Control Host

## Status

**Implemented and verified end-to-end across two physical devices (2026-07-29).** R-CH1 and
R-ROLE1 are implemented on branch `feature/pifinder-host-setup-tile` as "role cards" in the Mount
Bridge tile (the standalone R-PF1 tile and the first-attempt device-level role banner were both
built and then deliberately replaced - see the Device role model below for why). Live cross-device
verification: one Pi as PiFinder host (role card -> profile with local PiFinder LX200 only, own
LAN IP displayed), a second Pi as control host (role card -> remote `PiFinder LX200@<ip>:7624` +
Mount Bridge + mount driver) - the bridge on the control host coupled the remote PiFinder to
LX200 OnStep, drift readout live, goto-forward active. The INDI-only install mode
(`setup_indi_only_install_mode.md`) was used on both devices along the way. Extended live testing
the same day also surfaced and resolved a real reliability concern (Mount Bridge tile periodically
flashing "not coupled") - see Known Risks below; short version: it was a client-side status-poll
timeout, not an actual interruption to the coupling or correction logic. Originally written up
after a design discussion (2026-07-26) about supporting PiFinder hardware that never runs
StellarMate at all - it just exposes its own solved position over the network, while a separate,
more capable computer does the actual mount coupling.

## 1. Overview

Today, this project assumes PiFinder and the Mount Bridge coupling logic live on the *same*
machine (a StellarMate Pi running both PiFinder and, optionally, `indi_pifinder_mount_bridge`
against a locally-running mount driver). That's unnecessarily heavy for a real, common setup:
PiFinder on a weaker, dedicated Pi (e.g. Pi4/2GB) purely as a finder/push-to aid, while the actual
imaging/EAA/mount-control work happens on a separate, stronger machine - a StellarMate/Astroberry
Pi, a StellarMate Pro, or a plain Linux Intel box running KStars/Ekos. Many fixed observatory
setups already have a dedicated mount-control computer this way.

INDI already has a first-class mechanism for exactly this: **remote drivers**. A driver process
doesn't have to run on the same `indiserver` instance that uses it - `indiserver` can proxy a
driver that's actually running on a different host's `indiserver`, transparently, over TCP/IP. This
concept applies that mechanism to split PiFinder LX200 (must run near PiFinder, since it talks to
PiFinder's own local position server) from Mount Bridge (should run near the mount, since it needs
low-latency access to both PiFinder's *and* the mount's INDI properties).

## 2. Use Cases

- A PiFinder owner with a Pi4/2GB unit that can't comfortably also run a full StellarMate/KStars
  stack - PiFinder just needs to expose its position, nothing else.
- A fixed observatory with an existing, dedicated mount-control computer (any INDI-capable Linux
  box) - couple PiFinder to it without touching that computer's existing setup beyond adding two
  small driver entries.
- A StellarMate Pro (or equivalent) with no PiFinder hardware attached at all, coupling to a
  PiFinder that lives on a completely separate, cheaper Pi.
- Anyone on Astroberry or stock Ubuntu+KStars/Ekos wanting the same one-click Coupling-preset UX
  this project already built for StellarMate, without adopting StellarMate itself.

## 3. Architecture

```mermaid
flowchart LR
    subgraph PF["PiFinder host (any Pi, PiFinder software already running)"]
        POS["pos_server.py\n(127.0.0.1:4030)"]
        LX["indi_pifinder_lx200\n(own indiserver, e.g. :7624)"]
        POS -->|local TCP| LX
    end

    subgraph CH["Control host (StellarMate / Astroberry / Ubuntu+KStars / StellarMate Pro)"]
        WM["INDI Web Manager\n(profile: Mount Bridge + real mount driver)"]
        MB["indi_pifinder_mount_bridge"]
        MT["real mount driver\n(e.g. LX200 OnStep)"]
        WM --- MB
        WM --- MT
    end

    LX -.->|"remote driver\n(network, INDI protocol)"| WM
```

- **PiFinder host**: runs PiFinder as usual (unmodified), plus a small, standalone `indiserver`
  process serving just `indi_pifinder_lx200`, listening on the LAN. No Web Manager needed here -
  one driver, one fixed port, started by a systemd unit at boot. No Mount Bridge, no real mount
  driver, no PiFinder-application patching by this project at all - PiFinder itself is assumed
  already installed and running, by whatever means the user chose.
- **Control host**: runs the *actual* INDI Web Manager, with the profile containing
  `indi_pifinder_mount_bridge` and the real mount driver as normal local drivers, plus one *remote*
  driver entry pointing at `<pifinder-host-ip>:<pifinder-port>` for PiFinder LX200. From Mount
  Bridge's point of view, PiFinder LX200 is just another INDI device - the remote-driver mechanism
  makes the network hop invisible to it.
- The Control Center's Mount Bridge tile (this project's existing UI) can run on the control host
  exactly as it does today - `indi_client.py`/`webmanager_client.py` already have zero dependency
  on PiFinder's own Python code, only on INDI/Web-Manager network calls, so nothing there changes.

## 4. Requirements

### PiFinder host
- PiFinder itself already installed and running (any distribution) - out of scope for this
  project to install.
- On StellarMate specifically (today's only real target - a Pi running the *full* install, real
  PiFinder hardware attached), this can reuse the existing Web Manager + Mount Bridge tile's own
  "INDI Web Manager" setup checklist (steps 1-3: Profile, KStars Link, Drivers) almost unchanged -
  see R-PF1 below. On a non-StellarMate PiFinder host (stock Raspberry Pi OS/Debian, no Web
  Manager), the original plan still applies: a minimal standalone `indiserver -v -p <port>
  indi_pifinder_lx200` systemd service, no Web Manager needed - see the existing draft howto,
  [`docs/draft/stock_debian_pifinder_mount_howto.md`](../draft/stock_debian_pifinder_mount_howto.md)
  (from issue #37), for the apt repo/package steps already researched for that case.
- The chosen port reachable from the control host's LAN (firewall/network consideration, not just
  a config value) - StellarMate's own `indiserver` already binds `0.0.0.0`, not just localhost
  (live-verified 2026-07-28, `ss -tlnp` showed `LISTEN 0.0.0.0:7624`), so nothing extra needs
  configuring there beyond the firewall itself.

**R-PF1 (new, StellarMate PiFinder-host case only): a dedicated "PiFinder Host Setup" tile in the
Control Center**, next to the existing Mount Bridge tile - the same "INDI Web Manager" checklist
pattern (Profile / KStars Link / Drivers) but scoped to just steps 1-3, and only ever toggling
`PiFinder LX200` (never Mount Bridge - that has no business running on this host in the split
architecture). Must also **prominently display this device's own LAN IP address** - live-verified
2026-07-28 that a user setting this up needs to *copy that IP to the other machine*, and hunting
for it themselves (`ip addr`, router admin page, ...) is real friction this project can remove for
free (`gui_installer/server.py` already has `_get_all_ips()`, used today for the remote-links
tile - same source, new place to show it). The port practically never needs to be user-facing here
(defaults to 7624, StellarMate's own Web Manager profile already shows/lets you change it) - the IP
is the one piece of information the user actually needs handed to them.

### Control host
- Resolved, live-verified 2026-07-28 against a real StellarMate Web Manager (was an open question
  before): **StellarMate's own Web Manager profile editor has a first-class "Remote Drivers" text
  field** (`driver_label@host:port`, comma-separated for multiple), and the underlying REST API
  models it explicitly too - `POST /api/profiles/{profile}/drivers` accepts entries shaped like
  `{"label": "PiFinder LX200", "remote": "@<host>:<port>"}` (`ProfileDriver` schema, confirmed via
  the Web Manager's own `/openapi.json`) alongside plain local `{"label": ...}` entries for Mount
  Bridge and the real mount driver in the same profile. No manual `drivers.xml`/profile-JSON
  surgery needed, and the KStars Ekos Profile Editor fallback mentioned below is no longer the only
  path - StellarMate's own Web Manager UI/API already covers it directly.
  - Manual path (works today, no new code needed): type `PiFinder LX200@<pifinder-host-ip>:7624`
    into the Mount Bridge profile's own "Remote Drivers" field in Web Manager.
  - Fallback if a non-StellarMate control host's Web Manager doesn't expose this: KStars' own Ekos
    Profile Editor lets you add a remote driver by host:port directly, in every version researched
    so far.

**R-CH1 (new): a Control Center workflow on the control host to add/update the remote PiFinder
entry without leaving this project's own UI** - an IP (+ optional port, default 7624) input, wired
through `webmanager_client.py`'s existing `set_profile_drivers()`/`_set_driver_membership()`
machinery (already used for local PiFinder LX200/Mount Bridge membership toggling today - just
needs the `remote` field threaded through as an optional argument) rather than sending the user to
Web Manager's own page to hand-type the `label@host:port` string themselves. Natural home: extend
the Mount Bridge tile's existing step 3 "Drivers" row, since this is the same underlying
"is PiFinder LX200 in this profile" toggle, just choosing *how* (local vs. a given remote address)
instead of only on/off.
- Build and install `indi_pifinder_mount_bridge` (same build script as today, already portable to
  any distro with `libindi-dev` present - see concept doc 2 for the apt/pacman abstraction this
  still needs).
- Optionally, this project's Control Center (Mount Bridge tile only) for the same one-click
  Coupling UX - see concept doc 2 for how a lighter, non-StellarMate install of just that piece
  would work.

### Both roles
**R-HELP1 (new): `help.html` needs its own section for this whole split-host setup**, and both new
UI pieces (R-PF1, R-CH1) need an explicit pointer to it (an info-icon link, same pattern as every
other setup step already uses) - direct feedback (2026-07-28) that a feature like this is
unusable without the user being told, in the UI itself, that a guide exists and where to find it,
not just documented somewhere in the repo they'd have to already know to look for.

### Device role model (R-ROLE1)

Settled in a design discussion 2026-07-28, after a first attempt got it wrong. The trigger: with
both tiles (Mount Bridge, PiFinder Host Setup) always visible, nothing told the user which role
the current device actually plays - you could only guess, or infer it from seeing a physical OLED.
The first fix was a device-level banner deriving the role from whether `~/PiFinder` exists.
**Rejected, correctly**: the directory only proves what a device *cannot* do (no PiFinder installed
= cannot be a PiFinder host); its presence proves nothing about how the device is being *used*.
Two fully-installed PiFinders may pair up with one acting as the other's control host, and the same
device may be used differently from one session to the next - nobody should have to reinstall
anything to switch. (Also verified live, and worth stating because the question came up:
`--mode=indi_only` never touches `~/PiFinder` - its code path exits before any of the full mode's
delete/reinstall logic is even reached. Full install and INDI-only coexist on one device; INDI-only
over an existing full install just refreshes the INDI drivers.)

**The model: a device has no role - the running INDI profile has one.** The profile is already the
mechanism users know and switch for exactly this purpose ("what runs on this device right now"),
so the role is a *derived property of a profile*, never a stored device setting:

| Profile contains | Role of that profile |
|---|---|
| PiFinder LX200 (local) + Mount Bridge + mount driver | **All-in-one**: couples this device's own PiFinder to its own mount |
| PiFinder LX200 (local) only | **PiFinder host**: shares this device's position on the network, nothing else |
| Mount Bridge + mount driver + PiFinder LX200 as *remote* entry | **Control host**: couples a PiFinder running on another device |
| none of these | no PiFinder involvement / not configured yet |

Consequences, each falling out of the model rather than needing separate design:

- **Role switching = profile switching.** No new toggle, no persistent "device mode", no
  reinstalling. A user needing both setups keeps two profiles (e.g. "Standalone" and "Host for
  observatory") and starts whichever applies tonight - exactly what profiles are for.
- **Installation state is only the capability boundary.** A profile with a local PiFinder LX200 on
  a device without `~/PiFinder` is a *configuration error to flag*, not a role signal. Hiding the
  PiFinder Host Setup tile when PiFinder isn't installed remains valid - that's capability, not
  role.
- **R-ROLE1 (UI requirement): the role is displayed next to the profile selection** the tiles
  already share - e.g. `Profile "Simulation PFSM" → All-in-one: couples this device's PiFinder to
  LX200 OnStep` - derived live from the selected profile's actual driver entries, updating whenever
  the profile (or its contents) changes. This *replaces* the device-level banner from the first
  attempt: no static claims about the device, only honest statements about the selected profile.
- **Depends on R-CH1's three-state driver handling.** Distinguishing rows 1/2 from row 3 requires
  knowing whether PiFinder LX200 is in the profile *locally* or as a *remote* entry - exactly the
  absent/local/remote@host:port distinction R-CH1 introduces in the Drivers step, readable via the
  Web Manager's `GET /api/profiles/{item}/remote` (verified to exist, 2026-07-28).

Named and deliberately out of scope for now: a cross-device view ("show me all my devices and who
is currently doing what") - its own chapter if it ever becomes a real need, not part of this.

## 5. Design Principles

- **PiFinder host stays minimal and untouched.** This project should never patch or manage
  PiFinder's own application code on a host where it isn't also doing the full StellarMate install
  - only the one small driver + its service.
- **No new protocol.** Reuse INDI's own remote-driver mechanism exactly as designed - don't invent
  a custom network bridge or tunnel.
- **Security is the user's network, not ours to solve here.** INDI has no built-in authentication;
  exposing `indi_pifinder_lx200` on the LAN means anyone on that network can query (and, if they
  also reach the Mount Bridge/mount devices, potentially command) it. Acceptable for a typical
  home/observatory LAN, same trust model INDI itself already assumes everywhere else - call this
  out explicitly in user-facing docs rather than silently assuming it away.

## 6. Test Strategy

- Unit-testable pieces: none really new here beyond concept doc 2's OS-abstraction work - this
  concept is mostly about *how the pieces are wired together*, not new script logic.
- Needs live, cross-machine verification once built: two real machines (or two VMs) on the same
  LAN, PiFinder host + control host, confirming the remote-driver hop actually works end-to-end -
  can't be verified on a single Pi the way most of this project's work has been so far.

## 7. Known Risks / Open Questions

- ~~Remote-driver UX varies by Web Manager.~~ **Resolved 2026-07-28** - StellarMate's own Web
  Manager supports it natively (see Requirements, Control host). Still genuinely open for
  non-StellarMate Web Managers (Astroberry, plain `indiwebmanager`) - not yet checked against those.
- ~~Physical cross-machine verification pending.~~ **Resolved 2026-07-29**: verified live across
  two real Pis on the same LAN - PiFinder host role on one, control host role on the other, bridge
  coupling the remote PiFinder to the mount with live position data. Note the remaining related
  risk below (reconnect behavior) is now *more* relevant, not less, since the hop is real.
- **PiFinder version/protocol drift**: `pos_server.py`'s LX200 subset and its fixed port (4030) are
  assumed stable across "any PiFinder install" - true for the current upstream, but not guarded
  against future changes the way this project already guards its own installer against.
- **Network reliability**: this project already found (2026-07-26 live testing) that
  `indi_pifinder_lx200` has no reconnect logic if its connection to `pos_server.py` drops (see
  basic-memory `pifinder-stellarmate/00075`) - a real network hop (not just localhost) makes that
  kind of drop *more* likely, not less, so that gap matters more here than it did before. **Still
  open** - not the same issue as the one resolved just below, which looked identical from the
  Control Center's UI but had a different, unrelated cause.
- ~~Mount Bridge tile periodically flashes "not coupled" during cross-device coupling.~~
  **Resolved 2026-07-29**, and the underlying worry it raised - does the split-host coupling
  actually keep correcting during these flashes, or is real data lost - **answered live: no data
  loss, ever**. Root-caused via three simultaneous independent property polls during actual
  occurrences (PiFinder LX200, the mount, and Mount Bridge's own `DRIFT_STATUS`) plus a direct
  visual confirmation in Ekos (the mount was seen actively correcting *while* the tile showed "not
  coupled") - the entire INDI data path (PiFinder position, mount position, Mount Bridge's own
  correction computation) never stops. The only real fault was `indi_client.py`'s own 3-second
  client-side poll timeout occasionally elapsing while `indiserver` was mid-relay of an unrelated
  burst of mount-driver property updates - a purely local, project-specific bug in this project's
  own minimal INDI client (not stock INDI/libindi, not `indiserver`, not the drivers themselves).
  Fixed by scoping a longer timeout to just the passive background status poll (`server.py`'s
  `/api/mount_bridge_status`), leaving every interactive action's own fail-fast timeout untouched.
  Full diagnostic trail (including the hypotheses ruled out along the way - StellarMate's Web
  Manager driver-restart mechanism, a suspected TCP connection leak, `indiserver` itself hanging,
  the Mount Bridge driver process itself hanging - each disproven with live evidence before finding
  the real cause): basic-memory `pifinder-stellarmate/00079`.

## 8. Effort & Priority

Medium effort for the PiFinder-host side (mostly already drafted in issue #37, needs an automated
installer wrapped around it rather than a manual howto). Higher effort/uncertainty for the control-host
Web-Manager-remote-driver UX question, which needs research against real StellarMate/Astroberry
Web Manager UIs before it can be scoped precisely.

## Related

Issue #37 (stock Debian PiFinder howto - the PiFinder-host half of this is largely that issue,
reframed as an automated install rather than a manual walkthrough). See concept doc
[`setup_indi_only_install_mode.md`](setup_indi_only_install_mode.md) for how the installer itself
would be structured, and [`setup_script_test_suite.md`](setup_script_test_suite.md) for testing
the new logic this requires.
