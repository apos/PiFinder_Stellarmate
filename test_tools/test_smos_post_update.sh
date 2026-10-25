#!/usr/bin/env bash
# Loop-device test of bin/smos-post-update.sh --pre-reboot and the rescue (SD-boot) path
# (issue #561). Builds a throw-away "dual-boot disk" (boot partition label SM_BOOT_NVM, btrfs
# root label SM_ROOT_NVM with a running @system-2.3.0 and a staged @system-2.4.0 whose boot config
# was rewritten to LABEL=SM_ROOT, like the SMOS 2.4.0 update did) and runs the script against it.
# Nothing outside the temp directory and the two loop devices is touched. Needs sudo, losetup,
# mkfs.btrfs, mkfs.ext4 (the boot partition is ext4 here only because mkfs.vfat may be missing).
#
#   bash test_tools/test_smos_post_update.sh
set -u

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$HERE/bin/smos-post-update.sh"
T="$(mktemp -d)"
PASS=0; FAIL=0
LB=""; LR=""

cleanup() {
    sudo umount "$T/boot" "$T/top" 2>/dev/null
    [ -n "$LB" ] && sudo losetup -d "$LB" 2>/dev/null
    [ -n "$LR" ] && sudo losetup -d "$LR" 2>/dev/null
    sudo rm -rf "$T"
}
trap cleanup EXIT

ok()   { PASS=$((PASS + 1)); echo "  PASS: $*"; }
bad()  { FAIL=$((FAIL + 1)); echo "  FAIL: $*"; }
check() { # description, command...
    local d="$1"; shift
    if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi
}

build_disk() {
    truncate -s 64M "$T/boot.img"; truncate -s 300M "$T/root.img"
    LB="$(sudo losetup -f --show "$T/boot.img")"; LR="$(sudo losetup -f --show "$T/root.img")"
    sudo mkfs.ext4 -q -L SM_BOOT_NVM "$LB"
    sudo mkfs.btrfs -q -f -L SM_ROOT_NVM "$LR"
    mkdir -p "$T/top" "$T/boot" "$T/backup"
    sudo mount "$LR" "$T/top"
    for v in 2.3.0 2.4.0; do
        sudo btrfs subvolume create "$T/top/@system-$v" >/dev/null
        sudo mkdir -p "$T/top/@system-$v/etc/stellarmate/boot" "$T/top/@system-$v/etc/systemd/system/multi-user.target.wants"
    done
    ROOT_UUID="$(sudo blkid -s UUID -o value "$LR")"; BOOT_UUID="$(sudo blkid -s UUID -o value "$LB")"
    # running system: UUIDs (as 2.2.1/2.3.0 had); staged system: the labels the 2.4.0 update wrote
    printf 'UUID=%s /boot vfat defaults 0 2\nUUID=%s / btrfs subvol=@system-2.3.0,defaults 0 0\nUUID=%s /home btrfs subvol=@home,defaults 0 0\n' "$BOOT_UUID" "$ROOT_UUID" "$ROOT_UUID" | sudo tee "$T/top/@system-2.3.0/etc/fstab" >/dev/null
    reset_staged
    sudo mount "$LB" "$T/boot"
    reset_boot
    printf '[Unit]\nDescription=wg test\n[Service]\nType=oneshot\nExecStart=/bin/true\n[Install]\nWantedBy=multi-user.target\n' > "$T/backup/wg-nethserver-client.service"
}

reset_staged() {
    printf 'LABEL=SM_BOOT  /boot  vfat   defaults  0  2\nLABEL=SM_ROOT  /      btrfs  subvol=@system-2.4.0,defaults 0 0\nLABEL=SM_ROOT  /home  btrfs  subvol=@home,defaults 0 0\ntmpfs  /tmp  tmpfs  rw 0 0\n' | sudo tee "$T/top/@system-2.4.0/etc/fstab" >/dev/null
    echo 'console=tty1 root=LABEL=SM_ROOT rootfstype=btrfs rootflags=subvol=@system-2.0.0 rootwait' | sudo tee "$T/top/@system-2.4.0/etc/stellarmate/boot/cmdline.txt" >/dev/null
    sudo rm -f "$T/top/@system-2.4.0/etc/systemd/system/wg-nethserver-client.service" "$T/top/@system-2.4.0/etc/systemd/system/multi-user.target.wants/wg-nethserver-client.service"
    sudo rm -f "$T"/top/@system-2.4.0/etc/*.bak-pu-* "$T"/top/@system-2.4.0/etc/stellarmate/boot/*.bak-pu-*
}
reset_boot() {
    echo 'console=tty1 root=LABEL=SM_ROOT rootfstype=btrfs rootflags=subvol=@system-2.4.0 rootwait quiet' | sudo tee "$T/boot/cmdline.txt" >/dev/null
    sudo rm -f "$T"/boot/*.bak-pu-*
}

run_pu() { # extra env assignments are passed as args before --
    sudo env SMOS_PU_EXT_ROOT_DEV="$LR" SMOS_PU_EXT_BOOT_DEV="$LB" SMOS_PU_BOOT_DIR="$T/boot" \
        SMOS_PU_BACKUP_DIR="$T/backup" "$@"
}

grep_t() { sudo grep -q "$1" "$2"; }

build_disk
echo "disk: root $LR ($ROOT_UUID)  boot $LB ($BOOT_UUID)"

echo "== 1. --pre-reboot: staged @system-2.4.0 gets fixed, running @system-2.3.0 untouched"
OUT="$(run_pu SMOS_PU_RUNNING_ROOT="$LR" SMOS_PU_RUNNING_SUBVOL=@system-2.3.0 bash "$SCRIPT" --pre-reboot 2>&1)"; RC=$?
echo "$OUT" | sed 's/^/    /' | head -14
[ "$RC" -eq 0 ] && ok "exit 0" || bad "exit $RC"
check "boot cmdline -> root=UUID"            grep_t "root=UUID=$ROOT_UUID" "$T/boot/cmdline.txt"
check "boot cmdline: rest of the line kept"  grep_t "rootflags=subvol=@system-2.4.0 rootwait quiet" "$T/boot/cmdline.txt"
check "staged fstab /boot -> UUID"           grep_t "^UUID=$BOOT_UUID  /boot" "$T/top/@system-2.4.0/etc/fstab"
check "staged fstab / and /home -> UUID"     test "$(sudo grep -c "^UUID=$ROOT_UUID" "$T/top/@system-2.4.0/etc/fstab")" -eq 2
check "staged fstab: tmpfs line kept"        grep_t "^tmpfs" "$T/top/@system-2.4.0/etc/fstab"
check "template cmdline -> root=UUID"        grep_t "root=UUID=$ROOT_UUID" "$T/top/@system-2.4.0/etc/stellarmate/boot/cmdline.txt"
check "backup next to boot cmdline"          test -n "$(ls "$T"/boot/cmdline.txt.bak-pu-* 2>/dev/null)"
check "backup next to staged fstab"          test -n "$(ls "$T"/top/@system-2.4.0/etc/fstab.bak-pu-* 2>/dev/null)"
check "running @system-2.3.0 fstab untouched" grep_t "^UUID=$ROOT_UUID / btrfs subvol=@system-2.3.0" "$T/top/@system-2.3.0/etc/fstab"
check "WireGuard unit copied into staged system" test -f "$T/top/@system-2.4.0/etc/systemd/system/wg-nethserver-client.service"
check "WireGuard unit enabled offline in staged system" test -L "$T/top/@system-2.4.0/etc/systemd/system/multi-user.target.wants/wg-nethserver-client.service"
check "nothing written to the running system's WireGuard dir" test ! -e "$T/top/@system-2.3.0/etc/systemd/system/wg-nethserver-client.service"
check "no temporary mount left behind" test -z "$(findmnt -rn -o TARGET | grep '/run/smos-pu-root-')"

echo "== 2. rerun is idempotent"
OUT="$(run_pu SMOS_PU_RUNNING_ROOT="$LR" SMOS_PU_RUNNING_SUBVOL=@system-2.3.0 bash "$SCRIPT" --pre-reboot 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "exit 0" || bad "exit $RC"
echo "$OUT" | grep -q "changed" && bad "second run changed something" || ok "second run changed nothing"

echo "== 3. nothing staged (running == newest): no change"
reset_staged; reset_boot
OUT="$(run_pu SMOS_PU_RUNNING_ROOT="$LR" SMOS_PU_RUNNING_SUBVOL=@system-2.4.0 bash "$SCRIPT" --pre-reboot 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "exit 0" || bad "exit $RC"
echo "$OUT" | grep -q "nothing to do" && ok "reports nothing to do" || bad "no 'nothing to do' message"
check "boot cmdline unchanged" grep_t "root=LABEL=SM_ROOT " "$T/boot/cmdline.txt"

echo "== 4. root label is not a dual-boot label: no change"
sudo umount "$T/top"; sudo btrfs filesystem label "$LR" SM_ROOT >/dev/null 2>&1; sudo mount "$LR" "$T/top"
echo "    root label now: $(sudo blkid -p -s LABEL -o value "$LR")"
OUT="$(run_pu SMOS_PU_RUNNING_ROOT="$LR" SMOS_PU_RUNNING_SUBVOL=@system-2.3.0 bash "$SCRIPT" --pre-reboot 2>&1)"; RC=$?
echo "$OUT" | sed 's/^/    /' | head -6
[ "$RC" -eq 0 ] && ok "exit 0" || bad "exit $RC"
check "boot cmdline unchanged" grep_t "root=LABEL=SM_ROOT " "$T/boot/cmdline.txt"
sudo umount "$T/top"; sudo btrfs filesystem label "$LR" SM_ROOT_NVM >/dev/null 2>&1; sudo mount "$LR" "$T/top"

echo "== 5. never fails the shutdown: broken device -> exit 0"
sudo env SMOS_PU_EXT_ROOT_DEV=/dev/does-not-exist SMOS_PU_EXT_BOOT_DEV="$LB" SMOS_PU_BOOT_DIR="$T/boot" SMOS_PU_RUNNING_ROOT=/dev/does-not-exist bash "$SCRIPT" --pre-reboot >/dev/null 2>&1
[ $? -eq 0 ] && ok "exit 0" || bad "non-zero exit"

echo "== 6. rescue run (booted from SD, normal mode): labels are fixed without any flag"
reset_staged; reset_boot
OUT="$(run_pu SMOS_PU_RUNNING_ROOT=/dev/mmcblk0p2 bash "$SCRIPT" 2>&1)"; RC=$?
echo "$OUT" | sed 's/^/    /' | grep -i "dual-boot\|changed\|OK\|subvolume" | head -8
[ "$RC" -eq 0 ] && ok "exit 0" || bad "exit $RC"
echo "$OUT" | grep -q "UUID fixup enabled automatically" && ok "dual-boot layout auto-detected" || bad "not auto-detected"
check "boot cmdline -> root=UUID"   grep_t "root=UUID=$ROOT_UUID" "$T/boot/cmdline.txt"
check "staged fstab -> UUID"        test "$(sudo grep -c "^UUID=" "$T/top/@system-2.4.0/etc/fstab")" -eq 3
check "no mount points left under /run" test -z "$(ls -d /run/nvme-*-fix-* 2>/dev/null)"

echo "== 7. exact label match: LABEL=SM_ROOT_NVM must not be rewritten"
echo 'console=tty1 root=LABEL=SM_ROOT_NVM rootfstype=btrfs rootwait' | sudo tee "$T/boot/cmdline.txt" >/dev/null
OUT="$(run_pu SMOS_PU_RUNNING_ROOT=/dev/mmcblk0p2 bash "$SCRIPT" 2>&1)"
check "root=LABEL=SM_ROOT_NVM left alone" grep_t "root=LABEL=SM_ROOT_NVM " "$T/boot/cmdline.txt"
check "no UUID=..._NVM garbage"           test -z "$(sudo grep -E "UUID=[0-9a-f-]+_NVM" "$T/boot/cmdline.txt")"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
