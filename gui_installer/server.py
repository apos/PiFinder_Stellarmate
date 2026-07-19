#!/usr/bin/env python3
"""
Local web GUI for pifinder_stellarmate_setup.sh: shows live install progress
in a browser instead of a bare terminal, and drives the script's
--action=reinstall|update|cancel flag so no one has to sit at a keyboard
answering prompts (including the venv-bootstrap two-pass restart).

Stdlib only (http.server + subprocess) on purpose: this tool's job is to run
pifinder_stellarmate_setup.sh, which is what creates the PiFinder venv and
installs its pip requirements in the first place — it must work with nothing
but the bare system python3.
"""

import base64
import json
import re
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pam_auth

PORT = 8765
# Same account + mechanism PiFinder's own Remote login checks
# (sys_utils.verify_password("stellarmate", password)) - one password to
# remember for both. Only the page and state-changing actions require it;
# /state and /log stay open so PiFinder's INDI Drivers page can cross-origin
# poll status and show "Setup Wizard is running" without a login prompt.
AUTH_USER = "stellarmate"
AUTH_REALM = "PiFinder Setup"
GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
SETUP_SCRIPT = REPO_ROOT / "pifinder_stellarmate_setup.sh"
PIFINDER_DIR = Path.home() / "PiFinder"
PIFINDER_VENV_PY = PIFINDER_DIR / "python" / ".venv" / "bin" / "python3"
GPSD_PORT = 2947
PIFINDER_IMAGE = REPO_ROOT / "docs" / "images" / "readme" / "PiFinder.jpg"
AVVP_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "avvp_2019_logo_wortmarke_neg.png"
HEYAPOS_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "HeyApos_Wortmarke_logo.png"
# PiFinder's own splash bitmap (shown by pifinder_splash.service before the
# main app is up) - only exists once PiFinder has actually been installed.
PIFINDER_WELCOME_IMAGE = PIFINDER_DIR / "images" / "welcome.png"
LOG_FILE = REPO_ROOT / ".gui_setup.log"
STATUS_PAGE = GUI_DIR / "status_page.html"
# Deliberately decoupled from PiFinder's own web server/codebase: this just
# shells out to test_tools/fake_mode.sh (see its own header comment for the
# full rationale), which itself toggles between the real systemd service and
# a fake-hardware instance via the pifinder-remote skill's pf_remote.py.
FAKE_MODE_SCRIPT = REPO_ROOT / "test_tools" / "fake_mode.sh"
FAKE_MODE_PORT = 8081

# Must match the phase() call sites (and their order) in pifinder_stellarmate_setup.sh.
PHASES = [
    "Checking versions",
    "Setting up hardware access",
    "Cloning or updating PiFinder",
    "Installing system packages",
    "Creating Python venv",
    "Installing Python requirements",
    "Downloading star catalog",
    "Configuring hardware & services",
    "Building INDI drivers",
    "Setup complete",
]
PHASE_MARKER = "###PHASE### "
REBOOT_MARKER = "###REBOOT_NEEDED### "

_lock = threading.Lock()
_lines = []
_running = False
_exit_code = None
_process = None
_phase_index = -1  # furthest phase reached so far, -1 = none yet
_reboot_needed = None  # None = unknown yet, True/False once the run reports it
_last_action = None  # "fresh" | "reinstall" | "update" | "cancel" - lets the
# frontend tell a genuine successful install apart from a no-op Cancel run,
# both of which exit 0.

_mode_action_running = False  # True while fake_mode.sh start/stop is in flight
_mode_lines = []  # fake_mode.sh's own stdout/stderr, shown in the shared Terminal tile
_mode_exit_code = None
_mode_error = None  # short human reason the last mode switch failed, None if last one succeeded
_mode_target = None  # "fake" | "real" - which mode the in-flight/last switch was aiming for

# How long to wait, after fake_mode.sh itself exits, for the target mode to
# actually be reachable. `systemctl start` (and `pf_remote.py launch`) return
# as soon as the process is spawned, not once it's actually up - trusting
# that exit code alone would report "success" even when the target crashes
# a moment later (e.g. the real service with no HAT attached). Settle-check
# instead of trusting the exit code.
_MODE_SETTLE_TIMEOUT = 8
_MODE_SETTLE_INTERVAL = 1


def _fake_mode_up() -> bool:
    """Whether the fake-hardware PiFinder instance is currently answering."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{FAKE_MODE_PORT}/api/status", timeout=2)
        return True
    except Exception:
        return False


def _real_service_active() -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", "pifinder.service"]
    ).returncode == 0


def _real_service_failed() -> bool:
    return subprocess.run(
        ["systemctl", "is-failed", "--quiet", "pifinder.service"]
    ).returncode == 0


def _camera_hardware_present():
    """True/False if rpicam-hello can tell us whether a camera is physically
    attached, None if that tool isn't available (inconclusive either way).

    Deliberately independent of PiFinder's own process/software: a real-mode
    switch can settle as "systemd active" even with no camera at all (the
    camera subprocess crashes but the rest of the app - web server, GPS, IMU -
    keeps running, a known upstream issue - see
    basic-memory/pifinder-stellarmate/00001, "Test Mode kann abgestürzten
    Kamera-Prozess nicht retten"). Checking the raw hardware directly, the
    same way test_tools/keypad_gpio_matrix_test.py checks the keypad below
    PiFinder's own software layer, is the only way to catch that case.
    """
    try:
        result = subprocess.run(
            ["rpicam-hello", "--list-cameras"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    return "No cameras available" not in result.stdout


# BNO055 (the IMU PiFinder uses) answers on I2C address 0x28, or 0x29 if its
# ADR pin is pulled high.
_BNO055_I2C_ADDRESSES = ("0x28", "0x29")

_IMU_SCAN_SCRIPT = (
    "import board\n"
    "i2c = board.I2C()\n"
    "if not i2c.try_lock():\n"
    "    print('LOCK_FAILED')\n"
    "else:\n"
    "    try:\n"
    "        print(','.join(hex(a) for a in i2c.scan()))\n"
    "    finally:\n"
    "        i2c.unlock()\n"
)


def _imu_hardware_present():
    """True/False via a raw I2C bus scan for the IMU's address, None if the
    check itself couldn't run (no venv, board/blinka missing, bus busy).

    Runs through PiFinder's own venv (board.I2C()/adafruit_bno055 aren't
    installed system-wide) so bus resolution matches whatever PiFinder itself
    would use on this particular Pi - but the scan itself is independent of
    whether PiFinder is currently running: I2C bus scanning is a shared,
    non-exclusive operation (unlike the keypad's GPIO lines), so this is safe
    to run alongside a live pifinder.service.
    """
    if not PIFINDER_VENV_PY.exists():
        return None
    try:
        result = subprocess.run(
            [str(PIFINDER_VENV_PY), "-c", _IMU_SCAN_SCRIPT],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0 or "LOCK_FAILED" in result.stdout:
        return None
    return any(addr in result.stdout for addr in _BNO055_I2C_ADDRESSES)


def _gps_hardware_present():
    """True/False via a direct query to gpsd's own DEVICES report, None if
    gpsd itself couldn't be reached.

    gpsd is a shared daemon designed for concurrent clients, so this is safe
    to run alongside PiFinder's own gpsd connection - and it reports whatever
    serial/USB GPS receiver gpsd has actually opened, independent of whether
    a fix has been acquired yet (a "not locked" GPS is still present hardware,
    unlike a genuinely absent one).
    """
    try:
        s = socket.create_connection(("127.0.0.1", GPSD_PORT), timeout=2)
        s.settimeout(2)
        s.recv(4096)  # version banner
        s.sendall(b'?WATCH={"enable":true}\n')
        data = b""
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and b'"class":"DEVICES"' not in data:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
    except Exception:
        return None
    m = re.search(rb'"class":"DEVICES","devices":(\[.*?\])', data)
    if not m:
        return None
    try:
        return len(json.loads(m.group(1))) > 0
    except Exception:
        return None


def _run_fake_mode_action(action):
    global _mode_action_running, _mode_lines, _mode_exit_code, _mode_error, _mode_target
    target = "fake" if action == "start" else "real"
    with _lock:
        _mode_lines = []
        _mode_exit_code = None
        _mode_error = None
        _mode_target = target
    try:
        proc = subprocess.Popen(
            ["bash", str(FAKE_MODE_SCRIPT), action],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            with _lock:
                _mode_lines.append(line.rstrip("\n"))
        proc.wait(timeout=120)
        with _lock:
            _mode_exit_code = proc.returncode
    except Exception as e:
        with _lock:
            _mode_lines.append(f"[setup GUI] failed to run {FAKE_MODE_SCRIPT.name}: {e}")
            _mode_exit_code = -1

    with _lock:
        script_failed = _mode_exit_code not in (0, None)

    ok = False
    cam_present = None
    imu_present = None
    if not script_failed:
        # The subprocess exiting 0 isn't the same as the target actually
        # being up - settle-check the real, observable state before
        # declaring success.
        deadline = time.monotonic() + _MODE_SETTLE_TIMEOUT
        while time.monotonic() < deadline:
            if target == "fake":
                ok = _fake_mode_up()
            else:
                ok = _real_service_active() and not _real_service_failed()
            if ok:
                break
            time.sleep(_MODE_SETTLE_INTERVAL)

        if ok and target == "real":
            # systemd can report "active" with no camera/IMU attached at all
            # (see _camera_hardware_present() docstring) - a raw hardware
            # check is the only reliable way to catch that specific case. A
            # real instance without either isn't functional, so a switch
            # attempt should fail rather than report success.
            cam_present = _camera_hardware_present()
            imu_present = _imu_hardware_present()
            if cam_present is False or imu_present is False:
                ok = False

    with _lock:
        if ok:
            _mode_error = None
        else:
            if target == "real":
                missing = []
                if cam_present is False:
                    missing.append("camera")
                if imu_present is False:
                    missing.append("IMU")
                if missing:
                    _mode_error = (f"No PiFinder {' and '.join(missing)} hardware detected - "
                                   "reconnect the HAT, then try again, or use 'Back to Test Mode' below.")
                else:
                    _mode_error = "Real Mode failed to start - see Terminal below."
                _mode_lines.append("")
                _mode_lines.append("--- pifinder.service journal (last 40 lines) ---")
                journal = subprocess.run(
                    ["journalctl", "-u", "pifinder.service", "-n", "40", "--no-pager", "--output=cat"],
                    capture_output=True, text=True,
                ).stdout
                _mode_lines.extend(journal.splitlines())
            else:
                _mode_error = "Test Mode failed to start - see Terminal below."
        _mode_action_running = False


def _get_all_ips():
    """Every non-loopback IPv4 address on this machine, for the remote-access links."""
    try:
        output = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except Exception:
        return []
    ips = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[1] == "lo":
            continue
        ips.append(fields[3].split("/")[0])
    return ips


def _reader_thread(proc):
    global _running, _exit_code, _phase_index, _reboot_needed
    with open(LOG_FILE, "w") as log_f:
        for line in iter(proc.stdout.readline, ""):
            log_f.write(line)
            log_f.flush()
            stripped = line.rstrip("\n")
            if stripped.startswith(PHASE_MARKER):
                label = stripped[len(PHASE_MARKER):]
                if label in PHASES:
                    with _lock:
                        _phase_index = max(_phase_index, PHASES.index(label))
                continue  # phase markers are for the progress bar, not the log panel
            if stripped.startswith(REBOOT_MARKER):
                with _lock:
                    _reboot_needed = stripped[len(REBOOT_MARKER):] == "true"
                continue  # marker is for the Reboot button, not the log panel
            with _lock:
                _lines.append(stripped)
    proc.wait()
    with _lock:
        _running = False
        _exit_code = proc.returncode


def _start_run(action):
    global _running, _exit_code, _process, _lines, _phase_index, _reboot_needed, _last_action
    with _lock:
        if _running:
            return False, "A run is already in progress."
        if _mode_action_running:
            return False, "A PiFinder mode switch is still in progress - wait for it to finish first."
        _lines = []
        _running = True
        _exit_code = None
        _phase_index = -1
        _reboot_needed = None
        _last_action = action
        cmd = ["bash", str(SETUP_SCRIPT), f"--action={action}"]
        _process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=_reader_thread, args=(_process,), daemon=True).start()
    return True, None


def _do_reboot():
    time.sleep(1)  # give the HTTP response a moment to reach the browser
    subprocess.run(["sudo", "reboot"])


_server = None  # set in main(); used by /shutdown to stop serve_forever()


def _do_shutdown():
    time.sleep(1)  # give the HTTP response a moment to reach the browser
    if _server is not None:
        _server.shutdown()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; the browser is the UI

    def _require_auth(self):
        """Checks HTTP Basic Auth against the stellarmate account's own
        password via PAM. Sends the 401 challenge itself and returns False
        if missing/invalid; caller should return immediately in that case."""
        header = self.headers.get("Authorization", "")
        password = None
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
                _, _, password = decoded.partition(":")
            except Exception:
                password = None
        if password and pam_auth.verify_password(AUTH_USER, password):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{AUTH_REALM}"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # /state and /log (the only _send_json callers reachable without
        # auth, see _require_auth()) are meant to be freely reachable on the
        # LAN - CORS headers don't change that, they just let PiFinder's own
        # "INDI Drivers" page (served from a different port, hence a
        # different origin) read the response via fetch().
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path not in ("/state", "/log") and not self._require_auth():
            return

        if parsed.path == "/":
            body = STATUS_PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # This page's JS/HTML has changed repeatedly across sessions -
            # a browser caching a stale copy after an update makes fixed
            # bugs look like they're still there (e.g. a renamed route the
            # cached JS still links to). Never worth caching for a page
            # that's only open during an active install/update anyway.
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/pifinder.jpg":
            self._send_file(PIFINDER_IMAGE, "image/jpeg")
            return

        if parsed.path == "/avvp_logo.png":
            self._send_file(AVVP_LOGO, "image/png")
            return

        if parsed.path == "/heyapos_logo.png":
            self._send_file(HEYAPOS_LOGO, "image/png")
            return

        if parsed.path == "/pifinder_welcome.png":
            self._send_file(PIFINDER_WELCOME_IMAGE, "image/png")
            return

        if parsed.path == "/state":
            with _lock:
                running = _running
                exit_code = _exit_code
                phase_index = _phase_index
                reboot_needed = _reboot_needed
                last_action = _last_action
            self._send_json(
                {
                    "existing_install": PIFINDER_DIR.is_dir(),
                    "running": running,
                    "exit_code": exit_code,
                    "phase_index": phase_index,
                    "phase_total": len(PHASES),
                    "phase_label": PHASES[phase_index] if phase_index >= 0 else None,
                    "phases": PHASES,
                    "setup_script_path": str(SETUP_SCRIPT),
                    "ips": _get_all_ips(),
                    "port": PORT,
                    "reboot_needed": reboot_needed,
                    "action": last_action,
                }
            )
            return

        if parsed.path == "/api/pifinder_mode":
            with _lock:
                transitioning = _mode_action_running
                error = _mode_error
                target = _mode_target
            fake_up = _fake_mode_up()
            real_active = _real_service_active()
            if fake_up:
                mode = "fake"
            elif real_active:
                mode = "real"
            else:
                mode = "none"
            self._send_json(
                {"mode": mode, "transitioning": transitioning, "error": error, "target": target}
            )
            return

        if parsed.path == "/api/hardware_status":
            self._send_json(
                {
                    "camera": _camera_hardware_present(),
                    "imu": _imu_hardware_present(),
                    "gps": _gps_hardware_present(),
                }
            )
            return

        if parsed.path == "/api/pifinder_mode_log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _mode_lines[position:]
                new_position = len(_mode_lines)
                running = _mode_action_running
                exit_code = _mode_exit_code
            self._send_json(
                {"lines": new_lines, "position": new_position, "running": running, "exit_code": exit_code}
            )
            return

        if parsed.path == "/log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _lines[position:]
                new_position = len(_lines)
                running = _running
                exit_code = _exit_code
                phase_index = _phase_index
                reboot_needed = _reboot_needed
                last_action = _last_action
            self._send_json(
                {
                    "lines": new_lines,
                    "position": new_position,
                    "running": running,
                    "exit_code": exit_code,
                    "phase_index": phase_index,
                    "phase_total": len(PHASES),
                    "phase_label": PHASES[phase_index] if phase_index >= 0 else None,
                    "reboot_needed": reboot_needed,
                    "action": last_action,
                }
            )
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        # /shutdown stays open: PiFinder's INDI Drivers page (a different
        # origin/port) cross-origin-POSTs here to stop the installer, and
        # cross-origin requests never carry this page's cached Basic Auth
        # credentials. Shutting the installer down isn't destructive, unlike
        # /start and /reboot below, which do require auth.
        if parsed.path != "/shutdown" and not self._require_auth():
            return

        if parsed.path == "/start":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            if action not in ("fresh", "reinstall", "update", "cancel"):
                self._send_json({"started": False, "error": f"invalid action '{action}'"}, status=400)
                return
            started, error = _start_run(action)
            self._send_json({"started": started, "error": error})
            return

        if parsed.path == "/reboot":
            with _lock:
                if _running:
                    self._send_json({"rebooting": False, "error": "A run is still in progress."}, status=409)
                    return
            self._send_json({"rebooting": True})
            threading.Thread(target=_do_reboot, daemon=True).start()
            return

        if parsed.path == "/shutdown":
            with _lock:
                if _running:
                    self._send_json({"shutting_down": False, "error": "A run is still in progress."}, status=409)
                    return
            self._send_json({"shutting_down": True})
            threading.Thread(target=_do_shutdown, daemon=True).start()
            return

        if parsed.path == "/api/pifinder_mode":
            global _mode_action_running
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            if action not in ("enable_fake", "disable_fake"):
                self._send_json({"started": False, "error": f"invalid action '{action}'"}, status=400)
                return
            with _lock:
                if _mode_action_running:
                    self._send_json({"started": False, "error": "A mode switch is already in progress."}, status=409)
                    return
                if _running:
                    self._send_json({"started": False, "error": "An install/update run is in progress - wait for it to finish first."}, status=409)
                    return
                _mode_action_running = True
            script_arg = "start" if action == "enable_fake" else "stop"
            threading.Thread(target=_run_fake_mode_action, args=(script_arg,), daemon=True).start()
            self._send_json({"started": True})
            return

        self.send_error(404)


def main():
    # 0.0.0.0: reachable from other devices on the LAN, not just this Pi.
    # The page itself and the destructive actions (delete + reinstall, sudo
    # reboot) require the stellarmate account's own password (see
    # _require_auth()); /state, /log, /shutdown stay open (see their own
    # comments). Do not expose this port beyond a private home/observatory
    # LAN regardless.
    global _server
    _server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PiFinder setup GUI listening on http://0.0.0.0:{PORT}/ (all interfaces)")
    _server.serve_forever()


if __name__ == "__main__":
    main()
