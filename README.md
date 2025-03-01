
###############################
# Stellarmate Bookworm:;  add PiFinder user

sudo useradd -m pifinder
sudo passwd pifinder
sudo usermod -aG sudo pifinder
su - pifinder

# raspi boot - config.txt changed

### 
nano /boot/firmware/config.txt

# Pifinder main.py
dtoverlay=pwm-2chan

#### Then install PiFinder as described here:

https://pifinder.readthedocs.io/en/release/software.html

-  Enable SPI / I2C. The screen and IMU use these to communicate.

    run sudo raspi-config

    Select 3 - Interface Options

    Then I4 - SPI and choose Enable

    Then I5 - I2C and choose Enable


 - wget -O - https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh | bash

 You have to alter the files:


## - Alter the service 
##### pifinder.service
9c9
< ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.main
---
> ExecStart=/usr/bin/python -m PiFinder.main

#### pifinder_flash.service
6c6
< ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.splash
---
> ExecStart=/usr/bin/python -m PiFinder.splash



###############################
# Additional Packages

sudo apt-get update
sudo apt-get install libcap-dev python3-libcamera python3-venv


###############################
# Use venv


cd /home/pifinder/PiFinder/python
# Probably necessary to recreate
# rm -rf .venv
python3 -m venv /home/pifinder/PiFinder/python/.venv
source /home/pifinder/PiFinder/python/.venv/bin/activate
pip install -r /home/pifinder/PiFinder/python/requirements.txt


###############################
# PIP Additional requirements(.txt) within the venv
pip install picamera2

##############################
# rights for pifinder

sudo usermod -aG spi pifinder
sudo usermod -aG gpio pifinder
sudo usermod -aG i2c pifinder
sudo usermod -aG video pifinder



#########################
# PiFinder code 

## PiFinder

1. - alter PiFinder/main.py
(problems with finding libcamera soved by adding to syspath)

12,13d11
< import sys
< sys.path.append('/usr/lib/python3/dist-packages')



2. - alter PiFinder/solver.py 
(we create a __init__.py in PiFinder/tetra ... then using just "import" works)

24c24,25
< import cedar_detect_client
---
> from tetra3 import cedar_detect_client
>
153c154
<                             # OBSOLET match_max_error=0.005,
---
>                             match_max_error=0.005,



3. - import picamera2 fails on start
(add to PiFinder/camera_pi.py at the beginning)



import sys
print(sys.path)
from picamera2 import Picamera2
import libcamera


4. - ui

nano /home/pifinder/PiFinder/ui/marking_menus.py

# also import field
from dataclasses import dataclass, field 


# definition of up changed
@dataclass
class MarkingMenu:
    down: MarkingMenuOption
    left: MarkingMenuOption
    right: MarkingMenuOption
    ''' up: MarkingMenuOption = MarkingMenuOption(label="HELP")
    up: MarkingMenuOption = field(default_factory=MarkingMenuOption)
    '''
    up: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP"))

#########################
## Tetra: 

1. - the tetra3 import within PiFinder simply does not work
Within the .venv environment - this was the only way to get tetra3 working
See: https://tetra3.readthedocs.io/en/latest/installation.html#use-pip-to-download-and-install

pip install git+https://github.com/esa/tetra3.git



2. - import problems: Create and fill __init__.py

touch PiFinder/tetra3/__init__.py
echo -n "from .tetra3 import cedar_detect_client" > PiFinder/tetra3/__init__.py



3. - Alter PiFinder/tetra3/tetra3/cedar_detect_client.py

12c12,13
< from PiFinder.tetra3.tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc
---
> from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc 



4. - Alter PiFinder/tetra3/tetra3/tetra3.py

135,137c135,136
< from PiFinder.tetra3.tetra3.breadth_first_combinations import breadth_first_combinations
< from PiFinder.tetra3.tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density
<
---
> from tetra3.breadth_first_combinations import breadth_first_combinations
> from tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density

#########################
!!!!!!!!!!!!!!!!!!!!!!!!!
#########################
# Only tested locally as user "pifinder" - no field test


cd /home/pifinder/PiFinder/python

sudo chown -R pifinder:pifinder /home/pifinder/PiFinder
find /home/pifinder/PiFinder/python -name '*.pyc' -delete
find /home/pifinder/PiFinder/python -name '__pycache__' -type d -exec rm -rf {} +

/home/pifinder/PiFinder/python/.venv/bin/python3 -m PiFinder.main















