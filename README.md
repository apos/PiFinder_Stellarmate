# PiFinder on Stellarmate

> ### ℹ️ **Info**
>
> ** The projekt is currently in standby (expected restart in December 2025). ** But do not hesitate to cantact me eihter here or via https://discord.com/channels/1087556380724052059/1179949372847423489 


-----------

> ### ⚠️ **Warning**
>
> * This is is work in progress and (at the moment) highly experimental (you should know how to do things in Linux at the command line)
> * This is verified to work with the PiFinder-Version in "version.txt"
> * This project is not an official PiFinder (R) project. It is on your own to understand, how the script works. I am not responsible for any damage to your hard- or software by using this code.

> ### ℹ️ **Info**
>
> * The main changes and installation of PiFinder is made by the script `/home/pifinder/PiFinder_Stellarmate/bin/pifinder_stellarmate_setup.sh`
> * The script can not (yet) update an existing PiFinder installation.
> * The folder `/home/stellarmate/PiFinder_Stellarmate` persists. All Updates of PiFinder Code and so on have to be done from there, not from PiFinders Update tools.
> * The script downloads and installs the a known to work an tested  default PiFinder installation into `/home/stellarmate/PiFinder`. It then makes the necessary patches and adds additional functionalities.
> * PiFinders GPS and WiFi/LAN network management is NOT used, instead it uses the one from Stellarmate.

# Table of Contents

* [PiFinder on Stellarmate](#pifinder-on-stellarmate)
* [Table of Contents](#table-of-contents)
* [Purpose](#purpose)
* [Differences beetween using "PiFinder on StellarMate" and "stock PiFinder"](#differences-beetween-using-pifinder-on-stellarmate-and-stock-pifinder)
  * [GPS and WIFI/LAN](#gps-and-wifilan)
  * [PiFinder Menu](#pifinder-menu)
  * [PiFinder Web-Interface](#pifinder-web-interface)
* [Installation](#installation)
  * [General Prerequisites](#general-prerequisites)
  * [Let's go - 1. Pre Installation steps - preparation of Pi and Debian OS (part one)](#lets-go---1-pre-installation-steps---preparation-of-pi-and-debian-os-part-one)
    * [raspi-config (this is not done by the script!)](#raspi-config-this-is-not-done-by-the-script)
  * [Let's go - 2. Installation (part two and three)](#lets-go---2-installation-part-two-and-three)
    * [Part two (get the repo and run the script)](#part-two-get-the-repo-and-run-the-script)
    * [Part three (source the new virtual python environment and restart the script)](#part-three-source-the-new-virtual-python-environment-and-restart-the-script)
    * [⚠️ Reboot (for the second time)](#%EF%B8%8F-reboot-for-the-second-time)
  * [Uninstallation](#uninstallation)
* [PiFinder Stellarmate – KStars Location Integration Overview](#pifinder-stellarmate--kstars-location-integration-overview)
  * [Purpose](#purpose-1)
  * [What changed](#what-changed)
  * [How it works now](#how-it-works-now)
  * [Summary of advantages](#summary-of-advantages)
* [Background Information (no action required!)](#background-information-no-action-required)
  * [What Pifinder\_Stellarmate installation script does. Explained in some detail](#what-pifinder_stellarmate-installation-script-does-explained-in-some-detail)
    * [pifinder.service](#pifinderservice)
    * [pifinder\_splash.service](#pifinder_splashservice)

# Purpose

[PiFinder](https://www.pifinder.io/) is a perfect instrument for the visual astronomer with the ability to plate solve in near realtime. This is great for any telescope, but at most for Dobsonians, which give us the most amount of light for the price. 

[Stellarmate](https://www.stellarmate.com/) (dual license) is a software based on [KStars and EKOS](https://kstars.kde.org/de/) (open source), that enables to make professional astrophotography or EAA and control your equipment via [INDI](https://www.indilib.org/). All these technologies are based on Linux (server side) and are open to all thinkable clients, from tablets over handy up the pc. And this without any constrictions to the platform (Linux, Mac, Windows) - based on a modern IoT client/server architecture. In my opinion it is the the most advanced software stack controlling your astrophotography tasks in the field of astronomy. 

Combined with the powerful tool [Sky Safari](https://skysafariastronomy.com/) this offers vast possibilities to explore the sky and it's objects. Both visually and doing EAA. 

The [Raspberry-Pi](https://www.raspberrypi.org/) is an astonishing piece of hardware and softare eco system. Due to it's nature and versatility, it's Linux-based software and it's ARM-processor, it is ideal for the field of IoT. IoT is _the_ base of everything we do, when pairing hard-, software, our instruments and equipment. If you have a [PiFinder](https://www.pifinder.io/) already on you scope, why not use it also for EAA (e.g. live stacking). If you have an eq-platform for your big (non GoTo) Dobsonian, why not use it for serous astrophotography?

Stellarmate also runs on the Pi and also works together with Sky Safari.

I like to unite  [PiFinder](https://www.pifinder.io/),  [Stellarmate](https://www.stellarmate.com/) and the connection to [Sky Safari](https://skysafariastronomy.com/) to put both, visual and photographic experience inside one piece of hardware that sits right at the hat of my Dobsonian using my eq platform or other scopes I dual use for visual and EAA.

* PiFinder: quickly locate objects
* SkySafari: Observation planning, sky chart and quick "push to" (standalone or using PiFinder)
* Stellarmate: astrophotography and/or EAA through a dedicated astro camera - or/and (if available) guide scope and mount (ST4 enabled eq platform, GoTo mount)

# A word on Stellarmate setup on the Pi: hardware requirements

If you like to do serious astrophotography, and not just test:

1. a NVME driven Raspberry Pi
2. a powerful power source (at least 5 Amps) - I strongly recommend a power hat with 12 V input
3. do not rely on the Raspberry Pi's WLAN, but on LAN. You can simply use an external MiniRouter for this

Most problems, that people have, come from an underpowered Pi, the usage of a "fast" SD-Card driven Stellarmate - it is simply not enough - and network problems.

So: if you like to tinker around, just use your "Stellarmate Plus". But believe me from a very practical viewpoint over the years: it will make you live very, very troublesome. When the Pi5 comes into place, power even gets more important.


# Differences beetween using "PiFinder on StellarMate" and "stock PiFinder"

## GPS and WIFI/LAN

Some Services will not be used when running PiFinder in the Stellarmate OS environment. Stellarmate takes control over:

* GPSD => the PiFinders build in GPS will NOT be used at all
* WiFi (Client/ Host AP) and LAN -> Only Stellarmate OS/ Debian has the control over IP settings

This assures full functionality of both devices, Stellarmate and PiFinder side-by-side.

## PiFinder Menu

Therefore the following menu items you normally have in PiFinder are not available:

1. Settings -> Choice of WiFi mode
2. Settings -> Choice of GPS mode (GPSD only)
3. Choice of manually setting location, time or date
4. PiFinder Update

## PiFinder Web-Interface

You can reach the PiFinder Webinterface with a slightly different URL: http://stellarmate.local:8080/

# Installation

The setup is a three stage process and needs two reboots. Make sure to have the correct hard- and software requirements (Pi4, Debian bookworm, PiFinder hat):

1. Enable SPI and I2C (this is also necessary for PiFinder any way), prepare the Debian bookworm for the user "pifinder" and reboot.
2. Checkout the PiFinder\_Stellarmate Repo and run the setup script. Then the scipts stops.
3. In the kept open terminal (!), source the python virtual environment  (without this, the installation is NOT possible).  Then rerun the scipt within the new virtual environment and reboot

## General Prerequisites

* Stellarmate OS >= 1.8.1 (based on Debian Bookworm)
  See: [https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html](https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html)
  This "might" work with a standard Debian Bookworm and KStars Installation (but this is not tested)
* Raspberry Pi 4 (Pi 5 to be tested)
* PiFinder hardware (PiFinder hat)

## Let's go - 1. Pre Installation steps - preparation of Pi and Debian OS (part one)

> ### ⚠️ Important Information - try to read and undestand - afterwards proceed the steps
>
> On a totally new sytem, where you never run Stellarmate\_PiFinder, you need to run the following tasks

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

## Let's go - 2. Installation (part two and three)

> ### ⚠️ Important Information - try to read and undestand - afterwards proceed the steps
>
> 1\. Login or open a terminal. with the user `stellarmate` or the standard user of the operating system (e. g. "pi"). 
>
> 2\. Clone the Stellarmate\_PiFinder repo into the users home dir
>
> 3\. You have to run the script **twice**: therefore you MUST manually past the following text into the shell and rerrun the scipt as adviced later
>
> source /home/pifinder/PiFinder/python/.venv/bin/activate
> ./pifinder\_stellarmate\_setup.sh

### Part two (get the repo and run the script)

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
source /home/stellarmate/PiFinder/python/.venv/bin/activate
```

You should now see that the prompt changed to something like "(.venv) ...".
Then rerun the script

```
./pifinder_stellarmate_setup.sh
```

until you see:

```
##############################################
PiFinder setup complete. This is the version to run on Stellarmate OS (Pi4, Bookworm)
```

> ### ℹ️ Read the logs - Troubleshooting
>
> Bedore reboot, carefully read the prompt for any warnings or error. If so, please file an issue here with a complete description and all error-messages or I will not (b: [https://github.com/apos/PiFinder_Stellarmate/issues](https://github.com/apos/PiFinder_Stellarmate/issues)
>
> You might see some messages about non compatible patches. That's ok, because the script determines the actual system and only patches the files, that fit to your version/system
>
> Later on, if something does not work: Login with the user pifinder (!) and sheck on the commandline, if you pifinder starts correctly or if there are any errors: 
>
> `sudo systemctl stop pifinder.service; sleep 2; sudo systemctl start pifinder.service ; sudo journalctl -u pifinder.service -f`

### ⚠️ Reboot (for the second time)

![16B3C596-ED0E-41CD-A90B-EC1B08FA7882_1_105_c](https://github.com/user-attachments/assets/d378cdb2-2b10-451a-ae31-7413cd21250f)

## Uninstallation

If you want to fully remove the PiFinder installation, you can run the uninstall script provided in the repository:

```
~/PiFinder_Stellarmate/bin/uninstall_pifinder_stellarmate.sh
```

This will:

* Stop and disable all PiFinder-related services.
* Remove installed systemd unit files.
* Delete the directory `/home/<youruser>/PiFinder` (but not `PiFinder_data`).
* Print a hint for optionally removing the `PiFinder_Stellarmate` repository.

If you want to trigger the uninstall process from within the script itself (e.g., for a clean reinstall), you can call it like this:

```
~/PiFinder_Stellarmate/bin/uninstall_pifinder_stellarmate.sh --selfmove
```

This will copy the script to `/tmp` and execute it in the background from outside the repository folder to allow deletion.

If you want to reset your current installation (but keep all code and config files), you can use the `--reset` option:

```
~/PiFinder_Stellarmate/bin/uninstall_pifinder_stellarmate.sh --reset
```

This stops all services and deletes the Python virtual environment and temporary build/cache files – without deleting the repo.

# PiFinder Stellarmate – KStars Location Integration Overview

> ### ℹ️ **Info**
>
> * This section is for informational purposes only. No manual action required.

## Purpose

The purpose of this integration is to replace PiFinder's native GPS with location data provided by KStars via Stellarmate OS. This is especially useful when the PiFinder GPS module is not available or managed entirely by Stellarmate.

PiFinder no longer requires direct access to GPS hardware. Instead, it receives accurate time and geolocation information directly via the KStars API, using the current location set within Stellarmate. This location can originate from:

* Stellarmate App (mobile/tablet GPS)
* Manual location input in KStars GUI
* INDI-compatible GPS devices

Regardless of the source, once KStars has determined the current coordinates, PiFinder receives it via a background API request.

## What changed

Previously, PiFinder depended on a background script called `kstars_location_writer.py` that extracted data from the `~/.config/kstarsrc` file and wrote it to `/tmp/kstars_location.txt`. PiFinder then read this file periodically.

This has now changed:

* The `kstars_location_writer.py` and `/tmp/kstars_location.txt` are no longer used.
* PiFinder now queries the KStars internal web API directly at runtime.
* Altitude is supplemented by parsing `~/.config/kstarsrc` if missing in the API.

This new mechanism allows **live** location updates from Stellarmate/KStars even if the user moves to a new location or changes settings during a session.

## How it works now

The PiFinder GPS subsystem queries the following KStars internal endpoint:

```
http://localhost:8624/api/info/location
```

From this, the following information is extracted:

* Latitude
* Longitude
* Altitude (if missing, read from kstarsrc)
* Timezone (optional)

The data is then converted to a standard PiFinder GPS "fix", which overrides any previous coordinates, even if a location is already set — **as long as the source is not manually locked** or marked as "WEB".

This allows seamless use of Stellarmate as a GPS provider for PiFinder without manual sync or additional tools.

## Summary of advantages

* Automatic GPS sync from Stellarmate App or KStars settings
* No dependency on PiFinder’s internal GPS module
* Location and time available immediately on boot
* Seamless override logic inside PiFinder with source prioritization

# Background Information (no action required!)

> ### ℹ️ **Info**
>
> * The steps shown here are already done by the installation script. This is just for explanation purpose
> * This is only for Information. No action required

## What Pifinder\_Stellarmate installation script does. Explained in some detail

**1\. The following services are fully managed solely by StellarMate OS**

Services will not be used/disabled or altered through PiFinder in the Stellarmate environment by the installation script or when running PiFinder on Stellarmate.

This assures full functionality of both devices side-by-side.

* GPSD => the PiFinders build in GPS will NOT be used at all
* WiFi (Client/ Host AP) and LAN -> Only Stellarmate OS/ Debian has the control over IP settings

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

**8\. Changes to PiFinder code base - key changes**

> ### ℹ️ **Info**
>
> * The detailed changes, that are made are in "`bin/patch_PiFinder_installation_files.sh`" and it's companion "`bin/functions.sh`"
> * A copy of all patched files (compared to the actual PiFinder repo) are copied to the directory `src_pifinder`

Due to the bookworm environment is was necessary to alter some files. This will not affect it's functionalities.

`solver.py`

* sys.path.append(...) updated to use .parent
* "import tetra3" replaced with "from tetra3 import main"
* Adds "from tetra3 import cedar\_detect\_client" if missing

`Tetra3 and main.py`

* a lot of changes to basically how Tetra3 is called

`ui/marking_menus.py`

* Adds "field" to dataclass import
* Replaces HELP menu init with a default\_factory lambda

`ui/menu_structure.py`

`pifinder_post_update.sh`

* Adds virtual environment creation & activation after submodule init

`camera_pi.py`

* Adds "from picamera2 import Picamera" after numpy import

**9\. Use a python venv (virtual environment)**

The most important change is, that because of security reasons, it is not allowed to use global python libraries in Python 3.11 any more. You can use them, if installed through the OS package manager, but it is much better to use a dedicated local virtual environment for your python libraries and run the service within virtual environment:

```
cd /home/pifinder/PiFinder/python
python3 -m venv /home/pifinder/PiFinder/python/.venv --system-site-packages
source /home/pifinder/PiFinder/python/.venv/bin/activate
pip install -r /home/pifinder/PiFinder/python/requirements.txt
```

**10\. PIP Additional requirements(.txt) within the venv**

This goes into `requirements.txt`:

```
e.g. pip install picamera2
```

**11\. Alter the pifinder service to use the virtual python environment and start it with the stellarmate user**

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
