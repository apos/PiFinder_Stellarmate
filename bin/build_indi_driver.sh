#! /usr/bin/bash

# This script compiles and installs the PiFinder INDI driver by integrating it
# into the indi_lx200_generic driver executable.
# It uses a git-based workflow for safety and reliability.

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
git commit -a -m "Automated commit before build: $(date)"
cd "${pifinder_stellarmate_dir}"

echo "-> Resetting indi-source directory to a clean state..."
cd "${indi_source_dir}"
git reset --hard
cd "${pifinder_stellarmate_dir}"

echo "-> Preparing indi-source tree for build..."
echo "   Copying driver source files to ${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.cpp" "${INDI_TELESCOPE_DIR}/"
sudo cp "${DRIVER_SOURCE_DIR}/${DRIVER_NAME}.h" "${INDI_TELESCOPE_DIR}/"

echo "   Patching main telescope CMakeLists.txt..."
if grep -qF "$SOURCE_ENTRY" "$TELESCOPE_CMAKE_FILE"; then
    echo "   Driver source entry already exists. Skipping patch."
else
    echo "   Adding driver source entry to the indi_lx200generic target."
    sudo sed -i "/add_executable(indi_lx200generic/a \    ${SOURCE_ENTRY}" "$TELESCOPE_CMAKE_FILE"
fi

echo "-> Configuring the build..."
mkdir -p "${indi_source_dir}/build"
cd "${indi_source_dir}/build"
cmake -DCMAKE_INSTALL_PREFIX=/usr ..

echo "-> Building the driver..."
make

echo "-> Safely installing the driver..."
echo "   Backing up ${SYSTEM_DRIVERS_XML} to ${DRIVERS_XML_BACKUP}"
sudo cp "${SYSTEM_DRIVERS_XML}" "${DRIVERS_XML_BACKUP}"

sudo make install

echo "   Restoring ${SYSTEM_DRIVERS_XML} from backup."
sudo mv "${DRIVERS_XML_BACKUP}" "${SYSTEM_DRIVERS_XML}"

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