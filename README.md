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
*   [Prerequisites](#prerequisites)
    *   [Run raspi-config (this is not done by the script!)](#run-raspi-config-this-is-not-done-by-the-script)
    *   [What Pifinder\_Stellarmate installation script does (in basic terms)](#what-pifinder_stellarmate-installation-script-does-in-basic-terms)
    *   [Changes to PiFinder code base](#changes-to-pifinder-code-base)
        *   [PiFinder code - key changes](#pifinder-code---key-changes)
        *   [Use venv](#use-venv)
    *   [PIP Additional requirements(.txt) within the venv](#pip-additional-requirementstxt-within-the-venv)
    *   [Alter the pifinder service to use the virtual python environment](#alter-the-pifinder-service-to-use-the-virtual-python-environment)  
        \- [pifinder.service](#pifinderservice)  
        \- [pifinder\_splash.service](#pifinder_splashservice)
*   [PiFinder Stellarmate – KStars Location Integration Overview](#pifinder-stellarmate--kstars-location-integration-overview)
    *   [🔧 Purpose: Replace PiFinder's Native GPS with KStars-Based Geolocation](#-purpose-replace-pifinders-native-gps-with-kstars-based-geolocation)
    *   [🧠What the Location Writer Does](#what-the-location-writer-does)
    *   [systemd Service Integration](#systemd-service-integration)
*   [PiFinder Stellarmate – using PiFinder to take control over the mount (INDI)](#pifinder-stellarmate--using-pifinder-to-take-control-over-the-mount-indi)

# Purpose

[PiFinder](https://www.pifinder.io/) is a perfect instrument for the visual astronomer with the ability to plate solve in near realtime. This is great for any telescope, but at most for Dobsonians, which give us the most amount of light for the price. 

[Stellarmate](https://www.stellarmate.com/) (dual license) is a software based on [KStars and EKOS](https://kstars.kde.org/de/) (open source), that enables to make professional astrophotography or EAA and control your equipment via [INDI](https://www.indilib.org/). All these technologies are based on Linux (server side) and are open to all thinkable clients, from tablets over handy up the pc. And this without any constrictions to the platform (Linux, Mac, Windows) - based on a modern IoT client/server architecture. In my opinion it is the the most advanced software stack controlling your astrophotography tasks in the field of astronomy. 

Combined with the powerful tool [Sky Safari](https://skysafariastronomy.com/) this offers vast possibilities to explore the sky and it's objects. Both visually and doing EAA. 

The Raspberry-Pi is a astonishing piece of hardware. Due to it's nature and versatility, it's Linux-based software and it's ARM-processor, it is ideal for the field of IoT. IoT is _the_ base of everything we do, when pairing hard-, software, our instruments and equipment. If you have a [PiFinder](https://www.pifinder.io/)  already on you scope, why not use it also for EAA (e.g. live stacking). If you have an eq-platform for your big (non GoTo) Dobsonian, why not use it for serous astrophotography?

Stellarmate also runs on the Pi and also works together with Sky Safari.

I like to unite  [PiFinder](https://www.pifinder.io/),  [Stellarmate](https://www.stellarmate.com/) and the connection to [Sky Safari](https://skysafariastronomy.com/) to put both, visual and photographic experience inside one piece of hardware that sits right at the hat of my Dobsonian using my eq platform or other scopes I dual use for visual and EAA.

*   PiFinder: quickly locate objects
*   SkySafari: Observation planning, sky chart and quick "push to" (standalone or using PiFinder)
*   Stellarmate: astrophotography and/or EAA through a dedicated astro camera - or/and (if available) guide scope and mount (ST4 enabled eq platform, GoTo mount)

# Differences beetween using PiFinder on StellarMate an Stock PiFinder

## GPS and WIFI/LAN only from Stellarmate or the OS (Debian Bookworm)

Some Services will not be used or altered through PiFinder in the Stellarmate environment by the installation script or when running PiFinder on Stellarmate. This assures full functionality of both devices side-by-side.

*   GPSD => the PiFinders build in GPS will NOT be used at all
*   WiFi (Client/ Host AP) and LAN -> Only Stellarmate OS/ Debian has the control over IP settings

## PiFinder Menu items removed

Therefore the following menu items you normally have in PiFinder are not available:

1.  Settings -> Choice of WiFi mode
2.  Settings -> Choice of GPS mode (GPSD on
3.  Choice of manually setting location, time or date
4.  PiFinder Update

## PiFinder Web-Interface

You can reach the PiFinder Webinterface with

\-http://stellarmate.local:8080/

# Prerequisites

*   Stellarmate OS >= 1.8.1 (based on Debian Bookworm)  
    See: [https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html](https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html)  
    This "might" work with a standard Debian Bookworm and KStars Installation (but this is not tested)
*   Raspberry Pi 4 (Pi 5 to be tested)
*   PiFinder hardware (PiFinder hat)

# Pre Installation steps on the Raspberry Pi

These steps here are not run by the installations script. Once done, you do not have to repeat them any more on the device. 

### raspi-config (this is not done by the script!)

Enable SPI / I2C. The screen and IMU use these to communicate.

```
sudo raspi-config

Select 3 - Interface Options
Then I4 - SPI and choose Enable
Then I5 - I2C and choose Enable
```

# Installation procedure

> ### ⚠️ **Warning**
> 
> You have to run the script twice: therefore you MUST manually past the following text into the shell and rerrun the scipt as adviced late
> 
> source /home/pifinder/PiFinder/python/.venv/bin/activate  
> ./pifinder\_stellarmate\_setup.sh

1.  Go into /tmp or another directory
2.  Clone the repo
3.  git clone https://github.com/apos/PiFinder_Stellarmate.git
4.  Go into PiFinder\_Stellarmate directory
5.  Run the script the first time until it stops and says:

Paste the shown lines into the shell, this sources the newly created python virtual environment an restarts the script

```
source /home/pifinder/PiFinder/python/.venv/bin/activate
./pifinder_stellarmate_setup.sh
```

until you see:

```
##############################################
PiFinder setup complete, please restart the Pi. This is the version to run on Stellarmate OS (Pi4, Bookworm)
```

> ### ℹ️ Troubleshooting
> 
> *   Now carefully read the prompt for any warnings or error. If so, please file an issue here with a complete description and all error-messages or I will not (b: [https://github.com/apos/PiFinder_Stellarmate/issues](https://github.com/apos/PiFinder_Stellarmate/issues)
> *   Check on the commandline, if you pifinder starts correctly or if there are any errors: `sudo systemctl stop pifinder.service; sleep 2; sudo systemctl start pifinder.service ; sudo journalctl -u pifinder.service -f`

6\. Restart

![16B3C596-ED0E-41CD-A90B-EC1B08FA7882_1_105_c](https://github.com/user-attachments/assets/d378cdb2-2b10-451a-ae31-7413cd21250f)

# PiFinder Stellarmate – KStars Location Integration Overview

> ### ℹ️ **Info**
> 
> *   This is only for Information. No action required.

## Purpose

Purpose is, to replace PiFinder's Native GPS with KStars-Based Geolocation

Instead of using a direct GPS module via `gpsd`, the PiFinder now fetches **location and time data from KStars**, indeed form the file `kstarsrc` . KStars has several ways to determin the actual localtion: you can either type it in manuelly with in the KStars GUI (VNC), let it determine via GPSD or an INID GPS device or you simly you rely onto the Stellarmate App, which will automatically set everything from you tablet or phone. Stellarmate handles GPS/time synchronization. It simply does not matter, how KStars get the information - when it got the coordinates, the **"Location Writer Service"** writes the information into the following file and PiFinder will use it for the fix. 

`(.venv) pifinder@stellarmate:~/PiFinder $ cat /tmp/kstars_location.txt`  
`GPS Location,,49.47785331872243,8.450430929668666,100.42879867553711,2025-05-01T11:35:17.661929+00:00,2025-05-01T13:35:17.661965+02:00`

Since KStars saves it's location upon reboo, it is instantly avaiable the next time you start your Stellarmate/PiFinder.

## What the Location Writer Does

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

**2\. add PiFinder user to Stellarmate OS:**

This is essential and creates a second home directory `/home/pifinder` in which the installation of the PiFinder software takes place.

```
sudo useradd -m pifinder
sudo passwd pifinder
sudo usermod -aG sudo pifinder
su - pifinder
```

Info: the PiFinder service is running as "pifinder" user.

It also adds the user pifinder to rhe group `stellarmate`.

**3\. Add rights for hardware access to user 'pifinder'**

```
sudo usermod -aG spi pifinder
sudo usermod -aG gpio pifinder
sudo usermod -aG i2c pifinder
sudo usermod -aG video pifinder
```

**4\. add user pifinder to the sudoers group**

```
pifinder ALL=(ALL) NOPASSWD: ALL
```

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