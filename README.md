# PiFinder on Stellarmate

> ### ⚠️ **Warning**
> 
> *   This is is work in progress and (at the moment) highly experimental. As of 13.04.25 the script is ready for test and basically working (GPS from Stellarmate, no uninstall). 
> *   This project is not an official PiFinder (R) project. It is on your own to understand, how the script works. I am not responsible for any damage to your hard- or software by using this code.

> ### ℹ️ **Info**
> 
> *   The main changes and installation of pifinder is made by the script `/home/pifinder/PiFinder_Stellarmate/bin/pifinder_stellarmate_setup.sh`
> *   The script can not (yet) update an existing PiFinder installation.
> *   There is no uninstallation routine. You only can delete `/home/pifinder/PiFinder` and re-run the script.
> *   The folder `/home/pifinder/PiFinder_Stellarmate` persists. All Updates of PiFinder Code and so on have to be done from there, not from PiFinders Update tools.
> *   The script downloads and installs the default PiFinder installation into `/home/pifinder/PiFinder`. It then makes the necessary patches and adds additional functionalities.
> *   PiFinders GPS and WiFi/LAN network management is NOT used, instead it uses the one from Stellarmate.

# Table of Contents

- [PiFinder on Stellarmate](#pifinder-on-stellarmate)
- [Table of Contents](#table-of-contents)
- [Purpose](#purpose)
- [Prerequisites](#prerequisites)
    - [Run raspi-config (this is not done by the script!)](#run-raspi-config-this-is-not-done-by-the-script)
  - [What PiFinder\_Stellarmate installation script does (in basic terms)](#what-pifinder_stellarmate-installation-script-does-in-basic-terms)
  - [Changes to PiFinder code base](#changes-to-pifinder-code-base)
    - [PiFinder code - key changes](#pifinder-code---key-changes)
    - [Use venv](#use-venv)
  - [PIP Additional requirements(.txt) within the venv](#pip-additional-requirementstxt-within-the-venv)
  - [Alter the PiFinder service to use the virtual python environment](#alter-the-pifinder-service-to-use-the-virtual-python-environment)
        - [pifinder.service](#pifinderservice)
        - [pifinder\_splash.service](#pifinder_splashservice)
- [PiFinder Stellarmate – KStars Location Integration Overview](#pifinder-stellarmate--kstars-location-integration-overview)
  - [🔧 Purpose: Replace PiFinder's Native GPS with KStars-Based Geolocation](#-purpose-replace-pifinders-native-gps-with-kstars-based-geolocation)
  - [🧠What the Location Writer Does](#what-the-location-writer-does)
  - [systemd Service Integration](#systemd-service-integration)
- [PiFinder Stellarmate – using PiFinder to take control over the mount (INDI)](#pifinder-stellarmate--using-pifinder-to-take-control-over-the-mount-indi)

# Purpose

[PiFinder](https://www.pifinder.io/) is a perfect instrument for the visual astronomer, with the ability to plate solve in near real time. This is great for any telescope, but at most for Dobsonians, which give us the most amount of light for the price. 

[Stellarmate](https://www.stellarmate.com/) (dual license) is a software based on [KStars and EKOS](https://kstars.kde.org/de/) (open source), that enables to make professional astrophotography or EAA and control your equipment via [INDI](https://www.indilib.org/). All these technologies are based on Linux (server side) and are open to all thinkable clients, from tablets over cell phone up the pc. And this without any constrictions to the platform (Linux, Mac, Windows) — based on a modern IoT client/server architecture. In my opinion, it is the most advanced software stack controlling your astrophotography tasks in the field of astronomy. 

Combined with the powerful tool [Sky Safari](https://skysafariastronomy.com/), this offers vast possibilities to explore the sky and it's objects. Both visually and doing EAA. 

The Raspberry-Pi is an astonishing piece of hardware. Due to its nature and versatility, it's Linux-based software and it's ARM-processor, it is ideal for the field of IoT. IoT is _the_ base of everything we do, when pairing hard-, software,  our instruments, and equipment. If you have a [PiFinder](https://www.pifinder.io/)  already on your scope, why not use it also for EAA (e.g., live stacking). If you have an EQ platform for your big (non GoTo) Dobsonian, why not use it for serous astrophotography? 

Stellarmate also runs on the Pi and also works together with Sky Safari. 

I like to unite  [PiFinder](https://www.pifinder.io/),  [Stellarmate](https://www.stellarmate.com/) and the connection to [Sky Safari](https://skysafariastronomy.com/) to put both, visual and photographic experience inside one piece of hardware that sits right at the hat of my Dobsonian using my eq platform or other scopes I dual use for visual and EAA.

*   PiFinder: quickly locate objects
*   SkySafari: Observation planning, sky chart and quick “push to” (standalone or using PiFinder)
*   Stellarmate: astrophotography and/or EAA through a dedicated astro camera - or/and (if available) guide scope and mount (ST4 enabled EQ platform, GoTo mount)

![16B3C596-ED0E-41CD-A90B-EC1B08FA7882_1_105_c](https://github.com/user-attachments/assets/d378cdb2-2b10-451a-ae31-7413cd21250f) 

# Prerequisites

*   Stellarmate OS >= 1.8.1 (based on Debian Bookworm) 
    See: https://www.stellarmate.com/products/stellarmate-os/stellarmate-os-detail.html
*   Raspberry Pi 4 (Pi 5 to be tested)
*   PiFinder hardware (PiFinder hat)

### Run raspi-config (this is not done by the script!)

Enable SPI / I2C. The screen and IMU use these to communicate.

```
sudo raspi-config

Select 3 - Interface Options
Then I4 - SPI and choose Enable
Then I5 - I2C and choose Enable
```

## What Pifinder\_Stellarmate installation script does (in basic terms)

**1. The following services are fully managed solely by StellarMate OS**

Services will not be used/disabled or altered through PiFinder in the Stellarmate environment by the installation script or when running PiFinder on Stellarmate.

This assures full functionality of both devices side-by-side. 

*   GPSD
*   Wi-Fi (Host ap)
*   Network (LAN)

The installation of PiFinder within StellarMate OS (!) is non-destructive to Stellarmate. 
*   basic idea: using PiFinder as Guide-Scope (e. g., for a mount or S44-enabled EAA)
