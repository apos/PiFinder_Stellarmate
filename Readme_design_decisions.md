# Design Decisions — PiFinder LX200 INDI Integration

*[Deutsche Version](Readme_design_decisions_de.md)*

A condensed summary of the key design decisions behind the [PiFinder LX200 INDI
integration](Readme_PiFinder_LX200.md) (the `PiFinder LX200` driver and the optional `PiFinder
Mount Bridge`). See that document for the full rationale, code references, and diagrams.

## Architecture

- **Standalone build instead of a fat-binary/`indi-source` checkout**: the drivers link directly
  against the system `libindi` — 13.5 MB → 80 KB, builds in seconds instead of a full INDI rebuild,
  no conflict with `pacman`.
- **Two separate drivers instead of one**: `PiFinder LX200` (identical role in every scenario,
  whether or not a mount exists) and `PiFinder Mount Bridge` (the only building block that even
  knows a second, real mount exists) — independently buildable and enabled, no impact on each
  other.

## PiFinder LX200 Driver

- **Deliberately minimal capability** (`GOTO` + `ABORT`, no `SYNC`, no Park/Flip/tracking-rate):
  PiFinder has no motor and no internal position model to synchronize — any Sync concept belongs
  to the mount, not to PiFinder.
- **GoTo means push-to forwarding**: `Goto()` only writes `:Sr#`/`:Sd#` to PiFinder's own server;
  it never changes PiFinder's own reported position, which comes independently from the live solve.

## Mount Bridge

- **Only generic INDI properties sent to the mount** (`EQUATORIAL_EOD_COORD`/`ON_COORD_SET`), never
  a mount-specific protocol — makes the Bridge automatically compatible with any INDI mount, not
  just OnStepX.
- **Embedded INDI client** (`INDI::BaseClient`, following `indi_skysafari`) instead of a snoop
  mechanism inside the driver's own process — cleaner separated state.
- **One coupling dial instead of separate toggles** (Off / Verify-Alert / Auto-Correct /
  Goto-Forward): covers the whole spectrum from pure push-to to fully automatic GoTo with a single
  property.
- **Goto-Forward reuses the `TARGET_EOD_COORD` property `INDI::Telescope` already provides**
  instead of adding a custom one — avoids duplication (discovered only after a name collision bug).
- **After a Goto-Forward slew: verify via Sync, not another Goto** — the mount has already arrived;
  a remaining error is a calibration issue, not a missed slew (otherwise it would "hunt").
- **Settle delay (3 poll cycles) before verifying** — PiFinder needs time after the physical move
  to produce a fresh solve.

## Testing & Operations

- **Staged testing strategy**: fake LX200 server → `indi_simulator_telescope` → real EQ5/OnStepX —
  risk increased step by step, never tested on real hardware untested.
- **Documentation bilingual, English as the primary language** (the project page is in English),
  German as a secondary version with a language switcher.
