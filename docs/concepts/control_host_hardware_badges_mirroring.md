# Concept: Control host mirroring the remote PiFinder's hardware/solve badges

## 1. Context

Found live 2026-09-12, testing a real split-host setup (a UTM as Control host, a Pi5 as the
PiFinder device, both pointed at the same mount). Two related gaps were found and already fixed
in the PiFinder tile's own OLED mirror and Quick keys (issues/PRs #417/#418/#419, see
basic-memory/pifinder-stellarmate/00151 for the recurring "hardcoded to 127.0.0.1" pattern behind
both): both only ever talked to `location.hostname`/`127.0.0.1`, with no way to reach a remote
PiFinder at all.

The same gap remains for the **Cam / Solve / IMU / GPS badges** (`#mode-ampel-row` in
`gui_installer/status_page.html`, backed by `/api/hardware_status` and the debug-solve endpoints
in `gui_installer/server.py`). Direct feedback: *"Ich würde jetzt erwarten, dass ich vom Control
Host aus alles sehe, was auf dem PiFinder geschieht: OLED, Drift, Badges usw."* Tracked as a
follow-up in issue #416; this concept works out the actual design before touching code, since -
unlike the OLED/Quick-keys fixes - the badges are **not all the same kind of problem**.

## 2. Two genuinely different categories, not one fix

Reading every backend function behind these badges (`gui_installer/server.py`) shows they split
into two categories that need different treatment:

### 2a. Already a thin proxy to PiFinder's own web API - same fix as #419 (done)

- **Solve badge** → `_pifinder_solve_status()` / `_pifinder_toggle_debug_solve()` - both just GET/
  POST to PiFinder's own `/api/status` / `/api/debug_solve`, wherever that PiFinder actually runs.
- **GPS badge** → `_gps_status_snapshot()` → `_pifinder_status_snapshot()` - same thing, reads
  PiFinder's own reported `location` from its `/api/status` (deliberately not re-implemented
  locally - "StellarMate/PiFinder already do this, we just want to see the result").

All three were hardcoded to `127.0.0.1:{port}`, exactly like `_pifinder_send_key()`/
`_pifinder_login()` were before #419. **Same fix applied directly**: each function grew an
optional `host` parameter (default `127.0.0.1`), validated at the route (`_valid_pifinder_host()`)
same as `/api/pifinder_key`; the frontend passes `pifinderHost()` (same
`new URL(pifinderScreenUrl).hostname` `pfSendKey()` already used) as `?host=` on every
`/api/debug_solve` call. GPS got its own new route, `/api/gps_status?host=...`, kept separate from
`/api/hardware_status` rather than adding `?host=` there - camera/imu (2b, below) must keep reading
THIS device's own local hardware regardless of `?host=`, so folding gps into that same response
would make the parameter look like it applies to all three when it only ever would for gps.

### 2b. Genuine local hardware checks - needed a real Control-Center-to-Control-Center proxy (done)

- **Camera badge** → `_camera_hardware_present()` - runs `rpicam-hello --list-cameras`, a raw
  libcamera call against *this machine's own* camera stack. Deliberately independent of
  PiFinder's own software (catches PiFinder's camera subprocess having silently crashed while the
  rest of the app keeps running) - see its own docstring.
- **IMU badge** → `_imu_hardware_present()` - a raw I2C scan (`_IMU_SCAN_SCRIPT`) against *this
  machine's own* I2C bus.
- **PiFinder orientation badge** (Mount Type / PiFinder Type, next to the Cam/Solve/IMU/GPS row) -
  found live (2026-09-12) testing 2a: this looked like the same kind of proxy as Solve/GPS
  (`_pifinder_solve_status()`'s own `/api/orientation_status` call), and got the same `host` fix -
  but PiFinder's own `server.py` (`~/PiFinder/python/PiFinder/server.py`) hardcodes
  `request.remote_addr not in ("127.0.0.1", "::1")` on that specific route (and two others) as its
  own security restriction, unrelated to PFSM. No `?host=` fix on this side could work around
  that - it always 403s for a remote caller, `host` param or not.
- **CPU/Temp** (`#system-load-line`) and **local PiFinder service status** (`#pifinder-status-line`)
  - not originally in scope for this doc (they're not badges), but direct feedback (2026-09-13,
  "auf dem CH brauche ich sowohl die lokalen als auch die remote Werte") extended the same need to
  them: both only ever described THIS device, easy to misread as describing the mirrored one.

None of these can be pointed at a remote IP the way a `host` parameter fixes a web-API proxy -
`rpicam-hello`, a local I2C scan, and `os.getloadavg()` are only ever meaningful on the machine
they actually run on. Fixed by asking **the remote device's own Control Center** (which already
computes each of these correctly for itself) instead of a parameter tweak.

## 3. Design questions for 2b (resolved 2026-09-13)

- **Which endpoint makes the call?** New shared `_cc_proxy_get(host, path, auth_header)` -
  `GET http://{host}:8765{path}` with `timeout=5`, returns the parsed JSON or `None` on any
  failure (fails soft, same as every other unreachable-remote case). Used by:
  - `/api/hardware_status?host=...` - when `host` is set, proxies the *whole* remote response
    (camera/imu/gps) instead of reading local hardware, exactly as originally proposed here. GPS
    still also has its own direct-to-PiFinder route (`/api/gps_status?host=`, category 2a) - kept,
    since it already worked and is one hop shorter; the two mechanisms happen to serve the same
    badge row.
  - `/api/system_load?host=...` - proxies to the remote CC's own `/api/system_load` when `host` is
    given, local `_system_load_status()` otherwise (unchanged default).
  - `_pifinder_solve_status()`'s orientation fetch - when `host` isn't `127.0.0.1`/`::1` (PiFinder's
    own restriction, see 2b above), proxies through the remote CC's own `/api/debug_solve?port=N`
    instead of hitting PiFinder's `/api/orientation_status` directly - the remote CC's own call to
    that route genuinely originates from `127.0.0.1` on *its* side, sidestepping the 403 entirely.
- **Authentication - decided: assume the same stellarmate account password across every device in
  one PFSM fleet** (option (a) from the original list here, matching `_PIFINDER_REMOTE_PASSWORD`'s
  own "smate" convention). Implementation needs no credential storage at all: `_require_auth()`
  only ever checks the *password* half of Basic Auth, never the username (see its own comment) -
  so `_cc_proxy_get()` simply forwards the incoming request's own `Authorization` header verbatim
  to the remote CC, which authenticates it the same way its own browser client would.
- **Remote Control Center might not be running/reachable at all** - handled: every proxied route
  falls back to `None`/an all-null shape on any `_cc_proxy_get()` failure, and the frontend renders
  that as a neutral "unavailable (remote Control Center not reachable)" rather than a false
  positive/negative.
- **Where does the remote CC's address come from?** `pifinderHost()` (same
  `new URL(pifinderScreenUrl).hostname` `pfSendKey()`/2a already use) - reused unchanged, gated on
  `isControlHostRole()` for the CC-to-CC calls specifically (unlike the direct-to-PiFinder 2a
  calls, pointing `?host=` at this device's own address here would mean a pointless self-proxy).

## 4. Status

1. ~~Ship 2a (Solve + GPS `host` parameter).~~ Done (2026-09-12).
2. ~~Decide the auth question for 2b.~~ Done (2026-09-13) - same-password assumption, header
   forwarding.
3. ~~2b itself (Camera/IMU/orientation via CC-to-CC proxy, plus CPU/Temp and local PiFinder status
   once the need was raised).~~ Done (2026-09-13).

Everything in this doc is implemented. Still open, not part of this doc: the Test Hardware
button's own *functional* camera/IMU test (an actual `rpicam-hello` capture / I2C read, not just
presence) stays local-only - proxying an on-demand test run to a remote device is a bigger feature
than mirroring a passive status read, not attempted here.
