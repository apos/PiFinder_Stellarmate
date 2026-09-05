# First-Time Setup Wizard — Concept

Companion to the main [README.md](../../README.md) and
[Readme_ControlCenter.md](../../Readme_ControlCenter.md). Covers GitHub issue
[#265](https://github.com/apos/PiFinder_Stellarmate/issues/265) at the depth standard in
`basic-memory/basic-memory/00021_bm-documentation-depth-standard.md` — this is a **concept
document only** (per `basic-memory/basic-memory/00020_bm-cpt-command-system.md`'s cpt gate): it
proposes an architecture and a phased implementation, but no code changes ship from this document
alone.

## 1. Basic Functionality (Overview)

The Control Center already exposes every control a working Mount-Bridge setup needs — Role choice,
a 6-step Setup checklist, four Coupling presets, Multi-Point Alignment — but no *guided path*
through them. A first-time user has to discover the right order themselves, and the page's own
visual order doesn't match the order the code actually requires (see §3.1). The First-Time Wizard
is a thin guidance layer on top of the existing controls — it doesn't replace or duplicate any of
them, it sequences and highlights the ones a given user, in their current state, actually needs
next.

## 2. Use Cases

Per the issue, two starting situations, made concrete against what's actually on the page today:

1. **Fresh install** — a user has just run Install/Update for the first time. Nothing is
   configured: no Web Manager profile (or only the read-only "Simulators" default), no Role chosen,
   no mount linked, no Coupling preset applied. Goal: get to "PiFinder is talking to my mount" (or,
   for a PiFinder-only/Control-host role, to the equivalent end state for that role) in as few
   manual steps as possible.
2. **Returning user** — setup already exists, but something changed: a StellarMate/SMOS update
   reset `/etc` state (see README's "SMOS Updates" section), a driver got manually removed in Web
   Manager, hardware was swapped (new mount, new PiFinder unit), or a reboot left Ekos not yet
   connected. Goal: quickly identify *which* of the 6 checklist items regressed, without re-doing
   the ones that didn't.

Both scenarios read the exact same underlying state (§4) — the wizard's only job is presenting it
as "what to do next" instead of "here are six independent status rows and four unrelated tiles".

## 3. Architecture

### 3.1 Context: why a wizard, not just better ordering

Investigated live while writing this document — the actual current control flow has a real
ordering inversion, not just a discoverability gap:

- **On screen**, the Mount Bridge tile shows, top to bottom: Role cards → Mode cards/readiness line
  → Setup checklist & diagnostics (1. Profile → 2. KStars Link → 3. Drivers → 4. Mount → 5. Ekos →
  6. Connect) → Multi-Point Alignment.
- **In code**, `onRoleCardClick()` (`gui_installer/status_page.html`) hard-requires step 1 to be
  done first: `if (!wmSelectedProfile) { alert('Pick a profile in step 1 first.'); return; }` — a
  Role card click before that is a dead end (an alert, no progress).

So the two things closest to "step 0" on the page are in the wrong relative order for a first-time
user who reads top-to-bottom. A wizard doesn't need to reorder the static page (Role stays the
primary navigation once things are set up, per the original design rationale still in the code
comments) — it needs to present the *correct* first action regardless of where that control happens
to live spatially.

### 3.2 Building blocks (existing, reused — no new state machine)

The wizard is a **read layer + a "next action" pointer**, not a new source of truth:

| Existing signal | Where it already lives | What it tells the wizard |
|---|---|---|
| `existing_install` | `/state` | Fresh install vs. returning device (coarse) |
| `wmSelectedProfile`, `wmServerRunning` | `status_page.html` JS state (from Web Manager polling) | Step 1 done? |
| `wmKstarsLinked` | same | Step 2 done? |
| `wmHasLx200`, `wmHasBridge` | same | Step 3 done? (and which Role that implies) |
| `wmActiveMount` | same | Step 4 done? |
| `wmEkosConnected` | same | Step 5 done? |
| (Step 6, Connect) | `mb-connect-*` button states | Step 6 done? |
| `lastSolveSource` | same | "Solve" health (already tracked in `updateSimReadinessLine()`) |
| Active Coupling mode | `mb-preset-*` button active state | Whether a preset has ever been applied |

`updateSimReadinessLine()` (`gui_installer/status_page.html`, already shipped for #268/#267's
readiness line) already computes a 6-item `[label, ok]` array from exactly these signals. The
wizard's "what's left" list is the same computation, reframed as ordered steps with a "do this
next" affordance instead of a flat status line.

### 3.3 Proposed flow

```mermaid
flowchart TD
    Start([User opens Control Center]) --> CheckInstall{existing_install?}
    CheckInstall -->|No| InstallStep[Guide: Install/Update tile]
    CheckInstall -->|Yes| CheckReady{All 6 checklist<br/>items green?}
    InstallStep --> CheckReady

    CheckReady -->|No, one or more red/amber| Diagnose[Wizard panel:<br/>first red/amber item,<br/>highlighted + scrolled to]
    Diagnose --> ActOnStep[User completes that step<br/>via its existing control]
    ActOnStep --> CheckReady

    CheckReady -->|Yes, all 6 green| CheckCoupling{Coupling preset<br/>ever applied?}
    CheckCoupling -->|No| SuggestCoupling[Wizard panel:<br/>suggest a Coupling preset<br/>based on Role]
    CheckCoupling -->|Yes| Done([Wizard: "Setup complete" —<br/>panel collapses/hides])
    SuggestCoupling --> Done
```

Scenario detection (fresh vs. returning) falls out of the same state, not a separate branch: a
fresh install starts at "0 of 6 green", a returning device with one regressed item starts partway
through the same loop. No separate code path needed for the two use cases in §2 — they're the same
flow at different starting points, which is also why no "skip this if returning" logic is required.

### 3.4 Where it lives on the page

A new, dismissible panel (`#setup-wizard`) at the **top** of the Mount Bridge tile, above the Role
cards — the one place both "Role" and "Setup checklist" are visible without scrolling, so the
wizard can literally point at ("↓ start here") whichever control the user needs next regardless of
which existing section it lives in. Collapses automatically once §3.3's `Done` state is reached
(explicit user setups that never want it should be able to dismiss it manually too — a
`localStorage` flag, same pattern already used elsewhere on this page for collapsed-state memory,
e.g. `toggleCollapsibleSection`).

## 4. Design Principles

Per `basic-memory/basic-memory/00017_bm-ui-design-anforderung-klar-einheitlich.md`, already
established for this page and followed here, not reinvented:

- **No decorative emoji, traffic-light dots only.** The wizard's "done"/"next"/"not yet" states
  reuse the existing `.status-dot` (`dot-white`/`dot-green`/`dot-yellow`) vocabulary — a 7th status
  system would violate "same status logic, same visual language everywhere".
- **Label the visible thing, not the mechanism.** The wizard step text names the actual control
  ("Pick a profile below", not "Configure `wmSelectedProfile`").
- **Tooltips for the technical detail**, keeping the primary wizard text short.
- **Visible feedback on every action** — clicking "Take me there" scrolls to and briefly highlights
  the relevant existing control (a short outline-flash, not a new modal/dialog) rather than
  performing the action itself; the wizard points, the existing control still does the work. This
  also sidesteps building a second, parallel action path that could drift out of sync with the
  existing one (see #204/#216's ACTIVE_DEVICES-drift class of bug — a lesson from building a second
  code path that disagreed with the first).
- **Functional grouping**: the wizard is its own panel, not squeezed into an existing tile's
  unrelated content, since it's a cross-cutting layer over multiple tiles (Role + checklist +
  Coupling), not a peer of any one of them.

## 5. Technical Reference

No new backend state or endpoints — `/state`, the Web Manager polling already backing
`wmSelectedProfile`/etc., and `updateSimReadinessLine()`'s existing computation are sufficient. New
client-side surface only:

| Function (proposed) | Responsibility |
|---|---|
| `computeWizardStep()` | Same inputs as `updateSimReadinessLine()`; returns the single next incomplete step (or `null` = done) instead of the full 6-item list |
| `renderWizardPanel(step)` | Shows/hides `#setup-wizard`, sets its text + "Take me there" target from `step` |
| `scrollToAndHighlight(elementId)` | Generic helper - scroll + brief outline flash. Reusable outside the wizard too (e.g. a future "jump to failing check" link elsewhere) |

## 6. Test Strategy

- **Automated**: none currently planned — this whole page has no existing test harness beyond
  manual QA (consistent with the rest of `gui_installer/`).
- **Manual, both use cases from §2**:
  1. Fresh install (`bin/simulate_fresh_install.sh --mode=fresh` or a real reinstall) — confirm the
     wizard starts at step 1 and correctly advances through all 6 as each is completed.
  2. Simulated regression on an already-configured device — manually remove a driver in Web
     Manager, or disconnect Ekos — confirm the wizard correctly identifies *that* item, not a
     generic "something's wrong".
  3. Role-before-Profile dead end (§3.1) — confirm the wizard never suggests clicking a Role card
     before step 1 is done, closing the exact gap that motivated this document.

## 7. Effort / Priority

T-shirt size **M** (per `basic-memory/basic-memory/00019_bm-github-project-schema-todo-format`) —
no new backend, no new state machine, but touches the Mount Bridge tile's most-used code paths and
needs careful live verification against both use cases. Priority **P1**: raised directly from live
Pi4 testing as a real onboarding friction point, but not a correctness bug — nothing is broken
today, first-time setup is just harder than it needs to be.

## 8. Strategic Roadmap (dependencies made explicit)

1. **`computeWizardStep()` + read-only wizard panel** (no "Take me there" yet) — proves the step
   detection logic against both use cases in §6 before adding any interaction. Depends on nothing
   new; pure read of existing state.
2. **`scrollToAndHighlight()` + wired-up "Take me there"** — depends on (1) being verified correct;
   adding navigation on top of a wrong step-detection would just guide users to the wrong place
   faster.
3. **Dismiss/auto-collapse behavior** (`localStorage` persistence) — depends on (1)+(2) existing;
   premature before the panel's content is trustworthy.
4. **Coupling-preset suggestion step** (§3.3's `SuggestCoupling`) — deliberately last: the first
   three steps alone already close the concrete gap from #265 (getting through the checklist); a
   suggested Coupling preset is a smaller, separable enhancement on top, not a blocker for the core
   wizard to ship.

Each numbered step above is sized to become its own GitHub sub-issue (mirroring
`docs/concepts/pifinder_fake_solve_simulation.md`'s precedent of ordered, linked sub-issues) once
implementation is approved — not created yet, per the cpt gate: this document is the concept pass
requested in #265, actual code needs a separate go-ahead.
