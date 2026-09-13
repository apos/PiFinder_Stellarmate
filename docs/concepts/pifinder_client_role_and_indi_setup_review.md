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

## 3. The naming question

"PiFinder Client" reads as a proposal to rename what's shown for `role === 'host'` (today's card
title: "PiFinder host", pill: "PiFinder host") - "host" suggests this device is in charge, which
is backwards in a split setup where a *different* device's Control host is actually doing the
mount coupling. Three ways to read the request, needing a decision before touching code:

- **(a) Pure rename, same trigger.** Swap "PiFinder host" → "PiFinder Client" everywhere
  `role === 'host'` is shown (role card title/sub, tile pill, help.html), no new detection logic.
  Simplest, ships immediately - but doesn't distinguish "genuinely standalone, nobody else
  involved" (a lone PiFinder with no networking story at all) from "actively being remoted into by
  a Control host" (the case the name is actually about), so it risks confusing users who are
  running truly standalone.
- **(b) A real third state**, only shown once this device can actually detect a remote coupling
  (an incoming connection to its own indiserver/pos_server.py from an external IP) - this is
  exactly issue #416's own scope, not yet designed. Correct, but not a quick follow-up to this doc.
- **(c) A manual choice**, not auto-detected: add "PiFinder Client" as its own explicit role card
  (alongside today's "PiFinder host" and "Control host" cards) that a user picks *because they know
  ahead of time* this device will be controlled remotely - functionally identical to today's
  `role === 'host'` under the hood (same profile shape: local PiFinder LX200, no Mount Bridge),
  differing only in which card/label is shown and, per section 4 below, which mode tiles apply.
  Needs one new piece of state to remember the choice (today's two cards map 1:1 to underlying
  profile facts; a third card that maps to the *same* facts as "PiFinder host" needs something
  else - e.g. a `localStorage` flag - to tell them apart on reload).

No default recommended here - (a) is the cheapest, (c) is the most honest about being a labeling
choice rather than a detected fact, (b) is the real fix but a separate, larger project (#416).

## 4. INDI Setup section - what's already role-aware, what isn't

`updateProfileRoleLine()` already hides/adapts a fair amount for `role === 'host'`
(`hostMode` in that function): `#mb-operate-rows`, `#mb-steps-4-6` (Mount/Ekos/Connect steps),
`#mb-setup-btn-row` (One-Click Setup), `#mb-status-row`, `#mb-diagram`, `#mb-mode-caption-row`,
`#mb-mode-details` all hidden; `#mb-add-mount-row` (the "+ Couple a mount" button) and
`#mb-thisdevice-ip-row` shown instead. This is a solid existing baseline - whichever naming option
above is picked, this logic already keys off the same `hostMode`/`role` values and doesn't need
rework, just (for option (c)) extending to also recognize the new card's own state.

**Gap found reading `setModeTileVisible()`/the Mode & Power tiles**: the three mode tiles (Real
Hardware / **Full Simulation (INDI/Mount Bridge)** / PiFinder-only Fake Mode) are gated only on
whether an install/reinstall run is currently active - never on role. A `role === 'host'` device
has no Mount Bridge driver in its profile at all, so offering "Full Simulation (INDI/Mount
Bridge)" there doesn't correspond to anything real on that device - the tile's own toggle
(`toggleTruthInjector()`) would still just feed PiFinder's own `/api/fake_solve` (that part is
role-independent and fine), but the tile's *name* and framing ("INDI/Mount Bridge") imply
capabilities this profile doesn't have. Worth revisiting once the naming question above is
settled, since the fix differs by option: (a)/(c) could simply relabel or hide the "(INDI/Mount
Bridge)" qualifier for this role; (b) would additionally need to reflect the *actual* remote
Control host's own Mount Bridge state, which doesn't exist locally to read.

## 5. Not implemented yet

This is a concept only, per the same "concept first, mockup first for GUI changes" pattern the
Control host badges work followed - no naming decision has been made, and no code has changed as
part of this doc. Needs a decision on section 3's three options before any renaming lands, and a
mockup of whatever the chosen option's role card/pill looks like before it's built.
