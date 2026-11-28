# Concept: GoTos from the OnStep hand controller over USB

Status: concept, not implemented. 2026-11-28. Related: #658 (network, shipped in 3.0.0), #696 (USB), PR #707 (alignment over
USB, shipped to `dev`).

## 1. Overview

A GoTo started on the OnStep hand controller, the OnStep app or SkySafari goes straight to the controller. Over the **network** the
Mount Bridge reads the controller's target on a second command port and brings the scope onto the object. Over **USB/serial**
there is only one line, owned by the INDI OnStep driver, and the driver does not publish that target. This concept lists what
would have to change in the driver, what that costs, and the way that needs no driver change.

## 2. Measured facts

Real OnStep 10.14a, stock driver of INDI 2.2.5 on a serial line (a pty forwarded to the controller), commands sent on another
command port as a hand controller does (2026-11-28; the night run of 2026-11-27 for the end positions).

| Question | Result |
|---|---|
| GoTo started on the controller | `:GU#` loses `N`; the driver reports `EQUATORIAL_EOD_COORD` **Busy** until the slew ends |
| Movement with the direction buttons | `:GU#` keeps `N`; the property does **not** turn Busy |
| Where does a controller GoTo end? | on the commanded target (Dec exact; RA differs only by the sky's motion with tracking off) |
| Is the target readable through INDI? | no: the driver never asks `:Gr#` / `:Gd#`; `TARGET_EOD_COORD` changes only for GoTos sent through INDI |
| Alignment running on the controller | published in `Align Process` (the driver asks `:A?#` itself) - used by the Bridge since PR #707 |

So a GoTo from outside **is** visible through INDI, and it can be told apart from a button movement. What is not visible is the
target while the slew runs, or after a slew that was stopped.

## 3. Way A: no driver change (recommended first)

The Bridge treats a movement as a controller GoTo when all of these hold: no command went through INDI, the mount reported Busy,
no alignment, not parking. When the mount stands again, its **reported position is the target**; the Bridge then verifies with a
plate solve and refines, exactly as for any other GoTo.

| | |
|---|---|
| Gains | works over USB and network, for every mount driver that reports Busy for a GoTo from its handset |
| Misses | the target is known only at the end; a GoTo stopped half way looks like a GoTo to the stopping point (refining then corrects only the pointing error there) |
| Open | a "go home" from the handset must not be refined (is it reported as parking? to be measured); which other drivers report Busy for handset GoTos (not tested) |
| Effort | small: Bridge only; testable with the stand-in driver and on the real OnStep |

## 4. Way B: change the INDI OnStep driver

### 4.1 The change

File `drivers/telescope/lx200_OnStep.cpp`, function `ReadScopeStatus()`:

1. After the current position has been read (`getLX200RA` / `getLX200DEC`), ask `:Gr#` and `:Gd#` (the controller's target
   registers). They are get commands; OnStep answers them at any time, during a slew too.
2. Parse them like the current position and publish them in `TargetNP` (`TARGET_EOD_COORD`) **only when they changed** by more
   than half an arc minute.
3. Do this before the early return for manual motion, and skip it when `:GU#` reports parking (`I`, `h`).
4. A Sync also writes the target registers (`:CM#`): publish with state Idle for a changed target without a slew, so a client can
   tell it from a GoTo (target changed **and** Busy = GoTo).

The Mount Bridge already reads `TARGET_EOD_COORD`; its rule for a GoTo from outside would then use it over USB as well. About 30
lines in the driver, a few in the Bridge.

### 4.2 What it costs

| | |
|---|---|
| Whose code | the driver belongs to the system package `libindi`; PFSM would ship a patched copy of the binary |
| Build | `bin/build_indi_onstep_fix.sh` already does this for the mount type fix: sources of the installed INDI version, the diff, build, install |
| SMOS update | replaces `/usr`: the patched binary is gone, and a newer INDI may no longer take the diff. The script must run again and may need rework |
| Setup | not run by the setup today; running it there adds a download of the INDI sources and several minutes of build time |
| Side effects | the same binary serves all LX200-type drivers (symlinks): a faulty build affects them all |
| Upstream | a pull request to `indilib/indi` ends the maintenance once accepted and released; until then the costs above apply |

### 4.3 The existing fix (state 2026-11-28)

`diffs/indi_lx200_OnStep.diff` (mount type, #227; also parentheses in code that is only compiled with `OnStep_Alpha`) applies to
INDI 2.2.5 unchanged and is still needed: the stock driver reports fork (`:GXEM#` = 2) and alt-az (3) controllers as GEM
(`test_tools/onstep_mount_type_check.py`). The script now follows the installed version and takes the source list from it.

## 5. Recommendation and order

1. Way A in the Bridge, with tests (stand-in driver, then the real OnStep).
2. Way B only if A proves too weak in use (target needed during the slew), then preferably as an upstream pull request.

## 6. Test plan for either way

| Case | Expectation |
|---|---|
| GoTo on the controller, USB | followed to the object, source named on the page |
| Button movement | position taken over, no refine |
| Alignment on the controller | nothing synced (covered by `onstep_usb_alignment_test.py`) |
| Park / home from the controller | no refine |
| GoTo stopped half way | no drive onwards |
| Sync on the controller | not taken as a GoTo |

## 7. Open decisions (owner)

- Way A now?
- Should the setup build and install the mount type fix on devices with a fork or alt-az OnStep (today: manual script)?
- Offer the driver changes upstream?
