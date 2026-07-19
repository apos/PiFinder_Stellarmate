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
