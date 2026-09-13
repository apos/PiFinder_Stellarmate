# Concept: "PiFinder Client" role naming + INDI Setup section review

## 1. Context

Direct feedback (2026-09-13), after the Control host badges-mirroring work (docs/concepts/
control_host_hardware_badges_mirroring.md) and the connection-confirmation fix landed:

> Hinzu kommt der "SETTINGS" Bereich: das CC des "Pifinder Client" (das ist der neue Rollenname):
> hier muss a) ein neuer Modus her: "Pifinder Client" b) der gesamte "INDI Setup" Bereich
> inklusive vor allem des Mount nochmal geprüft werden.

Plus, on the Control host's own Mount Bridge diagram/badges: *"alle müssen an Hand des CH /
Client Pi Setups angepasst und getestet werden... Alle sollten transparent den Status anzeigen."*

This concept covers the naming/role question and inventories what the "INDI Setup" section
(Setup checklist & diagnostics, plus the Mode & Power mode tiles) already does vs. doesn't do
correctly for a device acting as a pure PiFinder client to someone else's Control host - written
up before touching code, since a role rename ripples through many call sites and is worth getting
right in one pass rather than several.

## 2. Today's role model (`deriveProfileRole()` in status_page.html)

```js
function deriveProfileRole() {
  const remote = !!wmLx200Remote;
  const local = wmHasLx200 === true && !remote;
  const bridge = wmHasBridge === true;
  if (local && bridge) return 'aio';              // merged into "PiFinder host" card (2026-09-12)
  if (local && !bridge) return 'host';             // merged into "PiFinder host" card (2026-09-12)
  if (remote && bridge) return 'ctrl';             // "Control host" card
  if (remote && !bridge) return 'ctrl-incomplete'; // "Control host" card, mount not linked yet
  if (bridge) return 'bridge-only';
  return 'none';
}
```

Purely derived from this device's own Web Manager profile - there is no "role" concept in the
backend at all, and no signal that tells a device "someone else's Mount Bridge is currently
pointed at you". A device configured as local PiFinder LX200 with no Mount Bridge (`role ===
'host'`) looks identical today whether it's genuinely standalone or is quietly being remotely
coupled by another device's Control host - **this device has no way to know the difference**,
because remote coupling happens entirely on the *other* device's own indiserver/Mount Bridge, over
the network, invisible to this one's own profile. This is the same gap issue #416 ("PiFinder-Slave
to Control host" mode) already flags, still unimplemented.

## 3. The naming question - decided: option (c), a manual third role card

"PiFinder Client" reads as a proposal to rename what's shown for `role === 'host'` (today's card
title: "PiFinder host", pill: "PiFinder host") - "host" suggests this device is in charge, which
is backwards in a split setup where a *different* device's Control host is actually doing the
mount coupling. Three ways to read the request were weighed:

- **(a) Pure rename, same trigger** - swap "PiFinder host" → "PiFinder Client" everywhere `role
  === 'host'` is shown, no new detection logic. Cheapest, but doesn't distinguish "genuinely
  standalone" from "actively remoted into" - and direct feedback (2026-09-13) confirmed this
  distinction matters: *"Under PiFinder Host the mount bridge is also possible (GoTo Mode), so for
  the user it is more clear to activate a certain 'one click' mode that makes the device ready for
  a certain use case."*
- **(b) A real third state**, only shown once this device can actually detect a remote coupling -
  issue #416's own scope, not yet designed, not a quick follow-up to this doc.
- **(c) A manual choice, not auto-detected** - add "PiFinder Client" as its own explicit role card
  alongside "PiFinder host" (kept for the GoTo Mode / local-mount case) and "Control host". **Picked**
  (2026-09-13): matches the quote above exactly - the card *is* the one-click mode selection, not a
  label chasing a detected fact.

### 3a. State model

"PiFinder Client" and "PiFinder host" both start from the *same* underlying profile shape (local
PiFinder LX200, no Mount Bridge yet - `deriveProfileRole()` returns `'host'` for both). The choice
between the two cards is therefore not derivable from the profile alone and needs its own stored
field - server-side, not `localStorage`, matching how every other "the user's own deliberate
choice must survive a restart/a different browser" fact on this page is already persisted
(`_mb_desired_mount`/`_mb_desired_coupling_mode`/etc. via `_save_mount_bridge_desired_state()`/
`MOUNT_BRIDGE_DESIRED_STATE_FILE`). New field: `pifinder_role_choice: "host" | "client" | null`
(`null` = no explicit choice yet, e.g. a fresh install - the role-card row shows neither card
active until one is clicked, same as today's pre-choice state). Read into a new `/state`/profile-
poll field the frontend already has a slot for (same JSON blob `wmSelectedProfile` etc. already
ride in), so no new endpoint is needed, just one more key.

### 3b. Mismatch handling - decided

Direct feedback (2026-09-13): *"the user should be warned and given the choice to abort / choose
PiFinder Host. We have the local yellow warning badges that should sit exactly at that place
(Settings)."* So: if `pifinder_role_choice === "client"` but a mount ever becomes actually coupled
(`wmActiveMount` truthy - via the existing "+ Couple a mount" flow, or a mount added directly in
Web Manager outside this UI entirely), show a `.showstopper-card` (the same amber, "No solve
source yet"-style card already used elsewhere on this page) right in the Settings section, with
two actions:
- **"Switch to 'PiFinder host'"** - only changes `pifinder_role_choice` to `"host"`; nothing about
  the actual INDI/mount configuration changes, since the two cards were never functionally
  different, only the stated intent was.
- **"Remove this mount coupling"** - calls the same unlink action "PiFinder host"'s own row
  already offers, restoring the "no mount" state that matches the declared "PiFinder Client" choice.

Mockup of both the three-card row and this warning card, using the page's own exact CSS
(`.mb-role-card`, `.showstopper-card`): https://claude.ai/code/artifact/b1673e9a-c933-48d7-b168-a6449ea77f52

No default forced automatically in either direction - matches this page's own established
principle (never guess/never silently reinterpret a deliberate user choice).

### 3c. Card wording - refined per direct feedback (2026-09-13)

The mockup's first draft overclaimed both directions - fixed in the mockup (linked above), final
wording:

- **"PiFinder host"** sub: *"Mount optional (GoTo Mode)."* - not *"couples a mount here too"*: *"PiFinder Host kann selbstverständlich auch ohne mount auskommen... die Einschränkung auf
  'couples a mount' kann leicht missinterpretiert werden"* - a mount was never mandatory for this
  card, the wording must not imply otherwise.
- **"PiFinder Client"** sub: *"No mount here - ready for a remote Control host."* - not *"Controlled
  remotely by a Control host"*: *"es kann auch sein, dass es keinen CH gibt und nur der PF in
  Betrieb ist. Das sollte man nicht so explizit sagen"* - describes the card's *readiness*/intent,
  not an asserted, currently-active relationship with a specific other device (which this device
  has no way to confirm anyway, per section 2's own point).

### 3d. Approved, with the section 6 follow-on gap now in scope

*"Das Konzept passt mit den o.g. Anpassungen... Und ja, Dein Nebenbefund muss berücksichtigt
werden."* - the concept (sections 2-4) is approved as designed, with 3c's wording, and the
Control-host-side gap flagged at the end of section 5 (a Control host can't yet tell a mirrored
device's "PiFinder Client" choice apart from "PiFinder host, no mount linked yet") is now explicitly
in scope for the implementation, not deferred. See section 5's own point 4 (added below) for what
that requires.

## 4. INDI Setup section - what's already role-aware, what isn't

`updateProfileRoleLine()` already hides/adapts a fair amount for `role === 'host'`
(`hostMode` in that function): `#mb-operate-rows`, `#mb-steps-4-6` (Mount/Ekos/Connect steps),
`#mb-setup-btn-row` (One-Click Setup), `#mb-status-row`, `#mb-diagram`, `#mb-mode-caption-row`,
`#mb-mode-details` all hidden; `#mb-add-mount-row` (the "+ Couple a mount" button) and
`#mb-thisdevice-ip-row` shown instead. This is a solid existing baseline, unaffected by the new
card: both "PiFinder host" and "PiFinder Client" still derive `role === 'host'` while no mount is
coupled, so `hostMode` stays exactly this - the new `pifinder_role_choice` field only changes which
card is highlighted and which text/mode-tile framing shows (below), not this visibility logic.

**Gap found reading `setModeTileVisible()`/the Mode & Power tiles**: the three mode tiles (Real
Hardware / **Full Simulation (INDI/Mount Bridge)** / PiFinder-only Fake Mode) are gated only on
whether an install/reinstall run is currently active - never on role. A `role === 'host'` device
has no Mount Bridge driver in its profile at all, so offering "Full Simulation (INDI/Mount
Bridge)" there doesn't correspond to anything real on that device - the tile's own toggle
(`toggleTruthInjector()`) would still just feed PiFinder's own `/api/fake_solve` (that part is
role-independent and fine), but the tile's *name* and framing ("INDI/Mount Bridge") imply
capabilities this profile doesn't have. Now that section 3 is decided: when
`pifinder_role_choice === "client"`, relabel or drop the "(INDI/Mount Bridge)" qualifier on that
tile (a PiFinder Client never has Mount Bridge in its own profile, by definition of the card); when
`"host"` (GoTo Mode) or `null` (no choice yet), keep today's wording unchanged.

## 5. Status

Decided (2026-09-13): option (c), a manual third "PiFinder Client" role card, with the state model
and mismatch-warning behavior from section 3 above, mocked up (linked in 3b). **Not implemented
yet** - concept + mockup only, per this project's own "concept first, mockup first for GUI
changes" pattern. Remaining work before it can ship:

1. Backend: `pifinder_role_choice` field (`_save_mount_bridge_desired_state()`/
   `MOUNT_BRIDGE_DESIRED_STATE_FILE`, same pattern as every other sticky Mount Bridge setting), a
   route to set it, included in the existing profile-poll response the frontend already reads.
2. Frontend: third `.mb-role-card`, `deriveProfileRole()`'s `'host'` branch presentation split by
   `pifinder_role_choice` (card highlighting, tile pill text, page/tile heading suffixes already
   built for `'host'`/`'ctrl'` extended to distinguish the two), the mismatch `.showstopper-card`
   from 3b.
3. The Mode & Power tile gap from section 4 (drop "(INDI/Mount Bridge)" wording for
   `pifinder_role_choice === "client"`).
4. **In scope per direct confirmation ("Dein Nebenbefund muss berücksichtigt werden")**: surface
   the remote device's own `pifinder_role_choice` to a Control host mirroring it, so its PiFinder
   tile pill can distinguish "the remote chose PiFinder Client" from "...chose PiFinder host but has
   no mount linked yet" - both currently derive the identical remote `role === 'host'` and would
   otherwise keep showing identically forever. Needs a way to read it across devices - likely the
   same category 2a/2b machinery already built for Solve/GPS/Camera/IMU/orientation
   (`docs/concepts/control_host_hardware_badges_mirroring.md`): either a thin proxy to the remote
   PiFinder's own API (if `pifinder_role_choice` ever became visible there) or, more likely, a
   direct Control-Center-to-Control-Center call (2b's `_cc_proxy_get()`) to the remote CC's own
   `/state`, which already carries this field per point 1 above. The already-shipped Round-2
   wording (the PiFinder tile's pill saying "Client Mode" for local `role === 'host'`, "PiFinder
   Client" for `role === 'ctrl'`/`'ctrl-incomplete'` describing the *mirrored* device) was the best
   name available before this was decided and reads consistently with the final design - it becomes
   the *correct, permanent* wording for "the remote's choice is known and is Client"; point 4 here
   is what makes the "no mount linked yet, choice unknown" case distinguishable instead of
   silently reading the same.
