#! /usr/bin/bash
set -euo pipefail

# Builds and installs the PiFinder Mount Bridge INDI driver - the optional
# component that couples PiFinder's position to whichever real INDI mount
# driver is active. See basic-memory pifinder-stellarmate/00009 for the
# design and pifinder-stellarmate/00012 for why this is a standalone build
# (same rationale as bin/build_indi_driver.sh: links against system libindi,
# no INDI source checkout needed).

source "$(dirname "$0")/functions.sh"

BRIDGE_DIR="${pifinder_stellarmate_dir}/indi_pifinder_bridge"
BUILD_DIR="${BRIDGE_DIR}/build"
SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"

if [[ "${1:-}" == "--clean-build" ]]; then
    echo "-> Removing existing build directory..."
    rm -rf "${BUILD_DIR}"
fi

echo "-> Configuring..."
mkdir -p "${BUILD_DIR}"
cmake -S "${BRIDGE_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

echo "-> Building..."
cmake --build "${BUILD_DIR}"

echo "-> Installing driver executable..."
stop_indi_driver_and_wait "indi_pifinder_mount_bridge"
# Replace atomically (copy next to the target, then rename over it): a plain
# `cp` over a binary that is still executing fails with "Text file busy", and
# something (Web Manager profile autostart, the Control Center's self-heal)
# may respawn the driver between stop_indi_driver_and_wait and this line.
# rename(2) just swaps the directory entry - a running instance keeps its old
# inode until it is restarted.
sudo cp "${BUILD_DIR}/indi_pifinder_mount_bridge" /usr/bin/indi_pifinder_mount_bridge.new
sudo chmod +x /usr/bin/indi_pifinder_mount_bridge.new
sudo mv -f /usr/bin/indi_pifinder_mount_bridge.new /usr/bin/indi_pifinder_mount_bridge

echo "-> Checking driver XML entry in ${SYSTEM_DRIVERS_XML}..."
if grep -qF "PiFinder Mount Bridge" "${SYSTEM_DRIVERS_XML}"; then
    echo "   Entry already present. Skipping."
else
    DRIVER_XML_ENTRY="        <device label=\"PiFinder Mount Bridge\" manufacturer=\"PiFinder\">\\n            <driver name=\"PiFinder Mount Bridge\">indi_pifinder_mount_bridge</driver>\\n            <version>1.0</version>\\n        </device>"
    sudo sed -i "/<devGroup group=\"Auxiliary\">/a ${DRIVER_XML_ENTRY}" "${SYSTEM_DRIVERS_XML}"
    echo "   Entry added."
fi

echo ""
echo "Done. (Any already-running instance was stopped automatically before"
echo "installing, to avoid a 'Text file busy' cp failure.)"
echo ""
echo "Restart the StellarMate Webmanager to see it in the catalog (from the"
echo "GUI/VNC session, not SSH): systemctl --user restart stellarmatewebmanager.service"
