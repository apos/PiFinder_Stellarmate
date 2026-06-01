#!/bin/bash
# PiFinder Pre-Start Script
# Wird als ExecStartPre in pifinder.service ausgeführt (als root)
# Stellt sicher dass alle Gruppen, Permissions und Overlays vorhanden sind

# Gruppen anlegen falls nicht vorhanden
getent group spi  > /dev/null 2>&1 || groupadd spi
getent group gpio > /dev/null 2>&1 || groupadd gpio
getent group i2c  > /dev/null 2>&1 || groupadd i2c
getent group kmem  > /dev/null 2>&1 || groupadd kmem
getent group input > /dev/null 2>&1 || groupadd input

# User zu Gruppen hinzufügen
PIFINDER_USER=${1:-stellarmate}
usermod -a -G spi,gpio,i2c,video,kmem,input "${PIFINDER_USER}" 2>/dev/null || true

# udev: /dev/gpiomem für gpio-Gruppe freigeben
udevadm trigger --action=change /dev/gpiomem 2>/dev/null || true

# PWM Overlay laden falls nicht aktiv (GPIO13, ALT0 = PWM1)
if [ ! -d /sys/class/pwm/pwmchip0 ]; then
    dtoverlay pwm pin=13 func=4 2>/dev/null || true
fi

# Swap aktivieren falls nicht aktiv
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

# WirePlumber + PipeWire: Services dauerhaft maskieren + pipewire-libcamera entfernen
# WirePlumber/PipeWire greifen auf /dev/video0 (Unicam/IMX296) zu und bringen
# den Sensor in einen defekten I2C-Zustand → Kamera zeigt nur schwarz, selbst
# nach Reboot (nur Power-Cycle hilft dann). Kein Audio nötig auf diesem Astro-Computer.
# pipewire-libcamera muss entfernt werden (kommt nach BTRFS-Reset zurück).
# Symlinks in /home überleben BTRFS-Reset.
SYSTEMD_USER_DIR="/home/${PIFINDER_USER}/.config/systemd/user"
mkdir -p "${SYSTEMD_USER_DIR}"

_mask_user_unit() {
    local unit="$1"
    local target="${SYSTEMD_USER_DIR}/${unit}"
    if [ ! -L "${target}" ] || [ "$(readlink "${target}")" != "/dev/null" ]; then
        ln -sf /dev/null "${target}"
        echo "✅ ${unit} maskiert"
    else
        echo "✅ ${unit} bereits maskiert — OK"
    fi
}

_mask_user_unit "wireplumber.service"
_mask_user_unit "pipewire.service"
_mask_user_unit "pipewire-pulse.service"
_mask_user_unit "pipewire.socket"
_mask_user_unit "pipewire-pulse.socket"
chown -R "${PIFINDER_USER}:${PIFINDER_USER}" "${SYSTEMD_USER_DIR}"

# pipewire-libcamera entfernen — greift direkt auf Kamera zu, ohne WirePlumber
if pacman -Q pipewire-libcamera &>/dev/null; then
    pacman -R --noconfirm pipewire-libcamera 2>/dev/null \
        && echo "✅ pipewire-libcamera entfernt" \
        || echo "⚠️  pipewire-libcamera konnte nicht entfernt werden"
else
    echo "✅ pipewire-libcamera nicht installiert — OK"
fi

exit 0
