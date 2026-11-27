# Concept: Mount Bridge target transparency — one Target, shown from the moment a GoTo is issued

> **Status: concept — not yet implemented.** Tracked as #657 (this concept), #658 (controller-side GoTo target never reaches
> the Bridge), #659 (Auto-correct syncs to a pre-stop solve), #660 (Goto-Forward "Waiting on fresh solve"), #661 (Auto-correct
> Goto action not selectable), #662 (no rebind after a mount switch).
> Found while testing the Mount Bridge against the realmode sky simulation
> ([pifinder_realmode_sky_simulation.md](pifinder_realmode_sky_simulation.md), #344, 2026-11-26) and agreed with the
> project owner the same day. **Nothing here changes the existing hand-control, reposition-detection, external-hold or
> Align behaviour** (see §3): it adds visibility and one read-only remembered value on top.

## 1. Problem

Two things the user cannot see today, both visible in the 2026-11-26 test (KStars GoTo to M3 and M13 on the Telescope
Simulator, which lands 8' east / 5' south of every target):

1. **"Held" appears only after the object is reached.** For a GoTo issued from KStars (or anywhere on the mount side) the
   Bridge waits until the mount has stopped and PiFinder has a fresh solve, then calls `setOriginalTarget()`
   (`pifinder_mount_bridge.cpp`, reposition detection). During the slew the chart shows the "Goto" marker only; "Held"
   is missing.
2. **For a GoTo sent straight to the mount, what is held is not the target.** Two paths exist today:
   - **GoTo to the PiFinder device** (KStars on "PiFinder LX200", push-to from the PiFinder menu; `handleGotoForward()`):
     the Bridge Syncs the mount to PiFinder's solved position, sends the GoTo to the *requested coordinates*, sets the
     held target to them **at once** (`setOriginalTarget(targetRA, targetDec)` at slew start) and then refines by plate
     solving (SLEWING/SETTLING, bounded retries) until the scope is on the target. This is the exact algorithm the
     project is built around, and it already works as wanted.
   - **GoTo sent straight to the mount** (KStars/Ekos or any INDI client on the mount device, as in the 2026-11-26
     test; "Following: MOUNT" in the Control Center): reposition detection sees only that the mount's position changed
     without a Bridge command. It **ignores the target coordinates the INDI client sent** (the mount's
     `TARGET_EOD_COORD` is used for the "Goto" marker only), waits for settle and a fresh solve, and then calls
     `setOriginalTarget(piRA, piDec)`: the held position is *where the scope landed*. Nothing refines to the requested
     object, and "Held" appears only at arrival.

   Reposition detection was written so that a hand-paddle fine-centring or a deliberately framed field is accepted and
   never fought (`mount_bridge_reposition_detection.md` §1). For a motion without any command that is right. For a GoTo
   whose coordinates **are** visible it throws the information away: after Auto-correct (Sync) the screen said
   *Drift 0.02' - Ok* while M13 was still 9.4' off the image centre. **Drift** (mount vs PiFinder: are the mount's
   coordinates right?) and **offset from the target** (PiFinder vs target: is the scope on the object?) are different
   questions and only the first is shown.

"Held target" is also the wrong word: to the user there is only the Target.

## 2. Terms and what the screen shows

| Term (UI) | Meaning | Changes on a hand move? |
|---|---|---|
| **Target** | What somebody asked for: coordinates, source (KStars, another INDI client, PiFinder, mount-side), age, name if known | **No.** Replaced only by a new GoTo or by an explicit user action |
| **Hold position** (today "Held target") | Where the Bridge keeps the scope and where it brings it back to after drift | Yes - takes over the new position after a hand-centring (existing behaviour) |
| **Drift** | mount vs PiFinder | - |
| **Offset from target** | PiFinder vs Target. **Information only, neutral colour, never an alarm and never triggers an action** - a user may take the object out of the centre on purpose | - |

Sky chart: Mount, PiFinder, **Target** (one marker replaces "Goto" and "Held"). The Hold position is drawn as a second
marker **only when it differs from the Target**, with a plain sentence next to it, e.g. *"Target M13 - holding 3.1' away
(moved by hand)"*.

Target text, in this order of preference: object name (§5), otherwise coordinates.

## 3. Constraints (must not change)

- Hand-paddle fine-centring and deliberate re-framing stay accepted without confirmation: reposition detection, UC4
  "Adopt new position?", `MaxSyncDriftNP`, `EXTERNAL_HOLD`, the settle/fresh-solve gates (#79) are **not touched**.
- Changing the alignment is never automatic. It happens by an explicit **Align** (§6), from wherever the user is.
- Every client sees the same: the Bridge is the one place that holds the Target and publishes it as INDI properties, so
  KStars/Ekos, StellarMate, the Control Center and PiFinder show identical information.
- Design for the observing night: user at the eyepiece, hand paddle in one hand, KStars or PiFinder for the next object.

## 4. Use cases (one evening, also the acceptance script)

The point of a GoTo is that the scope ends up **exactly** on the requested object, found by plate solving. That holds for
every GoTo whose coordinates are known, whoever sent it (see §4.1).

| Step | Target | Hold position | Bridge acts |
|---|---|---|---|
| 1. GoTo M13 from KStars (PiFinder device **or** mount device) | **shown at once** (new) | = Target | mount slews |
| 2. Scope lands 9' off | M13 | = Target | plate solve, Sync + re-Goto until on the target (today only on the PiFinder-device path; **mount-device path: see §4.1**) |
| 3. Hand paddle centres finely, after the refine has finished | M13 | new position | adopts it, does not fight (as today) |
| 4. User moves M13 off-centre on purpose | M13 | new position | as step 3; offset shown as a number, no warning |
| 5. User triggers Align (PiFinder menu, Control Center, later KStars Sync / hand controller) | M13 | = Target | Sync + PiFinder calibration on the object's coordinates (§6) |
| 6. Next GoTo (any source) | replaced at once | | as step 1 |

### 4.1 The same refine for a GoTo sent straight to the mount

> **Implemented for GoTos through INDI (2026-11-27), see §13. Still open: a GoTo started on the controller side (#658).**

Wanted by the project owner: same behaviour whoever initiates the GoTo (hand controller, any INDI client, KStars,
StellarMate, PiFinder). Today the PiFinder-device path refines to the commanded target and the mount-device path does
not. Proposal: split row 2 of the decision matrix in `mount_bridge_reposition_detection.md` §3.2:

- **2a. Mount moved and the mount's INDI target changed (`TARGET_EOD_COORD`, `ON_COORD_SET` = slew/track) - the
  coordinates are known.** Treat it like a PiFinder push-to: Target = those coordinates, shown at once; after arrival
  and a fresh solve the same bounded Sync + re-Goto refine runs (the existing `HOLDING`/`SETTLING` machinery with its
  retry budget and settle gate - no new loop). Only after that does a hand move count as fine-centring and get
  adopted.
- **2b. Mount moved and there really is no target (hand-paddle arrow keys: `:Mn#`/`:Ms#`/`:Me#`/`:Mw#` move at a rate,
  no target exists).** Unchanged: wait for settle and a fresh solve, adopt the landing position, say so on screen.

**BUG (found 2026-11-26): the target of a GoTo started on the controller side never reaches the Bridge.** The hand
controller (OnStep SHC), the OnStep app and SkySafari talk to the OnStep controller over its own TCP/WiFi link, not
through INDI: they set the target (`:Sr#`/`:Sd#`) and slew (`:MS#`). The controller knows its target, but the INDI OnStep
driver polls only the **current** position, so the Bridge sees "the mount moved" and nothing else. That is not
acceptable: a GoTo from the hand controller must behave exactly like one from KStars (2a). Standard LX200 can read the
controller's target (`:Gr#`/`:Gd#`, `getObjectRA/DEC` in libindi's `lx200driver.h`); neither the driver nor the Bridge
calls it today.

Fix direction: the PFSM-patched INDI OnStep driver (`diffs/indi_lx200_OnStep_v2.2.2.diff`) also polls `:Gr#`/`:Gd#`
and updates `TARGET_EOD_COORD` when the controller's target changes. The Bridge already reads that property
(`m_mountTargetNP`, `m_lastMountTargetTime`), so no second channel is needed and KStars, the Control Center and every
other INDI client see the same target. Cautions:
- LX200 **Sync** (`:CM#`) also works on the target set by `:Sr#`/`:Sd#`, so a changed target alone does not mean a GoTo.
  A GoTo is "target changed **and** the mount slews"; a Sync is "target changed and the position jumps without a
  slew" (this is the existing "a Sync must never be mistaken for a GoTo" rule).
- **Checked on the real controller (2026-11-26, read-only, OnStep 10.14a at 192.168.0.140, TCP port 9999):**
  `:GVP#` `On-Step#`, `:GVN#` `10.14a#`, current position `:GR#` 17:02:40 / `:GD#` +31*33:12, **target registers
  `:Gr#` 17:55:13 / `:Gd#` +31*33:12**, status `:GU#` `nNpea/EW150#` (not tracking, not slewing). So the controller
  **does answer** `:Gr#`/`:Gd#`, and the answer is a value of its own (RA differs from the current position by 52 min,
  Dec is identical - looks like the target of an earlier GoTo or Sync followed by a movement in RA only).
- **GoTo test (12:46, owner allowed moves below 1-2 degrees, TCP client sending `:Sr#` `:Sd#` `:MS#`, the commands the
  OnStep app, SkySafari and the hand controller send to the controller):** moved 2 min of RA (~0.43 deg) away and back.
  `:Gr#`/`:Gd#` showed the **new target at once**, before the first move, and kept it during the whole slew; `:GU#`
  showed the slew (the `N` "no goto" flag disappeared) and the position changed gradually (the path overshoots by up to
  ~15' in Dec on the way). Target registers restored afterwards.
- **Sync test (12:47, owner: the pointing model does not matter, no motion):** `:Sr#`/`:Sd#` + `:CM#` also set the
  target registers, and the reported position **jumped by the full 2 min in one step** with the slew flag never
  appearing (`:CM#` answers `N/A#`). Synced back the same way; the position is back within 2 s of RA.
- **Consequence for the design:** the target registers change for both, so the signature that tells them apart is
  exactly the one already in the concept: **GoTo = target changes and the mount slews (position moves gradually, `N`
  flag gone); Sync = target changes and the position jumps without a slew.** Both are visible to the Bridge once the
  driver polls the target.
- **Not tested:** the physical hand controller itself (SHC); it uses the same commands towards the controller, so the
  registers should behave the same, but this is to be confirmed once with a real hand-controller GoTo. If an OnStep
  firmware does not keep the target, the screen says "target unknown, landing position" for that mount, never a guess.

This is a change inside reposition detection, the part the project owner asked to be handled with great care: it needs
its own review, the classification must stay "signal + magnitude" (§4 of that concept), a **Sync must never be mistaken
for a GoTo**, the refine must be bounded and must stop for good once a hand move is seen, and it is verified first with
the simulator before any real night. Not part of slice 1.

Without a known target (a hand controller's own GoTo to a catalogue object sends no coordinates over INDI): the screen
says so — *"Mount moved without a command - target unknown"* while moving, then *"Landing position (source: hand
controller)"*. It must never pretend to know the object. If the mount exposes its target (OnStep over LX200), use it.

### 4.2 Coverage: there is no "normal" evening

Every combination must behave the same way (project owner, 2026-11-26). Where the Target comes from, per setup:

| Setup | Where a GoTo is issued | How the Bridge learns the Target | Refine to the Target |
|---|---|---|---|
| PiFinder only (no mount, e.g. Dobsonian push-to) | PiFinder menu, INDI client on the PiFinder device | PiFinder's `TARGET_EOD_COORD` | none (no mount); Target and offset are still shown |
| PiFinder + mount + INDI client on the **PiFinder device** | KStars/Ekos/any client | PiFinder's `TARGET_EOD_COORD` | yes, today (`handleGotoForward`) |
| PiFinder + mount + INDI client on the **mount device** | KStars/Ekos/any client, StellarMate | mount's `TARGET_EOD_COORD` | yes, since 2026-11-27 (§13) |
| PiFinder + mount + hand controller / OnStep app / SkySafari straight to the controller | the controller's own link, not INDI | **missing today:** driver must poll `:Gr#`/`:Gd#` (§4.1 BUG) | **missing today** (slice 4) |
| Same, hand-controller arrow keys only | - | no target exists | none; landing position adopted and said so |
| Any of the above after a hand correction | - | Target unchanged | no fight; offset is only a number; Align is explicit |

## 5. Object name

PiFinder already has the catalogues. PiFinder resolves the nearest catalogue object to the Target coordinates (tolerance
to be decided, a hint such as "~M13" when it is not exact) and shows the name on its own screen; the Control Center
reads it from PiFinder. **No match - show the numbers.** Neighbours (NGC 6207 beside M13) mean the name is a hint, not
proof, and the coordinates stay one tap away.

## 6. Align from everywhere (own follow-up, only noted here)

Align means: *"the scope points exactly at the Target now"* - mount Sync to the Target's coordinates plus PiFinder's own
calibration (`align_on_radec()`, #313). It needs the **Target's** coordinates, not PiFinder's position, which is what
is being corrected. Sources: the PiFinder menu (exists), the Control Center (exists), KStars' Sync button and the hand
controller's sync (both show up to the Bridge as a mount position jump without a slew - the same signature the sky
follower already detects). Whether the existing button "Align to Held Target" already does the right thing has to be
verified in the code before this is scheduled.

## 7. Slices (smallest and safest first)

1. **Control Center only, no driver change.** Merge the "Goto" and "Held" markers into Target (+ Hold position when it
   differs), show the target from the moment the command is issued, add the neutral offset number and the status
   sentence. Data: `TARGET_EOD_COORD` of mount/PiFinder (already used for the Goto marker), `TARGET_SOURCE`,
   `TARGET_SOURCE_AGE`, `HELD_TARGET_HORIZON_STATUS`, PiFinder and mount positions.
2. **Driver, additive - implemented on branch `feat/657-target-status`, verified on the simulator 2026-11-26.** One new read-only property `TARGET` (coordinates, source, time) fed from
   `getLastGotoTarget()`, set when a GoTo command with coordinates is seen. It is written by nothing else: hand moves,
   mount motion, Sync and reposition adoption do not touch it. Open test points: a KStars **Sync** must not become a
   Target (check `ON_COORD_SET`); a PiFinder target that was only selected, not pushed, is not a Target.
3. **Name** from PiFinder (§5).
4. **Same refine for every GoTo whose target is known** (§4.1) - includes reading the target from the OnStep controller
   (`:Gr#`/`:Gd#`, driver patch) so a hand-controller GoTo is covered. Touches reposition detection and the INDI OnStep
   driver, own review, simulator first, then the real OnStep.
5. **Align from everywhere** (§6) - own concept, own review.

Renaming "Held target" in the quick-action buttons ("Align to / Goto / Revert to Held Target") happens last, together
with the help text, because the labels carry behaviour.

## 8. Test plan

Realmode sky simulation (Telescope Simulator + `pifinder_sky_follow.py` with `--goto-error-east 8 --goto-error-north -5`)
gives a known landing error, so steps 1-6 of §4 can be checked against known numbers: Target stays M13, Offset reads
about 9.4' after landing, Hold position follows a simulated hand correction, Drift and Offset can be told apart.
The follower must see the slew (the Simulator's slew rate has to be low enough that short moves are visibly *Busy*).

## 9. Related findings from the same test (separate issues)

- **Auto-correct (Sync) synced to a solve taken before the mount stopped**: after the M3 GoTo the first Sync moved the
  mount by 24.5' instead of the real 9.4' (solve about 1 s old, last slew step about 27'); the second Sync fixed it. The
  freshness rule (5 s) does not look at "mount stopped, solve taken after".
- **Goto-Forward showed "Waiting on fresh solve" for more than 40 s** after a KStars GoTo while solves were fresh. Cause
  not found yet; needs the driver's debug log.
- **Auto-correct with the Goto action cannot be selected in the Control Center** (only through INDI).
- **After switching the mount device the Bridge does not rebind** until CONNECTION Disconnect/Connect. #158 (closed)
  was the same symptom ("changing Active Mount while connected doesn't actually rebind the client"): regression or not
  fully fixed. Related self-heal behaviour: #385, #505.

## Related

- Issues: #170 / #173 (Auto-correct Goto must land on and hold a GoTo made with the mount's own controls - closed; the
  expectation of this concept, to be re-verified against §4.1), #178, #585, #600, #603, #79, #158.
- [mount_bridge_reposition_detection.md](mount_bridge_reposition_detection.md)
- [mount_bridge_sync_on_pifinder_align.md](mount_bridge_sync_on_pifinder_align.md)
- [mount_bridge_external_hold.md](mount_bridge_external_hold.md)
- [pifinder_realmode_sky_simulation.md](pifinder_realmode_sky_simulation.md)

## 10. Slice 2 result (2026-11-26)

`TARGET_STATUS` (RA, DEC JNow, OFFSET_ARCMIN = PiFinder's solved position vs the Target, AGE_SEC) and `TARGET_STATUS_SOURCE`
(`Mount` / `PiFinder`) on the Mount Bridge, read-only, fed from the clients' own target properties (`getLastGotoTarget()`).
Simulator, landing error 8' E / 5' S, Auto-correct with the **Sync** action: GoTo M3 gave Target 13.7135 h / +28.32, offset
9.35', source Mount; after the Auto-correct Sync (drift 0.04') the Target and the offset **stayed** (9.24'). A Sync sent by
an INDI client to the Telescope Simulator does not change its `TARGET_EOD_COORD` (not yet checked for the LX200 OnStep driver).

Known limit, same root as #658: with Auto-correct + the **Goto** action (or Goto-Forward) reposition detection adopts the
landing position and pushes it to PiFinder as a "PUSH n" target; the Bridge then reports that PiFinder target, which is newer
than the mount's. The Target then is the landing position, not the requested object.

Testing note: the Control Center's readiness self-heal re-applies the coupling *mode* last chosen in the page but not the
*correction action*, so after a driver restart the action comes from the saved driver config (it came back as Goto
instead of Sync). Choose both in the Control Center after a restart, and check `CORRECTION_ACTION`.

## 11. Refine after a GoTo through the PiFinder device (2026-11-26, sky simulation, Goto-Forward)

Setup: Telescope Simulator, landing error 8' E / 5' S for a 45 deg slew, scaled with the slew length (a 38 deg slew landed 6.8' E /
4.3' N, a 9' corrective slew 0.4' / 0.2'). GoTo M13 / M3 sent to the PiFinder LX200 device, as KStars does.

- **Before the fix:** the first landing took 34 s of silence, then reposition detection (Fall 4) classified the 8' landing error as
  "likely a deliberate reposition or a disturbance", the 45 s confirmation timed out and the refine only ran as a "revert to
  the held target". About 70 s from GoTo to 0.6'.
- **Cause:** `handleRepositionDetection()` gated Fall 3/4 with `weCommandedIt`, which covers SLEWING but not SETTLING, although the
  comment above it says "SLEWING/SETTLING". SETTLING (the arrival verification with the Sync + re-Goto refine) was preempted every
  tick the drift could be measured and the landing error exceeded what passive sky motion allows since the last confirmed-good time.
- **Fix:** Fall 3/4 are skipped while our own forward or correct state is SETTLING. Fall 2 (the mount moving without our command) is
  unchanged. SETTLING is bounded (freshness wait, retry budget), then HOLDING applies reposition detection again.
- **After the fix:** landing, "Arrival verified ... residual 7.7 arcmin exceeds threshold 2.0 - synced and re-issued Goto" 2 s later,
  second landing 0.4', verified. About 26 s from GoTo to 0.47' off the target; `TARGET_STATUS` offset 0.47'.
- Not covered: a hand-paddle move during the few seconds of SETTLING is now refined back like a landing error (it does not ask
  "Adopt new position?"); to be judged by the owner, see the open question on the issue.

## 12. Positioning status: tell the user when the Bridge is still fine-adjusting (#665)

After a GoTo the Bridge slews, waits for a PiFinder solve, refines and verifies (about 26-30 s in the sky simulation). The user could
not tell whether the wait was their own misalignment or the program, nor when to keep their hands off the hand controller.

Three surfaces, one source:
1. **Bridge, INDI** (done): `POSITIONING_STATUS` (ATTEMPT, ATTEMPTS_MAX, RESIDUAL_ARCMIN, ELAPSED_SEC, TO_GO_DEG, SOLVE_AGE_SEC,
   HANDS_OFF) and `POSITIONING_PHASE.PHASE`: IDLE, SLEWING, VERIFYING, REFINING, ON_TARGET, GAVE_UP, HOLDING. Derived from the forward
   and correct state machines, changes none of them. HANDS_OFF = 1 from the start of the slew until the arrival is verified.
2. **Control Center**: a line under the sky chart (phase, attempt, residual, the cause of a wait, a Hands off / Hands free badge,
   a four-step bar).
3. **PiFinder screen**: an inverted "MOUNT MOVING" bar while the Bridge works.

Measured in the sky simulation (Goto-Forward, 38 deg slew): SLEWING 8 s (TO_GO 28.9 -> 0.4 deg), VERIFYING 8 s, REFINING 1 attempt
(residual 8.1'), VERIFYING 8 s, ON_TARGET after 28.4 s, residual 0.7'. Each verification costs about 8 s (SETTLE_TICKS 3 x 2 s, then
the wait for a fresh solve): the main part of the delay the user noticed.

**A second finding while building it:** the same GoTo was executed twice. The client's GoTo set the PiFinder LX200 device's
`TARGET_EOD_COORD`; about 30 s later `pollCurrentTarget()` republished PiFinder's pushed object converted back to JNow, 0.25' away;
the Bridge took it for a new target and slewed again (a second "hands off" stretch right after ON_TARGET). Fix in the PiFinder
LX200 driver: a target within 1' of the one already published is the same object and is not republished. After it: one run,
ON_TARGET stays.

### 12.1 Built and checked (2026-11-26)

- **Bridge** posts the status to PiFinder (`POST /api/bridge_positioning`) on every change of phase or attempt and every 3 s while
  hands off; after a failed post it waits 30 s (a PiFinder without the patch answers 404 and shows nothing).
- **PiFinder** (three diffs: `pfsm_bridge_status_py.diff` new module, `api_extensions_bridge_status_py.diff` registers the route,
  `ui_base_py.diff` title bar): "MOUNT MOVING" in a bright title bar while the Bridge moves the mount or verifies, "ON TARGET" for
  12 s, "MOUNT OFF 2.4'" (from 60' on in degrees, "MOUNT OFF 103°"; bright on black, no status icons) for 20 s after giving up. The number is the distance between mount and PiFinder. If both agree but PiFinder is more than the threshold from the GoTo target, the phase is `OFF_TARGET` ("OFF TARGET 103°"; card: "Not on the target") - "On target" needs both. The Control Center card shows the badge "Don't touch the mount" only while the mount is moved (wording changed 2026-11-27: "Hands off / Hands free / Hand OK" was not understood). The rotating constellation/SQM text is suppressed meanwhile (it ran into the longer
  title). A hands-off status that is not renewed within 8 s is ignored (fail safe). The title bar holds about 13 characters on the
  128 px display.
- Checked on the real PiFinder screen (`/api/screen`) and with the sky simulation end to end: SLEWING -> VERIFYING -> REFINING ->
  VERIFYING -> ON_TARGET in 30 s.
- Bugs found by running it, not by the tests: a Unix timestamp above 1e9 was thrown away by the number guard (every status looked
  stale; the tests used small times, they now use a real one); a residual of 123' made the text too long for the bar.
- Seen, not fixed: the Bridge did not follow the PiFinder LX200 target for two GoTos after it was started while PiFinder had just
  been restarted; a second restart of the Bridge fixed it (same family as #662 / #118).

## 13. Refine after a GoTo sent to the mount (2026-11-27, Telescope Simulator, sky simulation)

Requirement (#170, §4): whoever starts the GoTo, the scope ends up on the object. Until now only the PiFinder-device path did
that; a mount-side GoTo was taken for a movement without a command, the landing position became the target, and the remaining
difference between mount and PiFinder triggered the 45 s question of reposition detection (seen live: SLEW to Altair ended 7'
beside it).

How the Bridge tells what happened (its INDI client, `consumeMountEvent()`):

| Seen on the mount device | Meaning | Reaction (GoTo coupling) |
|---|---|---|
| `TARGET_EOD_COORD` published, away from the mount's position, not the echo of an own GoTo | GoTo of another client | those coordinates are the target at once (also sent to PiFinder); wait until the mount stands still, then the existing verify / Sync / re-GoTo sequence (`ForwardState`, 3 attempts) |
| `TARGET_EOD_COORD` equal to the mount's position | a direction button was released (INDI copies the position into the target) | ignored |
| `TELESCOPE_MOTION_NS` / `WE` switched on | hand movement | ends a running refine; position taken over |
| `TELESCOPE_ABORT_MOTION` | stop | ends the refine; no movement by the Bridge until the next GoTo, coupling change or manual trigger (no re-GoTo, no 45 s question) |
| `ON_COORD_SET` = Sync from another client, then a jump | their Sync | unchanged behaviour |

After any movement without target coordinates the mount is synced to PiFinder at once if they differ by more than the threshold
(no question), from a frame exposed after the mount stood still (#659). The 45 s question remains for a disagreement without any
mount movement.

Live check: `test_tools/mount_goto_refine_test.py --move` (GoTo, half-degree GoTo, direction button, stop, PiFinder GoTo). All
five passed on 2026-11-27; against the previous driver the first one failed (45 s question). Once, in the first run shortly after
a driver restart during which StellarMate's Web Manager restarted the driver in parallel, a mount GoTo was not recognised; it did
not recur in the following GoTos, including a deliberate repeat. The driver now logs why it does not take a new mount target as a
GoTo.

Not covered: the real OnStep; a stop on the hand controller itself (not visible in INDI); Ekos correcting during a **GO** at the
same time as the Bridge; a first landing further off than the auto-Sync limit (120') ends in "gave up"; alignment routines and
polar alignment, which slew the mount themselves - switch the coupling off for those.
