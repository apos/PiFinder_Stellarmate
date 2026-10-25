#! /usr/bin/bash
set -euo pipefail

# Fixes the black UTM window after boot on stellarmate-utm (x86 StellarMate OS
# in UTM on Apple Silicon, found live 2026-10-25 on SMOS 2.4.0).
#
# Root cause: SMOS's display-setup.service runs /usr/bin/setup-display.sh
# before display-manager.service. That script looks for a connected DRM
# connector and, if it finds none, writes a Dummy-driver Xorg config
# (/usr/share/X11/xorg.conf.d/20-display-setup.conf). On this VM the
# virtio-gpu device appears a few seconds AFTER the script has run (boot log:
# script at 20:45:10 "No physical display found", kernel "virtio-gpu-pci
# detected" at 20:45:12), so X starts on the Dummy driver and the UTM window
# stays black.
#
# Fix: a systemd drop-in that makes display-setup.service wait (max 40 s)
# until a DRM connector exists before the script runs. Only added when the
# VM has a virtio-gpu; on any other system this script does nothing.
# Safe to re-run. A SMOS update replaces the root filesystem, so re-run this
# script after every SMOS update (same as utm_fix_utm_apple_silicon_host_pause_issues.sh).

DROPIN_DIR="/etc/systemd/system/display-setup.service.d"
DROPIN="${DROPIN_DIR}/wait-for-drm.conf"

echo "-> Checking for a virtio-gpu (UTM guest)..."
if ! grep -qs "^0x1af4" /sys/class/drm/card*/device/vendor 2>/dev/null \
   && ! lspci -nn 2>/dev/null | grep -qi "virtio.*VGA\|1af4:1050"; then
    echo "   No virtio-gpu found - not a UTM guest, nothing to do."
    exit 0
fi

echo "-> Writing ${DROPIN}..."
sudo mkdir -p "${DROPIN_DIR}"
sudo tee "${DROPIN}" >/dev/null <<'EOF'
[Service]
ExecStartPre=/usr/bin/bash -c 'for i in $(seq 1 80); do ls /sys/class/drm/card*-*/status >/dev/null 2>&1 && exit 0; sleep 0.5; done; exit 0'
EOF
sudo systemctl daemon-reload
echo "   Written and loaded."

echo ""
echo "Done. Takes effect at the next boot. Verify afterwards with:"
echo "  journalctl -b -u display-setup --no-pager | grep -E 'Physical display|dummy'"
echo "  (should say 'Physical display connected, no action needed')"
echo "  grep -E 'LoadModule: \"(dummy|modesetting)\"' /var/log/Xorg.0.log"
echo "  (should show modesetting, not dummy)"
