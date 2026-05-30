#!/bin/bash
# restore_after_smos_update.sh
#
# Restores all root-partition items lost after a SMOS BTRFS snapshot reset.
# Does NOT touch /home/stellarmate/PiFinder/ or the venv.
#
# Restores:
#   - pacman repos (core/extra/alarm)
#   - System packages (git, python-pip, openexr, ...)
#   - Hardware groups + usermod
#   - udev rule for /dev/gpiomem
#   - /boot/config.txt [pi4] or [pi5] section
#   - /swapfile (btrfs-compatible)
#   - systemd services (from PiFinder_Stellarmate/pi_config_files/)
#   - drm_preview.py patch (if picamera2 present in venv)
#
# Use Case 2: SMOS update with existing PiFinder installation in /home

set -e

source "$(dirname "$0")/functions.sh"

echo "======================================================"
echo " PiFinder — Restore after SMOS Update"
echo "======================================================"
echo ""

# -------------------------------------------------------
# 1. pacman repos
# -------------------------------------------------------
echo "🔧 [1/8] Restoring pacman repos ..."
grep -q "^\[core\]" /etc/pacman.conf || \
    printf '\n[core]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/core\n\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n\n[alarm]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/alarm\n' \
    | sudo tee -a /etc/pacman.conf > /dev/null
sudo pacman -Sy --noconfirm
echo "  ✅ Repos added and synced"

# -------------------------------------------------------
# 2. System packages
# -------------------------------------------------------
echo "🔧 [2/8] Installing system packages ..."
# libcamera 0.7.1+ (pybind11 smart_holder) is NOT compatible with picamera2 from pip.
# python-libcamera must stay at 0.7.0 (no smart_holder) — pinned via IgnorePkg.
# If python-libcamera 0.7.0 cache pkg is available, downgrade; otherwise install from pacman.
# Prefer pinned package from repo, fall back to pacman cache
PYLIBCAM_PKG=$(ls "${pifinder_stellarmate_dir}/packages/python-libcamera-0.7.0-"*"-aarch64.pkg.tar.xz" 2>/dev/null | head -1)
[ -z "$PYLIBCAM_PKG" ] && PYLIBCAM_PKG=$(ls /var/cache/pacman/pkg/python-libcamera-0.7.0-*-aarch64.pkg.tar.xz 2>/dev/null | head -1)
sudo pacman -S --noconfirm --needed \
    git python-pip python-virtualenv libcap \
    libcamera libcamera-ipa \
    openexr
if [ -n "$PYLIBCAM_PKG" ]; then
    echo "  ℹ️  Installing python-libcamera 0.7.0 from cache (smart_holder fix) ..."
    sudo pacman -U --noconfirm "$PYLIBCAM_PKG"
else
    echo "  ⚠️  python-libcamera 0.7.0 not in cache — installing current version (may break camera!)"
    sudo pacman -S --noconfirm --needed python-libcamera
fi
# Pin python-libcamera to prevent upgrade to 0.7.1+ (smart_holder incompatible with picamera2)
grep -q "IgnorePkg.*python-libcamera" /etc/pacman.conf || \
    sudo sed -i '/^\[options\]/a IgnorePkg = python-libcamera' /etc/pacman.conf
echo "  ✅ Packages installed, python-libcamera pinned"

# -------------------------------------------------------
# 3. Groups + usermod
# -------------------------------------------------------
echo "🔧 [3/8] Creating hardware groups and adding user ..."
for grp in spi gpio i2c kmem input; do
    getent group "$grp" > /dev/null 2>&1 || sudo groupadd "$grp"
done
sudo usermod -a -G spi,gpio,i2c,video,kmem,input "${USER}"
echo "  ✅ Groups ready, user ${USER} added"

# -------------------------------------------------------
# 4. udev rule
# -------------------------------------------------------
echo "🔧 [4/8] Restoring udev rule for /dev/gpiomem ..."
echo 'SUBSYSTEM=="gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"' \
    | sudo tee /etc/udev/rules.d/99-gpiomem.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change /dev/gpiomem 2>/dev/null || true
echo "  ✅ /etc/udev/rules.d/99-gpiomem.rules restored"

# -------------------------------------------------------
# 5. config.txt — Pi-specific overlays
# -------------------------------------------------------
echo "🔧 [5/8] Restoring /boot/config.txt entries ..."

CONFIG_FILE=""
[ -f "/boot/firmware/config.txt" ] && CONFIG_FILE="/boot/firmware/config.txt"
[ -f "/boot/config.txt" ]          && CONFIG_FILE="/boot/config.txt"

if [ -z "$CONFIG_FILE" ]; then
    echo "  ⚠️  config.txt not found — skipping"
else
    add_to_section() {
        local section="$1"
        local line="$2"
        if grep -Fxq "$line" "$CONFIG_FILE"; then
            echo "  ℹ️  Already present: $line"
            return
        fi
        if ! grep -Fxq "[$section]" "$CONFIG_FILE"; then
            printf '\n[%s]\n%s\n' "$section" "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
            echo "  ✅ Created [$section] and added: $line"
        else
            sudo sed -i "/^\[$section\]/a $line" "$CONFIG_FILE"
            echo "  ✅ Added to [$section]: $line"
        fi
    }

    hw_model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
    if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
        add_to_section "pi5" "dtparam=i2c_arm_baudrate=10000"
        add_to_section "pi5" "dtoverlay=pwm,pin=13,func=4"
        add_to_section "pi5" "dtoverlay=uart3"
        add_to_section "pi5" "dtoverlay=pwm-2chan"
        add_to_section "pi5" "dtoverlay=imx296"
    elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
        add_to_section "pi4" "dtparam=i2c_arm_baudrate=10000"
        add_to_section "pi4" "dtoverlay=pwm,pin=13,func=4"
        add_to_section "pi4" "dtoverlay=uart3"
        add_to_section "pi4" "dtoverlay=imx296"
    fi
    echo "  ✅ config.txt updated"
fi

# -------------------------------------------------------
# 6. Swapfile
# -------------------------------------------------------
echo "🔧 [6/8] Restoring swapfile ..."
if [ ! -f /swapfile ]; then
    sudo touch /swapfile
    sudo chattr +C /swapfile 2>/dev/null || true
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || \
        echo "/swapfile none swap defaults 0 0" | sudo tee -a /etc/fstab
    echo "  ✅ Swapfile created and activated"
else
    echo "  ℹ️  Swapfile already exists"
fi

# -------------------------------------------------------
# 7. systemd services
# -------------------------------------------------------
echo "🔧 [7/8] Deploying systemd services ..."
sudo cp "${pifinder_stellarmate_dir}/pi_config_files/pifinder.service"        /etc/systemd/system/
sudo cp "${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service" /etc/systemd/system/
sudo cp "${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service"  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pifinder pifinder_splash pifinder-setup
echo "  ✅ Services deployed and enabled"

# -------------------------------------------------------
# 8. drm_preview.py patch (picamera2 in venv)
# -------------------------------------------------------
echo "🔧 [8/8] Checking picamera2 drm_preview.py patch ..."
DRM_PY=$("${python_venv}/bin/python" -c \
    "import picamera2.previews.drm_preview as m; print(m.__file__)" 2>/dev/null || true)
if [ -n "$DRM_PY" ]; then
    if grep -q "_pykms_available" "$DRM_PY"; then
        echo "  ℹ️  drm_preview.py already patched"
    else
        patch "$DRM_PY" < "${pifinder_stellarmate_dir}/diffs/drm_preview_smos.diff"
        echo "  ✅ drm_preview.py patched"
    fi
else
    echo "  ℹ️  picamera2 not found in venv — skipping"
fi

# -------------------------------------------------------
# Done
# -------------------------------------------------------
echo ""
echo "======================================================"
echo "✅ Restore complete. Please reboot to verify:"
echo "   sudo reboot"
echo ""
echo "After reboot, check:"
echo "   systemctl status pifinder pifinder-setup"
echo "   sudo journalctl -u pifinder -n 30"
echo "======================================================"
