# Concept: A native Ekos module for PiFinder

> **Status: concept — not yet implemented.**
> Tracked as [GitHub issue #370](https://github.com/apos/PiFinder_Stellarmate/issues/370)
> (`concept` + `pifinder` labels) on [Project #15](https://github.com/users/apos/projects/15).
> Under discussion with the KStars maintainer (Jasem Mutlaq). Largely subsumes
> [#43](https://github.com/apos/PiFinder_Stellarmate/issues/43) and feeds
> [#35](https://github.com/apos/PiFinder_Stellarmate/issues/35) /
> [#36](https://github.com/apos/PiFinder_Stellarmate/issues/36); update #370 if this concept is
> promoted, revised, or dropped.

## 1. Overview

Today PFSM's operational surface is split across three UIs:

- the **web Control Center** (`gui_installer/`, port 8765) — install/update, mode switching,
  hardware checks, and the Mount Bridge coupling dial;
- the raw **INDI Control Panel** in KStars — device connection, `ACTIVE_DEVICES`, advanced
  properties;
- **Ekos** itself — the actual imaging session (Mount, Capture, Guide, Align, Scheduler).

A user coupling PiFinder to a mount for an imaging run touches all three. Every cross-cutting
concern — does the Mount Bridge know guiding is running? does it know the Scheduler is mid-job? —
becomes a bridging problem because PFSM lives *outside* Ekos
(see [session_start_position_reconciliation.md](session_start_position_reconciliation.md) §6,
[#324](https://github.com/apos/PiFinder_Stellarmate/issues/324)).

**This concept**: a native **Ekos module** for PiFinder — a tab in the Ekos window alongside
Mount / Capture / Focus / Guide / Align / Scheduler, compiled into KStars, contributed upstream.

## 2. Why a module beats the current split

- **In-process access to Ekos state.** The module *is* an Ekos citizen: it reads the Guide
  module's `GuideState`, the Scheduler's state, and the Optical Train directly — no D-Bus bridge,
  no companion process, no `TIMED_GUIDE_*` heuristic. §6/#324's whole detection problem dissolves.
- **Ships with StellarMate automatically.** KStars is the core of the StellarMate stack; a merged
  module is on every box without a separate install step.
- **One coherent UI.** Coupling mode, drift, one-shot actions, Multi-Point Alignment, and PiFinder
  status all sit in the same window as the rest of the session, in Ekos's own idiom.
- **Roadmap alignment.** [#43](https://github.com/apos/PiFinder_Stellarmate/issues/43) ("surface
  Quick Actions / Coupling / INDI setup / Multi-Point / Test Hardware in the app") is largely this.
  [#35](https://github.com/apos/PiFinder_Stellarmate/issues/35) /
  [#36](https://github.com/apos/PiFinder_Stellarmate/issues/36) (SMOS integration) build on it.

## 3. Not a plugin — an upstream module

Ekos has **no runtime plugin loading** for its modules. Mount, Capture, Focus, Guide, Align,
Scheduler, Observatory, Analyze are all compiled into the KStars binary. "Developing the plugin"
therefore means **contributing a module to KStars** via a merge request on
[invent.kde.org/education/kstars](https://invent.kde.org/education/kstars), reviewed and merged by
the KStars maintainers. The prior contact with Jasem removes the largest risk (acceptance and
scope); the scope/shape should be agreed with him *before* code.

## 4. The one design decision: device *category* vs. *orchestrator*

| Option | What it entails | Assessment |
|---|---|---|
| **New device category** | Define a new `INDI` interface in libindi (a `<< interface >>` like `INDI::Telescope`, `INDI::CCD`) for "plate-solving position source / push-to aid"; add an `ISD::` wrapper in KStars; the module consumes it. | Touches libindi too. Probably overkill — `PiFinder LX200` is already `INDI::Telescope`, and PiFinder's job (a position source + a coupling policy) doesn't obviously need a new category. |
| **Orchestrator** *(preferred)* | The module consumes the **existing** devices — `PiFinder LX200` (`INDI::Telescope`) and `PiFinder Mount Bridge` (auxiliary) — via the current `ISD::` wrappers, and reads Guide / Scheduler / Align / Optical Train state directly. It surfaces status and drives the Mount Bridge; it does not become a device itself. | Smaller, no libindi change, reuses proven logic. The module is essentially the Control Center's Mount Bridge tile, native. |

## 5. Boundary: what stays in the INDI driver vs. what moves into the module

The **`indi_pifinder_mount_bridge` driver stays** and keeps owning the coupling *mechanism*:

- snooping `EQUATORIAL_EOD_COORD` on both devices, computing drift;
- the coupling state machine (`BRIDGE_MODE`, `CORRECTION_ACTION`, thresholds, freshness gates);
- issuing `EQUATORIAL_EOD_COORD` + `ON_COORD_SET` to the mount;
- Multi-Point Alignment, Reposition-Detection, Shadow Sync, horizon safety.

Rationale: the driver must keep working **headless** — a SkySafari-only or Stellarium-only user
with no KStars still needs coupling. Moving the logic into a KStars module would break that.

The **module owns the presentation and the Ekos-aware policy**:

- a readable status view (solve source, IMU, GPS, drift, coupling mode, "following" side);
- the coupling-mode picker and one-shot actions (thin wrappers over the driver's INDI properties);
- the setup flow (start the Web Manager profile, add the PiFinder drivers, pick the mount, connect)
  — the part [mount_bridge_web_integration.md](mount_bridge_web_integration.md) already designed
  as framework-agnostic logic;
- **guiding / Scheduler suspension**: the module watches Ekos state and, when guiding is
  calibrating/active/dithering or a Scheduler job is running, tells the driver to hold
  (a new INDI switch on the Bridge, e.g. `EXTERNAL_HOLD`, set by the module — the driver already
  has the concept of pausing its own mechanisms).

So: **driver = mechanism + headless survival; module = Ekos-native UI + Ekos-aware gating.**

## 6. What the module surfaces (first cut)

1. **Status** — solve status (real / synthetic / none), IMU dead-reckoning state, GPS lock,
   drift arcmin, coupling mode, which side is "followed".
2. **Coupling** — the four modes (Off / Verify-Alert / Auto-correct / Goto-Forward), threshold,
   correction action.
3. **One-shot actions** — Sync mount from PiFinder, Goto/Align Held Target, Stop.
4. **Multi-Point Alignment** — start/stop, point count / radius / min altitude / direction, progress.
5. **Setup** — profile start, driver add/remove, mount selection, connect (or defer to the
   existing INDI Control Panel for the advanced path).
6. **Guiding awareness indicator** — "Mount Bridge held: guiding active" so a quiet Bridge has a
   visible reason (matching PFSM's own "no silently-disabled control" principle).

## 7. Guiding / Scheduler / Optical Train — the wrinkle this removes

From inside Ekos the module has, with no bridging:

- **`OpticalTrainManager`** — which device is the guider, focuser, etc.
- **Guide module** — `Ekos::GuideState` (`GUIDE_CALIBRATING`, `GUIDE_GUIDING`, `GUIDE_DITHERING`,
  `GUIDE_ABORTED`/`GUIDE_REACQUIRE`, …) via signals, not polling. `GUIDE_DITHERING` being a named
  state means Reposition-Detection never has to guess whether a small move was a dither.
- **Scheduler module** — job state, for a coarse "a capture job is running, leave the mount alone"
  gate.
- **Align / Mount / Capture** — for meridian-flip and slew awareness.

The module translates that into the single `EXTERNAL_HOLD`-style signal to the driver (§5).

## 8. Anatomy of an Ekos module

Each module under `kstars/kstars/ekos/<module>/` is roughly:

- a **`QWidget`** — the tab UI (Qt Designer `.ui` + a controller class), added as a tab by
  `Ekos::Manager`;
- a **D-Bus interface** `org.kde.kstars.Ekos.PiFinder` (adaptor generated from an XML
  description), so scripts and the Scheduler can query/drive it — same pattern as `Ekos.Guide`,
  `Ekos.Mount`;
- a **state enum** (like `GuideState` / `CaptureState`) other modules and the Scheduler react to;
- **device access** via the `ISD::` wrappers in `kstars/kstars/indi/` (`ISD::Mount`,
  `ISD::GenericDevice` for the Bridge), wired up when a profile connects;
- **Optical Train** registration via `OpticalTrainManager` if train-scoped;
- **settings** via KConfigXT (`.kcfg` / `Options.kcfgc`).

> *Exact current file paths and class names are not pinned here — KStars refactors its module
> layout regularly. The shape above (compiled-in tab widget + D-Bus adaptor + `ISD::` wrappers +
> Manager wiring) is stable; confirm specifics against the tree at implementation time.*

## 9. Development environment

- Clone [invent.kde.org/education/kstars](https://invent.kde.org/education/kstars).
- Build deps: Qt6, KDE Frameworks 6, Eigen3, GSL, cfitsio, wcslib, **libindi (dev)**,
  StellarSolver, LibRaw, … CMake build; first build ~20–40 min. KDE's `kde-builder` is the usual
  base; distro `kstars-git` packages give a working dependency set.
- Test bench: the **PFSM UTM x86 VM** already is one — KStars + `indiserver` on :7624 + the
  PiFinder LX200 / Mount Bridge / PiFinder Simulator drivers + the Telescope Simulator. Develop
  the module against exactly that.
- Docs: [develop.kde.org](https://develop.kde.org); KStars' own `README` and the KStars
  matrix/mailing list.

## 10. KDE contribution process & licensing

- KStars is **GPL-2.0-or-later**.
- KDE uses **no CLA** — contributors agree to the KDE licensing policy; copyright stays with the
  author, licensed under the project's terms.
- Contribution is a **merge request on invent.kde.org**, reviewed by the KStars maintainers.

## 11. Effort & what's already portable

Non-trivial C++/Qt work, but the hard parts exist and are proven:

- **Coupling modes, drift math, Reposition-Detection, Multi-Point Alignment** — already in
  `indi_pifinder_bridge/` (C++), staying there. The module only wraps their INDI properties.
- **Setup orchestration** (profile start, driver add/remove, mount pick, connect) — already
  designed as framework-agnostic logic in
  [mount_bridge_web_integration.md](mount_bridge_web_integration.md); re-implemented once in
  C++/Qt for Ekos.
- **UI** — the Control Center's Mount Bridge tile is a working reference design for layout and
  wording.

A minimal first module (status view + coupling picker + one-shots, driving the existing driver)
is small. Guiding-hold, Multi-Point UI, and setup flow grow from there. Realistically weeks for
someone new to the KStars codebase; less with a KStars regular pairing on the Manager/`ISD` wiring.

## 12. Open questions for the Jasem discussion

1. **Category vs. orchestrator** (§4) — confirm the orchestrator approach, or is there a reason
   KStars would want a real device abstraction here?
2. **Where does the module sit** — its own top-level Ekos tab, or a sub-panel of the Mount module?
3. **The `EXTERNAL_HOLD` signal** (§5/§7) — a new switch on the Mount Bridge driver is the
   PFSM-side change; is there an existing Ekos convention for "another module asks this one to
   pause" that should be used instead?
4. **Optical Train** — should PiFinder be a selectable slot in the Optical Train editor (like
   "Guide via")? That would make "this train's position source is PiFinder" a first-class fact.
5. **Coexistence with the web Control Center** — the CC stays for install/update/mode-switching
   and headless setups. Is a partial-overlap period (both can set coupling) acceptable, or should
   one become read-only when the other is active?
6. **Upstream vs. StellarMate-only** — merged into KStars proper, or a StellarMate downstream
   patch? (Upstream is the point of this concept.)

## 13. Non-goals / risks

- **Not** removing the Mount Bridge INDI driver (§5) — headless coupling must survive.
- **Not** removing the web Control Center — install/update, hardware checks, Fake/Real mode, and
  the `INDI-only` control-host path have no Ekos equivalent.
- Risk: KStars module APIs are internal and move; a module is a standing maintenance commitment
  against upstream churn, unlike the self-contained INDI driver. Mitigated by keeping the module
  thin (presentation + gating) and the logic in the driver.
- Risk: review/merge latency is outside PFSM's control. Mitigated by early scope agreement with
  the maintainer.
