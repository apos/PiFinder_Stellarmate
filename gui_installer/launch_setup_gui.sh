#!/usr/bin/env bash
# Idempotent launcher for the PiFinder Setup GUI: starts gui_installer/server.py
# in the background if it isn't already listening, prints the URLs it's
# reachable under, then opens the status page in a browser.
#
# Verwendung:
#   ./launch_setup_gui.sh                     - startet (falls noetig) und oeffnet den Browser
#   ./launch_setup_gui.sh --shutdown-webserver - stoppt einen laufenden Webserver wieder

set -u

PORT=8765
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
print('   Setup-GUI erreichbar unter:')
for ip in ips:
    print(f'     http://{ip}:{port}/')
" "$state" "$PORT"
    echo "   Login: Benutzername egal, Passwort = dein stellarmate-Systempasswort"
    echo "   (schuetzt die Seite selbst sowie Reinstall/Update/Reboot; /state,"
    echo "   /log und /shutdown bleiben ohne Login erreichbar)"
}

if [ "${1:-}" = "--shutdown-webserver" ]; then
    state="$(_state_json)"
    if [ -z "$state" ]; then
        echo "Setup-GUI-Webserver läuft nicht (nichts zu beenden)."
        exit 0
    fi
    curl -s -X POST -m 2 "http://localhost:${PORT}/shutdown" -o /dev/null
    echo "Setup-GUI-Webserver wird beendet..."
    for _ in $(seq 1 20); do
        if [ -z "$(_state_json)" ]; then
            echo "Webserver gestoppt."
            exit 0
        fi
        sleep 0.25
    done
    echo "!! Webserver antwortet nach 5s noch - laeuft evtl. gerade ein Setup (Shutdown wird dann abgelehnt)."
    exit 1
fi

existing_state="$(_state_json)"
if [ -n "$existing_state" ]; then
    echo "Setup-GUI-Webserver läuft bereits."
    _print_urls "$existing_state"
else
    echo "Starte Setup-GUI-Webserver..."
    nohup python3 "${SCRIPT_DIR}/server.py" >/tmp/pifinder_gui_installer.log 2>&1 &
    state=""
    for _ in $(seq 1 20); do
        state="$(_state_json)"
        [ -n "$state" ] && break
        sleep 0.25
    done
    if [ -n "$state" ]; then
        echo "Webserver gestartet."
        _print_urls "$state"
    else
        echo "!! Webserver antwortet nach 5s nicht - siehe /tmp/pifinder_gui_installer.log"
        exit 1
    fi
fi

echo "   Zum Beenden: $0 --shutdown-webserver"

xdg-open "http://localhost:${PORT}/" >/dev/null 2>&1 &
