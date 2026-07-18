#!/usr/bin/env python3
"""
Raw keypad matrix scan, independent of PiFinder's own software.

Diagnoses whether physical key presses actually register at the electrical
level, bypassing PiFinder entirely (no keyboard_queue, no menu logic) - so it
can tell a genuine hardware fault (broken switch, bad solder joint, dead GPIO
pin/pull-up) apart from a software/navigation bug. Mirrors the exact scan
technique in PiFinder/python/PiFinder/keyboard_pi.py's run_keyboard(): drive
each row LOW in turn, read each column (pulled up, so LOW = pressed).

IMPORTANT: stop pifinder.service first (systemctl stop pifinder) - its own
keyboard process holds these same GPIO pins, and running both at once will
produce garbage readings (or GPIO errors) from the conflict, not a real
diagnosis. Restart it afterward (systemctl start pifinder).

Usage:
    sudo systemctl stop pifinder
    /home/stellarmate/PiFinder/python/.venv/bin/python \
        test_tools/keypad_gpio_matrix_test.py [duration_seconds]
    sudo systemctl start pifinder

With no arguments, scans for 20s. Press keys during the scan to see PRESS/
RELEASE lines; a key that never shows RELEASE (or shows PRESS with nobody
touching anything) means the fault is on that specific row/column's
electrical path, not a normal switch/keycap issue.

Background: found via this exact script (2026-07-19) that GPIO 16 (matrix
column 0) reads permanently LOW regardless of which row is driven, with or
without anyone touching the keypad - affecting every key in that column (7,
4, 1, and the "Zurueck"/LEFT key), not just the one the user first noticed.
Confirmed reproducible with zero physical contact, isolating it as a
hardware fault on that GPIO line rather than a single worn-out switch or a
software/navigation bug (a headless API-injected LEFT keypress was verified
separately, via the pifinder-remote skill, to navigate back correctly).
"""
import time
import sys
import RPi.GPIO as GPIO

cols = [16, 23, 26, 27]
rows = [19, 17, 18, 22, 20]

keymap = [
    "7", "8", "9", "NA",
    "4", "5", "6", "PLUS",
    "1", "2", "3", "MINUS",
    "NA", "0", "NA", "SQUARE",
    "LEFT(Zurueck)", "UP", "DOWN", "RIGHT",
]

GPIO.setmode(GPIO.BCM)
GPIO.setup(rows, GPIO.IN)
GPIO.setup(cols, GPIO.IN, pull_up_down=GPIO.PUD_UP)

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
print(f"Scanning matrix for {duration:.0f}s - press keys now (esp. Zurueck/LEFT)...", flush=True)

pressed = set()
start = time.time()
try:
    while time.time() - start < duration:
        for i in range(len(rows)):
            GPIO.setup(rows[i], GPIO.OUT, initial=GPIO.LOW)
            for j in range(len(cols)):
                keycode = i * len(cols) + j
                newval = GPIO.input(cols[j]) == GPIO.LOW
                if newval and keycode not in pressed:
                    pressed.add(keycode)
                    print(f"PRESS   row={rows[i]} col={cols[j]} keycode={keycode} -> {keymap[keycode]}", flush=True)
                elif not newval and keycode in pressed:
                    pressed.discard(keycode)
                    print(f"RELEASE row={rows[i]} col={cols[j]} keycode={keycode} -> {keymap[keycode]}", flush=True)
            GPIO.setup(rows[i], GPIO.IN)
        time.sleep(1 / 60)
finally:
    GPIO.cleanup()
print("Scan done.", flush=True)
