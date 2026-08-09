# Concept: Simulation fidelity gaps, and PiFinder's own orientation settings

> **Status: written up for the record (2026-08-09), not yet decided/implemented.** Captures a live
> discussion during Goto-Forward/sync-before-goto testing - the user's own considerations plus mine,
> deliberately kept as "considerations to act on later" rather than immediately coded. Written via
> this project's `cpt` convention (`basic-memory/basic-memory/00020_bm-cpt-command-system.md`); the
> entire `docs/concepts/` folder was read first per that convention.

## 1. Context

While testing the Goto-Forward edge-triggered fix (#194) and the new sync-before-first-goto behavior
against Telescope Simulator + Injected Solve, several deeper gaps surfaced that go beyond either fix
itself - the actual trigger was: "The mount does not slew" turned out to require a fresh solve that
Injected Solve, sitting static on a desk with no real motion, could never provide. That's one symptom
of a larger question: **what does "realistic" even mean for Mount Bridge simulation testing**, and
does today's simulation setup account for everything a real PiFinder installation depends on.

Related existing concepts, all read before writing this:
[`pifinder_fake_solve_simulation.md`](pifinder_fake_solve_simulation.md) (the Injected Solve mechanism
itself - single injection + real IMU dead-reckoning),
[`complete_position_simulator.md`](complete_position_simulator.md) (two simulation levels; "Mount is
source" as the mount→PiFinder reverse channel, already built as #130),
[`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md) (a different,
adjacent idea - PiFinder building its own mount model),
[`mount_bridge_reposition_detection.md`](mount_bridge_reposition_detection.md) (Fall 1-4 reposition
detection, whose SETTLING/freshness-wait logic is exactly what this session's test couldn't exercise
meaningfully),
[`mount_bridge_multistar_alignment.md`](mount_bridge_multistar_alignment.md) (already flags horizon/
altitude-limit awareness as an open question, structurally the same class of "the simulator needs to
know real-world constraints" gap as this document).

## 2. Two fundamentally different testing regimes (User)

Explicit framing that should govern every future testing decision here, not just tonight's:

**Simulation mode**: solve success and IMU predictability *should* be non-issues by construction -
there's no real camera to fail, no real stars to miss, no real gyro noise. If Injected Solve reports
"stale" after sitting genuinely settled for a while, that's arguably the simulation not doing its job,
not something a test script should route around externally (e.g. periodic `curl` calls to
`/api/fake_solve_enable_from_mount`).

**Real mode**: freshness checks exist because real solves genuinely can fail or go stale (clouds, FOV
obstruction, etc.) - *and* there's a second, distinct risk freshness alone never catches: a solve
that's fresh but **systematically wrong** due to a configuration/calibration mismatch, not a timing
one (see §5).

These two regimes should be reasoned about and tested separately, not conflated under one "does the
freshness gate work" umbrella.

## 3. ad1 - Solve rate/reliability as a real, unmeasured hardware property (User)

The user does not know whether Injected Solve currently keeps re-anchoring/refreshing continuously
while genuinely settled (open question, not yet verified against `~/PiFinder`'s actual
`integrator.py`/dead-reckoning settle-detection code).

Broader point, independent of that specific question: **PiFinder's real-world solve rate is itself an
unmeasured, hardware-and-conditions-dependent property** that any fidelity-conscious simulator would
need to model, not assume:

- Developers reportedly cite 1-3 solves/second as a rough figure, but no known tool surfaces this live
  from a running PiFinder (may exist in PiFinder's own code, not confirmed).
- Suspected (not confirmed) correlation: solve rate degrades under high CPU load and/or thermal
  throttling - directly relevant given this project's own prior findings (#139, wontfix'd: PiFinder's
  solver worker pool genuinely oversubscribes CPU on a Pi4 running KStars simultaneously).
- Suspected correlation to optics: the user runs an f/1.4 lens vs. stock PiFinder's f/2.0 - a faster
  lens gathers more light per exposure, plausibly improving solve success rate/speed. A simulator
  claiming to model solve reliability realistically would need this as a parameter, ideally backed by
  real measurements on real hardware under varied conditions (load, temperature, optics) rather than a
  single assumed constant.

**Consideration, not a decision**: building an actual solve-rate measurement tool (instrumenting
PiFinder's own solver loop, or reading it back from existing logs/telemetry if it already exists)
would be a prerequisite for any simulator that wants to claim realistic solve-timing fidelity - purely
speculative modeling without real numbers would just encode guesses as if they were facts.

## 4. ad2 - Should freshness-gated logic treat sim vs. real mode differently? (my considerations)

Framing the tradeoffs, not deciding:

**Option A - leave the gate mode-agnostic (current state).** `isPiFinderSolveFresh()` (and now the
new sync-before-first-goto logic) has no concept of "am I talking to a simulated or real PiFinder" -
it just checks `solve_source == "CAM"` and age. Pro: one code path, no special-casing, no risk of the
simulated path silently diverging from real behavior (directly the same principle
`pifinder_fake_solve_simulation.md` §5 already commits to: "reuse the real pipeline, don't build a
parallel one"). Con: exactly the friction hit tonight - a static Injected Solve can never satisfy this
gate for long, making sim-mode testing of settle/holding logic require manual intervention.

**Option B - fix it at the simulation layer, not the gate.** If Injected Solve's own settle-detection
already keeps re-anchoring while genuinely stationary (open question, §3), the "problem" may not exist
at all once actually verified - worth checking before building anything. If it does *not* currently
re-anchor while stationary, that could arguably be a real gap in Injected Solve itself (in `~/PiFinder`,
not this repo) worth fixing there, so *every* consumer downstream (not just Mount Bridge) sees
consistently fresh simulated solves without each one needing its own workaround.

**Option C - a test-only automatic mount→solve feedback loop**, e.g. a small always-on companion to
`/api/fake_solve_enable_from_mount` that keeps calling it on a timer while a Goto-Forward test session
is active. Pro: closes the loop without touching either the driver's real logic or PiFinder's own
simulation code. Con: yet another moving piece to maintain, and doesn't help anyone testing without
this repo's specific tooling.

**Consequence common to all three**: whichever is chosen, the driver's own freshness-gated logic
(sync-before-goto, Auto-correct's freshness check, SETTLING's arrival-confirmation wait) should
**not** be made aware of "am I in a simulation" - that would violate the same principle
`pifinder_fake_solve_simulation.md` is built on, and would mean real-mode behavior is no longer what's
actually being tested when running against a simulator. The fix, whichever it is, belongs on the
simulation side of the boundary, not the driver side.

**No recommendation made here** - needs the §3 open question answered first (does Injected Solve
already re-anchor while settled?) before choosing between B and C.

## 5. ad3 - Regression risk from tonight's two merged fixes, without a live real-mode re-test

Explicit user decision: real mode was extensively tested the previous night and is considered solid -
**do not re-run a full live real-sky verification tonight**. The concern instead: did merging
PR #199 (event-triggered Goto-Forward target detection) or PR #200 (PiFinder v2.6.1 pin) introduce a
regression that only a real-mode session would surface?

**Code-review-based assessment (not a substitute for eventual real-mode confirmation, but reasoned
without one):**

- **PR #199 (event-triggered target detection)**: the property-update mechanism it relies on
  (`INDI::Telescope::ISNewNumber()` republishing `TARGET_EOD_COORD` on every Goto request, regardless
  of whether the value changed) lives in libindi's base class, identical regardless of whether the
  backend is a real PiFinder or a simulated one - `lx200_pifinder.cpp`'s `Goto()` itself doesn't
  branch on this at all. No specific reason to expect this to behave differently for a real PiFinder
  than it did in tonight's simulator test. Lower risk.
- **The new, not-yet-merged sync-before-first-goto commit** (this session, on
  `fix/goto-forward-sync-before-first-goto`) is a genuinely new real-mode-relevant behavior that has
  **never been exercised in any mode yet** - it only fires when `isPiFinderSolveFresh()` is true at
  the exact moment Goto-Forward is switched on, which tonight's static-Injected-Solve setup never
  satisfied. This is the actual new risk surface for real mode, not PR #199's already-merged change.
  Needs its own real-mode verification before being trusted, separate from tonight's other testing.
- **PR #200 (v2.6.1 pin)**: bigger surface area in principle (updates PiFinder's own solving/camera
  pipeline code, not just Mount Bridge), but the two patches that needed fixing
  (`state.py`/`camera_interface.py`) were both small, additive, and specifically about the
  `debug_solve`/`fake_solve_active` state-tracking fields this project itself added - not upstream's
  actual solving/camera logic, which this project doesn't patch at all. Verified `/api/status` returns
  correct values live. No specific mechanism identified by which this would change real-mode solving
  behavior, but this is inference, not a live real-sky proof.

**Recommendation**: no urgent live real-mode re-test needed for PR #199 specifically. The
sync-before-first-goto commit (not yet merged) does need real-mode (or at least real-fresh-solve)
verification before being trusted - it simply hasn't been exercised at all yet. PR #200 carries the
most inherent uncertainty of the three but no concrete failure mechanism was found; treat as
lower-priority to verify, not zero-priority.

## 6. ad4 - Mount Type and PiFinder Type both feed the IMU dead-reckoning math (User)

Two distinct PiFinder settings, both affecting how IMU-measured device rotation gets translated into
sky-relative pointing direction - **any simulator attempting to model dead-reckoning realistically
must account for both**, not just one.

### (A) Mount Type (`Settings -> Mount Type`: Alt/Az / Equatorial)

**Already integrated, live-verified** (`basic-memory/pifinder-stellarmate/00017_mount-type-auto-sync`,
2026-07-17): Mount Bridge already auto-syncs this from the INDI mount's own `TELESCOPE_MOUNT_TYPE`
property (read by index per `inditelescope.h`'s fixed `MOUNT_ALTAZ=0/MOUNT_EQ_FORK=1/MOUNT_EQ_GEM=2`
enum, mapped to PiFinder's own two-valued setting) via a live-reload API call
(`POST /api/set_mount_type`, no PiFinder restart needed) - runs every `TimerHit()` tick, independent
of Coupling mode, only resends on actual change.

Tonight's screenshots confirm this is currently working correctly (Telescope Simulator's `GEM` ↔
PiFinder's own `Equatorial`, matching). Distinct and important: **manually** changing this setting via
PiFinder's own on-device Settings menu (not through Mount Bridge's auto-sync) triggers a full PiFinder
service restart (seen live tonight, "Restarting..." screen) - a much heavier operation than the
Bridge's own live-reload path. User's explicit point: **before manually touching this setting on the
device, first confirm via the existing auto-sync whether it already matches** - no need to manually
force a disruptive restart for a setting the Bridge already keeps in sync automatically.

### (B) PiFinder Type (`Settings -> Advanced -> PiFinder Type`: Left / Right / Straight / Flat v3 /
Flat v2 / AS Bloom)

**Not currently synced by anything - and structurally can't be, the way Mount Type is.** Mount Type
has an INDI-side source of truth (the mount driver's own `TELESCOPE_MOUNT_TYPE`) to read and auto-sync
from. PiFinder Type describes a purely physical fact - how the PiFinder unit itself is bolted onto the
OTA relative to the optical axis - that has no INDI-side equivalent to read from at all. Nothing on
the mount/Mount-Bridge side can ever know this automatically; it's a manual calibration fact the user
must set correctly themselves, matching their actual physical rig.

**Reference convention** (User, from
[the PiFinder build guide](https://pifinder.readthedocs.io/en/release/build_guide.html#configurations-overview)),
using the OLED's upper edge (viewed from above) as the reference:

| Type | OLED upper edge points... | Camera points... |
|---|---|---|
| Straight / Flat (v2/v3 are hardware-revision derivatives of this) | same direction as the optical axis | same direction as the optical axis |
| Right (Newtonian, focuser on the right) | "up" (PiFinder mounted above the focuser) | "right", matching the focuser's position |
| Left (Newtonian, focuser on the left) | "up" | "left", matching the focuser's position |

**Consequence for any dead-reckoning simulator**: both (A) and (B) jointly determine the rotation
transform between "what the IMU measured" and "where the sky actually is" - a simulator (or any
"replay a plausible slew as synthetic solves" tool, per `complete_position_simulator.md` §2's "full
simulation" mode) that ignores either setting would compute physically wrong orientations for any rig
configuration other than whatever one combination it happened to assume. This is the concrete
mechanism behind the "IMU can give false assumptions... PiFinder mounted contradictorily to modes"
risk flagged earlier for **real** mode too - a real installation with a PiFinder-Type/actual-mounting
mismatch would produce systematically-wrong-but-internally-consistent (i.e. still "fresh") solves,
which no freshness check could ever catch, only a physical/configuration audit could.

## 7. Open questions (not decided)

- Does Injected Solve's settle-detection already re-anchor continuously while genuinely stationary, or
  only once per motion→settle transition? (§3/§4 - blocks choosing between Option B and C)
- Does a real, measured solve-rate figure exist anywhere in PiFinder's own code/logs already, or would
  measuring it be new work? (§3)
- Should PiFinder Type ever be user-configurable *from* the Control Center (mirroring the existing
  device-role/profile UI patterns), or does it stay purely an on-device PiFinder setting this project
  never touches? (§6B - not raised by the user, noted here only as a natural follow-on question)
- Is there a place worth recording "confirmed real-mode-safe" vs. "not yet real-mode-tested" per
  Mount-Bridge behavior, given tonight's finding that simulator-only testing and real-mode testing can
  diverge in non-obvious ways (§5)?

## 8. Effort & Priority

Not sized - this document exists to capture considerations for a future decision, not to propose a
specific piece of work yet. The one concrete, small, unblocked action already known:
**real-mode-verify the sync-before-first-goto commit** before trusting it (§5) - independent of every
other open question here.
