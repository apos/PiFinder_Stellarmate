#! /usr/bin/bash
set -euo pipefail

# Fixes a cluster of stability problems found live on stellarmate-utm (an x86
# StellarMate VM running under UTM on Apple Silicon, 2026-08-31 - see
# basic-memory pifinder-stellarmate/00104 for the full investigation).
#
# Root cause: on Apple Silicon, UTM can only run an x86 guest via software
# emulation (no hardware virtualization for x86 on ARM) - there is no
# kvm-clock, and the guest's TSC clocksource is marginal. Every time the Mac
# host pauses/resumes the VM (sleep, or interacting with it after the host's
# own screen lock), the kernel's clocksource watchdog sees an implausibly
# long gap ("Long readout interval, skipping watchdog check"). Enough of
# these and it marks TSC "unstable" and falls back to acpi_pm - a much
# slower, IO-port-based timer that then causes systemd's own event loop
# (sd_event/epoll_wait) to SIGABRT across many daemons (systemd-logind
# first and worst, but also networkd/resolved/timesyncd/...). Every
# logind crash loses its in-memory session/seat state, so SDDM opens a
# BRAND NEW greeter+Xorg pair on a fresh VT instead of reusing the existing
# desktop session - repeated every 15-90 minutes, it silently piles up
# (~190MB per stacked greeter) until the system is memory-starved and the
# real desktop appears to have "crashed".
#
# This script applies the four fixes found; safe to re-run (each step
# checks before changing anything).

source "$(dirname "$0")/functions.sh"

echo "-> [1/4] Forcing the kernel to trust TSC unconditionally (tsc=reliable)..."
# The actual fix for the root cause above: stops the clocksource watchdog
# from ever downgrading to acpi_pm because of a pause/resume glitch. TSC
# itself works fine in normal operation (used correctly from boot until the
# first pause/resume incident) - only the watchdog's judgement of an
# artificial VM-pause gap as "skew" is wrong. Applied to whichever
# systemd-boot entry is currently the default, not hardcoded, so this keeps
# working across StellarMate OS snapshot updates (system-X.Y.Z.conf).
LOADER_CONF="/efi/loader/loader.conf"
if [[ ! -f "${LOADER_CONF}" ]]; then
    echo "   ${LOADER_CONF} not found - not a systemd-boot system? Skipping."
else
    DEFAULT_ENTRY="$(sudo awk '$1=="default"{print $2}' "${LOADER_CONF}")"
    ENTRY_FILE="/efi/loader/entries/${DEFAULT_ENTRY}"
    if [[ ! -f "${ENTRY_FILE}" ]]; then
        echo "   Default entry '${DEFAULT_ENTRY}' not found under /efi/loader/entries/. Skipping."
    elif sudo grep -q 'tsc=reliable' "${ENTRY_FILE}"; then
        echo "   Already set in ${ENTRY_FILE}. Skipping."
    else
        sudo sed -i '/^options/ s/$/ tsc=reliable/' "${ENTRY_FILE}"
        echo "   Added to ${ENTRY_FILE} - takes effect on next reboot."
    fi
fi

echo "-> [2/4] Enabling plasma-plasmashell.service..."
# Found disabled after a forced sddm restart (systemctl --user preset says
# it should be enabled) - kwin_x11/ksmserver started fine on their own, but
# plasmashell itself never did, since nothing pulled it in. Without this,
# any future session restart (e.g. after finally applying the tsc fix above)
# would look "crashed" again for an unrelated reason.
if systemctl --user is-enabled --quiet plasma-plasmashell.service 2>/dev/null; then
    echo "   Already enabled. Skipping."
else
    systemctl --user enable plasma-plasmashell.service
    echo "   Enabled."
fi

echo "-> [3/4] Fixing broken quotes in /etc/udev/rules.d/99-eth0.rules..."
# Had curly/smart quotes (a copy-paste artifact) instead of straight ones -
# udev logged "Invalid key/value pair, ignoring" on every rule reload
# (including the ones that happen during the pause/resume cascade above),
# pure noise but worth cleaning up since it's a one-line, zero-risk fix.
ETH0_RULES="/etc/udev/rules.d/99-eth0.rules"
EXPECTED_RULE='ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth0", ATTR{device/power/control}="on"'
if [[ -f "${ETH0_RULES}" ]] && [[ "$(sudo cat "${ETH0_RULES}")" == "${EXPECTED_RULE}" ]]; then
    echo "   Already fixed. Skipping."
elif [[ -f "${ETH0_RULES}" ]]; then
    echo "${EXPECTED_RULE}" | sudo tee "${ETH0_RULES}" > /dev/null
    sudo udevadm control --reload-rules
    echo "   Fixed and reloaded udev rules."
else
    echo "   ${ETH0_RULES} not present. Skipping."
fi

echo "-> [4/4] Disabling the screen locker entirely..."
# Direct user request, 2026-08-31 - not itself the root cause (that's the
# TSC issue above), but removes an extra source of host/guest session
# interaction while investigating "the GUI seems to freeze after I try to
# log back in" symptoms.
KSCREENLOCKER_RC="${HOME}/.config/kscreenlockerrc"
mkdir -p "$(dirname "${KSCREENLOCKER_RC}")"
cat > "${KSCREENLOCKER_RC}" <<'EOF'
[Daemon]
Autolock=false
Enabled=false
LockOnResume=false
Timeout=0
EOF
echo "   Written to ${KSCREENLOCKER_RC}."

echo ""
echo "Done. Steps 2-4 are already live. Step 1 (tsc=reliable) needs a VM"
echo "reboot to take effect - verify afterwards with:"
echo "  cat /sys/devices/system/clocksource/clocksource0/current_clocksource"
echo "(should keep reading 'tsc', including after the host pauses/resumes"
echo "the VM - previously it fell back to 'acpi_pm' after enough of that)."
echo ""
echo "If you ever land back in the stacked-greeter state before a reboot"
echo "happens, clean it up with: bash \"$(dirname "$0")/cleanup_stray_sddm_sessions.sh\""
