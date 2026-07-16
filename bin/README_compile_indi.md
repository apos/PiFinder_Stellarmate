# How to Build/Install the PiFinder INDI Driver

`indi_pifinder_lx200` is a small, standalone INDI telescope driver. It:
- Reports the current Right Ascension (RA) and Declination (Dec) from PiFinder.
- Accepts GoTo commands from INDI clients (KStars/EKOS, SkySafari) and forwards them to PiFinder
  as a push-to target, reusing PiFinder's existing SkySafari `:Sr#`/`:Sd#` mechanism.

It does **not** control any motors, tracking, or other mount functions - PiFinder has none.

The driver links directly against the system's `libindi` package (`libindilx200`,
`libindidriver` - already installed on any StellarMate system). It does **not** need an INDI
source checkout or a full INDI build.

`pifinder_stellarmate_setup.sh` already builds and installs this (and the Mount Bridge) for you.
Use the commands below only to rebuild manually, e.g. after pulling a driver-only code change.

## Build & install

```bash
cd ~/PiFinder_Stellarmate
bash bin/build_indi_driver.sh              # incremental build
bash bin/build_indi_driver.sh --clean-build # force a full rebuild
```

If the driver is already running (e.g. started via the StellarMate Webmanager), stop it first -
otherwise installing the new binary fails with "Text file busy".

## Prerequisites

CMake, a C++ compiler, and the `libindi` development package (headers + `.so` files). On
StellarMate OS these are already present. On a bare system:

```bash
sudo pacman -S cmake gcc libindi pkgconf   # Arch/StellarMate OS
# or
sudo apt-get install cmake build-essential libindi-dev pkg-config  # Debian/Ubuntu
```

## Getting it visible in KStars/EKOS/SkySafari

The driver being installed and in `/usr/share/indi/drivers.xml` is not the whole story - both the
StellarMate Webmanager and KStars (if it's the Flatpak build) have their own, separate driver
catalogs. See `pifinder-stellarmate/00011_indi-driver-integration-howto` in basic-memory for the
full connection recipe (Webmanager restart, KStars Remote-mode profile, SkySafari's
`indi_skysafari` bridge and its `ACTIVE_DEVICES` setting).

## Testing without a real PiFinder or sky

`test_tools/fake_pifinder_lx200.py` stands in for PiFinder's own LX200 server: runs a looping
demo tour (Vega → Sheliak → Sulafat → M57 Ring Nebula) on port 4031, speaking the same LX200
subset PiFinder's real `pos_server.py` does. Point the driver's Connection tab at
`127.0.0.1:4031` to test against it instead of a real PiFinder on port 4030.
