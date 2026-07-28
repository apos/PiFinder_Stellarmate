# Builds and installs the PiFinder INDI drivers (PiFinder LX200 + Mount
# Bridge) and restarts the StellarMate Web Manager so they show up in its
# driver catalog. Extracted out of pifinder_stellarmate_setup.sh's "full"
# flow so both it and the new --mode=indi_only path (see
# docs/concepts/setup_indi_only_install_mode.md) call the exact same logic
# instead of drifting apart via copy-paste.
#
# Impure (real builds, real systemctl calls) - not unit-tested, same as
# os_install_packages(). Requires functions.sh's pifinder_stellarmate_bin
# and add_warning() to already be sourced/defined by the caller.

build_and_install_indi_drivers() {
    echo "🔧 Building and installing PiFinder INDI drivers ..."

    # Stop any already-running instance first, or installing the new binary
    # fails with "Text file busy". Try a graceful Web Manager stop, then make
    # sure via pkill regardless of whether the server was started through the
    # Web Manager or manually.
    if curl -s -o /dev/null http://localhost:8624/api/server/status 2>/dev/null; then
        curl -s -X POST http://localhost:8624/api/server/stop >/dev/null 2>&1 || true
    fi
    pkill -f indi_pifinder_lx200 2>/dev/null || true
    pkill -f indi_pifinder_mount_bridge 2>/dev/null || true
    sleep 1

    bash "${pifinder_stellarmate_bin}/build_indi_driver.sh" \
        && echo "✅ PiFinder LX200 driver installed." \
        || add_warning "PiFinder LX200 INDI driver build/install FAILED — run bin/build_indi_driver.sh manually to see why."

    bash "${pifinder_stellarmate_bin}/build_indi_bridge.sh" \
        && echo "✅ PiFinder Mount Bridge driver installed." \
        || add_warning "PiFinder Mount Bridge INDI driver build/install FAILED — run bin/build_indi_bridge.sh manually to see why."

    # The StellarMate Web Manager caches its driver catalog at its own
    # process startup - restart it so newly built/updated drivers show up.
    # Requires a GUI/VNC user session; skip quietly if unavailable (e.g. run
    # over plain SSH).
    if systemctl --user restart stellarmatewebmanager.service 2>/dev/null; then
        echo "✅ StellarMate Web Manager restarted — INDI driver catalog is up to date."
    else
        add_warning "Could not restart stellarmatewebmanager.service (no GUI/VNC session?). Restart it manually so the PiFinder INDI drivers show up in its catalog: systemctl --user restart stellarmatewebmanager.service"
    fi
}
