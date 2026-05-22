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

exit 0
