# Builds and installs the PiFinder INDI drivers (PiFinder LX200 + Mount
# Bridge + Simulator) and restarts the StellarMate Web Manager so they show
# up in its driver catalog. Extracted out of pifinder_stellarmate_setup.sh's
# "full" flow so both it and the new --mode=indi_only path (see
# docs/concepts/setup_indi_only_install_mode.md) call the exact same logic
# instead of drifting apart via copy-paste.
#
# The Simulator driver was added here after a real incident (2026-09-05):
# it used to be built only by manually running bin/build_indi_simulator.sh,
# so every normal setup/reinstall/update run left whatever copy happened to
# already be in /usr/bin untouched - on one real device that copy was over
# a month stale and silently missing a since-added INDI property
# (FOLLOW_MOUNT_DEVICE), which sent the Mount Bridge readiness self-heal
# watchdog into an infinite, log-spamming retry loop trying to set a
# property the old binary didn't have. "Full Simulation" is a first-class,
# GUI-surfaced feature now (not just a developer test tool), so it gets the
# same automatic-rebuild guarantee as the other two drivers.
#
# Impure (real builds, real systemctl calls) - not unit-tested, same as
# os_install_packages(). Requires functions.sh's pifinder_stellarmate_bin
# and add_warning() to already be sourced/defined by the caller.

# Restores the GSC guide-star catalog (gsc binary + /usr/share/GSC data) onto
# the System paths the System-built INDI drivers look in, copied from the
# KStars Flatpak. A profile containing any PiFinder driver launches every
# driver from System sources (the Web Manager loads only one drivers.xml per
# profile), and the System build ships without GSC - so CCD/Guide/Telescope
# Simulator render a blank star field and Ekos guiding / plate-solve align /
# autofocus don't work. A SMOS update resets the root filesystem and wipes
# these copies again, so this runs on every setup/update, not just once.
# Copied rather than symlinked: Flatpak update paths aren't stable.
# Non-fatal: warns when KStars' Flatpak isn't there to copy from.
ensure_gsc_catalog() {
    if [ -x /usr/local/bin/gsc ] && [ -n "$(ls -A /usr/share/GSC 2>/dev/null)" ]; then
        return 0
    fi
    local fp_loc fp_files
    fp_loc="$(flatpak info --show-location org.kde.kstars 2>/dev/null)"
    fp_files="${fp_loc}/files"
    if [ -z "${fp_loc}" ] || [ ! -x "${fp_files}/bin/gsc" ] || [ ! -d "${fp_files}/share/GSC" ]; then
        add_warning "GSC star catalog is missing and could not be restored (KStars Flatpak with gsc not found) - Ekos guiding/plate-solve align/autofocus on simulated or real images will see a blank star field."
        return 0
    fi
    echo "-> Restoring GSC star catalog from the KStars Flatpak ..."
    if sudo cp "${fp_files}/bin/gsc" /usr/local/bin/gsc \
        && sudo rm -rf /usr/share/GSC \
        && sudo cp -r "${fp_files}/share/GSC" /usr/share/GSC; then
        echo "✅ GSC star catalog restored."
    else
        add_warning "Restoring the GSC star catalog from the KStars Flatpak failed - copy ${fp_files}/bin/gsc to /usr/local/bin/gsc and ${fp_files}/share/GSC to /usr/share/GSC manually."
    fi
}

build_and_install_indi_drivers() {
    echo "🔧 Building and installing PiFinder INDI drivers ..."

    # Stop any already-running instance first, or installing the new binary
    # fails with "Text file busy". Try a graceful Web Manager stop, then make
    # sure via pkill regardless of whether the server was started through the
    # Web Manager or manually.
    #
    # Found live (2026-09-13), reported repeatedly ("nach dem Updatelauf...
    # funktioniert das automatische Default hier immer noch nicht"): this
    # stop was never paired with a restart, unlike bin/build_indi_onstep_fix.sh's
    # own version of this exact same "rebuild a binary in place" problem,
    # which already does capture-then-restore correctly. Every single
    # Update/Reinstall run calls this function, so every one of them
    # deterministically left the profile stopped afterward - no self-heal
    # or "remember what was running" layer downstream of this ever got a
    # chance to matter, because the run that's SUPPOSED to leave the
    # device working again was the one guaranteeing it didn't, every time.
    active_profile="$(curl -s http://localhost:8624/api/server/status 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0].get("active_profile",""))' 2>/dev/null || true)"
    if [ -n "${active_profile}" ]; then
        curl -s -X POST http://localhost:8624/api/server/stop >/dev/null 2>&1 || true
    fi
    pkill -f "^(/[^ ]*/)?indi_pifinder_lx200( |\$)" 2>/dev/null || true
    pkill -f "^(/[^ ]*/)?indi_pifinder_mount_bridge( |\$)" 2>/dev/null || true
    pkill -f "^(/[^ ]*/)?indi_pifinder_simulator( |\$)" 2>/dev/null || true
    sleep 1

    bash "${pifinder_stellarmate_bin}/build_indi_driver.sh" \
        && echo "✅ PiFinder LX200 driver installed." \
        || add_warning "PiFinder LX200 INDI driver build/install FAILED — run bin/build_indi_driver.sh manually to see why."

    bash "${pifinder_stellarmate_bin}/build_indi_bridge.sh" \
        && echo "✅ PiFinder Mount Bridge driver installed." \
        || add_warning "PiFinder Mount Bridge INDI driver build/install FAILED — run bin/build_indi_bridge.sh manually to see why."

    bash "${pifinder_stellarmate_bin}/build_indi_simulator.sh" \
        && echo "✅ PiFinder Simulator driver installed." \
        || add_warning "PiFinder Simulator INDI driver build/install FAILED — run bin/build_indi_simulator.sh manually to see why."

    ensure_gsc_catalog

    # The StellarMate Web Manager caches its driver catalog at its own
    # process startup - restart it so newly built/updated drivers show up.
    # Requires a GUI/VNC user session; skip quietly if unavailable (e.g. run
    # over plain SSH).
    if systemctl --user restart stellarmatewebmanager.service 2>/dev/null; then
        echo "✅ StellarMate Web Manager restarted — INDI driver catalog is up to date."
    else
        add_warning "Could not restart stellarmatewebmanager.service (no GUI/VNC session?). Restart it manually so the PiFinder INDI drivers show up in its catalog: systemctl --user restart stellarmatewebmanager.service"
    fi

    # Restore whatever was actually running before this function touched
    # anything - same reasoning/pattern as build_indi_onstep_fix.sh. A
    # short wait first: the Web Manager daemon just restarted above and
    # needs a moment to actually accept requests again.
    if [ -n "${active_profile}" ]; then
        sleep 2
        echo "-> Restarting Web Manager profile '${active_profile}' (was running before this rebuild)..."
        curl -s -X POST "http://localhost:8624/api/server/start/${active_profile// /%20}" >/dev/null 2>&1 || true
    fi
}
