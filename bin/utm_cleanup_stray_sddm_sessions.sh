#! /usr/bin/bash
set -euo pipefail

# Recovery tool for the stacked-greeter symptom described in
# fix_utm_apple_silicon_host_pause_issues.sh's own header comment (and
# basic-memory pifinder-stellarmate/00104): each time systemd-logind
# crashes on this VM, SDDM opens a brand-new Xorg+greeter pair on a fresh
# VT instead of reusing the existing desktop session, piling up ~190MB per
# occurrence until the system runs out of memory and the real desktop
# (which is usually still alive underneath) looks "frozen"/"crashed".
#
# tsc=reliable (see the other script) should stop this from recurring after
# a reboot - this script is only for cleaning up a pile that has already
# built up before that reboot happens, WITHOUT touching the one session
# that is actually your real, working desktop.
#
# Run this instead of guessing which "Xorg" to kill by hand.

SDDM_PID="$(pgrep -x sddm | head -1)"
if [[ -z "${SDDM_PID}" ]]; then
    echo "sddm isn't running - nothing to do."
    exit 0
fi

# The real desktop is the one sddm-helper invocation that used --autologin
# (see /etc/sddm.conf's [Autologin] section) - every stray greeter/extra
# login attempt lacks that flag. Its own Xorg is that helper's grandparent
# via ps's PPID chain (helper -> startplasma-x11), so we protect the
# helper PID itself and let everything else under sddm go.
REAL_HELPER_PID="$(ps --ppid "${SDDM_PID}" -o pid,args --no-headers \
    | awk '/--autologin/{print $1; exit}')"

if [[ -z "${REAL_HELPER_PID}" ]]; then
    echo "Could not identify the real autologin session under sddm (PID ${SDDM_PID})."
    echo "Not killing anything - check 'ps --ppid ${SDDM_PID}' by hand."
    exit 1
fi

echo "Real desktop session: sddm-helper PID ${REAL_HELPER_PID} (protected)."

mapfile -t STRAY_PIDS < <(ps --ppid "${SDDM_PID}" -o pid --no-headers | awk -v real="${REAL_HELPER_PID}" '$1!=real')

if [[ ${#STRAY_PIDS[@]} -eq 0 ]]; then
    echo "No stray greeter/Xorg sessions found. Nothing to clean up."
    exit 0
fi

echo "Found ${#STRAY_PIDS[@]} stray process(es) under sddm - terminating:"
for pid in "${STRAY_PIDS[@]}"; do
    ps -p "${pid}" -o pid,args --no-headers || true
    sudo kill "${pid}" 2>/dev/null || true
done

echo ""
echo "Done. If sddm immediately respawns new greeters instead of settling,"
echo "the underlying crash loop is still active - check whether tsc=reliable"
echo "actually took effect (cat /sys/devices/system/clocksource/clocksource0/current_clocksource)"
echo "and whether the VM has been rebooted since it was added."
