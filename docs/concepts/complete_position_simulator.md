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
