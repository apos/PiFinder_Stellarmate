#!/usr/bin/env python3
"""Post-SMOS-update guard (survives a SMOS root reset because it lives in /home).

A SMOS update resets the root filesystem: the Control Center service and the
INDI drivers are gone, so the Control Center cannot show its own "SMOS was
updated" notice. This runs as a *user* unit (~/.config/systemd/user, see
pi_config_files/pifinder-smos-update-guard.service) and only acts when ALL of:

  - the SMOS version changed since the last completed setup/restore
    (.smos_version_restored vs /etc/stellarmate/version),
  - the Control Center unit no longer exists (a still-installed Control
    Center shows the same notice itself and starts on its own),
  - nothing is listening on the Control Center port.

Then it serves a one-screen notice with a button that runs
bin/restore_after_smos_update.sh (which re-installs the Control Center), after
which the regular Control Center takes over the same port.
"""
import base64
import getpass
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "gui_installer"))

PORT = 8777
AUTH_USER = "stellarmate"
RECORD_FILE = REPO / ".smos_version_restored"
VERSION_FILE = Path("/etc/stellarmate/version")
CC_UNIT_FILE = Path("/etc/systemd/system/pifinder-control-center.service")
RESTORE_SCRIPT = REPO / "bin" / "restore_after_smos_update.sh"
LOG_FILE = Path.home() / ".cache" / "pifinder_stellarmate" / "smos_restore.log"


def _read_version(path: Path):
    try:
        v = path.read_text().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    return v or None


def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def pending_versions():
    """(current, recorded) when a restore is pending, else None."""
    current = _read_version(VERSION_FILE)
    recorded = _read_version(RECORD_FILE)
    if not current or not recorded or current == recorded:
        return None
    return current, recorded


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PFSM - SMOS updated</title>
<style>
 body{background:#111;color:#ddd;font:16px/1.5 system-ui,sans-serif;margin:0;padding:2rem;max-width:42rem}
 .card{border:1px solid #b8860b;background:#2a2308;border-radius:8px;padding:1rem 1.25rem}
 h1{color:#ffc107;font-size:1.15rem;margin:.1rem 0 .6rem}
 button{background:#b8860b;color:#fff;border:0;border-radius:6px;padding:.6rem 1rem;font-size:1rem;cursor:pointer}
 button:disabled{opacity:.5;cursor:default} input{padding:.5rem;border-radius:6px;border:1px solid #555;background:#222;color:#eee}
 #msg{margin-top:.8rem;color:#ffd666} .hint{font-size:.85rem;color:#c9b27a}
</style>
<div class="card">
 <h1>&#9888; SMOS was updated (%(recorded)s &rarr; %(current)s)</h1>
 <p>The system update reset the root filesystem, which removed the PiFinder Control Center,
 the INDI drivers and related system setup. Run the post-update restore to put them back
 (takes a few minutes; this page switches to the Control Center when it is done).</p>
 <p><input id="pw" type="password" placeholder="stellarmate password" autocomplete="off">
 <button id="go">Run post-update restore</button></p>
 <p class="hint">The system password of the <b>stellarmate</b> user on this device (StellarMate OS default: <code>smate</code>).</p>
 <div id="msg"></div>
</div>
<script>
const msg=document.getElementById('msg'), go=document.getElementById('go');
go.onclick=async()=>{
  const pw=document.getElementById('pw').value;
  if(!pw){msg.textContent='Enter the stellarmate system password first.'; return;}
  go.disabled=true; msg.textContent='Starting...';
  const r=await fetch('/restore',{method:'POST',headers:{'Authorization':'Basic '+btoa('stellarmate:'+pw)}});
  if(!r.ok){go.disabled=false; msg.textContent=r.status===401?'That password was not accepted - use the stellarmate system password.':'Could not start: '+r.status; return;}
  msg.textContent='Restore running - the Control Center will appear here when it is finished...';
  const t=setInterval(async()=>{
    try{const s=await (await fetch('/state',{cache:'no-store'})).json();
        if(!s.smos_guard){clearInterval(t); location.reload();}}catch(e){}
  },3000);
};
</script>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "pfsm-smos-guard"

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        info = pending_versions()
        cur, rec = info if info else ("?", "?")
        if self.path.split("?")[0] == "/state":
            self._send(json.dumps({"smos_guard": True, "smos_current": cur, "smos_recorded": rec}).encode(),
                       "application/json")
        else:
            self._send((PAGE % {"current": cur, "recorded": rec}).encode(), "text/html; charset=utf-8")

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            password = base64.b64decode(header[6:]).decode().split(":", 1)[1]
        except Exception:
            return False
        import pam_auth
        return pam_auth.verify_password(AUTH_USER, password)

    def do_POST(self):
        if self.path.split("?")[0] != "/restore":
            self._send(b"{}", "application/json", 404)
            return
        if not self._authorized():
            self._send(b'{"started": false, "error": "unauthorized"}', "application/json", 401)
            return
        self._send(b'{"started": true}', "application/json")
        self.server.restore_requested = True
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def main() -> int:
    if pending_versions() is None:
        return 0
    if CC_UNIT_FILE.exists() or _port_in_use(PORT):
        return 0
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.restore_requested = False
    print(f"SMOS update guard: serving restore notice on :{PORT}", flush=True)
    httpd.serve_forever()
    httpd.server_close()
    if not httpd.restore_requested:
        return 0
    # Port must be free before the restore starts the Control Center again.
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, USER=getpass.getuser(), HOME=str(Path.home()))
    with open(LOG_FILE, "ab") as log:
        return subprocess.run(["bash", str(RESTORE_SCRIPT)], cwd=str(REPO), env=env,
                              stdout=log, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    sys.exit(main())
