# Concept: Session-Start Position Reconciliation (PiFinder / PiFinder Simulator / Mount)

> **Status: concept — not yet implemented.** Written via this project's `cpt` convention (see
> `basic-memory/basic-memory/00020_bm-cpt-command-system.md`). Not yet filed as a GitHub issue -
> see §9 for the proposed issue split. Update that issue (once filed) if this concept is revised.

## 1. Context

Found live on `stellarmate-pi5` (2026-09-08/09) while running [Test Execution
#322](https://github.com/apos/PiFinder_Stellarmate/issues/322) (TC-PFSM-319-01): at the start of a
Control Center / KStars session, none of "Sync mount from PiFinder", "Re-seed from mount", or
"Set position" reliably get PiFinder LX200, PiFinder Simulator, and the INDI mount to agree with
each other. Concretely hit this session:

- **"Re-seed from mount"** is disabled whenever Coupling is Off (`updateSeedControlsEnabled()`,
  `gui_installer/status_page.html`) - but Off is a very normal thing to still be in at session
  start, before the user has picked a Coupling preset.
- **"Sync mount from PiFinder"** (`TRIGGER_SYNC_NOW`) requires a *fresh* (`SolveFreshnessMaxAgeN`,
  default 5s), `CAM`-labeled PiFinder solve (`haveFreshCamPosition`,
  `indi_pifinder_bridge/pifinder_mount_bridge.cpp:3020`) - which a one-shot "Set position" no
  longer provides once [#323](https://github.com/apos/PiFinder_Stellarmate/issues/323)'s fix turns
  the continuously-refreshing Truth Injector off (see §9, item A).
- Even with a *bona fide* fresh solve present, one live attempt logged `[INFO] Manual SYNC sent to
  mount.` while the mount's own `EQUATORIAL_EOD_COORD` never actually changed - **unresolved**, see
  §9 item C.
- `PiFinder Simulator` holds its position independently once the mount goes idle (only follows
  live while the mount is actively slewing - see §4) - so at session start it can easily be sitting
  near/below the horizon from a previous session, with nothing to reconcile it.

Every one of these mechanisms already exists (#106, #205, #227, #313 built them one at a time, for
one purpose each). What's missing is a **coherent statement of what should happen, for every
plausible starting condition, at the moment a session begins** - so the existing pieces can be
checked against it, and the gaps closed deliberately rather than found one at a time, live, at
night.

## 2. What the user wants (verbatim intent, 2026-09-09)

Restated from the live conversation that produced this concept:

- The recurring, concrete pain: *"immer wenn ich die Session starte, habe ich das Problem [dass die
  Treiber auseinanderlaufen]. Und ich kann weder ein Reseed noch ein Sync from PiFinder direkt
  machen."* - this is a **session-start** problem specifically, not a general runtime one; once a
  GoTo has happened, the drivers reconcile on their own.
- In practice, the two mechanisms actually used are **"Sync from PF"** and **"Reseed from Mount"** -
  "Set position" is a rarely-needed manual/testing tool, not the primary workflow.
- The user already understands the horizon-safety mechanics (`isAboveHorizon()`) - a low/negative
  Alt on `PiFinder Simulator` is expected and not itself the bug; it's *why* Reseed-from-mount
  (mount is the trusted source at that moment, not PiFinder) is the tool they reach for.
- Explicit general expectation, stated as three principles (§3) - and explicit request that this be
  written down as a concept covering **all** plausible starting conditions, with a focus on program
  start (Control Center / KStars), then checked against the actual code (§8) rather than assumed.

## 3. General principles (as stated by the user)

1. **Whenever a sky position gets established - by any means (real solve, Fake-Solve, Set position,
   Sync from PiFinder, Reseed from Mount) - all components should end up agreeing on it**, and the
   mount should receive an explicit **Sync** (never a silent/implicit belief change) - after a
   plausibility check.
2. **Whenever a solve happens (real or fake), the same reconciliation should follow** - again after
   a plausibility check. (This is the same principle as #1, restated from the solve side rather
   than the "position was set" side - they're the same event from two different triggers.)
3. **Manually moving the mount by hand changes the picture** - open question, not yet answered:
   what should happen to the mount's own alignment model, and to KStars' belief, when that happens?
   (Directly relevant to [`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md)'s
   still-open "who holds the model" question - this concept doesn't resolve that, only flags where
   the two meet.)

## 4. Actors - precise terminology (to avoid this session's own confusion)

| Actor | What it actually is | Moves on its own? |
|---|---|---|
| **PiFinder** (the software) | The real or Fake-Mode PiFinder process; `/api/status` is its single source of truth (`solution.RA/Dec`, `solve_source`, `last_solve_success`, `fake_solve_active`). | Only via real camera solves, Fake-Solve injection, or IMU dead-reckoning between the two. |
| **PiFinder LX200** (INDI device) | A pass-through INDI/LX200 facade over PiFinder's own `/api/status` (`indi_pifinder_lx200`). Whatever PiFinder currently believes, this device reports - nothing more. | Follows PiFinder exactly; not an independent position source. |
| **PiFinder Simulator** (INDI device) | A *separate* stand-in device (`indi_pifinder_simulator`) used as a Shadow Sync target / Truth Injector source in Full-Simulation setups - **not** the same thing as PiFinder LX200, and not driven by `/api/status` at all. | Only while the watched mount is actively slewing (`ISSnoopDevice`, `pifinder_simulator.h:61-73` - "physically accurate, since a real PiFinder is rigidly bolted to the OTA and moves with any real mount movement"). Holds independently once the mount goes idle again - does **not** keep following further idle-state mount drift by design (see #177, basic-memory 00092/00164). |
| **The Mount** (`LX200 OnStep`, `Telescope Simulator`, ...) | The actual (or simulated) telescope mount, via its own INDI driver. Has its own internal pointing model, independent of PiFinder entirely. | Tracking (sidereal), GoTo/Sync commands, or hand-slewing. |
| **Mount Bridge** (`indi_pifinder_mount_bridge`) | The reconciliation layer between PiFinder and the Mount - this concept is primarily about what *it* should do at session start. | N/A - it's the mediator, not a position source itself. |

`PiFinder Simulator` matters for this concept only insofar as it's what `pifinder_truth_injector.py`
(Synthetic Solve) reads from to feed PiFinder - it is not itself a party to the three-way
reconciliation the user is asking about (PiFinder / PiFinder LX200 are one and the same belief; the
real triangle is **PiFinder's belief vs. the Mount vs. what the user actually wants**).

## 5. Constraints and use cases

### 5.1 Simulation

1. Session start, or mid-session (already-running Full Simulation profile).
2. Any combination of {real solve, Fake-Solve} × {real IMU, simulated/no IMU}.
3. **User deliberately wants to pick a specific starting point** - NCP, on the meridian, on the
   horizon, an arbitrary RA/Dec - to test a specific scenario (e.g. a horizon-safety edge case).
4. **The mount already has a position** from before this session started - last position, Home, or
   Park. **Park may be deliberately below the horizon** - not itself a fault condition.
5. The mount side may be real hardware or `Telescope Simulator` - orthogonal to whether PiFinder
   itself is simulated.

### 5.2 Real hardware

1. Session start, or mid-session.
2. Any combination of {real mount, simulated mount} × {Fake-Solve, real solve}.
3. **Daytime**: PiFinder's Day-Align exists, but it has **no associated sky coordinate** - it only
   calibrates the PiFinder-to-scope offset, not "where is this pointed." A day-align therefore
   cannot, by itself, seed a sky position for §3's reconciliation.
4. **Idea, not yet built**: a *real* daytime sky-object align (Sun with a proper solar filter, or
   the Moon) - unlike 5.2.3, this *would* carry a real sky coordinate and could seed reconciliation
   like a night solve does. Flagged here as a dependency for closing the daytime gap, not scoped
   further in this document.
5. **Night, overcast** (equivalent to 5.2.2's "no solve" case, elaborated):
   1. A solve happened earlier this session (before the clouds moved in).
   2. A clear patch is expected soon (worth holding position accurately in the meantime).
   3. A rough (or precise) position was set by hand - horizon/North, NCP, Park, or an arbitrary
      fixed point relative to horizon/meridian.
6. **Night, intermittent clouds**: solves arrive, then stop, then resume, repeatedly.
7. **Night, clear**: the baseline case - solves land continuously, nothing in this concept is
   needed.

## 6. Guiding interaction (cross-cutting - a fourth actor, not yet on the radar)

Raised separately (2026-09-09): a real guiding camera (a dedicated guide scope/OAG + PHD2 or Ekos's
own Guide module, driving the mount via `TELESCOPE_TIMED_GUIDE_NS`/`_WE` pulses) is a **fourth**
position-authority actor this concept hasn't considered - orthogonal to §5's Simulation/Real split,
since it can apply to either. Not a hypothetical: any serious imaging session on this hardware will
eventually run one. **Currently invisible to Mount Bridge entirely** - confirmed live,
`grep -rn "GUIDE\|ST4\|Guiding" indi_pifinder_bridge/` returns zero matches, and
[#8](https://github.com/apos/PiFinder_Stellarmate/issues/8) ("Add ST4 functionality to PiFinder")
was closed as unnecessary ("done via Stellarmate via a astrocam") - meaning guiding already runs
entirely outside PiFinder/Mount Bridge's current path, through StellarMate's own INDI ecosystem,
with **no existing signal Mount Bridge could piggyback on**.

The three states the user named, plus what's missing to actually build this:

1. **Calibration** (PHD2/Ekos measures guide rate and orientation via small deliberate test moves).
   Mount Bridge must not intervene at all - any Sync/Goto/Auto-correct mid-calibration would corrupt
   the measurement, and Reposition-Detection (#178/#300) would very likely misidentify the
   calibration moves themselves as an external reposition to react to.
2. **Guiding active**. Needs precise scoping, not a blanket "everything off" - candidates: Verify-
   Alert's drift alerts (still useful to *see*, probably shouldn't *act*), Auto-correct
   (Sync/Goto&Track - must suspend, a threshold-triggered correction during active guiding is far
   larger than a guide pulse and would kick the guide star out of the frame), Goto-Forward
   (must suspend for the same reason), Reposition-Detection (dithering - a legitimate, guiding-
   software-issued small position perturbation between subs - must **not** be misread as an
   unexpected external reposition), and the CC's own readiness watchdog (`_mb_readiness_self_heal`,
   basic-memory `00126...`) - a driver restart mid-guiding-session would be actively harmful, not
   just inconvenient. Each needs its own explicit decision, not an assumption that "suspend" means
   the same thing for all of them.
3. **Guiding lost/stopped**. Mount Bridge's own mechanisms should resume - but only once genuinely
   idle, not the instant a single guide frame is missed (mirrors §5.2.6's intermittent-clouds
   debounce concern for the same reason: a real momentary hiccup shouldn't cause a jarring Sync/Goto
   response before guiding has had a chance to recover on its own).

What else is missing (not in the user's original three, added here):

- **Detection mechanism** - the actual open problem, since there's no existing signal (see above).
  Candidates, none evaluated yet: snoop a guide-camera/PHD2 INDI device's own state property
  directly (if the specific guiding software running on this StellarMate setup exposes one);
  integrate with EkosLive's own guide-state API (an `ekoslive` process already runs on this device
  for other purposes - unclear whether it or PHD2 expose anything queryable); or a purely
  heuristic signal - a sustained pattern of small, frequent `TIMED_GUIDE_NS/WE` pulses on the mount
  device itself, inferred without any explicit "I am guiding" signal at all.
- **Pulse-guide vs. Sync/Goto scale mismatch** - worth stating explicitly: guide corrections are
  sub-arcsecond and continuous; anything Mount Bridge currently sends (a full Sync, or a Goto) is
  orders of magnitude larger. This is *why* §6.2's suspension matters, not just a nice-to-have.
- **GUI visibility** - if Mount Bridge goes quiet during guiding, the user needs to see *why*,
  matching the project's own established principle for exactly this class of problem (the
  Coupling-gate hint already added to `status_page.html` for the Quick Actions row, 2026-09-07: a
  button silently disabled with no visible reason is worse than one that's simply absent).
- **Meridian flip during a guided session** - adjacent, not solved here: guiding itself must
  stop/recalibrate around a flip regardless of Mount Bridge; flagging only so it isn't mistaken for
  part of this concept's scope when it's picked up later.
- **PiFinder's own solving is unaffected** - stated explicitly so it isn't left as an unstated
  assumption: different optical path/camera than the guide scope, no interference expected, no
  reason for PiFinder itself to pause solving while guiding runs. Only the *downstream* Mount
  Bridge reaction needs gating.

## 7. Focus: what should happen at program start (Control Center / KStars)

At the moment Ekos/the Control Center starts (or Mount Bridge (re)connects), the *only* thing known
for certain is each device's **last-persisted** state - not whether that state is still true. The
proposed behavior, per §3's principles:

| Starting condition | Trusted source | Expected action |
|---|---|---|
| PiFinder already has a fresh solve (real or Fake-Solve continuously refreshed, e.g. Synthetic Solve active) | PiFinder | Sync mount to PiFinder, once, automatically - already exists for Auto-correct/Goto-Forward (`syncMountToPiFinderPosition()`, the "#227 follow-up" unconditional initial sync) but **not** for Off/Verify-Alert (arguably correct - see §8.1) and not manually forceable without Coupling active (§8.2's gap). |
| PiFinder has no solve yet, but the mount's own position is trusted (just homed, just parked-and-known, or the user trusts wherever it settled) | Mount | Reseed PiFinder from the mount - today gated on Coupling ≠ Off (§8.2), which is exactly backwards for this specific case: reading the mount doesn't need Coupling automation active at all. |
| Neither is trusted (fresh boot, mount at an arbitrary/park position, no solve, no known-good reference) | Neither - user | User explicitly sets a position (Set position, or a day/night align) - needs to *stay* fresh long enough to be useful downstream (§8.3's staleness gap), and needs the plausibility check from §3 before being written to the mount. |
| Mount is manually moved after reconciliation | Mount (transiently) | Open - §3 principle 3, no proposed answer yet; overlaps `pifinder_mount_model_cloud_tracking.md`. |

"Plausibility check" (referenced throughout §3/§7, not newly invented here) is the existing
`isAboveHorizon()` / `HORIZON_SAFETY_MARGIN_DEG` mechanism
(`indi_pifinder_bridge/pifinder_mount_bridge.cpp:1819-1859`) - already applied to every
`sendMountCoordsSafe()` call. It has **no Park awareness** (§8.4) and is not currently applied to
the *reverse* direction (mount → PiFinder, via Reseed) at all.

## 8. Code-level audit — does the current implementation fulfill this?

Checked directly against the running driver/GUI code on `stellarmate-pi5` (branch `dev`,
`4157641`), not from memory.

### 8.1 Automatic Sync-on-fresh-solve (principle 1/2, PiFinder → Mount)

**Partially fulfilled.** `TimerHit()` calls `syncMountToPiFinderPosition()` unconditionally once per
connection (`m_didInitialSync`), but **only** when `BridgeModeS[MODE_AUTO_CORRECT] || BridgeModeS[MODE_GOTO_FORWARD]`
is selected (`pifinder_mount_bridge.cpp:1512-1517`). At session start with Coupling still at its
saved default - which the CC's own `_mb_readiness_self_heal` restart cycle keeps re-loading, see
basic-memory `00126_pi5-313-align-sync-deployment-und-test-2026-09-08.md` - this fires only if that
default happens to be Auto-correct/Goto-Forward. Off and Verify-Alert never get this automatic
reconciliation, which is arguably correct for Off (fully decoupled, by definition) but is a gap for
Verify-Alert (it monitors drift, but starts from a potentially wrong baseline with no initial Sync
to establish one).

**#313's own PiFinder-Align-Sync path** (`handlePiFinderAlignSync()`) is the one mechanism that
*does* fire regardless of Coupling mode (Off excluded) - but only on a confirmed PiFinder **Align**
event (`last_align_time` changing), not on an ordinary solve. It's the closest existing piece to
principle 1/2's "solve → reconcile" for Verify-Alert, just scoped to Align specifically rather than
every solve.

### 8.2 Reseed-from-mount's Coupling gate (Mount → PiFinder)

**Gap, confirmed live.** `updateSeedControlsEnabled()` (`status_page.html:2849`) disables
`fake-solve-reseed-btn` whenever Coupling is Off, per its own comment: *"it reads the coupled
mount's position"*. But reading the mount's `EQUATORIAL_EOD_COORD` via INDI does not actually
require any Coupling automation to be active - Coupling only gates *automatic* corrective writes.
This is the single change that would most directly unblock the user's stated real workflow
(§2): remove or relax this gate so Reseed-from-mount works with Coupling = Off, since that's
precisely the state a fresh session is normally in.

### 8.3 One-shot freshness after #323's fix (User → PiFinder)

**Gap, introduced/exposed by #323.** `api_fake_solve()`/`set_fake_solve_active()` stamp
`last_solve_success` once, at injection time; nothing re-stamps it afterward unless real IMU motion
settles and triggers the "settle re-anchor" path in `integrator.py` (§"2b" per its own comments) -
which never fires for a device that never moved in the first place. Confirmed live: age grew in
exact lockstep with wall-clock time (518s → 549s → 668s over successive checks, zero resets) once
Synthetic Solve was turned off. Anything gated on `SolveFreshnessMaxAgeN` (default 5s) - including
`TRIGGER_SYNC_NOW` itself - can never use a one-shot "Set position" result after its first few
seconds. Needs either: PiFinder-side periodic re-stamping while `fake_solve_active` and stationary
(symmetric with the existing settle-reanchor, just without requiring a prior motion event to
trigger it), or Mount-Bridge-side manual triggers accepting an older-but-still-`fake_solve_active`
position (loosening §8's freshness check specifically for human-initiated one-shot actions, not
automatic ones).

### 8.4 Park-position awareness (constraint 5.1.4 / 5.2's park references)

**Not implemented at all.** `grep -rn "park" indi_pifinder_bridge/` returns zero matches - Mount
Bridge has no awareness of the mount's own `TELESCOPE_PARK` state. A deliberately-below-horizon Park
position (explicitly called out by the user as legitimate, §5.1.4) would currently just look like
any other position to `isAboveHorizon()` - correctly refused for an active Sync/Goto, but with no
distinction between "refused because parked, expected" and "refused because something is wrong."

### 8.5 Live-open mystery: logged success, no mount movement

**Resolved, 2026-09-09 (later session).** Root-caused via basic-memory 00090 Regel 3's raw
`<message>`-capture technique against a clean, single-variable repro (direct `indi_setprop`
against the driver, no GUI/Python layer involved): `sendMountCoords()` itself was never broken -
a controlled direct test moved the mount exactly as commanded, confirmed via `indi_getprop`
before/after. Of the three original candidates, the stale-`m_client`-pointer hypothesis was ruled
out directly (a fresh driver restart reproduced the identical "no movement" symptom immediately);
the real causes turned out to be entirely upstream/downstream of `sendMountCoords()`, not in it:

- The GUI's own `sync_mount_to_pifinder_visible_position()` (Python) had a `state == "Ok"` gate on
  `"PiFinder LX200".EQUATORIAL_EOD_COORD` that, live-verified, can never be true even with a fully
  valid, confirmed position - that INDI property's `state` reflects the generic LX200 driver's own
  internal "have I ever been Synced" notion, unrelated to PiFinder's solve validity. Removed.
- Neither the GUI nor the driver ever checked whether the mount **accepted** the Sync it was sent -
  a genuine mount-level rejection (see the new §8.5.1 below) was reported to the GUI as unqualified
  "success" purely because the *command* was sent successfully, regardless of the outcome. Fixed:
  the trigger now watches the driver's own `<message>` log for the ~1.5s after sending and surfaces
  a real error if either Mount Bridge or the mount itself logs one.

See `gui_installer/indi_client.py`'s `sync_mount_to_pifinder_visible_position()` and
`_send_switch_and_confirm()` for the current implementation.

#### 8.5.1 New open item: OnStep pier-side/meridian limit on Sync (not resolved)

Live-reproduced, 2026-09-09: a Sync to a target requiring the opposite pier side from what OnStep
currently believes it's on (`LX200 OnStep.TELESCOPE_PIER_SIDE`, confirmed **read-only** via INDI -
not overridable from this project's side) is refused by the mount's own firmware:
`OnStep slew/syncError: Outside limits: Max/Min Dec, Under Pole Limit, Meridian Limit, Sync
attempted to wrong pier side`. This directly affects "Sync mount from PiFinder"'s own stated primary
use case ("useful after moving the mount by hand") - a manual clutch-release reposition to the
other pier side would hit exactly this refusal. Not a false negative (OnStep is protecting a real
mechanical/cable-wrap concern it can't verify from a bare Sync alone) but not yet worked around
either. Two directions floated, neither built/verified:
- Research OnStep's own correct procedure for "I was manually repositioned across the meridian,
  reset your assumption" (likely a distinct realign flow, not a plain Sync).
- An automatic, driver-side stepwise walk-across instead of one large jump - unconfirmed whether
  this actually bypasses the check (it may key off the target's absolute Hour Angle vs. the mount's
  stored belief, not the size of the jump) or just delays hitting the same wall.

### 8.6 Daytime real-object align (constraint 5.2.4)

**Not implemented; idea only**, per the user's own framing. Would need a new PiFinder-side UI flow
(pick Sun-with-filter or Moon, confirm centering, resolve to a real sky RA/Dec via ephemeris rather
than a plate-solve) before it could feed into this concept's reconciliation at all. Sizing/design
not attempted here - flagged as a dependency, not a task, for now.

### 8.7 Guiding awareness (§6)

**Not implemented at all - zero code, zero detection mechanism.** Confirmed live:
`grep -rn "GUIDE\|ST4\|Guiding" indi_pifinder_bridge/` returns nothing, and the one prior attempt at
a related capability (#8, ST4 pass-through) was deliberately closed as unnecessary once guiding
moved to StellarMate's own astrocam path - meaning Mount Bridge was never given any hook into it,
not that one was removed. Every one of §6's three states (calibration/active/lost) currently has
no effect on Mount Bridge's behavior whatsoever - Auto-correct, Goto-Forward, and
Reposition-Detection would all react to guide-induced drift/dithers exactly as if they were a real
external reposition, today.

### 8.8 Mount altitude/horizon status not surfaced anywhere (found 2026-09-09, live)

**Not implemented - no continuous signal exists at all.** Found live testing the no-solve banner
(§8/PR pending) on **Real Hardware** (not simulation): mount below the horizon, PiFinder itself also
below the horizon (no real solve possible), Coupling Off. The no-solve banner correctly appeared
("No solve active - neither real nor synthetic") - but said nothing about *why* nothing can help:
the mount itself being below the horizon is exactly the kind of context a first-time user needs to
understand the situation, and it's silently missing.

**Confirmed no existing property to reuse**: `indi_getprop "LX200 OnStep.HORIZONTAL_COORD.*"` returns
nothing - this OnStep driver exposes no live Alt/Az at all. The *only* place altitude gets computed
today is `PiFinderMountBridge::isAboveHorizon(ra, dec, altitude)`
(`indi_pifinder_bridge/pifinder_mount_bridge.cpp:1819-1859`, `HORIZON_SAFETY_MARGIN_DEG = -5.0`) -
and that's purely reactive, called only at the moment a `sendMountCoordsSafe()` write is attempted,
never stored or exposed as a standing, pollable value.

**Proposed design** (not started - sizing only):
- Compute altitude every `TimerHit()` tick from whatever `EQUATORIAL_EOD_COORD` the mount is
  already reporting (already snooped/watched, no new INDI subscription needed) - reuse
  `isAboveHorizon()`'s own math rather than a second, independently-maintained calculation that
  could drift out of sync with the actual safety gate.
- Expose as a new standing INDI number property on `PiFinder Mount Bridge` (e.g.
  `MOUNT_HORIZON_STATUS.ALTITUDE_DEG`), continuously updated - mirrors this same session's
  `STARTUP_DEFAULT_SOURCE` pattern added to `indi_pifinder_simulator` (§8.7's sibling fix, done
  2026-09-09 - a new backend endpoint reads a driver-computed value, a frontend poll surfaces it).
- Surface in the Control Center: extend the same no-solve banner text when the mount is confirmed
  below horizon ("...and the mount itself is currently N° below the horizon - point it above the
  horizon, or Sync once it's able to see something"), and/or a dedicated dot/value in the Mount
  Bridge diagram itself (`mb-diagram`) next to the existing Drift badge.
- Scope note: this is **more general** than §8.7's `indi_pifinder_simulator`-specific
  `STARTUP_DEFAULT_SOURCE` work - that one only exists in Full Simulation (where "PiFinder
  Simulator" is a device at all); this belongs on Mount Bridge itself and applies equally to Real
  Hardware and Full Simulation, since both drive a real (or real-shaped) `EQUATORIAL_EOD_COORD`.

**Implemented, 2026-09-09 (the deferred fresh session).** `MOUNT_HORIZON_STATUS.ALTITUDE_DEG`, a new
standing INDI number property on `PiFinder Mount Bridge`, computed every `TimerHit()` tick from the
mount's own reported `EQUATORIAL_EOD_COORD` (mode-independent, reuses `isAboveHorizon()`'s own math
exactly as proposed above). Surfaced as a dedicated below-horizon showstopper card in the Mount
Bridge tile (its own category, split from the PiFinder-category no-solve card per direct feedback:
"Mount below ist von der Kategorie Mount Bridge... immer konsequent unterhalb der badges"), with its
own "Sync mount from PiFinder" / "Goto Home Position" recovery actions - see §8.9 for how those
actions themselves were then hardened.

### 8.9 Sync mount from PiFinder: unification, result-verification, and related GUI fixes
(2026-09-09, live-tested end-to-end)

A cluster of fixes that came out of actually live-testing §8.8's below-horizon recovery banner,
worth recording together since they were found and fixed as one continuous debugging session:

- **Three separate "Sync mount from PiFinder" buttons** (Quick Actions, the sim-mismatch card, the
  below-horizon card) called two different backend mechanisms with different, inconsistent gating -
  confusing since all three carry the identical label. Unified to one: the new
  `SYNC_TO_COORDS`/`TRIGGER_SYNC_TO_COORDS` driver primitive (deliberately separate from the
  existing, fresh-solve-gated `TRIGGER_SYNC_NOW` used elsewhere for normal operation - see that
  property's own header comment in `pifinder_mount_bridge.h`), no freshness judgment, same as a
  manual Sync in KStars' own INDI panel.
- **Result verification** - see §8.5 above.
- **`_truth_injector_stop()` wasn't clearing `fake_solve_active`** on stop - only killed the
  subprocess, leaving `/api/status` reporting a stale "Injected" state indefinitely.
- **"PiFinder Simulator" doesn't follow a Sync**, only a genuine Slew (`EQUATORIAL_EOD_COORD` state
  `Busy`, or a changed slew target) - **by design**, `indi_pifinder_simulator/pifinder_simulator.cpp`
  `ISSnoopDevice()`, to avoid a documented 2026-09-01 feedback-loop bug. This made "Re-seed from
  mount" and "Sync mount from PiFinder" look broken (PiFinder Simulator visibly stayed put) even
  though both worked correctly for what they actually touch (PiFinder's real solve pipeline / the
  mount respectively) - neither had ever been able to reach "PiFinder Simulator" at all, a wholly
  separate INDI device. Fixed by having "Re-seed from mount" ALSO send a plain, direct INDI Sync to
  "PiFinder Simulator" itself (`sync_pifinder_simulator_to()`, no custom driver primitive needed -
  the simulator is a pure test fixture with no horizon-safety concern of its own).
- **`STARTUP_DEFAULT_SOURCE` (§8.7) is a one-time startup snapshot, never re-evaluated** - the
  sim-mismatch banner it drives stayed up even after the actual mismatch was genuinely fixed by a
  live Re-seed/Sync, since the underlying INDI property itself never changes again after driver
  startup (by design - not revisited here, an earlier attempt to widen the startup grace window was
  explicitly reverted per direct feedback). Fixed client-side instead: `status_page.html` now tracks
  a session-lifetime "acknowledged" flag, set only on a genuinely successful Re-seed/Sync from either
  of the banner's two buttons (not a live drift-threshold recheck - a *refused* action, e.g. mount
  below horizon, correctly leaves the banner up).
- **"OFF ist OFF"**: the "Synthetic Solve" toggle's displayed text/dot reflected only its own
  `_truth_injector_desired` intent flag, showing "off" even while a *different* mechanism (Manual
  one-shot seed, Re-seed from mount, Sync mount from PiFinder - all inject as a side effect) held the
  real, combined `fake_solve_active` true - directly contradicting a simultaneously-lit "Injected"
  badge. Both the toggle's click behavior (`_pifinder_fake_solve_active_live()`, checks the real
  state on both PiFinder ports rather than trusting its own memory of intent) and its display
  (`applyTruthInjectorState()`, now also considers `lastFakeSolveActive`) were fixed to reflect one
  single truth regardless of source.
- **CSS**: a long error message inside `#mb-action-status` inherited `text-transform: uppercase`
  from its parent `.group-label` (fine for a short heading, wrong for a sentence), and
  `white-space: nowrap` + `overflow: hidden` alone did not reliably prevent it from forcing the
  page's grid/flex ancestor chain wider (a known CSS "blowout" gotcha - `min-width: 0` on one element
  doesn't guarantee every ancestor has it too) - switched to wrapping instead of nowrap+ellipsis.
- **Injected Solve badge color reversed red → green**: red was chosen deliberately in an earlier
  mockup round ("not a real camera solve" caution) but reversed per direct feedback - injecting a
  synthetic position always "succeeds" by definition, so red (reserved for an actual problem) was
  the wrong signal; the "Injected" label itself already says it isn't a real solve.

## 9. Open questions / not decided here

- **A**: Should #323's auto-disable-Synthetic-Solve behavior extend to also *start* a lightweight
  self-refresh for a one-shot seed, or is periodic re-stamping better owned entirely on the PiFinder
  side (§8.3)? Two different components could each partially solve this - avoid solving it twice.
- ~~**B**: Exact mechanism for relaxing §8.2's Coupling gate~~ **Resolved, implemented 2026-09-09**:
  replaced with "mount linked and connected" (`data.mount_connected` from `/api/mount_bridge_status`,
  already computed server-side from the live mount device's own `CONNECTION` state) - live-verified
  on real hardware, "Re-seed from mount" now works correctly with Coupling = Off.
- ~~**C**: §8.5's silent-failure mystery~~ **Resolved 2026-09-09** - see §8.5. Replaced by a new
  open item, §8.5.1: OnStep's pier-side/meridian limit on Sync after a manual reposition.
- **D**: §3 principle 3 (manual mount movement) - genuinely unanswered; likely belongs jointly with
  `pifinder_mount_model_cloud_tracking.md` rather than as new scope here.
- **E**: §6's detection-mechanism candidates (INDI-device snoop vs. EkosLive API vs. pulse-frequency
  heuristic) - none evaluated against what's actually available on this StellarMate setup yet; needs
  its own investigation pass before any of §6 can move from concept to design.
- **F**: §6.2's per-mechanism suspension list is a first pass, not verified complete - a careful
  read of every automatic Mount Bridge action against "would this fire, incorrectly, mid-guiding" is
  still needed once §6's detection question (E) is resolved.
- ~~**G**: §8.8 (mount altitude/horizon status not surfaced)~~ **Resolved, implemented 2026-09-09**
  - see §8.8 and §8.9 for the follow-on fixes found while live-testing it.
- Should this concept's use-case matrix (§7) become an actual Test Case (TC-PFSM-...), the way #313
  did, once any of §8's gaps are closed? Natural follow-up, not decided yet.

## 10. References

- [#106](https://github.com/apos/PiFinder_Stellarmate/issues/106),
  [#205](https://github.com/apos/PiFinder_Stellarmate/issues/205) - Fake-Solve / Reseed-from-mount
  origins, see [`pifinder_fake_solve_simulation.md`](pifinder_fake_solve_simulation.md) and
  [`complete_position_simulator.md`](complete_position_simulator.md) §3.
- [#8](https://github.com/apos/PiFinder_Stellarmate/issues/8) - ST4 pass-through, closed as
  unnecessary; the reason §6/§8.7's guiding path currently has no hook into Mount Bridge at all.
- [#227](https://github.com/apos/PiFinder_Stellarmate/issues/227) - the original
  `syncMountToPiFinderPosition()` unconditional-initial-sync fix referenced in §8.1.
- [#313](https://github.com/apos/PiFinder_Stellarmate/issues/313) - Sync-on-confirmed-Align, the
  closest existing analogue to this concept's principle 1/2 for Verify-Alert (§8.1).
- [#319](https://github.com/apos/PiFinder_Stellarmate/issues/319) / [#322](https://github.com/apos/PiFinder_Stellarmate/issues/322) /
  [#323](https://github.com/apos/PiFinder_Stellarmate/issues/323) - the live testing session that
  surfaced this concept.
- [`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md) - overlaps §3
  principle 3 and §5.2.5/5.2.6 (tracking through cloud gaps via a mount-held model).
- `indi_pifinder_simulator/pifinder_simulator.h:61-73` (`ISSnoopDevice`) - `PiFinder Simulator`'s
  actual follow-while-slewing / hold-once-idle behavior (§4's terminology table); #177 and
  basic-memory `00092_pifinder-truth-simulator-konzept-und-umsetzung.md` / `00164` are the features
  that built this.
- basic-memory `pifinder-stellarmate/00105_simulation-alignment-luecke-und-mount-bridge-hang-2026-09-01.md`
  §1 - the originally-deferred "PiFinder alignment in Full Simulation" idea this concept revisits
  with more structure. Written 2026-09-01, **before** #177's follow-while-slewing behavior existed -
  its "rigid pin, never moves" framing is now only accurate for the idle-state case (§4).
- basic-memory `pifinder-stellarmate/00126_pi5-313-align-sync-deployment-und-test-2026-09-08.md` -
  the CC readiness-watchdog behavior referenced in §8.1.
