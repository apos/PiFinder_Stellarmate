#!/bin/bash
# StellarMate OS - Post-Update Boot Restore
# Restores cmdline.txt, config.txt, and pacman.conf after a pacman update.
# Then replaces LABEL= with UUID= in cmdline.txt and /etc/fstab, so SD and
# external storage don't collide with each other when running side by side.
#
# Usage:
#   sudo ./smos-post-update.sh                          - normal post-update run (from NVMe/SSD or SD)
#   sudo ./smos-post-update.sh --enable-dual-boot-sd-nvme
#                                                          - additionally: UUID fixup + _NVE/_NVM label rename.
#                                                            ONLY if SD AND NVMe/SSD are used as boot media at
#                                                            the same time - standard installs don't need this
#                                                            and should NOT set it!
#   sudo ./smos-post-update.sh --updatesd               - post-update + update the SD card (external boot only)
#   sudo ./smos-post-update.sh --updatenvme_memory       - memory sync SD -> ext. storage (SD boot only)
#   sudo ./smos-post-update.sh --sync-memory            - basic-memory + .claude <-> Nextcloud (rclone bisync)
#
# Supported hardware:
#   Pi5: NVMe via PCIe (/dev/nvme0n1) - labels _NVE, PCIe Gen3 config
#   Pi4: SSD/NVMe via USB (/dev/sda)  - labels _NVM, no PCIe fix

set -e

if [ "$EUID" -ne 0 ]; then
    echo "!! This script requires root privileges (blkid/fstab/config.txt/pacman need root)."
    echo "   Please run with sudo: sudo bash $(basename "$0") $*"
    exit 1
fi

UPDATE_SD=0
UPDATE_NVME_MEMORY=0
SYNC_MEMORY=0
DUAL_BOOT=0
for arg in "$@"; do
    case "$arg" in
        --updatesd)           UPDATE_SD=1 ;;
        --updatenvme_memory)  UPDATE_NVME_MEMORY=1 ;;
        --sync-memory)        SYNC_MEMORY=1 ;;
        --enable-dual-boot-sd-nvme)          DUAL_BOOT=1 ;;
    esac
done

REBOOT_NEEDED=0
SCRIPT_HAD_ERRORS=0

# ===== External storage: auto-detect device and type =====
NVME_BOOT_DEV=""
NVME_ROOT_DEV=""
NVME_BOOT_TMP=""
NVME_ROOT_TMP=""
STORAGE_TYPE=""   # "nvme" (PCIe, Pi5) or "usb" (USB SSD/NVMe, Pi4)
LABEL_POSTFIX=""  # "_NVE" for Pi5 NVMe, "_NVM" for Pi4 USB

_detect_external_storage() {
    if [ -b "/dev/nvme0n1p1" ]; then
        NVME_BOOT_DEV="/dev/nvme0n1p1"
        NVME_ROOT_DEV="/dev/nvme0n1p2"
        STORAGE_TYPE="nvme"
        LABEL_POSTFIX="_NVE"
        echo "   External storage: NVMe PCIe (/dev/nvme0n1) - Pi5 mode"
        return 0
    fi
    for base in /dev/sda /dev/sdb /dev/sdc; do
        if [ -b "${base}1" ] && [ -b "${base}2" ]; then
            NVME_BOOT_DEV="${base}1"
            NVME_ROOT_DEV="${base}2"
            STORAGE_TYPE="usb"
            LABEL_POSTFIX="_NVM"
            echo "   External storage: USB SSD/NVMe (${base}) - Pi4 mode"
            return 0
        fi
    done
    echo "!! No external storage found (neither /dev/nvme0n1 nor /dev/sdX)"
    return 1
}

_setup_nvme_dirs() {
    _detect_external_storage || return 1

    local root_dev
    root_dev=$(findmnt -n -o SOURCE / | sed 's/\[.*//')

    if [[ "$root_dev" == /dev/nvme* ]]; then
        BOOT_FROM_NVME=1
        NVME_BOOT_DIR="/boot"
        NVME_FSTAB="/etc/fstab"
        echo "   Boot source: NVMe ($root_dev)"
    else
        BOOT_FROM_NVME=0
        echo "   Boot source: SD ($root_dev) - mounting NVMe partitions..."

        if [ ! -b "$NVME_BOOT_DEV" ]; then
            echo "!! NVMe not found ($NVME_BOOT_DEV) - aborting."
            exit 1
        fi

        NVME_BOOT_TMP=$(mktemp -d /mnt/nvme-boot-fix-XXXXXX)
        NVME_ROOT_TMP=$(mktemp -d /mnt/nvme-root-fix-XXXXXX)

        mount "$NVME_BOOT_DEV" "$NVME_BOOT_TMP"
        mount -o subvolid=5 "$NVME_ROOT_DEV" "$NVME_ROOT_TMP"

        NVME_BOOT_DIR="$NVME_BOOT_TMP"

        # Read the active subvolume from NVMe's cmdline.txt, determine the fstab path
        local nvme_subvol
        nvme_subvol=$(grep -oP 'subvol=\K[^\s]+' "${NVME_BOOT_TMP}/cmdline.txt" | sed 's|^/||')
        if [ -n "$nvme_subvol" ] && [ -d "${NVME_ROOT_TMP}/${nvme_subvol}" ]; then
            NVME_FSTAB="${NVME_ROOT_TMP}/${nvme_subvol}/etc/fstab"
            echo "   NVMe subvolume: $nvme_subvol"
        else
            echo "!! Could not determine NVMe subvolume - skipping fstab fixup."
            NVME_FSTAB=""
        fi

        _cleanup_nvme_mounts() {
            [ -n "$NVME_BOOT_TMP" ] && { umount "$NVME_BOOT_TMP" 2>/dev/null; rmdir "$NVME_BOOT_TMP" 2>/dev/null; } || true
            [ -n "$NVME_ROOT_TMP" ] && { umount "$NVME_ROOT_TMP" 2>/dev/null; rmdir "$NVME_ROOT_TMP" 2>/dev/null; } || true
        }
        trap _cleanup_nvme_mounts EXIT
    fi
}

# ===== Functions =====

restore_file() {
    local src="$1"
    # Redirect path to the NVMe boot partition if needed
    local target
    if [[ "$src" == /boot/* ]]; then
        target="${NVME_BOOT_DIR}/${src#/boot/}"
    else
        target="$src"
    fi
    if [ -f "${target}.pacsave" ]; then
        cp "${target}.pacsave" "${target}"
        echo ">> $(basename "$src") restored."
        REBOOT_NEEDED=1
    else
        echo ">> $(basename "$src").pacsave not present - no restore needed."
    fi
}

rename_nvme_labels() {
    local boot_label root_label
    local new_boot_label="SM_BOOT${LABEL_POSTFIX}"
    local new_root_label="SM_ROOT${LABEL_POSTFIX}"

    boot_label=$(blkid -s LABEL -o value "$NVME_BOOT_DEV" 2>/dev/null)
    root_label=$(blkid -s LABEL -o value "$NVME_ROOT_DEV" 2>/dev/null)

    if [ "$boot_label" = "SM_BOOT" ]; then
        fatlabel "$NVME_BOOT_DEV" "$new_boot_label" \
            && echo ">> [Storage] Partition label: SM_BOOT -> ${new_boot_label}" \
            || echo "!! [Storage] fatlabel failed - manually: sudo fatlabel $NVME_BOOT_DEV $new_boot_label"
        REBOOT_NEEDED=1
    else
        echo ">> [Storage] Partition label /boot: OK (${boot_label})"
    fi

    if [ "$root_label" = "SM_ROOT" ]; then
        if [ "$BOOT_FROM_NVME" -eq 1 ]; then
            btrfs filesystem label / "$new_root_label"
        else
            btrfs filesystem label "$NVME_ROOT_TMP" "$new_root_label"
        fi
        echo ">> [Storage] Partition label: SM_ROOT -> ${new_root_label}"
        REBOOT_NEEDED=1
    else
        echo ">> [Storage] Partition label /root: OK (${root_label})"
    fi
}

fix_uuids() {
    local boot_uuid root_uuid
    boot_uuid=$(blkid -s UUID -o value "$NVME_BOOT_DEV")
    root_uuid=$(blkid -s UUID -o value "$NVME_ROOT_DEV")

    if [ -z "$boot_uuid" ] || [ -z "$root_uuid" ]; then
        echo "!! Could not determine UUIDs - LABEL= stays unchanged!"
        return 1
    fi

    # cmdline.txt on the NVMe boot partition: root=LABEL= -> root=UUID=
    local cmdline="${NVME_BOOT_DIR}/cmdline.txt"
    if grep -q 'root=LABEL=SM_ROOT' "$cmdline"; then
        sed -i "s|root=LABEL=SM_ROOT|root=UUID=${root_uuid}|g" "$cmdline"
        echo ">> [NVMe] cmdline.txt:  changed  (LABEL=SM_ROOT -> UUID=${root_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] cmdline.txt:  OK"
    fi

    # fstab on NVMe: LABEL=SM_BOOT and LABEL=SM_ROOT -> UUIDs
    if [ -z "$NVME_FSTAB" ]; then
        echo ">> [NVMe] fstab:        skipped (no path determined)"
        return 0
    fi
    if grep -q 'LABEL=SM_BOOT' "$NVME_FSTAB"; then
        sed -i "s|LABEL=SM_BOOT|UUID=${boot_uuid}|g" "$NVME_FSTAB"
        echo ">> [NVMe] fstab /boot:  changed  (LABEL=SM_BOOT -> UUID=${boot_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] fstab /boot:  OK"
    fi
    if grep -q 'LABEL=SM_ROOT' "$NVME_FSTAB"; then
        sed -i "s|LABEL=SM_ROOT|UUID=${root_uuid}|g" "$NVME_FSTAB"
        echo ">> [NVMe] fstab /:      changed  (LABEL=SM_ROOT -> UUID=${root_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] fstab /:      OK"
    fi
}

fix_nvme_config() {
    # PCIe Gen3 only matters for real NVMe (Pi5), not USB SSD (Pi4)
    if [ "$STORAGE_TYPE" != "nvme" ]; then
        echo ">> [Storage] config.txt PCIe fix: skipped (USB mode, no PCIe)"
        return 0
    fi

    local config="${NVME_BOOT_DIR}/config.txt"

    # Ensure dtparam=pciex1_gen=3 is set (PCIe Gen3 for NVMe, ~985 MB/s instead of ~500 MB/s)
    if ! grep -q 'dtparam=pciex1_gen=3' "$config"; then
        sed -i 's/\[pi5\]/[pi5]\ndtparam=pciex1_gen=3/' "$config"
        echo ">> [NVMe] config.txt: dtparam=pciex1_gen=3 added (PCIe Gen3)"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] config.txt: dtparam=pciex1_gen=3 OK"
    fi
}

install_extra_packages() {
    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo ">> Extra packages: skipped (SD boot - only relevant on NVMe)"
        return 0
    fi

    local pkg_list
    pkg_list="$(dirname "$(realpath "$0")")/package.list"

    if [ ! -f "$pkg_list" ]; then
        echo "!! package.list not found: $pkg_list - aborting."
        return 1
    fi

    local tmp_conf
    tmp_conf=$(mktemp)
    cat /etc/pacman.conf > "$tmp_conf"
    # [core] is already active in pacman.conf; add [extra] as a fallback
    if ! grep -q '^\[extra\]' "$tmp_conf"; then
        printf '\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n' >> "$tmp_conf"
    fi

    local installed=0 skipped=0 failed=0
    while IFS= read -r pkg || [ -n "$pkg" ]; do
        # Skip blank lines and comments
        [[ -z "$pkg" || "$pkg" =~ ^# ]] && continue

        if pacman -Q "$pkg" &>/dev/null; then
            echo ">> ${pkg}: present."
            (( skipped++ )) || true
        else
            echo ">> ${pkg} missing - installing..."
            if pacman -Sy --noconfirm --config "$tmp_conf" "$pkg"; then
                echo ">> ${pkg}: installed."
                (( installed++ )) || true
            else
                echo "!! ${pkg}: installation failed - please install manually."
                (( failed++ )) || true
            fi
        fi
    done < "$pkg_list"

    rm -f "$tmp_conf"
    echo "   Result: ${installed} installed, ${skipped} already present, ${failed} failed."
}

restore_wireguard() {
    local service="wg-nethserver-client"
    local backup_file="/home/stellarmate/bin/backup_files/${service}.service"

    # On SD boot, NVME_FSTAB points at the temporarily-mounted NVMe subvolume
    # (${NVME_ROOT_TMP}/${nvme_subvol}/etc/fstab); on NVMe boot it's simply
    # /etc/fstab -> the prefix trick gives the right "etc" location either way,
    # same as restore_file()/fix_uuids(). This whole step used to be skipped on
    # SD boot - exactly the case where the NVMe /etc needs repairing after a
    # failed update reboot (a snapshot switch can lose manually-created /etc
    # files like this service).
    if [ -z "$NVME_FSTAB" ]; then
        echo "!! WireGuard restore: skipped (NVMe subvolume not determinable)"
        return 0
    fi
    local etc_prefix="${NVME_FSTAB%/etc/fstab}"
    local service_file="${etc_prefix}/etc/systemd/system/${service}.service"

    # Restore the service from backup if missing
    if [ ! -f "$service_file" ]; then
        echo ">> Service file missing - restoring from backup..."
        echo "   Source:      $backup_file"
        echo "   Destination: $service_file"
        cp "$backup_file" "$service_file"
        if [ "$BOOT_FROM_NVME" -eq 1 ]; then
            systemctl daemon-reload
            systemctl enable --now "${service}.service"
            echo ">> Service restored, enabled, and started."
        else
            if systemctl --root="$etc_prefix" enable "${service}.service" 2>/dev/null; then
                echo ">> Service restored and enabled for the next NVMe boot (offline via --root)."
            else
                echo "!! Service file restored, but 'systemctl --root enable' failed."
                echo "   After the next NVMe boot, run manually: sudo systemctl enable --now ${service}.service"
            fi
        fi
    else
        echo ">> Service file: present"
        echo "   Path:  $service_file"
    fi

    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo ">> Live status skipped (SD boot, NVMe system isn't running)"
        return 0
    fi

    if systemctl is-active --quiet "${service}.service"; then
        local wg_iface wg_ip wg_endpoint wg_handshake
        wg_iface=$(wg show interfaces 2>/dev/null | awk '{print $1}')
        wg_ip=$(ip -4 addr show "$wg_iface" 2>/dev/null | awk '/inet / {print $2}')
        wg_endpoint=$(wg show "$wg_iface" endpoints 2>/dev/null | awk '{print $2}')
        wg_handshake=$(wg show "$wg_iface" latest-handshakes 2>/dev/null | awk '{print $2}')
        echo ">> Service: running"
        echo "   Interface:  $wg_iface"
        echo "   Tunnel IP:  ${wg_ip:-unknown}"
        echo "   Endpoint:   ${wg_endpoint:-unknown}"
        echo "   Handshake:  $(date -d "@${wg_handshake}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'no handshake yet')"
    else
        echo "!! Service: not active!"
    fi
}

update_sd() {
    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo "!! --updatesd requires NVMe boot (sync runs NVMe -> SD)."
        echo "   Please boot from NVMe and run again."
        return 1
    fi

    local SD_BOOT_DEV="/dev/mmcblk0p1"
    local SD_ROOT_DEV="/dev/mmcblk0p2"
    local MNT_SD_BTRFS="/mnt/sd-btrfs-root"
    local MNT_SD_BOOT="/mnt/sd-boot"

    # Check the SD card (before the trap, no cleanup needed yet)
    if [ ! -b "$SD_ROOT_DEV" ]; then
        echo "!! SD card not found ($SD_ROOT_DEV) - SD update skipped."
        echo "   Insert the SD card and run again with --updatesd."
        return 1
    fi

    # Cleanup function - runs on EXIT or error
    _cleanup_sd() {
        echo ">> Unmounting SD partitions..."
        umount "$MNT_SD_BOOT"   2>/dev/null || true
        umount "$MNT_SD_BTRFS"  2>/dev/null || true

        # Unmount any additional mounts of the same devices (e.g. a desktop
        # automount via udisks2, which mounts under /run/media/... on card
        # insert independently of this script) - otherwise the card is still
        # in use despite "SD update complete" and can't be safely removed.
        local dev extra_mnt
        for dev in "$SD_BOOT_DEV" "$SD_ROOT_DEV"; do
            while read -r extra_mnt; do
                [ -n "$extra_mnt" ] && umount "$extra_mnt" 2>/dev/null
            done < <(findmnt -n -o TARGET -S "$dev" 2>/dev/null)
        done
    }
    trap _cleanup_sd EXIT

    mkdir -p "$MNT_SD_BTRFS" "$MNT_SD_BOOT"

    echo ">> Mounting SD partitions..."
    mount -o subvolid=5 "$SD_ROOT_DEV" "$MNT_SD_BTRFS"
    mount "$SD_BOOT_DEV" "$MNT_SD_BOOT"

    # NVMe UUIDs (we're on NVMe, blkid directly)
    local nvme_boot_uuid nvme_root_uuid
    nvme_boot_uuid=$(blkid -s UUID -o value "$NVME_BOOT_DEV")
    nvme_root_uuid=$(blkid -s UUID -o value "$NVME_ROOT_DEV")

    # Determine the active NVMe subvolume
    local active_subvol
    active_subvol=$(findmnt -n -o OPTIONS / | grep -oP 'subvol=\K[^,\]]+')
    if [ -z "$active_subvol" ]; then
        echo "!! Could not determine the active NVMe subvolume - aborting."
        return 1
    fi
    echo "   Active subvolume: $active_subvol"

    # Create the target subvolume on SD if it doesn't exist
    local sd_subvol_path="${MNT_SD_BTRFS}/${active_subvol}"
    if [ ! -d "$sd_subvol_path" ]; then
        echo ">> Creating subvolume ${active_subvol} on SD..."
        btrfs subvolume create "$sd_subvol_path"
    else
        echo ">> Subvolume ${active_subvol} on SD: present."
    fi

    # Create @home on SD if it doesn't exist
    if [ ! -d "${MNT_SD_BTRFS}/@home" ]; then
        echo ">> Creating @home subvolume on SD..."
        btrfs subvolume create "${MNT_SD_BTRFS}/@home"
    fi

    # --- Space check ---
    echo ""
    echo ">> Space check..."
    local sys_size home_size boot_size total_needed sd_free
    sys_size=$(du -sx \
        --exclude=proc --exclude=sys --exclude=dev --exclude=run \
        --exclude=tmp --exclude=boot --exclude=home --exclude=mnt \
        / 2>/dev/null | awk '{print $1}')
    home_size=$(du -sx \
        --exclude=Pictures --exclude=Videos --exclude=Downloads --exclude=.cache \
        /home/stellarmate 2>/dev/null | awk '{print $1}')
    boot_size=$(du -sx /boot 2>/dev/null | awk '{print $1}')
    total_needed=$(( (sys_size + home_size + boot_size) * 12 / 10 ))  # +20% buffer

    sd_free=$(df --output=avail "$MNT_SD_BTRFS" | tail -1)

    printf "   System: %4d MiB  |  Home: %4d MiB  |  Boot: %4d MiB\n" \
        "$(( sys_size  / 1024 ))" "$(( home_size / 1024 ))" "$(( boot_size / 1024 ))"
    printf "   Needed (incl. 20%% buffer): %d MiB  |  SD free: %d MiB\n" \
        "$(( total_needed / 1024 ))" "$(( sd_free / 1024 ))"

    if [ "$total_needed" -gt "$sd_free" ]; then
        echo "!! Not enough space on SD - aborting."
        return 1
    fi
    echo "   Space: OK"

    # --- System sync ---
    echo ""
    echo ">> System sync NVMe -> SD (${active_subvol})..."
    rsync -aHAX --delete --one-file-system \
        --exclude=/proc --exclude=/sys --exclude=/dev --exclude=/run \
        --exclude=/tmp  --exclude=/boot --exclude=/home --exclude=/mnt \
        --exclude=/lost+found \
        --info=progress2 \
        / "${sd_subvol_path}/"
    echo ">> System sync: OK"

    # --- Boot sync ---
    echo ""
    echo ">> Boot sync NVMe -> SD..."
    rsync -aH --delete --info=progress2 /boot/ "${MNT_SD_BOOT}/"
    echo ">> Boot sync: OK"

    # --- Home sync ---
    echo ""
    echo ">> Home sync /home/stellarmate -> SD..."
    mkdir -p "${MNT_SD_BTRFS}/@home/stellarmate"
    rsync -aHAX --delete \
        --exclude=Pictures --exclude=Videos --exclude=Downloads --exclude=.cache \
        --info=progress2 \
        /home/stellarmate/ "${MNT_SD_BTRFS}/@home/stellarmate/"
    echo ">> Home sync: OK"

    # --- Patch cmdline.txt on SD: NVMe UUID -> LABEL= (vendor default) ---
    echo ""
    echo ">> Patching SD cmdline.txt..."
    if grep -q "$nvme_root_uuid" "${MNT_SD_BOOT}/cmdline.txt"; then
        sed -i "s|root=UUID=${nvme_root_uuid}|root=LABEL=SM_ROOT|g" "${MNT_SD_BOOT}/cmdline.txt"
        echo "   root=: UUID -> LABEL=SM_ROOT  OK"
    else
        echo "   root=: already correct"
    fi
    if grep -q 'subvol=' "${MNT_SD_BOOT}/cmdline.txt"; then
        sed -i "s|subvol=[^ ,]*|subvol=${active_subvol}|g" "${MNT_SD_BOOT}/cmdline.txt"
        echo "   subvol=: ${active_subvol}  OK"
    fi

    # --- Patch fstab in the SD subvolume: NVMe UUIDs -> LABEL= (vendor default) ---
    echo ">> Patching SD fstab..."
    local sd_fstab="${sd_subvol_path}/etc/fstab"
    sed -i \
        "s|UUID=${nvme_boot_uuid}|LABEL=SM_BOOT|g; \
         s|UUID=${nvme_root_uuid}|LABEL=SM_ROOT|g" \
        "$sd_fstab"
    echo "   UUIDs -> LABEL=SM_BOOT / LABEL=SM_ROOT  OK"

    # Reset the trap, then clean up manually
    trap - EXIT
    _cleanup_sd
    echo ""
    echo ">> SD update complete."
}

update_nvme_memory() {
    local NVME_BTRFS_MNT="/mnt/nvme-btrfs-root"
    local NVME_HOME="${NVME_BTRFS_MNT}/@home/stellarmate"

    # Check whether booted from SD
    if [ "$BOOT_FROM_NVME" -eq 1 ]; then
        echo "!! Not booted from SD - this command only makes sense on SD boot."
        return 1
    fi
    echo "   Boot source: SD  OK"

    # Check NVMe
    if [ ! -b "$NVME_ROOT_DEV" ]; then
        echo "!! NVMe not found ($NVME_ROOT_DEV) - aborting."
        return 1
    fi

    _cleanup_nvme_mem() {
        echo ">> Unmounting NVMe..."
        umount "$NVME_BTRFS_MNT" 2>/dev/null || true
    }
    trap _cleanup_nvme_mem EXIT

    mkdir -p "$NVME_BTRFS_MNT"
    echo ">> Mounting NVMe (subvolid=5)..."
    mount -o subvolid=5 "$NVME_ROOT_DEV" "$NVME_BTRFS_MNT"

    if [ ! -d "$NVME_HOME" ]; then
        echo "!! NVMe @home not found: $NVME_HOME - aborting."
        return 1
    fi

    # Space check
    echo ""
    echo ">> Space check..."
    local mem_size nvme_free
    mem_size=$(du -sx /home/stellarmate/basic-memory /home/stellarmate/.claude 2>/dev/null | awk '{sum += $1} END {print sum}')
    mem_size=$(( mem_size * 12 / 10 ))  # +20% buffer
    nvme_free=$(df --output=avail "$NVME_BTRFS_MNT" | tail -1)

    printf "   Memory data (incl. 20%% buffer): %d KiB  |  NVMe free: %d MiB\n" \
        "$mem_size" "$(( nvme_free / 1024 ))"

    if [ "$mem_size" -gt "$nvme_free" ]; then
        echo "!! Not enough space on NVMe - aborting."
        return 1
    fi
    echo "   Space: OK"

    # basic-memory sync
    echo ""
    echo ">> basic-memory: SD -> NVMe..."
    mkdir -p "${NVME_HOME}/basic-memory"
    rsync -aHAX --delete --info=progress2 \
        /home/stellarmate/basic-memory/ \
        "${NVME_HOME}/basic-memory/"
    echo ">> basic-memory: OK"

    # .claude sync
    echo ""
    echo ">> .claude: SD -> NVMe..."
    mkdir -p "${NVME_HOME}/.claude"
    rsync -aHAX --delete --info=progress2 \
        /home/stellarmate/.claude/ \
        "${NVME_HOME}/.claude/"
    echo ">> .claude: OK"

    trap - EXIT
    _cleanup_nvme_mem
    echo ""
    echo ">> Memory sync complete. NVMe is up to date."
}

sync_memory() {
    local RCLONE_CONF="/home/stellarmate/.config/rclone/rclone.conf"
    local RCLONE_BACKUP="/home/stellarmate/bin/backup_files/rclone.conf"

    # Install rclone if missing
    if ! command -v rclone &>/dev/null; then
        echo ">> rclone not found - installing..."
        local tmp_conf
        tmp_conf=$(mktemp)
        cat /etc/pacman.conf > "$tmp_conf"
        if ! grep -q '^\[extra\]' "$tmp_conf"; then
            printf '\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n' >> "$tmp_conf"
        fi
        if pacman -Sy --noconfirm --config "$tmp_conf" rclone; then
            echo ">> rclone: installed."
        else
            echo "!! rclone: installation failed - please install manually: sudo pacman -S rclone"
            rm -f "$tmp_conf"
            return 1
        fi
        rm -f "$tmp_conf"
    else
        echo ">> rclone: present."
    fi

    # Restore rclone.conf if missing
    if [ ! -f "$RCLONE_CONF" ]; then
        if [ -f "$RCLONE_BACKUP" ]; then
            echo ">> rclone.conf missing - restoring from backup..."
            mkdir -p "$(dirname "$RCLONE_CONF")"
            cp "$RCLONE_BACKUP" "$RCLONE_CONF"
            chmod 600 "$RCLONE_CONF"
            echo ">> rclone.conf: restored."
        else
            echo "!! rclone.conf missing and no backup under $RCLONE_BACKUP"
            echo "   Please configure manually: rclone config"
            return 1
        fi
    fi

    # The actual bisync logic (reachability check, --resync-on-first-run
    # detection, the bisync call itself) lives in one place -
    # basic-memory/basic-memory/scripts/sync_basic_memory.sh - and is also
    # what basic-memory-sync.timer (systemd --user, every 15 min, set up via
    # setup_basic_memory_sync.sh in the same directory) runs automatically.
    # This function's own job is just the root-only recovery above (rclone
    # missing / rclone.conf missing after an SMOS update wiped the root
    # filesystem) before delegating to it - not duplicating the sync logic.
    #
    # Run as user "stellarmate" (not as root): rclone looks up its config AND
    # the bisync state cache relative to $HOME. Under sudo/root that would be
    # /root/... instead of /home/stellarmate/....
    local sync_script="/home/stellarmate/basic-memory/basic-memory/scripts/sync_basic_memory.sh"
    if [ ! -f "$sync_script" ]; then
        echo "!! ${sync_script} missing - basic-memory checkout incomplete?"
        return 1
    fi
    echo ">> basic-memory bisync: local <-> Nextcloud ..."
    if sudo -u stellarmate bash "$sync_script"; then
        echo ">> basic-memory: OK"
    else
        echo "!! basic-memory bisync failed - please check manually"
        return 1
    fi
}

# ===== Main program =====

if [ "$SYNC_MEMORY" -eq 1 ]; then
    echo "=== Memory sync <-> Nextcloud ==="
    sync_memory
    exit 0
fi

if [ "$UPDATE_NVME_MEMORY" -eq 1 ]; then
    echo "=== Memory sync SD -> NVMe ==="
    _setup_nvme_dirs
    update_nvme_memory
    exit 0
fi

echo "=== StellarMate Post-Update Boot Restore ==="
_setup_nvme_dirs
echo ""

restore_file /boot/cmdline.txt
restore_file /boot/config.txt
restore_file /etc/pacman.conf

if [ "$DUAL_BOOT" -eq 1 ]; then
    echo ""
    echo "=== UUID fixup ==="
    fix_uuids || SCRIPT_HAD_ERRORS=1
else
    echo ""
    echo "=== UUID fixup / label rename: skipped (no --enable-dual-boot-sd-nvme) ==="
fi

echo ""
echo "=== NVMe config fixup ==="
fix_nvme_config

if [ "$DUAL_BOOT" -eq 1 ]; then
    echo ""
    echo "=== NVMe label rename ==="
    rename_nvme_labels
fi

echo ""
echo "=== Extra packages ==="
install_extra_packages || SCRIPT_HAD_ERRORS=1

echo ""
echo "=== WireGuard restore ==="
restore_wireguard

if [ "$UPDATE_SD" -eq 1 ]; then
    echo ""
    echo "=== SD update ==="
    update_sd || SCRIPT_HAD_ERRORS=1
fi

# Clean up NVMe mounts (if booted from SD)
if [ -n "$NVME_BOOT_TMP" ]; then
    trap - EXIT
    umount "$NVME_BOOT_TMP" 2>/dev/null; rmdir "$NVME_BOOT_TMP" 2>/dev/null || true
    umount "$NVME_ROOT_TMP" 2>/dev/null; rmdir "$NVME_ROOT_TMP" 2>/dev/null || true
fi

echo ""
if [ "$REBOOT_NEEDED" -eq 1 ]; then
    echo "=== Done. Reboot required: sudo reboot ==="
else
    echo "=== Done. No reboot needed. ==="
fi

if [ "$SCRIPT_HAD_ERRORS" -eq 1 ]; then
    echo "!! At least one step failed (see messages above) - please check."
    exit 1
fi
