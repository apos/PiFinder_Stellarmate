# Concept: Control Center Guide Rewrite (screenshots + use-case walkthroughs)

> **Status: concept - not started.** Written 2026-09-09 after a long live-testing session left the
> Mount Bridge / Sync GUI significantly changed (see
> [`session_start_position_reconciliation.md`](session_start_position_reconciliation.md) §8.8/§8.9)
> with no corresponding update to the user-facing guides. Blocked mid-session on tooling (see §5) -
> handed off to a fresh session rather than solved awkwardly here.

## 1. Why

`Readme_ControlCenter.md`/`_de.md` and `gui_installer/help.html` predate this session's Mount
Bridge/Sync work entirely - `Readme_ControlCenter.md`'s own Table of Contents has no Mount Bridge
section at all. The GUI area that got the most live-testing and the most fixes tonight (§8.8/§8.9)
is exactly the area with zero user-facing documentation.

## 2. Scope

- `Readme_ControlCenter.md` + `Readme_ControlCenter_de.md` - primary target, needs a new "Mount
  Bridge & Sync Workflows" section (nothing like it exists yet).
- `gui_installer/help.html` - the in-app help panel (linked from `(i)` icons throughout the GUI,
  e.g. `href="/help.html#mount-bridge"`) - check for matching gaps once the Readme content exists.
- Other `Readme_*.md` files - out of scope for this pass unless a specific gap is found.

## 3. Context that must inform the content (do not screenshot/document the wrong state)

- At write time, the live system was in **Full Simulation (INDI/Mount Bridge)** mode - simulated
  PiFinder + a simulated mount device ("LX200 OnStep", presented as mount type `EQ_GEM`), not real
  hardware. Any screenshots must be captioned as simulation, not presented as if from Real Hardware.
- **No meaningful Goto in this simulation setup** (direct instruction, 2026-09-09) - the walkthroughs
  should stick to **Sync-based** recovery flows (exactly what tonight's live-testing covered and
  verified end-to-end), not Goto-based ones. "Goto Home Position" is an exception - it's a native
  OnStep reference-position command, not a coordinate Goto, and was working.
- Before each screenshot: bring PiFinder/the tile into a clean, explicable state first - don't
  capture mid-broken-test-residue.

## 4. Agreed use-case selection and priority (confirmed with the user)

1. **Baseline reading**: PiFinder tile + Mount Bridge tile in their normal, collapsed state (badge
   row, Drift/Alt, Coupling status) - the foundation every other use case builds on.
2. **"PiFinder Simulator isn't related to the mount"** - Re-seed vs. Sync, when to use which. Most
   live-tested flow of the whole session.
3. **Mount below the horizon** - the recovery card, "Sync mount from PiFinder" / "Goto Home
   Position".
4. **Setting up Coupling modes** (Verify/Alert vs. Auto-correct) - one-time basic configuration.
5. **Synthetic Solve vs. Manual one-shot seed** - the difference, when to use which for testing.

## 5. Screenshot depth per use case

- Baseline: top-level badge rows only, **no** expanded sub-panels (Settings/Setup Checklist stay
  collapsed - not relevant to a first read).
- Coupling: **Quick Actions + Coupling Visual/GoTo** expanded (as normally shown), **Settings**
  collapsed (its own, separate, detail-level section).
- One screenshot per use case where possible - state + the action/button that resolves it in the
  same frame, not a click-by-click screenshot cascade.

## 6. Blocked here: screenshot tooling/file-transfer (read before resuming)

Live-verified 2026-09-09, this session runs its Bash tool on `stellarmate-pi5` (Linux/aarch64,
confirmed via `hostname`/`uname`); the only working browser automation
(`mcp__claude-in-chrome__*`, confirmed connected and working) controls the user's **macOS** Chrome -
two separate machines, no shared filesystem. `computer` tool's `save_to_disk: true` reports success
but a broad Pi-side filesystem search (`find / -xdev -newer ...`) found no new file anywhere - the
saved image does not land anywhere this session's Bash can reach. A Firefox-headless-on-the-Pi
workaround was also tried and ruled out: `firefox --headless --screenshot` cannot do the interactive
steps these use cases need (expanding panels, clicking Coupling/Sync buttons - it can only load a
URL once, no scripting), and it hung/timed out anyway (likely the Control Center's Basic Auth, which
headless Firefox has no way to satisfy).

**Not solved - handed to a fresh session instead of forced.** Whatever session picks this up needs
to work out its own architecture for getting actual image bytes into this git repo, e.g.:
- Running somewhere with both the browser (or a local headless one that can actually click through
  states) and a local clone of this repo on the *same* filesystem, or
- Some other file-transfer path between wherever screenshots are captured and this repo.

## 7. What's already known/re-usable when this resumes

- Live-observed exact current values (2026-09-09, may be stale by the time this resumes - re-verify
  the *layout*, the specific numbers don't matter): Drift 0.7', Alt 39°, Coupling = Verify/Alert
  only, "PiFinder Simulator isn't related to the mount" banner genuinely showing (good real example
  for use case 2).
- The Mount Bridge GUI consistency pass from 2026-09-09 (see CHANGELOG.md) is useful background for
  writing accurate walkthrough text even before new screenshots exist.
