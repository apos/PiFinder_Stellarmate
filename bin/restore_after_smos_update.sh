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

# Reset pacman's keyring + sync databases before the actual sync below - the
# same remedy StellarMate's own factory-reset tooling uses
# (reset_pacman_keys() in /usr/share/smoscore/scripts/common/
# reset-factory-common.sh), not a workaround invented here (same reasoning
# already applied to the core/extra/alarm install path in
# bin/os_detect.sh's os_pacman_install_arch()). Found live (2026-09-05,
# real SMOS 2.2.1->2.3.0 update, Pi4): a SMOS update can leave the local
# keyring/sync-db state corrupted ("Public keyring not found", "database
# ... is not valid (invalid or corrupted database (PGP signature))"),
# which then makes EVERY subsequent `pacman -S` in this script fail with
# "target not found" - not just for packages actually affected by the
# update, but for anything already installed too (confirmed live: `pacman -S
# --needed jq` failed even though jq was already present). Safe to run
# unconditionally: a no-op if the keyring/sync-db state is already fine,
# and this only restores pacman's own trust database to its default state
# (never touches installed packages).
sudo rm -rf /var/lib/pacman/sync/*
sudo pacman-key --init
sudo pacman-key --populate
sudo pacman -Sy --noconfirm
echo "  ✅ Repos added, keyring reset, and synced"

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
    openexr rclone wireguard-tools jq
# GitHub CLI (`gh`) - found missing entirely after a SMOS 2.2.1->2.3.0 update
# (2026-09-05), not just off PATH: package gone, only its config/cache dirs
# survived. Not a PiFinder runtime dependency (nothing here or in the venv
# calls it) - purely a dev-tooling convenience for whoever administers this
# checkout via Claude Code/the CLI. Best-effort, NOT gated by `set -e`
# (unlike libcamera below): a failure here must never abort the rest of this
# restore, and today it reliably WOULD fail if the pacman keyring is broken
# (see the "Public keyring not found"/"database ... is not valid (PGP
# signature)" errors documented in basic-memory pifinder-stellarmate/00116) -
# that is a separate, pre-existing problem this script does not attempt to
# fix (pacman-key repair is a security-relevant action for the user, not an
# automated script step).
sudo pacman -S --noconfirm --needed github-cli \
    && echo "  ✅ gh (GitHub CLI) installed" \
    || echo "  ⚠️  gh (GitHub CLI) install failed/skipped - likely the pacman keyring issue above; install manually once resolved (not required for PiFinder itself)."
# libcamera is pre-installed by SMOS base. The smos `libcamera` package BUNDLES
# the IPA modules (/usr/lib/libcamera/ipa/ipa_rpi_{pisp,vc4}.so) — SMOS has NO
# separate `libcamera-ipa` package (that is an Arch Linux ARM split-package
# concept). Never pull extra/libcamera-ipa: it hard-requires libcamera.so=0.7-64
# / libcamera-base.so=0.7-64, which the smos libcamera package does not declare
# (Provides: None), so pacman cannot prepare the transaction and the whole
# restore aborts via `set -e`.
if ! pacman -Q libcamera &>/dev/null; then
    sudo pacman -S --noconfirm libcamera
    echo "  ✅ libcamera installed"
else
    echo "  ℹ️  libcamera $(pacman -Q libcamera | awk '{print $2}') already present (SMOS base, IPA bundled)"
fi
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

# Risk 1: check libcamera major version
LIBCAM_MAJOR=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1)
LIBCAM_VER=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
if [ -n "$LIBCAM_MAJOR" ] && [ "$LIBCAM_MAJOR" -gt 0 ] 2>/dev/null; then
    echo "⚠️  WARNING: libcamera major version $LIBCAM_VER detected!"
    echo "    python-libcamera 0.7.0 may be incompatible. Camera may not work."
    echo "    Update packages/python-libcamera-*.pkg in PiFinder_Stellarmate repo."
else
    echo "ℹ️  libcamera $LIBCAM_VER — compatible with pinned python-libcamera 0.7.0"
fi

# -------------------------------------------------------
# 3. Groups + usermod
# -------------------------------------------------------
echo "🔧 [3/8] Creating hardware groups and adding user ..."

# groupadd/usermod require /etc/group and /etc/passwd to be well-formed,
# newline-terminated files. A missing trailing newline on the last line makes
# shadow-utils misreport "Non-text file" / "cannot open ...: Cannot allocate
# memory" (not a real ENOMEM - verified via strace, no syscall actually
# fails) and silently no-op instead of creating the group/updating the user.
# Found live on a fresh SMOS 2.3.0 x86 image (2026-09-05, PR #270) - fixed
# there in pifinder_stellarmate_setup.sh, but this restore script had the
# identical gap and reproduced the identical bug live on a real SMOS
# 2.2.1->2.3.0 update (Pi4, same day). Ensuring this here is a correctness
# precondition for the calls below, not a defensive workaround.
for f in /etc/group /etc/passwd; do
    if [ -n "$(sudo tail -c 1 "$f")" ]; then
        echo "⚠️  $f is missing its trailing newline - fixing before groupadd/usermod."
        sudo bash -c "printf '\n' >> '$f'"
    fi
done

# PiFinder cannot start at all without these (pifinder.service's
# SupplementaryGroups=), so a failure here must hard-abort the script, not
# just warn and continue.
for grp in spi gpio i2c kmem input; do
    if ! getent group "$grp" > /dev/null 2>&1; then
        sudo groupadd "$grp"
        if ! getent group "$grp" > /dev/null 2>&1; then
            echo "❌ FATAL: groupadd '$grp' failed - PiFinder cannot start without it (see pifinder.service's SupplementaryGroups=)."
            exit 1
        fi
    fi
done

sudo usermod -a -G spi,gpio,i2c,video,kmem,input "${USER}"
for grp in spi gpio i2c video kmem input; do
    if ! id -nG "${USER}" | tr ' ' '\n' | grep -qx "$grp"; then
        echo "❌ FATAL: user '${USER}' is not in group '$grp' after usermod - PiFinder cannot access the required hardware."
        exit 1
    fi
done
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
        add_to_section "pi5" "dtoverlay=pwm-2chan"
        add_to_section "pi5" "dtoverlay=imx296"
        # uart3 intentionally omitted: GPIO9 conflicts with SPI0-MISO on RP1
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
