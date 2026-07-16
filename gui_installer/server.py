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

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8765
GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
SETUP_SCRIPT = REPO_ROOT / "pifinder_stellarmate_setup.sh"
PIFINDER_DIR = Path.home() / "PiFinder"
PIFINDER_IMAGE = REPO_ROOT / "docs" / "images" / "readme" / "PiFinder.jpg"
AVVP_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "avvp_2019_logo_wortmarke_neg.png"
HEYAPOS_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "HeyApos_Wortmarke_logo.png"
LOG_FILE = REPO_ROOT / ".gui_setup.log"
STATUS_PAGE = GUI_DIR / "status_page.html"

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
    global _running, _exit_code, _process, _lines, _phase_index, _reboot_needed
    with _lock:
        if _running:
            return False, "A run is already in progress."
        _lines = []
        _running = True
        _exit_code = None
        _phase_index = -1
        _reboot_needed = None
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; the browser is the UI

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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

        if parsed.path == "/":
            body = STATUS_PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
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

        if parsed.path == "/state":
            with _lock:
                running = _running
                exit_code = _exit_code
                phase_index = _phase_index
                reboot_needed = _reboot_needed
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
                }
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
                }
            )
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
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

        self.send_error(404)


def main():
    # 0.0.0.0: reachable from other devices on the LAN, not just this Pi.
    # There is no login on this server and it can trigger destructive actions
    # (delete + reinstall, sudo reboot) - anyone on the same network can reach
    # it. Acceptable on a private home/observatory LAN; do not expose this
    # port beyond that.
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PiFinder setup GUI listening on http://0.0.0.0:{PORT}/ (all interfaces)")
    server.serve_forever()


if __name__ == "__main__":
    main()
