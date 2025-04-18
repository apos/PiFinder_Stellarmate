#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh

#################################
# MAIN
#################################

# Check, if there is already a PiFinder installation, if yes abort. 
if [ -d PiFinder ]
then
    echo "ERROR: There is already a PiFinder installation. Aborting installation. E.g. first rename the old directory."
    # exit 0
else
    echo "Installation from scratch ..."
    # Ensure, to be in the correct directory
    cd /home/pifinder
fi


# check if user is "pifinder"
if [ $(whoami) != "pifinder" ]
then
    echo "ERROR: actual user is NOT <<pifinder>> but <<$(whoami)>>. Please login with e.g. 'su - pifinder' to run this install script"
    exit 0
else 
    # add PiFinder user
    if check_user_exists "pifinder"
    then 
      echo "continuing ..."
    else
      sudo useradd -m pifinder
      sudo passwd pifinder
      sudo usermod -aG 

      # Add rights accessing hardware to user 'pifinder'
      sudo usermod -aG spi pifinder
      sudo usermod -aG gpio pifinder
      sudo usermod -aG i2c pifinder
      sudo usermod -aG video pifinder

      append_file="/etc/sudoers.d/010_pi-nopasswd"
      append_line="pifinder ALL=(ALL) NOPASSWD: ALL"
      if ! check_line_exists "${append_file}" "${append_line}"; then
        append_line_to_file "${append_file}" "${append_line}"
      else
        echo "Line '${append_line}' already exists in '${append_file}'. No need to append."
      fi

      echo "User PiFinder had to be instantiated. Please reboot before continuing."
      exit 0
    fi
fi

# Install some package requirements
sudo apt-get update
sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera python3-picamera2


# Download the actual source code 
git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
sudo chown -R pifinder:pifinder /home/pifinder/PiFinder


#########################################################################
# Make some Changes to the downloaded local installation files of PiFinder 
#########################################################################
cd /home/pifinder/PiFinder
bash ${pifinder_stellarmate_bin}/alter_PiFinder_installation_files.sh


############################################
# Create an activate3 VENV
############################################

# Check if venv is active and install requirements
if ! is_venv_active "${python_venv}"; then
  echo "Python venv is not active."

  # Check if venv directory exists
  if ! check_venv_exists "${python_venv}"; then
    echo "Python venv directory does not exist."
    # Create venv
    if create_venv "${python_venv}"; then
      echo " "
      echo "##### STOP ##############################################################"
      echo " MANUAL INPUT REQUIRED: Python venv successfully created."
      echo "You have to activate the venv manually and then re-run this setup script:"
      echo "" 
      echo "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"
      echo "source ${python_venv}/bin/activate"
      echo "./pifinder_stellarmate_setup.sh"
      echo "" 
      echo "##### GO ON #############################################################"
      
      # Exit the script, because venv must be activated manually for Requirements installation
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
sudo chown -R pifinder:pifinder /home/pifinder/PiFinder

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
sudo chown -R pifinder:pifinder /home/pifinder/PiFinder


###########################
# If already installed (also service)
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
sudo cp /home/pifinder/PiFinder/pi_config_files/pifinder.service /lib/systemd/system/pifinder.service
sudo cp /home/pifinder/PiFinder/pi_config_files/pifinder_splash.service /lib/systemd/system/pifinder_splash.service
sudo systemctl daemon-reload
sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash

echo "##############################################"
echo "PiFinder setup complete, please restart the Pi. This is the version to run on Stellarmate OS (Pi4, Bookworm)"

