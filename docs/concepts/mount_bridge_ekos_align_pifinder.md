# Align PiFinder automatically after an Ekos plate solve ("GO" in the StellarMate app)

> **Status: implemented 2026-11-27 (§5), not yet observed with a real Ekos solve.** Asked for by the project owner on 2026-11-27:
> "GO can be useful if one also wants a solve through the telescope camera in order to align the PiFinder afterwards", and: polar
> alignment and mount alignment must pause the Bridge like guiding does. §1-§4 are the first draft; §5 is what was built.

## 1. Idea

A successful Ekos alignment solve through the telescope camera is the best knowledge there is about where the telescope points. PiFinder
sits beside the telescope and needs exactly that for its own Align ("the scope points here"). So after such a solve PFSM aligns PiFinder
without anybody pressing a button.

## 2. What was checked (2026-11-27, Pi 5, read only)

- The StellarMate app's **GO** sends `mount_goto_target` and then `align_solve` to Ekos (KStars log).
- Ekos offers the alignment state on the session bus: `org.kde.kstars`, `/KStars/Ekos/Align`: property `status` (emits changes), signals
  `newStatus` and `newSolution`, method `getSolutionResult`. After a failed solve `status` read 2 and `getSolutionResult` -1e6 values.
- Both GO attempts of that day ended in "Solver Failed" (optics covered), so a successful run has **not** been observed yet.

## 3. Behaviour

1. Ekos alignment starts: the Control Center sets the Mount Bridge's external hold (as it does while guiding), so the Bridge does not
   correct against Ekos' own sync and slew.
2. Alignment **succeeds**: wait until Ekos has finished (including "slew to target"), then align PiFinder on the mount's position
   (PiFinder's own Align, the same as "Sync PiFinder from mount"), confirm it visibly, release the hold.
3. Alignment **fails or is aborted**: nothing is aligned; release the hold and say so.
4. A setting switches the feature off. Every automatic align is written to the log with the solve's position.

Safety: only a real solve triggers it - never a manual Sync without a solve, never a position below the horizon, never while PiFinder
cannot see what the telescope sees (outside the camera's field of view PiFinder refuses its Align; this is reported, not overridden).

## 4. Open points

- The meaning of every `status` value for the installed KStars version.
- Does a successful GO end with the mount on the target (Ekos action "slew to target") on the real OnStep?
- Interaction with the planned refine of mount-side GoTos (target transparency §4.1): during a GO, Ekos refines; the Bridge must not.
- Test: Telescope Simulator with the CCD Simulator (it renders GSC stars, so Ekos can solve) before the real camera and mount.

## 5. What was built

Owner's rule for the Ekos solver action: Sync -> do the same for PiFinder; Slew to target -> the scope ends on the object;
Nothing -> PFSM does nothing either.

- **Control Center** (same watchdog as guiding), every 3 s. KStars 3.8.5 `Align.status`: 0 idle, 1 complete, 2 failed,
  3 aborted, 4 in progress, 5 successful, 6 syncing, 7 slewing, 8 rotating, 9 suspended. 4 and 6-9 start the hold. It is kept
  while anything observable goes on: that status, a new line in `Align.logText`, or direction motion of the mount (how polar
  alignment turns it between two images). It ends 15 s after the last of these - no longer waiting time stands in for a check
  (owner, 2026-11-27). Camera exposures are not a signal of their own: measured with the CCD simulators, they happen only while
  Ekos is "in progress", and the alignment camera may be the imaging or guide camera. The page shows what keeps the pause.
- If the end state is solved (1 or 5) **and** another client synced the mount during the hold (`EXTERNAL_HOLD_SEEN.MOUNT_SYNCS`)
  and the coupling is on: PiFinder's Align on the mount's position, while still held. A refusal is logged, never forced.
- Release reason `alignment ended: solved` / `alignment ended: not solved`. **Driver:** after a solved end, or if the mount was
  synced or turned by its direction buttons during the hold, it moves and syncs nothing until the next GoTo; otherwise an
  interrupted GoTo is carried on.
- Checked: `test_tools/alignment_hold_test.py` (7, stand-ins), live on the Telescope Simulator the driver side
  (`mount_goto_refine_test.py --only hold`). **Not yet:** a real Ekos solve, polar alignment, the mount model tool.
