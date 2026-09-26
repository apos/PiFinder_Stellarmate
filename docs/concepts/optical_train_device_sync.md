# Concept: Keep Ekos Optical Trains in sync with the active mount device

> **Status: implemented** (`gui_installer/indi_client.py`, `server.py`, `status_page.html`).

## 1. Problem

Ekos "Optical Trains" (Mount/Camera/Guider/Focuser/Filter Wheel/Rotator/Dust Cap/Light Box, one set
per imaging configuration) are KStars' own concept, entirely independent of which INDI drivers are
currently loaded. Switching which mount device is actually in use - Full Simulation's "Telescope
Simulator" vs. a real mount driver (e.g. "LX200 OnStep") - does **not** touch any optical train's
device references at all. Live-caught (2026-09-26, real-sky session, transitioning from Full
Simulation to real hardware): after adding the real "LX200 OnStep" driver to the profile, **two**
separate optical trains ("APO80 PlayerOne GeminiFoc" and "LacertaZWO120mmGuide") were both still
pointing their `Mount` field at "Telescope Simulator" - and the guide train's `Guide via` field was
*also* set to "Telescope Simulator" (pulse-guiding through the mount, not a dedicated guide camera).

Two related failure modes this needs to cover, not just one:
1. **Automatic**: the Control Center's own "Full Simulation" toggle (`pifinder_truth_injector.py`
   start/stop) switches the driver set without touching optical trains at all.
2. **Manual**: a user directly adds/removes/links a mount driver via KStars/the StellarMate app (as
   in the 2026-09-26 session) - the Control Center never runs at that moment, so nothing here can
   fire automatically; a deliberate, user-triggered action must be available.

## 2. Ekos Optical Trains are not INDI - they live behind KStars' own DBus interface

Confirmed live: `qdbus6 org.kde.kstars /KStars/Ekos/OpticalTrain/<id>` exposes each train as its own
DBus object (`org.kde.kstars.Ekos.OpticalTrain`), with one `QString` property per device role
(`mount`, `camera`, `guider`, `focuser`, `filterWheel`, `rotator`, `dustCap`, `lightBox`) plus `name`/
`id`, and a `setXxx(QString)` method per property. KStars exposes no "list all trains" call; every
currently-registered train's id is discoverable from the same top-level object list `qdbus6
org.kde.kstars` already prints (`/KStars/Ekos/OpticalTrain/<id>` entries) - no separate enumeration
API needed.

This is genuinely a different system from indiserver/INDI properties (everything else this project
talks to) - no device connection, no `indi_getprop`, just KStars' own process-local DBus interface.
Requires `qdbus6` and a live KStars process; fails closed (raises, or returns nothing changed) if
either is missing, same as every other best-effort external dependency in this codebase.

## 3. Core primitive: swap by value, not by assumed field meaning

`swap_optical_train_devices(from_device, to_device)` (`indi_client.py`) walks every discovered train
and every one of the 8 device-role properties, and replaces the value with `to_device` **only where
the current value is exactly `from_device`** - never assuming which field "should" hold a mount.
Direct feedback confirmed this matters in practice: `guider` can validly hold either a real,
independent guide camera (leave alone) *or* the mount's own device name (pulse-guiding via the mount
- must be swapped, exactly like `mount` itself). A same-named value in ANY of the 8 fields means "this
field currently refers to that device," full stop - the property's nominal role doesn't change that.

Returns `{train_name: [changed_property, ...]}` - only trains that actually had something changed,
so a caller can report exactly what happened rather than a generic "done".

## 4. Two trigger points, one shared mechanism

### 4.1 Automatic - tied to the Full Simulation toggle

`_truth_injector_start()`/`_truth_injector_stop()` (server.py) are the only two places the Control
Center itself ever flips between "the mount is Telescope Simulator" and "the mount is whatever it
was before" as a deliberate, first-party action (Full Simulation on/off). Hooked in both directions:

- **Start** (entering Full Simulation): before starting the injector, call
  `swap_optical_train_devices(<current per-field values>, "Telescope Simulator")` - but since the
  "what to swap from" isn't a single known constant (a train could have any real mount configured),
  this direction instead **snapshots first**: for every train/field whose value is not already
  "Telescope Simulator", record `{train_id: {field: old_value}}` into `_optical_train_swap_memory`
  (persisted the same way `_mb_desired_*` fields already are, see `MOUNT_BRIDGE_DESIRED_STATE_FILE`),
  *then* sets that field to "Telescope Simulator". Only entries that actually changed are recorded -
  a field already on "Telescope Simulator" is left alone and not remembered (nothing to restore).
  A field with nothing selected reads back as the literal two-character string `"--"` (KStars' own
  placeholder), not empty/None - found live during testing (an unset field was otherwise treated as
  "has a device worth remembering," swapping and later restoring a field that was never really in
  use). Excluded via `indi_client.OPTICAL_TRAIN_NONE_SENTINEL` alongside the "already Telescope
  Simulator" check.
- **Stop** (leaving Full Simulation): for every remembered `(train_id, field, old_value)`, restore
  `old_value` **only if the field's current value is still exactly "Telescope Simulator"** - if the
  user changed it to something else while Full Simulation was active, that was a deliberate choice
  and must not be silently overwritten. Clear `_optical_train_swap_memory` after a successful
  restore pass (partial failures leave their own entries in place for the next attempt, same
  best-effort spirit as the rest of this mechanism).

A train created *after* the snapshot (mid-Full-Simulation) has no remembered entry and is correctly
left untouched on stop - it never had a "before" state to return to.

### 4.2 Manual - a dedicated Control Center action

New route `/api/optical_train_sync` (server.py) + button in the Mount setup checklist
(status_page.html, next to "Link telescope mount") - lets the user explicitly swap
`from_device`/`to_device` (defaulting `from_device` to "Telescope Simulator" and `to_device` to
whichever mount the "Mount (INDI WM Profile)" section shows as just-linked, editable). Reports back
exactly which trains/fields changed. This is what covers the 2026-09-26 session's actual need - a
manual real-hardware transition the automatic path in §4.1 never sees, since no Full Simulation
toggle was involved.

Both paths call the same `swap_optical_train_devices()` primitive; the manual path does not touch
`_optical_train_swap_memory` at all (it's an explicit, one-shot user action, not part of the
Full-Simulation on/off pair that needs a "restore later" memory).

## 5. Edge cases considered

- **KStars not running / qdbus6 missing**: `_qdbus()` raises `INDIClientError`; both trigger paths
  treat this as best-effort (log and continue) - never blocks the Full Simulation toggle or the
  manual action's other effects.
- **A field manually changed while Full Simulation is active**: not restored on stop (see §4.1) -
  the live current value always wins over a remembered snapshot for the *restore* direction.
- **Multiple trains, only some affected**: handled naturally - the primitive checks every train/field
  independently; the snapshot only ever records entries that actually changed.
- **Toggling Full Simulation on/off multiple times in a row**: the second "on" snapshot only records
  fields not already "Telescope Simulator" - a field left on "Telescope Simulator" from a previous
  cycle's not-yet-restored state is not re-recorded (there is nothing new to remember; it already
  reflects Full Simulation's own value).

## 6. Related

`indi_client.py`'s `sync_pifinder_simulator_to()`/`sync_mount_to_pifinder_visible_position()`
(same file, same "keep the simulator/mount mirrors honest" spirit, different layer - INDI properties,
not Ekos optical trains). basic-memory pifinder-stellarmate, 2026-09-26 real-sky session notes.
