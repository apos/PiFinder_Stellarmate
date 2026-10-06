# Concept: PiFinder's own mount model, for tracking through cloud cover

## 1. Context

Separate from [`complete_position_simulator.md`](complete_position_simulator.md)'s testing/simulation
work, though it shares the same underlying theme (PiFinder maintaining a position belief independent
of a literal fresh camera solve).

Real-world problem (User): PiFinder currently has no fallback once it stops getting fresh solves
(passing cloud, moving indoors, camera obstruction, ...) beyond IMU dead-reckoning, which accumulates
error over time and has no independent check on it. A real equatorial mount, once properly
polar-aligned and synced, can in principle keep pointing accurately for much longer than PiFinder's
own dead-reckoning alone - its own internal mount model (accounting for polar misalignment, cone
error, etc., depending on the mount) is a second, independent source of positional truth that
PiFinder currently never uses.

## 2. The idea

PiFinder builds an internal "mount model" of its own, so it can keep tracking through solve gaps
(clouds, obstruction, ...) more robustly than IMU dead-reckoning alone - complementary to, not a
replacement for, the existing dead-reckoning mechanism.

## 3. Why this is tricky - the IMU interaction

Flagged by the user as the hard part: this only cleanly works in two states -
**at rest** (no motion, nothing to reconcile against a moving IMU estimate) and **at solve** (a fresh
camera solve just landed, unambiguous ground truth). Anything in between - active hand-slewing, or a
GoTo in progress - means the IMU is already the authoritative live-motion source, and introducing a
second, independent-but-not-necessarily-synchronized position source (a mount model) into that same
window risks the two disagreeing about where PiFinder currently is, with no principled way to decide
which one is right mid-motion.

## 4. Proposed precondition: LX200 "Align" command

For a mount model to be useful, the mount needs to learn PiFinder's verified position at the right
moments - the same way a human aligns a mount by centering a known star and syncing. Proposed
mechanism: LX200 gains the ability to send a fresh PiFinder solve to the mount as an **Align**
command (distinct from a plain Sync - conceptually "here is a verified position, incorporate it into
your alignment model," not just "reset your current pointing to this"). This is a precondition for
the mount-model idea, not the idea itself - without it, the mount has no way to receive
PiFinder-verified positions to build its own model from in the first place.

## 5. Who actually holds the model?

Two non-exclusive directions:

- **The INDI driver / an actual mount that already has its own mount model** supplies or assists with
  this data - many real mounts (encoders, multi-star alignment, PEC, ...) already maintain a more
  sophisticated position model than PiFinder ever could from IMU alone. PiFinder leaning on that,
  once it's been fed verified Align data, could be more accurate than building an independent model
  from scratch.
- **The mount fundamentally serves as "the mount model" itself**, via the existing "Mount is source"
  Coupling preset (#130) - but only under specific conditions: no solve has occurred recently *and*
  the mount is actively driving (tracking/slewing on its own model, not just sitting idle), with the
  IMU necessarily disabled during that window (per §3 - avoiding the two-source conflict) and manual
  slewing of PiFinder itself disallowed while in this state (nothing to reconcile a hand-slew against
  if the IMU is off).

This second direction directly reuses "Mount is source" - but for a materially different purpose than
[`complete_position_simulator.md`](complete_position_simulator.md) built it for (testing). Whether
that's the same code path wearing two hats, or two conceptually distinct behaviors that happen to
share a mechanism, is an open design question - see §7.

## 6. GUI integration implications (rough)

- A real mount model in use is a distinct operating state from either "normal" (camera+IMU) or a
  Coupling preset - the existing hardware-status ampel row (Cam/Solve/IMU/GPS) would need a way to
  show "tracking via mount model, no recent solve" without it reading as an error state, similar to
  how Injected Solve already gets its own badge distinct from a real solve failure (#128).
  Auto-correct/Verify-Alert's own relationship to this state also needs thinking through - correcting
  the mount from a position that itself came from the mount would be circular.
- If IMU must be disabled while the mount model is authoritative (§3), the GUI needs to make that
  visible and explain why - an unexplained "IMU: off" would read as a hardware fault otherwise.
- Manual slew lockout (§5) needs a clear, visible reason in the GUI when active, not just a silently
  unresponsive control.

## 7. Open questions

- Is "Mount is source" (§5's second direction) the right mechanism to reuse for this, or does the
  real-world mount-model use case need its own, differently-gated mode despite the surface
  similarity? Not yet decided.
- How does PiFinder detect the "at rest" vs. "in motion" boundary reliably enough to gate the model
  switch described in §3 - existing settle-detection (see `complete_position_simulator.md` §5) may or
  may not be sufficient as-is.
- Effort estimate: LX200 Align command (§4) is a small, well-scoped addition (~1-2 days) on top of
  the existing Sync mechanism. The mount-model logic itself (§2/§3/§5) is materially bigger and
  harder to size without first resolving §7's mechanism question - rough order of magnitude, weeks
  not days, given the IMU-interaction complexity flagged in §3.
- Not yet prioritized against other open work - concept-only at this stage, no implementation
  decision made.
