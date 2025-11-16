#! /usr/bin/bash

# This script compiles and installs the PiFinder INDI driver.
# It provides options for cleaning the build, getting the INDI source,
# and restarting the INDI server for testing.

# Get some important vars and functions
source $(dirname "$0")/functions.sh

# --- HELP FUNCTION ---
show_help() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo "Compiles and installs the PiFinder INDI driver. The standard build procedure"
    echo "is always run. Options below provide additional pre-build and post-build actions."
    echo ""
    echo "Options:"
    echo "  -a, --all              Equivalent to -g -c -i. Gets source, cleans, and starts interactive test."
    echo "  -c, --clean-build      Removes the existing build directory before compiling."
    echo "  -g, --get-indi-source  Clones the INDI library source code from GitHub if not present."
    echo "  -i, --indi-restart     Starts the interactive test session after a successful build."
    echo "  -h, --help             Display this help message and exit."
    echo ""
    echo "At least one option must be provided to run the script."
}

# --- SCRIPT ENTRY POINT ---
# If no arguments are provided, show help and exit.
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Log file for the script's output
LOG_FILE="${pifinder_stellarmate_dir}/indi_driver_build.log"
exec > >(tee "${LOG_FILE}") 2>&1

echo "############################################################"
echo "Starting PiFinder INDI Driver Build Script"
echo "Timestamp: $(date)"
echo "############################################################"


############################################################
# Default values for parameters
get_indi_source=false
indi_restart=false
clean_build=false

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -a|--all)
            get_indi_source=true
            indi_restart=true
            clean_build=true
            shift
            ;;
        -g|--get-indi-source)
            get_indi_source=true
            shift
            ;;
        -i|--indi-restart)
            indi_restart=true
            shift
            ;;
        -c|--clean-build)
            clean_build=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown parameter passed: $1"
            show_help
            exit 1
            ;;
    esac
done

############################################################
# --get-indi-source | -g
if [ "$get_indi_source" = true ]; then
    echo "-> Getting INDI source..."
    if [ -d "${indi_source_dir}" ]; then
        echo "   INDI source directory already exists. Skipping clone."
    else
        cd "${pifinder_stellarmate_dir}"
        git clone https://github.com/indilib/indi.git "${indi_source_dir}"
    fi
fi

############################################################
# --indi-restart | -i (Pre-script)
if [ "$indi_restart" = true ]; then
    echo "-> Stopping INDI server..."
    killall indiserver
fi

############################################################
# --clean-build | -c
if [ "$clean_build" = true ]; then
    echo "-> Cleaning build directory..."
    rm -rf "${indi_source_dir}/build"
    mkdir "${indi_source_dir}/build"
fi

############################################################
# Standard Procedure
############################################################

echo "-> Starting standard build procedure..."

# Check if indi-source directory exists
if [ ! -d "${indi_source_dir}" ]; then
    echo "   ERROR: INDI source directory not found. Please run with --get-indi-source."
    exit 1
fi

# Check if build directory exists
if [ ! -d "${indi_source_dir}/build" ]; then
    echo "   Build directory not found. Creating it."
    mkdir "${indi_source_dir}/build"
fi


echo "-> Integrating local driver with indi-source..."
# Create a subdirectory for our driver
DRIVER_SUBDIR="${indi_source_dir}/drivers/telescope/indi_pifinder"
mkdir -p "${DRIVER_SUBDIR}"

# Copy all our local driver files into the subdirectory
cp "${indi_pifinder_dir}/pifinder_lx200.h" "${DRIVER_SUBDIR}/"
cp "${indi_pifinder_dir}/pifinder_lx200.cpp" "${DRIVER_SUBDIR}/"
cp "${indi_pifinder_dir}/indi_pifinder_lx200_driver.xml.in" "${DRIVER_SUBDIR}/"
cp "${indi_pifinder_dir}/CMakeLists.txt" "${DRIVER_SUBDIR}/"

# Add our driver subdirectory to the main telescope CMakeLists.txt
CMAKE_FILE="${indi_source_dir}/drivers/telescope/CMakeLists.txt"
SUBDIR_ENTRY="add_subdirectory(indi_pifinder)"
if grep -q "add_subdirectory(indi_pifinder)" "${CMAKE_FILE}"; then
    echo "   Driver subdirectory entry already exists in CMakeLists.txt. Skipping patch."
else
    echo "   Adding driver subdirectory entry to CMakeLists.txt..."
    echo "" >> "${CMAKE_FILE}"
    echo "# Add PiFinder LX200 driver" >> "${CMAKE_FILE}"
    echo "${SUBDIR_ENTRY}" >> "${CMAKE_FILE}"
fi

echo "-> Removing old driver files..."
sudo rm -f /usr/share/indi/pifinder_lx200.xml
sudo rm -f /usr/bin/indi_pifinder_lx200

echo "-> Building the driver..."
cd "${indi_source_dir}/build"
cmake ..
make indi_pifinder_lx200

echo "-> Installing the driver..."
sudo cp drivers/telescope/indi_pifinder_lx200 /usr/bin/
sudo cp ../drivers/telescope/pifinder_lx200.xml /usr/share/indi/

echo "-> Build and installation complete."


############################################################
# --indi-restart | -i (Interactive Test Session)
if [ "$indi_restart" = true ]; then
    echo "-> Preparing for interactive test session..."
    log_dir="/home/${SUDO_USER:-${USER}}/.local/share/kstars/logs/$(date +%F)"

    echo "   -> Deleting old KStars logs for today to ensure a clean test..."
    mkdir -p "${log_dir}" # Ensure the directory exists before trying to remove files
    rm -f "${log_dir}"/log_*.txt
    echo "   -> Old logs deleted."

    echo ""
    echo "########################### ACTION REQUIRED ############################"
    echo "Please start KStars/Ekos now and connect to your profile containing"
    echo "the 'PiFinder LX200' driver. Perform any tests you need."
    echo "The script will wait for 30 seconds after you press ENTER."
    echo "######################################################################"
    read -p "Press ENTER to continue..."

    echo "-> Waiting 30 seconds for testing..."
    sleep 30

    echo "-> Capturing new KStars logs..."
    if ls "${log_dir}"/log_*.txt 1> /dev/null 2>&1; then
        echo "--- Appending KStars Logs ---"
        cat "${log_dir}"/log_*.txt
        echo "--- End of KStars Logs ---"
    else
        echo "   No new log file was found for today in ${log_dir}"
    fi
fi

echo "############################################################"
echo "Script finished."
echo "Timestamp: $(date)"
echo "Log file located at: ${LOG_FILE}"
echo "############################################################"
