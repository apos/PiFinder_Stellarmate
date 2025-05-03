# PiFinder on Stellarmate

> ### ⚠️ **Warning**
> 
> *   This is is work in progress and (at the moment) highly experimental.
> *   This is verified to work with the Piversion in "version.txt"
> *   This project is not an official PiFinder (R) project. It is on your own to understand, how the script works. I am not responsible for any damage to your hard- or software by using this code.

> ### ℹ️ **Info**
> 
> *   The main changes and installation of PiFinder is made by the script `/home/pifinder/PiFinder_Stellarmate/bin/pifinder_stellarmate_setup.sh`
> *   The script can not (yet) update an existing PiFinder installation.
> *   There is no uninstall routine. You only can delete `/home/pifinder/PiFinder` and re-run the script.
> *   The folder `/home/pifinder/PiFinder_Stellarmate` persists. All Updates of PiFinder Code and so on have to be done from there, not from PiFinders Update tools.
> *   The script downloads and installs the a known to work an tested  default PiFinder installation into `/home/pifinder/PiFinder`. It then makes the necessary patches and adds additional functionalities.
> *   PiFinders GPS and WiFi/LAN network management is NOT used, instead it uses the one from Stellarmate.

# Table of Contents

*   [PiFinder on Stellarmate](#pifinder-on-stellarmate)
*   [Table of Contents](#table-of-contents)
*   [Purpose](#purpose)
*   [Differences beetween using PiFinder on StellarMate and a stock PiFinder](#differences-beetween-using-pifinder-on-stellarmate-and-a-stock-pifinder)
    *   [GPS and WIFI/LAN only from Stellarmate or the OS (Debian Bookworm)](#gps-and-wifilan-only-from-stellarmate-or-the-os-debian-bookworm)
    *   [PiFinder Menu items removed](#pifinder-menu-items-removed)
    *   [PiFinder Web-Interface](#pifinder-web-interface)
*   [Installation](#installation)
    *   [General Prerequisites](#general-prerequisites)
    *   [Let's go - 1. Pre Installation steps - preparation of Pi and Debian OS (part one)](#lets-go---1-pre-installation-steps---preparation-of-pi-and-debian-os-part-one)
        *   [raspi-config (this is not done by the script!)](#raspi-config-this-is-not-done-by-the-script)
        *   [Add PiFinder user to Stellarmate OS](#add-pifinder-user-to-stellarmate-os)
        *   [Add rights for hardware access to user 'pifinder'](#add-rights-for-hardware-access-to-user-pifinder)
        *   [Add user pifinder to the sudoers group](#add-user-pifinder-to-the-sudoers-group)
        *   [⚠️ Reboot (first time)](#%EF%B8%8F-reboot-first-time)
    *   [Let's go - 2. Installation (part two and three)](#lets-go---2-installation-part-two-and-three)
        *   [Part one (get the repo and run the script)](#part-one-get-the-repo-and-run-the-script)
        *   [Part two (source the new virtual python environment and restart the script)](#part-two-source-the-new-virtual-python-environment-and-restart-the-script)
        *   [⚠️ Reboot (for the second time)](#%EF%B8%8F-reboot-for-the-second-time)
*   [PiFinder Stellarmate – KStars Location Integration Overview](#pifinder-stellarmate--kstars-location-integration-overview)
    *   [Purpose](#purpose-1)
    *   [What the Location Writer Does](#what-the-location-writer-does)
    *   [systemd Service Integration](#systemd-service-integration)
*   [Background Information (no action required!)](#background-information-no-action-required)
    *   [What Pifinder\_Stellarmate installation script dowa in detail](#what-pifinder_stellarmate-installation-script-dowa-in-detail)
        *   [Changes to PiFinder code base - key changes](#changes-to-pifinder-code-base---key-changes)
        *   [Alter the pifinder service to use the virtual python environment](#alter-the-pifinder-service-to-use-the-virtual-python-environment)
            *   [pifinder.service](#pifinderservice)
            *   [pifinder\_splash.service](#pifinder_splashservice)

# Purpose

[PiFinder](https://www.pifinder.io/) is a perfect instrument for the visual astronomer with the ability to plate solve in near realtime. This is great for any telescope, but at most for Dobsonians, which give us the most amount of light for the price. 

[Stellarmate](https://www.stellarmate.com/) (dual license) is a software based on [KStars and EKOS](https://kstars.kde.org/de/) (open source), that enables to make professional astrophotography or EAA and control your equipment via [INDI](https://www.indilib.org/). All these technologies are based on Linux (server side) and are open to all thinkable clients, from tablets over handy up the pc. And this without any constrictions to the platform (Linux, Mac, Windows) - based on a modern IoT client/server architecture. In my opinion it is the the most advanced software stack controlling your astrophotography tasks in the field of astronomy. 

Combined with the powerful tool [Sky Safari](https://skysafariastronomy.com/) this offers vast possibilities to explore the sky and it's objects. Both visually and doing EAA. 

The [Raspberry-Pi](https://www.raspberrypi.org/) is an astonishing piece of hardware and softare eco system. Due to it's nature and versatility, it's Linux-based software and it's ARM-processor, it is ideal for the field of IoT. IoT is _the_ base of everything we do, when pairing hard-, software, our instruments and equipment. If you have a [PiFinder](https://www.pifinder.io/) already on you scope, why not use it also for EAA (e.g. live stacking). If you have an eq-platform for your big (non GoTo) Dobsonian, why not use it for serous astrophotography?

Stellarmate also runs on the Pi and also works together with Sky Safari.

I like to unite  [PiFinder](https://www.pifinder.io/),  [Stellarmate](https://www.stellarmate.com/) and the connection to [Sky Safari](https://skysafariastronomy.com/) to put both, visual and photographic experience inside one piece of hardware that sits right at the hat of my Dobsonian using my eq platform or other scopes I dual use for visual and EAA.

*   PiFinder: quickly locate objects
*   SkySafari: Observation planning, sky chart and quick "push to" (standalone or using PiFinder)
*   Stellarmate: astrophotography and/or EAA through a dedicated astro camera - or/and (if available) guide scope and mount (ST4 enabled eq platform, GoTo mount)

# Differences beetween using "PiFinder on StellarMate" and "stock PiFinder"

## GPS and WIFI/LAN

Some Services will not be used when running PiFinder in the Stellarmate OS environment. Stellarmate takes control over:

*   GPSD => the PiFinders build in GPS will NOT be used at all
*   WiFi (Client/ Host AP) and LAN -> Only Stellarmate OS/ Debian has the control over IP settings

This assures full functionality of both devices, Stellarmate and PiFinder side-by-side.

## PiFinder Menu

Therefore the following menu items you normally have in PiFinder are not available:

1.  Settings -> Choice of WiFi mode
2.  Settings -> Choice of GPS mode (GPSD only)
3.  Choice of manually setting location, time or date
4.  PiFinder Update

## PiFinder Web-Interface

You can reach the PiFinder Webinterface with a slightly different URL: http://stellarmate.local:8080/

# Installation

The setup is a three stage process and needs two reboots. Make sure to have the correct hard- and software requirements (Pi4, Debian bookworm, PiFinder hat):

1.  Enable SPI and I2C (this is also necessary for PiFinder any way), prepare the Debian bookworm for the user "pifinder" and reboot. 
2.  Checkout the PiFinder\_Stellarmate Repo and run the setup script. Then the scipts stops. 
3.  In the kept open terminal (!), source the python virtual environment  (without this, the installation is NOT possible).  Then rerun the scipt within the new virtual environment and reboot

## General Prerequisites

*   Stellarmate OS >= 1.8.1 (based on Debian Bookworm)  
    See: [https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html](https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html)  
    This "might" work with a standard Debian Bookworm and KStars Installation (but this is not tested)
*   Raspberry Pi 4 (Pi 5 to be tested)
*   PiFinder hardware (PiFinder hat)

## Let's go - 1. Pre Installation steps - preparation of Pi and Debian OS (part one)

> ### ⚠️ Important Information - try to read and undestand - afterwards proceed the steps
> 
> On a totally new sytem, where you never run Stellarmate\_PiFinder, you need to run the following tasks, instantiate a new user "pifinder" with it's own home directory and reboot. If you do not do this, you will not be able to use the PiFinder code with Stellarmate. PiFinder's code is not installed under the user "stellarmate" - you will not find it there. And this is intended. 

These steps here are not run by the installations script. Once done, you do not have to repeat them any more on the device. 

Please use the stellarmate oder standard user with sudo permission to do these tasks,.

### raspi-config (this is not done by the script!)

Enable SPI / I2C. The screen and IMU use these to communicate.

```
sudo raspi-config

Select 3 - Interface Options
Then I4 - SPI and choose Enable
Then I5 - I2C and choose Enable
```

### Add PiFinder user to Stellarmate OS

This is essential and creates a second home directory `/home/pifinder` in which the installation of the PiFinder software takes place.

```
sudo useradd -m pifinder
sudo passwd pifinder
sudo usermod -a -G sudo pifinder
su - pifinder
```

Info: the PiFinder service is running as "pifinder" user.

It also adds the user pifinder to rhe group `stellarmate`.

### Add rights for hardware access to user 'pifinder'

```
sudo usermod -a -G spi pifinder
sudo usermod -a -G gpio pifinder
sudo usermod -a -G i2c pifinder
sudo usermod -a -G video pifinder
```

### Add user pifinder to the sudoers group

Therefore we need to append this line to `/etc/sudoers.d/010_pi-nopasswd`

```
pifinder ALL=(ALL) NOPASSWD: ALL
```

You can paste this into the shell to do this job for you:

```
append_file="/etc/sudoers.d/010_pi-nopasswd"
append_line="pifinder ALL=(ALL) NOPASSWD: ALL"

# Create file if missing
if ! sudo test -f "$append_file"; then
    echo "$append_line" | sudo tee "$append_file" > /dev/null
    echo "✅ sudoers file created with entry for pifinder"
else
    # Check if line already present, otherwise append
    if ! sudo grep -qF "$append_line" "$append_file"; then
         echo "$append_line" | sudo tee -a "$append_file" > /dev/null
         echo "✅ sudoers line added for pifinder"
    else
         echo "ℹ️ sudoers line already present for pifinder"
    fi
fi
```

### ⚠️ Reboot (first time)

## Let's go - 2. Installation (part two and three)

> ### ⚠️ Important Information - try to read and undestand - afterwards proceed the steps
> 
> To use the installation script, you have to do this with the user "pifinder", NOT with user "stellarmate" !!!
> 
> 1\. Login or open a terminal. with the user `pifinder`
> 
> 2\. Clone the Stellarmate\_PiFinder repo into the user "pifinders" home dir (not in stellarmates dir or another user)
> 
> 3\. You have to run the script **twice**: therefore you MUST manually past the following text into the shell and rerrun the scipt as adviced later
> 
> source /home/pifinder/PiFinder/python/.venv/bin/activate  
> ./pifinder\_stellarmate\_setup.sh

### Part two (get the repo and run the script)

`su - pinder`, when you are logged in as user "stellarate", "pi", etc.  (or login directly with ssh as user pifinder)  
If this does not work, something went wrong. Repeat the steps from "Pre Installation steps"

```
su - pifinder
```

Clone the repo in the users dir: 

```
git clone https://github.com/apos/PiFinder_Stellarmate.git
```

Go into PiFinder\_Stellarmate directory

```
cd PiFinder_Stellarmate
```

Run the script the first time and wait for the script to stop :..

```
./pifinder_stellarmate_setup.sh
```

### Part three (source the new virtual python environment and restart the script)

⚠️ After the script stopped, do not close the terminal ⚠️ 

Paste the shown lines into the shell. This sources the newly created python virtual environment an restarts the script

```
source /home/pifinder/PiFinder/python/.venv/bin/activate
```

You should now see that the prompt changed to something like "(.venv) ...".  
Then rerun the script

```
./pifinder_stellarmate_setup.sh
```

until you see:

```
##############################################
PiFinder setup complete, please restart the Pi. This is the version to run on Stellarmate OS (Pi4, Bookworm)
```

> ### ℹ️ Read the logs - Troubleshooting
> 
> *   Bedore reboot, carefully read the prompt for any warnings or error. If so, please file an issue here with a complete description and all error-messages or I will not (b: [https://github.com/apos/PiFinder_Stellarmate/issues](https://github.com/apos/PiFinder_Stellarmate/issues)
> *   You might see some messages about non compatible patches. That's ok, because the script determines the actual system and only patches the files, that fit to your version/system
> *   Later on, if something does not work: Login with the user pifinder (!) and sheck on the commandline, if you pifinder starts correctly or if there are any errors:   
>     `sudo systemctl stop pifinder.service; sleep 2; sudo systemctl start pifinder.service ; sudo journalctl -u pifinder.service -f`

### ⚠️ Reboot (for the second time)

![16B3C596-ED0E-41CD-A90B-EC1B08FA7882_1_105_c](https://github.com/user-attachments/assets/d378cdb2-2b10-451a-ae31-7413cd21250f)

# PiFinder Stellarmate – KStars Location Integration Overview

> ### ℹ️ **Info**
> 
> *   This is only for Information. No action required.

## Purpose

Purpose is, to replace PiFinder's Native GPS with KStars-Based Geolocation

Instead of using a direct GPS module via `gpsd`, the PiFinder now fetches **location and time data from KStars.** This it done by reading the file `kstarsrc` which stores all necessary informations, we need. KStars has several ways to determin the actual localtion: you can either type it in manuelly with in the KStars GUI (VNC), let it determine via GPSD or an INDI compatible GPS device or you simly you rely onto the Stellarmate App, which will automatically set everything from you tablet or phone. Stellarmate handles GPS/time synchronization. It simply does not matter, how KStars get the information - when it got the coordinates, the **"Location Writer Service"** writes the information into the following file and PiFinder will use it for the fix. 

`(.venv) pifinder@stellarmate:~/PiFinder $ cat /tmp/kstars_location.txt`  
`GPS Location,,49.47785331872243,8.450430929668666,100.42879867553711,2025-05-01T11:35:17.661929+00:00,2025-05-01T13:35:17.661965+02:00`

Since KStars saves it's location upon reboot, these data are instantly avaiable the next time you start your Stellarmate/PiFinder. This is perfect, if your location does not vary. If not, you simply start the Stellarmate App and this will imediately sync time, date and location for you. 

## What the "Location Writer" does

```
/home/pifinder/PiFinder_Stellarmate/bin/kstars_location_writer.py
```

This Python script:

*   Parses the `~/.config/kstarsrc` file from the KStars user session.
*   Extracts the current location:
    *   **Latitude**
    *   **Longitude**
    *   **Altitude**
    *   **City & Country**
*   Captures the current time in:
    *   **UTC**
    *   **Local time with offset**
*   Writes all data into a plain-text file:  
    `/tmp/kstars_location.txt`

The file is updated every 10 seconds.

## systemd Service Integration

```
/etc/systemd/system/pifinder_kstars_location_writer.service
```

This service ensures the writer script:

*   **Starts at boot** in the graphical session.
*   **Runs as user** `**stellarmate**` (same as the KStars session).
*   **Creates** `**/tmp/kstars_location.txt**` with correct permissions:
    *   Uses `Group=pifinder` so the PiFinder service (which runs as user `pifinder`) can read it.
    *   Prepares the file with `ExecStartPre` commands (`touch`, `chmod`).

**Example:**

```
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
  WantedBy=default.targipment
```

# Background Information (no action required!)

> ### ℹ️ **Info**
> 
> *   The steps shown here are already done by the installation script. This is just for explanation purpose
> *   This is only for Information. No action required

## What Pifinder\_Stellarmate installation script dowa in detail

**1\. The following services are fully managed solely by StellarMate OS**

Services will not be used/disabled or altered through PiFinder in the Stellarmate environment by the installation script or when running PiFinder on Stellarmate.

This assures full functionality of both devices side-by-side.

*   GPSD => the PiFinders build in GPS will NOT be used at all
*   WiFi (Client/ Host AP) and LAN -> Only Stellarmate OS/ Debian has the control over IP settings

**2\. The installation of PiFinder within StellarMate OS (!) is non destructive to Stellarmate**

But: it can not update an existing PiFinder installation. You have to backup you settings in PiFinder, reinstall it and replay you settings

**5\. install additional Packages**

```
sudo apt-get update
sudo apt-get install -y git python3-pip python3-venv libcap-dev python3-libcamera
```

**6\. add parameters to raspberry pi config.txt**

The location of the config.txt on bookworm has changed to: `/boot/firmware/config.txt`

E.g. add the following lines to the file:

```
# Pifinder main.py needs this:
dtoverlay=pwm-2chan
```

**7\. Install PiFinder with the modified pifinder\_setup.sh**

This is mostly corresponding and follows the original installation guide from PiFinder: https://pifinder.readthedocs.io/en/release/software.html

### Changes to PiFinder code base - key changes

> ### ℹ️ **Info**
> 
> *    The detailed changes, that are made are in "PiFinder\_Stellarmate/bin/alter\_PiFinder\_installation\_files.sh" and it's companion "bin/funcitons.sh"

Due to the bookworm environment is was necessary to alter some files. This will not affect it's functionalities.

`solver.py`

*   sys.path.append(...) updated to use .parent
*   "import tetra3" replaced with "from tetra3 import main"
*   Adds "from tetra3 import cedar\_detect\_client" if missing

`Tetra3 and main.py`

*   a lot of changes to basically how Tetra3 is called

`ui/marking_menus.py`

*   Adds "field" to dataclass import
*   Replaces HELP menu init with a default\_factory lambda

`ui/menu_structure.py`

`pifinder_post_update.sh`

*   Adds virtual environment creation & activation after submodule init

`camera_pi.py`

*   Adds "from picamera2 import Picamera" after numpy import

**8\. Use a python venv (virtual environment)**

The most important change is, that because of security reasons, it is not allowed to use global python libraries in Python 3.11 any more. You can use them, if installed through the OS package manager, but it is much better to use a dedicated local virtual environment for your python libraries and run the service within virtual environment:

```
cd /home/pifinder/PiFinder/python
python3 -m venv /home/pifinder/PiFinder/python/.venv --system-site-packages
source /home/pifinder/PiFinder/python/.venv/bin/activate
pip install -r /home/pifinder/PiFinder/python/requirements.txt
```

**9\. PIP Additional requirements(.txt) within the venv**

This goes into `requirements.txt`:

```
e.g. pip install picamera2
```

### Alter the pifinder service to use the virtual python environment

#### pifinder.service

```
9c9
< ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.main
---
> ExecStart=/usr/bin/python -m PiFinder.main
```

#### pifinder\_splash.service

```
##### pifinder_flash.service
6c6
< ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.splash
---
> ExecStart=/usr/bin/python -m PiFinder.splash
```