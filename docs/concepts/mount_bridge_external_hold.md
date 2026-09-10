# Concept: Mount Bridge `EXTERNAL_HOLD` — Control Center suspends coupling during guiding

> **Status: concept — not yet implemented.**
> Tracked as [GitHub issue #372](https://github.com/apos/PiFinder_Stellarmate/issues/372)
> (`concept` + `pifinder` labels) on [Project #15](https://github.com/users/apos/projects/15).
> This is the first implementable step of the guiding-awareness concept
> ([session_start_position_reconciliation.md](session_start_position_reconciliation.md) §6,
> [#324](https://github.com/apos/PiFinder_Stellarmate/issues/324)), and the
> Control-Center-side stand-in for what a native
> [Ekos module](ekos_pifinder_module.md) ([#370](https://github.com/apos/PiFinder_Stellarmate/issues/370))
> would eventually do in-process. Update #372 if this concept is promoted, revised, or dropped.

## 1. Overview

While a guiding run is active (dedicated guide camera + Ekos's Guide module or PHD2), several of
the Mount Bridge's automatic behaviours would *harm* the session if they fired — a
threshold-triggered `Sync`/`Goto` is orders of magnitude larger than a guide pulse and kicks the
guide star out of the frame; a dither looks exactly like an unexplained external reposition. Today
the Mount Bridge has no idea guiding is happening
([§6](session_start_position_reconciliation.md), `grep -rn "GUIDE" indi_pifinder_bridge/` → 0).

**This concept** adds the minimum needed to close that gap without an Ekos module:

1. one new switch on the `PiFinder Mount Bridge` INDI driver, `EXTERNAL_HOLD`, that gates its
   *acting* behaviours while leaving its *observing* behaviours live;
2. a Control Center watchdog that reads Ekos's `Ekos::GuideState` over `qdbus` (the CC already
   shells out to `qdbus` for its Ekos integration — see `_ekos_qdbus()` in
   `gui_installer/server.py`) and sets/clears that switch;
3. a small status-page surface so a quiet Bridge has a visible reason.

Everything stays in the existing components. The coupling *mechanism* does not move into KStars —
that is deliberate (headless / SkySafari-only setups keep working).

## 2. Part 1 — `EXTERNAL_HOLD` on the Mount Bridge driver

### 2.1 New properties (group `Main Control`)

| Property | Type | Elements | Notes |
|---|---|---|---|
| `EXTERNAL_HOLD` | Switch (1oM), `IP_RW` | `HOLD_ON` "Hold" · `HOLD_OFF` "Release" (default) | Set by the Control Center; also settable by hand for testing / from the INDI Control Panel |
| `EXTERNAL_HOLD_REASON` | Text, `IP_RO` | `REASON` | Free text, e.g. `guiding: dithering`, `guiding: calibrating`, `""` when released |

A single `bool m_externalHold` (+ the reason string) backs it. `ISNewSwitch` for `EXTERNAL_HOLD`
sets the flag, logs `LOG_INFO` (`"External hold ON - <reason>"` / `"External hold released"`), and
sets `EXTERNAL_HOLD.s` / `EXTERNAL_HOLD_REASON.s` state so it shows correctly in any INDI client.

### 2.2 What it gates in `TimerHit()`

`TimerHit()` is the driver's single periodic callback (`indi_pifinder_bridge/pifinder_mount_bridge.cpp`,
~line 1493). Split its work into *observe* (always) and *act* (skipped while held):

| Keeps running while held | Skipped while held |
|---|---|
| read both `EQUATORIAL_EOD_COORD`s, compute drift, update `DRIFT_STATUS` | `handleAutoCorrectGoto()` / the correct-state path — **no `Sync`/`Goto` to the mount** |
| update `MOUNT_HORIZON_STATUS`, `ORIGINAL_TARGET(_DRIFT)`, `TARGET_SOURCE(_AGE)` | `handleGotoForward()` — a **new** PiFinder target is **not** forwarded (the held-target tracking still runs, so a later release can act on it) |
| Verify/Alert **logging** (the passive "PiFinder and mount disagree by N" warning) | `handleRepositionDetection()`'s **reaction** (Fall 1-4 / `REPOSITION_CONFIRM`) — a dither must not be read as an external reposition |
| Shadow Sync (mirrors commands the Bridge *does* send — while held it sends none, so a no-op) | `handlePiFinderAlignSync()` (sync-on-PiFinder-align, #196) |

Implementation shape: one early branch in `TimerHit()` after the drift computation —
`if (m_externalHold) { updateStatusOnly(); return; }` — or an `actionsAllowed()` guard on each
acting handler. The former is simpler and keeps the skip list in one place.

### 2.3 Interactions and edge cases

- **`MANUAL_TRIGGER` stays honoured while held.** Explicit user action (Sync Now, Goto Held
  Target, …) is an override — the user knows guiding is running. (Optionally: log a warning.)
- **Multi-Point Alignment.** The Control Center will not set `HOLD_ON` while a run is active (it
  checks `ALIGN_PROGRESS` first — §3.3). If `HOLD_ON` arrives mid-run anyway (hand-set), the
  driver logs a warning and lets the run finish; it does not force-abort it.
- **`BRIDGE_MODE` unchanged.** Hold does not change the selected coupling mode — on release the
  Bridge resumes in whatever mode it was in and corrects the accumulated drift on the next tick
  (subject to the mode's own freshness / sanity gates).
- **Config.** `EXTERNAL_HOLD` is *not* persisted (`IUSaveConfig`) — it's a live, externally-driven
  state, meaningless to restore across a restart. On (re)connect it starts `HOLD_OFF`.
- **Readiness watchdog.** The Control Center's `_mount_bridge_readiness_self_heal()` must **skip a
  driver restart while `EXTERNAL_HOLD` is `HOLD_ON`** — a restart mid-guiding-session is actively
  harmful. One `indi_getprop` check (or a cached value from §3) before `restart_mount_bridge_driver()`.

## 3. Part 2 — Control Center watchdog

### 3.1 `_guiding_hold_watchdog(interval=3)`

Same pattern as `_truth_injector_watchdog()` / `_mount_bridge_readiness_watchdog()` — a daemon
thread started once from `main()`.

```
HELD_STATES = { GUIDE_CALIBRATING, GUIDE_GUIDING, GUIDE_DITHERING,
                GUIDE_MANUAL_DITHERING, GUIDE_SUSPENDED, GUIDE_REACQUIRE }
RELEASE_DEBOUNCE_S = 15

idle_since = None
loop every `interval`:
    gs = _ekos_guide_status()            # int, or None if Guide module not up
    if gs is None:
        continue                         # Ekos/Guide absent -> don't touch EXTERNAL_HOLD at all
    want_hold = gs in HELD_STATES
    if want_hold:
        idle_since = None
    else:
        idle_since = idle_since or monotonic()
        want_hold = (monotonic() - idle_since) < RELEASE_DEBOUNCE_S   # §6.3: don't release on one missed frame
    reason = _guide_state_label(gs) if want_hold else ""
    _set_mount_bridge_external_hold(want_hold, reason)                # idempotent: only writes on change
```

### 3.2 Two new helpers

- **`_ekos_guide_status()`** — `qdbus6 org.kde.kstars /KStars/Ekos/Guide org.kde.kstars.Ekos.Guide.status`
  → `int`. Returns `None` on any error (Guide module not instantiated, Ekos not running, timeout).
  The existing `_ekos_qdbus()` is hardwired to the `/KStars/Ekos` object path — either generalise
  it to take a path, or add this focused helper.
- **`_set_mount_bridge_external_hold(on: bool, reason: str)`** — writes
  `PiFinder Mount Bridge.EXTERNAL_HOLD` (+ `EXTERNAL_HOLD_REASON`) via the existing
  `indi_client` path. Tracks the last value it wrote in a module global and **skips the write when
  unchanged**, so it doesn't spam INDI or the driver log every 3 s.

### 3.3 Guards

- Do nothing if `EXTERNAL_HOLD` isn't a known property on the Bridge yet (old driver) — log once,
  then stay quiet.
- Do not set `HOLD_ON` while `ALIGN_PROGRESS` shows a Multi-Point run in progress.
- If the watchdog thread itself dies, it must not leave the Bridge stuck held — a `try/finally`
  that clears `EXTERNAL_HOLD` on unexpected exit, plus the driver could self-release after a long
  timeout with no watchdog refresh (a "dead-man" — optional for v1, listed under §6).

### 3.4 `GuideState` enum

`Ekos::GuideState` is an internal KStars enum and its integer values have been renumbered across
releases. **Do not hardcode from memory** — read them live: run guiding in the simulator, poll
`Ekos.Guide.status` through each phase (idle → calibrating → guiding → dithering → aborted), record
the integers on the tested KStars version, and pin them in `server.py` with a comment naming that
version (same approach as the `ekosStatus` enum comment already in `server.py`).

## 4. Part 3 — status-page surface

- `/api/mount_bridge_status` gains `external_hold: bool` and `external_hold_reason: str`.
- The `INDI Mount Bridge` section shows a **neutral** (not red — this is expected, not an error)
  indicator when held: `⏸ Paused — guiding (dithering)`. Matches the project's established rule
  that a control going quiet needs a visible reason (the Coupling-gate hint added to
  `status_page.html` for the Quick Actions row, 2026-09-07).
- The Drift badge / Coupling row reflect "paused" rather than looking idle.

## 5. Test procedure (Full Simulation)

1. Full Simulation running; **Coupling = Auto-correct (Sync)**; a small non-zero drift.
2. Ekos → **Guide**: select the CCD Simulator's guide camera, **Calibrate**, then **Guide**.
3. CC watchdog observes `GUIDE_GUIDING` → sets `EXTERNAL_HOLD = HOLD_ON`. Status page shows the
   paused indicator; driver log: `External hold ON - guiding`.
4. Push the drift past the threshold (Sync the Telescope Simulator to an offset). **Expected:** the
   Bridge does **not** Sync the mount back (it would, without hold). `DRIFT_STATUS` keeps updating;
   Verify/Alert warnings still appear in the log.
5. Trigger a **dither** in Ekos. **Expected:** Reposition-Detection does **not** fire
   (`REPOSITION_CONFIRM` stays idle).
6. **Stop guiding.** After ~15 s continuously idle, the watchdog sets `HOLD_OFF`. **Expected:** on
   the next tick the Bridge corrects the accumulated drift per the active mode.
7. Restart the Mount Bridge driver via the CC readiness path *while step 3's hold is active*.
   **Expected:** the readiness watchdog skips the restart and logs why.

## 6. Explicitly out of scope for v1

- **Scheduler gate** (`/KStars/Ekos/Scheduler .status`) — a coarser "a capture job is running"
  hold. Add once the Guide-only version is proven.
- **Queuing** forwarded Goto-Forward targets that arrive during a hold — v1 just skips them; the
  held-target tracking already survives, so a release re-converges.
- **Dead-man timeout** in the driver (auto-release if the watchdog stops refreshing) — nice
  robustness, not needed to test the logic.
- **Per-mode nuance** beyond the §2.2 table (e.g. keeping Verify/Alert's *visual* alert louder
  during a hold) — start with the simple observe/act split.
- Anything PHD2-specific — v1 keys off Ekos's own Guide module state, which is what Ekos reports
  regardless of whether the internal guider or PHD2 is doing the work.

## 7. Why this order

This is throwaway-ish scaffolding on the CC side (a watchdog + two helpers) but the driver half —
`EXTERNAL_HOLD` and the `TimerHit()` observe/act split — is **not** throwaway: a native
[Ekos module](ekos_pifinder_module.md) would drive the *same* switch, just from in-process Ekos
state instead of a `qdbus`-polling watchdog. So the risky, permanent part (the driver change) is
built once, and the CC watchdog proves the behaviour end-to-end before committing to the module.
