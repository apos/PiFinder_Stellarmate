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
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

import pam_auth
import indi_client
import webmanager_client

PORT = 8765
# Same account + mechanism PiFinder's own Remote login checks
# (sys_utils.verify_password("stellarmate", password)) - one password to
# remember for both. Only the page and state-changing actions require it;
# /state and /log stay open so PiFinder's PFSM page can cross-origin
# poll status and show "Setup Wizard is running" without a login prompt.
AUTH_USER = "stellarmate"
AUTH_REALM = "PiFinder Setup"
GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
SETUP_SCRIPT = REPO_ROOT / "pifinder_stellarmate_setup.sh"
PIFINDER_DIR = Path.home() / "PiFinder"
PIFINDER_VENV_PY = PIFINDER_DIR / "python" / ".venv" / "bin" / "python3"
GPSD_PORT = 2947
# Thumbnails, not the full-resolution originals used elsewhere (e.g. the
# README) - these are only ever shown small on this page (128px/78px tall),
# so serving the originals wasted a lot of load time for nothing (the
# HeyApos one alone was ~2MB at 1920x1080 for a 78px-tall footer logo).
PIFINDER_IMAGE = REPO_ROOT / "docs" / "images" / "readme" / "PiFinder_thumb.jpg"
AVVP_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "avvp_2019_logo_wortmarke_neg_thumb.png"
HEYAPOS_LOGO = REPO_ROOT / "docs" / "images" / "readme" / "HeyApos_Wortmarke_logo_thumb.png"
# Negative/for-dark-background variant - matches this page's own #111 body background.
PROJECT_LOGO = REPO_ROOT / "docs" / "images" / "logo" / "PiFinder-Stellarmate_Wortmarke_Negativ_fuer-dunklen-hg.png"
# PiFinder's own splash bitmap (shown by pifinder_splash.service before the
# main app is up) - only exists once PiFinder has actually been installed.
PIFINDER_WELCOME_IMAGE = PIFINDER_DIR / "images" / "welcome.png"
# #117: cached red-tinted version of the above, matching the real OLED's
# actual red rendering (see displays.py's RED_RGB color mask) instead of the
# full-color/blue original - see _pifinder_welcome_image_red() below.
PIFINDER_WELCOME_IMAGE_RED = GUI_DIR / ".welcome_red_cache.png"
LOG_FILE = REPO_ROOT / ".gui_setup.log"
# Written just before a successful run's self-restart (see
# _restart_control_center()) so the fresh process can tell the reloaded page
# "the run you were watching actually finished OK" - otherwise that whole
# result (and the log content, even though LOG_FILE itself survives) is
# invisible to a brand-new process with empty in-memory state. Deliberately
# consumed (read once, then deleted - see /last_run_summary below) rather
# than relying only on an age check, so a write that's somehow interrupted
# or never cleaned up can't linger and get misattributed to some later,
# unrelated restart - found live 2026-08-01.
RESULT_FILE = REPO_ROOT / ".gui_setup.result"
STATUS_PAGE = GUI_DIR / "status_page.html"
HELP_PAGE = GUI_DIR / "help.html"


def _page_version() -> str:
    """Short content hash of status_page.html - lets an already-open browser
    tab notice its HTML/JS has changed on disk (e.g. this file was edited, or
    the whole service was restarted with newer code) even though it has no
    other way to find out short of the user manually reloading. Cheap enough
    to read+hash on every /page_version request - this file is a few hundred
    KB at most, polled at most every few seconds by any one client."""
    return hashlib.sha256(STATUS_PAGE.read_bytes()).hexdigest()[:12]
# Deliberately decoupled from PiFinder's own web server/codebase: this just
# shells out to test_tools/fake_mode.sh (see its own header comment for the
# full rationale), which itself toggles between the real systemd service and
# a fake-hardware instance via the pifinder-remote skill's pf_remote.py.
FAKE_MODE_SCRIPT = REPO_ROOT / "test_tools" / "fake_mode.sh"
FAKE_MODE_PORT = 8081

# Waveshare 3.5" LCD dev/test setup (basic-memory/pifinder-stellarmate/00024,
# 00030) - the overlay that drives it (waveshare35b-v2) claims GPIO lines a
# real HAT's OLED/keypad also need, so it can only be on OR the real HAT,
# never both. Pi firmware overlays only apply at boot, so toggling it always
# means editing /boot/config.txt and rebooting - see _set_lcd_overlay(). Once
# active, pifinder-fake-mode-autostart.service (see pi_config_files/) starts
# Fake Mode plus the screen mirror automatically at boot - nothing left to
# start manually here.
CONFIG_TXT = Path("/boot/config.txt")
WAVESHARE_OVERLAY = "dtoverlay=waveshare35b-v2"
LCD_FRAMEBUFFER = Path("/dev/fb1")  # exists iff the overlay is currently active

# A plain USB/2.4GHz-dongle numpad bridged to PiFinder's /api/key (evdev,
# see test_tools/fb_keyboard_bridge.py's own header) - unlike the LCD above,
# this needs no GPIO or overlay at all, works against either Real or Fake
# Mode (auto-probed, and self-heals across a mode switch on its own - see
# the script's send()), and has nothing to do with the physical display - it
# was wrongly bundled with the LCD's autostart at first (see 00031). Managed
# as its own systemd unit (pifinder-numpad-bridge.service, see
# pi_config_files/) rather than a tracked Popen, so "on" persists across
# reboots the same way pifinder-control-center.service's own enabled-state
# does - see 00035.
KEYBOARD_BRIDGE_SERVICE = "pifinder-numpad-bridge.service"

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
# --mode=indi_only's own, much shorter phase() call sequence - a completely
# separate list, not a subset of PHASES, since "Building INDI drivers" also
# appears there: matching by name against the full list (see _reader_thread()
# below) would otherwise land on that entry's position in PHASES (index 8 of
# 10) and mark everything before it - hardware access, cloning, venv, star
# catalog, none of which indi_only mode ever runs - as falsely "done". Found
# live (2026-07-28) via the Control Center's own checklist showing exactly
# that.
PHASES_INDI_ONLY = [
    "Installing INDI build dependencies",
    "Building INDI drivers",
    "Setup complete",
]
PHASE_MARKER = "###PHASE### "
REBOOT_MARKER = "###REBOOT_NEEDED### "

_lock = threading.Lock()

# Failed-auth rate limiting - see _require_auth(). Found live (2026-07-25): a
# browser tab with stale/wrong cached Basic Auth credentials, combined with
# several independent polling loops on this page, retried a wrong password
# on every single poll - well over a hundred failed attempts in a few
# minutes, briefly bursting past 10/second. Each failed attempt calls into
# PAM, which does real password-hashing work (deliberately slow, e.g.
# sha512crypt) - expensive enough, repeated fast enough, to visibly starve
# the GIL and make unrelated background threads (the startup hardware test,
# in this case) look hung even though nothing was actually deadlocked. Also
# a real, if mild, brute-force exposure on its own regardless of that
# incident - this call site had no limit on repeated attempts at all before.
_auth_failures = {}  # client_ip -> (failure_count, first_failure_monotonic)
_AUTH_LOCKOUT_THRESHOLD = 5
_AUTH_LOCKOUT_WINDOW = 30.0  # seconds
# Caps how many PAM calls can run *at once*, regardless of whether they'll
# turn out right or wrong. Found live: this page fires ~15 independent
# polling loops - once the credentials are actually correct, enough of them
# can still land inside pam_authenticate() (real wall-clock work, not
# instant) at the same moment that a naive "count every attempt, clear on
# success" scheme false-locks out the *correct* password purely from
# concurrency (reproduced live: entering the right password worked, then a
# few seconds later - the next round of concurrent polls - got locked out
# again, repeatedly). A concurrency cap sidesteps that entirely: it doesn't
# need to know in advance whether an attempt will succeed, it just makes
# the rest queue briefly (blocking on the semaphore costs no CPU/GIL time)
# instead of all hitting PAM's expensive hashing at once.
_auth_semaphore = threading.Semaphore(2)

_lines = []
_running = False
_exit_code = None
_process = None
_phase_index = -1  # furthest phase reached so far, -1 = none yet
_reboot_needed = None  # None = unknown yet, True/False once the run reports it
_last_action = None  # "fresh" | "reinstall" | "update"
_last_mode = "full"  # "full" | "indi_only" - selects PHASES vs PHASES_INDI_ONLY
# True from the moment a successful setup-script run finishes until this
# process itself gets killed by _restart_control_center() below - exposed via
# /state and /log so the frontend can show a "restarting..." lock overlay
# instead of the normal success screen. A successful run may have landed on
# different PiFinder_Stellarmate code (branch switch/self-update always run
# first, any action/mode) - this process is a long-lived import of that code,
# so it stays stale until the systemd service itself restarts, unlike the
# setup script subprocess, which already gets fresh code via self_update.sh's
# own re-exec. Found live (2026-07-29): editing the code on disk did nothing
# for the still-running Control Center until it was manually restarted.
_cc_restart_pending = False

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

# Ports PiFinder itself might be listening on (real service on 80, its
# historical port-80-busy fallback 8080, or the fake-hardware instance on
# FAKE_MODE_PORT) - used to validate the ?port= the frontend passes when
# proxying to PiFinder's own /api/debug_solve, so this never becomes an
# open proxy to an arbitrary host/port. Always dials 127.0.0.1 regardless
# of which IP the browser used to reach this page - this server and
# PiFinder always run on the same Pi.
_ALLOWED_PIFINDER_PORTS = {"80", "8080", str(FAKE_MODE_PORT)}


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


def _real_service_state() -> str:
    """pifinder.service's raw systemd ActiveState string (active,
    activating, inactive, failed, deactivating, ...) - added 2026-08-09
    (#192) so the frontend's OLED-mirror wait overlay can say something
    concrete about *why* it's still waiting instead of a generic message
    the whole time. Deliberately not --quiet: without it, `systemctl
    is-active` prints the state to stdout regardless of exit code (a
    non-0 exit just means "not active", the printed state still tells you
    which of inactive/failed/activating/deactivating it actually is)."""
    result = subprocess.run(
        ["systemctl", "is-active", "pifinder.service"],
        capture_output=True,
        text=True,
    )
    return (result.stdout or "").strip() or "unknown"


def _lcd_overlay_active() -> bool:
    """Whether the Waveshare LCD dev overlay is active right now - checked
    against the actual framebuffer device, not /boot/config.txt (overlays
    only apply at boot, so config.txt can say one thing while a pending
    reboot hasn't happened yet - /dev/fb1 is always the current truth)."""
    return LCD_FRAMEBUFFER.exists()


def _set_lcd_overlay(enable: bool):
    """Comments/uncomments the waveshare35b-v2 overlay line in
    /boot/config.txt (backing it up first) and triggers a reboot - Pi
    firmware overlays only apply at boot, so there's no live-toggle path.
    Once the reboot completes: if enabled, pifinder-fake-mode-autostart.
    service brings up Fake Mode + the screen/keyboard bridges automatically
    (pifinder.service itself skips cleanly, see its own
    ConditionPathExists); if disabled, pifinder.service starts normally like
    any other boot. Returns (ok, error)."""
    if not CONFIG_TXT.exists():
        return False, f"{CONFIG_TXT} not found."
    backup = CONFIG_TXT.with_name(f"config.txt.bak_before_lcd_toggle_{time.strftime('%Y%m%d_%H%M%S')}")
    if subprocess.run(["sudo", "cp", str(CONFIG_TXT), str(backup)]).returncode != 0:
        return False, f"Could not back up {CONFIG_TXT} - aborting rather than editing it unbacked-up."
    if enable:
        # Uncomment if present-but-commented; append if missing entirely
        # (shouldn't normally happen once set up once, but don't assume).
        sed_result = subprocess.run(
            ["sudo", "sed", "-i", f"s/^#{re.escape(WAVESHARE_OVERLAY)}/{WAVESHARE_OVERLAY}/", str(CONFIG_TXT)]
        )
        if sed_result.returncode != 0:
            return False, f"Could not edit {CONFIG_TXT}."
        grep_result = subprocess.run(["grep", "-qxF", WAVESHARE_OVERLAY, str(CONFIG_TXT)])
        if grep_result.returncode != 0:
            append_result = subprocess.run(
                ["sudo", "tee", "-a", str(CONFIG_TXT)], input=f"{WAVESHARE_OVERLAY}\n", text=True,
                stdout=subprocess.DEVNULL,
            )
            if append_result.returncode != 0:
                return False, f"Could not append the overlay line to {CONFIG_TXT}."
    else:
        sed_result = subprocess.run(
            ["sudo", "sed", "-i", f"s/^{re.escape(WAVESHARE_OVERLAY)}/#{WAVESHARE_OVERLAY}/", str(CONFIG_TXT)]
        )
        if sed_result.returncode != 0:
            return False, f"Could not edit {CONFIG_TXT}."
    threading.Thread(target=_do_reboot, daemon=True).start()
    return True, None


def _keyboard_bridge_running() -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", KEYBOARD_BRIDGE_SERVICE]
    ).returncode == 0


def _stop_keyboard_bridge():
    """Disables + stops pifinder-numpad-bridge.service - systemd's own
    enabled-state is the persistence mechanism (same as
    pifinder-control-center.service), so this is what makes "off" survive
    a reboot too, not just the current session."""
    subprocess.run(["sudo", "systemctl", "disable", "--now", KEYBOARD_BRIDGE_SERVICE])


def _start_keyboard_bridge():
    """Enables + starts pifinder-numpad-bridge.service. Returns (ok, error)."""
    if not (_fake_mode_up() or _real_service_active()):
        return False, "PiFinder is not running (neither Fake nor Real Mode) - start one first."
    result = subprocess.run(["sudo", "systemctl", "enable", "--now", KEYBOARD_BRIDGE_SERVICE])
    if result.returncode != 0:
        return False, f"systemctl enable --now {KEYBOARD_BRIDGE_SERVICE} failed (exit {result.returncode})."
    return True, None


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
        # 25s, not the original 10s: found live 2026-08-03 with a genuinely
        # present, working camera still showing "unconfirmed" (grey, not
        # red) right after an install/update run - rpicam-hello enumerating
        # under a heavily loaded Pi (compiling INDI drivers etc., load >8 on
        # 4 cores) took longer than 10s, so this call's own timeout fired
        # and got caught below, returning None ("inconclusive") instead of
        # True. This is a background poll (every 20s, see
        # refreshHardwareStatusAndDependents() in status_page.html), so a
        # slower worst case here doesn't block the UI - it just delays that
        # one badge's next update.
        result = subprocess.run(
            ["rpicam-hello", "--list-cameras"],
            capture_output=True, text=True, timeout=25,
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

    Retries a couple of times before concluding "not present" - found live
    2026-08-04 that a single miss can happen even with a genuinely present,
    working IMU: try_lock() only serializes within this one process, not
    bus-wide against PiFinder's own IMU reader polling the same device at
    ~30Hz, so an unlucky scan can occasionally race a concurrent transaction
    and come back empty. A momentary miss isn't a "not detected" verdict on
    its own; only every attempt missing is.
    """
    if not PIFINDER_VENV_PY.exists():
        return None
    for attempt in range(3):
        try:
            result = subprocess.run(
                [str(PIFINDER_VENV_PY), "-c", _IMU_SCAN_SCRIPT],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            return None
        if result.returncode != 0 or "LOCK_FAILED" in result.stdout:
            return None
        if any(addr in result.stdout for addr in _BNO055_I2C_ADDRESSES):
            return True
        if attempt < 2:
            time.sleep(0.3)
    return False


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


def _pifinder_status_snapshot(ports=("80", "8080", str(FAKE_MODE_PORT))):
    """GETs PiFinder's own /api/status from whichever of `ports` answers
    first (real service on 80/8080, or the fake-hardware instance). Returns
    the parsed dict, or None if none of them are reachable. Shared by the
    camera functional test (reading PiFinder's own CAM_FAILED signal instead
    of fighting it for the camera device) and the GPS status snapshot."""
    for port in ports:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as resp:
                return json.loads(resp.read())
        except Exception:
            continue
    return None


def _journal_grep_since_boot(unit: str, patterns, max_lines=3):
    """Greps `journalctl -u unit -b` for any of `patterns`, returns the last
    matching line(s) joined, or None if the check itself failed or nothing
    matched. Good enough resolution for classifying a failure that's usually
    still fresh in the log right after it happens - not trying to scope this
    to the exact current service invocation."""
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-b", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    lines = [ln for ln in result.stdout.splitlines() if any(p in ln for p in patterns)]
    if not lines:
        return None
    return " | ".join(lines[-max_lines:])


def _as_text(x):
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    return x or ""


def _journal_process_crash_detail(unit: str, process_name: str, max_block_lines=25):
    """Looks for the most recent `Process <process_name>:` crash block (the
    header Python's multiprocessing prints for an uncaught exception in a
    named subprocess - see main.py's Process(..., name="Camera"/"IMU", ...))
    in `journalctl -u unit -b`, and returns its final exception line (e.g.
    "IndexError: list index out of range"), or None if no such crash block
    is present.

    Scoped to the named subprocess specifically - a blanket "any Traceback in
    the whole service journal" search would misattribute an unrelated
    subprocess's crash (this is exactly how a stale IMU crash got reported as
    a camera failure during development - the IMU and Camera subprocesses
    share one journal).
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-b", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    lines = result.stdout.splitlines()
    header = f"Process {process_name}:"
    last_start = None
    for i, ln in enumerate(lines):
        if ln.strip() == header:
            last_start = i
    if last_start is None:
        return None
    block = lines[last_start:last_start + max_block_lines]
    if len(block) < 2 or "Traceback (most recent call last)" not in block[1]:
        return None
    # The traceback's final line (the first non-indented line after the
    # header) is the actual exception, e.g. "IndexError: list index out of
    # range" - more useful in a one-line status than the full stack.
    for ln in block[2:]:
        if ln and not ln.startswith((" ", "\t", "~", "^")):
            return ln.strip()
    return None


# --- Deeper "functional" hardware tests (the "Test Hardware" button) ------
#
# The passive checks above (_camera_hardware_present/_imu_hardware_present)
# only prove *presence* - a camera that answers "yes I exist" to
# rpicam-hello can still fail to actually deliver frames (a loose ribbon
# cable did exactly this - see basic-memory pifinder-stellarmate/00047).
# These go one step further and try to actually use the hardware, then
# classify any failure as hardware/driver/python so it's clear at a glance
# whether this is a cable problem or a PiFinder bug - both in the tile and
# in the shared Terminal output (see _run_hardware_test() below).

# Substrings from libcamera's own C++-level log output (not a Python
# exception - picamera2 keeps running after logging these) that specifically
# indicate a sensor/cable problem rather than a software bug. Seen live after
# a loose ribbon cable: "Camera frontend has timed out!" - see 00047.
_CAMERA_DRIVER_ERROR_PATTERNS = (
    "Camera frontend has timed out",
    "Timed out waiting for reconfiguration",
)

_CAMERA_CAPTURE_SCRIPT = (
    "import json, sys\n"
    "try:\n"
    "    from picamera2 import Picamera2\n"
    "    picam2 = Picamera2()\n"
    "    picam2.configure(picam2.create_still_configuration())\n"
    "    picam2.start()\n"
    "    arr = picam2.capture_array()\n"
    "    picam2.stop()\n"
    "    picam2.close()\n"
    "    print(json.dumps({'ok': True, 'shape': list(arr.shape)}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'ok': False, 'exc_type': type(e).__name__, 'exc_msg': str(e)}))\n"
    "    sys.exit(1)\n"
)

_IMU_READ_SCRIPT = (
    "import json, sys\n"
    "try:\n"
    "    import board\n"
    "    import adafruit_bno055\n"
    "    i2c = board.I2C()\n"
    "    sensor = adafruit_bno055.BNO055_I2C(i2c)\n"
    "    temp = sensor.temperature\n"
    "    calib = sensor.calibration_status\n"
    "    print(json.dumps({'ok': True, 'temperature': temp,"
    " 'calibration_status': list(calib) if calib else None}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'ok': False, 'exc_type': type(e).__name__, 'exc_msg': str(e)}))\n"
    "    sys.exit(1)\n"
)

# #117: tints a grayscale-derived version of the source image pure red
# (R=luminance, G=0, B=0) - the same mapping PiFinder's own displays.py uses
# for its real OLED (RED_RGB = ColorMask([1, 0, 0], "RGB")) - so the static
# placeholder matches the warm red glow the live hardware is always seen in,
# instead of the full-color/blue splash image as cloned from upstream.
_RED_CONVERT_SCRIPT = (
    "import sys\n"
    "from PIL import Image\n"
    "src, dst = sys.argv[1], sys.argv[2]\n"
    "grey = Image.open(src).convert('L')\n"
    "zero = Image.new('L', grey.size, 0)\n"
    "Image.merge('RGB', (grey, zero, zero)).save(dst)\n"
)


def _pifinder_welcome_image_red():
    """Returns the path to a red-tinted cache of PIFINDER_WELCOME_IMAGE,
    (re)generating it via PiFinder's own venv (has Pillow, unlike the system
    python3 this server itself runs under) whenever missing or older than
    the source. Returns None if the source doesn't exist yet (PiFinder not
    installed) or generation fails - callers should fall back to serving
    the plain original in that case rather than 404ing a placeholder image."""
    if not PIFINDER_WELCOME_IMAGE.is_file():
        return None
    if (
        PIFINDER_WELCOME_IMAGE_RED.is_file()
        and PIFINDER_WELCOME_IMAGE_RED.stat().st_mtime >= PIFINDER_WELCOME_IMAGE.stat().st_mtime
    ):
        return PIFINDER_WELCOME_IMAGE_RED
    if not PIFINDER_VENV_PY.exists():
        return None
    try:
        result = subprocess.run(
            [str(PIFINDER_VENV_PY), "-c", _RED_CONVERT_SCRIPT,
             str(PIFINDER_WELCOME_IMAGE), str(PIFINDER_WELCOME_IMAGE_RED)],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not PIFINDER_WELCOME_IMAGE_RED.is_file():
        return None
    return PIFINDER_WELCOME_IMAGE_RED


def _classify_capture_failure(stdout, stderr, timed_out):
    """Turns a capture/read subprocess's raw result into (error_type,
    detail). error_type is "hardware"/"driver"/"python"/"unknown"/None
    (None = success) - the three buckets the user asked to tell apart at a
    glance, plus "unknown" for whatever doesn't fit."""
    combined = _as_text(stdout) + "\n" + _as_text(stderr)
    if timed_out:
        return "driver", (
            "Capture timed out - matches a known sensor/cable connection "
            "issue (see 'Camera frontend has timed out' in the driver log)."
        )
    for pattern in _CAMERA_DRIVER_ERROR_PATTERNS:
        if pattern in combined:
            return "driver", f"{pattern} (libcamera) - check the sensor cable/connector."
    try:
        data = json.loads(_as_text(stdout).strip().splitlines()[-1])
    except Exception:
        return "unknown", (combined.strip()[-500:] or "No output from the test script.")
    if data.get("ok"):
        return None, None
    return "python", f"{data.get('exc_type', 'Exception')}: {data.get('exc_msg', '')}"


def _camera_functional_test(log):
    """Runs the camera functional test, logging progress via log(line).
    Returns {"status": "functional"|"error"|"absent"|"unknown",
             "error_type": "hardware"|"driver"|"python"|"unknown"|None,
             "detail": str|None}."""
    log("Camera: checking hardware presence (rpicam-hello --list-cameras) ...")
    present = _camera_hardware_present()
    if present is None:
        log("Camera: rpicam-hello unavailable - can't determine presence.")
        return {"status": "unknown", "error_type": None, "detail": "rpicam-hello unavailable"}
    if present is False:
        log("Camera: NOT detected.")
        return {"status": "absent", "error_type": "hardware", "detail": "No camera detected by rpicam-hello."}
    log("Camera: hardware present.")

    if _real_service_active():
        log(
            "Camera: pifinder.service is running in Real Mode - reading its own live "
            "status instead of a separate capture test (avoids fighting it for exclusive "
            "access to the same camera device)."
        )
        status = _pifinder_status_snapshot(ports=("80", "8080"))
        if status is None:
            log("Camera: PiFinder's own API isn't reachable right now - can't confirm functional status.")
            return {"status": "unknown", "error_type": None, "detail": "PiFinder API unreachable"}
        # Deliberately NOT using solution.solve_source ("CAM"/"CAM_FAILED") as
        # the signal here: that only reflects whether the most recent
        # plate-solve attempt matched stars, which fails constantly and
        # completely normally indoors/no-sky-view - it says nothing about
        # whether the camera itself is working. The two signals that
        # actually mean "the camera is broken" are (a) PiFinder having
        # silently fallen back to the simulated camera, and (b) a real
        # driver/Python error in the journal.
        camera_type = status.get("camera_type")
        log(f"Camera: PiFinder reports camera_type={camera_type!r} - checking the journal for driver/Python errors ...")
        crash_detail = _journal_process_crash_detail("pifinder.service", "Camera")
        if crash_detail:
            log(f"Camera: FAILED (python) - {crash_detail}")
            return {"status": "error", "error_type": "python", "detail": crash_detail}
        driver_detail = _journal_grep_since_boot("pifinder.service", _CAMERA_DRIVER_ERROR_PATTERNS, max_lines=3)
        if driver_detail:
            log(f"Camera: FAILED (driver) - {driver_detail}")
            return {"status": "error", "error_type": "driver", "detail": driver_detail}
        if camera_type == "debug":
            detail = (
                "PiFinder fell back to the simulated/debug camera - the real camera failed "
                "to initialize (check the pifinder.service journal around its last startup)."
            )
            log(f"Camera: FAILED (hardware) - {detail}")
            return {"status": "error", "error_type": "hardware", "detail": detail}
        log("Camera: no driver/Python errors in the journal, real camera_type reported - functional.")
        return {"status": "functional", "error_type": None, "detail": None}

    log("Camera: PiFinder isn't running in Real Mode - running an isolated capture test via its own camera stack ...")
    if not PIFINDER_VENV_PY.exists():
        log("PiFinder venv not found - can't run the test.")
        return {"status": "unknown", "error_type": None, "detail": "PiFinder venv not found"}
    try:
        result = subprocess.run(
            [str(PIFINDER_VENV_PY), "-c", _CAMERA_CAPTURE_SCRIPT],
            capture_output=True, text=True, timeout=15,
        )
        error_type, detail = _classify_capture_failure(result.stdout, result.stderr, False)
    except subprocess.TimeoutExpired as e:
        error_type, detail = _classify_capture_failure(e.stdout, e.stderr, True)
    except Exception as e:
        error_type, detail = "python", f"{type(e).__name__}: {e}"

    if error_type is None:
        log("Camera: capture succeeded - functional.")
        return {"status": "functional", "error_type": None, "detail": None}
    log(f"Camera: capture FAILED ({error_type}) - {detail}")
    return {"status": "error", "error_type": error_type, "detail": detail}


def _imu_functional_test(log):
    """Runs the IMU functional test, logging progress via log(line). Same
    result shape as _camera_functional_test()."""
    log("IMU: scanning I2C bus for the BNO055 (address 0x28/0x29) ...")
    present = _imu_hardware_present()
    if present is None:
        log("IMU: I2C scan unavailable - can't determine presence.")
        return {"status": "unknown", "error_type": None, "detail": "I2C scan unavailable"}
    if present is False:
        log("IMU: NOT detected.")
        return {"status": "absent", "error_type": "hardware", "detail": "No BNO055 found on the I2C bus."}
    log("IMU: address found on the bus.")

    if _real_service_active():
        # Unlike the plain bus scan above, a full register read here would
        # run concurrently with PiFinder's own IMU process polling the same
        # sensor at ~30Hz (see imu_pi.py) - contention on that read is
        # exactly what produced a spurious IMU crash during development of
        # this feature. Check PiFinder's own journal instead of racing it.
        log("IMU: pifinder.service is running - checking its journal for a crashed IMU process instead of a concurrent read.")
        crash_detail = _journal_process_crash_detail("pifinder.service", "IMU")
        if crash_detail:
            log(f"IMU: FAILED (python) - {crash_detail}")
            return {"status": "error", "error_type": "python", "detail": crash_detail}
        log("IMU: no crashed IMU process in the journal - functional.")
        return {"status": "functional", "error_type": None, "detail": None}

    log("IMU: PiFinder isn't running - reading a live sensor value to confirm it actually responds ...")
    if not PIFINDER_VENV_PY.exists():
        log("PiFinder venv not found - can't run the test.")
        return {"status": "unknown", "error_type": None, "detail": "PiFinder venv not found"}
    try:
        result = subprocess.run(
            [str(PIFINDER_VENV_PY), "-c", _IMU_READ_SCRIPT],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        log("IMU: read timed out.")
        return {"status": "error", "error_type": "driver", "detail": "I2C read timed out."}
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        log(f"IMU: read FAILED (python) - {detail}")
        return {"status": "error", "error_type": "python", "detail": detail}
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        detail = (result.stdout + result.stderr).strip()[-500:] or "No output from the read test."
        log(f"IMU: read FAILED (unknown) - {detail}")
        return {"status": "error", "error_type": "unknown", "detail": detail}
    if data.get("ok"):
        log(f"IMU: read succeeded (temperature={data.get('temperature')}) - functional.")
        return {"status": "functional", "error_type": None, "detail": None}
    detail = f"{data.get('exc_type', 'Exception')}: {data.get('exc_msg', '')}"
    log(f"IMU: read FAILED (python) - {detail}")
    return {"status": "error", "error_type": "python", "detail": detail}


def _gps_status_snapshot(log):
    """Reads PiFinder's own already-existing GPS/location handling via its
    /api/status endpoint - deliberately not re-implemented here (the user's
    own framing: StellarMate/PiFinder already do this, we just want to see
    the result). Returns the `location` dict PiFinder reports (lat/lon/
    altitude/timezone/lock/...), or None if PiFinder isn't reachable."""
    log(
        "GPS: reading location/time status from PiFinder's own /api/status "
        "(reuses PiFinder's existing GPS handling, not re-implemented here) ..."
    )
    status = _pifinder_status_snapshot()
    if status is None:
        log("GPS: PiFinder's API isn't reachable right now (Real or Fake Mode must be running).")
        return None
    location = status.get("location") or {}
    log(
        "GPS: lock={lock} lat={lat} lon={lon} alt={altitude}m tz={timezone} "
        "source={source} last_lock={last_gps_lock}".format(
            lock=location.get("lock"),
            lat=location.get("lat"),
            lon=location.get("lon"),
            altitude=location.get("altitude"),
            timezone=location.get("timezone"),
            source=location.get("source"),
            last_gps_lock=location.get("last_gps_lock"),
        )
    )
    return location


_hwtest_running = False  # True while a Test Hardware run is in flight
_hwtest_lines = []  # progress log, shown in the shared Terminal tile
_hwtest_result = {"camera": None, "imu": None, "gps": None}

_reset_running = False  # True while a Reset run is in flight
_reset_lines = []  # progress log, shown in the shared Terminal tile
_reset_exit_code = None


def _hwtest_log(line: str):
    with _lock:
        _hwtest_lines.append(line)


# KStars stores its own Equipment Profiles (separate from the Web Manager
# profiles this feature manages) in a local SQLite DB, including whether
# "INDI Web Manager" is ticked for a given profile (indiwebmanagerport
# column - NULL if unticked, the Web Manager port if ticked - confirmed live
# 2026-07-25 by comparing two real rows, one with/one without the checkbox
# set in KStars' own Profile Editor). Read-only: this file can be open by a
# live KStars process, and writing to it risks corruption/lost updates -
# see the wizard's "Step 3" check, which only ever reads this and guides the
# user to fix it themselves in KStars if needed, never writes to it.
_KSTARS_USERDB_CANDIDATES = [
    Path.home() / ".var/app/org.kde.kstars/data/kstars/userdb.sqlite",  # Flatpak (StellarMate default)
    Path.home() / ".local/share/kstars/userdb.sqlite",  # native package install
]


def _kstars_webmanager_link_status(profile: str) -> dict:
    """{"checked": bool, "kstars_profile_found": bool, "linked": bool,
    "host": str|None, "indiwebmanagerport": int|None}. "checked" is False if
    no KStars user database could be found at all (nothing to report)."""
    db_path = next((p for p in _KSTARS_USERDB_CANDIDATES if p.exists()), None)
    if not db_path:
        return {"checked": False, "kstars_profile_found": False, "linked": False,
                "host": None, "indiwebmanagerport": None}
    try:
        # Open read-only via URI mode - never creates/locks the file for
        # writing even if KStars has it open at the same time.
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        try:
            row = con.execute(
                "SELECT host, port, indiwebmanagerport FROM profile WHERE name = ?", (profile,)
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        return {"checked": False, "kstars_profile_found": False, "linked": False,
                "host": None, "indiwebmanagerport": None, "error": str(e)}
    if not row:
        return {"checked": True, "kstars_profile_found": False, "linked": False,
                "host": None, "indiwebmanagerport": None}
    host, _port, iwm_port = row
    linked = iwm_port is not None and str(host).lower() in ("localhost", "127.0.0.1")
    return {"checked": True, "kstars_profile_found": True, "linked": linked,
            "host": host, "indiwebmanagerport": iwm_port}


def _ekos_indi_status() -> dict:
    """Reads KStars/Ekos's *own* INDI connection status via its D-Bus
    interface (org.kde.kstars.Ekos.indiStatus). This is a different thing
    from indiserver simply running with drivers connected - it reflects
    whether Ekos itself has its own client session connected, which is
    what the StellarMate App is understood to piggyback on. A Coupling
    preset writing to Mount Bridge while indiserver is up but Ekos was
    never connected wouldn't be visible in the session the user is
    actually looking at - found live 2026-07-26: indiStatus read 0 (Idle)
    even with several devices already connected via this tile's own
    Web-Manager/INDI-client path.

    Ekos::CommunicationStatus (KStars' own enum): Idle=0, Pending=1,
    Success=2, Error=3 - verified live via `qdbus6 org.kde.kstars
    /KStars/Ekos org.kde.kstars.Ekos.indiStatus`.

    Returns {"kstars_running": bool, "connected": bool|None}. "connected"
    is None when KStars isn't running at all (D-Bus name not registered) -
    nothing to report, not an error. Only ever reads this property - never
    calls Ekos's own connectDevices()/disconnectDevices() D-Bus methods,
    even though they exist, since that would drive a GUI the user may be
    actively looking at without them having asked for it here."""
    env = dict(os.environ)
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid()}/bus"
    try:
        result = subprocess.run(
            ["qdbus6", "org.kde.kstars", "/KStars/Ekos", "org.kde.kstars.Ekos.indiStatus"],
            env=env, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"kstars_running": False, "connected": None}
    if result.returncode != 0:
        return {"kstars_running": False, "connected": None}
    try:
        status = int(result.stdout.strip())
    except ValueError:
        return {"kstars_running": True, "connected": None}
    return {"kstars_running": True, "connected": status == 2}


def _ekos_qdbus(*args):
    env = dict(os.environ)
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid()}/bus"
    return subprocess.run(
        ["qdbus6", "org.kde.kstars", "/KStars/Ekos", *args],
        env=env, capture_output=True, text=True, timeout=5,
    )


def _ekos_start_profile(profile_name: str) -> dict:
    """Starts the given Ekos profile via org.kde.kstars.Ekos's D-Bus
    interface (setProfile + start) - unlike _ekos_indi_status() above,
    this DOES drive Ekos's own GUI, on purpose: found live 2026-08-04 that
    "go click Start/Connect in KStars yourself" was a hard blocker for
    Autoconnect, even though the profile name is already known here (same
    Web Manager profile the user already picked in this tile) and Ekos
    exposes exactly the needed calls (verified live via `qdbus6
    org.kde.kstars /KStars/Ekos org.kde.kstars.Ekos.getProfiles`).

    Only backs off while INDI is genuinely, currently connected
    (indiStatus == 2) - something is already going on (maybe the user's own
    unrelated KStars work) and yanking their live session out from under
    them would be wrong. Deliberately checks indiStatus here, not
    ekosStatus: found live (2026-08-05) that ekosStatus stays stuck at
    Success (2) even after the underlying INDI session was stopped
    externally (via the Web Manager's own Stop, not Ekos's Stop button),
    which permanently blocked every later Setup click from ever attempting
    a restart - Ekos never reset ekosStatus back to Idle on its own. If
    ekosStatus indicates a stale loaded-but-disconnected profile in that
    situation, stop() is called first to tear it down cleanly before
    reloading, rather than calling start() over it and risking a second,
    conflicting indiserver/driver launch alongside whatever's left running.

    Only ever called from the explicit, user-initiated Autoconnect flow,
    never from a passive/background poll - same reasoning
    _ekos_indi_status() already documents, just not an absolute "never
    touch Ekos" rule.

    Returns {"attempted": bool, "reason": str|None} - "attempted": False
    with a reason means the caller should fall back to the manual
    instructions, not that anything failed loudly.
    """
    try:
        status_result = _ekos_qdbus("org.kde.kstars.Ekos.ekosStatus")
    except (OSError, subprocess.TimeoutExpired):
        return {"attempted": False, "reason": "KStars/Ekos not reachable via D-Bus"}
    if status_result.returncode != 0:
        return {"attempted": False, "reason": "KStars not running"}
    try:
        ekos_status = int(status_result.stdout.strip())
    except ValueError:
        return {"attempted": False, "reason": "unexpected ekosStatus value"}

    try:
        indi_result = _ekos_qdbus("org.kde.kstars.Ekos.indiStatus")
        indi_status = int(indi_result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        indi_status = None
    if indi_status == 2:
        return {"attempted": False, "reason": "Ekos already has a session in progress"}

    try:
        if ekos_status != 0:
            _ekos_qdbus("org.kde.kstars.Ekos.stop")
        set_result = _ekos_qdbus("org.kde.kstars.Ekos.setProfile", profile_name)
        if set_result.returncode != 0 or set_result.stdout.strip() != "true":
            return {"attempted": False, "reason": f"profile '{profile_name}' not found in Ekos"}
        _ekos_qdbus("org.kde.kstars.Ekos.start")
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"attempted": False, "reason": str(e)}
    return {"attempted": True, "reason": None}


_mb_lines = []  # Mount Bridge action log, shown in #mount-bridge-tile's own log panel
_mb_last_running = None  # last known /api/mount_bridge_status "running" value, to log transitions


def _mb_log(line: str):
    with _lock:
        _mb_lines.append(f"{time.strftime('%H:%M:%S')} {line}")


def _parse_threshold(raw: str) -> float:
    """European keyboards/locales often produce a comma decimal separator
    (e.g. "0,5") - Python's float() only accepts a period and raises
    ValueError otherwise. The frontend already normalizes this before
    sending (see status_page.html's readThresholdInputRaw()), but this is a
    public HTTP endpoint - normalize here too as a backstop for any other
    caller. Raises ValueError on genuinely invalid input, same as float()."""
    return float(raw.replace(",", "."))


class _BackgroundRetrier:
    """Fire-and-forget 'run this in a background thread, but never run two
    attempts at once' helper - extracted from #118's original hand-rolled
    in-flight-flag + threading.Thread pattern so a future feature needing
    the same shape ("keep retrying an action from a polling loop without
    stacking concurrent attempts") can reuse it instead of reimplementing
    the guard by hand. Deliberately minimal: it does not schedule its own
    retries - the caller's own polling loop (e.g. a watchdog's `while True:
    time.sleep(interval)`) is what re-triggers a fresh attempt each tick;
    this only guards against overlapping ones."""

    def __init__(self):
        self._in_flight = False
        self._lock = threading.Lock()

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def trigger(self, action_fn) -> bool:
        """Starts action_fn() in a background daemon thread unless an
        earlier call's thread is still running. Returns True if a new
        attempt was started, False if one was already in flight (the
        caller's own next polling tick will just call trigger() again).
        action_fn takes no arguments; any exception it raises is swallowed
        (log inside action_fn if you want to know about failures)."""
        with self._lock:
            if self._in_flight:
                return False
            self._in_flight = True

        def _run():
            try:
                action_fn()
            finally:
                with self._lock:
                    self._in_flight = False

        threading.Thread(target=_run, daemon=True).start()
        return True


# Found live investigating #139: a 4-core Pi 4 at or above this 1-minute-
# load-average-per-core ratio was observed making PiFinder's own position
# server (pos_server.py) genuinely unresponsive to LX200 queries for several
# seconds at a time - not a bug anywhere, just a busy CPU. Deliberately
# coarse: a signal for a human to notice, not a claim that anything is
# actually broken (see /api/system_load and #139's own writeup).
_SYSTEM_LOAD_HIGH_RATIO = 1.5


def _cpu_temp_c():
    """SoC temperature in Celsius, or None if unreadable (non-Pi hardware,
    permissions, ...) - /sys/class/thermal is universal across Pi models
    and needs no subprocess (unlike vcgencmd)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def _system_load_status() -> dict:
    """CPU load average (1/5/15 min, from os.getloadavg()) relative to core
    count, plus SoC temperature. "high" only means "worth a human glancing
    at" - see _SYSTEM_LOAD_HIGH_RATIO's own comment. "percent" (load1 as a
    percentage of total available CPU, uncapped - >100% means genuinely
    oversubscribed, not a display bug) is what the UI actually shows now;
    "a load average of 9.7" meant nothing to most users without also
    knowing the core count to divide by themselves."""
    load1, load5, load15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    ratio1 = load1 / cpu_count
    return {
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
        "cpu_count": cpu_count,
        "ratio1": round(ratio1, 2),
        "percent": round(ratio1 * 100),
        "temp_c": _cpu_temp_c(),
        "high": ratio1 >= _SYSTEM_LOAD_HIGH_RATIO,
    }


def _pifinder_service_settings_stale():
    """True if pifinder.service's actually-running process's scheduling
    priority doesn't match what's currently configured for the unit -
    meaning it was started before the config last changed (e.g. an Update
    run that left an already-running instance untouched before
    pifinder_stellarmate_setup.sh's own start->restart fix - see that
    change's own comment) and needs a restart to pick up the current
    settings. Compares against the unit's OWN currently-loaded value
    rather than a hardcoded expected number, so this keeps working no
    matter what Nice= (or any future scheduling directive) is actually set
    to - nothing here needs to know the number itself.
    Returns None if pifinder.service isn't running or the check itself
    failed (nothing to report, not a mismatch)."""
    try:
        shown = subprocess.run(
            ["systemctl", "show", "pifinder.service", "--property=Nice,MainPID"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        # Deliberately NOT --value with a comma-separated property list -
        # found live: systemctl does not guarantee returning --value output
        # in the order the properties were requested in, so a positional
        # unpack silently paired the wrong values together. Self-labeled
        # "Key=Value" lines (systemctl's default format) sidestep that
        # entirely regardless of what order they come back in.
        values = dict(line.split("=", 1) for line in shown.strip().splitlines() if "=" in line)
        configured_nice = values.get("Nice")
        main_pid = values.get("MainPID")
        if configured_nice is None or main_pid is None or int(main_pid) <= 0:
            return None
        actual_nice = subprocess.run(
            ["ps", "-o", "ni=", "-p", main_pid],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not actual_nice:
            return None
        return int(actual_nice) != int(configured_nice)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


# #118: pos_server.py restarting (PiFinder service restart/crash-recovery/
# redeploy) silently breaks "PiFinder LX200"'s already-open TCP connection -
# CONNECTION stays On but ReadScopeStatus() keeps serving the frozen
# pre-restart RA/Dec forever, with nothing surfacing the failure. An
# in-driver fix was attempted and confirmed NOT to self-heal live (see
# #139, which tracks that alternative separately); this is the approved
# Control-Center-side fix instead: detect the restart from here and redo
# the same disconnect/connect cycle already confirmed live by hand via
# indi_setprop (#118's documented workaround).
_pifinder_lx200_healed_for_start = None  # pifinder.service start time we last confirmed LX200 connected against
_pifinder_lx200_reconnect_retrier = _BackgroundRetrier()


def _pifinder_service_start_monotonic():
    """pifinder.service's ActiveEnterTimestampMonotonic (microseconds since
    boot), or None if the service isn't running / systemctl can't answer.
    Monotonic rather than the wall-clock timestamp - a plain integer,
    always comparable, and immune to wall-clock/timezone parsing edge
    cases; changes exactly once per service (re)start, which is all that's
    needed here."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "pifinder.service", "--property=ActiveEnterTimestampMonotonic", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def _pifinder_lx200_auto_reconnect(status: dict) -> None:
    """Called every _pifinder_lx200_reconnect_watchdog() tick: whenever
    pifinder.service's own start time has moved on since we last confirmed
    "PiFinder LX200" freshly connected, force a reconnect to redo the TCP
    handshake. Deliberately keeps retrying every tick - not just once -
    until a fresh connect is actually confirmed: found live (2026-08-03)
    that pos_server.py isn't necessarily listening again the moment
    pifinder.service's own start time changes (PiFinder itself can still be
    mid-startup for camera/IMU init), so a single disconnect+connect attempt
    right after detecting the restart can itself fail and leave the driver
    *honestly* disconnected - gating retries on "still looks connected"
    would then never retry again. Once _pifinder_lx200_healed_for_start
    catches up to the current start time, this goes quiet again; only a
    genuinely new restart (a further-advanced start time) reawakens it.
    Runs the actual attempt in a background thread (via _BackgroundRetrier)
    so a detected restart never blocks the watchdog loop; its in-flight
    guard means a still-pending attempt is left alone rather than stacking
    a second one."""
    global _pifinder_lx200_healed_for_start
    if status.get("active_pifinder") != "PiFinder LX200":
        return
    current_start = _pifinder_service_start_monotonic()
    if current_start is None:
        return
    if _pifinder_lx200_healed_for_start is None:
        # First observation since this Control Center process started -
        # assume whatever's currently connected is already healthy rather
        # than forcing a reconnect for no reason on every restart of the
        # Control Center itself.
        _pifinder_lx200_healed_for_start = current_start
        return
    if current_start == _pifinder_lx200_healed_for_start:
        return
    was_connected = status.get("pifinder_connected") is True

    def _do_reconnect():
        global _pifinder_lx200_healed_for_start
        try:
            if was_connected:
                # Frozen-stale case: CONNECTION was already On, so DISCONNECT
                # first (mirrors the manual indi_setprop workaround from #118).
                indi_client.disconnect_device("PiFinder LX200")
                time.sleep(1.0)
            indi_client.connect_device("PiFinder LX200")
            time.sleep(1.0)
            fresh = indi_client.get_properties(device="PiFinder LX200").get("PiFinder LX200", {})
            now_connected = fresh.get("CONNECTION", {}).get("elements", {}).get("CONNECT") == "On"
            if now_connected:
                _pifinder_lx200_healed_for_start = current_start
                _mb_log("PiFinder LX200 auto-reconnect after pifinder.service restart succeeded")
            else:
                _mb_log(
                    "PiFinder LX200 auto-reconnect attempt did not take yet "
                    "(pos_server.py likely still starting) - will retry"
                )
        except indi_client.INDIClientError as e:
            _mb_log(f"PiFinder LX200 auto-reconnect after pifinder.service restart failed: {e}")

    started = _pifinder_lx200_reconnect_retrier.trigger(_do_reconnect)
    if started:
        _mb_log(
            f"pifinder.service restarted (monotonic start {_pifinder_lx200_healed_for_start} -> "
            f"{current_start}) - PiFinder LX200 {'still showed connected' if was_connected else 'not connected yet'}, "
            "attempting reconnect (#118)"
        )


def _pifinder_lx200_reconnect_watchdog(interval=20):
    """Runs for the Control Center's whole lifetime, independent of whether
    anyone has this web page open - #118's staleness bites just as easily
    during a KStars/Ekos-only session that never touches this GUI. Started
    once from main() as a daemon thread. Same 20s cadence as the frontend's
    own /api/mount_bridge_status poll (not tied to it - see that handler's
    own comment for why device_timeout is kept short by default here)."""
    while True:
        time.sleep(interval)
        try:
            status = indi_client.mount_bridge_status()
        except indi_client.INDIClientError:
            continue
        if not status.get("running"):
            continue
        try:
            _pifinder_lx200_auto_reconnect(status)
        except Exception as e:  # a watchdog thread must never die silently
            _mb_log(f"auto-reconnect watchdog raised unexpectedly: {e}")


def _run_hardware_test():
    """Runs all three checks in sequence and stores the combined result.
    Camera/IMU/GPS are deliberately sequential, not parallel: the camera
    test's PiFinder-is-running branch and the GPS snapshot both hit the same
    /api/status endpoint, and running I2C/camera probes concurrently would
    only make failures harder to attribute to one subsystem."""
    # try/finally is load-bearing, not defensive style: found live 2026-08-01
    # that without it, an uncaught exception from any of the three checks
    # below (plausible whenever the device is between installs - ~/PiFinder
    # missing, no venv, etc.) leaves _hwtest_running stuck True forever, in a
    # daemon thread that just dies silently - permanently locking out every
    # other mutex-guarded action (Reset/Uninstall/Reinstall/mode switch/...)
    # until the whole service is restarted, and the startup auto-run (see
    # _startup_hardware_test() below) can then hit the exact same failure
    # again on the very next start.
    global _hwtest_running, _hwtest_result
    with _lock:
        _hwtest_lines.clear()
        _hwtest_result = {"camera": None, "imu": None, "gps": None}
    try:
        _hwtest_log("=== Test Hardware: starting Camera / IMU / GPS checks ===")
        camera_result = _camera_functional_test(_hwtest_log)
        imu_result = _imu_functional_test(_hwtest_log)
        gps_location = _gps_status_snapshot(_hwtest_log)
        _hwtest_log("=== Test Hardware: done ===")
        with _lock:
            _hwtest_result = {"camera": camera_result, "imu": imu_result, "gps": gps_location}
    except Exception as e:
        _hwtest_log(f"=== Test Hardware: internal error - {e} ===")
    finally:
        with _lock:
            _hwtest_running = False


def _startup_hardware_test(timeout=120, interval=2, extended_retry_interval=15):
    """Runs at Control Center startup (see main()). pifinder-control-center.
    service has no ordering dependency on pifinder.service (deliberately -
    the Control Center must be able to start standalone, e.g. before PiFinder
    is even installed) - the two race independently at boot. Running the
    test immediately then reliably lost that race: PiFinder's own web server
    typically isn't up for several seconds after its service starts, so the
    very first startup test kept reporting a stale "PiFinder API
    unreachable" Camera/GPS result that then sat there until someone
    clicked the button by hand (live-reproduced across two reboots - see
    basic-memory pifinder-stellarmate/00048). Poll for PiFinder to answer
    first, then run the real test - if it never comes up within `timeout`,
    run anyway (accurately reports "not running" rather than waiting forever).

    Found live (2026-08-09, #188) after a full Pi reboot (not just a Control
    Center restart): PiFinder can take noticeably longer than this initial
    `timeout` to become reachable, competing with everything else the whole
    system is starting at once (X11, KStars, indiserver, ...) - the original
    design's own tradeoff ("run anyway, accurately reports not-running") then
    left a stale "PiFinder API unreachable" result sitting there with nothing
    to self-correct it once PiFinder actually did come up moments later,
    same symptom as before the 00048 fix just with a longer boot this time.
    Self-heals now: if the first attempt still couldn't reach PiFinder, keep
    quietly re-running the test every extended_retry_interval seconds,
    indefinitely, stopping as soon as PiFinder answers - each check is cheap
    (one HTTP call plus, once reachable, the same lightweight camera/imu/gps
    checks the button itself triggers) and this loop's whole purpose is
    stopping itself the moment it succeeds, so there's no real cost to not
    giving up after some arbitrary window - the alternative (silently
    staying stale forever after a slow-but-real boot) is worse than a few
    more harmless checks."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _pifinder_status_snapshot(ports=("80", "8080")) is not None or _fake_mode_up():
            break
        time.sleep(interval)
    _run_hardware_test()

    while True:
        with _lock:
            still_unreachable = _hwtest_result.get("gps") is None
        if not still_unreachable:
            break
        time.sleep(extended_retry_interval)
        if _pifinder_status_snapshot(ports=("80", "8080")) is None and not _fake_mode_up():
            continue  # still not reachable - no point re-running the test yet
        _run_hardware_test()


def _pifinder_solve_status(port: str):
    """GET the currently-reachable PiFinder instance's own /api/status and
    pull out debug_solve (Tools -> Test Mode's on/off state) plus the real
    solve-freshness fields (solve_source/last_solve_attempt/last_solve_success)
    - all from the same request, since /api/status already returns both.
    None if unreachable.

    solve_source is "CAM" (fresh plate-solve), "CAM_FAILED" (attempted, no
    star match - normal indoors/no sky view, not itself a hardware problem),
    or "IMU" (currently dead-reckoning between solves). See
    PiFinder/types/positioning.py's SolveSource enum."""
    if port not in _ALLOWED_PIFINDER_PORTS:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as resp:
            data = json.loads(resp.read())
        # solve_source/last_solve_attempt/last_solve_success live under
        # data["solution"], not top-level (only debug_solve is top-level) -
        # found live during TC-PFSM-85-01 step 4 (2026-08-02): the badge
        # stayed grey/"unknown" through a real, confirmed plate-solve because
        # this always read None from the wrong path.
        solution = data.get("solution") or {}
        # PiFinder's own Mount Type + PiFinder Type (Settings -> Mount Type /
        # Settings -> Advanced -> PiFinder Type), read directly from
        # PiFinder's own /api/orientation_status - deliberately NOT sourced
        # from Mount Bridge's PIFINDER_ORIENTATION INDI property, which only
        # exists while Mount Bridge is running/connected. The PiFinder
        # orientation ampel badge must show whenever PiFinder hardware
        # itself is present, regardless of Mount Bridge/coupling state
        # (direct feedback, 2026-08-09: "the PiFinder badge MUST be visible
        # when Hardware ist present, not only, when coupling is enable").
        # Best-effort: an older PiFinder without this route, or a transient
        # failure, just leaves both fields None - never breaks the rest of
        # this (already independently useful) response.
        pifinder_mount_type = None
        pifinder_screen_direction = None
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/orientation_status", timeout=3
            ) as resp:
                orientation = json.loads(resp.read())
            pifinder_mount_type = orientation.get("mount_type")
            pifinder_screen_direction = orientation.get("screen_direction")
        except Exception:
            pass
        return {
            "pifinder_mount_type": pifinder_mount_type,
            "pifinder_screen_direction": pifinder_screen_direction,
            "debug_solve": data.get("debug_solve"),
            # Fake-Solve (see #106/#128) - a synthetic RA/Dec injected via
            # PiFinder's /api/fake_solve, with real IMU dead-reckoning taking
            # over from there. Deliberately separate from debug_solve above
            # (which only swaps in a canned test image for the camera) and
            # from solve_source below (real solve health) - must never be
            # displayed as if it were a real "CAM" solve, see #128.
            "fake_solve_active": data.get("fake_solve_active"),
            # RA/Dec of the currently-tracked (injected + dead-reckoned)
            # position, shown alongside the active/off state - "active" alone
            # doesn't say much for what's meant to be a real, usable
            # simulator (User feedback, #128).
            "fake_solve_ra": solution.get("RA"),
            "fake_solve_dec": solution.get("Dec"),
            "solve_source": data.get("solve_source", solution.get("solve_source")),
            "last_solve_attempt": data.get(
                "last_solve_attempt", solution.get("last_solve_attempt")
            ),
            "last_solve_success": data.get(
                "last_solve_success", solution.get("last_solve_success")
            ),
        }
    except Exception:
        return None


def _pifinder_enable_fake_solve_from_mount(port: str):
    """Turn Injected Solve on, seeded with the currently coupled mount's
    live RA/Dec (read once via INDI, same source as /api/mount_bridge_status'
    active_mount) - a one-time "start here", not a continuous mount-follow
    (that's the larger #130 concept, not yet built). Returns
    (success: bool, error: str or None)."""
    if port not in _ALLOWED_PIFINDER_PORTS:
        return False, "invalid port"
    try:
        status = indi_client.mount_bridge_status()
    except Exception as e:
        return False, f"could not reach Mount Bridge: {e}"
    active_mount = status.get("active_mount")
    if not active_mount:
        return False, "no mount configured in Mount Bridge"
    try:
        props = indi_client.get_properties(device=active_mount)
        eq = props.get(active_mount, {}).get("EQUATORIAL_EOD_COORD", {}).get("elements", {})
        ra_deg = float(eq["RA"]) * 15.0  # INDI reports RA in hours
        dec_deg = float(eq["DEC"])
    except Exception as e:
        return False, f"could not read {active_mount}'s position: {e}"
    try:
        body = json.dumps({"ra": ra_deg, "dec": dec_deg}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/fake_solve",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200, None
    except Exception as e:
        return False, str(e)


def _pifinder_disable_fake_solve(port: str) -> bool:
    """DELETE to PiFinder's own /api/fake_solve - turns Fake-Solve back off,
    resuming normal real-camera solving."""
    if port not in _ALLOWED_PIFINDER_PORTS:
        return False
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/fake_solve", method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _pifinder_set_fake_solve(port: str, ra_deg: float, dec_deg: float):
    """POST an explicit RA/Dec (degrees, JNow) straight to PiFinder's own
    /api/fake_solve - independent of any coupled mount, unlike
    _pifinder_enable_fake_solve_from_mount() above. Turns Injected Solve on
    if it wasn't already, or re-seeds it to this exact position if it was
    (#205 - the GUI had no way to set/nudge a specific position without
    direct API access). Returns (success: bool, error: str or None)."""
    if port not in _ALLOWED_PIFINDER_PORTS:
        return False, "invalid port"
    if not (0 <= ra_deg <= 360) or not (-90 <= dec_deg <= 90):
        return False, "RA/Dec out of range"
    try:
        body = json.dumps({"ra": ra_deg, "dec": dec_deg}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/fake_solve",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200, None
    except Exception as e:
        return False, str(e)


def _pifinder_toggle_debug_solve(port: str) -> bool:
    """POST to PiFinder's own /api/debug_solve - toggles Tools -> Test Mode
    directly via PiFinder's ui_queue, bypassing menu navigation/keyboard_queue
    (which drops keypresses unreliably - see basic-memory/pifinder-stellarmate/
    00021 for how this was found)."""
    if port not in _ALLOWED_PIFINDER_PORTS:
        return False
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/debug_solve", method="POST", data=b""
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# The exact key codes PiFinder's own remote.html sends to /key_callback -
# LNG_* is that page's "arm Long, then press a key" combo, reproduced here
# so the Control Center's compact keypad (PiFinder tile "Quick keys") drives
# PiFinder through the identical, already-battle-tested code path instead of
# inventing a second key-mapping convention.
_ALLOWED_PIFINDER_KEY_CODES = {
    "LEFT", "UP", "DOWN", "RIGHT", "SQUARE",
    "LNG_LEFT", "LNG_UP", "LNG_DOWN", "LNG_RIGHT", "LNG_SQUARE",
}


# /key_callback is a browser-facing route on PiFinder's side, gated by its
# own @auth_required (Flask session cookie) - unlike /api/debug_solve, which
# is explicitly exempted there as a machine-to-machine call (see that
# route's own comment in PiFinder/server.py). A plain proxy POST here with
# no cookie gets silently 302-redirected to /login and urlopen happily
# reports 200 for the login PAGE it followed to - found live 2026-08-04:
# the Quick keys looked like they worked (no error anywhere) but never
# actually pressed anything. Fix: log in first (same account + password
# this Control Center's own auth already uses - see AUTH_USER/the comment
# above it), keep the resulting session cookie only for the one key press.
# "smate" is this project's documented default Remote-page password (shown
# in the Quick Links row) - if a user changed their stellarmate account
# password from that default, this login attempt fails and _pifinder_send_key
# returns False (Quick keys quietly stop working, same as PiFinder being
# unreachable for any other reason - no crash).
_PIFINDER_REMOTE_PASSWORD = "smate"

# Logging in is expensive - PAM's own password verification alone measured
# ~5s live on this hardware (crypt() cost, not a bug) - paying that on every
# single key press made the Quick keys feel completely unresponsive (found
# live 2026-08-04 right after adding the login step above: presses "worked"
# but took ~5s each, several seconds behind a burst of clicks). Cache one
# opener (with its session cookie) per port and reuse it; only pay the
# login cost again if a cached session turns out to be gone/expired.
_pifinder_key_openers: dict[str, urllib.request.OpenerDirector] = {}
_pifinder_key_openers_lock = threading.Lock()


def _pifinder_login(port: str) -> urllib.request.OpenerDirector | None:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    login_req = urllib.request.Request(
        f"http://127.0.0.1:{port}/login",
        method="POST",
        data=urlencode({"password": _PIFINDER_REMOTE_PASSWORD}).encode(),
    )
    opener.open(login_req, timeout=10)
    if not any(c.name == "session" for c in cookie_jar):
        return None  # wrong password (account password changed from the default)
    return opener


def _pifinder_send_key(port: str, code: str) -> bool:
    """POST to PiFinder's own /key_callback - same endpoint remote.html's
    buttonClicked() uses, so a press from this Control Center's compact
    keypad behaves identically to one from PiFinder's own remote page."""
    if port not in _ALLOWED_PIFINDER_PORTS or code not in _ALLOWED_PIFINDER_KEY_CODES:
        return False
    key_req_data = json.dumps({"button": code}).encode()
    try:
        with _pifinder_key_openers_lock:
            opener = _pifinder_key_openers.get(port)
            if opener is None:
                opener = _pifinder_login(port)
                if opener is None:
                    return False
                _pifinder_key_openers[port] = opener
        key_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/key_callback",
            method="POST",
            data=key_req_data,
            headers={"Content-Type": "application/json"},
        )
        with opener.open(key_req, timeout=8) as resp:
            if resp.status == 200 and "/login" not in resp.url:
                return True
        # Cached session no longer valid (PiFinder restarted, cookie
        # expired, ...) - drop it and try exactly once more with a fresh
        # login rather than silently failing from here on.
        with _pifinder_key_openers_lock:
            _pifinder_key_openers.pop(port, None)
            opener = _pifinder_login(port)
            if opener is None:
                return False
            _pifinder_key_openers[port] = opener
        key_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/key_callback",
            method="POST",
            data=key_req_data,
            headers={"Content-Type": "application/json"},
        )
        with opener.open(key_req, timeout=8) as resp:
            return resp.status == 200 and "/login" not in resp.url
    except Exception:
        return False


def _run_fake_mode_action(action):
    # try/finally wrapper is load-bearing, not defensive style - see
    # _run_hardware_test()'s comment for the general shape of this bug
    # (found live there first, 2026-08-01). _run_fake_mode_action_inner()'s
    # tail (settle-check loop, _camera_hardware_present()/
    # _imu_hardware_present() probes, a journalctl subprocess.run() call) has
    # no exception handling of its own - an uncaught exception anywhere in
    # there would leave _mode_action_running stuck True forever, same
    # lock-everything-out consequence. Wrapped here instead of re-indenting
    # the whole (long, already-branchy) inner function.
    global _mode_action_running
    try:
        _run_fake_mode_action_inner(action)
    finally:
        with _lock:
            _mode_action_running = False


def _run_fake_mode_action_inner(action):
    global _mode_lines, _mode_exit_code, _mode_error, _mode_target
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
                                   "reconnect the HAT, then try again, or use 'Back to Fake Mode' below.")
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
                _mode_error = "Fake Mode failed to start - see Terminal below."
    # _mode_action_running is cleared by the _run_fake_mode_action() wrapper's
    # finally block, not here - see its comment.


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


def _consume_result_file():
    """Read-once: called by GET /last_run_summary, right after this process
    restarted following a successful run - tells the reloaded page what the
    run it was watching actually did, since a brand-new process otherwise
    has no memory of it (see RESULT_FILE's own comment). Always deletes the
    file, whether or not it's fresh enough to report - a stale/interrupted
    leftover must never linger for some later, unrelated restart to pick up
    (found live 2026-08-01, see basic-memory pifinder-stellarmate/00001)."""
    if not RESULT_FILE.exists():
        return {"available": False}
    try:
        written_at = json.loads(RESULT_FILE.read_text())["written_at"]
    except Exception:
        written_at = 0
    finally:
        RESULT_FILE.unlink(missing_ok=True)
    if time.time() - written_at > 300:
        return {"available": False}
    try:
        log_tail = LOG_FILE.read_text().splitlines()[-50:]
    except Exception:
        log_tail = []
    return {"available": True, "log_tail": log_tail}


def _write_result_file():
    """Atomic write (temp file + os.replace) - a torn/partial write here
    would otherwise be readable by /last_run_summary as valid JSON garbage
    before the fresh process even starts."""
    tmp = RESULT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"written_at": time.time()}))
    os.replace(tmp, RESULT_FILE)


def _restart_control_center():
    """Kills and relaunches this process via systemd, so it picks up
    whatever PiFinder_Stellarmate code a just-finished run landed on - see
    _cc_restart_pending's own comment for why this process doesn't already
    pick that up on its own. The sleep gives the frontend one more /log or
    /state poll to observe _cc_restart_pending before this process dies -
    without it, a fast enough restart could kill the process before the
    browser ever learns a restart was coming, and it'd just look like a
    crash instead of the deliberate, communicated restart it actually is."""
    time.sleep(2)
    subprocess.run(["sudo", "systemctl", "restart", "pifinder-control-center.service"])


def _reader_thread(proc):
    # try/finally is load-bearing, not defensive style - see
    # _run_hardware_test()'s comment for the general shape of this bug
    # (found live there first, 2026-08-01). This is the MAIN install/update/
    # reinstall run's own reader - previously had no exception handling at
    # all, so a failure here (LOG_FILE unwritable, a readline() error, ...)
    # would've left _running stuck True forever, locking out every other
    # mutex-guarded action AND blocking any retry of the run itself.
    global _running, _exit_code, _phase_index, _reboot_needed, _cc_restart_pending
    # _last_mode is set by _start_run() before this thread starts and never
    # changes for the lifetime of this run - safe to read once, unlocked.
    phases = PHASES_INDI_ONLY if _last_mode == "indi_only" else PHASES
    try:
        with open(LOG_FILE, "w") as log_f:
            for line in iter(proc.stdout.readline, ""):
                log_f.write(line)
                log_f.flush()
                stripped = line.rstrip("\n")
                if stripped.startswith(PHASE_MARKER):
                    label = stripped[len(PHASE_MARKER):]
                    if label in phases:
                        with _lock:
                            _phase_index = max(_phase_index, phases.index(label))
                    continue  # phase markers are for the progress bar, not the log panel
                if stripped.startswith(REBOOT_MARKER):
                    with _lock:
                        _reboot_needed = stripped[len(REBOOT_MARKER):] == "true"
                    continue  # marker is for the Reboot button, not the log panel
                with _lock:
                    _lines.append(stripped)
        proc.wait()
        with _lock:
            _exit_code = proc.returncode
    except Exception as e:
        with _lock:
            _lines.append(f"[setup GUI] internal error: {e}")
            _exit_code = -1
    finally:
        with _lock:
            _running = False
            # Any successful run (fresh/reinstall/update, any mode) already ran
            # switch_branch.sh + self_update.sh at its very start, so it may have
            # landed on different PiFinder_Stellarmate code regardless of which
            # action was picked - always restart on success, not just for
            # specific actions.
            if _exit_code == 0:
                _cc_restart_pending = True
                _write_result_file()
    if _exit_code == 0:
        threading.Thread(target=_restart_control_center, daemon=True).start()


def _current_pifinder_stellarmate_branch():
    """Best-effort - None if this isn't a git checkout or the command fails,
    which the branch-picker UI treats as "can't tell, show nothing"."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
        return branch if result.returncode == 0 and branch else None
    except Exception:
        return None


def _start_run(action, branch=None, mode=None):
    global _running, _exit_code, _process, _lines, _phase_index, _reboot_needed, _last_action, _last_mode
    with _lock:
        if _running:
            return False, "A run is already in progress."
        if _mode_action_running:
            return False, "A PiFinder mode switch is still in progress - wait for it to finish first."
        if _hwtest_running:
            return False, "A hardware test is still in progress - wait for it to finish first."
        if _reset_running:
            return False, "A reset is still in progress - wait for it to finish first."
        if _uninstall_running:
            return False, "An uninstall is still in progress - wait for it to finish first."
        _lines = []
        _running = True
        _exit_code = None
        _phase_index = -1
        _reboot_needed = None
        _last_action = action
        _last_mode = mode or "full"
        cmd = ["bash", str(SETUP_SCRIPT), f"--action={action}"]
        if branch:
            cmd.append(f"--branch={branch}")
        if mode and mode != "full":
            cmd.append(f"--mode={mode}")
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


def _do_poweroff():
    # Deliberately a separate function/route from _do_shutdown() below, which
    # only stops this GUI's own web server process - this one powers off the
    # whole Pi, matching the "Shutdown Pi" button (distinct from "Close Setup").
    time.sleep(1)  # give the HTTP response a moment to reach the browser
    subprocess.run(["sudo", "poweroff"])


_server = None  # set in main(); used by /shutdown to stop serve_forever()


UNINSTALL_SCRIPT = REPO_ROOT / "bin" / "uninstall_pifinder_stellarmate.sh"


_uninstall_running = False  # True while an Uninstall run is in flight
_uninstall_lines = []  # progress log, shown in the shared Terminal tile


def _do_uninstall():
    # This server process runs from inside the very directory tree being
    # deleted (~/PiFinder_Stellarmate) - --selfmove copies the uninstall
    # script to /tmp first and continues from there, so the removal of this
    # repo (and this server's own pifinder-control-center.service) survives
    # this process's own directory disappearing out from under it. See the
    # script's own --selfmove header comment for the full rationale.
    #
    # Streams into _uninstall_lines exactly like _run_reset() (found live,
    # 2026-08-01, user: "der User muss sehen, was passiert") - the bulk of
    # the real work (stopping/disabling/removing units incl. this server's
    # own pifinder-control-center.service, removing INDI drivers, deleting
    # ~/PiFinder) runs in *this* subprocess, before --selfmove hands off to
    # the detached /tmp copy that deletes ~/PiFinder_Stellarmate itself -
    # that final step is no longer observable here once this process's own
    # unit gets stopped partway through, same as it always was; this only
    # changes how the part that IS still running gets surfaced (Popen +
    # incremental read instead of blocking subprocess.run(), same child
    # process either way - no change to what actually runs or how/when it
    # can get signaled).
    global _uninstall_running
    time.sleep(1)  # give the HTTP response a moment to reach the browser
    try:
        proc = subprocess.Popen(
            ["bash", str(UNINSTALL_SCRIPT), "--selfmove"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            with _lock:
                _uninstall_lines.append(line.rstrip("\n"))
        proc.wait()
    except Exception:
        pass
    finally:
        with _lock:
            _uninstall_running = False


def _run_reset():
    """Runs bin/uninstall_pifinder_stellarmate.sh --reset via Popen, streaming
    output into _reset_lines line-by-line so it shows live in the shared
    Terminal tile (like Install/Update/Test Hardware) - unlike the previous
    _do_reset(), which blocked on subprocess.run(capture_output=True) and
    only reported the result via a browser alert() at the end, with nothing
    visible in the terminal while it ran (found live during TC-PFSM-84-01,
    user: "There is no Terminal output at all"). --reset only touches
    ~/PiFinder's own venv/build state, never this repo's own directory -
    unlike _do_uninstall(), safe to run directly, no --selfmove/self-deletion
    concern."""
    # try/finally is load-bearing - see _run_hardware_test()'s comment for
    # why (found live 2026-08-01: the same missing-try/finally bug, there in
    # _run_hardware_test(), permanently locked out every other mutex-guarded
    # action). Popen()/readline() throwing here is less likely than a real
    # hardware check throwing, but "less likely" isn't "impossible."
    global _reset_running, _reset_exit_code
    try:
        proc = subprocess.Popen(
            ["bash", str(UNINSTALL_SCRIPT), "--reset"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            with _lock:
                _reset_lines.append(line.rstrip("\n"))
        proc.wait()
        with _lock:
            _reset_exit_code = proc.returncode
    except Exception as e:
        with _lock:
            _reset_lines.append(f"[setup GUI] internal error: {e}")
            _reset_exit_code = -1
    finally:
        with _lock:
            _reset_running = False


def _do_shutdown():
    time.sleep(1)  # give the HTTP response a moment to reach the browser
    # Persist "should NOT run after a reboot" the same way starting it (via
    # launch_setup_gui.sh's `systemctl enable --now`) persists "should run" -
    # mirrors systemd's own enabled-state instead of a separate flag file.
    # Best-effort: a failure here shouldn't block the actual shutdown below.
    subprocess.run(["sudo", "systemctl", "disable", "pifinder-control-center.service"])
    if _server is not None:
        _server.shutdown()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; the browser is the UI

    def _send_401(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{AUTH_REALM}"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _require_auth(self):
        """Checks HTTP Basic Auth against the stellarmate account's own
        password via PAM. Sends the 401 challenge itself and returns False
        if missing/invalid; caller should return immediately in that case.

        Rate-limited per client IP: after _AUTH_LOCKOUT_THRESHOLD *confirmed
        wrong-password* attempts within _AUTH_LOCKOUT_WINDOW seconds,
        further attempts are rejected immediately without calling PAM at
        all. Only counts requests that actually included a password AND
        got it wrong (never the plain "no Authorization header at all"
        case - see _auth_failures' own comment). The PAM call itself is
        additionally gated by _auth_semaphore, capping how many can run
        concurrently regardless of outcome - see that semaphore's own
        comment for why: an earlier version counted every *attempt* before
        knowing whether it would succeed, which under this page's ~15
        concurrent polling loops false-locked-out the *correct* password
        purely from concurrent timing, not from it actually being wrong -
        reproduced live (entering the right password worked, then locked
        out again a few seconds later, repeatedly)."""
        header = self.headers.get("Authorization", "")
        password = None
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
                _, _, password = decoded.partition(":")
            except Exception:
                password = None

        if password is None:
            self._send_401()
            return False

        client_ip = self.client_address[0]
        now = time.monotonic()
        with _lock:
            count, first_failure = _auth_failures.get(client_ip, (0, now))
            if now - first_failure >= _AUTH_LOCKOUT_WINDOW:
                count, first_failure = 0, now
            if count >= _AUTH_LOCKOUT_THRESHOLD:
                self._send_401()
                return False

        with _auth_semaphore:
            ok = pam_auth.verify_password(AUTH_USER, password)

        if ok:
            with _lock:
                _auth_failures.pop(client_ip, None)
            return True

        with _lock:
            count, first_failure = _auth_failures.get(client_ip, (0, now))
            if now - first_failure >= _AUTH_LOCKOUT_WINDOW:
                count, first_failure = 0, now
            _auth_failures[client_ip] = (count + 1, first_failure)
        self._send_401()
        return False

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # /state and /log (the only _send_json callers reachable without
        # auth, see _require_auth()) are meant to be freely reachable on the
        # LAN - CORS headers don't change that, they just let PiFinder's own
        # "PFSM" page (served from a different port, hence a
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

        # /api/uninstall_log exempted like /state and /log: the PAM check
        # inside _require_auth() adds real latency per request, and every
        # millisecond matters here specifically - this server stops its own
        # systemd unit partway through an uninstall run, so a slower/
        # authenticated poll has a worse chance of completing at all before
        # the connection drops (found live 2026-08-01).
        if parsed.path not in ("/state", "/log", "/page_version", "/api/uninstall_log") and not self._require_auth():
            return

        if parsed.path == "/page_version":
            self._send_json({"version": _page_version()})
            return

        if parsed.path == "/last_run_summary":
            self._send_json(_consume_result_file())
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

        if parsed.path == "/help.html":
            self._send_file(HELP_PAGE, "text/html; charset=utf-8")
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

        if parsed.path == "/project_logo.png":
            self._send_file(PROJECT_LOGO, "image/png")
            return

        if parsed.path == "/pifinder_welcome.png":
            self._send_file(_pifinder_welcome_image_red() or PIFINDER_WELCOME_IMAGE, "image/png")
            return

        if parsed.path == "/state":
            with _lock:
                running = _running
                exit_code = _exit_code
                phase_index = _phase_index
                reboot_needed = _reboot_needed
                last_action = _last_action
                restarting = _cc_restart_pending
                phases = PHASES_INDI_ONLY if _last_mode == "indi_only" else PHASES
                mode_action_running = _mode_action_running
                hwtest_running = _hwtest_running
                reset_running = _reset_running
                uninstall_running = _uninstall_running
            self._send_json(
                {
                    "existing_install": PIFINDER_DIR.is_dir(),
                    "running": running,
                    "exit_code": exit_code,
                    "phase_index": phase_index,
                    "phase_total": len(phases),
                    "phase_label": phases[phase_index] if phase_index >= 0 else None,
                    "phases": phases,
                    "setup_script_path": str(SETUP_SCRIPT),
                    "ips": _get_all_ips(),
                    "port": PORT,
                    "reboot_needed": reboot_needed,
                    "action": last_action,
                    "current_branch": _current_pifinder_stellarmate_branch(),
                    "restarting": restarting,
                    # Diagnostic - lets a stuck mutex guard (any action
                    # rejected with "X is in progress" when nothing visibly
                    # is) be root-caused from the outside instead of guessed
                    # at (found live, 2026-08-01: a rejected Uninstall click
                    # with no way to tell which flag was actually stuck).
                    "mode_action_running": mode_action_running,
                    "hwtest_running": hwtest_running,
                    "reset_running": reset_running,
                    "uninstall_running": uninstall_running,
                }
            )
            return

        if parsed.path == "/api/system_load":
            self._send_json(_system_load_status())
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
                {
                    "mode": mode,
                    "transitioning": transitioning,
                    "error": error,
                    "target": target,
                    # Raw systemd state (#192) - lets the OLED-mirror wait
                    # overlay distinguish "service not started"/"failed" from
                    # "started, just not answering /image yet" instead of a
                    # single generic message throughout.
                    "real_service_state": _real_service_state(),
                }
            )
            return

        if parsed.path == "/api/display_bridge":
            self._send_json({"enabled": _lcd_overlay_active()})
            return

        if parsed.path == "/api/keyboard_bridge":
            self._send_json({"running": _keyboard_bridge_running()})
            return

        if parsed.path == "/api/mount_bridge_status":
            # Phase 1 of the Mount Bridge web integration (see
            # docs/concepts/mount_bridge_web_integration.md) - read-only
            # snapshot via indi_client.py's minimal INDI client, talking
            # directly to indiserver (default 127.0.0.1:7624). Coupling
            # mode/drift are only ever populated once the device is
            # actually connected (BRIDGE_MODE/DRIFT_STATUS aren't defined
            # by the driver until then - verified against
            # indi_pifinder_bridge's own updateProperties()) - "running":
            # true with everything else null/None is the normal, expected
            # shape for "loaded but not yet connected", not a bug.
            global _mb_last_running
            try:
                # Longer timeout than indi_client's own default (3.0s/1.5s) -
                # deliberately scoped to ONLY this passive, periodic
                # background poll (called every 20s from the frontend, see
                # setInterval in status_page.html), not the module-wide
                # DEFAULT_TIMEOUT every interactive action (Connect/
                # Disconnect, driver toggles, coupling changes) also relies
                # on - those stay snappy on a genuine failure. Found live
                # (2026-07-29): indiserver occasionally takes longer than 3s
                # to answer a getProperties request for "PiFinder Mount
                # Bridge" specifically while it's busy relaying a burst of
                # unrelated property updates from the mount driver - proven
                # harmless via direct polling of the same properties during
                # several live occurrences (Mount Bridge's own drift
                # computation, and the underlying PiFinder/mount position
                # data, kept updating throughout; Ekos was seen actively
                # correcting the mount at the same moment this poll came back
                # empty). Not a real disconnect, just this poll's own
                # patience being too short for an otherwise-healthy system.
                status = indi_client.mount_bridge_status(
                    timeout=indi_client.TIMEOUT_BACKGROUND_POLL,
                    device_timeout=indi_client.DEVICE_TIMEOUT_BACKGROUND_POLL,
                )
            except indi_client.INDIClientError as e:
                status = {"running": False, "error": str(e)}
                _mb_log(f"status check failed: {e}")
            if status.get("running") != _mb_last_running:
                _mb_log(
                    "Mount Bridge status changed: running={} bridge_connected={} "
                    "active_mount={}".format(
                        status.get("running"), status.get("bridge_connected"), status.get("active_mount")
                    )
                )
                _mb_last_running = status.get("running")
            self._send_json(status)
            return

        if parsed.path == "/api/mount_bridge_drift":
            # Fast, best-effort companion to /api/mount_bridge_status above -
            # added because tying the drift readout to that endpoint's 20s
            # cadence (deliberately slow, see the comment above) made it feel
            # "sluggish" and out of sync with the mount's actual movement
            # (live feedback, 2026-07-29). Polled every few seconds from the
            # frontend (see refreshMbDrift() in status_page.html); a miss
            # here just skips one number update - it never touches the
            # connection-status miss-streak/unconfirmed gate, so a short
            # timeout is fine and doesn't risk reintroducing the flapping
            # that the longer timeout above was chosen to avoid.
            try:
                drift = indi_client.mount_bridge_drift()
            except indi_client.INDIClientError as e:
                drift = {"running": False, "error": str(e)}
            self._send_json(drift)
            return

        if parsed.path == "/api/webmanager/profiles":
            # Phase 2 of the Mount Bridge web integration (see
            # docs/concepts/mount_bridge_web_integration.md) - UC3 (profile
            # selection, read-only list) + server running-state, so the
            # frontend can show which profile is actually active right now.
            try:
                profiles = webmanager_client.list_profiles()
                status = webmanager_client.server_status()
            except webmanager_client.WebManagerError as e:
                self._send_json({"error": str(e)}, status=502)
                return
            self._send_json(
                {
                    "profiles": [p.get("name") for p in profiles],
                    "running": status["running"],
                    "active_profile": status["active_profile"],
                }
            )
            return

        if parsed.path == "/api/webmanager/pifinder_drivers":
            # UC4/UC5 groundwork: whether PiFinder LX200 / Mount Bridge are
            # currently in the given profile - drives the two toggle
            # buttons' checked state.
            qs = parse_qs(parsed.query)
            profile = qs.get("profile", [""])[0]
            if not profile:
                self._send_json({"error": "missing 'profile' query param"}, status=400)
                return
            try:
                self._send_json(webmanager_client.pifinder_driver_status(profile))
            except webmanager_client.WebManagerError as e:
                self._send_json({"error": str(e)}, status=502)
            return

        if parsed.path == "/api/webmanager/other_drivers":
            # Phase 3 (UC5): candidates for "which loaded driver is the
            # mount" - every profile driver except the two PiFinder ones,
            # each now flagged is_telescope so the frontend can auto-select
            # an unambiguous single candidate (see other_profile_drivers()'s
            # own docstring for the one real exception this needs to
            # account for).
            qs = parse_qs(parsed.query)
            profile = qs.get("profile", [""])[0]
            if not profile:
                self._send_json({"error": "missing 'profile' query param"}, status=400)
                return
            try:
                self._send_json({"drivers": webmanager_client.other_profile_drivers(profile)})
            except webmanager_client.WebManagerError as e:
                self._send_json({"error": str(e)}, status=502)
            return

        if parsed.path == "/api/kstars_webmanager_link":
            # Setup-wizard step: is this profile's *KStars-side* Equipment
            # Profile actually set to use the local Web Manager? This is a
            # separate thing from the Web-Manager-side profile this feature
            # otherwise manages - KStars keeps its own copy in its own
            # SQLite DB (read-only check, see _kstars_webmanager_link_status()
            # docstring for why this is never auto-fixed).
            qs = parse_qs(parsed.query)
            profile = qs.get("profile", [""])[0]
            if not profile:
                self._send_json({"error": "missing 'profile' query param"}, status=400)
                return
            self._send_json(_kstars_webmanager_link_status(profile))
            return

        if parsed.path == "/api/ekos_indi_status":
            # Gates the Coupling presets (see status_page.html's
            # isFullyReadyForCoupling()): a Coupling command only matters if
            # it reaches the same Ekos session the user (or the StellarMate
            # App) is actually observing through - see
            # _ekos_indi_status()'s own docstring.
            self._send_json(_ekos_indi_status())
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

        if parsed.path == "/api/debug_solve":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            self._send_json(_pifinder_solve_status(port) or {"debug_solve": None})
            return

        if parsed.path == "/api/hardware_test_log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _hwtest_lines[position:]
                new_position = len(_hwtest_lines)
                running = _hwtest_running
                result = _hwtest_result
            self._send_json(
                {"lines": new_lines, "position": new_position, "running": running, "result": result}
            )
            return

        if parsed.path == "/api/reset_log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _reset_lines[position:]
                new_position = len(_reset_lines)
                running = _reset_running
                exit_code = _reset_exit_code
            self._send_json(
                {"lines": new_lines, "position": new_position, "running": running, "exit_code": exit_code}
            )
            return

        if parsed.path == "/api/uninstall_log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _uninstall_lines[position:]
                new_position = len(_uninstall_lines)
                running = _uninstall_running
            self._send_json({"lines": new_lines, "position": new_position, "running": running})
            return

        if parsed.path == "/api/mount_bridge_log":
            qs = parse_qs(parsed.query)
            position = int(qs.get("position", ["0"])[0])
            with _lock:
                new_lines = _mb_lines[position:]
                new_position = len(_mb_lines)
            self._send_json({"lines": new_lines, "position": new_position})
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
                restarting = _cc_restart_pending
                phases = PHASES_INDI_ONLY if _last_mode == "indi_only" else PHASES
            self._send_json(
                {
                    "lines": new_lines,
                    "position": new_position,
                    "running": running,
                    "exit_code": exit_code,
                    "phase_index": phase_index,
                    "phase_total": len(phases),
                    "phase_label": phases[phase_index] if phase_index >= 0 else None,
                    "reboot_needed": reboot_needed,
                    "action": last_action,
                    "restarting": restarting,
                }
            )
            return

        self.send_error(404)

    def do_POST(self):
        global _hwtest_running, _mode_action_running, _reset_running, _reset_exit_code, _uninstall_running
        parsed = urlparse(self.path)

        # /shutdown stays open: PiFinder's PFSM page (a different
        # origin/port) cross-origin-POSTs here to stop the installer, and
        # cross-origin requests never carry this page's cached Basic Auth
        # credentials. Shutting the installer down isn't destructive, unlike
        # /start and /reboot below, which do require auth.
        if parsed.path != "/shutdown" and not self._require_auth():
            return

        if parsed.path == "/start":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            # "cancel" isn't accepted here - it's still a real interactive-
            # terminal menu option in pifinder_stellarmate_setup.sh, but the
            # GUI's own Cancel button (which just round-tripped through the
            # whole script to print one line and exit 0, then shut the
            # server down anyway) is gone in favor of "Close Setup" being
            # shown directly on the choices screen too.
            if action not in ("fresh", "reinstall", "update"):
                self._send_json({"started": False, "error": f"invalid action '{action}'"}, status=400)
                return
            # branch is optional (see bin/switch_branch.sh) - only a plain
            # branch-name shape is accepted here, since this becomes a shell
            # argument; git's own naming rules already rule out most of the
            # dangerous characters, but this is a defense-in-depth check, not
            # a git-refname validator.
            branch = qs.get("branch", [""])[0].strip()
            if branch and not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
                self._send_json({"started": False, "error": f"invalid branch name '{branch}'"}, status=400)
                return
            # --mode=indi_only (see docs/concepts/setup_indi_only_install_mode.md,
            # R1) - installs just the INDI stack, no PiFinder hardware/
            # application. Optional; omitted/"full" is today's unchanged behavior.
            mode = qs.get("mode", ["full"])[0].strip()
            if mode not in ("full", "indi_only"):
                self._send_json({"started": False, "error": f"invalid mode '{mode}'"}, status=400)
                return
            started, error = _start_run(action, branch or None, mode)
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

        if parsed.path == "/poweroff":
            with _lock:
                if _running:
                    self._send_json({"powering_off": False, "error": "A run is still in progress."}, status=409)
                    return
            self._send_json({"powering_off": True})
            threading.Thread(target=_do_poweroff, daemon=True).start()
            return

        if parsed.path == "/uninstall":
            with _lock:
                if _running or _mode_action_running or _hwtest_running or _reset_running or _uninstall_running:
                    self._send_json(
                        {"uninstalling": False, "error": "An install/update run, mode switch, hardware test, reset, or uninstall is in progress - wait for it to finish first."},
                        status=409,
                    )
                    return
                _uninstall_lines.clear()
                _uninstall_running = True
            self._send_json({"uninstalling": True})
            threading.Thread(target=_do_uninstall, daemon=True).start()
            return

        if parsed.path == "/reset":
            with _lock:
                if _running or _mode_action_running or _hwtest_running or _reset_running or _uninstall_running:
                    self._send_json(
                        {"started": False, "error": "An install/update run, mode switch, hardware test, reset, or uninstall is in progress - wait for it to finish first."},
                        status=409,
                    )
                    return
                _reset_lines.clear()
                _reset_running = True
                _reset_exit_code = None
            self._send_json({"started": True})
            threading.Thread(target=_run_reset, daemon=True).start()
            return

        if parsed.path == "/api/pifinder_mode":
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
                if _hwtest_running:
                    self._send_json({"started": False, "error": "A hardware test is in progress - wait for it to finish first."}, status=409)
                    return
                if _reset_running:
                    self._send_json({"started": False, "error": "A reset is in progress - wait for it to finish first."}, status=409)
                    return
                if _uninstall_running:
                    self._send_json({"started": False, "error": "An uninstall is in progress - wait for it to finish first."}, status=409)
                    return
                _mode_action_running = True
            script_arg = "start" if action == "enable_fake" else "stop"
            threading.Thread(target=_run_fake_mode_action, args=(script_arg,), daemon=True).start()
            self._send_json({"started": True})
            return

        if parsed.path == "/api/pifinder_service":
            # Direct pifinder.service (Real Mode) control - shouldn't
            # normally be needed (the Real/Fake Mode toggle above already
            # manages it via fake_mode.sh), but useful to recover a
            # crashed/hung Real Mode instance without a full mode
            # round-trip. Deliberately does NOT touch Fake Mode's own
            # separate process (pf_remote.py) - this is only ever the
            # systemd unit.
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            if action not in ("start", "stop", "restart"):
                self._send_json({"success": False, "error": f"invalid action '{action}'"}, status=400)
                return
            with _lock:
                if _running or _mode_action_running or _hwtest_running or _reset_running or _uninstall_running:
                    self._send_json(
                        {"success": False, "error": "An install/update run, mode switch, hardware test, reset, or uninstall is in progress - wait for it to finish first."},
                        status=409,
                    )
                    return
            try:
                # daemon-reload first: systemd caches a unit's parsed config
                # in memory and does NOT re-read a changed file on disk on
                # its own before start/restart (only warns "Unit file
                # changed on disk" in its log) - without this, a button
                # click right after an update could restart the OLD,
                # already-loaded config instead of whatever's actually in
                # /etc/systemd/system/pifinder.service right now (found live
                # investigating #139's Nice=/CPUWeight= rollout - see that
                # change's own commit for the underlying finding).
                subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True, text=True, timeout=10)
                result = subprocess.run(
                    ["sudo", "systemctl", action, "pifinder.service"],
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                self._send_json({"success": False, "error": f"systemctl {action} pifinder.service timed out"}, status=502)
                return
            if result.returncode != 0:
                self._send_json({"success": False, "error": result.stderr.strip() or f"systemctl {action} failed"}, status=502)
                return
            self._send_json({"success": True})
            return

        if parsed.path == "/api/debug_solve":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            self._send_json({"success": _pifinder_toggle_debug_solve(port)})
            return

        if parsed.path == "/api/pifinder_key":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            key = qs.get("key", [""])[0]
            self._send_json({"success": _pifinder_send_key(port, key)})
            return

        if parsed.path == "/api/fake_solve_disable":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            self._send_json({"success": _pifinder_disable_fake_solve(port)})
            return

        if parsed.path == "/api/fake_solve_enable_from_mount":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            ok, err = _pifinder_enable_fake_solve_from_mount(port)
            self._send_json({"success": ok, "error": err})
            return

        if parsed.path == "/api/fake_solve_set":
            qs = parse_qs(parsed.query)
            port = qs.get("port", [""])[0]
            try:
                ra_deg = float(qs.get("ra", [""])[0])
                dec_deg = float(qs.get("dec", [""])[0])
            except (ValueError, IndexError):
                self._send_json({"success": False, "error": "ra/dec must be numeric degrees"}, status=400)
                return
            ok, err = _pifinder_set_fake_solve(port, ra_deg, dec_deg)
            self._send_json({"success": ok, "error": err})
            return

        if parsed.path == "/api/hardware_test":
            with _lock:
                if _hwtest_running:
                    self._send_json({"started": False, "error": "A hardware test is already in progress."}, status=409)
                    return
                if _running or _mode_action_running:
                    self._send_json(
                        {"started": False, "error": "An install/update run or mode switch is in progress - wait for it to finish first."},
                        status=409,
                    )
                    return
                if _reset_running:
                    self._send_json({"started": False, "error": "A reset is in progress - wait for it to finish first."}, status=409)
                    return
                if _uninstall_running:
                    self._send_json({"started": False, "error": "An uninstall is in progress - wait for it to finish first."}, status=409)
                    return
                _hwtest_running = True
            threading.Thread(target=_run_hardware_test, daemon=True).start()
            self._send_json({"started": True})
            return

        if parsed.path == "/api/display_bridge":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            if action not in ("start", "stop"):
                self._send_json({"success": False, "error": f"invalid action '{action}'"}, status=400)
                return
            with _lock:
                if _mode_action_running or _running or _hwtest_running or _reset_running or _uninstall_running:
                    self._send_json({"success": False, "error": "An install/update, mode switch, hardware test, reset, or uninstall is in progress - wait for it to finish first."}, status=409)
                    return
            want_enabled = action == "start"
            if _lcd_overlay_active() == want_enabled:
                self._send_json({"success": True, "rebooting": False})
                return
            ok, error = _set_lcd_overlay(want_enabled)
            self._send_json({"success": ok, "error": error, "rebooting": ok})
            return

        if parsed.path == "/api/keyboard_bridge":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            if action not in ("start", "stop"):
                self._send_json({"success": False, "error": f"invalid action '{action}'"}, status=400)
                return
            if action == "stop":
                _stop_keyboard_bridge()
                self._send_json({"success": True})
                return
            if _keyboard_bridge_running():
                self._send_json({"success": True})
                return
            ok, error = _start_keyboard_bridge()
            self._send_json({"success": ok, "error": error})
            return

        if parsed.path == "/api/webmanager/server":
            # UC2: start/stop the selected profile's indiserver instance -
            # scoped in the concept doc from the start but never actually
            # wired up until live testing showed why it matters: indiserver
            # only reads a profile's driver list at *startup*, so adding/
            # removing drivers via UC4/UC5 while the profile keeps running
            # never takes effect on the live indiserver until it's restarted
            # (found live: "LX200 OnStep" added via Web Manager stayed in
            # the profile's DB row but never actually started as a process).
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            profile = qs.get("profile", [""])[0]
            if action not in ("start", "stop"):
                self._send_json({"success": False, "error": "expected ?action=start|stop"}, status=400)
                return
            if action == "start" and not profile:
                self._send_json({"success": False, "error": "missing 'profile' query param"}, status=400)
                return
            _mb_log(f"{'starting' if action == 'start' else 'stopping'} profile{' ' + profile if profile else ''}...")
            try:
                if action == "start":
                    webmanager_client.start_server(profile)
                else:
                    webmanager_client.stop_server()
            except webmanager_client.WebManagerError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log(f"  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/webmanager/pifinder_drivers":
            # UC4: add/remove ONLY PiFinder LX200 / PiFinder Mount Bridge to/
            # from a profile - no other profile editing. See
            # webmanager_client.py's module docstring for why removal uses a
            # delete-and-recreate-the-profile workaround (a StellarMate Web
            # Manager quirk found and verified live while building this -
            # not present in the open-source project it's based on).
            qs = parse_qs(parsed.query)
            profile = qs.get("profile", [""])[0]
            driver = qs.get("driver", [""])[0]
            action = qs.get("action", [""])[0]
            # add_remote (lx200 only): use a PiFinder LX200 running on
            # another device, via INDI's own remote-driver mechanism - see
            # docs/concepts/remote_indi_coupling_split_host.md (R-CH1).
            valid = (
                profile
                and (
                    (driver in ("lx200", "bridge") and action in ("add", "remove"))
                    or (driver == "lx200" and action == "add_remote")
                )
            )
            if not valid:
                self._send_json(
                    {"success": False,
                     "error": "expected ?profile=<name>&driver=lx200|bridge&action=add|remove"
                              " (or driver=lx200&action=add_remote&remote=<host[:port]>)"},
                    status=400,
                )
                return
            remote_spec = None
            if action == "add_remote":
                remote_spec = qs.get("remote", [""])[0].strip()
                # Hostname or IP, optional :port - becomes part of a Web
                # Manager profile entry, so keep the shape strict.
                if not re.fullmatch(r"[A-Za-z0-9._-]+(:\d{1,5})?", remote_spec):
                    self._send_json(
                        {"success": False, "error": f"invalid remote host '{remote_spec}' (expected host or host:port)"},
                        status=400,
                    )
                    return
                if ":" not in remote_spec:
                    remote_spec += ":7624"

            if driver == "lx200":
                lx200_state = {"add": "local", "remove": "absent", "add_remote": "remote"}[action]
                def setter(prof, _present):
                    webmanager_client.set_pifinder_lx200_state(prof, lx200_state, remote=remote_spec)
            else:
                setter = webmanager_client.set_pifinder_bridge
            driver_label = "PiFinder LX200" if driver == "lx200" else "PiFinder Mount Bridge"
            if action == "add_remote":
                driver_label = f"PiFinder LX200 (remote {remote_spec})"

            # indiserver only reads a profile's driver list at startup - a
            # driver added/removed here never takes effect on an already-
            # running indiserver until it's restarted (found live: "LX200
            # OnStep" added via Web Manager sat in the profile's DB row for
            # over an hour without ever actually starting as a process).
            # Rather than expect the user to remember "stop, change, start"
            # as three separate steps, do it automatically here whenever
            # this profile is the one currently running - one click, fully
            # visible in the log below.
            try:
                srv_status = webmanager_client.server_status()
            except webmanager_client.WebManagerError:
                srv_status = {"running": False, "active_profile": None}
            was_running = srv_status["running"] and srv_status["active_profile"] == profile

            if was_running:
                _mb_log(f"stopping profile '{profile}' (needed to apply the driver change)...")
                try:
                    webmanager_client.stop_server()
                except webmanager_client.WebManagerError as e:
                    _mb_log(f"  failed: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return
                _mb_log(f"  done.")

            _mb_log(f"{'add' if action != 'remove' else 'remove'} {driver_label} {'to' if action != 'remove' else 'from'} profile '{profile}'...")
            try:
                setter(profile, action == "add")
            except webmanager_client.WebManagerError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log(f"  done.")

            if was_running:
                _mb_log(f"restarting profile '{profile}'...")
                try:
                    webmanager_client.start_server(profile)
                except webmanager_client.WebManagerError as e:
                    _mb_log(f"  failed: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return
                # Wait for indiserver to actually be back up before this
                # request returns - otherwise the frontend's immediate
                # post-action refresh can land in the brief window where
                # Web Manager reports "not running" yet, flashing a
                # confusing "profile not running" state that then
                # self-corrects a moment later (seen live, 2026-07-25).
                deadline = time.monotonic() + 8.0
                while time.monotonic() < deadline:
                    try:
                        status = webmanager_client.server_status()
                    except webmanager_client.WebManagerError:
                        status = {"running": False, "active_profile": None}
                    if status["running"] and status["active_profile"] == profile:
                        break
                    time.sleep(0.3)
                _mb_log(f"  done.")

            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_active_devices":
            # Phase 3 (UC5): sets PiFinder Mount Bridge's ACTIVE_DEVICES to
            # point at the user-selected mount driver. ACTIVE_PIFINDER is
            # always re-asserted as "PiFinder LX200" (its own default -
            # there is exactly one PiFinder LX200 device, no need to make
            # this configurable) rather than left to chance.
            qs = parse_qs(parsed.query)
            mount = qs.get("mount", [""])[0]
            unlink = qs.get("action", [""])[0] == "unlink"
            if not mount and not unlink:
                self._send_json({"success": False, "error": "missing 'mount' query param"}, status=400)
                return
            _mb_log("unlinking Mount Bridge's mount..." if unlink else f"linking Mount Bridge to mount '{mount}'...")
            try:
                indi_client.set_mount_bridge_active_devices("PiFinder LX200", "" if unlink else mount)
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            # Persist to the driver's own config file (CONFIG_PROCESS.CONFIG_SAVE) -
            # set_text() above only changes the *live* property. Without this, any
            # later reconnect (driver restart, Ekos profile restart, ...) silently
            # reloads whatever ACTIVE_MOUNT was saved on disk from a much earlier
            # session, undoing this selection with no indication anything reverted -
            # found live (#158) chasing a "Mount is source" test that kept reading
            # from a stale mount device not even in the current profile. Best-effort:
            # the live selection above already took effect either way, so a save
            # failure here is logged, not fatal to the request.
            try:
                indi_client.set_switch("PiFinder Mount Bridge", "CONFIG_PROCESS", "CONFIG_SAVE")
            except indi_client.INDIClientError as e:
                _mb_log(f"  warning: active-devices selection applied but not saved to disk: {e}")
            _mb_log(f"  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_connect":
            # Phase 3 (UC5/UC6 groundwork): generic CONNECTION.CONNECT/
            # DISCONNECT trigger - works for PiFinder LX200, PiFinder Mount
            # Bridge, or whichever mount driver the user selected, since
            # CONNECTION is a standard property every INDI driver has.
            # Connection *parameters* (serial port, baud, TCP host) are
            # never touched here for the user's own mount - see the concept
            # doc's explicit non-goal. "PiFinder LX200" is the one
            # exception: its target is always this project's own
            # pos_server.py (127.0.0.1:4030), a fixed constant, not
            # something to expect the user to configure by hand - see
            # ensure_pifinder_lx200_tcp()'s own docstring for why (left on
            # its default of a shared serial port, it competes with the
            # user's real mount driver for the same USB adapter). The
            # not-currently-defined auto-heal (restart the profile, retry)
            # only applies to connecting - disconnecting a device that
            # isn't even loaded is just an plain error, nothing to recover.
            qs = parse_qs(parsed.query)
            device = qs.get("device", [""])[0]
            profile = qs.get("profile", [""])[0]
            disconnecting = qs.get("action", [""])[0] == "disconnect"
            if not device:
                self._send_json({"success": False, "error": "missing 'device' query param"}, status=400)
                return

            if disconnecting:
                _mb_log(f"disconnecting '{device}'...")
                try:
                    indi_client.disconnect_device(device)
                except indi_client.INDIClientError as e:
                    _mb_log(f"  failed: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return
                _mb_log(f"  done.")
                self._send_json({"success": True})
                return

            # Most common cause of "not currently defined" here, seen live:
            # the device was added to the profile (by this UI or directly in
            # Web Manager) after indiserver was last started, so it was
            # never actually spawned/proxied as a process - INDI's way of
            # saying "I've never heard of this device". Rather than surface
            # that cryptic message, restart the profile once and retry
            # automatically - the user shouldn't have to know/remember that
            # indiserver needs a restart to pick up driver-list changes.
            # Applies equally to PiFinder LX200's own TCP-connection-settings
            # check below (ensure_pifinder_lx200_tcp() raises the identical
            # error, and hit this exact gap live on a REMOTE PiFinder LX200
            # entry, 2026-07-29: the local indiserver needs a moment longer
            # to finish proxying a remote device's properties than a local
            # one, and this check used to fail hard before ever reaching the
            # retry logic below - restart_and_retry()'s own poll (not a flat
            # sleep) already tolerates that extra beat, no separate timeout
            # needed for the remote case specifically.
            def restart_and_retry(retry_fn):
                # This restart doesn't just affect `device` - it kills and
                # respawns every driver process in the profile, so Mount
                # Bridge's own ACTIVE_DEVICES link (if it had one) is wiped
                # along with everything else. Found live: this left the tile
                # showing "not coupled" for up to 30s afterward (until the
                # unrelated periodic poll noticed and re-linked it), which
                # looked like step 4 "hanging" even though nothing was
                # actually stuck - just waiting on a poll that had no idea a
                # restart had just happened. Capture the link now, while
                # it's still there, so it can be restored immediately after
                # rather than left to that poll's own schedule.
                mb_before = indi_client.mount_bridge_status()
                previous_mount = mb_before.get("active_mount") if mb_before.get("running") else None
                previous_pifinder = mb_before.get("active_pifinder") if mb_before.get("running") else None

                _mb_log(f"'{device}' not loaded yet - restarting profile '{profile}' to pick it up...")
                try:
                    webmanager_client.stop_server()
                    webmanager_client.start_server(profile)
                except webmanager_client.WebManagerError as e:
                    _mb_log(f"  restart failed: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return False
                # indiserver needs a moment to actually fork/proxy the
                # driver and complete its own startup handshake before
                # it'll answer getProperties for it - poll briefly instead
                # of a flat sleep.
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if indi_client.get_properties(device=device, timeout=indi_client.TIMEOUT_QUICK_RETRY).get(device):
                        break
                    time.sleep(0.3)
                _mb_log(f"  restarted. retrying...")
                try:
                    retry_fn()
                except indi_client.INDIClientError as e:
                    _mb_log(f"  still failed: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return False
                _mb_log(f"  done.")
                if previous_mount:
                    _mb_log(f"  restoring Mount Bridge's link to '{previous_mount}' (lost in the restart above)...")
                    try:
                        indi_client.set_mount_bridge_active_devices(previous_pifinder or "PiFinder LX200", previous_mount)
                        _mb_log(f"  done.")
                    except indi_client.INDIClientError as e:
                        # Not fatal to this connect call - the retry itself
                        # already succeeded above. The periodic poll's own
                        # auto-link will still catch this as a fallback.
                        _mb_log(f"  failed: {e} (will retry via the periodic auto-link check instead)")
                return True

            if device == "PiFinder LX200":
                try:
                    indi_client.ensure_pifinder_lx200_tcp()
                except indi_client.INDIClientError as e:
                    if "not currently defined" not in str(e) or not profile:
                        _mb_log(f"could not verify PiFinder LX200's connection settings: {e}")
                        self._send_json({"success": False, "error": str(e)}, status=502)
                        return
                    if not restart_and_retry(indi_client.ensure_pifinder_lx200_tcp):
                        return  # restart_and_retry() already sent the error response

            _mb_log(f"connecting '{device}'...")
            try:
                indi_client.connect_device(device)
                _mb_log(f"  done.")
                self._send_json({"success": True})
                return
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                if "not currently defined" not in str(e) or not profile:
                    self._send_json({"success": False, "error": str(e)}, status=502)
                    return

            if not restart_and_retry(lambda: indi_client.connect_device(device)):
                return  # restart_and_retry() already sent the error response
            self._send_json({"success": True})
            return

        if parsed.path == "/api/ekos_start_profile":
            # Explicit, user-initiated only (Autoconnect step 5) - see
            # _ekos_start_profile()'s own docstring for why this is safe to
            # do here despite _ekos_indi_status() elsewhere deliberately
            # never touching Ekos from a passive poll.
            qs = parse_qs(parsed.query)
            profile = qs.get("profile", [""])[0]
            if not profile:
                self._send_json({"attempted": False, "reason": "missing 'profile' query param"}, status=400)
                return
            self._send_json(_ekos_start_profile(profile))
            return

        if parsed.path == "/api/mount_bridge_coupling":
            # Phase 4: the three one-click Coupling presets, plus "off" (the
            # Decouple button - no dedicated preset button of its own, see
            # onDecoupleClick()). mode is "verify_alert"|"auto_correct"|
            # "goto_forward"|"off" (short form here, translated to the
            # driver's own MODE_* constants in indi_client.set_coupling_
            # mode()). threshold/action are only meaningful for
            # verify_alert/auto_correct - harmless if sent for goto_forward
            # or off, indi_client.py ignores them there.
            qs = parse_qs(parsed.query)
            mode_arg = qs.get("mode", [""])[0]
            mode_map = {
                "verify_alert": "MODE_VERIFY_ALERT",
                "auto_correct": "MODE_AUTO_CORRECT",
                "goto_forward": "MODE_GOTO_FORWARD",
                "off": "MODE_OFF",
            }
            if mode_arg not in mode_map:
                self._send_json(
                    {"success": False, "error": "expected ?mode=verify_alert|auto_correct|goto_forward|off"},
                    status=400,
                )
                return
            threshold_arg = qs.get("threshold", [""])[0]
            action_arg = qs.get("action", [""])[0]
            try:
                threshold = _parse_threshold(threshold_arg) if threshold_arg else None
            except ValueError:
                self._send_json({"success": False, "error": f"invalid threshold '{threshold_arg}'"}, status=400)
                return
            _mb_log(
                f"setting coupling mode {mode_arg} (threshold={threshold_arg or 'default'}, "
                f"action={action_arg or 'default'})..."
            )
            try:
                indi_client.set_coupling_mode(
                    mode_map[mode_arg],
                    drift_threshold=threshold,
                    correction_action=action_arg or None,
                )
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log(f"  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_threshold":
            # Standalone threshold push, separate from /api/mount_bridge_coupling
            # above - added because the threshold input field previously only
            # ever reached the driver via a coupling-preset button click, so
            # editing it while Verify/Alert or Auto-correct was already active
            # silently had no effect even though the tile's own drift caption
            # (client-side, from the same input field) made it look like it
            # had (found live, 2026-07-29). The frontend only calls this while
            # one of those two modes is already active - see status_page.html's
            # applyThresholdChange().
            qs = parse_qs(parsed.query)
            threshold_arg = qs.get("threshold", [""])[0]
            try:
                threshold = _parse_threshold(threshold_arg)
            except ValueError:
                self._send_json({"success": False, "error": f"invalid threshold '{threshold_arg}'"}, status=400)
                return
            _mb_log(f"setting drift threshold to {threshold}...")
            try:
                indi_client.set_drift_threshold(threshold)
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log(f"  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_manual_sync":
            # Manual, immediate one-shot: syncs the mount to PiFinder's
            # current solved position right now, regardless of Coupling
            # mode - the one case none of the presets react to on their own
            # is the mount having been moved entirely by hand (no Goto at
            # all involved).
            _mb_log("syncing mount from PiFinder's current position...")
            try:
                indi_client.trigger_manual_sync()
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log("  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_abort":
            # Emergency stop - see #179. Two steps, in this order:
            # 1. ABORT_MOUNT stops the mount's *current* physical motion
            #    immediately.
            # 2. Coupling -> Off (same as Decouple/onDecoupleClick()) stops
            #    Mount Bridge from re-triggering another correction on its
            #    next poll tick - found live 2026-08-07: sending ABORT
            #    alone stopped the mount for a moment, then Auto-correct/
            #    Goto-Forward just synced and re-slewed it right back
            #    toward the same target, since nothing about the drift/mode
            #    that caused the original correction had changed. A stop
            #    button that only pauses for one tick isn't a stop button.
            _mb_log("EMERGENCY STOP: sending ABORT to the mount...")
            try:
                indi_client.trigger_abort_mount()
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log("  decoupling (Coupling -> Off) so nothing re-triggers another correction...")
            try:
                indi_client.set_coupling_mode("MODE_OFF")
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log("  done.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_multialign_start":
            # #191/#217: kicks off a Multi-Point Alignment sequence. Fresh
            # candidates are fetched by the driver itself on every Start
            # (fetchAlignmentCandidates()) - nothing to pass from here.
            # Independent of Coupling mode, same as Manual Sync/Abort above.
            _mb_log("starting Multi-Point Alignment...")
            try:
                indi_client.trigger_multipoint_align_start()
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log("  started - see the Alignment progress readout for per-point status.")
            self._send_json({"success": True})
            return

        if parsed.path == "/api/mount_bridge_multialign_stop":
            # #217: verified live against Telescope Simulator that this
            # correctly aborts an in-progress sequence at the INDI level
            # (stopMultiPointAlignment() -> abortMount()) - the earlier
            # "can't abort" report traced to this button not existing in the
            # GUI at all, not to a backend fault.
            _mb_log("stopping Multi-Point Alignment...")
            try:
                indi_client.trigger_multipoint_align_stop()
            except indi_client.INDIClientError as e:
                _mb_log(f"  failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=502)
                return
            _mb_log("  done.")
            self._send_json({"success": True})
            return

        self.send_error(404)


def main():
    # 0.0.0.0: reachable from other devices on the LAN, not just this Pi.
    # The page itself and the destructive actions (delete + reinstall, sudo
    # reboot) require the stellarmate account's own password (see
    # _require_auth()); /state, /log, /shutdown stay open (see their own
    # comments). Do not expose this port beyond a private home/observatory
    # LAN regardless.
    global _server, _hwtest_running
    _server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PiFinder setup GUI listening on http://0.0.0.0:{PORT}/ (all interfaces)")
    # Run Test Hardware once automatically on every Control Center start
    # (not just on a manual button click) - the tile would otherwise sit on
    # the bare "present (not yet tested)" presence check, possibly for a long
    # time, after every restart (including the one that just deployed this
    # feature - see basic-memory pifinder-stellarmate/00048). No mutex check
    # needed here: nothing else can possibly be running yet this early.
    _hwtest_running = True
    threading.Thread(target=_startup_hardware_test, daemon=True).start()
    # #118: auto-heal "PiFinder LX200"'s silent stale-connection bug after a
    # pifinder.service restart - see _pifinder_lx200_reconnect_watchdog()'s
    # own docstring.
    threading.Thread(target=_pifinder_lx200_reconnect_watchdog, daemon=True).start()
    # One-time check, not a watchdog: an already-running pifinder.service
    # left over from before this Control Center's own start (e.g. surviving
    # an Update run from before the setup script's start->restart fix, or a
    # manual `systemctl start` from outside this GUI) won't self-correct on
    # its own - just log it once so it's visible instead of silently stale.
    # Deliberately not auto-restarted: this only reports, it never
    # interrupts a possibly-active observing session on its own initiative.
    if _pifinder_service_settings_stale():
        _mb_log(
            "pifinder.service is running with a stale scheduling priority (doesn't match the "
            "currently configured Nice=/CPUWeight=) - restart it (Mode tile or the Control Center "
            "itself) to apply the current settings."
        )
    _server.serve_forever()


if __name__ == "__main__":
    main()
