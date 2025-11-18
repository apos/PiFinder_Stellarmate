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

XML_FILENAME="${DRIVER_NAME}_driver.xml"
XML_SOURCE_FILE="${DRIVER_SOURCE_DIR}/indi_${XML_FILENAME}.in"
XML_DEST_FILE="/usr/share/indi/${XML_FILENAME}"

echo "   Installing driver-specific XML file to ${XML_DEST_FILE}"
sudo cp "${XML_SOURCE_FILE}" "${XML_DEST_FILE}"

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
