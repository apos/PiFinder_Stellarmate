#!/bin/bash
# PiFinder Pre-Start Script
# Runs as ExecStartPre in pifinder.service (as root)
# Ensures all groups, permissions, and overlays are present

# Create groups if they don't exist
getent group spi  > /dev/null 2>&1 || groupadd spi
getent group gpio > /dev/null 2>&1 || groupadd gpio
getent group i2c  > /dev/null 2>&1 || groupadd i2c
getent group kmem  > /dev/null 2>&1 || groupadd kmem
getent group input > /dev/null 2>&1 || groupadd input

# Add the user to the groups
PIFINDER_USER=${1:-stellarmate}
usermod -a -G spi,gpio,i2c,video,kmem,input "${PIFINDER_USER}" 2>/dev/null || true

# udev: open up /dev/gpiomem for the gpio group
udevadm trigger --action=change /dev/gpiomem 2>/dev/null || true

# Load the PWM overlay if not active (GPIO13, ALT0 = PWM1)
if [ ! -d /sys/class/pwm/pwmchip0 ]; then
    dtoverlay pwm pin=13 func=4 2>/dev/null || true
fi

# Enable swap if not active
if [ -f /swapfile ] && ! swapon --show | grep -q /swapfile; then
    swapon /swapfile 2>/dev/null || true
fi

# Python version check: warn if venv Python != system Python
VENV_PY="/home/stellarmate/PiFinder/python/.venv/bin/python"
if [ -f "$VENV_PY" ]; then
    venv_ver=$("$VENV_PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    sys_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ -n "$venv_ver" ] && [ "$venv_ver" != "$sys_ver" ]; then
        echo "ERROR: PiFinder venv Python $venv_ver != system Python $sys_ver." >&2
        echo "ERROR: Run pifinder_stellarmate_setup.sh to rebuild the venv." >&2
    fi
fi

# WirePlumber + PipeWire: mask the services permanently + remove pipewire-libcamera
# WirePlumber/PipeWire grab /dev/video0 (Unicam/IMX296) and leave the sensor in a
# broken I2C state -> camera shows only black, even after a reboot (only a power
# cycle fixes it). No audio needed on this astro computer.
# pipewire-libcamera must be removed (it comes back after a BTRFS reset).
# Symlinks under /home survive a BTRFS reset.
SYSTEMD_USER_DIR="/home/${PIFINDER_USER}/.config/systemd/user"
mkdir -p "${SYSTEMD_USER_DIR}"

_mask_user_unit() {
    local unit="$1"
    local target="${SYSTEMD_USER_DIR}/${unit}"
    if [ ! -L "${target}" ] || [ "$(readlink "${target}")" != "/dev/null" ]; then
        ln -sf /dev/null "${target}"
        echo "✅ ${unit} masked"
    else
        echo "✅ ${unit} already masked - OK"
    fi
}

_mask_user_unit "wireplumber.service"
_mask_user_unit "pipewire.service"
_mask_user_unit "pipewire-pulse.service"
_mask_user_unit "pipewire.socket"
_mask_user_unit "pipewire-pulse.socket"
chown -R "${PIFINDER_USER}:${PIFINDER_USER}" "${SYSTEMD_USER_DIR}"

# Remove pipewire-libcamera - it accesses the camera directly, bypassing WirePlumber
if pacman -Q pipewire-libcamera &>/dev/null; then
    pacman -R --noconfirm pipewire-libcamera 2>/dev/null \
        && echo "✅ pipewire-libcamera removed" \
        || echo "⚠️  Could not remove pipewire-libcamera"
else
    echo "✅ pipewire-libcamera not installed - OK"
fi

# ===== Pi5: rpi-lgpio (GPIO compatibility for the Pi5 RP1 GPIO) =====
# RPi.GPIO doesn't know the Pi5 SoC (RP1) -> rpi-lgpio as a drop-in replacement.
# liblgpio.so lives under /usr/local/lib/ -> lost on a BTRFS reset.
# Rebuild: only needs gcc (no swig, no internet) - the source stays under /home.
# Wheels live under packages/ -> no internet needed for pip install.
PIFINDER_VENV="/home/${PIFINDER_USER}/PiFinder/python/.venv"
PIFINDER_SM_DIR="/home/${PIFINDER_USER}/PiFinder_Stellarmate"
HW_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
if echo "$HW_MODEL" | grep -q "Raspberry Pi 5"; then
    LGPIO_SRC="/home/${PIFINDER_USER}/lgpio-src"
    LGPIO_LIB="/usr/local/lib/liblgpio.so"

    # Ensure /usr/local/lib is in ldconfig's search path (lost on a BTRFS reset)
    if [ ! -f /etc/ld.so.conf.d/local.conf ] || ! grep -q '/usr/local/lib' /etc/ld.so.conf.d/local.conf; then
        echo "/usr/local/lib" > /etc/ld.so.conf.d/local.conf
        ldconfig
        echo ">> [Pi5] /usr/local/lib: added to ldconfig path."
    fi

    # Rebuild liblgpio.so if missing (after a BTRFS reset)
    # Only needs gcc - no swig, no make install, no internet
    if [ ! -f "$LGPIO_LIB" ]; then
        echo ">> [Pi5] liblgpio.so missing - rebuilding..."
        if [ ! -d "$LGPIO_SRC" ]; then
            echo "!! [Pi5] lgpio source missing: $LGPIO_SRC"
            echo "   Please rerun the setup script: bash pifinder_stellarmate_setup.sh"
        else
            (
                cd "$LGPIO_SRC"
                gcc -O3 -Wall -pthread -fpic \
                    -c lgCtx.c lgDbg.c lgErr.c lgGpio.c lgHdl.c lgI2C.c lgNotify.c \
                       lgPthAlerts.c lgPthTx.c lgSerial.c lgSPI.c lgThread.c lgUtil.c \
                    2>/dev/null
                gcc -shared -pthread -Wl,-soname,liblgpio.so.1 \
                    lgCtx.o lgDbg.o lgErr.o lgGpio.o lgHdl.o lgI2C.o lgNotify.o \
                    lgPthAlerts.o lgPthTx.o lgSerial.o lgSPI.o lgThread.o lgUtil.o \
                    -o liblgpio.so.1 2>/dev/null
            ) && install -m 0755 "${LGPIO_SRC}/liblgpio.so.1" /usr/local/lib/ \
              && ln -sf /usr/local/lib/liblgpio.so.1 /usr/local/lib/liblgpio.so \
              && ldconfig \
              && echo ">> [Pi5] liblgpio.so: rebuilt." \
              || echo "!! [Pi5] liblgpio.so: build failed."
        fi
    else
        echo ">> [Pi5] liblgpio.so: OK"
    fi

    # Install rpi-lgpio into the venv if it isn't importable
    # Installed from local packages/ - no internet needed
    if [ -f "${PIFINDER_VENV}/bin/python" ]; then
        if ! "${PIFINDER_VENV}/bin/python" -c "import RPi.GPIO" &>/dev/null; then
            echo ">> [Pi5] rpi-lgpio missing - installing from packages/..."
            if "${PIFINDER_VENV}/bin/pip" install --quiet \
                --no-index --find-links="${PIFINDER_SM_DIR}/packages/" \
                rpi-lgpio lgpio; then
                echo ">> [Pi5] rpi-lgpio: installed."
            else
                echo "!! [Pi5] rpi-lgpio: installation failed."
            fi
        else
            echo ">> [Pi5] rpi-lgpio (RPi.GPIO): OK"
        fi
    fi
fi

exit 0
