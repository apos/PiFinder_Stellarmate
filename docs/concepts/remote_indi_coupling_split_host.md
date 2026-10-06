# Concept: PiFinder as a separate device, Mount Bridge on a remote Control host (split-host coupling)

> **Status: implemented and verified** across two physical Raspberry Pis on 2026-07-29 (released in
> v1.3.0; PRs #70 and #71). Tracked as
> [GitHub issue #60](https://github.com/apos/PiFinder_Stellarmate/issues/60) (closed). Narrower
> follow-ups are tracked separately — see §8.
>
> **Provenance:** the original of this document lived on the since-deleted branch
> `concept/remote-mount-bridge-and-setup-refactor` and never reached `main`/`dev`. This file is a
> **reconstruction** (2026-10-06) from the surviving sources: issue #60 and its closing comment, the
> basic-memory notes `pifinder-stellarmate/00076`, `00078` and `00079`, the code comments that cite
> this document (`R-CH1`, `R-PF1`, `R-ROLE1`), the commit history and `Readme_PiFinder_LX200.md`. Where the
> original's wording is lost, this says so.

## 1. Idea

The `PiFinder LX200` driver runs on the **PiFinder's own host** (it talks locally to `pos_server.py`) and
is exposed over the network by that host's own `indiserver`. A separate, more capable **Control host**
runs the real INDI Web Manager, `indi_pifinder_mount_bridge` and the real mount driver, and adds
`PiFinder LX200` as an INDI **remote driver** (`PiFinder LX200@<ip>:7624`) instead of a local one.

```
PiFinder host                                    Control host
  pos_server.py ── indi_pifinder_lx200 ──┐         KStars/Ekos ── Web Manager profile
                    indiserver :7624  ───┼── LAN ──▶  PiFinder LX200@<ip>:7624  (remote)
                                         │            indi_pifinder_mount_bridge
                                                      real mount driver (e.g. LX200 OnStep)
```

### Who it serves

- PiFinder hardware too weak to also run a full StellarMate/KStars stack (e.g. a Pi 4/2 GB).
- Fixed-observatory setups with an existing dedicated mount-control computer.
- A Control host that is a StellarMate (Pi 5 / x86), Astroberry, plain Ubuntu + KStars, or a StellarMate
  Pro with no PiFinder attached.

Builds directly on issue #37, whose already-researched stock-Debian howto is effectively the
**PiFinder-host half** of this concept. Its install-side counterpart is
[`setup_indi_only_install_mode.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/setup_indi_only_install_mode.md) (#61).

## 2. Device role model (R-ROLE1)

**A device has no role — the selected Web Manager *profile* has one**, derived live from which drivers it
actually contains (`deriveProfileRole()` in `status_page.html`):

| Local PiFinder LX200 | Remote PiFinder LX200 | Mount Bridge | Role |
|---|---|---|---|
| yes | – | yes | all-in-one |
| yes | – | no | PiFinder host |
| – | yes | yes | Control host |
| – | yes | no | Control host, incomplete |
| – | – | yes | bridge only |
| – | – | no | none |

Install state (is `~/PiFinder` present?) is **only a capability limit**, not a role indicator: it
disables the cards that cannot work and drives the config-error warning. The reasoning was settled by two
rejected designs:

1. **Rejected: a device banner derived from the existence of `~/PiFinder`.** Objection: that directory is
   no role indicator — two full PiFinders can take turns, and INDI-only mode deletes nothing.
2. **Rejected: a separate "PiFinder Host Setup" tile** (R-PF1, built and then removed), plus an
   unobtrusive grey "Role:" line and a hidden "remote:" input. Objection: the role was undiscoverable
   ("stared at it for two minutes"); the choice between use cases never showed up *as* a choice.
3. **Final: role cards** at the top of the setup area of the Mount Bridge tile — one tile, several roles,
   plus a coloured **"Role:" chip** at the very top, both derived live from the profile. Clicking a card
   reconfigures the profile after a confirm dialog; the Control-host card asks for the PiFinder host's IP.
   The role is the main navigation, not a derived side note.

Wording of the original three cards (project owner's, verbatim): *"All-in-one – PiFinder hardware with
mount."*, *"PiFinder host – PiFinder only, no mount."*, *"Control host – No PiFinder hardware. Couples to
remote PiFinder."* Intro line: *"Three setup variants for integrating your PiFinder with INDI. Choose the
appropriate role."* The **PiFinder-host** role hides everything mount-related and instead shows the
device's own LAN IP (R-PF1) — exactly what the other device's Control-host card asks for.

**Later evolution** (2026-09-12/13, not part of the original concept): the All-in-one and PiFinder-host
cards were merged, and **"PiFinder Client"** was added as an explicit third role card (#434) — it
configures the same profile shape as a PiFinder host (local PiFinder LX200, no Mount Bridge) and differs
only in telling the Control Center which use case the device is for; a device cannot detect this on its
own. See [`pifinder_client_role_and_indi_setup_review.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/pifinder_client_role_and_indi_setup_review.md)
and #416 (prevent double mount access).

## 3. Remote-driver support (R-CH1)

`gui_installer/webmanager_client.py` puts a profile's `PiFinder LX200` entry into exactly **one of three
states**, never a local and a remote at once (`set_pifinder_lx200_state()`):

- **absent** — no PiFinder LX200 at all,
- **local** — a local driver on this device (classic setup),
- **remote** — proxied from another device's `indiserver`; `remote` = that device's `host:port`.

Every other driver in the profile — local or remote — is left untouched. All seven state transitions
(absent ↔ local ↔ remote, remote update) were tested against a throw-away profile. The server endpoint
additionally accepts `driver=lx200&action=add_remote&remote=<host[:port]>`.

### Verified facts about StellarMate's Web Manager remote API

**The OpenAPI documentation is misleading** — these were found live:

- Setting a remote entry: `POST /api/profiles/{p}/drivers` with `{"remote": "PiFinder LX200@host:port"}`
  **without** a `label` key. The form from the OpenAPI schema (`label` + `remote`) is silently stored as a
  **local** driver and the remote spec is lost.
- Remote entries **also appear** in `GET .../labels` as a normal label. Local vs. remote is only
  distinguishable via `GET /api/profiles/{p}/remote` (a comma-separated string).
- Removing a remote entry needs the same **delete-and-recreate workaround** as removing a label (a plain
  POST leaves the label lingering, which would be misread as a *local* PiFinder LX200 present). This is a
  StellarMate Web Manager quirk, not present in the open-source project it is based on.
- `indiserver` on StellarMate binds `0.0.0.0:7624` by default — nothing extra to configure LAN-side
  except the firewall.

## 4. Setup flow

1. **PiFinder device:** needs `PiFinder LX200` built and an `indiserver` hosting it. On a StellarMate
   device: role card "PiFinder host". On a stock Debian PiFinder: the manual path in #37, or the
   INDI-only install ([`setup_indi_only_install_mode.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/setup_indi_only_install_mode.md)) — note that
   today the stock PiFinder host side is **not** a ready-made script (#401).
2. **Control host:** install via INDI-only mode, then the "Control host" role card and the PiFinder
   host's IP. The Mount Bridge and the mount driver run here.
3. **Safety patch on the PiFinder side:** `pos_server.py` must carry the patch that makes an unsolved
   PiFinder signal *no data* instead of the hard-coded fake coordinate RA=0/Dec=0 (issue #107) — otherwise
   a remote Mount Bridge can read that as real drift. See #401.

## 5. Delivered and verified

- Live over **two physical Raspberry Pis**, 2026-07-28/29: Pi 4 as PiFinder host (profile with only a local
  PiFinder LX200), Pi 5 as Control host (Mount Bridge + LX200 OnStep + `PiFinder LX200@<pi4-ip>:7624` as
  remote driver). The bridge coupled the remote PiFinder with live position data, GoTo-forward active,
  drift display green — set up on both sides via the role cards in a few clicks. The mount side was
  simulation at that point; a real-mount test followed later.
- INDI-only install ran cleanly on the second device (≈1 min, Atomic-Updates cycle with relock).
- Shipped via **PR #70** (role cards / remote-driver support) and **PR #71** (Mount Bridge reliability
  follow-up, below).

## 6. Known risks and findings

### 6.1 Periodic "not coupled" flicker — resolved (2026-07-29)

Symptom: the Mount Bridge tile repeatedly showed "not coupled" for ~7 s to ~2 min, every few minutes
("absolute no-go" for imaging if real). The diagnostic trail ruled out, with evidence: StellarMate's
PID-based driver restart on remote entries (real, but only once after a profile start — the Web Manager
treats a remote entry's missing local PID as a crash, restarts it 3× then "gives up"), a TCP connection
leak, a hung `indiserver`, and a hung Mount Bridge process (`strace` showed no gap > 3 s).

**Actual cause:** the control layer's own `indi_client.get_properties()` call for "PiFinder Mount Bridge"
(the periodic 20 s background poll) used a client-side `DEFAULT_TIMEOUT = 3.0 s`. `indiserver` is
occasionally still busy distributing a flood of small property updates from the OnStep driver (~37/s seen)
and answers that one query just over 3 s late — while the system is healthy. Three parallel direct polls
(PiFinder LX200, the mount, the Bridge's `DRIFT_STATUS`) showed zero outages, and the mount was seen
tracking live in Ekos during a "not coupled" display. It is a decision in our own lean client, not in
libindi, `indiserver` or the drivers.

**Fix:** `/api/mount_bridge_status` passes `timeout=7.0, device_timeout=3.0` **only** for that passive
poll (the global default stays 3.0 s so interactive actions still fail fast); the UI needs **two**
consecutive empty polls (~40 s) before showing "not loaded"; the status dot now pulses on the first miss
instead of staying silent.

### 6.2 `indi_pifinder_lx200` has no reconnect logic

If its connection to `pos_server.py` drops, the driver does not reconnect. More relevant over a real
network than on localhost. Tracked separately (#139, closed).

### 6.3 Non-StellarMate Web Managers

Whether Astroberry's or plain `indiwebmanager` support adding a remote driver as easily as a local one is
**not verified**. The concept's biggest open question at the time. See #400.

### 6.4 No authentication

INDI has none. Exposing the LX200 driver on the LAN is acceptable in a home/observatory network but should
be documented explicitly, not silently assumed.

### 6.5 Two devices on one mount

If the PiFinder device still runs its own Mount Bridge linked to the same mount, two independent INDI
clients steer it — found live 2026-09-12, tracked in #416.

### 6.6 Other

- The Mount Bridge sends `POST http://127.0.0.1/api/set_mount_type` on every reconnect (fallback port
  8080). Harmless and fast, unnecessary on a Control host; later work made the Bridge target the
  *remote* PiFinder's HTTP host (#452/#453).
- The Control Center and `gui_installer/` still assume StellarMate's Web Manager — #400.

## 7. Implementation map

| Piece | Where |
|---|---|
| Three-state remote-driver handling, Web Manager workarounds | `gui_installer/webmanager_client.py` (`set_pifinder_lx200_state`, `get_remote_drivers`) |
| `add_remote` action, validation | `gui_installer/server.py` |
| Role cards, role chip, PiFinder-host LAN IP, `deriveProfileRole()` | `gui_installer/status_page.html` |
| INDI-only install (light PiFinder-host-side and Control-host install) | [`setup_indi_only_install_mode.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/setup_indi_only_install_mode.md) |

## 8. Related

#37 (stock-Debian PiFinder howto) · #61 (INDI-only install) · #62 (test suite) · #400 (Control host on
non-StellarMate) · #401 (`pos_server.py` safety patch for a stock PiFinder) · #416 (PiFinder host role,
no double mount access) · #434 (PiFinder Client card) ·
[`control_host_hardware_badges_mirroring.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/control_host_hardware_badges_mirroring.md) ·
[`pifinder_client_role_and_indi_setup_review.md`](https://github.com/apos/PiFinder_Stellarmate/blob/dev/docs/concepts/pifinder_client_role_and_indi_setup_review.md).
