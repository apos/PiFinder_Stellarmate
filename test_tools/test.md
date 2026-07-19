# test_tools/ — Testing & Diagnostic Tools

Standalone tools for testing PiFinder_Stellarmate components in isolation,
without needing the full hardware/software stack wired up. Each tool isolates
exactly ONE layer, so a reported fault can be pinned down precisely instead of
guessing across camera/GPIO/software/menu-logic all at once.

## fake_pifinder_lx200.py

- **Purpose:** stand-in for PiFinder's own `pos_server.py` (its LX200 TCP
  server, normally port 4030) for developing/testing `indi_pifinder_bridge` /
  the Mount Bridge coupling logic without a real PiFinder running a live
  plate-solve loop.
- **What it does:** speaks the small LX200 subset PiFinder's real server
  exposes (`:GR#`/`:GD#` position queries, acks `:Sr`/`:Sd` target commands)
  on its own port (default 4031), running a looping demo tour through Lyra
  (Vega → Sheliak → Sulafat → M57 Ring Nebula) so there's always a realistic,
  moving position to test against.
- **Usage:** `python3 test_tools/fake_pifinder_lx200.py [--port N]`, then
  point the INDI driver/bridge at that port instead of PiFinder's real 4030.
- **When to use:** iterating on the INDI driver or Mount Bridge logic itself,
  independent of PiFinder/camera/solver being up at all.

## keypad_gpio_matrix_test.py

- **Purpose:** raw hardware diagnostic for the physical keypad, independent
  of PiFinder's own software - bypasses `keyboard_queue` and all menu logic
  entirely.
- **What it does:** mirrors `PiFinder/python/PiFinder/keyboard_pi.py`'s exact
  row/col GPIO matrix scan (drive each row LOW in turn, read each
  pulled-up column), printing PRESS/RELEASE with row/col/keycode. A fault
  shows up as a specific GPIO line misbehaving (e.g. a whole matrix column
  reading LOW permanently, with or without anyone touching anything) rather
  than a vague "something feels off."
- **Usage:** **stop `pifinder.service` first** - its own keyboard process
  holds the same GPIO pins, and running both at once produces garbage
  readings from the conflict, not a real diagnosis.
  ```bash
  sudo systemctl stop pifinder
  /home/stellarmate/PiFinder/python/.venv/bin/python \
      test_tools/keypad_gpio_matrix_test.py [duration_seconds]
  sudo systemctl start pifinder
  ```
- **When to use:** a specific key is reported as not responding. Confirms or
  rules out a genuine hardware fault (electrical signal never changes,
  reproducible even with zero physical contact during the scan).

## fake_mode.sh

- **Purpose:** run PiFinder with zero real hardware attached (camera,
  keyboard, display all faked) as a normal, browsable web service - useful
  whenever the physical HAT is disconnected (repair, inspection, bench work)
  but you still want the web UI up for development/testing. Interactive:
  start it now, stop it later whenever you're done, in two separate SSH
  commands.
- **What it does:** a thin wrapper around the `pifinder-remote` Claude Code
  skill's `pf_remote.py` (see below) plus the real `pifinder.service`: `start`
  stops the real service and launches a fake-hardware instance (`--camera
  debug --keyboard none --display headless`) on port 8081; `stop` reverses
  that (stops the fake instance, restarts the real service); `status` reports
  which of the two is currently active. Once started, it's a completely
  normal PiFinder web server - browse to it like any other instance, log in
  with the usual password, no need to keep using this script or
  `pf_remote.py` to interact with it.
- **Usage:**
  ```bash
  test_tools/fake_mode.sh start    # stop the real service, start fake mode
  test_tools/fake_mode.sh status   # check which mode is active
  test_tools/fake_mode.sh stop     # stop fake mode, restart the real service
  ```
- **When to use:** the HAT (camera/keyboard/OLED) is off the device for
  inspection or repair, but you still want to poke at PiFinder's web UI,
  test a code change, or just confirm the software side is healthy.

## fb_screen_mirror.py

- **Purpose:** mirror a running PiFinder instance's screen onto a small
  local SPI display (e.g. the Waveshare 3.5inch RPi LCD (B) dev/testing
  screen, see `pifinder_stellarmate_setup.sh`'s/`/boot/config.txt`'s
  `waveshare35b-v2` overlay comment) - so Fake Mode (or Real Mode) can be
  watched visually without the real HAT's OLED attached.
- **What it does:** polls PiFinder's own `GET /api/screen` (the same stable,
  hardware-independent endpoint the Setup GUI's OLED mirror and
  `pf_remote.py` use), scales/letterboxes/rotates the 128x128 image to fit
  the target framebuffer, and writes raw RGB565 pixels directly to it (e.g.
  `/dev/fb1`) - no `fbcp`/DispmanX involved, which is broken on Pi5 (DispmanX
  was removed in favor of DRM/KMS). Auto-probes ports 80/8080/8081, verifying
  each candidate actually returns a decodable image (not just HTTP 200) -
  StellarMate's own nginx dashboard squats on port 80 and returns HTTP 200
  with an HTML body for *any* path, a known false-positive trap.
- **Usage:**
  ```bash
  /home/stellarmate/PiFinder/python/.venv/bin/python3 \
      test_tools/fb_screen_mirror.py [--fb /dev/fb1] [--rotate 0|90|180|270]
  ```
  Uses PiFinder's own venv (already has Pillow + numpy - no new system
  packages needed). `--rotate` is degrees counter-clockwise ("left").
- **When to use:** developing/testing with the physical HAT disconnected but
  a small SPI screen attached instead - see
  `basic-memory/pifinder-stellarmate/00024_waveshare-lcd-fake-mode-dev-setup.md`
  for the full overlay setup and a documented GPIO conflict with the real
  keypad matrix.

## fb_keyboard_bridge.py

- **Purpose:** control PiFinder from a plain USB/wireless keyboard or numpad
  with no physical PiFinder keypad/HAT attached - the natural input-side
  companion to `fb_screen_mirror.py` for a fully hardware-independent
  dev/test setup.
- **What it does:** reads raw evdev key events (works with or without an
  X11/desktop session, unlike PiFinder's own `--keyboard local` mode, which
  needs X11 via `pynput`) and posts them to the same stable `/api/key`
  endpoint `pf_remote.py` and the Setup GUI use. Ships with a mapping tuned
  for a numpad-only device (confirmed against a LogiLink ID0120): NumLock
  off = `4/8/6/2` are arrows, NumLock on = plain digits (state tracked
  internally, since NumLock doesn't change a numpad key's raw evdev keycode -
  only a higher keymap layer this tool deliberately bypasses); `+`/`-` always
  PLUS/MINUS; Enter always SQUARE; Backspace/Delete always a second LEFT.
  Replicates the real keypad's hold behavior too: holding UP/DOWN repeats;
  holding LEFT/RIGHT/SQUARE >1s sends the LNG_* variant instead (LNG_SQUARE
  opens/closes PiFinder's marking menu); holding SQUARE while pressing
  another mapped key sends its ALT_* variant.
- **Usage:**
  ```bash
  /home/stellarmate/PiFinder/python/.venv/bin/pip install evdev   # once
  /home/stellarmate/PiFinder/python/.venv/bin/python3 \
      test_tools/fb_keyboard_bridge.py [--device /dev/input/eventN]
  ```
  Auto-detects the first keyboard/numpad-like input device if `--device` is
  omitted. `evdev` is deliberately *not* added to PiFinder_Stellarmate's
  `requirements_additional.txt` - it's only needed for this dev tool, not
  for every end-user install.
- **When to use:** same scenario as `fb_screen_mirror.py` - no physical
  keypad attached. Live-tested (LogiLink ID0120): navigation, long-press,
  and the marking menu all confirmed working - see
  `basic-memory/pifinder-stellarmate/00024_waveshare-lcd-fake-mode-dev-setup.md`
  for two real bugs found and fixed during that testing (a missed
  long-press timer, and a thread race that closed the marking menu
  immediately on release).

## Related: the `pifinder-remote` Claude Code skill

Not in this directory (it lives in the PiFinder checkout itself, under
`.claude/skills/pifinder-remote/`, since it drives PiFinder headlessly), but
the natural software-side complement to `keypad_gpio_matrix_test.py`: it
launches a second, headless PiFinder instance and injects virtual keypresses
via its `/api/key` HTTP endpoint (the same endpoint a phone app or any other
remote control would use), to test menu/navigation *logic* in isolation from
physical hardware.

Together, these give a full hardware-vs-software split for a "this key/input
doesn't work" report:

1. **`pifinder-remote` skill** — does the software correctly react to a
   LEFT/RIGHT/etc. keypress *event*? Confirms or rules out a
   navigation-logic bug.
2. **`keypad_gpio_matrix_test.py`** — does physically pressing the key
   actually change the electrical signal on its GPIO line? Confirms or rules
   out a hardware fault.

Run both before concluding which side the problem is on - see
`basic-memory/basic-memory/00015_bm-hardware-vs-software-diagnostic-split.md`
for why this two-step split is worth doing as a default habit, not just for
PiFinder.

## Adding a new tool here

Add a short section above with the same shape: **Purpose**, **What it
does**, **Usage**, **When to use**.
