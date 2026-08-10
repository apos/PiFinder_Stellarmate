# Concept: Automatic Multi-Point Alignment via Mount Bridge

> **Status: concept — not yet implemented.** Written via this project's `cpt` (concept)
> convention — see `basic-memory/basic-memory/00020_bm-cpt-command-system.md` and
> `00021_bm-documentation-depth-standard.md` for the standard this document follows. Tracked as
> [GitHub issue #191](https://github.com/apos/PiFinder_Stellarmate/issues/191) on
> [Project #15](https://github.com/users/apos/projects/15) — update that issue if this concept is
> promoted, revised, or dropped.
>
> **Builds on two existing concepts, read both first:**
> - [`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md) §4 already
>   proposes an **Align** LX200 command ("here is a verified position, incorporate it into your
>   alignment model" — distinct from a plain Sync's "reset your current pointing to this"). This
>   concept is the first concrete, motivating use case for actually building that primitive — see
>   §8.
> - [`mount_bridge_reposition_detection.md`](mount_bridge_reposition_detection.md) §3.5/§4 already
>   established the freshness-gating and settle-detection discipline ("never adopt a position
>   confirmed only by IMU-interpolated data") this concept reuses point-by-point, and its own §8
>   already flagged the overlap with the cloud-tracking document — this concept is the third
>   document in that same overlapping cluster, not a fresh, unrelated idea.

## 1. Overview

A button that performs an automated multi-point alignment: instead of the user manually centering
several known stars in an eyepiece/reticle and confirming each one at the mount's hand controller
(classic 2-/3-star align), PiFinder's own plate-solving determines where the mount is *actually*
pointing at several sky positions in sequence, and each verified position is sent directly to the
mount over INDI — the same generic, mount-agnostic `EQUATORIAL_EOD_COORD`/`ON_COORD_SET` path Mount
Bridge already uses everywhere else (`pifinder_bridge_client.cpp`'s `sendMountCoords()`).

Motivation: a single Sync (today's only "teach the mount a true position" mechanism) only refines
the mount's model at one point in the sky. Real GoTo accuracy across the whole sky depends on the
mount's alignment model having several verified reference points spread across different
sky regions — normally built by a human doing exactly that, star by star, by hand. Nothing here is
architecturally new; it automates a workflow astronomers already do manually, using PiFinder's
plate-solving instead of human eyeballing/centering as the "is this the true position" judge.

## 2. Use Cases

| # | User action | System behavior |
|---|---|---|
| UC1 | Click "Multi-Point Alignment", accept defaults (radius, point count, etc.) | Runs the full sequence from PiFinder's current pointing, Sync-ing the mount at each verified point |
| UC2 | Configure radius (30°/60°/100° presets), point count (1–10), median-solve count, minimum altitude, before starting | Candidate points are drawn only from within the configured radius of PiFinder's *current* view, above the configured minimum altitude |
| UC3 | Enable "also feed KStars/Ekos alignment model" | Each verified point is additionally handed to Ekos's own alignment subsystem, not just the mount's firmware (see §4.5 — open question, not just a checkbox) |
| UC4 | Click Stop Movement mid-sequence | Sequence aborts immediately (reuses the existing `abortMount()` panic-button path, #179) — mount stops where it is, no further points attempted, no automatic resume |
| UC5 | A candidate point fails to solve (cloud, too dim, camera obstruction) | Point is skipped (not retried indefinitely — see §4.3), sequence continues with the next candidate; a point skipped past the configured count is not silently replaced by an extra one — user sees fewer completed points than requested rather than the sequence running longer than expected |

## 3. Configuration Parameters (User, 2026-08-09)

| Parameter | Type | Notes |
|---|---|---|
| Search radius | degrees, preset choices (30° / 60° / 100°, free entry also allowed) | Centered on PiFinder's *current* solved/reported position at the moment the button is clicked — not a fixed catalog position, not the mount's own reported position (those two can disagree, see §4.2) |
| Number of points | integer, 1–10 | How many verified alignment points to collect before finishing |
| Solves per point (median) | integer | Each point's final RA/Dec is the **median** of this many independent camera solves at that position, not a single solve — reduces sensitivity to one noisy/wrong solve. Needs its own settle-then-sample loop, see §4.3 |
| Minimum altitude | degrees above horizon | Candidate points below this are excluded from selection entirely (not attempted-then-skipped) |
| Candidate source | "KStars catalog" or "PiFinder Bright Stars catalog" | See §4.2 — which catalog actually supplies candidate coordinates within the radius/altitude constraints |
| Feed KStars/Ekos alignment model too | boolean, off by default | See §4.5 — open question on how this interacts with the mount's own model, not yet resolved enough to default it on |

## 4. Architecture

### 4.1 Context

```mermaid
flowchart LR
    subgraph Candidate source
        KSC[KStars star catalog]
        PFC["PiFinder \"Bright Stars\" catalog"]
    end
    UI[Control Center: Multi-Point Alignment button] -- radius/count/altitude/median params --> SEQ[Alignment sequencer]
    KSC -.one of the two.-> SEQ
    PFC -.one of the two.-> SEQ
    SEQ -- blind GoTo per point --> MB[Mount Bridge]
    MB -- EQUATORIAL_EOD_COORD + ON_COORD_SET=SLEW --> LX[Mount's INDI driver]
    PF[PiFinder camera] -- N solves per point, median taken --> SEQ
    SEQ -- verified position --> MB
    MB -- ON_COORD_SET=SYNC/ALIGN --> LX
    SEQ -. optional (UC3, open question) .-> EKA[Ekos alignment module]
```

### 4.2 Candidate point selection

Two concrete sourcing options were named (User), not a bespoke new star list:

- **KStars's own star catalog** — Ekos/KStars already has a full sky catalog with magnitude data;
  querying "bright stars within radius R of point X, above altitude A" is exactly the kind of query
  KStars's own scripting/DBus interface is built for. Advantage: already includes proper
  magnitude-based filtering and is the same catalog the user already sees on the sky map.
- **PiFinder's own "Bright Stars" catalog** — PiFinder already ships a bright-star catalog for its
  own UI (needs verification: which file/table exactly, under `astro_data/` or the catalogs DB —
  not yet confirmed which one is meant here). Advantage: no KStars/Ekos dependency at all, works
  even in a PiFinder-only ("PiFinder host") role setup with no mount-side KStars session — see the
  existing Role concept (All-in-one / PiFinder host / Control host, `Readme_PiFinder_LX200.md`).

The center of the search radius is **PiFinder's current solved position**, not the mount's current
reported position — the two can disagree (that disagreement is exactly what an ordinary Mount
Bridge Coupling mode corrects, and is *also* likely why the user wants to realign in the first
place). Using PiFinder's own view keeps the alignment run anchored to what the user is actually
looking at through the finder right now, not wherever the mount's (possibly wrong) internal model
currently believes it's pointing.

### 4.3 Per-point sequence flow

```mermaid
flowchart TD
    Start[Start sequence] --> Candidates[Select up to N candidate points\nwithin radius, above min altitude,\nfrom the chosen catalog]
    Candidates --> NextPoint{Points remaining\nand not aborted?}
    NextPoint -- no --> Done[Sequence complete - report N verified / M attempted]
    NextPoint -- yes --> Goto[Blind GoTo to candidate point\n- mount's current, possibly imperfect model]
    Goto --> Settled{Mount finished slewing?\nisMountSlewing==false}
    Settled -- no --> Settled
    Settled -- yes --> SolveLoop[Collect solves until median-count\nreached or a bounded attempt limit expires]
    SolveLoop --> Enough{Median-count solves\nsuccessfully collected?}
    Enough -- no, limit expired --> Skip[Skip this point - log why,\ndoes not count toward N]
    Skip --> NextPoint
    Enough -- yes --> Median[Compute median RA/Dec\nacross the collected solves]
    Median --> Sync["Sync (or Align, see §4.5)\nmount to the median position"]
    Sync --> KStarsFeed{Feed KStars model too?\n(UC3, opt-in)}
    KStarsFeed -- yes --> EkosAdd[Hand the same verified point\nto Ekos's alignment module]
    KStarsFeed -- no --> NextPoint
    EkosAdd --> NextPoint
    Start -.Stop Movement.-> Abort[Abort - mount stops where it is,\nno further points, no auto-resume]
```

The settle-then-median-sample step directly reuses the same discipline `handleGotoForward()`
already applies for a single point (wait for `isMountSlewing()==false`, then wait for a **fresh**
PiFinder solve — `isPiFinderSolveFresh()`, `solve_source=="CAM"` — before trusting it, exactly the
#79 freshness-gate pattern used everywhere else in Mount Bridge). What's new here, not present
anywhere else in this project yet, is collecting **several** solves per point and taking their
**median** rather than trusting the first fresh one — a genuinely new aggregation step, not a
reuse of existing code.

### 4.4 Skip vs. retry vs. abort

- **A single failed solve attempt** at a point: retry (bounded — needs its own attempt cap, e.g. a
  handful of tries with a short pause between, mirroring `MAX_FRESHNESS_WAIT_TICKS`'s existing
  bounded-wait pattern elsewhere in this file) before giving up on that specific solve sample.
- **A point that never accumulates enough solves** for its median within a reasonable bound (cloud
  cover sitting right on that patch of sky, camera obstruction, ...): skipped entirely (UC5) — the
  sequence moves on to the next candidate rather than stalling the whole run on one bad point.
- **User-triggered abort** (UC4): the existing `abortMount()`/Stop Movement path already covers
  this cleanly — immediately stops any in-flight motion and (per its existing behavior) also sets
  Coupling to Off, so nothing else tries to act on the half-finished sequence's state afterward. No
  new abort mechanism needed, matching the user's own direct confirmation.

### 4.5 Open question: Sync vs. the proposed "Align" primitive, and the KStars-model interaction

Two things flagged as genuinely unresolved, not just left as vague future work:

- **Sync today only ever resets the mount's *current pointing* to a given coordinate** — whether
  repeated Syncs at different points actually accumulate into a real multi-point alignment model,
  or whether each new Sync simply overwrites the last one's contribution, is **firmware-dependent**.
  Confirmed for the primary target mount: **OnStep does build a real multi-point model from
  repeated Syncs** (User, 2026-08-09) — so for OnStep specifically, the simple "just Sync N times"
  sequence in §4.3 is sufficient, no `ALIGNMENT_POINTSET_*`-style INDI Alignment Subsystem
  properties or a dedicated Align command are strictly required to make this concept work. For any
  *other* mount driver this feature might later target, that assumption needs re-verifying — not
  guaranteed to generalize. Building the "Align" primitive `pifinder_mount_model_cloud_tracking.md`
  §4 already proposes remains worth doing regardless (it's the semantically correct operation this
  concept is actually performing — "here is a verified position, learn it" — even where a plain
  Sync happens to produce the same practical effect on OnStep today), but is not a hard blocker for
  a first OnStep-only implementation.
- **Feeding Ekos's own alignment module in addition to the mount's firmware model** (UC3): raised
  by the user with an explicit caveat — "hoffentlich kommen die sich nicht ins Gehege" (hopefully
  they don't get in each other's way). Genuinely open: does KStars/Ekos apply its own alignment
  correction *on top of* the mount's already-corrected pointing (double-correcting), or does
  enabling a KStars alignment model change how Ekos itself interprets/forwards GoTo commands in a
  way that could conflict with Mount Bridge's own direct INDI Sync calls? Needs actual research
  into Ekos's alignment-module behavior (and likely a live test on real hardware, in the same style
  as tonight's Fall-2 live verification) before this defaults to anything other than off. Not
  resolved by this document — flagged here so it isn't quietly implemented without that research
  first.

## 5. ADR: Sync-only for a first OnStep-scoped implementation, revisit Align primitive if generalized

**Context**: §4.5 identified that whether repeated Syncs actually build a multi-point model is
firmware-dependent, and that `pifinder_mount_model_cloud_tracking.md` already separately proposes a
more semantically correct "Align" primitive for exactly this kind of "teach a verified position"
operation.

**Decision**: build the first version of this feature using plain `ON_COORD_SET=SYNC` (already
confirmed sufficient for OnStep, the primary/only currently-verified target), rather than blocking
this concept's implementation on first building a new INDI Align command. Explicitly revisit this
once/if the feature is generalized to other mount drivers, or once the cloud-tracking concept's own
Align primitive gets built for its own reasons — at that point, this feature should switch to using
it too rather than maintaining two separate "teach a verified position" code paths long-term.

**Consequences**:
- Positive: unblocks a working first implementation now, using infrastructure (Sync,
  freshness-gating, settle-detection, abort) that already exists and is already live-verified
  tonight (#178's Fall-2 work).
- Negative: if this feature is later used against a mount driver where repeated Sync does *not*
  build a real multi-point model, the alignment run would silently produce no better accuracy than
  a single-point Sync, despite appearing to complete N points successfully — worth a clear
  driver-compatibility caveat in the GUI/docs once implemented, not just in this concept document.

## 6. Installation / Test

**Update (2026-08-10): §4.2 is implemented, not just documented.** Branch
`feature/191-multipoint-alignment-poc` (not merged) - `MULTI_POINT_ALIGN` INDI switch (Start/Stop)
on Mount Bridge, `AlignConfigNP` (radius/count/min_altitude) exposing §3's relevant parameters,
candidates fetched fresh on every Start from PiFinder's own new `/api/nearby_bright_stars` endpoint
(companion patch, `diffs/api_extensions_py.diff` - its "Str" bright-named-star catalog, altitude-
filtered server-side using PiFinder's own GPS location/time via skyfield). The originally-reduced
PoC's fixed hardcoded 4-point set is gone. §4.3's median-of-N-solves and §4.5's KStars-model feed
remain out of scope. Live-verified end to end against `Telescope Simulator`: correctly fetched real
candidates and slewed to the first one (Alioth) rather than any hardcoded point.

**Horizon safety - now closed structurally, not just documented.** The original PoC's fixed points
had no altitude/horizon awareness at all - live-confirmed (User, 2026-08-10) starting a sequence
while the target sat below the horizon on PiFinder's own sky-map. §4.2's catalog-driven,
altitude-filtered selection (now implemented, see above) closes this: candidates below the
configured minimum altitude are never selected in the first place, not caught after the fact.
**Not yet addressed**: candidate altitude filtering rules out "below the horizon" but not
cable-wrap/meridian-flip risk for a given mount's current orientation - same class of gap as the
still-open KStars-horizon-fencing item, unrelated to this fix.

**No Control Center GUI yet (User decision, 2026-08-10) - INDI Control Panel only.** Deliberately
not built this session ("erstmal nicht - Branch bleibt technisch/INDI-only") - no Start/Stop button,
no progress display, no visible warning surface in the Control Center itself. Right now the only
places to observe this feature at all are the INDI Control Panel's own properties/log (fetch
failures go to `MULTI_POINT_ALIGN`'s `IPS_ALERT` + a `LOG_ERROR`; a skipped point logs a
`LOG_WARN`) - a normal Control Center user has no way to see or use this feature yet. Revisit once
§4.3/§4.5 (or at least a scoping decision to skip them) land, per the User's own stated preference
to build GUI "in einem Rutsch" rather than piecemeal.

**Waiting for a fresh solve at each point needs no special handling for real use** (User, 2026-08-10):
the mount arrives, PiFinder's own continuous camera solve loop naturally produces a fresh solve once
stationary, exactly as it always does — the sequence's per-point wait is correct as designed, not a
gap to work around. This only fails to self-resolve when testing against `Telescope Simulator` +
Injected Solve specifically (no real camera in that loop at all, so nothing ever re-solves on its
own) — a testing-environment limitation, not something the feature itself needs to accommodate.
Without a real solve, a point simply waits out `MAX_FRESHNESS_WAIT_TICKS` and gets skipped (§4.4's
existing behavior); test against real sky/hardware for meaningful end-to-end verification of this
PoC's actual alignment behavior.

Once the full feature (catalog selection, median-of-N, KStars feed) is built, it inherits Mount
Bridge's existing test surface (INDI Control Panel, `indi_getprop`/`indi_setprop`, the Control
Center GUI, live verification under real sky) rather than introducing a new one. Testing methodology
notes worth carrying forward from earlier live-testing experience
(`basic-memory/pifinder-stellarmate/00089` §7):
- Prefer real, continuous camera solving over synthetic `/api/fake_solve` injection when verifying
  the median-of-N-solves step — synthetic injections showed non-deterministic drift under repeated
  rapid calls, which would confound testing an aggregation step specifically designed to smooth out
  solve noise.
- `/api/fake_solve`'s RA is in degrees, not hours — convert before any INDI property use (a real
  ~23° mis-slew happened from exactly this mistake in an earlier session).

## 7. Effort / Priority

- **Size**: M–L. The core sequence (§4.3) reuses existing settle/freshness/abort building blocks
  almost entirely — the genuinely new pieces are candidate-point selection (§4.2, needs picking and
  wiring up one of the two catalog sources), the median-of-N-solves aggregation (§4.3, not present
  anywhere else in this codebase), and the new sequencing/progress UI. The KStars-model-feed
  option (§4.5) is a separate, larger, research-first piece that could reasonably ship later than
  the core feature.
- **Priority**: high (per the user, 2026-08-09) — backlog, not yet "Ready" (needs the §4.2 catalog
  decision and §4.5 research resolved, or at least a scoping decision to defer §4.5 to a follow-up,
  before implementation can start).

## 8. Relationship to the other two documents in this cluster

- **`pifinder_mount_model_cloud_tracking.md`**: this concept is the first concrete use case that
  would actually benefit from that document's proposed Align primitive (§4 there), even though
  §4.5/§5 above conclude a first OnStep-only implementation doesn't strictly need it yet. If that
  primitive gets built (for either concept's sake), this concept should switch to using it rather
  than keeping a separate plain-Sync path indefinitely (see the ADR, §5 above).
- **`mount_bridge_reposition_detection.md`**: this concept's per-point settle-then-solve step
  (§4.3) is the same "wait for genuine stop, then wait for a fresh solve before trusting a new
  position" discipline that document's UC2 already established for a single external reposition
  event — same underlying primitive, applied here repeatedly across a planned sequence of points
  instead of reactively to one unplanned external move. No new detection logic needed from that
  document; this concept only *initiates* the moves (via its own sequencer), it doesn't need to
  *detect* them as external, since Mount Bridge itself is the one commanding each GoTo.

## Related

- [GitHub issue #191](https://github.com/apos/PiFinder_Stellarmate/issues/191)
- [`pifinder_mount_model_cloud_tracking.md`](pifinder_mount_model_cloud_tracking.md)
- [`mount_bridge_reposition_detection.md`](mount_bridge_reposition_detection.md)
- `basic-memory/pifinder-stellarmate/00089_indi-debugging-werkzeugkasten-auf-diesem-pi4.md` §7
  (tonight's live-testing methodology notes, directly relevant to §6 above)
