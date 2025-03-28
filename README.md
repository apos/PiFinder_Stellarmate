
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

## PiFinder

### python/PiFinder/main.py
(problems with finding libcamera soved by adding to syspath)

    12,13d11
    < import sys
    < sys.path.append('/usr/lib/python3/dist-packages')



### python/tetra3/__init__.py
(we create a __init__.py in python/PiFinder/tetra ... then using just "import" works)

    touch python/tetra3(/__init_py
    echo -n "from .tetra3 import cedar_detect_client" > python/tetra3(/__init_py


### PiFinder/python/solver.py 
Alter the import and delete "match_max_error ..."

        24c24,25
        < import cedar_detect_client
        ---
        > from tetra3 import cedar_detect_client
        >
        153c154
        <                             # OBSOLET match_max_error=0.005,
        ---
        >                             match_max_error=0.005,



### import picamera2 fails on start
PiCamera is needed. Add to python/camera_pi.py at the beginning

    import sys
    print(sys.path)
    from picamera2 import Picamera2
    import libcamera


### ui/marking_menus.py

#### also import field
from dataclasses import dataclass, field 


#### definition of up changed
    @dataclass
    class MarkingMenu:
        down: MarkingMenuOption
        left: MarkingMenuOption
        right: MarkingMenuOption
        ''' up: MarkingMenuOption = MarkingMenuOption(label="HELP")
        up: MarkingMenuOption = field(default_factory=MarkingMenuOption)
        '''
        up: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP"))


### python/PiFinder/tetra3/__init__.py
Import problems. 

    touch python/PiFinder/tetra3/__init__.py
    echo -n "from .tetra3 import cedar_detect_client" > python/PiFinder/tetra3/__init__.py


### python/PiFinder/tetra3/tetra3/cedar_detect_client.py
This "hack" only works, if Tetra 3 was installed before via git

        12c12,13
        < from PiFinder.tetra3.tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc
        ---
        > from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc 



### python/PiFinder/tetra3/tetra3/tetra3.py

        135,137c135,136
        < from PiFinder.tetra3.tetra3.breadth_first_combinations import breadth_first_combinations
        < from PiFinder.tetra3.tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density
        <
        ---
        > from tetra3.breadth_first_combinations import breadth_first_combinations
        > from tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density




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
