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

### 4.1 Open decision: the same refine for a GoTo sent straight to the mount

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
| PiFinder + mount + INDI client on the **mount device** | KStars/Ekos/any client, StellarMate | mount's `TARGET_EOD_COORD` | **missing today** (§4.1, slice 4) |
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
