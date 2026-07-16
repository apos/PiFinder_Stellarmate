#!/usr/bin/env bash
# Idempotent launcher for the PiFinder Setup GUI: starts gui_installer/server.py
# in the background if it isn't already listening, then opens the status page.

set -u

PORT=8765
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! curl -s -o /dev/null -m 1 "http://localhost:${PORT}/state"; then
    nohup python3 "${SCRIPT_DIR}/server.py" >/tmp/pifinder_gui_installer.log 2>&1 &
    for _ in $(seq 1 20); do
        curl -s -o /dev/null -m 1 "http://localhost:${PORT}/state" && break
        sleep 0.25
    done
fi

xdg-open "http://localhost:${PORT}/" >/dev/null 2>&1 &
