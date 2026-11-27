# Align PiFinder automatically after an Ekos plate solve ("GO" in the StellarMate app)

> **Status: concept, not implemented.** Asked for by the project owner on 2026-11-27: "GO can be useful if one also wants a solve
> through the telescope camera in order to align the PiFinder afterwards. It would be great if PFSM did that automatically when it
> comes from SMOS/GO and a solve actually happens."

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
