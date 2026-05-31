#!/bin/bash
# simulate_fresh_install.sh
#
# Simulates the state after a SMOS BTRFS snapshot reset.
# Backs up all affected files to /home/stellarmate/pifinder_sim_backup/<timestamp>/
#
# Usage:
#   bash simulate_fresh_install.sh [--mode=update]   # Use Case 2: SMOS update, /home intact (default)
#   bash simulate_fresh_install.sh --mode=fresh      # Use Case 1: brand new SMOS, no PiFinder at all
#
# After running this script, execute the appropriate restore/setup script:
#   Use Case 2: bash bin/restore_after_smos_update.sh
#   Use Case 1: bash pifinder_stellarmate_setup.sh

set -e

# Parse --mode argument
MODE="update"
for arg in "$@"; do
    case "$arg" in
        --mode=fresh)  MODE="fresh"  ;;
        --mode=update) MODE="update" ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/stellarmate/pifinder_sim_backup/${TIMESTAMP}"

echo "======================================================"
echo " PiFinder SMOS Fresh-Install Simulation  [mode: ${MODE}]"
echo " Backup: ${BACKUP_DIR}"
echo "======================================================"
echo ""
if [ "$MODE" = "fresh" ]; then
    echo "⚠️  Mode FRESH: removes services, udev rules, config.txt [pi4] section,"
    echo "    swapfile, pacman repos AND /home/stellarmate/PiFinder/ + venv."
    echo "    Simulates brand-new SMOS without any PiFinder installation."
else
    echo "⚠️  Mode UPDATE: removes services, udev rules, config.txt [pi4] section,"
    echo "    swapfile and pacman repos — simulating a BTRFS snapshot reset."
    echo "    /home/PiFinder and venv remain untouched."
fi
echo ""
read -p "Proceed? (yes/no): " confirm
confirm="${confirm//[$'\r\n']}"  # strip CR/LF (VSCode SSH terminal sends CRLF)
[[ "$confirm" != "yes" ]] && echo "Aborted." && exit 0

# -------------------------------------------------------
# BACKUP
# -------------------------------------------------------
echo ""
echo "📦 Creating backup in ${BACKUP_DIR} ..."
mkdir -p "${BACKUP_DIR}/etc/systemd/system"
mkdir -p "${BACKUP_DIR}/etc/udev/rules.d"
mkdir -p "${BACKUP_DIR}/etc"
mkdir -p "${BACKUP_DIR}/boot"

# systemd services
for f in pifinder.service pifinder_splash.service pifinder-setup.service; do
    [ -f "/etc/systemd/system/${f}" ] && \
        rsync -a "/etc/systemd/system/${f}" "${BACKUP_DIR}/etc/systemd/system/" && \
        echo "  ✅ /etc/systemd/system/${f}"
done

# udev rules
[ -f "/etc/udev/rules.d/99-gpiomem.rules" ] && \
    rsync -a "/etc/udev/rules.d/99-gpiomem.rules" "${BACKUP_DIR}/etc/udev/rules.d/" && \
    echo "  ✅ /etc/udev/rules.d/99-gpiomem.rules"

# pacman.conf
[ -f "/etc/pacman.conf" ] && \
    rsync -a "/etc/pacman.conf" "${BACKUP_DIR}/etc/pacman.conf" && \
    echo "  ✅ /etc/pacman.conf"

# fstab
[ -f "/etc/fstab" ] && \
    rsync -a "/etc/fstab" "${BACKUP_DIR}/etc/fstab" && \
    echo "  ✅ /etc/fstab"

# config.txt
CONFIG_FILE=""
[ -f "/boot/firmware/config.txt" ] && CONFIG_FILE="/boot/firmware/config.txt"
[ -f "/boot/config.txt" ]          && CONFIG_FILE="/boot/config.txt"
[ -n "$CONFIG_FILE" ] && \
    rsync -a "$CONFIG_FILE" "${BACKUP_DIR}/boot/config.txt" && \
    echo "  ✅ ${CONFIG_FILE}"

# swapfile info (not the file itself — too large)
swapon --show > "${BACKUP_DIR}/swapon_show.txt" 2>/dev/null || true
echo "  ✅ swapon --show → ${BACKUP_DIR}/swapon_show.txt"

echo ""
echo "✅ Backup complete: ${BACKUP_DIR}"
echo ""

# -------------------------------------------------------
# SIMULATION: Remove what BTRFS reset would wipe
# -------------------------------------------------------
echo "🗑️  Stopping PiFinder services ..."
sudo systemctl stop pifinder 2>/dev/null || true
sudo systemctl stop pifinder-setup 2>/dev/null || true
sudo systemctl stop pifinder_splash 2>/dev/null || true

echo "🗑️  Disabling and removing systemd service files ..."
sudo systemctl disable pifinder pifinder-setup pifinder_splash 2>/dev/null || true
sudo rm -f /etc/systemd/system/pifinder.service
sudo rm -f /etc/systemd/system/pifinder_splash.service
sudo rm -f /etc/systemd/system/pifinder-setup.service
sudo systemctl daemon-reload
echo "  ✅ Services removed"

echo "🗑️  Removing udev rule ..."
sudo rm -f /etc/udev/rules.d/99-gpiomem.rules
sudo udevadm control --reload-rules 2>/dev/null || true
echo "  ✅ /etc/udev/rules.d/99-gpiomem.rules removed"

echo "🗑️  Removing [pi4] section from ${CONFIG_FILE} ..."
if [ -n "$CONFIG_FILE" ]; then
    # Remove from [pi4] up to (but not including) the next [section] or EOF
    sudo python3 - "$CONFIG_FILE" <<'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    content = f.read()
# Remove [pi4] block: from [pi4] to next [...] section or end of file
cleaned = re.sub(r'\n?\[pi4\].*?(?=\n\[|\Z)', '', content, flags=re.DOTALL)
with open(path, 'w') as f:
    f.write(cleaned)
print(f"  ✅ [pi4] section removed from {path}")
PYEOF
fi

echo "🗑️  Removing swapfile ..."
if [ -f /swapfile ]; then
    sudo swapoff /swapfile 2>/dev/null || true
    sudo rm -f /swapfile
    # Remove fstab entry
    sudo sed -i '/\/swapfile/d' /etc/fstab
    echo "  ✅ /swapfile removed and fstab cleaned"
else
    echo "  ℹ️  No swapfile found"
fi

echo "🗑️  Resetting pacman.conf to smos-only ..."
sudo python3 - <<'PYEOF'
import re
path = '/etc/pacman.conf'
with open(path) as f:
    content = f.read()
# Remove [core], [extra], [alarm] blocks we added
for repo in ['core', 'extra', 'alarm']:
    content = re.sub(
        r'\n\[' + repo + r'\]\n(?:.*\n)*?(?=\n\[|\Z)',
        '',
        content
    )
with open(path, 'w') as f:
    f.write(content)
print("  ✅ pacman.conf reset to smos-only")
PYEOF

# -------------------------------------------------------
# FRESH MODE: additionally remove /home/PiFinder and venv
# -------------------------------------------------------
if [ "$MODE" = "fresh" ]; then
    echo "🗑️  [fresh] Stopping and removing PiFinder venv ..."
    rm -rf /home/stellarmate/PiFinder/python/.venv
    echo "  ✅ venv removed"

    echo "🗑️  [fresh] Removing /home/stellarmate/PiFinder/ ..."
    rm -rf /home/stellarmate/PiFinder
    echo "  ✅ /home/stellarmate/PiFinder/ removed"
fi

echo ""
echo "======================================================"
echo "✅ Simulation complete [mode: ${MODE}]."
echo ""
if [ "$MODE" = "fresh" ]; then
    echo "Next step — full setup:"
    echo "  cd /home/stellarmate/PiFinder_Stellarmate"
    echo "  bash pifinder_stellarmate_setup.sh"
else
    echo "Next step — restore root-only items (services, config.txt, swapfile):"
    echo "  cd /home/stellarmate/PiFinder_Stellarmate"
    echo "  bash bin/restore_after_smos_update.sh"
fi
echo ""
echo "To restore from backup:"
echo "  sudo rsync -a ${BACKUP_DIR}/etc/ /etc/"
echo "  sudo rsync -a ${BACKUP_DIR}/boot/config.txt ${CONFIG_FILE}"
echo "  sudo systemctl daemon-reload"
echo "======================================================"
