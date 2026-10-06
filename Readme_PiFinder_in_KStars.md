# PiFinder in KStars — Sky-Map View & Right-Click Operations

*[Deutsche Version](Readme_PiFinder_in_KStars_de.md)*

> **Scope:** what KStars shows once **PiFinder LX200** and/or **PiFinder Simulator** are
> connected, and what the right-click Goto / Sync / … operations do to each.
>
> - Getting the devices connected: [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md)
> - The Mount Bridge / Injected-Solve test rig: [Readme_PiFinder_Simulator.md](Readme_PiFinder_Simulator.md)

---

## Table of Contents

1. [The two devices in KStars](#the-two-devices-in-kstars)
2. [How KStars draws them](#how-kstars-draws-them)
3. [Right-click operations](#right-click-operations)
4. [Typical flows](#typical-flows)
5. [See Also](#see-also)

---

## The two devices in KStars

| Device | Represents | Context-menu items |
|---|---|---|
| **PiFinder LX200** (`indi_pifinder_lx200`) | PiFinder's live plate-solved position (real hardware) | Goto, Abort, Find Telescope — **no Sync** |
| **PiFinder Simulator** (`indi_pifinder_simulator`) | A hand-set stand-in for that position (hardware-free testing) | Goto, **Sync**, Abort, Find Telescope |

Both are `INDI::Telescope` devices, so KStars treats them like any mount: a marker on the sky map,
a submenu in every sky-map right-click, and a row in the Ekos **Mount** module. Neither drives a
motor — PiFinder has none, and the Simulator only holds a value.

The **Telescope Simulator** (stock INDI, not part of this project) usually sits alongside them as
the *mount* stand-in when there is no real mount.

## How KStars draws them

- **Sky-map marker** — a red **crosshair with a double circle** at the device's current RA/Dec,
  updated live (about once a second for PiFinder LX200; the truth-injector interval for the
  Simulator). The circle is a fixed screen size, not a real field of view.
- **Label** — the device name beside the marker. When PiFinder and the mount point at the same
  place, their markers and labels **overlap** — that is the normal "they agree" state, not an
  error.
- A **solid** crosshair means the device reports it is tracking; a **dashed / dotted** circle
  means idle / not tracking (the stock Telescope Simulator shows this until told to track).

<table>
<tr>
<td align="center" width="50%">
<a href="docs/images/pfinder_lx200/kstars_marker_colocated.png"><img src="docs/images/pfinder_lx200/kstars_marker_colocated.png" width="380"></a><br>
<sub>PiFinder LX200, PiFinder Simulator and the mount all at the same RA/Dec — one marker, three labels stacked</sub>
</td>
<td align="center" width="50%">
<a href="docs/images/pfinder_lx200/kstars_context_menu_both_mount_and_pifinder.png"><img src="docs/images/pfinder_lx200/kstars_context_menu_both_mount_and_pifinder.png" width="380"></a><br>
<sub>PiFinder and the mount pointing at different places — two separate crosshairs (here deliberately far apart)</sub>
</td>
</tr>
</table>

In **Ekos → Mount**, PiFinder LX200 appears in the telescope dropdown with its RA/Dec and Az/Alt
and a tracking-state indicator. Its slew / park controls are inert (nothing to move).

## Right-click operations

Right-click anywhere on the sky map. The context menu lists **one submenu per connected INDI
telescope** — here *Telescope Simulator*, *PiFinder LX200*, *PiFinder Simulator*. Each submenu
acts on **that** device, using the **clicked sky position** as the target.

<table>
<tr>
<td align="center" width="40%">
<a href="docs/images/pfinder_lx200/kstars_context_menu_devices.png"><img src="docs/images/pfinder_lx200/kstars_context_menu_devices.png" width="240"></a><br>
<sub>One submenu per connected telescope device</sub>
</td>
<td align="center" width="60%">
<a href="docs/images/pfinder_lx200/kstars_submenu_pifinder_lx200.png"><img src="docs/images/pfinder_lx200/kstars_submenu_pifinder_lx200.png" width="360"></a><br>
<sub>PiFinder LX200: Goto, Abort, Find Telescope — no Sync</sub>
</td>
</tr>
</table>

### PiFinder LX200 — Goto / Abort / Find Telescope

| Item | Effect |
|---|---|
| **Goto** | Sends the clicked RA/Dec to PiFinder as a **push-to target** — identical to choosing an object on PiFinder's own screen or a SkySafari push-to. PiFinder shows push-to arrows toward it. The marker does **not** jump: PiFinder's reported position keeps coming from the live solve, and its track state stays idle — nothing physically moves. |
| **Abort** | Clears the push-to target. (No motor to stop.) |
| **Find Telescope** | Recenters the sky map on the marker. Read-only. |

**Why no Sync:** PiFinder has nothing to synchronise — it reports the freshly solved actual
position on every frame. To push a correction onto a coupled *mount*, use the Mount Bridge, not
this menu — see
[Readme_PiFinder_LX200.md → Coupling Dial](Readme_PiFinder_LX200.md#the-mount-bridge-coupling-dial).

### PiFinder Simulator — Goto / Sync / Abort / Find Telescope

<table>
<tr>
<td align="center">
<a href="docs/images/pfinder_lx200/kstars_submenu_pifinder_simulator.png"><img src="docs/images/pfinder_lx200/kstars_submenu_pifinder_simulator.png" width="360"></a><br>
<sub>PiFinder Simulator: Goto and Sync both just set the held position</sub>
</td>
</tr>
</table>

The Simulator holds one settable RA/Dec. **Goto and Sync do the same thing here** — both set the
held position to the clicked coordinates immediately, with no slew and no motion model. The
distinction is kept only so the device still behaves like an ordinary telescope for any client
that expects one. With the truth injector running, that new position is injected into PiFinder as
a solve within one cycle, and everything downstream (PiFinder LX200's marker, Mount Bridge drift)
reacts as if a real solve landed there. This is how you place "PiFinder" exactly where a test
needs it. The Simulator can also **dead-reckon along with a mount's slews** — see
[Readme_PiFinder_Simulator.md → Mount-following](Readme_PiFinder_Simulator.md#mount-following-follow_mount_device).

### Telescope Simulator — the mount stand-in

<table>
<tr>
<td align="center">
<a href="docs/images/pfinder_lx200/kstars_submenu_telescope_simulator.png"><img src="docs/images/pfinder_lx200/kstars_submenu_telescope_simulator.png" width="360"></a><br>
<sub>Telescope Simulator: a full mount menu — Goto, Sync, Park/UnPark</sub>
</td>
</tr>
</table>

The stock INDI mount simulator, used as the mount side when there is no real mount. Full mount
menu: **Goto** (simulated slew), **Sync**, **Park / UnPark**, **Goto & Set As Parking Position**.
Sync it deliberately right or wrong against the PiFinder position to give Verify/Alert or
Auto-correct something to react to. A real mount's own driver submenu looks similar.

## Typical flows

- **Visual push-to, real PiFinder, no mount** — right-click the target → *PiFinder LX200 → Goto* →
  follow the arrows on PiFinder's screen.
- **Visual push-to with a coupled mount** — same click; with the Mount Bridge in *Goto-Forward*
  the mount slews there too. See
  [Coupling Dial](Readme_PiFinder_LX200.md#the-mount-bridge-coupling-dial).
- **Hardware-free test** — *PiFinder Simulator → Sync* to place PiFinder, *Telescope Simulator →
  Sync* to place the mount (agreeing or not), then watch the Mount Bridge. Full setup in
  [Readme_PiFinder_Simulator.md](Readme_PiFinder_Simulator.md).

## See Also

- [Readme_PiFinder_LX200.md](Readme_PiFinder_LX200.md) — connecting the devices, the INDI Control Panel, the Mount Bridge and its Coupling modes
- [Readme_PiFinder_Simulator.md](Readme_PiFinder_Simulator.md) — the PiFinder Simulator + truth injector test rig
- [Readme_ControlCenter.md](Readme_ControlCenter.md) — the Control Center that drives the whole simulation setup
- [README.md](README.md)
