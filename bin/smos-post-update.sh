#!/bin/bash
# StellarMate OS - Post-Update Boot Restore
# Stellt cmdline.txt, config.txt und pacman.conf nach einem pacman-Update wieder her.
# Ersetzt danach LABEL= durch UUID= in cmdline.txt und /etc/fstab,
# damit SD und externer Storage sich beim gleichzeitigen Betrieb nicht in die Quere kommen.
#
# Verwendung:
#   sudo ./smos-post-update.sh                    – normaler Post-Update-Lauf (von NVMe/SSD oder SD)
#   sudo ./smos-post-update.sh --updatesd         – Post-Update + SD-Karte aktualisieren (nur ext. Boot)
#   sudo ./smos-post-update.sh --updatenvme_memory – Memory-Sync SD → ext. Storage (nur SD-Boot)
#   sudo ./smos-post-update.sh --sync-memory      – basic-memory + .claude ↔ Nextcloud (rclone bisync)
#
# Unterstützte Hardware:
#   Pi5: NVMe via PCIe (/dev/nvme0n1) – Labels _NVE, PCIe Gen3 config
#   Pi4: SSD/NVMe via USB (/dev/sda)  – Labels _NVM, kein PCIe-Fix

set -e

if [ "$EUID" -ne 0 ]; then
    echo "!! Dieses Skript benoetigt Root-Rechte (blkid/fstab/config.txt/pacman brauchen root)."
    echo "   Bitte mit sudo starten: sudo bash $(basename "$0") $*"
    exit 1
fi

UPDATE_SD=0
UPDATE_NVME_MEMORY=0
SYNC_MEMORY=0
for arg in "$@"; do
    case "$arg" in
        --updatesd)           UPDATE_SD=1 ;;
        --updatenvme_memory)  UPDATE_NVME_MEMORY=1 ;;
        --sync-memory)        SYNC_MEMORY=1 ;;
    esac
done

REBOOT_NEEDED=0

# ===== Externer Storage: Gerät und Typ automatisch erkennen =====
NVME_BOOT_DEV=""
NVME_ROOT_DEV=""
NVME_BOOT_TMP=""
NVME_ROOT_TMP=""
STORAGE_TYPE=""   # "nvme" (PCIe, Pi5) oder "usb" (USB SSD/NVMe, Pi4)
LABEL_POSTFIX=""  # "_NVE" für Pi5 NVMe, "_NVM" für Pi4 USB

_detect_external_storage() {
    if [ -b "/dev/nvme0n1p1" ]; then
        NVME_BOOT_DEV="/dev/nvme0n1p1"
        NVME_ROOT_DEV="/dev/nvme0n1p2"
        STORAGE_TYPE="nvme"
        LABEL_POSTFIX="_NVE"
        echo "   Externer Storage: NVMe PCIe (/dev/nvme0n1) – Pi5-Modus"
        return 0
    fi
    for base in /dev/sda /dev/sdb /dev/sdc; do
        if [ -b "${base}1" ] && [ -b "${base}2" ]; then
            NVME_BOOT_DEV="${base}1"
            NVME_ROOT_DEV="${base}2"
            STORAGE_TYPE="usb"
            LABEL_POSTFIX="_NVM"
            echo "   Externer Storage: USB SSD/NVMe (${base}) – Pi4-Modus"
            return 0
        fi
    done
    echo "!! Kein externer Storage gefunden (kein /dev/nvme0n1 und kein /dev/sdX)"
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
        echo "   Boot-Quelle: NVMe ($root_dev)"
    else
        BOOT_FROM_NVME=0
        echo "   Boot-Quelle: SD ($root_dev) – NVMe-Partitionen werden gemountet..."

        if [ ! -b "$NVME_BOOT_DEV" ]; then
            echo "!! NVMe nicht gefunden ($NVME_BOOT_DEV) – Abbruch."
            exit 1
        fi

        NVME_BOOT_TMP=$(mktemp -d /mnt/nvme-boot-fix-XXXXXX)
        NVME_ROOT_TMP=$(mktemp -d /mnt/nvme-root-fix-XXXXXX)

        mount "$NVME_BOOT_DEV" "$NVME_BOOT_TMP"
        mount -o subvolid=5 "$NVME_ROOT_DEV" "$NVME_ROOT_TMP"

        NVME_BOOT_DIR="$NVME_BOOT_TMP"

        # Aktives Subvolume aus NVMe cmdline.txt lesen, fstab-Pfad ermitteln
        local nvme_subvol
        nvme_subvol=$(grep -oP 'subvol=\K[^\s]+' "${NVME_BOOT_TMP}/cmdline.txt" | sed 's|^/||')
        if [ -n "$nvme_subvol" ] && [ -d "${NVME_ROOT_TMP}/${nvme_subvol}" ]; then
            NVME_FSTAB="${NVME_ROOT_TMP}/${nvme_subvol}/etc/fstab"
            echo "   NVMe Subvolume: $nvme_subvol"
        else
            echo "!! NVMe-Subvolume nicht ermittelbar – fstab-Fixup wird übersprungen."
            NVME_FSTAB=""
        fi

        _cleanup_nvme_mounts() {
            [ -n "$NVME_BOOT_TMP" ] && { umount "$NVME_BOOT_TMP" 2>/dev/null; rmdir "$NVME_BOOT_TMP" 2>/dev/null; } || true
            [ -n "$NVME_ROOT_TMP" ] && { umount "$NVME_ROOT_TMP" 2>/dev/null; rmdir "$NVME_ROOT_TMP" 2>/dev/null; } || true
        }
        trap _cleanup_nvme_mounts EXIT
    fi
}

# ===== Funktionen =====

restore_file() {
    local src="$1"
    # Pfad auf NVMe-Boot-Partition umleiten wenn nötig
    local target
    if [[ "$src" == /boot/* ]]; then
        target="${NVME_BOOT_DIR}/${src#/boot/}"
    else
        target="$src"
    fi
    if [ -f "${target}.pacsave" ]; then
        cp "${target}.pacsave" "${target}"
        echo ">> $(basename "$src") wiederhergestellt."
        REBOOT_NEEDED=1
    else
        echo ">> $(basename "$src").pacsave nicht vorhanden – keine Wiederherstellung nötig."
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
            && echo ">> [Storage] Partition-Label: SM_BOOT → ${new_boot_label}" \
            || echo "!! [Storage] fatlabel fehlgeschlagen – manuell: sudo fatlabel $NVME_BOOT_DEV $new_boot_label"
        REBOOT_NEEDED=1
    else
        echo ">> [Storage] Partition-Label /boot: OK (${boot_label})"
    fi

    if [ "$root_label" = "SM_ROOT" ]; then
        if [ "$BOOT_FROM_NVME" -eq 1 ]; then
            btrfs filesystem label / "$new_root_label"
        else
            btrfs filesystem label "$NVME_ROOT_TMP" "$new_root_label"
        fi
        echo ">> [Storage] Partition-Label: SM_ROOT → ${new_root_label}"
        REBOOT_NEEDED=1
    else
        echo ">> [Storage] Partition-Label /root: OK (${root_label})"
    fi
}

fix_uuids() {
    local boot_uuid root_uuid
    boot_uuid=$(blkid -s UUID -o value "$NVME_BOOT_DEV")
    root_uuid=$(blkid -s UUID -o value "$NVME_ROOT_DEV")

    if [ -z "$boot_uuid" ] || [ -z "$root_uuid" ]; then
        echo "!! UUID-Ermittlung fehlgeschlagen – LABEL= bleibt unverändert!"
        return 1
    fi

    # cmdline.txt auf NVMe-Boot-Partition: root=LABEL= → root=UUID=
    local cmdline="${NVME_BOOT_DIR}/cmdline.txt"
    if grep -q 'root=LABEL=SM_ROOT' "$cmdline"; then
        sed -i "s|root=LABEL=SM_ROOT|root=UUID=${root_uuid}|g" "$cmdline"
        echo ">> [NVMe] cmdline.txt:  geändert  (LABEL=SM_ROOT → UUID=${root_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] cmdline.txt:  OK"
    fi

    # fstab auf NVMe: LABEL=SM_BOOT und LABEL=SM_ROOT → UUIDs
    if [ -z "$NVME_FSTAB" ]; then
        echo ">> [NVMe] fstab:        übersprungen (kein Pfad ermittelt)"
        return 0
    fi
    if grep -q 'LABEL=SM_BOOT' "$NVME_FSTAB"; then
        sed -i "s|LABEL=SM_BOOT|UUID=${boot_uuid}|g" "$NVME_FSTAB"
        echo ">> [NVMe] fstab /boot:  geändert  (LABEL=SM_BOOT → UUID=${boot_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] fstab /boot:  OK"
    fi
    if grep -q 'LABEL=SM_ROOT' "$NVME_FSTAB"; then
        sed -i "s|LABEL=SM_ROOT|UUID=${root_uuid}|g" "$NVME_FSTAB"
        echo ">> [NVMe] fstab /:      geändert  (LABEL=SM_ROOT → UUID=${root_uuid})"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] fstab /:      OK"
    fi
}

fix_nvme_config() {
    # PCIe Gen3 nur relevant für echten NVMe (Pi5), nicht für USB SSD (Pi4)
    if [ "$STORAGE_TYPE" != "nvme" ]; then
        echo ">> [Storage] config.txt PCIe-Fix: übersprungen (USB-Modus, kein PCIe)"
        return 0
    fi

    local config="${NVME_BOOT_DIR}/config.txt"

    # dtparam=pciex1_gen=3 sicherstellen (PCIe Gen3 für NVMe, ~985 MB/s statt ~500 MB/s)
    if ! grep -q 'dtparam=pciex1_gen=3' "$config"; then
        sed -i 's/\[pi5\]/[pi5]\ndtparam=pciex1_gen=3/' "$config"
        echo ">> [NVMe] config.txt: dtparam=pciex1_gen=3 eingetragen (PCIe Gen3)"
        REBOOT_NEEDED=1
    else
        echo ">> [NVMe] config.txt: dtparam=pciex1_gen=3 OK"
    fi
}

install_extra_packages() {
    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo ">> Extra-Pakete: übersprungen (SD-Boot – nur auf NVMe sinnvoll)"
        return 0
    fi

    local pkg_list
    pkg_list="$(dirname "$(realpath "$0")")/package.list"

    if [ ! -f "$pkg_list" ]; then
        echo "!! package.list nicht gefunden: $pkg_list – Abbruch."
        return 1
    fi

    local tmp_conf
    tmp_conf=$(mktemp)
    cat /etc/pacman.conf > "$tmp_conf"
    # [core] ist in pacman.conf bereits aktiv; [extra] als Fallback ergänzen
    if ! grep -q '^\[extra\]' "$tmp_conf"; then
        printf '\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n' >> "$tmp_conf"
    fi

    local installed=0 skipped=0 failed=0
    while IFS= read -r pkg || [ -n "$pkg" ]; do
        # Leerzeilen und Kommentare überspringen
        [[ -z "$pkg" || "$pkg" =~ ^# ]] && continue

        if pacman -Q "$pkg" &>/dev/null; then
            echo ">> ${pkg}: vorhanden."
            (( skipped++ )) || true
        else
            echo ">> ${pkg} fehlt – wird installiert..."
            if pacman -Sy --noconfirm --config "$tmp_conf" "$pkg"; then
                echo ">> ${pkg}: installiert."
                (( installed++ )) || true
            else
                echo "!! ${pkg}: Installation fehlgeschlagen – bitte manuell installieren."
                (( failed++ )) || true
            fi
        fi
    done < "$pkg_list"

    rm -f "$tmp_conf"
    echo "   Ergebnis: ${installed} installiert, ${skipped} bereits vorhanden, ${failed} fehlgeschlagen."
}

restore_wireguard() {
    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo ">> WireGuard Restore: übersprungen (SD-Boot – nur auf NVMe sinnvoll)"
        return 0
    fi

    local service="wg-nethserver-client"
    local service_file="/etc/systemd/system/${service}.service"
    local backup_file="/home/stellarmate/bin/backup_files/${service}.service"

    # Service aus Backup wiederherstellen falls fehlt
    if [ ! -f "$service_file" ]; then
        echo ">> Service-File fehlt – wird aus Backup wiederhergestellt..."
        echo "   Quelle:  $backup_file"
        echo "   Ziel:    $service_file"
        cp "$backup_file" "$service_file"
        systemctl daemon-reload
        systemctl enable --now "${service}.service"
        echo ">> Service wiederhergestellt, aktiviert und gestartet."
    else
        echo ">> Service-File: vorhanden"
        echo "   Pfad:  $service_file"
    fi

    if systemctl is-active --quiet "${service}.service"; then
        local wg_iface wg_ip wg_endpoint wg_handshake
        wg_iface=$(wg show interfaces 2>/dev/null | awk '{print $1}')
        wg_ip=$(ip -4 addr show "$wg_iface" 2>/dev/null | awk '/inet / {print $2}')
        wg_endpoint=$(wg show "$wg_iface" endpoints 2>/dev/null | awk '{print $2}')
        wg_handshake=$(wg show "$wg_iface" latest-handshakes 2>/dev/null | awk '{print $2}')
        echo ">> Service: läuft"
        echo "   Interface:  $wg_iface"
        echo "   Tunnel-IP:  ${wg_ip:-unbekannt}"
        echo "   Endpoint:   ${wg_endpoint:-unbekannt}"
        echo "   Handshake:  $(date -d "@${wg_handshake}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'noch kein Handshake')"
    else
        echo "!! Service: nicht aktiv!"
    fi
}

update_sd() {
    if [ "$BOOT_FROM_NVME" -eq 0 ]; then
        echo "!! --updatesd erfordert NVMe-Boot (Sync läuft NVMe → SD)."
        echo "   Bitte von NVMe booten und erneut ausführen."
        return 1
    fi

    local SD_BOOT_DEV="/dev/mmcblk0p1"
    local SD_ROOT_DEV="/dev/mmcblk0p2"
    local MNT_SD_BTRFS="/mnt/sd-btrfs-root"
    local MNT_SD_BOOT="/mnt/sd-boot"

    # SD-Karte prüfen (vor trap, noch kein Cleanup nötig)
    if [ ! -b "$SD_ROOT_DEV" ]; then
        echo "!! SD-Karte nicht gefunden ($SD_ROOT_DEV) – SD-Update übersprungen."
        echo "   SD einlegen und erneut mit --updatesd ausführen."
        return 1
    fi

    # Cleanup-Funktion – wird bei EXIT oder Fehler ausgeführt
    _cleanup_sd() {
        echo ">> SD-Partitionen werden ausgehängt..."
        umount "$MNT_SD_BOOT"   2>/dev/null || true
        umount "$MNT_SD_BTRFS"  2>/dev/null || true

        # Zusaetzliche Mounts derselben Geraete aushaengen (z.B. Desktop-Automount
        # via udisks2, das beim Einstecken der Karte unabhaengig vom Skript unter
        # /run/media/... mountet) - sonst ist die Karte trotz "SD-Update abgeschlossen"
        # noch belegt und laesst sich nicht sicher entnehmen.
        local dev extra_mnt
        for dev in "$SD_BOOT_DEV" "$SD_ROOT_DEV"; do
            while read -r extra_mnt; do
                [ -n "$extra_mnt" ] && umount "$extra_mnt" 2>/dev/null
            done < <(findmnt -n -o TARGET -S "$dev" 2>/dev/null)
        done
    }
    trap _cleanup_sd EXIT

    mkdir -p "$MNT_SD_BTRFS" "$MNT_SD_BOOT"

    echo ">> SD-Partitionen mounten..."
    mount -o subvolid=5 "$SD_ROOT_DEV" "$MNT_SD_BTRFS"
    mount "$SD_BOOT_DEV" "$MNT_SD_BOOT"

    # NVMe-UUIDs (wir sind auf NVMe, blkid direkt)
    local nvme_boot_uuid nvme_root_uuid
    nvme_boot_uuid=$(blkid -s UUID -o value "$NVME_BOOT_DEV")
    nvme_root_uuid=$(blkid -s UUID -o value "$NVME_ROOT_DEV")

    # Aktives NVMe-Subvolume ermitteln
    local active_subvol
    active_subvol=$(findmnt -n -o OPTIONS / | grep -oP 'subvol=\K[^,\]]+')
    if [ -z "$active_subvol" ]; then
        echo "!! Aktives NVMe-Subvolume nicht ermittelbar – Abbruch."
        return 1
    fi
    echo "   Aktives Subvolume: $active_subvol"

    # Ziel-Subvolume auf SD anlegen falls nicht vorhanden
    local sd_subvol_path="${MNT_SD_BTRFS}/${active_subvol}"
    if [ ! -d "$sd_subvol_path" ]; then
        echo ">> Subvolume ${active_subvol} auf SD anlegen..."
        btrfs subvolume create "$sd_subvol_path"
    else
        echo ">> Subvolume ${active_subvol} auf SD: vorhanden."
    fi

    # @home auf SD anlegen falls nicht vorhanden
    if [ ! -d "${MNT_SD_BTRFS}/@home" ]; then
        echo ">> @home-Subvolume auf SD anlegen..."
        btrfs subvolume create "${MNT_SD_BTRFS}/@home"
    fi

    # --- Platz-Check ---
    echo ""
    echo ">> Platz-Check..."
    local sys_size home_size boot_size total_needed sd_free
    sys_size=$(du -sx \
        --exclude=proc --exclude=sys --exclude=dev --exclude=run \
        --exclude=tmp --exclude=boot --exclude=home --exclude=mnt \
        / 2>/dev/null | awk '{print $1}')
    home_size=$(du -sx \
        --exclude=Pictures --exclude=Videos --exclude=Downloads --exclude=.cache \
        /home/stellarmate 2>/dev/null | awk '{print $1}')
    boot_size=$(du -sx /boot 2>/dev/null | awk '{print $1}')
    total_needed=$(( (sys_size + home_size + boot_size) * 12 / 10 ))  # +20% Puffer

    sd_free=$(df --output=avail "$MNT_SD_BTRFS" | tail -1)

    printf "   System: %4d MiB  |  Home: %4d MiB  |  Boot: %4d MiB\n" \
        "$(( sys_size  / 1024 ))" "$(( home_size / 1024 ))" "$(( boot_size / 1024 ))"
    printf "   Benötigt (inkl. 20%% Puffer): %d MiB  |  SD frei: %d MiB\n" \
        "$(( total_needed / 1024 ))" "$(( sd_free / 1024 ))"

    if [ "$total_needed" -gt "$sd_free" ]; then
        echo "!! Nicht genug Platz auf SD – Abbruch."
        return 1
    fi
    echo "   Platz: OK"

    # --- System-Sync ---
    echo ""
    echo ">> System-Sync NVMe → SD (${active_subvol})..."
    rsync -aHAX --delete --one-file-system \
        --exclude=/proc --exclude=/sys --exclude=/dev --exclude=/run \
        --exclude=/tmp  --exclude=/boot --exclude=/home --exclude=/mnt \
        --exclude=/lost+found \
        --info=progress2 \
        / "${sd_subvol_path}/"
    echo ">> System-Sync: OK"

    # --- Boot-Sync ---
    echo ""
    echo ">> Boot-Sync NVMe → SD..."
    rsync -aH --delete --info=progress2 /boot/ "${MNT_SD_BOOT}/"
    echo ">> Boot-Sync: OK"

    # --- Home-Sync ---
    echo ""
    echo ">> Home-Sync /home/stellarmate → SD..."
    mkdir -p "${MNT_SD_BTRFS}/@home/stellarmate"
    rsync -aHAX --delete \
        --exclude=Pictures --exclude=Videos --exclude=Downloads --exclude=.cache \
        --info=progress2 \
        /home/stellarmate/ "${MNT_SD_BTRFS}/@home/stellarmate/"
    echo ">> Home-Sync: OK"

    # --- cmdline.txt auf SD patchen: NVMe-UUID → LABEL= (Herstellerstandard) ---
    echo ""
    echo ">> SD cmdline.txt patchen..."
    if grep -q "$nvme_root_uuid" "${MNT_SD_BOOT}/cmdline.txt"; then
        sed -i "s|root=UUID=${nvme_root_uuid}|root=LABEL=SM_ROOT|g" "${MNT_SD_BOOT}/cmdline.txt"
        echo "   root=: UUID → LABEL=SM_ROOT  OK"
    else
        echo "   root=: bereits korrekt"
    fi
    if grep -q 'subvol=' "${MNT_SD_BOOT}/cmdline.txt"; then
        sed -i "s|subvol=[^ ,]*|subvol=${active_subvol}|g" "${MNT_SD_BOOT}/cmdline.txt"
        echo "   subvol=: ${active_subvol}  OK"
    fi

    # --- fstab im SD-Subvolume patchen: NVMe-UUIDs → LABEL= (Herstellerstandard) ---
    echo ">> SD fstab patchen..."
    local sd_fstab="${sd_subvol_path}/etc/fstab"
    sed -i \
        "s|UUID=${nvme_boot_uuid}|LABEL=SM_BOOT|g; \
         s|UUID=${nvme_root_uuid}|LABEL=SM_ROOT|g" \
        "$sd_fstab"
    echo "   UUIDs → LABEL=SM_BOOT / LABEL=SM_ROOT  OK"

    # Trap zurücksetzen, dann manuell aufräumen
    trap - EXIT
    _cleanup_sd
    echo ""
    echo ">> SD-Update abgeschlossen."
}

update_nvme_memory() {
    local NVME_BTRFS_MNT="/mnt/nvme-btrfs-root"
    local NVME_HOME="${NVME_BTRFS_MNT}/@home/stellarmate"

    # Prüfen ob von SD gebootet
    if [ "$BOOT_FROM_NVME" -eq 1 ]; then
        echo "!! Nicht von SD gebootet – dieser Befehl ist nur auf SD-Boot sinnvoll."
        return 1
    fi
    echo "   Boot-Quelle: SD  ✓"

    # NVMe prüfen
    if [ ! -b "$NVME_ROOT_DEV" ]; then
        echo "!! NVMe nicht gefunden ($NVME_ROOT_DEV) – Abbruch."
        return 1
    fi

    _cleanup_nvme_mem() {
        echo ">> NVMe aushängen..."
        umount "$NVME_BTRFS_MNT" 2>/dev/null || true
    }
    trap _cleanup_nvme_mem EXIT

    mkdir -p "$NVME_BTRFS_MNT"
    echo ">> NVMe mounten (subvolid=5)..."
    mount -o subvolid=5 "$NVME_ROOT_DEV" "$NVME_BTRFS_MNT"

    if [ ! -d "$NVME_HOME" ]; then
        echo "!! NVMe @home nicht gefunden: $NVME_HOME – Abbruch."
        return 1
    fi

    # Platz-Check
    echo ""
    echo ">> Platz-Check..."
    local mem_size nvme_free
    mem_size=$(du -sx /home/stellarmate/basic-memory /home/stellarmate/.claude 2>/dev/null | awk '{sum += $1} END {print sum}')
    mem_size=$(( mem_size * 12 / 10 ))  # +20% Puffer
    nvme_free=$(df --output=avail "$NVME_BTRFS_MNT" | tail -1)

    printf "   Memory-Daten (inkl. 20%% Puffer): %d KiB  |  NVMe frei: %d MiB\n" \
        "$mem_size" "$(( nvme_free / 1024 ))"

    if [ "$mem_size" -gt "$nvme_free" ]; then
        echo "!! Nicht genug Platz auf NVMe – Abbruch."
        return 1
    fi
    echo "   Platz: OK"

    # basic-memory sync
    echo ""
    echo ">> basic-memory: SD → NVMe..."
    mkdir -p "${NVME_HOME}/basic-memory"
    rsync -aHAX --delete --info=progress2 \
        /home/stellarmate/basic-memory/ \
        "${NVME_HOME}/basic-memory/"
    echo ">> basic-memory: OK"

    # .claude sync
    echo ""
    echo ">> .claude: SD → NVMe..."
    mkdir -p "${NVME_HOME}/.claude"
    rsync -aHAX --delete --info=progress2 \
        /home/stellarmate/.claude/ \
        "${NVME_HOME}/.claude/"
    echo ">> .claude: OK"

    trap - EXIT
    _cleanup_nvme_mem
    echo ""
    echo ">> Memory-Sync abgeschlossen. NVMe ist auf aktuellem Stand."
}

sync_memory() {
    local RCLONE_REMOTE="nextcloud:basic-memory"
    local LOCAL_MEMORY="/home/stellarmate/basic-memory"
    local RCLONE_CONF="/home/stellarmate/.config/rclone/rclone.conf"
    local RCLONE_BACKUP="/home/stellarmate/bin/backup_files/rclone.conf"
    local BISYNC_FLAG=""

    # rclone installieren falls fehlt
    if ! command -v rclone &>/dev/null; then
        echo ">> rclone nicht gefunden – wird installiert..."
        local tmp_conf
        tmp_conf=$(mktemp)
        cat /etc/pacman.conf > "$tmp_conf"
        if ! grep -q '^\[extra\]' "$tmp_conf"; then
            printf '\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n' >> "$tmp_conf"
        fi
        if pacman -Sy --noconfirm --config "$tmp_conf" rclone; then
            echo ">> rclone: installiert."
        else
            echo "!! rclone: Installation fehlgeschlagen – bitte manuell: sudo pacman -S rclone"
            rm -f "$tmp_conf"
            return 1
        fi
        rm -f "$tmp_conf"
    else
        echo ">> rclone: vorhanden."
    fi

    # rclone.conf wiederherstellen falls fehlt
    if [ ! -f "$RCLONE_CONF" ]; then
        if [ -f "$RCLONE_BACKUP" ]; then
            echo ">> rclone.conf fehlt – wird aus Backup wiederhergestellt..."
            mkdir -p "$(dirname "$RCLONE_CONF")"
            cp "$RCLONE_BACKUP" "$RCLONE_CONF"
            chmod 600 "$RCLONE_CONF"
            echo ">> rclone.conf: wiederhergestellt."
        else
            echo "!! rclone.conf fehlt und kein Backup unter $RCLONE_BACKUP"
            echo "   Bitte manuell konfigurieren: rclone config"
            return 1
        fi
    fi

    # Als User "stellarmate" ausfuehren (nicht als root): rclone sucht Config UND
    # bisync-State-Cache relativ zu $HOME. Unter sudo/root waere das /root/... statt
    # /home/stellarmate/... - Config faende sich per --config noch, der bisync-State
    # (~/.cache/rclone/bisync) aber nicht, was einen unnoetigen --resync erzwingen wuerde.
    if ! sudo -u stellarmate rclone lsd "$RCLONE_REMOTE" --max-depth 0 &>/dev/null; then
        echo "!! Nextcloud nicht erreichbar oder Remote 'nextcloud' nicht konfiguriert"
        echo "   Setup: rclone config (WebDAV, https://nextcloud.blue-it.org/remote.php/webdav/, vendor=other)"
        return 1
    fi

    # Beim ersten Lauf --resync setzen (kein bisync-Status vorhanden)
    local bisync_state_dir="/home/stellarmate/.cache/rclone/bisync"
    if [ ! -d "$bisync_state_dir" ] || [ -z "$(ls -A "$bisync_state_dir" 2>/dev/null)" ]; then
        echo "   Erster Lauf – initialer Resync (--resync)"
        BISYNC_FLAG="--resync"
    fi

    echo ">> basic-memory bisync: lokal ↔ Nextcloud ..."
    if sudo -u stellarmate rclone bisync "$LOCAL_MEMORY" "$RCLONE_REMOTE" \
        --size-only \
        --exclude ".obsidian/**" \
        --create-empty-src-dirs \
        $BISYNC_FLAG 2>&1; then
        echo ">> basic-memory: OK"
    else
        echo "!! basic-memory bisync fehlgeschlagen – bitte manuell prüfen"
        return 1
    fi
}

# ===== Hauptprogramm =====

if [ "$SYNC_MEMORY" -eq 1 ]; then
    echo "=== Memory-Sync ↔ Nextcloud ==="
    sync_memory
    exit 0
fi

if [ "$UPDATE_NVME_MEMORY" -eq 1 ]; then
    echo "=== Memory-Sync SD → NVMe ==="
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

echo ""
echo "=== UUID-Fixup ==="
fix_uuids

echo ""
echo "=== NVMe Config-Fixup ==="
fix_nvme_config

echo ""
echo "=== NVMe Label-Rename ==="
rename_nvme_labels

echo ""
echo "=== Extra-Pakete ==="
install_extra_packages

echo ""
echo "=== WireGuard Restore ==="
restore_wireguard

if [ "$UPDATE_SD" -eq 1 ]; then
    echo ""
    echo "=== SD-Update ==="
    update_sd
fi

# Cleanup NVMe-Mounts (falls von SD gebootet)
if [ -n "$NVME_BOOT_TMP" ]; then
    trap - EXIT
    umount "$NVME_BOOT_TMP" 2>/dev/null; rmdir "$NVME_BOOT_TMP" 2>/dev/null || true
    umount "$NVME_ROOT_TMP" 2>/dev/null; rmdir "$NVME_ROOT_TMP" 2>/dev/null || true
fi

echo ""
if [ "$REBOOT_NEEDED" -eq 1 ]; then
    echo "=== Fertig. Reboot erforderlich: sudo reboot ==="
else
    echo "=== Fertig. Kein Reboot nötig. ==="
fi
