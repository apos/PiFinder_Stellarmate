#! /usr/bin/bash
set -euo pipefail

# Builds and installs a patched "indi_lx200generic" binary (the shared
# binary behind "indi_lx200_OnStep" - a symlink, see below) that fixes the
# OnStep/OnStepX mount-type misdetection from issue #227: :GXEM# returns the
# raw numeric OnStep web-interface mount-select value ("1 GEM, 2 EQ Fork, or
# 3 Alt/Azm") on this firmware, but the upstream driver's switch statement
# only recognizes letter codes (A/K/k/E) and silently defaults anything else
# - including '3' - to GEM. See diffs/indi_lx200_OnStep.diff and
# indi_onstep_fix/CMakeLists.txt for details.
#
# This binary is owned by the system "libindi" package, so a plain package
# reinstall/upgrade will overwrite it with the stock (bugged) version again
# - rerun this script afterwards to reapply the fix.

# Usage: bin/build_indi_onstep_fix.sh [--clean-build | --build-only]
# Checked against INDI 2.2.5 (2026-11-28): the diff applies unchanged and the stock driver still reports every mount type of a
# controller answering :GXEM# with 1/2/3 as GEM. A GEM ("1") is therefore right without this fix.

source "$(dirname "$0")/functions.sh"

FIX_DIR="${pifinder_stellarmate_dir}/indi_onstep_fix"
DIFF_FILE="${pifinder_stellarmate_dir}/diffs/indi_lx200_OnStep.diff"
BACKUP_SUFFIX="orig-backup-$(date +%Y-%m-%d)"

# The sources must match the installed libindi (an SMOS update may bring a newer one). INDI_VERSION=vX.Y.Z overrides.
installed_version="$(pacman -Q libindi 2>/dev/null | awk '{print $2}' | cut -d- -f1)"
INDI_VERSION="${INDI_VERSION:-${installed_version:+v${installed_version}}}"
if [[ -z "${INDI_VERSION}" ]]; then
    echo "ERROR: the installed libindi version cannot be told (pacman); pass INDI_VERSION=vX.Y.Z."
    exit 1
fi
echo "-> INDI ${INDI_VERSION} (installed libindi: ${installed_version:-unknown})"
SRC_CACHE_DIR="${FIX_DIR}/build/indi-src-${INDI_VERSION}"
BUILD_DIR="${FIX_DIR}/build/out-${INDI_VERSION}"

if [[ "${1:-}" == "--clean-build" ]]; then
    echo "-> Removing existing source cache and build directory..."
    rm -rf "${SRC_CACHE_DIR}" "${BUILD_DIR}"
fi

if [[ ! -d "${SRC_CACHE_DIR}/.git" ]]; then
    echo "-> Cloning indilib/indi ${INDI_VERSION} (shallow)..."
    rm -rf "${SRC_CACHE_DIR}"
    git clone --depth 1 --branch "${INDI_VERSION}" https://github.com/indilib/indi.git "${SRC_CACHE_DIR}"
fi

echo "-> Applying mount-type fix diff..."
if ! (cd "${SRC_CACHE_DIR}" && patch -p1 --dry-run -N < "${DIFF_FILE}" >/dev/null 2>&1); then
    echo "   Already applied or checkout is dirty - checking if it's already applied cleanly..."
    if ! (cd "${SRC_CACHE_DIR}" && patch -p1 --dry-run -R < "${DIFF_FILE}" >/dev/null 2>&1); then
        echo "ERROR: diff does not apply cleanly (forward or reverse). Investigate ${SRC_CACHE_DIR} manually."
        exit 1
    fi
    echo "   Diff already applied, continuing."
else
    (cd "${SRC_CACHE_DIR}" && patch -p1 -N < "${DIFF_FILE}")
fi

echo "-> Configuring..."
mkdir -p "${BUILD_DIR}"
cmake -S "${FIX_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release -DINDI_SRC_DIR="${SRC_CACHE_DIR}"

echo "-> Building..."
cmake --build "${BUILD_DIR}"

if [[ "${1:-}" == "--build-only" ]]; then
    echo "-> Built: ${BUILD_DIR}/indi_lx200generic (not installed)."
    exit 0
fi

echo "-> Stopping INDI server (if running) to avoid 'Text file busy'..."
active_profile="$(curl -s http://localhost:8624/api/server/status 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0].get("active_profile",""))' 2>/dev/null || true)"
curl -s -X POST http://localhost:8624/api/server/stop >/dev/null 2>&1 || true
sleep 1

echo "-> Backing up and installing driver executable..."
if [[ -f /usr/bin/indi_lx200generic && ! -f "/usr/bin/indi_lx200generic.${BACKUP_SUFFIX}" ]]; then
    sudo cp /usr/bin/indi_lx200generic "/usr/bin/indi_lx200generic.${BACKUP_SUFFIX}"
fi
# Replace atomically (copy next to the target, then rename over it): a plain
# `cp` over a binary that is still executing fails with "Text file busy", and
# something (Web Manager profile autostart, the Control Center's self-heal)
# may respawn the driver between stop_indi_driver_and_wait and this line.
# rename(2) just swaps the directory entry - a running instance keeps its old
# inode until it is restarted.
sudo cp "${BUILD_DIR}/indi_lx200generic" /usr/bin/indi_lx200generic.new
sudo chmod +x /usr/bin/indi_lx200generic.new
sudo mv -f /usr/bin/indi_lx200generic.new /usr/bin/indi_lx200generic

if [[ -n "${active_profile}" ]]; then
    echo "-> Restarting INDI server with profile '${active_profile}'..."
    curl -s -X POST "http://localhost:8624/api/server/start/${active_profile// /%20}" >/dev/null 2>&1 || true
fi

echo ""
echo "Done. indi_lx200_OnStep (symlink to indi_lx200generic) now includes the"
echo "mount-type fix. Verify after reconnecting the mount driver:"
echo "  indi_getprop -h localhost -p 7624 -t 5 \"LX200 OnStep.TELESCOPE_MOUNT_TYPE.*\""
echo ""
echo "To roll back: sudo cp /usr/bin/indi_lx200generic.${BACKUP_SUFFIX} /usr/bin/indi_lx200generic"
