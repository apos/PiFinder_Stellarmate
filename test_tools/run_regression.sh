#!/usr/bin/env bash
# The project's regression run. See test_tools/README.md.
#
#   bash test_tools/run_regression.sh                 offline: page, Python and shell tests; touches nothing
#   bash test_tools/run_regression.sh driver          + the drivers against stand-ins on their own indiservers
#   bash test_tools/run_regression.sh live --move     + the running Full Simulation: MOVES THE TELESCOPE SIMULATOR
#   bash test_tools/run_regression.sh all --move      everything
#
# Every test's raw output is kept in ~/pfsm_test_logs/<time>/ - a failure can always be read afterwards.
# Exit status 0 only if every test passed.
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
LEVEL="${1:-offline}"
MOVE="${2:-}"
case "$LEVEL" in offline | driver | live | all) ;; *)
    sed -n '2,11p' "$0"
    exit 2
    ;;
esac
PY="$HOME/PiFinder/python/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
LOGS="$HOME/pfsm_test_logs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOGS" || exit 2
declare -a RESULTS=()
FAILED=0

run() { # name, timeout seconds, command...
    local name="$1" limit="$2"
    shift 2
    local start=$SECONDS
    if timeout "$limit" "$@" >"$LOGS/$name.log" 2>&1; then
        RESULTS+=("ok    $name ($((SECONDS - start)) s)")
    else
        local code=$?
        FAILED=$((FAILED + 1))
        [ "$code" -eq 124 ] && RESULTS+=("FAIL  $name (> $limit s)  $LOGS/$name.log") || RESULTS+=("FAIL  $name (exit $code)  $LOGS/$name.log")
    fi
    echo "${RESULTS[-1]}"
    local note # a test says with "note ..." what it had to work around: that belongs into the summary, passed or not
    while IFS= read -r note; do
        RESULTS+=("      $note")
        echo "      $note"
    done < <(grep '^note ' "$LOGS/$name.log")
}

offline() {
    local f
    if command -v node >/dev/null; then
        for f in test_tools/*_test.js; do run "$(basename "$f" .js)" 120 node "$f"; done
    else
        echo "skip  page tests: node is not installed"
    fi
    # Only tests that need no hardware, no pifinder.service and no running INDI server. Never run test_tools/*_test.py as a whole:
    # some of the others press GPIO keys, restart PiFinder or move a mount.
    for f in alignment_hold bridge_binding bridge_restart_fifo clock_status cold_profile_autostart compat_check driver_port_order \
        driver_stdout driver_watch field_problem gsc_sim lx200_reconnect mount_silence patch_drift_check pfsm_bridge_status pifinder_sky_follow \
        pifinder_sky_renderer sky_math solver_arch_patch target_status; do
        run "${f}_test" 300 "$PY" "test_tools/${f}_test.py"
    done
    if [ -x bin/tests/vendor/bats-core/bin/bats ]; then
        run shell_bats 600 bash bin/tests/run_all.sh
    else
        echo "skip  shell tests: run 'git submodule update --init --recursive' first"
    fi
}

driver() {
    local build="indi_pifinder_bridge/build"
    run driver_build 900 bash -c "cmake -S indi_pifinder_bridge -B $build -DCMAKE_BUILD_TYPE=Release && cmake --build $build -j3"
    local port
    for port in 7690 7694 7695 7697 7698 7699 9998 9999; do
        if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$port\$"; then
            echo "skip  driver tests: port $port is in use"
            FAILED=$((FAILED + 1))
            return
        fi
    done
    local t
    for t in bridge_late_mount bridge_switch_mount bridge_off_stops_slew onstep_controller mpa_onstep; do
        run "${t}_test" 600 "$PY" "test_tools/${t}_test.py"
    done
}

sim_restart() { # a clean simulated sky and mount model - the state every live test starts from
    timeout 120 "$PY" - <<EOF
import sys, time
sys.path.insert(0, "$REPO/gui_installer")
import gsc_sim, indi_client
with gsc_sim.switching():
    gsc_sim.stop(indi=indi_client)
    result = gsc_sim.start(landing="typical", device="Telescope Simulator", indi=indi_client)
print("sky simulation restarted:", result.get("ok"), result.get("error") or "")
indi_client.set_switch("PiFinder Mount Bridge", "BRIDGE_MODE", "MODE_GOTO_FORWARD")
time.sleep(30)
sys.exit(0 if result.get("ok") else 1)
EOF
}

live() {
    if [ "$MOVE" != "--move" ]; then
        echo "skip  live tests: they move the Telescope Simulator, add --move"
        FAILED=$((FAILED + 1))
        return
    fi
    # Preconditions are set up here, not hoped for: only simulators, the Bridge running, a clean sky.
    if ! timeout 60 "$PY" - >"$LOGS/live_preconditions.log" 2>&1 <<EOF; then
import sys
sys.path.insert(0, "$REPO/gui_installer")
import indi_client
devices = indi_client.get_properties(timeout=15)
real = [d for d, p in devices.items() if "TELESCOPE_PARK" in p and d != "Telescope Simulator" and d != "PiFinder LX200"]
missing = [d for d in ("PiFinder Mount Bridge", "PiFinder LX200", "Telescope Simulator") if d not in devices]
print("devices:", sorted(devices))
if real or missing:
    sys.exit("not the simulator profile: real mount %s, missing %s" % (real, missing))
EOF
        echo "skip  live tests: start the simulator profile first ($LOGS/live_preconditions.log)"
        FAILED=$((FAILED + 1))
        return
    fi
    run sim_restart_1 200 bash -c "$(declare -f sim_restart); REPO='$REPO' PY='$PY' sim_restart"
    run live_goto_refine 1500 "$PY" test_tools/mount_goto_refine_test.py --move
    run sim_restart_2 200 bash -c "$(declare -f sim_restart); REPO='$REPO' PY='$PY' sim_restart"
    run live_alignment 900 "$PY" test_tools/mpa_hold_target_test.py --move
    run sim_restart_3 200 bash -c "$(declare -f sim_restart); REPO='$REPO' PY='$PY' sim_restart"
}

echo "PFSM regression: $LEVEL, $(git rev-parse --abbrev-ref HEAD) $(git rev-parse --short HEAD), logs in $LOGS"
offline
[ "$LEVEL" = driver ] || [ "$LEVEL" = all ] && driver
[ "$LEVEL" = live ] || [ "$LEVEL" = all ] && live
{
    echo "PFSM regression $LEVEL on $(uname -n) $(date '+%Y-%m-%d %H:%M'), $(git rev-parse --abbrev-ref HEAD) $(git rev-parse --short HEAD)"
    printf '%s\n' "${RESULTS[@]}"
    echo "$FAILED failed"
} >"$LOGS/summary.txt"
echo "----"
grep -c '^ok' "$LOGS/summary.txt" | sed 's/$/ passed/'
echo "$FAILED failed - $LOGS/summary.txt"
exit $((FAILED > 0))
