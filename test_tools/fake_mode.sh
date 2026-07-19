#!/usr/bin/env bash
# Toggle PiFinder between its real systemd service (real camera/keyboard/
# display hardware) and a "fake hardware" development instance (camera debug,
# keyboard none, display headless). Useful whenever the physical HAT is
# disconnected/being worked on but you still want PiFinder's normal web UI up
# for development or testing - run this over SSH, no desktop session needed.
#
# Under the hood this is a thin wrapper around the pifinder-remote Claude
# Code skill's pf_remote.py (lives in the PiFinder checkout, not here) - it
# already solves starting/stopping a headless PiFinder instance cleanly
# (correct process-group handling, graceful-then-forced shutdown), so this
# script just drives that plus the real systemd service around it. It's a
# normal PiFinder process either way - use it from a browser like any other
# PiFinder instance, not just via pf_remote.py.
#
# Usage:
#   test_tools/fake_mode.sh start   - stop the real service, start fake-hardware mode
#   test_tools/fake_mode.sh stop    - stop fake-hardware mode, restart the real service
#   test_tools/fake_mode.sh status  - show which mode (if any) is currently active

set -u

PIFINDER_REPO="/home/stellarmate/PiFinder"
PF_REMOTE="${PIFINDER_REPO}/.claude/skills/pifinder-remote/scripts/pf_remote.py"
FAKE_PORT=8081

_fake_running() {
    curl -s -m 2 "http://127.0.0.1:${FAKE_PORT}/api/status" >/dev/null 2>&1
}

_print_urls() {
    echo "Reachable at (same login as always - password: your stellarmate system password):"
    for ip in $(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^127\.'); do
        echo "  http://${ip}:${FAKE_PORT}/"
    done
}

case "${1:-}" in
    start)
        if _fake_running; then
            echo "Fake-hardware mode is already running."
            _print_urls
            exit 0
        fi
        echo "Stopping the real pifinder.service ..."
        sudo systemctl stop pifinder.service
        echo "Starting fake-hardware PiFinder (camera debug, keyboard none, display headless) ..."
        python3 "$PF_REMOTE" --repo "$PIFINDER_REPO" launch
        echo ""
        _print_urls
        ;;
    stop)
        if ! _fake_running; then
            echo "Fake-hardware mode isn't running."
        else
            echo "Stopping fake-hardware PiFinder ..."
            python3 "$PF_REMOTE" --repo "$PIFINDER_REPO" --port "$FAKE_PORT" stop
        fi
        echo "Starting the real pifinder.service ..."
        sudo systemctl start pifinder.service
        ;;
    status)
        if _fake_running; then
            echo "Fake-hardware mode: RUNNING (port ${FAKE_PORT})"
        else
            echo "Fake-hardware mode: not running"
        fi
        if systemctl is-active --quiet pifinder.service; then
            echo "Real pifinder.service: active"
        else
            echo "Real pifinder.service: inactive"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        echo ""
        echo "  start   Stop the real pifinder.service, start a fake-hardware"
        echo "          PiFinder instance (camera debug, keyboard none, display"
        echo "          headless) on port ${FAKE_PORT} - useful when the HAT is"
        echo "          disconnected but you still want the web UI for dev/testing."
        echo "  stop    Stop the fake-hardware instance, restart the real service."
        echo "  status  Show which mode is currently active."
        exit 1
        ;;
esac
