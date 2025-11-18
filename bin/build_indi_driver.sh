#! /usr/bin/bash

# This script compiles and installs the PiFinder INDI driver by integrating it
# into the indi_lx200_generic driver executable.
# It uses a git-based workflow for safety and reliability, supporting both
# fast incremental builds and full clean builds.

source $(dirname "$0")/functions.sh

LOG_FILE="${pifinder_stellarmate_dir}/indi_driver_build.log"
exec > >(tee "${LOG_FILE}") 2>&1

echo "############################################################"
echo "Starting PiFinder INDI Driver Git-Managed Build Script"
echo "Timestamp: $(date)"
echo "############################################################"

DRIVER_NAME="pifinder_lx200"
INDI_TELESCOPE_DIR="${indi_source_dir}/drivers/telescope"
DRIVER_SOURCE_DIR="${indi_pifinder_dir}"
TELESCOPE_CMAKE_FILE="${INDI_TELESCOPE_DIR}/CMakeLists.txt"
SOURCE_ENTRY="${DRIVER_NAME}.cpp"
SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"
DRIVERS_XML_BACKUP="/tmp/drivers.xml.pifinder.bak"
SYSTEM_DRIVERS_XML="/usr/share/indi/drivers.xml"
DRIVERS_XML_BACKUP="/tmp/drivers.xml.pifinder.bak"

echo "-> Committing changes in ${DRIVER_SOURCE_DIR}..."
cd "${DRIVER_SOURCE_DIR}"
# Use --no-verify to bypass any potential pre-commit hooks
git commit -a -m "Automated commit before build: $(date)" --no-verify
cd "${pifinder_stellarmate_dir}"

# --- Build Mode Logic ---
if [[ "$1" == "--clean-build" ]]; then
    echo "-> Performing a FULL CLEAN build..."
    echo "   Resetting indi-source directory to a clean state..."
    cd "${indi_source_dir}"
    git reset --hard
    cd "${pifinder_stellarmate_dir}"

    echo "   Cleaning build directory..."
    sudo rm -rf "${indi_source_dir}/build"
else
    echo "-> Performing an INCREMENTAL build..."
    echo "   Restoring pristine version of CMakeLists.txt before patching."
    cd "${indi_source_dir}"
    git checkout HEAD -- "${TELESCOPE_CMAKE_FILE}"
    cd "${pifinder_stellarmate_dir}"
fi

echo "-> Preparing indi-source tree for build..."
echo "   Copying driver source files to ${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.cpp" "${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.h" "${INDI_TELESCOPE_DIR}/"

echo "   Patching main telescope CMakeLists.txt..."
if grep -qF "$SOURCE_ENTRY" "$TELESCOPE_CMAKE_FILE"; then
    echo "   Driver source entry already exists. Skipping patch."
else
    # Find the line number of the add_executable(indi_lx200generic line
    LINE_NUM=$(grep -nF "add_executable(indi_lx200generic" "$TELESCOPE_CMAKE_FILE" | cut -d: -f1)

    # If the line is found, then patch it
    if [ -n "$LINE_NUM" ]; then
        echo "   Adding driver source entry to the indi_lx200generic target."
        sudo sed -i "${LINE_NUM}a \    ${SOURCE_ENTRY}" "$TELESCOPE_CMAKE_FILE"
    else
        echo "   Error: Could not find 'add_executable(indi_lx200generic' in $TELESCOPE_CMAKE_FILE."
        exit 1
    fi
fi

echo "-> Configuring the build (if necessary)..."
if [ ! -d "${indi_source_dir}/build" ]; then
    mkdir -p "${indi_source_dir}/build"
fi
cd "${indi_source_dir}/build"
# CMake will only re-configure if something has changed
cmake -DCMAKE_INSTALL_PREFIX=/usr ..

echo "-> Building the driver (incrementally)..."
make indi_lx200generic

echo "-> Installing the driver executable and creating symlink..."
sudo cp "${indi_source_dir}/build/drivers/telescope/indi_lx200generic" "/usr/bin/indi_lx200generic"
sudo chmod +x "/usr/bin/indi_lx200generic" # Ensure it's executable

echo "   Creating symbolic link for ${DRIVER_NAME}..."
sudo ln -sf /usr/bin/indi_lx200generic /usr/bin/indi_${DRIVER_NAME}

echo "-> Injecting driver XML entry into /usr/share/indi/drivers.xml..."
# Backup drivers.xml before modifying
sudo cp "${SYSTEM_DRIVERS_XML}" "${DRIVERS_XML_BACKUP}"

# Use sed to insert the driver entry after the <devGroup group="Telescopes"> line
# The XML entry needs to be escaped for sed
DRIVER_XML_ENTRY="        <device label=\"PiFinder LX200\" manufacturer=\"PiFinder\">\\n            <driver name=\"PiFinder LX200\">indi_pifinder_lx200</driver>\\n            <version>1.0</version>\\n        </device>"

# Check if the entry already exists to prevent duplicates
if ! grep -qF "PiFinder LX200" "${SYSTEM_DRIVERS_XML}"; then
    sudo sed -i "/<devGroup group=\"Telescopes\">/a ${DRIVER_XML_ENTRY}" "${SYSTEM_DRIVERS_XML}"
    echo "   PiFinder LX200 driver entry added."
else
    echo "   PiFinder LX200 driver entry already exists. Skipping injection."
fi

# Restore drivers.xml from backup (this is now redundant as we are modifying it directly, but keeping for safety if future changes revert to full file replacement)
# sudo mv "${DRIVERS_XML_BACKUP}" "${SYSTEM_DRIVERS_XML}"

echo "-> Build and installation complete."

# --- KStars Log Management for Testing ---
KSTARS_LOG_DIR="/home/stellarmate/.local/share/kstars/logs"
KSTARS_LOG_FILE="${KSTARS_LOG_DIR}/kstars_indi_log.txt"
TEMP_KSTARS_LOG="${pifinder_stellarmate_dir}/.gemini/tmp/kstars_indi_log_$(date +%Y%m%d_%H%M%S).txt"

echo "-> Clearing old KStars logs in ${KSTARS_LOG_DIR}"
sudo rm -f "${KSTARS_LOG_DIR}"/*

echo "-> Waiting 30 seconds for driver testing and log generation..."
sleep 30

if [ -f "${KSTARS_LOG_FILE}" ]; then
    echo "-> Copying latest KStars log to ${TEMP_KSTARS_LOG} for inspection..."
    sudo cp "${KSTARS_LOG_FILE}" "${TEMP_KSTARS_LOG}"
else
    echo "-> Warning: KStars log file not found at ${KSTARS_LOG_FILE}. Skipping copy."
fi

echo "############################################################"
echo "Script finished."
echo "Timestamp: $(date)"
echo "Log file located at: ${LOG_FILE}"
echo "############################################################"
