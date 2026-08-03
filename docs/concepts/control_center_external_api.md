# Concept: Control Center as a documented, externally-usable API

## 1. Question that triggered this

While live-testing the Mount Bridge (#106/#116) via direct INDI/HTTP calls, the question came up:
do the Control Center's buttons and status tiles (PiFinder Mode/Power, Hardware Test, Mount Bridge
coupling/sync/threshold, Web Manager setup checklist, Uninstall/Reset, ...) have real API endpoints
behind them, usable for external/automated control - not just human clicks in the browser?

## 2. Current state (as found, `gui_installer/server.py`)

**Short answer: yes, functionally.** The Control Center is not server-rendered HTML with hidden
form posts - the frontend is a thin client over a genuine JSON HTTP API on the same server
(`pifinder-control-center.service`, port 8765). Every visible action already has a route. Full
inventory of `do_GET`/`do_POST` routes as of this writing:

**Status / read (GET)**
- `/page_version`, `/last_run_summary`, `/state`, `/log`
- `/api/mount_bridge_status`, `/api/mount_bridge_drift`, `/api/mount_bridge_log`
- `/api/webmanager/profiles`, `/api/webmanager/pifinder_drivers`, `/api/webmanager/other_drivers`
- `/api/kstars_webmanager_link`, `/api/ekos_indi_status`
- `/api/hardware_status`, `/api/hardware_test_log`, `/api/debug_solve`
- `/api/reset_log`, `/api/uninstall_log`, `/api/pifinder_mode_log`

**Actions (POST)**
- `/start` (install/update/reinstall, with `branch`/`mode` params), `/reboot`, `/shutdown`,
  `/poweroff`, `/uninstall`, `/reset`
- `/api/pifinder_mode` (enable_fake/disable_fake), `/api/pifinder_service` (start/stop/restart)
- `/api/debug_solve`, `/api/hardware_test`
- `/api/display_bridge`, `/api/keyboard_bridge`
- `/api/webmanager/server`, `/api/webmanager/pifinder_drivers`
- `/api/mount_bridge_active_devices`, `/api/mount_bridge_connect`, `/api/mount_bridge_coupling`
  (Verify/Alert, Auto-correct Sync, Auto-correct Goto&Track, Goto-Forward, Decouple),
  `/api/mount_bridge_threshold`, `/api/mount_bridge_manual_sync`

Every button visible in the two screenshots reviewed (PiFinder Mode/Test/Power tile, Mount Bridge
tile incl. the setup checklist) maps onto one of these. There is no button that's UI-only with no
backing endpoint.

## 3. What's missing for this to be a *real*, documented external API

The routes work, but nothing here was designed as a public integration surface - it grew as "the
backend for this one frontend". Concretely missing:

1. **No documentation.** The only way to discover a route, its parameters, or its response shape is
   reading `server.py` source. No README section, no OpenAPI/Swagger spec, no changelog discipline
   for route changes.
2. **No stability contract.** Nothing marks a route as "safe to depend on externally" vs. "internal
   implementation detail that can change any time a UI tweak needs it to". All 35+ routes currently
   look equally official from the outside.
3. **Auth reuses the OS account password, not a scoped token.** `_require_auth()` checks HTTP Basic
   Auth against the `stellarmate` Linux account's real password via PAM (rate-limited lockout on
   repeated failures). That's a reasonable model for "a human logs into the web UI", but handing the
   same credential to an external script/automation means that script now holds the account's actual
   login password - no scoping (e.g. read-only vs. destructive), no revocation short of changing the
   OS password, no per-client identification.
4. **A few routes are deliberately auth-exempt** (`/state`, `/log`, `/page_version`,
   `/api/uninstall_log` - for polling latency during time-critical operations like uninstall). Fine
   as designed, but worth calling out explicitly in any API doc since it's a real, intentional
   exception to "everything needs auth", not an oversight.
5. **No consistent error/response envelope documented.** Responses are JSON and mostly follow a
   `{"started": bool, "error": str}`-ish shape per route, but this convention lives only in the
   source, not written down anywhere as a rule new routes should follow.

## 4. Why this matters now

Tonight's live testing (#106 family) drove PiFinder/the Mount Bridge/INDI directly via `curl` and
`indi_getprop`/`indi_setprop`, bypassing the Control Center entirely - which worked, but only
because someone (an agent, in this case) was willing to read `server.py` source to find the right
route/property names by hand. A documented, stable, properly-scoped API would make this kind of
external control (testing, automation, future integrations - e.g. a Home Assistant bridge, a CLI
tool, a second device orchestrating this one) something anyone can do without spelunking through
the implementation.

## 5. Proposed direction (not yet decided/implemented)

- Write a single reference doc (or generate one from the route table) listing every endpoint,
  method, params, and response shape - the inventory in §2 as a starting point.
- Decide, route by route, which are "public API" (documented, stability-considered) vs.
  "internal-only" (used by the frontend, no external stability promise).
- Consider a dedicated API-token mechanism for non-interactive clients, separate from the OS account
  password - at minimum for read-only status routes, possibly tiered (read-only token vs. a token
  with destructive-action rights) for anything that reboots/uninstalls/resets.
- Establish the response-envelope convention as a written rule for future routes.

## 6. Open questions

- ~~Is external automation actually a goal here~~ **Answered (User, 2026-08-03)**: the direct
  INDI/curl approach used tonight is legitimate and justified for one-off live testing. The real
  question is narrower: exactly *what* can the API reliably be used for (e.g. "solve happened",
  "camera is running", "IMU works", "GPS has a fix"), and how much that can be trusted. Before this
  API can be used *consistently* as part of the PiFinder_Stellarmate development/testing workflow
  (not just ad-hoc), its correctness needs to be continuously verified - i.e. **a test suite for the
  Control Center API is a prerequisite**, not an optional nice-to-have alongside §5's other items.
  Only once that exists does "use the API as a standard dev/test tool" become something that can be
  stated with confidence. See #124.
- If a token mechanism is wanted: PAM-backed like today, a separate secrets file, or something else
  entirely?
- Scope: does this cover *all* 35+ routes, or just the Mount Bridge / PiFinder Mode subset that's
  actually been useful for testing so far?
