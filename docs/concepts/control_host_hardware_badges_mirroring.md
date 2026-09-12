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

### 2b. Genuine local hardware checks - need a real Control-Center-to-Control-Center proxy

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
  own security restriction, unrelated to PFSM. No `?host=` fix on this side can work around that -
  it always 403s for a remote caller, `host` param or not. Getting this value for a remote PiFinder
  needs the exact same thing as camera/imu: asking *that device's own* Control Center (where the
  request genuinely comes from 127.0.0.1), not this one. Frontend already treats "reachable but
  no orientation data" as a neutral grey "unavailable" rather than a self-contradicting green "?/?"
  (2026-09-12 fix), so this doesn't currently mislead - it's just not implemented yet.

Neither of these can be pointed at a remote IP the way a `host` parameter fixes a web-API proxy -
`rpicam-hello` and a local I2C scan are only ever meaningful on the machine that actually has the
hardware. To show the *remote* PiFinder's camera/IMU presence, the Control host's own Control
Center needs to ask **the remote device's own Control Center** (which already computes this
correctly for itself, via the exact same `/api/hardware_status` endpoint) - a genuine
Control-Center-to-Control-Center call, not a parameter tweak.

## 3. Design questions for 2b (not yet decided)

- **Which endpoint makes the call?** Proposed: `/api/hardware_status` itself grows an optional
  `host` parameter too, for consistency with 2a - but unlike 2a, when `host` is set it doesn't
  read local hardware at all, it does `GET http://{host}:8765/api/hardware_status` (the remote
  Control Center's own endpoint, not PiFinder's) and relays the result. Keeps the frontend's own
  call site identical for every badge (`?host=...` everywhere), even though the two categories
  work completely differently underneath.
- **Authentication.** The remote Control Center's `/api/hardware_status` is behind
  `_require_auth()` (HTTP Basic Auth against the stellarmate account's own password via PAM) -
  this proxy call needs credentials for a *different device*. Options to weigh: (a) assume the
  same stellarmate account password across every device in one PFSM fleet (plausible default,
  matches `_PIFINDER_REMOTE_PASSWORD`'s own "smate" convention for PiFinder's Remote page), (b)
  add a way to store/enter the remote CC's credentials once per Control host setup, (c) exempt
  this one read-only endpoint from auth when the request itself originates from another PFSM
  Control Center's own proxy call (harder to verify safely). No decision made here yet.
- **Remote Control Center might not be running/reachable at all** - the PiFinder device's own CC
  is only needed for its *own* first-time setup in the usual flow; nothing requires it to keep
  running afterward. The proxy call needs to fail soft (badge shows "unconfirmed"/grey, not an
  error) exactly like every other unreachable-PiFinder case already does.
- **Where does the remote CC's address come from?** Same value already known for the OLED/Quick-
  keys fixes (`wmLx200Remote`'s host part) - the *INDI* port (7624 by default) is unrelated to the
  Control Center's own port (8765), so this reuses only the hostname, not the full `host:port`
  string, same as the OLED fix already does.

## 4. Suggested order of work

1. ~~Ship 2a first (Solve + GPS `host` parameter) - mechanical, same pattern as #419, no open
   design questions, immediate value on its own.~~ Done (2026-09-12).
2. Decide the auth question for 2b before writing any of it - the rest of the design follows
   once that's settled, and it's the one genuinely new piece of infrastructure this needs.
3. 2b itself (Camera + IMU via CC-to-CC proxy) once 2 is answered.

2b (Camera/IMU) not implemented yet - concept only for that part, per direct request ("dann bitte
das Konzept erstellen"). The auth question in section 3 above is still open.
