#!/usr/bin/env bash
# Idempotent launcher for the PiFinder Setup GUI: starts gui_installer/server.py
# in the background if it isn't already listening, prints the URLs it's
# reachable under, then opens the status page in a browser.
#
# Usage:
#   ./launch_setup_gui.sh                     - starts it (if needed) and opens the browser
#   ./launch_setup_gui.sh --shutdown-webserver - stops an already-running webserver

set -u

PORT=8765
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Pull the latest PiFinder_Stellarmate before anything else runs - see
# bin/self_update.sh for the safety model (skips cleanly during active
# development, aborts loudly on a real failure instead of continuing on an
# uncertain checkout).
source "${REPO_DIR}/bin/self_update.sh"
self_update_pifinder_stellarmate "$REPO_DIR" "$@"

_state_json() {
    curl -s -m 2 "http://localhost:${PORT}/state" 2>/dev/null
}

_print_urls() {
    local state="$1"
    python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
port = data.get('port', sys.argv[2])
ips = data.get('ips') or []
if not ips:
    ips = ['localhost']
print('   Setup GUI reachable at:')
for ip in ips:
    print(f'     http://{ip}:{port}/')
" "$state" "$PORT"
    echo "   Login: any username, password = your stellarmate system password"
    echo "   (protects the page itself plus Reinstall/Update/Reboot; /state,"
    echo "   /log and /shutdown stay reachable without login)"
}

# Managed via systemd (pifinder-control-center.service) rather than a plain
# background process, so "was it running before the last shutdown/reboot?"
# persists automatically across reboots via systemd's own enabled-state -
# see the unit's own header comment. server.py's own /shutdown handler
# disables the unit as part of shutting itself down; starting here enables
# it. Both still go through the HTTP routes (not `systemctl start/stop`
# directly) so /shutdown's "refuse while a run is in progress" safety check
# still applies.
if [ "${1:-}" = "--shutdown-webserver" ]; then
    state="$(_state_json)"
    if [ -z "$state" ]; then
        echo "Setup GUI webserver isn't running (nothing to stop)."
        sudo systemctl disable pifinder-control-center.service 2>/dev/null || true
        exit 0
    fi
    curl -s -X POST -m 2 "http://localhost:${PORT}/shutdown" -o /dev/null
    echo "Stopping setup GUI webserver..."
    for _ in $(seq 1 20); do
        if [ -z "$(_state_json)" ]; then
            echo "Webserver stopped."
            exit 0
        fi
        sleep 0.25
    done
    echo "!! Webserver still responding after 5s - a setup run may be in progress (shutdown is refused while it is)."
    exit 1
fi

existing_state="$(_state_json)"
if [ -n "$existing_state" ]; then
    echo "Setup GUI webserver is already running."
    _print_urls "$existing_state"
else
    echo "Starting setup GUI webserver..."
    sudo systemctl enable --now pifinder-control-center.service
    state=""
    for _ in $(seq 1 20); do
        state="$(_state_json)"
        [ -n "$state" ] && break
        sleep 0.25
    done
    if [ -n "$state" ]; then
        echo "Webserver started."
        _print_urls "$state"
    else
        echo "!! Webserver not responding after 5s - see: journalctl -u pifinder-control-center -n 50"
        exit 1
    fi
fi

echo "   To stop: $0 --shutdown-webserver"

xdg-open "http://localhost:${PORT}/" >/dev/null 2>&1 &
