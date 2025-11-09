#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

# This script is known to work with
pifinder_stellarmate_version_stable="2.3.0"

# This script is actually tested against this version
pifinder_stellarmate_version_testing="2.3.0"


############################################################
# MAIN
############################################################

############################################################
# Get some important vars and functinons
source $(pwd)/bin/functions.sh

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

# Add rights accessing hardware to user
sudo usermod -a -G spi ${USER}
sudo usermod -a -G gpio ${USER}
sudo usermod -a -G i2c ${USER}
sudo usermod -a -G video ${USER}

sudo chown -R ${USER}:${USER} ${pifinder_stellarmate_dir}

############################################################
# Check if a PiFinder installation already exists.
if [ -d "${pifinder_home}/PiFinder" ]; then
    echo "⚠️  An existing PiFinder installation was found at ${pifinder_home}/PiFinder."
    echo "❓ Please choose an action:"
    echo "   1. Delete the existing installation and reinstall from scratch."
    echo "   2. Update the existing installation with 'git pull'."
    echo "   3. Cancel the installation."
    read -p "Enter your choice (1, 2, or 3): " choice

    case "$choice" in
        1)
            echo "🗑️  Deleting the existing installation..."
            bash "${pifinder_stellarmate_bin}/uninstall_pifinder_stellarmate.sh" --selfmove
            sleep 4
            if [ -d "${pifinder_home}/PiFinder" ]; then
                echo "❌ ERROR: The PiFinder folder still exists after the uninstall attempt. Aborting setup."
                exit 1
            fi
            echo "Installation from scratch ..."
            cd "${pifinder_home}"
            git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
            sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
            ;;
        2)
            echo "🔄 Updating the existing installation with 'git pull'..."
            cd "${pifinder_home}/PiFinder"
            git pull
            sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
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
else
    echo "🚀 No existing installation found. Starting fresh..."
    cd "${pifinder_home}"
    git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
    sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
fi

# Install some package requirements
sudo apt-get update
sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera python3-picamera2


#########################################################################
# Make some Changes to the downloaded local installation files of PiFinder 
cd ${pifinder_home}/PiFinder
bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh

# Replace patched service files with the correct Stellarmate versions
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service ${pifinder_home}/PiFinder/pi_config_files/pifinder.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service ${pifinder_home}/PiFinder/pi_config_files/pifinder_splash.service

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
  echo "Python venv is active. Installing Requirements."
  install_requirements "${python_requirements}"
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

# Hipparcos catalog
if ls "${pifinder_dir}/astro_data/hip_main.dat"
then
  echo "hip_main.dat already installed"
else
  wget -O ${pifinder_dir}/astro_data/hip_main.dat https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat
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


CONFIG_FILE="/boot/firmware/config.txt"

echo "🔧 Ensuring required config.txt entries are present ..."

add_if_missing() {
    local line="$1"
    local marker="$2"
    if ! grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Added: $line"
    else
        echo "ℹ️  Already present: $line"
    fi
}

# Optionaler Marker, um PiFinder-Block zu kennzeichnen
add_if_missing "#Pifinder"

# Interfaces und Overlays
add_if_missing "dtparam=spi=on"
add_if_missing "dtparam=i2c_arm=on"
add_if_missing "dtparam=i2c_arm_baudrate=10000"
add_if_missing "dtoverlay=pwm,pin=13,func=4"
add_if_missing "dtoverlay=uart3"
add_if_missing "dtoverlay=pwm-2chan"  # Speziell für Bookworm

echo "✅ config.txt checks complete."



# Enable service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service /etc/systemd/system/pifinder.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service /etc/systemd/system/pifinder_splash.service

sudo systemctl daemon-reexec
sudo systemctl daemon-reload

sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash

echo "🔧 Starting PiFinder services ..."
sudo systemctl start pifinder
sudo systemctl start pifinder_splash

echo "##############################################"
echo "PiFinder setup complete. This is the version to run on Stellarmate OS (Pi4, Bookworm)"




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
  echo "Python venv is active. Installing Requirements."
  install_requirements "${python_requirements}"
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

# Hipparcos catalog
if ls "${pifinder_dir}/astro_data/hip_main.dat"
then
  echo "hip_main.dat already installed"
else
  wget -O ${pifinder_dir}/astro_data/hip_main.dat https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat
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


CONFIG_FILE="/boot/firmware/config.txt"

echo "🔧 Ensuring required config.txt entries are present ..."

add_if_missing() {
    local line="$1"
    local marker="$2"
    if ! grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Added: $line"
    else
        echo "ℹ️  Already present: $line"
    fi
}

# Optionaler Marker, um PiFinder-Block zu kennzeichnen
add_if_missing "#Pifinder"

# Interfaces und Overlays
add_if_missing "dtparam=spi=on"
add_if_missing "dtparam=i2c_arm=on"
add_if_missing "dtparam=i2c_arm_baudrate=10000"
add_if_missing "dtoverlay=pwm,pin=13,func=4"
add_if_missing "dtoverlay=uart3"
add_if_missing "dtoverlay=pwm-2chan"  # Speziell für Bookworm

echo "✅ config.txt checks complete."



# Enable service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service /etc/systemd/system/pifinder.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service /etc/systemd/system/pifinder_splash.service

sudo systemctl daemon-reexec
sudo systemctl daemon-reload

sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash

echo "🔧 Starting PiFinder services ..."
sudo systemctl start pifinder
sudo systemctl start pifinder_splash

echo "##############################################"
echo "PiFinder setup complete. This is the version to run on Stellarmate OS (Pi4, Bookworm)"
