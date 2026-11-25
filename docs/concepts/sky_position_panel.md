# Concept: Sky Position Panel (all-sky view of mount and PiFinder)

> **Status: step 1 (driver and `indi_client.py`) built, GUI tile not yet.** Tracked as
> [GitHub issue #598](https://github.com/apos/PiFinder_Stellarmate/issues/598); step 1 is
> [issue #600](https://github.com/apos/PiFinder_Stellarmate/issues/600).
> Mockup (private Artifact): <https://claude.ai/artifact/H8zHyccPCpR4zbXfwGSVXs>, version 3.
> Decisions below are the project owner's, 2026-11-25 (two rounds).

## 1. Why

With the Sync buttons (`Sync mount from PiFinder`, `Sync PiFinder from mount`) the user has to know
which of the two devices is wrong, but at that moment sees neither position. Found live on 2026-11-25: PiFinder
sat 14° below the horizon and 135° from the mount, and nothing on the page showed that. A small picture of the
whole sky with both positions answers "who is wrong" at a glance, before any text is read.

## 2. Decisions (owner, 2026-11-25)

1. **Small.** One more tile in the PiFinder glance row (`#pifinder-glance-row`, next to the OLED mirror and the
   keypad). No buttons, no readout column, no text block beside it.
2. **Text lives inside the graphic.** Short names, no exact values. Below the horizon the name carries the
   altitude: `PiFinder −14°`. Positions that agree **still show both names**.
3. **Control Center colour scheme**, not a new palette (section 3).
4. **Display only.** A click on the picture does nothing (decided).
5. **Design cases:** both agree; PiFinder below the horizon (today's case); far apart but both visible; held target
   plus a new Goto target; no mount (Dobsonian); location unknown. The mockup shows all of them at true size.
6. **Goto target and Held target are part of version 1** ("das brauchen wir"). The panel draws a list of markers, so
   further kinds can be added later without redesign.
7. **Recommendation arrow only where it can be known:** when exactly one of mount/PiFinder is below the horizon, an
   arrow on the connecting line points to the one that should be corrected (the direction to sync). When both are
   visible but far apart, only the user can know which is right: no arrow.
8. **(i) help link** in the tile label, like the other tiles, with the explanation text (mockup shows the text).
9. **The mount's state is part of its name:** `Mount tracking`, `Mount not tracking`, `Mount parked` (owner,
   2026-11-25: a mount that is not tracking drifts away from its target, which is exactly what was happening on the
   Pi5). A parked mount is drawn grey.
10. **Observer location is required** and comes from the StellarMate app and/or KStars (section 5). Without a mount
   (for example a Dobsonian) the panel shows PiFinder and the targets only.

## 3. What the picture shows

- **Projection:** azimuthal, zenith in the centre, horizon as the rim, dashed rings at 30° and 60° altitude,
  faint cross. **North up, East left** (looking up at the sky; same as the Stellarium view the owner uses).
  Letters N E S W outside the rim, N emphasised.
- **Markers:** mount = blue dot (`#7ec8ff`). PiFinder = light diamond (`#ddd`) with its field of view as a small
  square drawn to the same scale (13.7° for the 16 mm lens, from `/api/solution` `FOV` when a solve exists, otherwise
  the configured lens value). Whether the mount lies inside that square tells the user if PiFinder's Align can work.
  **Goto** (the last Goto target the user sent, to the mount or to PiFinder) = white ring. **Held** (the target the Mount Bridge holds the mount on,
  `ORIGINAL_TARGET`) = blue cross. When Held, Mount and PiFinder coincide the names move to free spots (greedy
  placement, first free of: toward the middle, other side, above, below).
- **Names:** `Mount <state>`, `PiFinder`, `Goto`, `Held`, bold, with a dark halo so they stay readable over rings. Placed toward the
  disc's middle so they stay inside. When the markers are closer than about 30 px the names go to opposite sides
  (`Mount` left, `PiFinder` right).
- **Line** between the two, dashed, in the status colours the page already uses: green (`#4caf50`) = agree
  (within about 7°, i.e. inside PiFinder's field), yellow (`#f5a623`) = far apart, red (`#e53935`) = one of them is
  below the horizon.
- **Below the horizon:** the marker is hollow, sits just outside the rim in the direction of its azimuth, red
  outline, and the name carries the altitude (`PiFinder −14°`, soft red `#ff8a80`). Same rule for the mount.
  The arrow (decision 7) sits at 60 % of the line, red, pointing to the below-horizon device.
- **Size:** about 230 px square on the desktop layout, the same height class as the OLED tile; one column on a
  phone. Text 11.5 px.
- **Night mode:** the page's `body.night-mode` filter already recolours everything; no separate palette. To be
  checked on the device.

## 4. States the panel must handle (no guessing, no invented positions)

| State | Drawn |
|---|---|
| Mount and PiFinder positions known | both markers, line |
| No mount configured/connected (Dobsonian), or PiFinder Client role | PiFinder, Goto and Held (if any); no mount marker, no line |
| PiFinder has no position | mount only |
| Position stale (driver marks `IPS_BUSY`, "last known, not confirmed") | marker drawn faint (50 % opacity), name unchanged |
| **Observer location unknown** | no picture, one line inside the tile: `Location unknown` |
| Mount Bridge not running / not connected | tile greyed, `no data` |

The location case matters: the driver's `isAboveHorizon()` deliberately **fails open** without a location
(returns altitude 90, "above"). Used as-is, both markers would be drawn at the zenith, which is a wrong picture.
The panel must therefore get an explicit validity flag and never plot an altitude of 90 that came from the
fail-open path.

## 5. Data

What existed before step 1: `MOUNT_HORIZON_STATUS.ALTITUDE_DEG` and `PIFINDER_HORIZON_STATUS.ALTITUDE_DEG` (INDI
numbers in `indi_pifinder_bridge/pifinder_mount_bridge.cpp`, libnova from RA/Dec, observer location and system time),
exposed by `indi_client.mount_bridge_status()` as `mount_altitude_deg` / `pifinder_altitude_deg`; they drive the yellow
horizon cards. **Azimuth did not exist anywhere in the GUI path.**

**Step 1 (built, issue #600), all in the driver, next to the altitude it already computed:**

- `AZIMUTH_DEG` (0 to 360, **from north, east 90**) added to both horizon properties. libnova counts azimuth from the
  south, westwards; the driver shifts by 180°. Checked against PiFinder's own `Az` for the same RA/Dec and time:
  327.946° (driver math) vs 327.944° (PiFinder `/api/solution`). Altitude differed by 0.18° (PiFinder −14.446°,
  libnova −14.622°), which does not matter for a picture.
- New `GOTO_TARGET_HORIZON_STATUS` (the last Goto target: the `TARGET_EOD_COORD` of the mount **or** of the PiFinder device,
  whichever was updated last, because KStars slews the mount directly while push-to and Goto Forward go to PiFinder - found
  live 2026-11-25, issue #603; RA 0 / Dec 0 counts as "none") and
  `HELD_TARGET_HORIZON_STATUS` (`ORIGINAL_TARGET`, J2000 converted to JNow). Same `ALTITUDE_DEG`/`AZIMUTH_DEG` elements,
  `Ok` above, `Alert` below, `Idle` none.
- New `OBSERVER_LOCATION` (`LAT`, `LONG`; `Idle` = unknown). **Location source, in this order:** INDI
  `GEOGRAPHIC_COORD` of the PiFinder device, then of the mount (this is what KStars and the StellarMate app write to
  every device they drive, and it exists even without a mount); then PiFinder's own GPS lock (`/api/status`). An
  all-zero INDI location is INDI's "never set" default and counts as unknown. Resolved at most once per 3 s (it used
  to be one or two HTTP requests on **every** horizon check).
- `isAboveHorizon()` still fails open without a location (altitude 90, "above"), so the safety behaviour is unchanged;
  the panel never uses that placeholder because `OBSERVER_LOCATION` is `Idle` then.
- **Mount state** needs no driver change: it comes from the mount device's own standard properties `TELESCOPE_PARK`
  (PARK on = parked) and `TELESCOPE_TRACK_STATE` (TRACK_ON / TRACK_OFF), which the Control Center already reads for
  the "mount is parked" card (`read_mount_state`). It goes into `sky.mount_state` (`parked` | `tracking` |
  `not tracking` | `None`). Parked wins over the tracking state.
- `indi_client.mount_bridge_status()` returns a new key `sky` = `{location_known, lat, lon, mount, pifinder, goto,
  held}`; each position is `{alt, az, below, stale}` or `None`. **Without a known location every position is `None`.**
  Older drivers lack the new properties; the panel then has no data and shows nothing.

Why in the driver and not in Python: one implementation of "where is this in the sky" (location, time, libnova)
shared by the horizon safety check and the picture, so the picture can never disagree with the check that refuses a
sync.

**Refresh:** the existing 2 s Mount Bridge status poll. No new endpoint, no new polling of PiFinder.

**Markers as a list** (decision 6): the draw function takes `[{id, kind, alt, az, name, state}]`. Version 1 builds up
to four entries (Mount, PiFinder, Goto, Held); a further kind is one more entry, no change to the drawing code.

## 6. Implementation plan

1. **Driver** (`indi_pifinder_bridge`): azimuth, Goto/Held positions, observer location (sources above), one
   location lookup per 3 s. **Built (#600) and verified live on the Pi5 in Full Simulation (2026-11-25):** the new properties exist with the
   intended states (Goto/Held `Idle` while unset), `OBSERVER_LOCATION` equals the INDI location KStars/the app set,
   PiFinder azimuth 337.65° vs PiFinder's own `Az` 337.71°, mount altitude/azimuth 53.33°/118.95° vs an independent
   libnova calculation 53.34°/118.96°. Not yet checked: Goto/Held markers while a target is set, and a real-hardware run.
2. **`indi_client.py`:** `sky` key. **Built (#600)**, tested with canned property dumps (known/unknown location, older
   driver, missing element).
3. **GUI** (`status_page.html`): a pure function `skyPoint(alt, az, R)` plus `drawSkyPanel(markers)` building the
   SVG; tile with (i) added to `#pifinder-glance-row`; fed from the existing `/api/mount_bridge_status` poll
   (`refreshMountBridgeStatus`), `sky` key. The projection function is testable on its own with `node`.
4. **Tests:** projection (N up, E left; az 90 lands left of centre; alt below 0 lands outside the rim); name placement
   (no overlap for the three coincident-markers case); the state table in section 4 (location unknown must never
   draw); arrow only when exactly one device is below the horizon.
5. **Docs:** Control Center readmes (EN/DE), `help.html` entry "Sky" (the (i) target), CHANGELOG, screenshot.

Slicing: driver + `indi_client` first (invisible, testable through `indi_getprop`), then the tile. Each as its own
PR into `dev`.

## 7. Risks

- **Clock and location:** altitude/azimuth are only as good as the Pi's clock and the location PiFinder reports.
  With a wrong clock the picture is wrong in exactly the way the horizon check is. The tile does not hide this; the
  existing horizon cards stay the authority for refusals.
- **Azimuth convention** (libnova south-based) is the classic place for a mirrored or rotated picture; covered by
  the unit tests in step 4 and a check against PiFinder's own `Az` from `/api/solution` on the device.
- **Fail-open altitude 90** (section 4): the reason for `OBSERVER_LOCATION` and for `sky` being empty without it.
- **Location source change in a safety path:** the horizon check now also uses the INDI location (KStars/app) before
  PiFinder's GPS. If the two differ by a lot the check follows the app's location; the log line `Observer location: ...
  from ...` records which one is in use.
- **Driver ABI:** only new elements on existing properties; the GUI tolerates their absence (an old driver after a
  partial update shows the tile as `no data`).

## 8. Open questions

1. Placement on a narrow screen: below the OLED (suggested) or hidden.
2. Resolved 2026-11-25: the KStars / StellarMate app location is the truth for PFSM (so designed); the order in
   section 5 stays (app/KStars first, PiFinder GPS only as fallback).
