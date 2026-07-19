#!/usr/bin/env bash

# Call with "--selfmove" to run from /tmp in background: ./uninstall_pifinder_stellarmate.sh --selfmove

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./functions.sh
source "${SCRIPT_DIR}/functions.sh"

# Every systemd unit this project installs into /etc/systemd/system. Keep in
# sync with the "cp ... /etc/systemd/system/" lines in
# pifinder_stellarmate_setup.sh - this list has drifted out of date at least
# once already (pifinder-setup.service, pifinder-fake-mode-autostart.service,
# pifinder-control-center.service and pifinder-numpad-bridge.service all
# postdate the original version of this script and were missing here).
SYSTEM_UNITS=(
    pifinder.service
    pifinder_splash.service
    pifinder-setup.service
    pifinder-fake-mode-autostart.service
    pifinder-control-center.service
    pifinder-numpad-bridge.service
)

SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"

_stop_disable_remove_units() {
    echo "🔧 Stopping PiFinder systemd units ..."
    for unit in "${SYSTEM_UNITS[@]}"; do
        sudo systemctl stop "$unit" 2>/dev/null
    done

    echo "🧹 Disabling PiFinder systemd units ..."
    for unit in "${SYSTEM_UNITS[@]}"; do
        sudo systemctl disable "$unit" 2>/dev/null
    done

    echo "🗑️  Removing systemd unit files ..."
    for unit in "${SYSTEM_UNITS[@]}"; do
        sudo rm -f "/etc/systemd/system/${unit}"
    done

    echo "🔄 Reloading systemd ..."
    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload
}

_remove_indi_drivers() {
    echo "🔭 Removing PiFinder INDI drivers ..."
    sudo rm -f /usr/bin/indi_pifinder_lx200
    sudo rm -f /usr/bin/indi_pifinder_mount_bridge
    # Leftover from the old lx200generic fat-binary/symlink approach, if present.
    sudo rm -f /usr/bin/indi_lx200_pifinder

    if [ -f "$SYSTEM_DRIVERS_XML" ]; then
        if grep -qF "PiFinder LX200" "$SYSTEM_DRIVERS_XML" || grep -qF "PiFinder Mount Bridge" "$SYSTEM_DRIVERS_XML"; then
            sudo sed -i '/<device label="PiFinder LX200"/,/<\/device>/d' "$SYSTEM_DRIVERS_XML"
            sudo sed -i '/<device label="PiFinder Mount Bridge"/,/<\/device>/d' "$SYSTEM_DRIVERS_XML"
            echo "   ✅ Removed driver entries from ${SYSTEM_DRIVERS_XML}"
            echo "   ℹ️  Restart the StellarMate Webmanager (from the GUI/VNC session, not SSH) to"
            echo "      drop them from its catalog: systemctl --user restart stellarmatewebmanager.service"
        else
            echo "   ℹ️  No PiFinder entries found in ${SYSTEM_DRIVERS_XML}"
        fi
    fi
}

_remove_gpiomem_udev_rule() {
    if [ -f /etc/udev/rules.d/99-gpiomem.rules ]; then
        echo "🔧 Removing /dev/gpiomem* udev rule ..."
        sudo rm -f /etc/udev/rules.d/99-gpiomem.rules
        sudo udevadm control --reload-rules
    fi
}

_unmask_wireplumber() {
    echo "🔊 Restoring WirePlumber/PipeWire (unmasking, if pifinder_pre_start.sh masked them) ..."
    local user_dir="${pifinder_home}/.config/systemd/user"
    for unit in wireplumber.service pipewire.service pipewire-pulse.service pipewire.socket pipewire-pulse.socket; do
        local target="${user_dir}/${unit}"
        # Only remove if it's still exactly the /dev/null mask we created -
        # never touch a real user unit file that happens to share the name.
        if [ -L "$target" ] && [ "$(readlink "$target")" = "/dev/null" ]; then
            rm -f "$target"
            echo "   ✅ ${unit} unmasked"
        fi
    done
    echo "   ℹ️  pipewire-libcamera was removed from the system during install (it conflicted with"
    echo "      PiFinder's camera access) - reinstall manually if you want it back: sudo pacman -S pipewire-libcamera"
}

_remove_lgpio_build() {
    local hw_model
    hw_model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
    if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
        echo "🔧 [Pi5] Removing lgpio build artifacts ..."
        sudo rm -f /usr/local/lib/liblgpio.so /usr/local/lib/liblgpio.so.1
        sudo ldconfig
        rm -rf "${pifinder_home}/lgpio-src"
        echo "   ℹ️  rpi-lgpio/lgpio Python packages lived inside the now-deleted venv - nothing"
        echo "      further to remove for those. /etc/ld.so.conf.d/local.conf was left in place"
        echo "      (harmless generic ldconfig search-path entry)."
    fi
}

_print_manual_cleanup_notes() {
    echo ""
    echo "ℹ️  Left in place deliberately (shared system config, not exclusively PiFinder's):"
    echo "    - /boot/config.txt: dtparam=spi=on, dtparam=i2c_arm=on, dtparam=i2c_arm_baudrate=10000,"
    echo "      dtoverlay=pwm,pin=13,func=4, dtoverlay=imx296, and (Pi4) dtoverlay=uart3 /"
    echo "      (Pi5) dtoverlay=pwm-2chan. Other hardware/StellarMate features may also depend on"
    echo "      SPI/I2C being enabled - review and remove by hand if you're sure nothing else needs them."
    echo "    - /etc/pacman.conf: 'IgnorePkg = python-libcamera' pin (prevents an incompatible"
    echo "      libcamera-vs-python-libcamera version mismatch) - remove by hand if desired."
    echo "    - Hardware group memberships added to your user (spi, gpio, i2c, kmem, input, video)."
}

echo "🚫 Uninstalling PiFinder (Stellarmate version) ..."

_stop_disable_remove_units
_remove_indi_drivers
_remove_gpiomem_udev_rule
_unmask_wireplumber
_remove_lgpio_build

echo "🗂️ Deleting PiFinder installation directory ..."
sudo rm -rf "${pifinder_dir}"

echo "⚠️  NOTE: The folder ${pifinder_data_dir} was NOT removed."
echo "    You can delete it manually if needed."

echo "📦 Optional: You may now remove the repository clone with:"
echo "    rm -rf ${pifinder_stellarmate_dir}"

_print_manual_cleanup_notes

echo "✅ Uninstall complete."


if [[ "${1:-}" == "--selfmove" ]]; then
    echo "🧪 Copying script to /tmp and executing in background ..."
    tmp_script="/tmp/uninstall_pifinder_stellarmate.sh"
    cp "$0" "$tmp_script"
    chmod +x "$tmp_script"
    echo "cd / && nohup \"$tmp_script\" --run > /tmp/uninstall_pifinder.log 2>&1 < /dev/null & disown" | bash
    echo "ℹ️  Script is now running in background from /tmp. Monitor with:"
    echo "    tail -f /tmp/uninstall_pifinder.log"
    exit 0
fi

# --reset mode: clean install and config, but keep user data, the repo, and
# the system-level integrations (systemd units, INDI drivers, udev rule) -
# only the venv/build state is wiped, ready for pifinder_stellarmate_setup.sh
# to rebuild it.
if [[ "${1:-}" == "--reset" ]]; then
    echo "♻️  Resetting PiFinder installation ..."
    sleep 1
    cd /

    echo "🔧 Stopping PiFinder core services ..."
    sudo systemctl stop pifinder.service pifinder_splash.service pifinder-setup.service 2>/dev/null

    echo "🧹 Cleaning Python virtual environment ..."
    sudo rm -rf "${python_venv}"

    echo "🧽 Removing leftover build artifacts and logs ..."
    sudo rm -rf "${pifinder_dir}/python/build"
    sudo rm -rf "${pifinder_dir}/python/dist"
    sudo rm -rf "${pifinder_dir}/python"/*.egg-info
    sudo find "${pifinder_dir}/python" -name __pycache__ -exec rm -rf {} +

    echo "♻️  PiFinder reset complete. You can now re-run the setup script:"
    echo "    ./pifinder_stellarmate_setup.sh"
    exit 0
fi

if [[ "${1:-}" == "--run" ]]; then
    echo "🔁 Running uninstall from /tmp ..."
    sleep 1
    cd /

    _stop_disable_remove_units
    _remove_indi_drivers
    _remove_gpiomem_udev_rule
    _unmask_wireplumber
    _remove_lgpio_build

    echo "🗂️ Deleting PiFinder installation directory ..."
    sudo rm -rf "${pifinder_dir}"
    sudo rm -rf "${pifinder_stellarmate_dir}"

    echo "⚠️  NOTE: The folder ${pifinder_data_dir} was NOT removed."
    echo "    You can delete it manually if needed."

    _print_manual_cleanup_notes

    echo "✅ Uninstall complete."
    exit 0
fi
