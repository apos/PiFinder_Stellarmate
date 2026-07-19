#!/usr/bin/env bash
# Run at boot only when the Waveshare LCD dev overlay is active - see
# pi_config_files/pifinder-fake-mode-autostart.service's
# ConditionPathExists=/dev/fb1. pifinder.service itself skips cleanly in
# that case (GPIO conflict with the real HAT's OLED, see its own
# ConditionPathExists=!/dev/fb1), so without this, a reboot with the
# overlay on would leave PiFinder not running at all. Starts Fake Mode
# (camera/keyboard/display all stubbed - no GPIO clash) plus the
# screen/keyboard bridges, so the LCD actually shows something without a
# manual step after every reboot. See basic-memory/pifinder-stellarmate/00030.
set -u

REPO_DIR="/home/stellarmate/PiFinder_Stellarmate"
PIFINDER_VENV_PY="/home/stellarmate/PiFinder/python/.venv/bin/python3"
FAKE_PORT=8081

echo "LCD overlay active - starting Fake Mode instead of the real service..."
if ! bash "${REPO_DIR}/test_tools/fake_mode.sh" start; then
    echo "ERROR: fake_mode.sh start failed - LCD dev autostart aborted." >&2
    exit 1
fi

echo "Waiting for Fake Mode's API to answer before starting the LCD bridges..."
up=0
for _ in $(seq 1 60); do
    if curl -s -m 2 "http://127.0.0.1:${FAKE_PORT}/api/status" >/dev/null 2>&1; then
        up=1
        break
    fi
    sleep 1
done
if [ "$up" -ne 1 ]; then
    echo "ERROR: Fake Mode API never answered - not starting the LCD bridges." >&2
    exit 1
fi

echo "Starting screen mirror + keyboard bridge..."
setsid nohup "${PIFINDER_VENV_PY}" "${REPO_DIR}/test_tools/fb_screen_mirror.py" \
    --rotate 90 --base-url "http://127.0.0.1:${FAKE_PORT}" \
    >/tmp/fb_screen_mirror.log 2>&1 < /dev/null &
setsid nohup "${PIFINDER_VENV_PY}" "${REPO_DIR}/test_tools/fb_keyboard_bridge.py" \
    --base-url "http://127.0.0.1:${FAKE_PORT}" \
    >/tmp/fb_keyboard_bridge.log 2>&1 < /dev/null &

echo "LCD dev autostart complete."
