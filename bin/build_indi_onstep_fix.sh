#! /usr/bin/bash
set -euo pipefail

# Builds and installs a patched "indi_lx200generic" binary (the shared
# binary behind "indi_lx200_OnStep" - a symlink, see below) that fixes the
# OnStep/OnStepX mount-type misdetection from issue #227: :GXEM# returns the
# raw numeric OnStep web-interface mount-select value ("1 GEM, 2 EQ Fork, or
# 3 Alt/Azm") on this firmware, but the upstream driver's switch statement
# only recognizes letter codes (A/K/k/E) and silently defaults anything else
# - including '3' - to GEM. See diffs/indi_lx200_OnStep_v2.2.2.diff and
# indi_onstep_fix/CMakeLists.txt for details.
#
# This binary is owned by the system "libindi" package, so a plain package
# reinstall/upgrade will overwrite it with the stock (bugged) version again
# - rerun this script afterwards to reapply the fix.

source "$(dirname "$0")/functions.sh"

INDI_VERSION="v2.2.2"          # must match the installed libindi package version
FIX_DIR="${pifinder_stellarmate_dir}/indi_onstep_fix"
SRC_CACHE_DIR="${FIX_DIR}/build/indi-src"
BUILD_DIR="${FIX_DIR}/build/out"
DIFF_FILE="${pifinder_stellarmate_dir}/diffs/indi_lx200_OnStep_v2.2.2.diff"
BACKUP_SUFFIX="orig-backup-$(date +%Y-%m-%d)"

installed_version="$(pacman -Q libindi 2>/dev/null | awk '{print $2}' | cut -d- -f1)"
if [[ -n "${installed_version}" && "${installed_version}" != "${INDI_VERSION#v}" ]]; then
    echo "WARNING: installed libindi is ${installed_version}, this fix is pinned to ${INDI_VERSION}."
    echo "         Proceeding anyway, but verify the fix still applies/builds cleanly."
fi

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

echo "-> Stopping INDI server (if running) to avoid 'Text file busy'..."
active_profile="$(curl -s http://localhost:8624/api/server/status 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0].get("active_profile",""))' 2>/dev/null || true)"
curl -s -X POST http://localhost:8624/api/server/stop >/dev/null 2>&1 || true
sleep 1

echo "-> Backing up and installing driver executable..."
if [[ -f /usr/bin/indi_lx200generic && ! -f "/usr/bin/indi_lx200generic.${BACKUP_SUFFIX}" ]]; then
    sudo cp /usr/bin/indi_lx200generic "/usr/bin/indi_lx200generic.${BACKUP_SUFFIX}"
fi
sudo cp "${BUILD_DIR}/indi_lx200generic" /usr/bin/indi_lx200generic
sudo chmod +x /usr/bin/indi_lx200generic

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
