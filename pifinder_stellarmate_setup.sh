#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

# ToDo: source...
pifinder_stellarmate_dir="/home/pifinder/PiFinder_Stellarmate"
pifinder_stellarmate_bin="/home/pifinder/PiFinder_Stellarmate/bin"
pifinder_dir="/home/pifinder/PiFinder"
python_venv="${pifinder_dir}/python/.venv"
python_requirements="${pifinder_dir}/python/requirements.txt" # Pfad zur requirements.txt


# Ensure, to be in the correct directory
cd /home/pifinder


# check if user is "pifinder"
if [ $(whoami) != "pifinder" ]
then
    echo "ERROR: actual user is NOT <<pifinder>> but <<$(whoami)>>. Please login with e.g. 'su - pifinder' to run this install script"
    exit 0
else 
    cd ${HOME}
fi

# Check, if there is already a PiFinder installation, if yes abort. 
if [ -d PiFinder]
then
    echo "ERROR: There is already a PiFinder installation. Aborting installation. E.g. first rename the old directory."
    exit 0
fi

# add PiFinder user
sudo useradd -m pifinder
sudo passwd pifinder
sudo usermod -aG 

# Add rights accessing hardware to user 'pifinder'
sudo usermod -aG spi pifinder
sudo usermod -aG gpio pifinder
sudo usermod -aG i2c pifinder
sudo usermod -aG video pifinder

# Install some package requirements
sudo apt-get update
sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera

# Download the actual source code 
git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
cd /home/pifinder/PiFinder

# NOT / LATER USED BECAUSE OF VENV: sudo pip install -r python/requirements.txt

# Make some Changes to the downloaded local installation files of PiFinder 
bash ${pifinder_stellarmate_bin}/alter_PiFinder_installation_files.sh


############################################
# VENV
############################################
is_venv_active() {
  local venv_path="$1"

  if [ -n "${VIRTUAL_ENV}" ] && [ "${VIRTUAL_ENV}" = "${venv_path}" ]; then
    echo "Python venv '${venv_path}' is active."
    return 0 # True: venv is active
  else
    echo "Python venv '${venv_path}' is NOT active."
    return 1 # False: venv is not active
  fi
}

check_venv_exists() {
  local venv_path="$1"
  if [ -d "${venv_path}" ]; then
    echo "Python venv directory '${venv_path}' exists."
    return 0 # True: venv directory exists
  else
    echo "Python venv directory '${venv_path}' does NOT exist."
    return 1 # False: venv directory does not exist
  fi
}

create_venv() {
  local venv_path="$1"
  echo "Creating Python venv in '${venv_path}'..."
  python3 -m venv "${venv_path}"
  if [ $? -eq 0 ]; then
    echo "Python venv successfully created in '${venv_path}'."
    return 0 # True: venv created successfully
  else
    echo "Error creating Python venv in '${venv_path}'."
    return 1 # False: venv creation failed
  fi
}

install_requirements() {
  local requirements_file="$1"
  echo "Installing Python Requirements from '${requirements_file}'..."
  pip install -r "${requirements_file}"
  if [ $? -eq 0 ]; then
    echo "Python Requirements installed successfully."
    return 0 # True: requirements installed successfully
  else
    echo "Error installing Python Requirements."
    return 1 # False: requirements installation failed
  fi
}

############################################################
# Check if venv is active and install requirements
if ! is_venv_active "${python_venv}"; then
  echo "Python venv is not active."

  # Check if venv directory exists
  if ! check_venv_exists "${python_venv}"; then
    echo "Python venv directory does not exist."
    # Create venv
    if create_venv "${python_venv}"; then
      echo "Python venv successfully created. Please activate the venv manually with:"
      echo "source ${python_venv}/bin/activate"
      echo "and run the script again to install the Requirements."
      exit 1 # Exit script because venv must be activated manually for Requirements installation
    else
      echo "Error creating Python venv. Aborting."
      exit 1
    fi
  else
     echo "Python venv directory exists. Please activate the venv manually with:"
     echo "source ${python_venv}/bin/activate"
     echo "and run the script again to install the Requirements."
     exit 1 # Exit script because venv must be activated manually for Requirements installation
  fi
else
  echo "Python venv is active. Installing Requirements."
  install_requirements "${python_requirements}"
fi



# install tetra from repo
# Within the .venv environment - this was the only way to get tetra3 working
# See: https://tetra3.readthedocs.io/en/latest/installation.html#use-pip-to-download-and-install
if ! is_venv_active "${python_venv}"
then
    echo "Python venv <${python_venv}> is not active. Exiting installation. Please check, why."
    exit 0
else
    pip install git+https://github.com/esa/tetra3.git
fi  

# NOT USED, PART OF STELLARMATE-OS: samba samba-common-bin dnsmasq hostapd dhcpd gpsd


# ensure, correct rights are set
sudo chown -R pifinder:pifinder /home/pifinder/PiFinder

# NOT USED, PART OF STELLARMATE-OS: Setup GPSD
# NOT USED, PART OF STELLARMATE-OS: sudo dpkg-reconfigure -plow gpsd
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/gpsd.conf /etc/default/gpsd

# data dirs
mkdir ~/PiFinder_data
mkdir ~/PiFinder_data/captures
mkdir ~/PiFinder_data/obslists
mkdir ~/PiFinder_data/screenshots
mkdir ~/PiFinder_data/solver_debug_dumps
mkdir ~/PiFinder_data/logs
chmod -R 777 ~/PiFinder_data

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

# Hipparcos catalog
wget -O /home/pifinder/PiFinder/astro_data/hip_main.dat https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat


# Enable interfaces
echo "#Pifinder" | sudo tee -a /boot/firmware/config.txt
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
echo "dtparam=i2c_arm_baudrate=10000" | sudo tee -a /boot/firmware/config.txt
echo "dtoverlay=pwm,pin=13,func=4" | sudo tee -a /boot/firmware/config.txt
echo "dtoverlay=uart3" | sudo tee -a /boot/firmware/config.txt
# This is new for bookworm
echo "dtoverlay=pwm-2chan" | sudo tee -a /boot/firmware/config.txt



# Enable service
sudo cp /home/pifinder/PiFinder/pi_config_files/pifinder.service /lib/systemd/system/pifinder.service
sudo cp /home/pifinder/PiFinder/pi_config_files/pifinder_splash.service /lib/systemd/system/pifinder_splash.service
sudo systemctl daemon-reload
sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash

echo "##############################################"
echo "PiFinder setup complete, please restart the Pi"

