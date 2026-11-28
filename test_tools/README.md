# Tests

## The regression run

```bash
bash test_tools/run_regression.sh
```

| Call | Covers | Needs | Touches |
|---|---|---|---|
| `run_regression.sh` (offline) | page logic (JS), Python logic, the shell tests (bats) | node; PiFinder's venv for the sky renderer | nothing |
| `run_regression.sh driver` | + the Mount Bridge against stand-ins on its own INDI servers: late and switched mounts, coupling off during a slew, OnStep hand controller and alignment (network and USB), park / home and a mount with its own alignment | libindi development files; free ports 7690, 7691, 7693-7699, 9998, 9999 | nothing running |
| `run_regression.sh live --move` | + the running Full Simulation: GoTo following and refining, Multi-Point Alignment | the simulator profile with the Mount Bridge, the GSC sky simulation available | **moves the Telescope Simulator**, restarts the sky simulation, leaves it in the GoTo coupling |
| `run_regression.sh all --move` | everything (about 40 minutes on a Pi 5) | all of the above | as above |

The raw output of every test is kept in `~/pfsm_test_logs/<time>/`, with `summary.txt`. Exit status 0 only if all passed.

**Never run `test_tools/*_test.py` as a whole.** Some tests outside the run press GPIO keys, restart `pifinder.service` or move a
mount (`align_sync_test`, `keypad_gpio_matrix_test`, `pifinder_pushto_stress_test`, `tracking_toggle_stress_test`).

## What to know about the simulated environment

- The live tests start from a freshly started sky simulation: after several alignment runs the Telescope Simulator's mount model
  distorts, and resetting the model alone while the simulation runs shifts the simulated sky.
- PiFinder cannot solve every simulated star field and solves single ones wrongly (#697). When the mount stands on the target and
  the fault is the camera's, the live tests take another field.
- The simulator's alignment model fits its points: Multi-Point Alignment may count fewer points than were synced (#702).
- Whatever a test had to work around is a line starting with `note` in its log and in `summary.txt`. Read them: a passed run with
  notes is not the same as a clean one.
- On x86 PiFinder has no matching `cedar-detect-server` and uses its own star finder (patched since 3.0.0, untested there).

## Not part of the run

| Script | For |
|---|---|
| `test_smos_post_update.sh` | the SMOS post-update boot fix on a throw-away disk image (needs root and loop devices) |
| `mount_model_check.py --move`, `ekos_align_probe.py` | does the mount arrive; what Ekos does during an alignment |
| `onstep_watch.py`, `bridge_props.py`, `bridge_messages.py`, `bridge_stall_catcher.py` | watching a running system |
| `fake_onstep_indi_driver.py` | the stand-in OnStep INDI driver used by the OnStep tests |
| `onstep_mount_type_check.py` | what a (patched) OnStep driver build reports as mount type |

Writing a new test: it sets up its own preconditions, restores what it changed, keeps its raw output, and refuses to run where it
could move real hardware it was not written for.
