
# PiFinder on Stellarmate - Overview

### WARNING : this is is only a basic summary and the project which is highly experimental 
- The script can not update an existing PiFinder installation
- The main changes and installation of pifinder is made by the script /home/pifinder/PiFinder_Stellarmate/bin/pifinder_stellarmate_setup.sh
- The script downloads and installs a default PiFinder installation into /home/pifinder/PiFinder. It then makes the necessary patches and adds additional functionality
- PiFinders GPS and WiFi/LAN  network management is NOT used, instead it uses the one from Stellarmate

# Table of Contents

- [PiFinder on Stellarmate - Overview](#pifinder-on-stellarmate---overview)
    - [WARNING : this is is only a basic summary and the project which is highly experimental](#warning--this-is-is-only-a-basic-summary-and-the-project-which-is-highly-experimental)
- [Table of Contents](#table-of-contents)
- [Prerequisites](#prerequisites)
    - [Run raspi-config](#run-raspi-config)
  - [Assumptions for running PiFinder on Stellarmate](#assumptions-for-running-pifinder-on-stellarmate)
  - [What the script does](#what-the-script-does)
    - [add PiFinder user](#add-pifinder-user)
      - [Add rights accessing hardware to user 'pifinder'](#add-rights-accessing-hardware-to-user-pifinder)
      - [add pifinder to the sudoers group](#add-pifinder-to-the-sudoers-group)
      - [install additional Packages](#install-additional-packages)
      - [add parameters to raspberry pi config.txt](#add-parameters-to-raspberry-pi-configtxt)
    - [Install PiFinder with the modified pifinder\_setup.sh](#install-pifinder-with-the-modified-pifinder_setupsh)
- [Changes to PiFinder code base](#changes-to-pifinder-code-base)
  - [PiFinder code](#pifinder-code)
- [Use venv](#use-venv)
- [PIP Additional requirements(.txt) within the venv](#pip-additional-requirementstxt-within-the-venv)
  - [Alter the pifinder service to use the virtual python environment](#alter-the-pifinder-service-to-use-the-virtual-python-environment)
        - [pifinder.service](#pifinderservice)
        - [pifinder\_splash.service](#pifinder_splashservice)
- [PiFinder Stellarmate – KStars Location Integration Overview](#pifinder-stellarmate--kstars-location-integration-overview)
  - [🔧 Purpose: Replace PiFinder's Native GPS with KStars-Based Geolocation](#-purpose-replace-pifinders-native-gps-with-kstars-based-geolocation)
  - [🧠 What the Location Writer Does](#-what-the-location-writer-does)
    - [📜 `/home/pifinder/PiFinder_Stellarmate/bin/kstars_location_writer.py`](#-homepifinderpifinder_stellarmatebinkstars_location_writerpy)
  - [⚙️ systemd Service Integration](#️-systemd-service-integration)
    - [📜 `/etc/systemd/system/pifinder_kstars_location_writer.service`](#-etcsystemdsystempifinder_kstars_location_writerservice)



# Prerequisites
- Stellarmate OS >= 1.8.1 (based on Debian Bookworm)
  See: https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html 
- Raspberry Pi 4
- PiFinder hardware (hat)

### Run raspi-config
Enable SPI / I2C. The screen and IMU use these to communicate.

    sudo raspi-config

    Select 3 - Interface Options
    Then I4 - SPI and choose Enable
    Then I5 - I2C and choose Enable

## Assumptions for running PiFinder on Stellarmate
1. The following services are fully managed soleyly by StellarMate OS: 
- GPSD
- WiFi (Hostap)
- IP

These services will not be altered through PiFinder's installation script (pifinder_setup.sh).

2. The installation of PiFinder within StellarMate OS is non destructive.  PiFinder service is running as "pifinder" user


## What the script does
Hint: the script "pifinder_stellarmate_setup.sh" does the following tasks:

### add PiFinder user
    sudo useradd -m pifinder
    sudo passwd pifinder
    sudo usermod -aG sudo pifinder
    su - pifinder

#### Add rights accessing hardware to user 'pifinder'
    sudo usermod -aG spi pifinder
    sudo usermod -aG gpio pifinder
    sudo usermod -aG i2c pifinder
    sudo usermod -aG video pifinder

#### add pifinder to the sudoers group
pifinder ALL=(ALL) NOPASSWD: ALL

#### install additional Packages

    sudo apt-get update
    sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera

#### add parameters to raspberry pi config.txt
The location of the config.txt on bookworm has changed to:
     /boot/firmware/config.txt

E.g. add the following lines to the file:  
     # Pifinder main.py needs this: 
     dtoverlay=pwm-2chan

### Install PiFinder with the modified pifinder_setup.sh
This is mostly corresponding and follows the original installation guide from PiFinder: https://pifinder.readthedocs.io/en/release/software.html




# Changes to PiFinder code base 

## PiFinder code 

✅ Key changes:

📁 solver.py
- sys.path.append(...) updated to use .parent
- "import tetra3" replaced with "from tetra3 import main"
- Adds "from tetra3 import cedar_detect_client" if missing

📁 tetra3/tetra3/__init__.py
- from .tetra3 import ... → from .main import ...

📁 tetra3/tetra3/cedar_detect_client.py
- from tetra3 import ... → from . import ...

📁 tetra3/tetra3/cedar_detect_pb2_grpc.py
- import cedar_detect_pb2 → from . import cedar_detect_pb2

📄 tetra3.py → Renamed to main.py
- Prevents conflicts with the tetra3 package name

📁 ui/marking_menus.py
- Adds "field" to dataclass import
- Replaces HELP menu init with a default_factory lambda

📁 pifinder_post_update.sh
- Adds virtual environment creation & activation after submodule init

📁 camera_pi.py
- Adds "from picamera2 import Picamera" after numpy import


# Use venv
The most important change is, that because of security reasons, it is not allowed to use global pyhton libraries in Python 3.11 any more. You can use them, if installed throught the OS package manager, but it is much better to use a dedicated local virtual environment for your python libraries and run the service with thi:

    # rm -rf .venv # remove an old environment 
    cd /home/pifinder/PiFinder/python
    python3 -m venv /home/pifinder/PiFinder/python/.venv
    source /home/pifinder/PiFinder/python/.venv/bin/activate
    pip install -r /home/pifinder/PiFinder/python/requirements.txt


# PIP Additional requirements(.txt) within the venv
This goes into requirements.txt

    e.g.   pip install picamera2


## Alter the pifinder service to use the virtual python environment

##### pifinder.service

    9c9
    < ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.main
    ---
    > ExecStart=/usr/bin/python -m PiFinder.main

##### pifinder_splash.service

    ##### pifinder_flash.service
    6c6
    < ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.splash
    ---
    > ExecStart=/usr/bin/python -m PiFinder.splash


# PiFinder Stellarmate – KStars Location Integration Overview

## 🔧 Purpose: Replace PiFinder's Native GPS with KStars-Based Geolocation

Instead of using a direct GPS module via `gpsd`, the PiFinder now fetches **location and time data from KStars**, which may be configured manually or received via INDI GPS devices. This is especially useful when Stellarmate handles GPS/time synchronization and PiFinder is running headless.

---

## 🧠 What the Location Writer Does

### 📜 `/home/pifinder/PiFinder_Stellarmate/bin/kstars_location_writer.py`

This Python script:

- Parses the `~/.config/kstarsrc` file from the KStars user session.
- Extracts the current location:
  - **Latitude**
  - **Longitude**
  - **Altitude**
  - **City & Country**
- Captures the current time in:
  - **UTC**
  - **Local time with offset**
- Writes all data into a plain-text file:  
  `/tmp/kstars_location.txt`

The file is updated every 10 seconds.

---

## ⚙️ systemd Service Integration

### 📜 `/etc/systemd/system/pifinder_kstars_location_writer.service`

This service ensures the writer script:

- **Starts at boot** in the graphical session.
- **Runs as user `stellarmate`** (same as the KStars session).
- **Creates `/tmp/kstars_location.txt`** with correct permissions:
  - Uses `Group=pifinder` so the PiFinder service (which runs as user `pifinder`) can read it.
  - Prepares the file with `ExecStartPre` commands (`touch`, `chmod`).

**Example:**

      ```ini
      [Unit]
      Description=KStars Location Writer for PiFinder
      After=graphical.target

      [Service]
      Type=simple
      ExecStartPre=/bin/touch /tmp/kstars_location.txt
      ExecStartPre=/bin/chmod 664 /tmp/kstars_location.txt
      ExecStart=/usr/bin/python3 /home/pifinder/PiFinder_Stellarmate/bin/kstars_location_writer.py
      Restart=always
      RestartSec=5
      User=stellarmate
      Group=pifinder
      Nice=10
      StandardOutput=journal
      StandardError=journal

      [Install]
      WantedBy=default.target

