#! /usr/bin/bash
set -euo pipefail

# Builds and installs the PiFinder LX200 INDI driver.
#
# Standalone driver: links directly against the system's libindi
# (libindilx200, libindidriver, both installed via pacman/apt as part of
# the libindi package) - no INDI source checkout, no full INDI build needed.
# Replaces the old lx200generic fat-binary approach (see basic-memory
# pifinder-stellarmate/00008 for why).

source "$(dirname "$0")/functions.sh"

BUILD_DIR="${indi_pifinder_dir}/build"
SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"

if [[ "${1:-}" == "--clean-build" ]]; then
    echo "-> Removing existing build directory..."
    rm -rf "${BUILD_DIR}"
fi

echo "-> Configuring..."
mkdir -p "${BUILD_DIR}"
cmake -S "${indi_pifinder_dir}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

echo "-> Building..."
cmake --build "${BUILD_DIR}"

echo "-> Installing driver executable..."
stop_indi_driver_and_wait "indi_pifinder_lx200"
sudo cp "${BUILD_DIR}/indi_pifinder_lx200" /usr/bin/indi_pifinder_lx200
sudo chmod +x /usr/bin/indi_pifinder_lx200

# Remove artifacts from the old lx200generic fat-binary/symlink approach, if present.
sudo rm -f /usr/bin/indi_lx200_pifinder

echo "-> Checking driver XML entry in ${SYSTEM_DRIVERS_XML}..."
if grep -qF "PiFinder LX200" "${SYSTEM_DRIVERS_XML}"; then
    echo "   Entry already present. Skipping."
else
    DRIVER_XML_ENTRY="        <device label=\"PiFinder LX200\" manufacturer=\"PiFinder\">\\n            <driver name=\"PiFinder LX200\">indi_pifinder_lx200</driver>\\n            <version>1.0</version>\\n        </device>"
    sudo sed -i "/<devGroup group=\"Telescopes\">/a ${DRIVER_XML_ENTRY}" "${SYSTEM_DRIVERS_XML}"
    echo "   Entry added."
fi

echo ""
echo "Done. (Any already-running instance was stopped automatically before"
echo "installing, to avoid a 'Text file busy' cp failure.)"
echo ""
echo "The StellarMate Webmanager caches its driver catalog at its own startup -"
echo "restart it to see a newly-added driver (must run from the GUI/VNC"
echo "session, not SSH - see basic-memory pifinder-stellarmate/00011):"
echo "  systemctl --user restart stellarmatewebmanager.service"
