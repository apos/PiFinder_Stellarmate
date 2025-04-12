
# PiFinder on Stellarmate 


### WARNING : this is is only a basic summary and the project highly experimental 
The main changes and installation of pifinder is made by the script /home/pifinder/PiFinder_Stellarmate/bin/pifinder_stellarmate_setup.sh
NOT by /home/pifinder/PiFinder/pifinder_setup.sh

## Prerequisites
- Stellarmate OS >= 1.8.1 (based on Debian Bookworm)
  See: https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html 
- Raspberry Pi 4
- PiFinder hardware (hat)

## Assumptions for running PiFinder on Stellarmate
1. The following services are fully managed soleyly by StellarMate OS: 
- GPSD
- WiFi (Hostap)
- IP

These services will not be altered through PiFinder's installation script (pifinder_setup.sh).

2. The installation of PiFinder within StellarMate OS is non destructive.  PiFinder service is running as "pifinder" user


# Pre installation steps 
Hint: the script "pifinder_stellarmate_setup.sh" does this for you !


Additionan installs on Stellarmate OS. 

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

### add pifinder to the sudoers group
pifinder ALL=(ALL) NOPASSWD: ALL

#### install additional Packages

    sudo apt-get update
    sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera


### add raspi boot 
The location of the config.txt on bookworm has changed to:
     /boot/firmware/config.txt

Add the following lines to the file:  
     # Pifinder main.py needs this: 
     dtoverlay=pwm-2chan

### Install PiFinder with the modified pifinder_setup.sh
This is mostly corresponding and follows the original installation guide from PiFinder: https://pifinder.readthedocs.io/en/release/software.html

#### Run raspi-config
Enable SPI / I2C. The screen and IMU use these to communicate.

    sudo raspi-config

    Select 3 - Interface Options
    Then I4 - SPI and choose Enable
    Then I5 - I2C and choose Enable


Then run the modified installation script (not the one from Brickbots)

    # wget -O - https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh
    wget -O - 


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

    pip install picamera2


# Tetra: 

The tetra3 import within PiFinder simply did not work
within the .venv environment - this was the only way to get tetra3 working.

Probably the structure integrating tetra3 within PiFinder module is not a good idea

See: https://tetra3.readthedocs.io/en/latest/installation.html#use-pip-to-download-and-install

Please install within the venv!

    pip install git+https://github.com/esa/tetra3.git


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



# Run the install script locally to test
## WARNING: Only tested locally as user "pifinder" - no field test

    cd /home/pifinder/PiFinder/python

    sudo chown -R pifinder:pifinder /home/pifinder/PiFinder
    find /home/pifinder/PiFinder/python -name '*.pyc' -delete
    find /home/pifinder/PiFinder/python -name '__pycache__' -type d -exec rm -rf {} +
    /home/pifinder/PiFinder/python/.venv/bin/python3 -m PiFinder.main
