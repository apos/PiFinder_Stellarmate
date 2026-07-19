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


def _run_fake_mode_action(action):
    global _mode_action_running
    try:
        subprocess.run(["bash", str(FAKE_MODE_SCRIPT), action], timeout=120)
    except Exception:
        pass
    finally:
        with _lock:
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
            fake_up = _fake_mode_up()
            real_active = _real_service_active()
            if fake_up:
                mode = "fake"
            elif real_active:
                mode = "real"
            else:
                mode = "none"
            self._send_json({"mode": mode, "transitioning": transitioning})
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
