# Concept: PiFinder as a Separate Device, Mount Bridge on a Remote Control Host

## Status

**Concept - not implemented, but the control-host half's key open question is now resolved
(2026-07-28, verified live against a real StellarMate Web Manager - see Requirements and Known
Risks below).** Written up after a design discussion (2026-07-26) about supporting
PiFinder hardware that never runs StellarMate at all - it just exposes its own solved position
over the network, while a separate, more capable computer does the actual mount coupling.

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
- A working INDI stack with dev headers to compile against (`libindi-dev`, `cmake`,
  `build-essential`/equivalent) - **not preinstalled on stock Raspberry Pi OS/Debian**, unlike
  StellarMate where it ships as part of the base OS image. See the existing draft howto,
  [`docs/draft/stock_debian_pifinder_mount_howto.md`](../draft/stock_debian_pifinder_mount_howto.md)
  (from issue #37), for the exact apt repo/package steps already researched for this.
- Build and install `indi_pifinder_lx200` only (not Mount Bridge - that stays on the control host).
- A systemd service running a minimal `indiserver -v -p <port> indi_pifinder_lx200` (not the full
  Web Manager - a fixed single-driver `indiserver` is enough and simpler to reason about).
- The chosen port reachable from the control host's LAN (firewall/network consideration, not just
  a config value).

### Control host
- Whatever INDI Web Manager it already has (StellarMate's own, Astroberry's, or a plain
  `indiwebmanager` install per issue #37's draft) needs a way to add PiFinder LX200 as a *remote*
  driver, not a local one. Needs verifying per Web Manager UI - some Web Manager profile editors
  expose "Remote" driver entries directly; if a given one doesn't, this project may need to
  document (or script) the underlying `drivers.xml`/profile-JSON edit directly instead.
  **Open question, not yet verified against a real Web Manager UI.**
  - Fallback for when it's not available cleanly: KStars' own Ekos Profile Editor lets you add a
    remote driver by host:port directly, in every version researched so far.
- Build and install `indi_pifinder_mount_bridge` (same build script as today, already portable to
  any distro with `libindi-dev` present - see concept doc 2 for the apt/pacman abstraction this
  still needs).
- Optionally, this project's Control Center (Mount Bridge tile only) for the same one-click
  Coupling UX - see concept doc 2 for how a lighter, non-StellarMate install of just that piece
  would work.

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

- **Remote-driver UX varies by Web Manager.** Not yet confirmed whether StellarMate's own Web
  Manager UI supports adding a remote driver as easily as a local one - if not, this project may
  need its own small helper (script or Control Center feature) to do that edit for the user.
- **No physical test hardware for the split scenario yet** (two separate machines on a LAN) - this
  entire concept is currently unverified beyond the INDI protocol's own documented remote-driver
  support.
- **PiFinder version/protocol drift**: `pos_server.py`'s LX200 subset and its fixed port (4030) are
  assumed stable across "any PiFinder install" - true for the current upstream, but not guarded
  against future changes the way this project already guards its own installer against.
- **Network reliability**: this project already found (2026-07-26 live testing) that
  `indi_pifinder_lx200` has no reconnect logic if its connection to `pos_server.py` drops (see
  basic-memory `pifinder-stellarmate/00075`) - a real network hop (not just localhost) makes that
  kind of drop *more* likely, not less, so that gap matters more here than it did before.

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
