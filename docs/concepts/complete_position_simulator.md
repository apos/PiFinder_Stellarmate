# Concept: a complete, GUI-controllable position simulator

## 1. Context

#106 built the core mechanism (Fake-Solve: inject a synthetic RA/Dec, real IMU dead-reckoning takes
over, settle-detection re-anchors) and #128 gave it a status indicator in the Control Center. Both
only cover one scenario: a real device with working IMU, driven by hand. This concept covers what's
needed to make position simulation *complete* - usable without touching real hardware at all, and
controllable from the GUI rather than raw `curl`/`indi_setprop` calls.

## 2. Two simulation levels (User, 2026-08-03)

The user must choose between two modes, since they need fundamentally different mechanics:

**a) Full simulation** - no physical device at hand at all (Fake Mode's headless instance, no real
IMU). There is no real motion to dead-reckon from, so reaching a PushTo target needs **artificial,
stepwise Fake-Solve injections** that animate a path from the current position toward the target
over time (a sequence of `POST /api/fake_solve` calls tracing a plausible slew), rather than a single
jump. **Not yet built.**

**b) Partial simulation** - real device, real working IMU, real PushTo. Dead-reckoning runs on the
*actual* IMU as the user physically moves the scope; they see the real IMU-driven tracking live, and
once movement stops, a (fake) "solve" lands on the settled position. **Already built** - this is
exactly the existing Fake-Solve mechanism from #106 (single injection + real dead-reckoning + settle
re-anchor), verified live during TC-PFSM-106-01. No new work needed for this mode.

## 3. New capability: the INDI mount as position source

Second clarification (User): a GoTo is a GoTo regardless of who issues it - hand controller, OnStep's
own app/web GUI, SkySafari, KStars, or any other INDI client. In this simulation mode, **the INDI
mount itself (real, or the stock INDI Telescope Simulator) becomes the position source**, and
PiFinder's reported position should follow it - which mirrors reality, since a real mount and a real
PiFinder are physically coupled (wherever the mount points, PiFinder points too).

This enables **full simulation with zero real PiFinder hardware**: point/slew a simulated mount
(Telescope Simulator, or a real one), and have a Fake-Mode PiFinder instance mirror its position.

### What already works vs. what's missing

- **Already works, no changes needed**: "Sync mount from PiFinder", "Auto-correct (Sync)",
  "Auto-correct (Goto & Track)", and "Goto-Forward" all operate on whatever `getPiFinderRADE()`
  reports (via LX200 `:GR#`/`:GD#`) - they don't know or care whether that position is a real solve
  or a Fake-Solve. These need no code changes for this concept.
- **Missing**: the reverse channel, mount → PiFinder. Nothing today reads the mount's INDI
  `EQUATORIAL_EOD_COORD` and feeds it into PiFinder as a Fake-Solve. This is the actual new piece:
  something (most naturally the Mount Bridge, which already watches both devices) needs a mode that
  periodically (or on-change) reads the mount's position and calls PiFinder's `/api/fake_solve` with
  it - the mirror image of what Auto-correct/Sync already do in the other direction.
- This also resolves #128's open question ("where would a GUI 'enable Fake-Solve' button get its
  target RA/Dec from?") - answer: from the coupled mount's current position, not a manual picker.

## 4. GUI needs (Control Center)

- A way to select/enter this "mount is the position source" mode - likely a new coupling direction
  alongside the existing Mount Bridge modes (Off / Verify-Alert / Auto-correct / Goto-Forward), all
  of which currently assume PiFinder is the source and the mount follows.
- For mode (a) (full simulation, no hardware): some way to pick or enter a PushTo target and trigger
  the animated approach - needs its own small design pass once this concept is agreed on.

## 5. Dead reckoning - explanation for `help.html`

Dead reckoning ("koppelnavigation") is a centuries-old navigation technique from sailing/aviation:
starting from a **last known, verified position**, estimate the **current** position by applying the
motion measured since then (heading, speed, elapsed time) - with no new external fix (no GPS, no star
sighting). The name likely comes from "deduced reckoning" ("ded. reckoning").

In PiFinder specifically: `ImuDeadReckoning` anchors on the **last real plate-solve** (a verified
RA/Dec/Roll), then uses the IMU's measured **rotation since that anchor** to rotate the anchored
position forward - producing the current estimate. This is real sensor math on real physical motion,
**not** a simulation of movement. Error accumulates over time (gyro drift), which is why a fresh
solve periodically re-anchors and bounds it - the exact mechanism whose absence caused #79 (Auto-
correct reacting to this ever-advancing estimate instead of waiting for a fresh solve).

## 6. On-device integration - open question, concept only for now

Separate, larger question (User, 2026-08-03): how (if at all) should Fake-Solve be surfaced in
PiFinder's own on-device menu/OLED, not just the Control Center web UI? Explicitly **concept-only at
this stage - no implementation decision yet**. Framing constraint from the user: avoid ending up
maintaining two parallel systems (on-device menu state vs. Control Center state) - the Control Center
should be the leading/authoritative one if both need to exist at all. Needs its own dedicated
follow-up discussion before any design is proposed here.

## 7. Open questions

- Does the Mount Bridge gain a new "mount is the source" mode, or is this better as a separate,
  smaller tool/script dedicated to full-simulation testing? **Resolved, see §8**: built as a Mount
  Bridge Coupling preset (#130), but found to only cover one of the two testing needs this concept
  was meant to serve.
- For mode (a)'s animated approach: what determines the slew path/speed - mimic a real mount's slew
  rate, or just a fixed number of interpolated steps? Still open.
- Whether/how on-device (§6) should exist at all - explicitly deferred.

## 8. 2026-08-05 revision: "Mount is source" tests the wrong direction for Auto-correct/Verify-Alert

Built and live-tested (#130, TC-PFSM-130-01/#132/#133) since §3/§7 above were written. Works
correctly for what it actually does - PiFinder mirroring the mount - but live testing exposed a
structural gap this concept didn't anticipate: **§3 assumed "mount is source" would let all of
Verify/Alert and both Auto-correct presets be tested too** ("already works, no changes needed" -
§3's bullet list). That assumption was wrong.

**Why:** Verify/Alert and Auto-correct exist to catch and fix cases where the *mount's own belief*
about its position (its polar/NCP alignment, its internal mount model, whatever
`EQUATORIAL_EOD_COORD` it reports) has diverged from where PiFinder *independently, truthfully*
knows it's pointing - a real mis-alignment or tracking failure. Testing that needs **two genuinely
independent position sources that can be made to disagree**. "Mount is source" collapses them into
one (PiFinder mirrors the mount), so there is nothing left to disagree with - confirmed live
2026-08-05: switching between "Mount is source" and Auto-correct only ever exercises "does PiFinder
follow the mount" (useful for Goto-Forward), never "does the mount get corrected when it's wrong."

**The actual need (User, 2026-08-05):** PiFinder should behave like a real telescope **pinned to a
real point on the sky** - a fixed RA/Dec that stays valid indefinitely without needing anything from
a mount (Earth's rotation is already accounted for in the RA/Dec frame; a real, correctly-tracking
telescope keeps re-solving the same RA/Dec forever). The mount, separately, has **its own model**
(real or the stock INDI Telescope Simulator - doesn't matter which) that can be made to diverge from
that fixed truth on purpose (bad polar alignment, tracking disabled, a manual GoTo elsewhere, ...),
so Verify/Alert and Auto-correct have something real to detect and fix.

**Stop-gap built same day, works but isn't the real fix:** Injected Solve (a one-time RA/Dec seed)
plus a new "Keep fresh" toggle (`/api/fake_solve_refresh`, re-injects PiFinder's own current position
every 3s so it doesn't age out of Mount Bridge's `SolveFreshnessMaxAgeNP` gate, #79) - together these
approximate "PiFinder pinned to a fixed point," but as **two separately-operated controls** that have
to be remembered and combined correctly, with their own confusing interactions with Coupling mode
switches (#161's mutual-exclusivity behavior). User feedback: "Eine verständliche und bedienbare
Simulation. Das haben wir gerade nicht" (an understandable, operable simulation - that's not what we
have right now).

### Implementation options going forward

**A. Formalize the stop-gap (small, ~1-2 days).** Merge Injected Solve + Keep fresh into one
coherent "Simulate a fixed sky position" control with a single on/off state and status row, instead
of two independently-clickable things that happen to combine correctly if you remember to use them
together. Same underlying mechanism, no PiFinder-core changes - purely an API-layer/GUI cleanup.

**B. A real sky-truth mode inside PiFinder itself (medium, ~1 week).** Instead of the Control Center
polling `/api/fake_solve_refresh` every 3s to keep a position alive, give PiFinder its own mode
(sibling to `debug_solve`) that continuously, self-sufficiently reports a chosen fixed RA/Dec as a
genuine solve - no external "keep fresh" traffic needed at all, PiFinder is simply telling the truth
about a real, if simulated, fixed pointing. This is the direct implementation of "PiFinder gets its
own sky simulator" and the one that actually resolves the structural gap, not just papers over it.

**C. Live-moving targets via KStars (larger, ~1-2 weeks, only if needed later).** Extend B so the
held "truth" can optionally track a real Solar System object's live position (Moon/planet/comet,
queried from KStars via D-Bus) instead of a fixed star. Not needed for the Auto-correct/Verify-Alert
gap itself - a fixed point is sufficient, since Verify/Alert and Auto-correct only care about
*divergence*, not about the truth itself moving. Worth building only if a specific test case needs a
genuinely moving reference.

**Recommendation:** A now unblocks testing immediately at low cost; B is the actual fix and should
happen before this is considered done, not indefinitely deferred as "the stop-gap is good enough."

### What this means for "Mount is source" itself

Keep it - it's real, working, and correctly answers its own question ("does PiFinder follow the
mount"), which Goto-Forward-style testing genuinely needs. The fix is in how it's *presented*: stop
implying (as §3 originally did) that it also covers Verify/Alert/Auto-correct testing. User's current
assessment: for the sky-truth-simulation purpose this concept is actually about, "das ist ein
Workaround, der uns nichts bringt" (a workaround that doesn't get us anywhere) - accurate for *that*
purpose, not a reason to remove the mode itself.

### Relation to the separate "PiFinder mount model" idea

A related but distinct idea surfaced the same day (tracking through cloud cover in *real* operation,
not simulation): PiFinder building its own internal mount-model so it can keep tracking without fresh
solves, with LX200 able to send a solve to the mount as an "Align" command, and a real mount's own
existing alignment model potentially supplying or standing in for that data. Write-up:
[`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md). Both ideas share
the same underlying theme - PiFinder maintaining a position belief independent of a literal fresh
camera solve - but serve different purposes (production robustness vs. test tooling) and should be
designed/built independently; a shared mechanism isn't assumed.

### Known open bug, deliberately deferred until the above is settled

Auto-correct (Sync), tested live 2026-08-05 against the stop-gap (§8 above): drift shown well past
threshold, caption correctly said "Correcting the mount now," but the mount was not actually
observed to move/sync back. Root cause not yet investigated - user explicitly asked to defer this
until the sky-truth-simulator concept above is settled, rather than debug further against a stop-gap
setup that may not be the right thing to keep debugging.

## 9. 2026-09-01 revision: §8's two-mode split is itself incomplete - three independent movement sources, not two mutually-exclusive modes

§8's B recommendation was built (`indi_pifinder_simulator`, Option B - see [[00092]]/[[00164]]) and
correctly gave PiFinder its own independent, self-sufficient sky-truth ("PiFinder Simulator" mode).
Live-tested again 2026-09-01 (GoTo-Forward against `Telescope Simulator`, both PushTo-triggered and
mount-side-GoTo-triggered - basic-memory pifinder-stellarmate/00105) exposed that **this still isn't
a complete simulation** - not a regression of §8's fix, but a gap §8 itself didn't yet cover.

**The physical model, stated precisely (User, 2026-09-01):** PiFinder is rigidly bolted to the OTA.
Wherever the telescope *actually, physically* points, PiFinder points too - that's mechanics, not a
design choice. What makes PiFinder's reported position independent of the mount is **not** "it never
moves" - it's that PiFinder verifies the true pointing direction itself (camera solve, or IMU dead-
reckoning between solves), rather than trusting the mount's own internal belief about where it points.
The drift Verify/Alert and Auto-correct exist to catch is specifically: *the mount's reported position
diverges from the true physical pointing, without the telescope having actually, physically moved*
(bad polar alignment, backlash, thermal effects, a stale internal model - not a commanded slew).

**Why neither existing mode alone is a correct simulation:**

- **"PiFinder Simulator" (§8's fix)**: correctly holds an independent truth so mount-model drift can
  be detected - but incorrectly *also* ignores a **real, physical mount movement** (a genuine GoTo).
  In reality PiFinder would follow along (rigid mount), so Goto-Forward-style tests run against this
  mode see PiFinder "left behind," which isn't physically accurate. Confirmed live 2026-09-01: a
  Telescope-Simulator GoTo to Capella succeeded correctly (Mount Bridge's Fall-2 detection worked,
  `TARGET_SOURCE=MOUNT` set correctly), but `PiFinder Simulator` stayed frozen at its old position -
  this is [[00105]]/#238/#177's finding, not a Mount Bridge bug.
- **"Mount is source" (§3/§7)**: correctly follows real mount movement, but blindly mirrors
  *everything* the mount reports, including a wrong/drifted model with no real movement behind it -
  exactly §8's original finding, still true, unchanged by this revision.

**Third, so-far entirely unsimulated case (User, 2026-09-01): PiFinder/the OTA itself is moved
manually** (e.g. the real-world manual PushTo-guiding walk, or simply someone repositioning the
scope by hand). PiFinder's own truth changes correctly (it re-solves the new position) - but the
**mount's own reported position does not**, since its encoders/steppers never registered the manual
movement. This is a *third* realistic divergence trigger, structurally different from both of the
above: unlike mode-drift (§8, mount wrong, nothing moved) and mount-GoTo (this section, mount right,
telescope moved because mount drove it), here PiFinder is right (it moved and knows it), the mount is
now wrong (didn't move, doesn't know PiFinder/the OTA moved), and nothing has synced them yet - the
classic real-world "manual correction/bump, mount needs re-sync" scenario. Manually Sync()'ing/GoTo-
ing `PiFinder Simulator` directly (already possible today, unchanged) technically produces this same
data shape (PiFinder's own position changes, mount's doesn't) - open question below is whether that
existing mechanism is sufficient as-is, or whether this deserves its own explicit, animated/first-
class control mirroring how mount-movement (below) is meant to work, rather than an instant jump.

**Proposed direction - collapse into one "Full Simulation" mode with independently-triggerable
stimuli**, rather than mutually-exclusive modes for different purposes:

1. `PiFinder Simulator` stays the sole independent truth, self-sufficient (§8, unchanged).
2. New: detect the *active mount's* real slewing (e.g. its `EQUATORIAL_EOD_COORD` state going
   `Busy` during a commanded GoTo - available on both the stock Telescope Simulator and real mount
   drivers). While detected, `PiFinder Simulator`'s truth interpolates/follows the mount's live
   position (dead-reckoning through the slew, physically accurate - PiFinder is rigidly attached).
   Once the mount's status returns to idle/tracking, `PiFinder Simulator` holds its now-updated
   position independently again - it does **not** keep following any further mount-side drift after
   the slew completes, preserving §8's mode-drift-detection property. This is [[00177]]'s originally-
   proposed direction, still the right one, now scoped precisely against the physical model above
   instead of as a vague "optional following."
3. Moving PiFinder/the OTA directly (manual Sync/Goto on `PiFinder Simulator`) already exists and
   needs no new mechanism for the underlying data shape - open question is only whether it deserves
   a more explicit/animated first-class control for realism, or whether the existing manual
   Sync/Goto is sufficient as the simulated stand-in for "someone moved the scope by hand."

**Where this lives**: most naturally inside `indi_pifinder_simulator` itself (it already snoops
nothing today - would need to watch the profile's Active Mount device, similar to how Mount Bridge
already watches both PiFinder and mount), or inside `test_tools/pifinder_truth_injector.py` if
keeping the driver itself dependency-free of mount-awareness is preferred. Not yet decided - the
driver location is probably preferable since it avoids adding a third moving part (the injector
would then need to *also* poll the mount, not just read-and-forward PiFinder Simulator) and keeps
"is a real GoTo in progress" as a single source of truth inside the one process that owns the
simulated PiFinder state.

**Open questions for the actual implementation pass:**

- Exact slew-detection signal to key off - `EQUATORIAL_EOD_COORD` state `Busy`, or something more
  specific (`TELESCOPE_STATUS` if a driver exposes it)? Needs checking against both the stock
  Telescope Simulator and whatever real mount driver is active, since not all INDI mount drivers
  necessarily use `Busy` the same way.
- Interpolation during the slew: mimic the mount's actual live position tick-by-tick (simplest,
  matches §7's still-open "mimic slew rate" question by just reusing whatever rate the mount itself
  reports), vs. a fixed/idealized rate - recommend the former, since it needs no separate
  slew-speed model of its own.
- Should PiFinder Simulator continue holding through an *aborted* slew the same way it does after a
  *completed* one, or does an abort need different handling?
- §8's "which mode is currently active" GUI language (mode tiles from the 2026-08-30/31 Full-
  Simulation rework, see basic-memory pifinder-stellarmate/00102/00103) will need revisiting once
  this lands - "PiFinder Simulator" stops being a single fixed-truth mode and becomes "independent
  truth that also physically follows real mount movement," which may no longer need presenting as a
  separate concept from "Mount is source" at all. Not designed yet - flag only.

Refs: [[00105]] (live 2026-09-01 test that surfaced this), issues #177 (original proposal, now
scoped precisely) and #238 (superseded framing - corrected in a follow-up comment, this section is
the authoritative version going forward).
