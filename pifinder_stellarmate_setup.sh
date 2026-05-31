#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

# This script is known to work with
pifinder_stellarmate_version_stable="2.5.1"

# This script is actually tested against this version
pifinder_stellarmate_version_testing="2.5.1"


############################################################
# MAIN
############################################################

############################################################
# Get some important vars and functinons
source $(pwd)/bin/functions.sh

# Define a lock file for resuming the script after venv activation
lock_file="${pifinder_stellarmate_dir}/.resume_from_venv"

# Source python venv if it exists
if [ -f "${python_venv}/bin/activate" ]; then
    source "${python_venv}/bin/activate"
fi

############################################################
# VERSION CHECK (Live check from GitHub)

# Read local PiFinder version
pifinder_local_version=$(cat "$(pwd)/version.txt" 2>/dev/null)

# Fetch online version from GitHub (release branch)
github_version=$(curl -s https://raw.githubusercontent.com/brickbots/PiFinder/release/version.txt | tr -d '\r')

echo "ℹ️  Local PiFinder version: $pifinder_local_version"
echo "ℹ️  GitHub PiFinder version: $github_version"

# Function to compare versions (returns 1 if $1 > $2)
version_gt() {
    [ "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1" ]
}

# Function to compare versions (returns 0 if equal)
version_eq() {
    [ "$1" = "$2" ]
}

# Main check
if version_eq "$github_version" "$pifinder_stellarmate_version_stable"; then
    echo "✅ PiFinder version $github_version matches STABLE version. Proceeding..."
elif version_gt "$github_version" "$pifinder_stellarmate_version_stable"; then
    echo "⚠️  Actual PiFinder version in Git-main ($github_version) is NEWER than tested version ($pifinder_stellarmate_version_stable)."
    echo "⚠️  Proceed only if you are testing new features."
    read -p "⚠️⚠️⚠️  Continue with installation? (yes/no): " confirm
    confirm="${confirm//[$'\r\n']}"
    if [[ "$confirm" != "yes" ]]; then
        echo "ℹ️  Installation cancelled by user."
        exit 0
    fi

    # Optional: Warn again if version is even newer than "testing"
    if version_gt "$github_version" "$pifinder_stellarmate_version_testing"; then
        echo "❌ GitHub version $github_version is NEWER than the last defined TESTING version $pifinder_stellarmate_version_testing."
        echo "❌ This might break your current test configuration."
        echo "❌❌❌ Exiting to prevent unintended test mismatches."
        exit 1
    fi
else
    echo "❌ PiFinder version $github_version is not supported by this Stellarmate patch script."
    echo "❌ Expected STABLE: $pifinder_stellarmate_version_stable or TESTING: $pifinder_stellarmate_version_testing"
    exit 1
fi

echo "$pifinder_stellarmate_version_stable" > "$(pwd)/version.txt"



############################################################
echo "ℹ️ INFO: running as user <<$(whoami)>> – assuming this is the correct Stellarmate setup user."

# Create hardware groups if missing (Arch/SMOS does not create these by default)
for grp in spi gpio i2c kmem input; do
    getent group "$grp" > /dev/null 2>&1 || sudo groupadd "$grp"
done

# Add rights accessing hardware to user
sudo usermod -a -G spi,gpio,i2c,video,kmem,input ${USER}

# udev rule for /dev/gpiomem access (Arch Linux)
echo 'SUBSYSTEM=="gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpiomem.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change /dev/gpiomem

sudo chown -R ${USER}:${USER} ${pifinder_stellarmate_dir}

############################################################
# Check if a PiFinder installation already exists.
if [ -d "${pifinder_home}/PiFinder" ]; then
    # If resuming, skip the prompt
    if [ -f "$lock_file" ] && is_venv_active "${python_venv}"; then
        echo "✅ Resuming installation after virtual environment activation."
    else
        echo "⚠️  An existing PiFinder installation was found at ${pifinder_home}/PiFinder."
        echo "❓ Please choose an action:"
        echo "   1. Delete the existing installation and reinstall from scratch."
        echo "   2. Update the existing installation with 'git reset --hard origin/release'."
        echo "   3. Cancel the installation."
        read -p "Enter your choice (1, 2, or 3): " choice
        choice="${choice//[$'\r\n']}"

        case "$choice" in
            1)
                sudo systemctl stop pifinder
                echo "🗑️  Deleting the existing PiFinder installation directory..."
                sudo rm -rf "${pifinder_home}/PiFinder"
                sleep 2 # Give some time for the deletion to complete
                if [ -d "${pifinder_home}/PiFinder" ]; then
                    echo "❌ ERROR: The PiFinder folder still exists after deletion. Aborting setup."
                    exit 1
                fi
                echo "Installation from scratch ..."
                cd "${pifinder_home}"
                git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
                find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                ;;
            2)
                sudo systemctl stop pifinder
                echo "🔄 Updating the existing installation with 'git reset --hard origin/release'..."
                cd "${pifinder_home}/PiFinder"
                git reset --hard origin/release
                git pull
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                ;;
            3)
                echo "ℹ️  Installation cancelled by user."
                exit 0
                ;;
            *)
                echo "❌ Invalid choice. Please run the script again and select 1, 2, or 3."
                exit 1
                ;;
        esac
    fi
else
    echo "🚀 No existing installation found. Starting fresh..."
    cd "${pifinder_home}"
    git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
    sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
    echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
    bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
fi

# Arch/SMOS: add core, extra, alarm repos if missing (pacman.conf resets after reboot)
grep -q "^\[core\]" /etc/pacman.conf || printf '\n[core]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/core\n\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n\n[alarm]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/alarm\n' | sudo tee -a /etc/pacman.conf > /dev/null
sudo pacman -Sy --noconfirm

# Install system package requirements (Arch/SMOS)
# libcamera 0.7.1+ uses pybind11 smart_holder — incompatible with picamera2 from pip.
# python-libcamera must stay at 0.7.0 — use cached package if available, then pin.
sudo pacman -S --noconfirm --needed \
    git python-pip python-virtualenv libcap \
    libcamera libcamera-ipa \
    openexr
# Prefer pinned package from repo, fall back to pacman cache
PYLIBCAM_PKG=$(ls "${pifinder_stellarmate_dir}/packages/python-libcamera-0.7.0-"*"-aarch64.pkg.tar.xz" 2>/dev/null | head -1)
[ -z "$PYLIBCAM_PKG" ] && PYLIBCAM_PKG=$(ls /var/cache/pacman/pkg/python-libcamera-0.7.0-*-aarch64.pkg.tar.xz 2>/dev/null | head -1)
if [ -n "$PYLIBCAM_PKG" ]; then
    echo "ℹ️  Installing python-libcamera 0.7.0 from cache (smart_holder fix) ..."
    sudo pacman -U --noconfirm "$PYLIBCAM_PKG"
else
    echo "⚠️  python-libcamera 0.7.0 not in cache — installing current (may need manual fix)"
    sudo pacman -S --noconfirm --needed python-libcamera
fi
grep -q "IgnorePkg.*python-libcamera" /etc/pacman.conf || \
    sudo sed -i '/^\[options\]/a IgnorePkg = python-libcamera' /etc/pacman.conf




#########################################################################
# Make some Changes to the downloaded local installation files of PiFinder 
cd ${pifinder_home}/PiFinder

# Replace patched service files with the correct Stellarmate versions
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service ${pifinder_home}/PiFinder/pi_config_files/pifinder.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service ${pifinder_home}/PiFinder/pi_config_files/pifinder_splash.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service ${pifinder_home}/PiFinder/pi_config_files/pifinder-setup.service

############################################
# Create swapfile BEFORE pip install — pip builds (numpy, pandas, picamera2)
# consume huge amounts of RAM and will kill the system without swap on Pi4
if [ ! -f /swapfile ]; then
    echo "🔧 Creating 2GB swapfile (btrfs-compatible, needed before pip install) ..."
    sudo touch /swapfile
    sudo chattr +C /swapfile 2>/dev/null || true
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap defaults 0 0" | sudo tee -a /etc/fstab
    echo "✅ Swapfile ready."
else
    # Ensure swap is active even if file exists (e.g. after reboot without fstab)
    swapon --show | grep -q /swapfile || sudo swapon /swapfile 2>/dev/null || true
    echo "ℹ️  Swapfile already exists and active."
fi

############################################
# Python version check: delete venv if system Python changed (e.g. after SMOS update)
if [ -f "${python_venv}/bin/python" ]; then
    venv_ver=$("${python_venv}/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    sys_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ -n "$venv_ver" ] && [ "$venv_ver" != "$sys_ver" ]; then
        echo "⚠️  Python version mismatch: venv=$venv_ver, system=$sys_ver — deleting venv for rebuild."
        rm -rf "${python_venv}"
    else
        echo "ℹ️  Python version OK: venv=$venv_ver, system=$sys_ver"
    fi
fi

############################################
# Create an activate3 VENV

# Check if venv is active and install requirements
if ! is_venv_active "${python_venv}"; then
  echo "Python venv is not active."

  # Check if venv directory exists
  if ! check_venv_exists "${python_venv}"; then
    echo "Python venv directory does not exist."
    # Create venv
    if create_venv "${python_venv}"; then
      echo " "
      echo "##### STOP ##########################################################"
      echo "##### DO NOT CLOSE THIS TERMINAL !!! MANUAL INPUT REQUIRED !!! ######"
      echo "The Python virtual environment was successfully created and MUST be activated manually."
      echo "Please run the following command in this terminal to activate the virtual environment."
      echo "Then rerun the scipt from within the new virtual environment (you see somthing like (.venv) after activation:"
      echo "" 
      echo "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"
      echo "source ${python_venv}/bin/activate"
      echo "./pifinder_stellarmate_setup.sh"
      echo "" 
      # Create the lock file before exiting
      touch "${lock_file}"
      # Exit the script, because venv must be activated   manually for Requirements installation
      exit 1
    else
      echo "Error creating Python venv. Aborting."
      exit 1 
    fi
  else
     echo -e "STOP: Python venv directory exists. Please activate the venv manually with:\n vvvvvvvv"
     echo "source ${python_venv}/bin/activate"
     echo -e "\nTHEN: run the script again to install the Requirements."
     exit 1 # Exit script because venv must be activated manually for Requirements installation
  fi
else
  # Venv seems active, but let's double-check if the directory is actually there
  if ! check_venv_exists "${python_venv}"; then
    echo "###################################################################"
    echo "WARNING: Your shell thinks a virtual environment is active,"
    echo "but the directory has been removed (likely during reinstallation)."
    echo "Please run 'deactivate' and then re-run this setup script."
    echo "###################################################################"
    exit 1
  else
    # Clean up the lock file if it exists, as we are now proceeding
    rm -f "${lock_file}"
    echo "Python venv is active. Installing Requirements."
    install_requirements "${python_requirements}"
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete

    # Install python-libinput 0.1.0 manually (0.3.0a0 unavailable; setup.py uses removed 'imp')
    echo "🔧 Installing python-libinput 0.1.0 (patched for Python 3.12+) ..."
    LIBINPUT_TMP=$(mktemp -d)
    curl -sL https://files.pythonhosted.org/packages/source/p/python-libinput/python-libinput-0.1.0.tar.gz \
        -o "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz"
    tar xzf "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz" -C "${LIBINPUT_TMP}"
    # Patch setup.py: replace removed 'imp' module with importlib.util
    sed -i 's/from imp import load_source/import importlib.util\ndef load_source(name, path):\n    spec = importlib.util.spec_from_file_location(name, path)\n    mod = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(mod)\n    return mod/' \
        "${LIBINPUT_TMP}/python-libinput-0.1.0/setup.py"
    nice -n 15 ionice -c 3 pip install "${LIBINPUT_TMP}/python-libinput-0.1.0/"
    rm -rf "${LIBINPUT_TMP}"
    echo "✅ python-libinput 0.1.0 installed."

    # Re-run patch script now that picamera2 is installed (drm_preview.py patch)
    echo "🔧 Applying drm_preview.py patch post pip-install (pykms not available on Arch) ..."
    # Use find instead of Python import (import fails without pykms installed)
    DRM_PY=$(find "${python_venv}" -name "drm_preview.py" 2>/dev/null | head -1)
    if [ -n "$DRM_PY" ]; then
        if grep -q "_pykms_available" "$DRM_PY"; then
            echo "  ℹ️  drm_preview.py already patched"
        else
            patch -N "$DRM_PY" < "${pifinder_stellarmate_dir}/diffs/drm_preview_smos.diff" && \
                echo "  ✅ drm_preview.py patched" || echo "  ⚠️  drm_preview.py patch failed"
        fi
    else
        echo "  ⚠️  picamera2 not found in venv — skipping"
    fi
  fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder

# NOT USED, PART OF STELLARMATE-OS: samba samba-common-bin dnsmasq hostapd dhcpd gpsd
# NOT USED, PART OF STELLARMATE-OS: Setup GPSD
# NOT USED, PART OF STELLARMATE-OS: sudo dpkg-reconfigure -plow gpsd
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/gpsd.conf /etc/default/gpsd

# data dirs
mkdir -p ~/PiFinder_data
mkdir -p ~/PiFinder_data/captures
mkdir -p ~/PiFinder_data/obslists
mkdir -p ~/PiFinder_data/screenshots
mkdir -p ~/PiFinder_data/solver_debug_dumps
mkdir -p ~/PiFinder_data/logs
chmod -R 777 ~/PiFinder_data

# Hipparcos catalog — check file exists AND is non-empty (>1MB)
HIP_DAT="${pifinder_dir}/astro_data/hip_main.dat"
HIP_MIN_SIZE=1000000
if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
    echo "ℹ️  hip_main.dat already installed"
else
    [ -f "$HIP_DAT" ] && rm -f "$HIP_DAT"  # remove empty/partial file
    echo "🔧 Downloading Hipparcos catalog..."
    HIP_URLS=(
        "https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://vizier.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://cdsarc.u-strasbg.fr/ftp/cats/I/239/hip_main.dat"
    )
    HIP_OK=false
    for url in "${HIP_URLS[@]}"; do
        echo "  Trying: $url"
        wget -q --timeout=30 -L -O "$HIP_DAT" "$url" 2>/dev/null
        if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
            echo "✅ hip_main.dat downloaded from $url"
            HIP_OK=true
            break
        else
            rm -f "$HIP_DAT"
        fi
    done
    if [ "$HIP_OK" = false ]; then
        echo "⚠️  hip_main.dat download failed from all mirrors."
        echo "    Plate solving with Hipparcos stars will be unavailable."
        echo "    Retry manually: wget -O ${HIP_DAT} https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
    fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder


###########################
# Not used: tf already installed (also service)
###########################

# Wifi config
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.* /etc
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.conf.sta /etc/dhcpcd.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dnsmasq.conf /etc/dnsmasq.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/hostapd.conf /etc/hostapd/hostapd.conf
# NOT USED, PART OF STELLARMATE-OS: echo -n "Client" > ~/PiFinder/wifi_status.txt
# NOT USED, PART OF STELLARMATE-OS: sudo systemctl unmask hostapd

# NOT USED, PART OF STELLARMATE-OS:  open permissisons on wpa_supplicant file so we can adjust network config
# NOT USED, PART OF STELLARMATE-OS:  sudo chmod 666 /etc/wpa_supplicant/wpa_supplicant.conf

# NOT USED, PART OF STELLARMATE-OS:  Samba config
# NOT USED, PART OF STELLARMATE-OS:  sudo cp ~/PiFinder/pi_config_files/smb.conf /etc/samba/smb.conf


if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo "❌ config.txt nicht gefunden!"; exit 1
fi

echo "🔧 Ensuring required config.txt entries are present ..."

# Add a line globally if not already present anywhere in config.txt
add_if_missing() {
    local line="$1"
    if ! grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Added: $line"
    else
        echo "ℹ️  Already present: $line"
    fi
}

# Add a line inside a specific [section] block; creates section if missing.
# Lines are only added once per section (idempotent).
add_to_section() {
    local section="$1"
    local line="$2"
    # Check if line already exists anywhere in file (avoid duplicates across sections)
    if grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "ℹ️  Already present: $line"
        return
    fi
    # Insert section header + line if section missing, else append after last line of section
    if ! grep -Fxq "[$section]" "$CONFIG_FILE"; then
        printf '\n[%s]\n%s\n' "$section" "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Created [$section] and added: $line"
    else
        # Append line after the section header
        sudo sed -i "/^\[$section\]/a $line" "$CONFIG_FILE"
        echo "✅ Added to [$section]: $line"
    fi
}

# Global entries (apply to all Pi models)
add_if_missing "dtparam=spi=on"
add_if_missing "dtparam=i2c_arm=on"

# Detect Pi model for model-specific overlays
hw_model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    # Pi5: PWM on GPIO13 (ALT0), uart3, imx296
    add_to_section "pi5" "dtparam=i2c_arm_baudrate=10000"
    add_to_section "pi5" "dtoverlay=pwm,pin=13,func=4"
    add_to_section "pi5" "dtoverlay=uart3"
    add_to_section "pi5" "dtoverlay=pwm-2chan"
    add_to_section "pi5" "dtoverlay=imx296"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    # Pi4: PWM on GPIO13 (ALT0), uart3, imx296 — NO pwm-2chan (would override to GPIO19)
    add_to_section "pi4" "dtparam=i2c_arm_baudrate=10000"
    add_to_section "pi4" "dtoverlay=pwm,pin=13,func=4"
    add_to_section "pi4" "dtoverlay=uart3"
    add_to_section "pi4" "dtoverlay=imx296"
fi

echo "✅ config.txt checks complete."

# Swapfile is created earlier (before pip install) — see above



# Enable service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service /etc/systemd/system/pifinder.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service /etc/systemd/system/pifinder_splash.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service /etc/systemd/system/pifinder-setup.service

sudo systemctl daemon-reexec
sudo systemctl daemon-reload

sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash
sudo systemctl enable pifinder-setup

echo "🔧 Starting PiFinder services ..."
sudo systemctl start pifinder-setup
sudo systemctl start pifinder
sudo systemctl start pifinder_splash

# INDI Driver Installation (Step 5 from indi_driver_compile.md, without indi_add_driver)
# Requires prior manual compilation — see bin/README_compile_indi.md
echo "🔧 Installing PiFinder LX200 INDI driver..."
INDI_BIN=~/indi-source/build/drivers/telescope/indi_pifinder_lx200
INDI_XML=${pifinder_stellarmate_dir}/indi_pifinder/indi_pifinder_driver.xml.in
if [ -f "$INDI_BIN" ] && [ -f "$INDI_XML" ]; then
    sudo cp "$INDI_BIN" /usr/bin/
    sudo cp "$INDI_XML" /usr/share/indi/pifinder_lx200.xml
    echo "✅ PiFinder LX200 INDI driver installed."
else
    echo "ℹ️  INDI driver binary not found — skipping (requires manual compilation)."
    echo "    See bin/README_compile_indi.md for instructions."
fi

# Detect Pi and OS versions for the final summary message
hw_model=$(tr -d '\0' < /proc/device-tree/model)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    current_pi="Pi 5"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    current_pi="Pi 4"
else
    current_pi="Unknown Pi"
fi
current_os=$(lsb_release -sc 2>/dev/null || grep "^ID=" /etc/os-release | cut -d= -f2)

echo "##############################################"
echo "✅ PiFinder setup complete."
echo "   - PiFinder Version: $github_version"
echo "   - PiFinder-Stellarmate Scripts: $pifinder_local_version"
echo "   - Hardware: $current_pi"
echo "   - OS: $current_os"
echo "##############################################"
