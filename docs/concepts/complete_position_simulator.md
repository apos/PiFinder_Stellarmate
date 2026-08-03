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
  smaller tool/script dedicated to full-simulation testing?
- For mode (a)'s animated approach: what determines the slew path/speed - mimic a real mount's slew
  rate, or just a fixed number of interpolated steps?
- Whether/how on-device (§6) should exist at all - explicitly deferred.
