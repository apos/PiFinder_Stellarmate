#! /usr/bin/bash
set -euo pipefail

# Builds and installs the PiFinder Simulator INDI driver - a precisely,
# manually settable "sky truth" position for testing Mount Bridge's
# Auto-correct/Verify-Alert modes without a real mount or clear sky. See
# basic-memory pifinder-stellarmate/00164 and
# indi_pifinder_simulator/pifinder_simulator.h for the design (same
# standalone-build rationale as bin/build_indi_driver.sh /
# bin/build_indi_bridge.sh: links against system libindi, no INDI source
# checkout needed).

source "$(dirname "$0")/functions.sh"

SIM_DIR="${pifinder_stellarmate_dir}/indi_pifinder_simulator"
BUILD_DIR="${SIM_DIR}/build"
SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"

if [[ "${1:-}" == "--clean-build" ]]; then
    echo "-> Removing existing build directory..."
    rm -rf "${BUILD_DIR}"
fi

echo "-> Configuring..."
mkdir -p "${BUILD_DIR}"
cmake -S "${SIM_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

echo "-> Building..."
cmake --build "${BUILD_DIR}"

echo "-> Installing driver executable..."
sudo cp "${BUILD_DIR}/indi_pifinder_simulator" /usr/bin/indi_pifinder_simulator
sudo chmod +x /usr/bin/indi_pifinder_simulator

echo "-> Checking driver XML entry in ${SYSTEM_DRIVERS_XML}..."
if grep -qF "PiFinder Simulator" "${SYSTEM_DRIVERS_XML}"; then
    echo "   Entry already present. Skipping."
else
    DRIVER_XML_ENTRY="        <device label=\"PiFinder Simulator\" manufacturer=\"PiFinder\">\\n            <driver name=\"PiFinder Simulator\">indi_pifinder_simulator</driver>\\n            <version>1.0</version>\\n        </device>"
    sudo sed -i "/<devGroup group=\"Telescopes\">/a ${DRIVER_XML_ENTRY}" "${SYSTEM_DRIVERS_XML}"
    echo "   Entry added."
fi

echo ""
echo "Done. If the driver was already running, stop it first before installing,"
echo "or the cp above will fail with 'Text file busy'."
echo ""
echo "Restart the StellarMate Webmanager to see it in the catalog (from the"
echo "GUI/VNC session, not SSH): systemctl --user restart stellarmatewebmanager.service"
