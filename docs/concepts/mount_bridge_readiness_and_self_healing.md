# Concept: Mount Bridge readiness checks + self-healing

## 1. Context

Live-tested 2026-09-01 (basic-memory pifinder-stellarmate/00105/00106, PR #237/#239, issue #238):
across a single testing session, Mount Bridge repeatedly became unresponsive or lost its linked/
coupled state, and the Full-Simulation truth-injector died once with nothing noticing. Each time,
the only way anything got fixed was a human (or an agent, driving raw `indi_setprop`/service
restarts) noticing something looked wrong and manually repairing it. Direct user feedback: *"Was
mich einfach stört, ist die Zuverlässigkeit... So ein 'Readiness' und 'Self-Healing' Prozess sollte
nach jeder Benutzerinteraktion stattfinden."*

This concept is scoped to Mount Bridge specifically - the truth-injector already has exactly this
pattern (`_truth_injector_watchdog()` in `gui_installer/server.py`, 5s interval, restarts it if it
dies while still "desired"), built in response to the same kind of feedback on 2026-08-10 ("Muss
dann zuverlässig laufen"). That mechanism is not broken; today's Full-Simulation failure traced to
an *agent* starting the injector via a raw shell command instead of through the Control Center's
own toggle, which bypasses the tracking the watchdog depends on - a process discipline problem, not
a design gap. Mount Bridge has no equivalent at all.

## 2. Failure modes actually observed today (not hypothetical)

- **Driver goes unresponsive while the process stays alive.** Confirmed twice with `gdb -p <pid>`:
  both threads sitting cleanly in `select()`, no deadlock visible, yet zero bytes back for any new
  `getProperties` - not yet root-caused (issue #238). A restart via indiFIFO stop/start reliably
  recovers it.
- **Repeated connect/disconnect cycling.** User's own Control Center log:
  ```
  17:16:24 Mount Bridge status changed: running=False bridge_connected=None active_mount=None
  17:17:18 Mount Bridge status changed: running=True bridge_connected=True active_mount=Telescope Simulator
  17:21:24 Mount Bridge status changed: running=False bridge_connected=None active_mount=None
  17:21:44 Mount Bridge status changed: running=True bridge_connected=True active_mount=Telescope Simulator
  17:24:00 Mount Bridge status changed: running=False bridge_connected=None active_mount=None
  ```
  Roughly every 1-5 minutes, unprompted.
- **Reconnect races ahead of the driver actually being ready**, from the same log:
  ```
  17:25:00 linking Mount Bridge to mount 'Telescope Simulator'...
  17:25:03   warning: active-devices selection applied but not saved to disk: PiFinder Mount Bridge:
             property 'CONFIG_PROCESS' not currently defined (device may not be connected yet, or
             the name is wrong)
  17:26:21 setting coupling mode goto_forward (threshold=default, action=default)...
  17:26:24   failed: PiFinder Mount Bridge: property 'BRIDGE_MODE' not currently defined (device
             may not be connected yet, or the name is wrong)
  ```
  These are one-shot actions fired the instant a `running=True` transition is observed, with no
  retry - if the driver's own property definitions haven't caught up yet (plausible right after a
  reconnect from the flapping above), the action is simply lost, silently, with only a log line
  buried in the Mount Bridge details panel.
- **Coupling mode not reliably restored after a reconnect** - implied by the above (a `failed` link/
  mode-set leaves the tile showing stale/wrong state until the next user action notices).

## 3. Design: per-use-case required state, checked and self-healed

Same shape the user asked for: it's already clear, per active use case, what has to be true. A
single watchdog loop (same pattern/cadence as `_truth_injector_watchdog()`, extending it rather
than inventing a second mechanism) evaluates these in order, self-healing on the first mismatch
found each tick rather than piling up multiple repairs at once:

| # | Precondition (only relevant when...) | Required state | Self-heal action |
|---|---|---|---|
| 1 | Mount Bridge is supposed to be running at all (a profile that includes it is active) | `getProperties` against `PiFinder Mount Bridge` answers within a short timeout | Restart the driver (indiFIFO stop/start) - the only known recovery for the unresponsive-but-alive case (§2, issue #238 stays open for the *why*, this is the mitigation) |
| 2 | (1) is healthy | `CONNECTION.CONNECT=On` | Send `CONNECT=On` |
| 3 | (2) is healthy | `ACTIVE_DEVICES.ACTIVE_MOUNT`/`ACTIVE_PIFINDER` match the profile's configured devices, and both those devices themselves report `CONNECTION.CONNECT=On` | Re-run the existing "link" step (already idempotent - same code the Setup button uses), **with retries** (e.g. 3 attempts, 1-2s apart) instead of firing once - directly fixes the `CONFIG_PROCESS`/`BRIDGE_MODE not currently defined` race in §2, which is really "acted before the driver finished defining properties," not a permanent failure |
| 4 | (3) is healthy AND the user has a coupling mode selected (not Off) | `BRIDGE_MODE` matches the last mode the user actually chose (tracked server-side, same idea as `_truth_injector_device`) | Re-apply the coupling mode (+ threshold/action), same retry treatment as (3) |
| 5 | Full Simulation is desired (existing truth-injector concept, extended) | Injector process alive **and** PiFinder's own `last_solve_success` is recent (not just "process exists" - it could be alive but failing every cycle silently) | Restart the injector (existing `_truth_injector_start()`) |
| 6 | Full Simulation is desired **and** `PiFinder Simulator` is the active PiFinder device (PR #239's mount-follow feature) | `PiFinder Simulator.FOLLOW_MOUNT_DEVICE` is set and equals the current `ACTIVE_MOUNT` | Set it - this also fully closes today's "Dead reckoning geht nicht" report at the root instead of requiring anyone to configure it by hand at all; see its own note below |

Checks 1-4 are the actual new ground (nothing like them exists for Mount Bridge today); 5 is a
small extension of the existing truth-injector watchdog; 6 is a very small, mostly-independent
addition that happens to fit the same loop naturally.

## 4. On check 6 - closes a whole class of "silently not simulating physics correctly"

Right now `FOLLOW_MOUNT_DEVICE` is a raw INDI property nobody sets except by hand (`indi_setprop`,
or a not-yet-built Control Center control) - discovered live today: it doesn't survive a driver
restart without PR #239's persistence fix, and even with that fix, a user who links a *different*
mount than before has no way to know they also need to update this separately. Since the Control
Center already knows `ACTIVE_MOUNT` (it's the one that sets it during linking), the watchdog
keeping `FOLLOW_MOUNT_DEVICE` in lockstep with it removes an entire manual-configuration step -
"Full Simulation is on and a mount is linked" already implies "PiFinder should dead-reckon-follow
that mount while it slews," per §9 of `complete_position_simulator.md`. No separate GUI control
needed at all if this stays self-maintaining.

## 5. Where this lives

`gui_installer/server.py`, as a new `_mount_bridge_readiness_watchdog()` thread started next to
`_truth_injector_watchdog()` in the same startup block. Reuses `indi_client.py`'s existing
functions (`mount_bridge_status()`, `set_coupling_mode()`, the linking helper already behind the
Setup button) rather than new INDI-protocol code - this is orchestration, not a new capability.

Logging: reuse `_mb_log()` (already shown in the Mount Bridge details panel), but each self-heal
action should log distinctly from a plain status-changed line (e.g. "self-healed: restarted
unresponsive Mount Bridge driver") so the pattern in §2's log excerpt becomes legible as "the
system caught and fixed something" instead of unexplained flapping.

## 6. Open questions

- **Watchdog interval.** 5s (matching the truth-injector one) risks fighting a driver that's still
  mid-restart from the *previous* tick's self-heal - needs a short cooldown after taking an action
  before re-evaluating that same check, not a fixed retry every tick regardless.
- **Restart storms.** If check 1's restart doesn't actually fix an unresponsive driver (root cause
  from #238 unknown), a naive loop would restart it every 5s forever. Needs a backoff/give-up-and-
  surface-loudly threshold (a handful of attempts, then stop and show a clear GUI warning instead
  of silently retrying forever) - same shape as `indi_client.py`'s own `BINDING_RETRY_MAX_ATTEMPTS`
  pattern already used for the PiFinder/mount property-binding race.
- **Server-side "last chosen coupling mode" tracking** (needed for check 4) doesn't exist yet -
  needs to be set wherever the user's own coupling-mode-change request currently gets sent, small
  addition.
- **Should self-healing be visible/interruptible**, or fully silent? Given the readiness-line work
  from 2026-08-30/31 (basic-memory 00102/00103) already surfaces "is everything ready" passively,
  probably: silent when it succeeds (that's the whole point), loud only when it gives up (previous
  bullet).
- Not addressed here at all: root-causing *why* Mount Bridge goes unresponsive in the first place
  (issue #238) - this concept treats it as a fact to recover from, not a bug to fix directly.
