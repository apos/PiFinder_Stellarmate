"""GSC sky simulation for the Control Center (docs/concepts/pifinder_realmode_sky_simulation.md, #344).

The mode "Real hardware + GSC simulation": a star field rendered from the GSC catalogue replaces the camera picture, PiFinder's real
solver (Cedar / tetra3) solves it, the mount is any INDI mount (the Telescope Simulator, or the real one). The work is done by
test_tools/pifinder_sky_follow.py, which watches the mount over INDI and rewrites PiFinder's Test Mode picture. This module starts and
stops it as a background process, switches PiFinder's Test Mode with it and keeps the old "PiFinder Simulator" INDI device out of the
way while the simulation runs (it would show a stale second PiFinder in KStars).

Everything that touches the system takes its paths from the module constants, so the tests can point them at a temporary directory.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
STATE_PATH = HOME / ".pfsm" / "gsc_sim.json"
LOG_PATH = HOME / ".pfsm" / "gsc_sim.log"
ORIGINAL_IMAGE_BACKUP = HOME / ".pfsm" / "gsc_sim_original_test_image.png"
REPO = Path(__file__).resolve().parent.parent
FOLLOW_SCRIPT = REPO / "test_tools" / "pifinder_sky_follow.py"
PF_PYTHON = HOME / "PiFinder" / "python" / ".venv" / "bin" / "python"
PF_REPO = HOME / "PiFinder"
PF_TEST_IMAGE = PF_REPO / "test_images" / "pifinder_debug_02.png"
GSC_BINARY = "gsc"
GSC_DATA = "/usr/share/GSC"
PF_URL = "http://127.0.0.1:8080"
OLD_SIMULATOR_DEVICE = "PiFinder Simulator"
DEFAULT_MOUNT = "Telescope Simulator"

# The error a finished GoTo of 45 degrees lands the scope off its target (east, north arcminutes); shorter slews land closer.
LANDING = {"off": None, "typical": (8.0, -5.0), "large": (16.0, -10.0)}
LANDING_LABELS = {
    "off": "none (a perfect mount)",
    "typical": "typical (8′ E / 5′ S)",
    "large": "large (16′ E / 10′ S)",
}
FOLLOWER_MARK = "pifinder_sky_follow.py"


def availability():
    """(ok, reason): whether this device can run the simulation at all."""
    if not FOLLOW_SCRIPT.exists():
        return False, "The sky follower script is missing (test_tools/pifinder_sky_follow.py)."
    if not PF_PYTHON.exists():
        return False, "PiFinder is not installed on this device: the simulation needs its Python environment."
    if not PF_TEST_IMAGE.parent.exists():
        return False, "PiFinder's test picture folder is missing: the simulation needs PiFinder on this device."
    if shutil.which(GSC_BINARY) is None and not (Path("/usr/local/bin") / GSC_BINARY).exists():
        return False, "The GSC star catalogue tool (gsc) is not installed."
    if not Path(GSC_DATA).exists():
        return False, "The GSC star catalogue data is missing (%s)." % GSC_DATA
    return True, ""


def build_command(landing="typical", device=DEFAULT_MOUNT, restore=None):
    """The command line that starts the follower."""
    if landing not in LANDING:
        raise ValueError("unknown landing error '%s'" % landing)
    cmd = [str(PF_PYTHON), str(FOLLOW_SCRIPT), "--device", device]
    error = LANDING[landing]
    if error is not None:
        cmd += ["--goto-error-east", str(error[0]), "--goto-error-north", str(error[1])]
    if restore:
        cmd += ["--restore", str(restore)]
    return cmd


def _alive(pid):
    """Whether pid is a running sky follower (not just any process that reuses the number)."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return FOLLOWER_MARK.encode() in handle.read()
    except (OSError, ValueError):
        return False


def read_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE_PATH)


def _http_json(path, method="GET", timeout=4):
    request = urllib.request.Request(PF_URL + path, method=method, data=b"{}" if method == "POST" else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def pifinder_status():
    """PiFinder's /api/status, or None when it does not answer."""
    try:
        return _http_json("/api/status")
    except Exception:
        return None


def set_test_mode(want):
    """Switch PiFinder's Test Mode to `want` (the API only toggles). Returns the state afterwards, or None when PiFinder is unreachable."""
    status = pifinder_status()
    if status is None:
        return None
    if bool(status.get("debug_solve")) != bool(want):
        try:
            _http_json("/api/debug_solve", method="POST")
        except Exception:
            return None
    return bool(want)


def _back_up_original_image():
    """Keep PiFinder's original test picture to put back when the simulation ends.

    The original is the one in PiFinder's git checkout (HEAD): the file on disk may be a leftover simulated frame from a
    follower that was killed. Without git (or outside the checkout) the picture on disk is used once.
    """
    ORIGINAL_IMAGE_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    try:
        rel = PF_TEST_IMAGE.relative_to(PF_REPO)
        shown = subprocess.run(["git", "-C", str(PF_REPO), "show", "HEAD:" + rel.as_posix()], capture_output=True, timeout=10)
        if shown.returncode == 0 and shown.stdout:
            ORIGINAL_IMAGE_BACKUP.write_bytes(shown.stdout)
            return
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    if not ORIGINAL_IMAGE_BACKUP.exists() and PF_TEST_IMAGE.exists():
        shutil.copyfile(PF_TEST_IMAGE, ORIGINAL_IMAGE_BACKUP)


def start(landing="typical", device=DEFAULT_MOUNT, indi=None, popen=subprocess.Popen):
    """Start the simulation: the follower, Test Mode, and the old PiFinder Simulator device disconnected.

    `indi` is the indi_client module (or a stand-in): only disconnect_device() is used. Returns the status dict, with a "warnings"
    list for the parts that did not work (PiFinder not answering, the old device not there).
    """
    ok, reason = availability()
    if not ok:
        return dict(status(), ok=False, error=reason)
    if _alive(read_state().get("pid")):
        return dict(status(), ok=True, warnings=["The simulation was already running."])
    warnings = []
    _back_up_original_image()
    pf = pifinder_status()
    test_mode_was_on = bool(pf.get("debug_solve")) if pf else False
    env = dict(os.environ, GSCDAT=GSC_DATA)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "ab")
    try:
        proc = popen(build_command(landing, device, ORIGINAL_IMAGE_BACKUP), stdout=log, stderr=subprocess.STDOUT, env=env,
                     start_new_session=True, cwd=str(REPO))
    finally:
        log.close()  # the child has its own copy of the descriptor
    state = {"pid": proc.pid, "started": time.time(), "landing": landing, "device": device,
             "test_mode_was_on": test_mode_was_on, "old_simulator_disconnected": False}
    if set_test_mode(True) is None:
        warnings.append("PiFinder does not answer: Test Mode could not be switched on.")
    if indi is not None:
        try:
            indi.disconnect_device(OLD_SIMULATOR_DEVICE)
            state["old_simulator_disconnected"] = True
        except Exception as exc:  # the device may simply not be in this profile
            warnings.append("The old PiFinder Simulator device was left alone: %s" % exc)
    write_state(state)
    return dict(status(), ok=True, warnings=warnings)


def stop(indi=None, wait=8.0):
    """Stop the simulation: the follower (it puts PiFinder's original test picture back), Test Mode if the simulation switched it on,
    and the old PiFinder Simulator device back on if the simulation disconnected it."""
    state = read_state()
    pid = state.get("pid")
    warnings = []
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGINT)  # the follower restores the original picture on Ctrl-C
        except OSError:
            pass
        deadline = time.time() + wait
        while time.time() < deadline and _alive(pid):
            time.sleep(0.1)
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(1.0)
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            warnings.append("The follower had to be killed; PiFinder's test picture may not be restored.")
            if ORIGINAL_IMAGE_BACKUP.exists():
                try:
                    shutil.copyfile(ORIGINAL_IMAGE_BACKUP, PF_TEST_IMAGE)
                except OSError:
                    pass
    if not state.get("test_mode_was_on", False):
        if set_test_mode(False) is None:
            warnings.append("PiFinder does not answer: Test Mode could not be switched off.")
    if indi is not None and state.get("old_simulator_disconnected"):
        try:
            indi.connect_device(OLD_SIMULATOR_DEVICE)
        except Exception as exc:
            warnings.append("The old PiFinder Simulator device could not be connected again: %s" % exc)
    try:
        STATE_PATH.unlink()
    except OSError:
        pass
    return dict(status(), ok=True, warnings=warnings)


HEAL_COOLDOWN_SEC = 40.0   # PiFinder's camera takes up to ~30 s to act on the Test Mode command: do not toggle it twice
_last_heal = 0.0


def simulation_state(running, test_mode, solve_source):
    """The one truth the mode tile shows. The simulation is ON only when it actually works: the follower runs, PiFinder is in Test
    Mode and solves the simulated picture. Everything in between is named, never shown as "on":
      off        nothing runs
      waiting    the follower runs but PiFinder does not answer (restarting)
      restoring  the follower runs but Test Mode is off (PiFinder was restarted): it is switched on again
      starting   follower and Test Mode are there, the first solve is not (yet)
      on         solving the simulated sky
    """
    if not running:
        return "off"
    if test_mode is None:
        return "waiting"
    if not test_mode:
        return "restoring"
    return "on" if solve_source == "CAM" else "starting"


def status(include_pifinder=True, heal=False):
    """What the settings tile shows. With heal=True a running simulation whose Test Mode has gone off (PiFinder restarted, e.g. by an
    update) gets it switched on again, at most once per HEAL_COOLDOWN_SEC."""
    global _last_heal
    available, reason = availability()
    state = read_state()
    running = _alive(state.get("pid"))
    out = {"available": available, "reason": reason, "running": running, "landing": state.get("landing") if running else None,
           "device": state.get("device") if running else None, "started": state.get("started") if running else None,
           "test_mode": None, "solve_source": None, "healed": False,
           "landings": [{"id": k, "label": v} for k, v in LANDING_LABELS.items()]}
    if include_pifinder and running:
        pf = pifinder_status()
        if pf:
            out["test_mode"] = bool(pf.get("debug_solve"))
            out["solve_source"] = (pf.get("solution") or {}).get("solve_source")
            if heal and not out["test_mode"] and time.time() - _last_heal >= HEAL_COOLDOWN_SEC:
                _last_heal = time.time()
                out["healed"] = set_test_mode(True) is not None
    out["state"] = simulation_state(running, out["test_mode"], out["solve_source"]) if (include_pifinder or not running) else ("on" if running else "off")
    return out


RESTORE_MIN_GAP_SEC = 30.0     # between two restarts of a dead follower
RESTORE_MAX_PER_WINDOW = 3     # a follower that keeps dying (mount missing, ...) is not restarted forever
RESTORE_WINDOW_SEC = 600.0
_restore_times = []


def restore(indi=None, popen=subprocess.Popen, now=time.time):
    """Keep the simulation the way it was last chosen, across updates, crashes and reboots.

    The state file exists from "start" until "stop" - it is the memory of what the user wants. So:
      * state file, follower running -> PiFinder's Test Mode is switched on again if an update/restart put it off (status(heal=True))
      * state file, follower dead    -> the follower is started again (at most RESTORE_MAX_PER_WINDOW times per RESTORE_WINDOW_SEC,
                                        at least RESTORE_MIN_GAP_SEC apart), keeping what the first start recorded about Test Mode
                                        and the old PiFinder Simulator device
      * no state file                -> the user did not want it: nothing happens.
    Returns a short word for logging: "none", "healthy", "healed", "restarted", "waiting", "gave-up", "unavailable".
    """
    state = read_state()
    if not state.get("pid"):
        return "none"
    if _alive(state["pid"]):
        return "healed" if status(heal=True).get("healed") else "healthy"
    ok, _reason = availability()
    if not ok:
        return "unavailable"
    t = now()
    _restore_times[:] = [x for x in _restore_times if t - x < RESTORE_WINDOW_SEC]
    if len(_restore_times) >= RESTORE_MAX_PER_WINDOW:
        return "gave-up"
    if _restore_times and t - _restore_times[-1] < RESTORE_MIN_GAP_SEC:
        return "waiting"
    _restore_times.append(t)
    try:
        STATE_PATH.unlink()          # start() refuses to start while the old state names a living follower; it is dead, so write anew
    except OSError:
        pass
    result = start(state.get("landing", "typical"), state.get("device", DEFAULT_MOUNT), indi=None, popen=popen)
    if not result.get("ok"):
        write_state(state)           # keep the wish, try again later
        return "unavailable"
    fresh = read_state()
    fresh["test_mode_was_on"] = state.get("test_mode_was_on", False)
    fresh["old_simulator_disconnected"] = state.get("old_simulator_disconnected", False)
    write_state(fresh)
    if indi is not None and fresh["old_simulator_disconnected"]:
        try:
            indi.disconnect_device(OLD_SIMULATOR_DEVICE)   # a restart of the INDI drivers may have brought it back
        except Exception:
            pass
    return "restarted"
