#! /usr/bin/bash

# This script compiles and installs the PiFinder INDI driver by integrating it
# into the indi_lx200_generic driver executable.

source $(dirname "$0")/functions.sh

LOG_FILE="${pifinder_stellarmate_dir}/indi_driver_build.log"
# Overwrite log file instead of appending
exec > >(tee "${LOG_FILE}") 2>&1

echo "############################################################"
echo "Starting PiFinder INDI Driver Integration Build Script"
echo "Timestamp: $(date)"
echo "############################################################"

DRIVER_NAME="pifinder_lx200"
INDI_TELESCOPE_DIR="${indi_source_dir}/drivers/telescope"
DRIVER_SOURCE_DIR="${indi_pifinder_dir}"
TELESCOPE_CMAKE_FILE="${INDI_TELESCOPE_DIR}/CMakeLists.txt"
CMAKE_BACKUP_FILE="${TELESCOPE_CMAKE_FILE}.pifinder.bak"
SOURCE_ENTRY="${DRIVER_NAME}.cpp"

# --- Cleanup Function ---
cleanup() {
    echo "-> Cleaning up build artifacts..."
    if [ -f "$CMAKE_BACKUP_FILE" ]; then
        echo "   Restoring original CMakeLists.txt from backup."
        sudo mv "$CMAKE_BACKUP_FILE" "$TELESCOPE_CMAKE_FILE"
    fi
    echo "   Removing copied driver source files."
    sudo rm -f "${INDI_TELESCOPE_DIR}/${DRIVER_NAME}.cpp"
    sudo rm -f "${INDI_TELESCOPE_DIR}/${DRIVER_NAME}.h"
    echo "   Cleaning build directory."
    sudo rm -rf "${indi_source_dir}/build"
}

# --clean-build | -c
if [[ "$1" == "--clean-build" ]]; then
    cleanup
    # Exit after cleaning if that's the only goal
    if [[ "$2" == "--only" ]]; then
        echo "-> Cleanup complete."
        exit 0
    fi
fi

echo "-> Preparing indi-source tree for build..."

# Create a backup of the original CMakeLists.txt if it doesn't exist
if [ ! -f "$CMAKE_BACKUP_FILE" ]; then
    echo "   Creating backup of CMakeLists.txt."
    sudo cp "$TELESCOPE_CMAKE_FILE" "$CMAKE_BACKUP_FILE"
else
    echo "   Backup file already exists. Restoring from it for a clean state."
    sudo cp "$CMAKE_BACKUP_FILE" "$TELESCOPE_CMAKE_FILE"
fi

echo "   Copying driver source files to ${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.cpp" "${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.h" "${INDI_TELESCOPE_DIR}/"

echo "   Patching main telescope CMakeLists.txt..."
if grep -qF "$SOURCE_ENTRY" "$TELESCOPE_CMAKE_FILE"; then
    echo "   Driver source entry already exists. No changes needed."
else
    echo "   Adding driver source entry to the indi_lx200generic target."
    sudo sed -i "/add_executable(indi_lx200generic/a \    ${SOURCE_ENTRY}" "$TELESCOPE_CMAKE_FILE"
fi

echo "-> Configuring the build..."
if [ ! -d "${indi_source_dir}/build" ]; then
    echo "   Build directory not found. Creating it."
    mkdir -p "${indi_source_dir}/build"
fi
cd "${indi_source_dir}/build"
cmake -DCMAKE_INSTALL_PREFIX=/usr ..

echo "-> Building the driver..."
make

echo "-> Installing the driver and XML file..."
sudo make install

XML_FILENAME="${DRIVER_NAME}_driver.xml"
XML_SOURCE_FILE="${DRIVER_SOURCE_DIR}/indi_${XML_FILENAME}.in"
XML_DEST_FILE="/usr/share/indi/${XML_FILENAME}"

echo "   Installing XML file to ${XML_DEST_FILE}"
sudo cp "${XML_SOURCE_FILE}" "${XML_DEST_FILE}"

# Get INDI version from the generated indiversion.h in the build directory
INDI_VERSION_MAJOR=$(grep "#define INDI_VERSION_MAJOR" indiversion.h | awk '{print $3}')
INDI_VERSION_MINOR=$(grep "#define INDI_VERSION_MINOR" indiversion.h | awk '{print $3}')

echo "   Configuring XML file with version ${INDI_VERSION_MAJOR}.${INDI_VERSION_MINOR}"
sudo sed -i "s|@INDI_DRIVERS_DIR@|/usr/bin|g" "${XML_DEST_FILE}"
sudo sed -i "s|@INDI_VERSION_MAJOR@|${INDI_VERSION_MAJOR}|g" "${XML_DEST_FILE}"
sudo sed -i "s|@INDI_VERSION_MINOR@|${INDI_VERSION_MINOR}|g" "${XML_DEST_FILE}"

echo "-> Build and installation complete."
echo "############################################################"
echo "Script finished."
echo "Timestamp: $(date)"
echo "Log file located at: ${LOG_FILE}"
echo "############################################################"
