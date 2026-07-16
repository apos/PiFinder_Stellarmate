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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8765
GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
SETUP_SCRIPT = REPO_ROOT / "pifinder_stellarmate_setup.sh"
PIFINDER_DIR = Path.home() / "PiFinder"
LOG_FILE = REPO_ROOT / ".gui_setup.log"
STATUS_PAGE = GUI_DIR / "status_page.html"

_lock = threading.Lock()
_lines = []
_running = False
_exit_code = None
_process = None


def _reader_thread(proc):
    global _running, _exit_code
    with open(LOG_FILE, "w") as log_f:
        for line in iter(proc.stdout.readline, ""):
            with _lock:
                _lines.append(line.rstrip("\n"))
            log_f.write(line)
            log_f.flush()
    proc.wait()
    with _lock:
        _running = False
        _exit_code = proc.returncode


def _start_run(action):
    global _running, _exit_code, _process, _lines
    with _lock:
        if _running:
            return False, "A run is already in progress."
        _lines = []
        _running = True
        _exit_code = None
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

        if parsed.path == "/state":
            with _lock:
                running = _running
                exit_code = _exit_code
            self._send_json(
                {
                    "existing_install": PIFINDER_DIR.is_dir(),
                    "running": running,
                    "exit_code": exit_code,
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
            self._send_json(
                {
                    "lines": new_lines,
                    "position": new_position,
                    "running": running,
                    "exit_code": exit_code,
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
        self.send_error(404)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PiFinder setup GUI listening on http://localhost:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
