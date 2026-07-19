# Upstream PR templates

Ready-to-file PR descriptions for every patch identified as upstream-relevant in
[`docs/upstream_patch_inventory.md`](upstream_patch_inventory.md). All target `brickbots/PiFinder`'s
**`main`** branch (per that repo's own `CLAUDE.md`: "main is the integration/development branch. All
PRs target main"). The `apos/PiFinder` fork already exists and `gh` is already authenticated as
`apos` — technically ready to open as soon as the prerequisite below is satisfied.

## Prerequisite for all of the below (not yet done)

Every diff in this project has only ever run **already patched** — on top of the previous patch in
the chain, never against a clean checkout. Before opening any of these PRs, verify each one still
applies cleanly (or note what's drifted) against the *current* `brickbots/PiFinder` `main` tip in an
isolated worktree, not the live, patched `~/PiFinder` checkout. PR 1 in particular rests on a finding
(§ below) that was only checked once, in a throwaway worktree, and needs re-confirming before it's
filed.

Recommended order: **PR 1 → PR 2 → PR 3**, each depending on the previous being merged (or at least
open) on `main`. PRs 4–7 are independent of that chain and of each other.

---

## PR 1 — Bugfix: restore the missing `"debug"` command handler in `camera_interface.py`

**Depends on**: nothing. **Blocks**: PR 2, PR 3.

**⚠️ Re-verify before opening.** This is based on a single check against `main` in an isolated
worktree on 2026-07-19 (see basic-memory `pifinder-stellarmate/00022`), not on real hardware, and
not re-checked since. Confirm the handler is still absent on the current `main` tip before filing —
it's entirely possible this has already been fixed independently.

### Suggested title
`Fix: "Tools -> Test Mode" no longer substitutes a test image (dead command handler)`

### Suggested body

> ## What's broken
>
> `ui/callbacks.py`'s `activate_debug()` (wired to the "Test Mode" menu item) sends a `"debug"`
> command to the camera process's command queue, same as it always has. On `main`, nothing consumes
> that command any more — `camera_interface.py`'s image-capture loop has no `if command == "debug":`
> branch. The console still prints "Test Mode Activated" and the GPS/date faking still happens (those
> live elsewhere), but the actual image substitution — the entire visible point of Test Mode — silently
> does nothing.
>
> ## How I found it
>
> While preparing an unrelated feature PR that touches this same command loop, I diffed
> `camera_interface.py` against an older PiFinder release where the feature still worked end-to-end,
> and found the handler present there but missing on `main`.
>
> ## The fix
>
> Restore the handler (this is the block present on the older release, before whatever change
> dropped it — happy to adjust to match `main`'s current structure exactly):
>
> ```python
> if command == "debug":
>     debug = not debug
> ```
>
> plus whatever `debug`-gated branch selects the canned test image vs. live camera capture in the
> surrounding loop (present but unreachable without the command handler above).
>
> ## Testing
>
> Manually toggled Test Mode via the OLED menu before/after the fix, confirmed the displayed image
> switches to/from the canned test image as expected. [Attach before/after screenshots or a short
> clip once verified against `main` directly.]

---

## PR 2 — Feature: reliable Test Mode toggle + status via the HTTP API

**Depends on**: PR 1 (merged or open). **Blocks**: PR 3.

### Suggested title
`Add POST /api/debug_solve + debug_solve status field for reliable Test Mode control`

### Suggested body

> ## Motivation
>
> Two gaps in driving "Tools → Test Mode" (`activate_debug()`) programmatically:
>
> 1. **No reliable trigger.** The only way to activate it via the API today is simulating the
>    menu-navigation keypresses through `POST /api/key` — in practice unreliable (keypresses can be
>    dropped, or the menu cursor can end up on the wrong item if a request is even slightly delayed,
>    since it depends on exact prior menu state).
> 2. **No way to read the state back at all.** The on/off flag (`debug` in
>    `camera_interface.py`'s capture loop) is a bare local variable in a subprocess, invisible to
>    anything else — no way for a client to know whether Test Mode is currently on without guessing.
>
> This is useful for anything scripting or monitoring PiFinder over its HTTP API — test harnesses,
> remote-control integrations, third-party dashboards — not something specific to any one downstream
> integration.
>
> ## Changes
>
> - **`state.py`**: new `SharedStateObj.debug_solve()` / `set_debug_solve(v: bool)`, backed by a new
>   `__debug_solve: bool = False` field — makes the toggle state visible outside the camera process
>   for the first time.
> - **`camera_interface.py`**: the existing `if command == "debug":` handler (see PR 1) now also
>   calls `shared_state.set_debug_solve(debug)`, so the shared flag stays in sync with the local
>   toggle at the one place that already changes it.
> - **`main.py`**: new `ui_command == "toggle_debug_solve"` case, `command_queues["camera"].put("debug")`
>   — a direct bridge from the existing `ui_queue` (already passed through to the web server process)
>   to the same command the menu item sends, without simulating any keypresses at all.
> - **`api_extensions.py`**: new `POST /api/debug_solve` (puts `"toggle_debug_solve"` on `ui_queue`);
>   `GET /api/status` gains a `debug_solve` field reporting the current state.
>
> ## Testing
>
> Verified against a debug/fake-hardware instance: toggling via the new endpoint reliably flips
> state on every call (no drops across repeated rapid toggles in testing), and `GET /api/status`'s
> `debug_solve` field tracks it correctly, including staying correct when Test Mode is instead
> toggled the old way, through the OLED menu.
>
> One caveat worth noting in review: on a debug/fake-hardware camera backend, `debug_solve: false`
> doesn't mean "showing a live camera image" — a fake backend has no live camera to fall back to
> either way, so it keeps cycling its own synthetic test images regardless of this flag. The flag
> only reflects whether the *fixed* canned test image is being substituted for whatever the backend
> would otherwise produce.

---

## PR 3 — Feature: fall back to the debug camera instead of crashing when no camera is attached

**Depends on**: PR 2 (merged or open, for the `debug_solve` state this uses).

### Suggested title
`Camera process: fall back to debug camera on init failure instead of crashing`

### Suggested body

> ## Motivation
>
> If no camera is physically attached (or it fails to initialize for any other reason),
> `CameraPI.__init__()` lets `Picamera2()`'s exception propagate uncaught. That crashes the *entire*
> camera subprocess before `get_image_loop()` is ever reached — which takes every other command on
> that process's queue down with it too, since they're all serviced by the same loop. This includes
> Test Mode (see PR 2): a crashed process can't be toggled into debug mode, since it has to already
> be running to receive the toggle at all.
>
> This matters most exactly when Test Mode would be most useful: bench-testing PiFinder's UI/solve
> pipeline without a camera attached, running it on hardware with a temporarily broken camera, or in
> CI. Right now that specific, common scenario doesn't degrade gracefully — it silently disables a
> whole subsystem instead of falling back to the synthetic-image path that already exists for
> exactly this purpose (`CameraDebug`).
>
> ## Changes
>
> - **`camera_pi.py`**: `get_images()` now wraps `CameraPI(exposure_time)` in a try/except; on
>   failure, logs the error, notifies the console, and falls back to `CameraDebug(exposure_time)`
>   instead of letting the process die.
> - **`camera_interface.py`**: `get_image_loop()` gains an `initial_debug: bool = False` parameter,
>   used to seed the loop's own `debug` state (and sync `shared_state.set_debug_solve()`) from the
>   very first line. The fallback path above passes `initial_debug=True`. Without this, the fallback
>   and the Test Mode toggle's state could independently drift apart — verified as an actual bug
>   during testing: toggling Test Mode "off" while running on the fallback camera left the loop's
>   internal state effectively still "on" underneath a UI that displayed "off", because the fallback
>   had only set the *shared/displayed* flag directly, never the loop's own state variable, and the
>   next toggle click flipped from that real-but-unseen state instead of the one the UI showed.
>
> ## Testing
>
> Verified against hardware with no camera attached: process no longer crashes, `GET /api/status`
> correctly shows `debug_solve: true` immediately on start (no manual toggle needed), and the
> existing Test Mode toggle (PR 2) continues to alternate correctly afterward — including confirming
> it doesn't drift out of sync on the very first toggle, which is what exposed the state-seeding bug
> above during development.

---

## PR 4 — Feature: comprehensive IP address display (`all_ips()`)

**Depends on**: nothing.

### Suggested title
`Show every non-loopback IP address, not just the default-route one`

### Suggested body

> ## Motivation
>
> The Web UI home page and OLED status screen currently show a single IP address
> (`Network.local_ip()` — the address the OS would pick for outbound traffic). On any host with more
> than one active network path — wired Ethernet alongside WiFi, or a WireGuard/VPN tunnel — every
> other address the device is just as reachable on is invisible. This is a plain usability gap, not
> tied to any particular downstream setup: anyone connecting over "the other" interface currently has
> to already know its address some other way.
>
> ## Changes
>
> - **`sys_utils.py`**: new `Network.all_ips()`, parses `ip -4 -o addr show` and returns every
>   non-loopback IPv4 address currently assigned across all interfaces. (`_tty_out=False` on the `sh`
>   call avoids `sh` allocating a pty that would make `ip` colorize its output with ANSI escapes.)
> - **`sys_utils_fake.py`**: matching stub for the fake-hardware test backend.
> - **`ui/status.py`**: OLED status row now shows `", ".join(all_ips())` instead of the single
>   `local_ip()` value, reusing the row's existing horizontal scroller for overflow when there's more
>   than one address.
> - **`server.py`**: the home page's `ip=` template variable does the same join.
>
> ## Testing
>
> Verified on a Pi with both WiFi and wired Ethernet active simultaneously: both addresses now show,
> comma-separated, on the OLED status screen (scrolling correctly when the combined string overflows
> the row) and on the web UI home page.

---

## PR 5 — Feature: WDS/extended-catalog background loader CPU throttling

**Depends on**: nothing.

### Suggested title
`Lower priority + longer yield for the background WDS/extended-catalog loader`

### Suggested body

> ## Motivation
>
> The deferred background loader for the WDS (double-star) and extended catalogs runs at normal
> thread priority with a 50ms yield between batches. On slower hardware this was observed to cause
> visible UI/solve-loop stutter while the background load is in progress.
>
> ## Changes
>
> - `catalogs.py`: the background loader thread calls `os.nice(15)` on start, and its inter-batch
>   yield increases from 0.05s to 0.1s.
>
> ## Testing
>
> Compared UI responsiveness during the initial catalog background-load window before/after, on a
> Raspberry Pi 4. [Attach specific before/after numbers or a description of the test if available —
> this was observed qualitatively during this project's own testing rather than benchmarked
> precisely; worth tightening before filing.]

---

## PR 6 — Feature: `PIFINDER_WEB_PORT` environment override

**Depends on**: nothing.

### Suggested title
`Add optional PIFINDER_WEB_PORT env var to override the 80/8080 auto-detection`

### Suggested body

> ## Motivation
>
> The web server currently always binds port 80 (if running as the `pifinder` service, which can
> claim it) or 8080 otherwise. There's no way to run a second, independent instance alongside an
> existing one — useful for dev/testing (e.g. a hardware-free "fake mode" instance running next to a
> real one) without a source change.
>
> ## Changes
>
> - `server.py`'s `run()`: if the `PIFINDER_WEB_PORT` environment variable is set, binds that exact
>   port instead of the existing auto-detection logic. Completely inert when unset — existing
>   behavior for every current user is unchanged.
>
> ## Testing
>
> Ran two instances simultaneously (`PIFINDER_WEB_PORT=8081` on the second) against the same machine
> without a port conflict; unset behavior verified unchanged (still picks 80/8080 as before).

---

## PR 7 (optional, needs discussion) — Battery-friendly pre-solve sleep behavior

**Depends on**: nothing, but **significantly more invasive than PRs 1–6** — a real behavioral change
to `PowerManager`, not a bugfix or additive API. Recommend opening as a **draft PR or a discussion
issue first**, not a ready-to-merge PR, to get maintainer buy-in on the approach and the specific
timings before investing in a polished patch. Included here for completeness since it was found
during this project's own work, not because it's as low-risk as the others above.

### What it is

`main.py`'s `PowerManager.update()` currently has one sleep policy regardless of whether a plate
solve has ever succeeded. This project's local patch (`diffs/main_py.diff`, not otherwise described
in the inventory doc's §1 list because of its size/risk) adds a small state machine
(`warmup → pre_sleep → retry → solved`) so that *before* the first successful solve, the device
sleeps for 30s between short 2-minute/1-minute wake windows instead of staying fully awake — useful
for battery life while waiting for a first solve (e.g. clouds, or the device sitting powered-on
before being carried to the eyepiece), while normal post-solve sleep behavior (the existing
configured timeout) is unchanged once a solve has actually landed. If solve is lost after having
succeeded once (e.g. clouds roll in), it currently re-enters `warmup` rather than staying in the
post-solve sleep policy.

### Suggested framing when opening

> ## Motivation
>
> [Describe the battery-life motivation and the specific field scenario that prompted this — device
> powered on but not yet solving, e.g. waiting for a clear patch of sky or during initial setup at
> the eyepiece.]
>
> ## Proposed behavior
>
> [Lay out the four states and their timings as above, but flag explicitly that the specific
> durations (120s/30s/60s) are what this project happened to use and are very much up for discussion
> — they haven't been tuned against real battery-life data, just chosen as reasonable-seeming
> defaults.]
>
> ## Open questions for maintainers
>
> - Should this be configurable rather than hardcoded?
> - Is re-entering `warmup` (rather than a lighter recovery state) the right response to losing an
>   established solve, or too aggressive?
> - Any existing telemetry/user reports this should be weighed against?

---

## Not templated: generic-username login support

Noted in the inventory doc (§2) as a lighter-weight alternative to this project's SMOS-specific
`"pifinder"` → `"stellarmate"` hardcoded swap in `server.py`'s `verify_password`/`change_password`
calls: a generic, configurable system-account username (e.g. read from `config.json` or an env var,
defaulting to today's hardcoded `"pifinder"`) would let any downstream integration point login checks
at its own account without needing a source patch at all. Not written up as a full PR template here
since it's speculative — worth proposing only if there's actual appetite upstream for a
configurable-username story; flagged for awareness rather than filed.
