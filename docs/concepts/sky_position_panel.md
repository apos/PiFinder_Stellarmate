# Concept: Sky Position Panel (all-sky view of mount and PiFinder)

> **Status: concept, nothing built.** Tracked as
> [GitHub issue #598](https://github.com/apos/PiFinder_Stellarmate/issues/598).
> Mockup (private Artifact): <https://claude.ai/artifact/H8zHyccPCpR4zbXfwGSVXs>, version 2.
> Decisions below are the project owner's, 2026-11-25.

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
4. **Display only.** A click on the picture does nothing. (Open to revisit, see section 8.)
5. **Three situations are the design cases:** both agree; PiFinder below the horizon (today's case); far apart but
   both visible. The mockup shows all three at true size.
6. **Room for more later** (goto target, held target, ...) without redesign: the panel draws a list of markers;
   version 1 fills it with two (section 5).

## 3. What the picture shows

- **Projection:** azimuthal, zenith in the centre, horizon as the rim, dashed rings at 30° and 60° altitude,
  faint cross. **North up, East left** (looking up at the sky; same as the Stellarium view the owner uses).
  Letters N E S W outside the rim, N emphasised.
- **Markers:** mount = blue dot (`#7ec8ff`). PiFinder = light diamond (`#ddd`) with its field of view as a small
  square drawn to the same scale (13.7° for the 16 mm lens, from `/api/solution` `FOV` when a solve exists, otherwise
  the configured lens value). Whether the mount lies inside that square tells the user if PiFinder's Align can work.
- **Names:** `Mount` and `PiFinder`, bold, with a dark halo so they stay readable over rings. Placed toward the
  disc's middle so they stay inside. When the markers are closer than about 30 px the names go to opposite sides
  (`Mount` left, `PiFinder` right).
- **Line** between the two, dashed, in the status colours the page already uses: green (`#4caf50`) = agree
  (within about 7°, i.e. inside PiFinder's field), yellow (`#f5a623`) = far apart, red (`#e53935`) = one of them is
  below the horizon.
- **Below the horizon:** the marker is hollow, sits just outside the rim in the direction of its azimuth, red
  outline, and the name carries the altitude (`PiFinder −14°`, soft red `#ff8a80`). Same rule for the mount.
- **Size:** about 230 px square on the desktop layout, the same height class as the OLED tile; one column on a
  phone. Text 11.5 px.
- **Night mode:** the page's `body.night-mode` filter already recolours everything; no separate palette. To be
  checked on the device.

## 4. States the panel must handle (no guessing, no invented positions)

| State | Drawn |
|---|---|
| Mount and PiFinder positions known | both markers, line |
| No mount configured/connected, or PiFinder Client role | PiFinder only, name `PiFinder`, no line |
| PiFinder has no position | mount only |
| Position stale (driver marks `IPS_BUSY`, "last known, not confirmed") | marker drawn faint (50 % opacity), name unchanged |
| **Observer location unknown** | no picture, one line inside the tile: `Location unknown` |
| Mount Bridge not running / not connected | tile greyed, `no data` |

The location case matters: the driver's `isAboveHorizon()` deliberately **fails open** without a location
(returns altitude 90, "above"). Used as-is, both markers would be drawn at the zenith, which is a wrong picture.
The panel must therefore get an explicit validity flag and never plot an altitude of 90 that came from the
fail-open path.

## 5. Data

What exists today: `MOUNT_HORIZON_STATUS.ALTITUDE_DEG` and `PIFINDER_HORIZON_STATUS.ALTITUDE_DEG` (INDI numbers,
`indi_pifinder_bridge/pifinder_mount_bridge.cpp`, computed with libnova from RA/Dec, the observer location fetched
from PiFinder `/api/status` and the system time). They are exposed by `indi_client.mount_bridge_status()` as
`mount_altitude_deg` / `pifinder_altitude_deg` and already drive the yellow horizon cards. **Azimuth does not exist
anywhere in the GUI path yet.**

**Recommended: add azimuth in the driver**, next to the altitude it already computes:

- `isAboveHorizon()` gets a second out-parameter (azimuth) and a validity result. `ln_get_hrz_from_equ()` already
  returns it; **libnova measures azimuth from the south, westwards**, so the driver converts to the usual
  north-based degrees (`az_north = fmod(az_ln + 180, 360)`) before publishing.
- Both horizon properties get a second number element `AZIMUTH_DEG` (0 to 360) and a `LOCATION_VALID` flag (or a
  separate property), so the GUI reads one coherent set. Existing readers use the element name `ALTITUDE_DEG`
  (`indi_client.py`), so adding elements does not break them.
- `indi_client.mount_bridge_status()` passes `mount_azimuth_deg`, `pifinder_azimuth_deg`, `location_known` through
  unchanged in shape (new keys only).
- One cheap side effect to fix while there: `isAboveHorizon()` fetches the location over HTTP on every call, and it
  is called twice per tick. Fetch it once per tick (or cache for a few seconds).

Why in the driver and not in Python: one implementation of "where is this in the sky" (location, time,
libnova) shared by the horizon safety check and the picture, so the picture can never disagree with the check that
refuses a sync. A second implementation in the Control Center would need its own location and clock handling.

**Refresh:** the existing 2 s Mount Bridge status poll. No new endpoint, no new polling of PiFinder.

**Markers as a list** (future-proofing, decision 6): the draw function takes
`[{id, kind, alt, az, name, state}]`. Version 1 builds two entries. A goto or held target would be a third entry,
no change to the drawing code. **Not decided and not part of version 1:** whether goto/held target appear, and in
what style (suggestion if wanted: small ring, white outline, name `Target`).

## 6. Implementation plan

1. **Driver** (`indi_pifinder_bridge`): azimuth + location flag + single location fetch per tick. Rebuild is part of
   the normal update (`build_and_install_indi_drivers`). Verify on the Pi5 with `indi_getprop`
   (unfiltered dump, see CHANGELOG notes on filtered reads) in Full Simulation and with the real mount.
2. **`indi_client.py`:** read the new elements, expose the new keys. Unit-test with a canned property dump.
3. **GUI** (`status_page.html`): a pure function `skyPoint(alt, az, R)` plus `drawSkyPanel(markers)` building the
   SVG; tile added to `#pifinder-glance-row`; fed from the existing `/api/mount_bridge_status` poll
   (`refreshMountBridgeStatus`). The projection function is testable on its own with `node`.
4. **Tests:** projection (N up, E left; az 90 lands left of centre; alt below 0 lands outside the rim); marker
   spacing rule for the names; the state table in section 4 (location unknown must never draw).
5. **Docs:** Control Center readmes (EN/DE), `help.html` short entry "Sky", CHANGELOG, screenshot.

Slicing: driver + `indi_client` first (invisible, testable through `indi_getprop`), then the tile. Each as its own
PR into `dev`.

## 7. Risks

- **Clock and location:** altitude/azimuth are only as good as the Pi's clock and the location PiFinder reports.
  With a wrong clock the picture is wrong in exactly the way the horizon check is. The tile does not hide this; the
  existing horizon cards stay the authority for refusals.
- **Azimuth convention** (libnova south-based) is the classic place for a mirrored or rotated picture; covered by
  the unit tests in step 4 and a check against PiFinder's own `Az` from `/api/solution` on the device.
- **Fail-open altitude 90** (section 4): the reason for the explicit validity flag.
- **Driver ABI:** only new elements on existing properties; the GUI tolerates their absence (an old driver after a
  partial update shows the tile as `no data`).

## 8. Open questions for the owner

1. Goto target and held target as a third marker, later? Suggested style in section 5.
2. Display only (current decision), or later a click that opens the full Alt/Az readout in a popover?
3. Placement on a narrow screen: below the OLED (suggested) or hidden.
