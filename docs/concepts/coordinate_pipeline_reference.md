# Reference: the PiFinder ↔ Mount coordinate pipeline (epoch, unit, frame)

> **Status: reference.** This is not a feature design - it is the authoritative
> map of *what representation a coordinate is in at every hop* between PiFinder
> and the mount, for both the real-hardware and the full-simulation scenario.
> Written 2026-09-01 after a run of bugs (#160, #232, and the Goto-Forward
> "never pinpoint" symptom) that were each really the *same class* of bug -
> a coordinate handed across a hop in the wrong representation - but kept
> looking like new, unrelated problems because this table did not exist.

## Why this document

Every coordinate crossing the PiFinder↔mount boundary carries **three
independent representation choices**, and a defect in any one of them looks
like "drift":

| Axis | Values | Notes |
|---|---|---|
| **Epoch** | `J2000` / `JNow` (epoch-of-date, "EOD", "apparent") | J2000↔JNow differ by precession: ~13′ in RA, ~2′ in Dec for a mid-sky object in 2026, and **growing every year**. |
| **Unit** | RA in **hours** (0-24) / RA in **degrees** (0-360) | Dec is always degrees. A factor-of-15 error = a gross, obvious runaway. |
| **Frame** | equatorial RA/Dec / IMU "screen" quaternion frame | Only relevant on the IMU dead-reckoning path (§4). |

The rule that keeps this sane: **PiFinder is J2000 everywhere internally.**
Anything that talks to a *mount* is JNow (INDI's `EQUATORIAL_EOD_COORD` /
`TARGET_EOD_COORD` are epoch-of-date by definition). Every hop between the two
worlds must precess, exactly once, in the right direction.

## Canonical conversions

- **JNow → J2000**: remove precession/nutation/aberration. `INDI::ObservedToJ2000`
  (libindi, no extra dependency) or libnova `ln_get_equ_prec` (reverse).
- **J2000 → JNow**: apply them. `INDI::J2000toObserved` / `ln_get_equ_prec`.
- Julian Date from a unix timestamp: `jd = unixtime / 86400.0 + 2440587.5`.

## The pipeline - full simulation scenario

```
[Telescope Simulator]            EQUATORIAL_EOD_COORD / TARGET_EOD_COORD
   epoch JNow, unit hours                 |
                                          | INDI snoop (IUSnoopNumber)
                                          v
[PiFinder Simulator]  ISSnoopDevice(): copies mount RA/Dec verbatim while
   epoch JNow, unit hours       following a forwarded GoTo (target changed)
   (pure passthrough - no conversion, correct: JNow in, JNow out)
                                          |
                                          | indi_getprop EQUATORIAL_EOD_COORD
                                          v
[test_tools/pifinder_truth_injector.py]   reads JNow hours, ra_deg = ra_h*15
   POSTs {"ra": deg, "dec": deg} to  ---> /api/fake_solve
   NO epoch conversion (sends JNow)
                                          |
                                          v
[PiFinder /api/fake_solve handler]  converts the received JNow -> J2000
   (fixed in #160, commit 3326f05 "injected JNow mount coords as J2000")
   stores PiFinder's `solution` in J2000
                                          |
                                          v
[PiFinder /api/status]  solution.RA/Dec: epoch J2000, RA in DEGREES
                                          |
                                          | HTTP GET
                                          v
[Mount Bridge httpGetPiFinderFreshCamPosition()]
   /15.0  -> RA hours                (unit fix, documented in-function)
   J2000 -> JNow via INDI::J2000toObserved   <-- ADDED 2026-09-01 (#232)
   returns epoch JNow, unit hours
                                          |
                                          v
[Mount Bridge drift / sync logic]  angularSeparationArcmin(piRADE, mountRADE)
   both sides now JNow hours  ->  drift ~ 0 when actually pinpoint
```

### The two epoch hops that must both be present

1. **truth injector's JNow → `/api/fake_solve` → J2000** (inside PiFinder, since #160).
2. **`httpGetPiFinderFreshCamPosition()` J2000 → JNow** (inside Mount Bridge, since #232 / this doc's date).

Hop 2 was missing after PR #243 unified every Mount Bridge position read onto
the HTTP source. The old `getPiFinderRADE()` path had read the already-JNow
"PiFinder LX200" INDI mirror, so no one had had to precess; the HTTP source is
raw J2000 and nobody added the step. Result: a fixed ~13′ RA phantom drift that
Mount Bridge chased forever (#232). Symptom looked like "the mount never lands
pinpoint after a GoTo".

## The pipeline - real hardware scenario

```
[real mount driver]  EQUATORIAL_EOD_COORD          epoch JNow, hours
[PiFinder camera]  plate solve -> solution         epoch J2000, degrees
[pos_server.py]  LX200 :GR#/:GD# export
   comment says "Convert from J2000 to now epoch" via
   position_of_radec(...).radec(epoch=ts.from_datetime(dt))   -> JNow
[PiFinder LX200 driver]  publishes EQUATORIAL_EOD_COORD        epoch JNow
[Mount Bridge httpGetPiFinderFreshCamPosition()]  reads /api/status J2000
   -> J2000toObserved -> JNow   (same single hop as the sim scenario)
```

Open question carried from #232: whether `pos_server.py`'s own J2000→JNow
export is correct, or double-applies, or uses a wrong clock. The August #232
data (raw 30.6′ vs "converted" 45.5′ off the mount - conversion made it *worse*)
was taken through the `pos_server.py` + old `getPiFinderRADE()` path, not the
HTTP path this doc fixes. To be re-measured on real hardware. The HTTP path
(`/api/status` → `J2000toObserved`) does **not** go through `pos_server.py` and
is now epoch-correct on its own.

## The IMU dead-reckoning path (frame, not just epoch)

`test_tools/pifinder_imu_injector.py` feeds `/api/fake_imu` a quaternion so
PiFinder's `ImuDeadReckoning.predict()` reports a chosen RA/Dec between
fake-solve injections. This path additionally involves the **IMU "screen"
frame**: `q_imu2cam(screen_direction)` (must match the unit's real
`PIFINDER_ORIENTATION.SCREEN_DIRECTION`) and `radec2q_eq()`. It is a test tool
for slew *smoothness* only - the steady-state position after a GoTo comes from
the fake-solve path above, not this one. Its own residual accuracy is a
separate concern from the epoch pipeline (see `full_simulation_imu_dead_reckoning.md`).

## Checklist before touching any coordinate hop

1. Which scenario(s) does this code run in - sim, real, or both?
2. What epoch is the value on the way in? On the way out? Is there exactly one
   precession between the PiFinder (J2000) world and the mount (JNow) world?
3. RA in hours or degrees on each side?
4. Verify against the **driver logs** (`~/.var/app/org.kde.kstars/data/kstars/logs/`,
   `~/PiFinder_data/pifinder.log`), not ad-hoc `indi_getprop` reconstruction -
   see `basic-memory/basic-memory/00090` rule 3.
5. After the change: re-check the *whole* table end to end, not just the one
   symptom that prompted it.

## Related

- #160 (closed) - `/api/fake_solve` injected JNow as J2000
- #232 - the ~17′ phantom residual this doc's epoch hop 2 addresses
- #177 - PiFinder Simulator dead-reckoning-follow (the "PiFinder Simulator
  stayed frozen during a forwarded GoTo" half of the pinpoint symptom)
- PR #243 - unified Mount Bridge position reads onto the HTTP source
- `full_simulation_imu_dead_reckoning.md`, `complete_position_simulator.md`
