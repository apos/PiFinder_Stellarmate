#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

# This script is known to work with
pifinder_stellarmate_version_stable="2.6.0"

# This script is actually tested against this version
pifinder_stellarmate_version_testing="2.6.0"

# StellarMate OS version this script was tested with (rolling release — changes matter!)
smos_version_stable="2.2.1"
smos_version_testing="2.2.1"


############################################################
# MAIN
############################################################

# --action=reinstall|update|cancel: drive the existing-install menu and the
# venv bootstrap non-interactively (used by gui_installer/server.py). Without
# it, behavior is unchanged — the script still prompts on a terminal.
ACTION=""
for arg in "$@"; do
    case "$arg" in
        --action=*)
            ACTION="${arg#--action=}"
            ;;
    esac
done

# Captured once, up front: the script itself does `cd "${pifinder_home}"` etc.
# further down, which permanently changes this process's cwd. The automated
# re-execs below rely on `$(pwd)` (via `source $(pwd)/bin/functions.sh`) being
# the repo root again, so they must `cd` back here first.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SETUP_START=$SECONDS

############################################################
# Get some important vars and functinons
source $(pwd)/bin/functions.sh

# Define a lock file for resuming the script after venv activation
lock_file="${pifinder_stellarmate_dir}/.resume_from_venv"

# Warnings file — persists across both runs for final summary
warnings_file="${pifinder_stellarmate_dir}/.setup_warnings"

# Clear warnings on first run (no lock file = first run)
[ ! -f "$lock_file" ] && > "$warnings_file"

# Helper: add a critical warning (shown in final summary)
add_warning() {
    echo "  ⚠️  $1"
    echo "$1" >> "$warnings_file"
}

# Machine-readable phase marker for gui_installer/server.py's progress bar.
# Because the venv bootstrap re-execs this whole script from the top (see
# below), phases 1-4 print again on the second pass — the GUI tracks the
# furthest phase reached so far rather than the latest one, so that's harmless.
phase() {
    echo "###PHASE### $1"
}

# Source python venv if it exists
if [ -f "${python_venv}/bin/activate" ]; then
    source "${python_venv}/bin/activate"
fi

phase "Checking versions"

############################################################
# VERSION CHECK (Live check from GitHub)

# Read local PiFinder version
pifinder_local_version=$(cat "$(pwd)/version.txt" 2>/dev/null)

# Fetch online version from GitHub (release branch)
github_version=$(curl -s https://raw.githubusercontent.com/brickbots/PiFinder/release/version.txt | tr -d '\r')

echo "ℹ️  Local PiFinder version: $pifinder_local_version"
echo "ℹ️  GitHub PiFinder version: $github_version"

# Function to compare versions (returns 1 if $1 > $2)
version_gt() {
    [ "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1" ]
}

# Function to compare versions (returns 0 if equal)
version_eq() {
    [ "$1" = "$2" ]
}

# Main check
if version_eq "$github_version" "$pifinder_stellarmate_version_stable"; then
    echo "✅ PiFinder version $github_version matches STABLE version. Proceeding..."
elif version_gt "$github_version" "$pifinder_stellarmate_version_stable"; then
    echo "⚠️  Actual PiFinder version in Git-main ($github_version) is NEWER than tested version ($pifinder_stellarmate_version_stable)."
    echo "⚠️  Proceed only if you are testing new features."
    read -p "⚠️⚠️⚠️  Continue with installation? (yes/no): " confirm
    confirm="${confirm//[$'\r\n']}"
    if [[ "$confirm" != "yes" ]]; then
        echo "ℹ️  Installation cancelled by user."
        exit 0
    fi

    # Optional: Warn again if version is even newer than "testing"
    if version_gt "$github_version" "$pifinder_stellarmate_version_testing"; then
        echo "❌ GitHub version $github_version is NEWER than the last defined TESTING version $pifinder_stellarmate_version_testing."
        echo "❌ This might break your current test configuration."
        echo "❌❌❌ Exiting to prevent unintended test mismatches."
        exit 1
    fi
else
    echo "❌ PiFinder version $github_version is not supported by this Stellarmate patch script."
    echo "❌ Expected STABLE: $pifinder_stellarmate_version_stable or TESTING: $pifinder_stellarmate_version_testing"
    exit 1
fi

echo "$pifinder_stellarmate_version_stable" > "$(pwd)/version.txt"

############################################################
# SMOS VERSION CHECK

current_smos_version=$(curl -s http://localhost:8624/api/info/version 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null)

if [ -z "$current_smos_version" ]; then
    echo "⚠️  SMOS version could not be determined (API not reachable). Proceeding anyway."
elif version_eq "$current_smos_version" "$smos_version_stable"; then
    echo "✅ SMOS version $current_smos_version matches tested STABLE version. Proceeding..."
elif version_gt "$current_smos_version" "$smos_version_stable"; then
    echo "⚠️  SMOS $current_smos_version is NEWER than tested version ($smos_version_stable)."
    echo "⚠️  Arch is rolling release — package versions may differ. Proceed with caution."
    read -p "⚠️⚠️⚠️  Continue anyway? (yes/no): " confirm_smos
    confirm_smos="${confirm_smos//[$'\r\n']}"
    if [[ "$confirm_smos" != "yes" ]]; then
        echo "ℹ️  Installation cancelled by user."
        exit 0
    fi
else
    echo "⚠️  SMOS $current_smos_version is OLDER than tested version ($smos_version_stable). Proceeding anyway."
fi

############################################################
phase "Setting up hardware access"

echo "ℹ️ INFO: running as user <<$(whoami)>> – assuming this is the correct Stellarmate setup user."

# Create hardware groups if missing (Arch/SMOS does not create these by default)
for grp in spi gpio i2c kmem input; do
    getent group "$grp" > /dev/null 2>&1 || sudo groupadd "$grp"
done

# Add rights accessing hardware to user
sudo usermod -a -G spi,gpio,i2c,video,kmem,input ${USER}

# udev rule for /dev/gpiomem access (Arch Linux)
echo 'SUBSYSTEM=="gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpiomem.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change /dev/gpiomem

sudo chown -R ${USER}:${USER} ${pifinder_stellarmate_dir}

############################################################
phase "Cloning or updating PiFinder"

# Check if a PiFinder installation already exists.
if [ -d "${pifinder_home}/PiFinder" ]; then
    # If resuming, skip the prompt
    if [ -f "$lock_file" ] && is_venv_active "${python_venv}"; then
        echo "✅ Resuming installation after virtual environment activation."
    else
        echo "⚠️  An existing PiFinder installation was found at ${pifinder_home}/PiFinder."
        echo "❓ Please choose an action:"
        echo "   1. Delete the existing installation and reinstall from scratch."
        echo "   2. Update the existing installation with 'git reset --hard origin/release'."
        echo "   3. Cancel the installation."

        case "$ACTION" in
            reinstall) choice="1" ;;
            update)    choice="2" ;;
            cancel)    choice="3" ;;
            "")
                read -p "Enter your choice (1, 2, or 3): " choice
                choice="${choice//[$'\r\n']}"
                ;;
            *)
                echo "❌ Unknown --action='$ACTION' (expected reinstall|update|cancel)."
                exit 1
                ;;
        esac

        case "$choice" in
            1)
                sudo systemctl stop pifinder
                echo "🗑️  Deleting the existing PiFinder installation directory..."
                sudo rm -rf "${pifinder_home}/PiFinder"
                sleep 2 # Give some time for the deletion to complete
                if [ -d "${pifinder_home}/PiFinder" ]; then
                    echo "❌ ERROR: The PiFinder folder still exists after deletion. Aborting setup."
                    exit 1
                fi
                echo "Installation from scratch ..."
                cd "${pifinder_home}"
                git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
                find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/first_steps.html" "${pifinder_home}/PiFinder/python/views/"
                ;;
            2)
                sudo systemctl stop pifinder
                echo "🔄 Updating the existing installation with 'git reset --hard origin/release'..."
                cd "${pifinder_home}/PiFinder"
                git reset --hard origin/release
                git pull
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/first_steps.html" "${pifinder_home}/PiFinder/python/views/"
                ;;
            3)
                echo "ℹ️  Installation cancelled by user."
                exit 0
                ;;
            *)
                echo "❌ Invalid choice. Please run the script again and select 1, 2, or 3."
                exit 1
                ;;
        esac
    fi
else
    echo "🚀 No existing installation found. Starting fresh..."
    cd "${pifinder_home}"
    git clone --recursive --branch release https://github.com/brickbots/PiFinder.git
    sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
    echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
    bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
fi

phase "Installing system packages"

# Arch/SMOS: add core, extra, alarm repos if missing (pacman.conf resets after reboot)
grep -q "^\[core\]" /etc/pacman.conf || printf '\n[core]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/core\n\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n\n[alarm]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/alarm\n' | sudo tee -a /etc/pacman.conf > /dev/null
sudo pacman -Sy --noconfirm

# Install system package requirements (Arch/SMOS)
# libcamera 0.7.1+ uses pybind11 smart_holder — incompatible with picamera2 from pip.
# python-libcamera must stay at 0.7.0 — use cached package if available, then pin.
sudo pacman -S --noconfirm --needed \
    git python-pip python-virtualenv libcap \
    openexr
# libcamera + libcamera-ipa are pre-installed by SMOS — only install if missing.
# Never upgrade: repo may carry a newer pkgrel with incompatible soname (SMOS packaging bug:
# libcamera 0.7.1-64 breaks libcamera-ipa 0.7.1-1 soname dependency).
if ! pacman -Q libcamera &>/dev/null || ! pacman -Q libcamera-ipa &>/dev/null; then
    sudo pacman -S --noconfirm libcamera libcamera-ipa
    echo "  ✅ libcamera installed"
else
    echo "  ℹ️  libcamera $(pacman -Q libcamera | awk '{print $2}') already present (SMOS base)"
fi
# Prefer pinned package from repo, fall back to pacman cache
PYLIBCAM_PKG=$(ls "${pifinder_stellarmate_dir}/packages/python-libcamera-0.7.0-"*"-aarch64.pkg.tar.xz" 2>/dev/null | head -1)
[ -z "$PYLIBCAM_PKG" ] && PYLIBCAM_PKG=$(ls /var/cache/pacman/pkg/python-libcamera-0.7.0-*-aarch64.pkg.tar.xz 2>/dev/null | head -1)
if [ -n "$PYLIBCAM_PKG" ]; then
    echo "ℹ️  Installing python-libcamera 0.7.0 from cache (smart_holder fix) ..."
    sudo pacman -U --noconfirm "$PYLIBCAM_PKG"
    PYLIBCAM_METHOD="pinned 0.7.0 from $(basename $PYLIBCAM_PKG)"
else
    add_warning "python-libcamera 0.7.0 not found — installed current version. Camera may fail (smart_holder)!"
    sudo pacman -S --noconfirm --needed python-libcamera
    PYLIBCAM_METHOD="current version (UNPINNED — may cause smart_holder error!)"
fi
grep -q "IgnorePkg.*python-libcamera" /etc/pacman.conf || \
    sudo sed -i '/^\[options\]/a IgnorePkg = python-libcamera' /etc/pacman.conf

# Risiko 1: libcamera Major-Version prüfen — python-libcamera 0.7.0 ist nur für 0.7.x kompatibel
LIBCAM_VER=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
LIBCAM_MAJOR=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1)
if [ -n "$LIBCAM_MAJOR" ] && [ "$LIBCAM_MAJOR" -gt 0 ] 2>/dev/null; then
    add_warning "libcamera $LIBCAM_VER detected — python-libcamera 0.7.0 may be incompatible! Update packages/ in SM repo if camera fails."
else
    echo "ℹ️  libcamera version $LIBCAM_VER — compatible with python-libcamera 0.7.0"
fi




#########################################################################
# Make some Changes to the downloaded local installation files of PiFinder 
cd ${pifinder_home}/PiFinder

# Replace patched service files with the correct Stellarmate versions
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service ${pifinder_home}/PiFinder/pi_config_files/pifinder.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service ${pifinder_home}/PiFinder/pi_config_files/pifinder_splash.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service ${pifinder_home}/PiFinder/pi_config_files/pifinder-setup.service

############################################
# Create swapfile BEFORE pip install — pip builds (numpy, pandas, picamera2)
# consume huge amounts of RAM and will kill the system without swap on Pi4
if [ ! -f /swapfile ]; then
    echo "🔧 Creating 2GB swapfile (btrfs-compatible, needed before pip install) ..."
    sudo touch /swapfile
    sudo chattr +C /swapfile 2>/dev/null || true
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap defaults 0 0" | sudo tee -a /etc/fstab
    echo "✅ Swapfile ready."
else
    # Ensure swap is active even if file exists (e.g. after reboot without fstab)
    swapon --show | grep -q /swapfile || sudo swapon /swapfile 2>/dev/null || true
    echo "ℹ️  Swapfile already exists and active."
fi

phase "Creating Python venv"

############################################
# Python version check: delete venv if system Python changed (e.g. after SMOS update)
if [ -f "${python_venv}/bin/python" ]; then
    venv_ver=$("${python_venv}/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    sys_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ -n "$venv_ver" ] && [ "$venv_ver" != "$sys_ver" ]; then
        echo "⚠️  Python version mismatch: venv=$venv_ver, system=$sys_ver — deleting venv for rebuild."
        rm -rf "${python_venv}"
    else
        echo "ℹ️  Python version OK: venv=$venv_ver, system=$sys_ver"
    fi
fi

############################################
# Create an activate3 VENV

# Check if venv is active and install requirements
if ! is_venv_active "${python_venv}"; then
  echo "Python venv is not active."

  # Check if venv directory exists
  if ! check_venv_exists "${python_venv}"; then
    echo "Python venv directory does not exist."
    # Create venv
    if create_venv "${python_venv}"; then
      touch "${lock_file}"
      if [ -n "$ACTION" ]; then
        echo "🔁 Virtual environment created — re-executing inside it automatically ..."
        cd "$SCRIPT_DIR"
        exec bash -c "source '${python_venv}/bin/activate' && exec '$0' \"\$@\"" -- "$@"
      fi
      echo " "
      echo "##### STOP ##########################################################"
      echo "##### DO NOT CLOSE THIS TERMINAL !!! MANUAL INPUT REQUIRED !!! ######"
      echo "The Python virtual environment was successfully created and MUST be activated manually."
      echo "Please run the following command in this terminal to activate the virtual environment."
      echo "Then rerun the scipt from within the new virtual environment (you see somthing like (.venv) after activation:"
      echo ""
      echo "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"
      echo "source ${python_venv}/bin/activate"
      echo "./pifinder_stellarmate_setup.sh"
      echo ""
      # Exit the script, because venv must be activated   manually for Requirements installation
      exit 1
    else
      echo "Error creating Python venv. Aborting."
      exit 1
    fi
  else
    if [ -n "$ACTION" ]; then
      echo "🔁 Virtual environment directory exists but isn't active — re-executing inside it automatically ..."
      cd "$SCRIPT_DIR"
      exec bash -c "source '${python_venv}/bin/activate' && exec '$0' \"\$@\"" -- "$@"
    fi
    echo -e "STOP: Python venv directory exists. Please activate the venv manually with:\n vvvvvvvv"
    echo "source ${python_venv}/bin/activate"
    echo -e "\nTHEN: run the script again to install the Requirements."
    exit 1 # Exit script because venv must be activated manually for Requirements installation
  fi
else
  # Venv seems active, but let's double-check if the directory is actually there
  if ! check_venv_exists "${python_venv}"; then
    if [ -n "$ACTION" ]; then
      # Happens when the top-of-script `source .venv/bin/activate` picked up a
      # venv that a reinstall then deleted+recreated later in this same run —
      # $VIRTUAL_ENV is now stale. Drop it and re-exec cleanly so the script
      # re-detects the (missing) venv and goes through the normal create path.
      echo "🔁 Stale venv reference (directory was removed) — re-executing cleanly ..."
      cd "$SCRIPT_DIR"
      exec env -u VIRTUAL_ENV bash "$0" "$@"
    fi
    echo "###################################################################"
    echo "WARNING: Your shell thinks a virtual environment is active,"
    echo "but the directory has been removed (likely during reinstallation)."
    echo "Please run 'deactivate' and then re-run this setup script."
    echo "###################################################################"
    exit 1
  else
    # Clean up the lock file if it exists, as we are now proceeding
    rm -f "${lock_file}"
    phase "Installing Python requirements"
    echo "Python venv is active. Installing Requirements."
    install_requirements "${python_requirements}"
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete

    # Install python-libinput 0.1.0 manually (0.3.0a0 unavailable; setup.py uses removed 'imp')
    echo "🔧 Installing python-libinput 0.1.0 (patched for Python 3.12+) ..."
    LIBINPUT_TMP=$(mktemp -d)
    curl -sL https://files.pythonhosted.org/packages/source/p/python-libinput/python-libinput-0.1.0.tar.gz \
        -o "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz"
    tar xzf "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz" -C "${LIBINPUT_TMP}"
    # Patch setup.py: replace removed 'imp' module with importlib.util
    sed -i 's/from imp import load_source/import importlib.util\ndef load_source(name, path):\n    spec = importlib.util.spec_from_file_location(name, path)\n    mod = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(mod)\n    return mod/' \
        "${LIBINPUT_TMP}/python-libinput-0.1.0/setup.py"
    nice -n 15 ionice -c 3 pip install "${LIBINPUT_TMP}/python-libinput-0.1.0/"
    rm -rf "${LIBINPUT_TMP}"
    echo "✅ python-libinput 0.1.0 installed."

    # Patch skyfield starlib.py for numpy 2.0 compatibility (Risiko 3)
    echo "🔧 Patching skyfield starlib.py for numpy 2.0 compatibility ..."
    SKYFIELD_VER=$("${python_venv}/bin/python" -c "import skyfield; print(skyfield.__version__)" 2>/dev/null || echo "unknown")
    STARLIB_PY=$(find "${python_venv}" -name "starlib.py" -path "*/skyfield/*" 2>/dev/null | head -1)
    if [ -n "$STARLIB_PY" ]; then
        if grep -q "numpy 2.0" "$STARLIB_PY"; then
            echo "  ℹ️  starlib.py already patched (skyfield $SKYFIELD_VER)"
        else
            patch -N "$STARLIB_PY" < "${pifinder_stellarmate_dir}/diffs/starlib_numpy2_smos.diff" && \
                echo "  ✅ starlib.py patched for skyfield $SKYFIELD_VER" || \
                add_warning "starlib.py patch FAILED for skyfield $SKYFIELD_VER — update diffs/starlib_numpy2_smos.diff! Star charts may crash."
        fi
    else
        echo "  ⚠️  skyfield not found in venv — skipping"
    fi

    # Patch picamera2 drm_preview.py (pykms not available on Arch) (Risiko 2)
    echo "🔧 Applying drm_preview.py patch post pip-install ..."
    PICAM_VER=$("${python_venv}/bin/python" -c "import importlib.metadata; print(importlib.metadata.version('picamera2'))" 2>/dev/null || echo "unknown")
    DRM_PY=$(find "${python_venv}" -name "drm_preview.py" 2>/dev/null | head -1)
    if [ -n "$DRM_PY" ]; then
        if grep -q "_pykms_available" "$DRM_PY"; then
            echo "  ℹ️  drm_preview.py already patched (picamera2 $PICAM_VER)"
        else
            patch -N "$DRM_PY" < "${pifinder_stellarmate_dir}/diffs/drm_preview_smos.diff" && \
                echo "  ✅ drm_preview.py patched for picamera2 $PICAM_VER" || \
                add_warning "drm_preview.py patch FAILED for picamera2 $PICAM_VER — update diffs/drm_preview_smos.diff! Camera import will fail."
        fi
    else
        echo "  ⚠️  picamera2 not found in venv — skipping"
    fi

    # Pi5: lgpio C-Bibliothek + rpi-lgpio (RPi.GPIO Drop-in für Pi5 RP1-GPIO)
    hw_model_setup=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
    if echo "$hw_model_setup" | grep -q "Raspberry Pi 5"; then
        echo "🔧 [Pi5] lgpio / rpi-lgpio Setup ..."

        # swig installieren (Builddep für lgpio Python-Bindings)
        if ! command -v swig &>/dev/null; then
            echo "  Installing swig ..."
            sudo pacman -S --noconfirm swig 2>/dev/null && echo "  ✅ swig installed." || echo "  ⚠️  swig install failed — lgpio Python bindings may not build."
        fi

        # lgpio-Quellcode clonen falls nicht vorhanden
        LGPIO_SRC="${pifinder_home}/lgpio-src"
        if [ ! -d "$LGPIO_SRC" ]; then
            echo "  Cloning lgpio source to $LGPIO_SRC ..."
            git clone --depth=1 https://github.com/joan2937/lg "$LGPIO_SRC" \
                && echo "  ✅ lgpio source cloned." \
                || add_warning "[Pi5] lgpio clone failed — GPIO will not work! Retry: git clone https://github.com/joan2937/lg $LGPIO_SRC"
        else
            echo "  ✅ lgpio source: already present ($LGPIO_SRC)"
        fi

        # liblgpio.so bauen und installieren
        if [ ! -f /usr/local/lib/liblgpio.so ]; then
            echo "  Building liblgpio.so ..."
            make -C "$LGPIO_SRC" -s && sudo make -C "$LGPIO_SRC" install -s && sudo ldconfig \
                && echo "  ✅ liblgpio.so built and installed." \
                || add_warning "[Pi5] liblgpio.so build failed — GPIO will not work!"
        else
            echo "  ✅ liblgpio.so: already installed."
        fi

        # rpi-lgpio + lgpio aus lokalem packages/ installieren
        echo "  Installing rpi-lgpio + lgpio ..."
        LGPIO_WHL=$(ls "${pifinder_stellarmate_dir}/packages/lgpio-"*.whl 2>/dev/null | head -1)
        if [ -n "$LGPIO_WHL" ]; then
            pip install --quiet --no-index \
                --find-links="${pifinder_stellarmate_dir}/packages/" \
                rpi-lgpio lgpio \
                && echo "  ✅ rpi-lgpio installed from packages/." \
                || add_warning "[Pi5] rpi-lgpio install from packages/ failed."
        else
            pip install --quiet rpi-lgpio \
                && echo "  ✅ rpi-lgpio installed from PyPI." \
                || add_warning "[Pi5] rpi-lgpio install failed — GPIO will not work!"
        fi
    fi
  fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder

# NOT USED, PART OF STELLARMATE-OS: samba samba-common-bin dnsmasq hostapd dhcpd gpsd
# NOT USED, PART OF STELLARMATE-OS: Setup GPSD
# NOT USED, PART OF STELLARMATE-OS: sudo dpkg-reconfigure -plow gpsd
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/gpsd.conf /etc/default/gpsd

# data dirs
mkdir -p ~/PiFinder_data
mkdir -p ~/PiFinder_data/captures
mkdir -p ~/PiFinder_data/obslists
mkdir -p ~/PiFinder_data/screenshots
mkdir -p ~/PiFinder_data/solver_debug_dumps
mkdir -p ~/PiFinder_data/logs
chmod -R 777 ~/PiFinder_data

phase "Downloading star catalog"

# Hipparcos catalog — check file exists AND is non-empty (>1MB)
HIP_DAT="${pifinder_dir}/astro_data/hip_main.dat"
HIP_MIN_SIZE=1000000
if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
    echo "ℹ️  hip_main.dat already installed"
else
    [ -f "$HIP_DAT" ] && rm -f "$HIP_DAT"  # remove empty/partial file
    echo "🔧 Downloading Hipparcos catalog..."
    HIP_URLS=(
        "https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://vizier.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://cdsarc.u-strasbg.fr/ftp/cats/I/239/hip_main.dat"
    )
    HIP_OK=false
    HIP_METHOD="not downloaded"
    for url in "${HIP_URLS[@]}"; do
        echo "  Trying: $url"
        wget -q --timeout=30 -L -O "$HIP_DAT" "$url" 2>/dev/null
        if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
            echo "✅ hip_main.dat downloaded from $url"
            HIP_OK=true
            HIP_METHOD="downloaded from $url"
            break
        else
            rm -f "$HIP_DAT"
        fi
    done
    if [ "$HIP_OK" = false ]; then
        # Last resort: use bundled compressed copy from the SM repo
        HIP_GZ="${pifinder_stellarmate_dir}/src_pifinder/astro_data/hip_main.dat.gz"
        if [ -f "$HIP_GZ" ]; then
            echo "ℹ️  Using bundled hip_main.dat.gz from PiFinder_Stellarmate repo ..."
            gunzip -c "$HIP_GZ" > "$HIP_DAT"
            echo "✅ hip_main.dat extracted from bundled copy ($(stat -c%s "$HIP_DAT") bytes)"
            HIP_OK=true
            HIP_METHOD="extracted from bundled src_pifinder/astro_data/hip_main.dat.gz"
        else
            add_warning "hip_main.dat not available — star charts will fail! Retry: wget -O ${HIP_DAT} https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
            HIP_METHOD="FAILED — not available!"
        fi
    fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder


###########################
# Not used: tf already installed (also service)
###########################

# Wifi config
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.* /etc
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.conf.sta /etc/dhcpcd.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dnsmasq.conf /etc/dnsmasq.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/hostapd.conf /etc/hostapd/hostapd.conf
# NOT USED, PART OF STELLARMATE-OS: echo -n "Client" > ~/PiFinder/wifi_status.txt
# NOT USED, PART OF STELLARMATE-OS: sudo systemctl unmask hostapd

# NOT USED, PART OF STELLARMATE-OS:  open permissisons on wpa_supplicant file so we can adjust network config
# NOT USED, PART OF STELLARMATE-OS:  sudo chmod 666 /etc/wpa_supplicant/wpa_supplicant.conf

# NOT USED, PART OF STELLARMATE-OS:  Samba config
# NOT USED, PART OF STELLARMATE-OS:  sudo cp ~/PiFinder/pi_config_files/smb.conf /etc/samba/smb.conf

phase "Configuring hardware & services"

if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo "❌ config.txt nicht gefunden!"; exit 1
fi

echo "🔧 Ensuring required config.txt entries are present ..."

# Tracks whether this run actually changed /boot/config.txt - the only thing
# in this script that needs a real reboot (Pi firmware overlays are only
# applied at boot). Everything else (code, services, INDI drivers) is already
# restarted live by the end of this script.
CONFIG_CHANGED=false

# Add a line globally if not already present anywhere in config.txt
add_if_missing() {
    local line="$1"
    if ! grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Added: $line"
        CONFIG_CHANGED=true
    else
        echo "ℹ️  Already present: $line"
    fi
}

# Add a line inside a specific [section] block; creates section if missing.
# Lines are only added once per section (idempotent).
add_to_section() {
    local section="$1"
    local line="$2"
    # Check if line already exists anywhere in file (avoid duplicates across sections)
    if grep -Fxq "$line" "$CONFIG_FILE"; then
        echo "ℹ️  Already present: $line"
        return
    fi
    # Insert section header + line if section missing, else append after last line of section
    if ! grep -Fxq "[$section]" "$CONFIG_FILE"; then
        printf '\n[%s]\n%s\n' "$section" "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "✅ Created [$section] and added: $line"
    else
        # Append line after the section header
        sudo sed -i "/^\[$section\]/a $line" "$CONFIG_FILE"
        echo "✅ Added to [$section]: $line"
    fi
    CONFIG_CHANGED=true
}

# Global entries (apply to all Pi models)
add_if_missing "dtparam=spi=on"
add_if_missing "dtparam=i2c_arm=on"

# Detect Pi model for model-specific overlays
hw_model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    # Pi5: PWM on GPIO13 (ALT0), imx296
    # ACHTUNG: dtoverlay=uart3 auf Pi5/RP1 belegt GPIO9 (UART3-RX) = SPI0-MISO → SPI-Konflikt!
    # Auf Pi4/BCM2711 ist uart3 auf GPIO4/5 → kein Konflikt.
    # TODO Pi5 GPS-Dongle/UBLOX: SPI-freie UART-Pins auf RP1 ermitteln und hier eintragen.
    add_to_section "pi5" "dtparam=i2c_arm_baudrate=10000"
    add_to_section "pi5" "dtoverlay=pwm,pin=13,func=4"
    add_to_section "pi5" "dtoverlay=pwm-2chan"
    add_to_section "pi5" "dtoverlay=imx296"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    # Pi4: PWM on GPIO13 (ALT0), uart3, imx296 — NO pwm-2chan (would override to GPIO19)
    add_to_section "pi4" "dtparam=i2c_arm_baudrate=10000"
    add_to_section "pi4" "dtoverlay=pwm,pin=13,func=4"
    add_to_section "pi4" "dtoverlay=uart3"
    add_to_section "pi4" "dtoverlay=imx296"
fi

echo "✅ config.txt checks complete."

# Swapfile is created earlier (before pip install) — see above



# System-Fixes anwenden (WirePlumber, Gruppen, PWM, Swap etc.)
echo "🔧 Running pifinder_pre_start.sh to apply system fixes ..."
sudo bash "${pifinder_stellarmate_bin}/pifinder_pre_start.sh" "${USER}"
echo "✅ System fixes applied"

# Enable service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service /etc/systemd/system/pifinder.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service /etc/systemd/system/pifinder_splash.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service /etc/systemd/system/pifinder-setup.service

sudo systemctl daemon-reexec
sudo systemctl daemon-reload

sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash
sudo systemctl enable pifinder-setup

echo "🔧 Starting PiFinder services ..."
sudo systemctl start pifinder-setup
sudo systemctl start pifinder
sudo systemctl start pifinder_splash

phase "Building INDI drivers"

# Build and install the PiFinder INDI drivers (PiFinder LX200 + Mount Bridge).
# See Readme_PiFinder_LX200.md for what these do and how to use them.
echo "🔧 Building and installing PiFinder INDI drivers ..."

# Stop any already-running instance first, or installing the new binary fails
# with "Text file busy". Try a graceful Web Manager stop, then make sure via pkill
# regardless of whether the server was started through the Web Manager or manually.
if curl -s -o /dev/null http://localhost:8624/api/server/status 2>/dev/null; then
    curl -s -X POST http://localhost:8624/api/server/stop >/dev/null 2>&1 || true
fi
pkill -f indi_pifinder_lx200 2>/dev/null || true
pkill -f indi_pifinder_mount_bridge 2>/dev/null || true
sleep 1

bash "${pifinder_stellarmate_bin}/build_indi_driver.sh" \
    && echo "✅ PiFinder LX200 driver installed." \
    || add_warning "PiFinder LX200 INDI driver build/install FAILED — run bin/build_indi_driver.sh manually to see why."

bash "${pifinder_stellarmate_bin}/build_indi_bridge.sh" \
    && echo "✅ PiFinder Mount Bridge driver installed." \
    || add_warning "PiFinder Mount Bridge INDI driver build/install FAILED — run bin/build_indi_bridge.sh manually to see why."

# The StellarMate Web Manager caches its driver catalog at its own process
# startup - restart it so newly built/updated drivers show up. Requires a
# GUI/VNC user session; skip quietly if unavailable (e.g. run over plain SSH).
if systemctl --user restart stellarmatewebmanager.service 2>/dev/null; then
    echo "✅ StellarMate Web Manager restarted — INDI driver catalog is up to date."
else
    add_warning "Could not restart stellarmatewebmanager.service (no GUI/VNC session?). Restart it manually so the PiFinder INDI drivers show up in its catalog: systemctl --user restart stellarmatewebmanager.service"
fi

# Detect Pi and OS versions for the final summary message
hw_model=$(tr -d '\0' < /proc/device-tree/model)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    current_pi="Pi 5"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    current_pi="Pi 4"
else
    current_pi="Unknown Pi"
fi
current_os=$(lsb_release -sc 2>/dev/null || grep "^ID=" /etc/os-release | cut -d= -f2)

LIBCAM_FULL=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}')
PYLIBCAM_FULL=$(pacman -Q python-libcamera 2>/dev/null | awk '{print $2}')
PICAM_FULL=$("${python_venv}/bin/python" -c "import importlib.metadata; print(importlib.metadata.version('picamera2'))" 2>/dev/null || echo "unknown")
SKYFIELD_FULL=$("${python_venv}/bin/python" -c "import skyfield; print(skyfield.__version__)" 2>/dev/null || echo "unknown")
NUMPY_FULL=$("${python_venv}/bin/python" -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "unknown")
PYTHON_FULL=$("${python_venv}/bin/python" --version 2>&1 | awk '{print $2}')

echo ""
echo "##############################################"
echo "  PiFinder Setup — Installation Summary"
echo "##############################################"
echo "  PiFinder:             $github_version"
echo "  SM Scripts:           $pifinder_local_version"
echo "  SMOS:                 ${current_smos_version:-unknown}  [tested: $smos_version_stable]"
echo "  Hardware:             $current_pi"
echo "  OS:                   $current_os"
echo "  Python (venv):        $PYTHON_FULL"
echo "  numpy:                $NUMPY_FULL"
echo "  skyfield:             $SKYFIELD_FULL"
echo "  picamera2:            $PICAM_FULL"
echo "  libcamera:            $LIBCAM_FULL"
echo "  python-libcamera:     $PYLIBCAM_FULL  [${PYLIBCAM_METHOD:-pinned}]"
echo "  hip_main.dat:         ${HIP_METHOD:-already present}"
_elapsed=$(( SECONDS - SETUP_START ))
echo "  Setup time:           $(( _elapsed / 60 ))m $(( _elapsed % 60 ))s"
echo "##############################################"

if [ -f "$warnings_file" ] && [ -s "$warnings_file" ]; then
    echo ""
    echo "  ⚠️  CRITICAL WARNINGS — ACTION REQUIRED:"
    echo "##############################################"
    while IFS= read -r line; do
        echo "  ❌ $line"
    done < "$warnings_file"
    echo "##############################################"
    echo "  PiFinder may not work correctly until"
    echo "  the above issues are resolved."
else
    echo "  ✅ No critical warnings — setup completed cleanly."
fi
echo "##############################################"
echo ""
if [ "$CONFIG_CHANGED" = true ]; then
    echo "###REBOOT_NEEDED### true"
    echo "  ➡️  /boot/config.txt was changed — please reboot now to activate it:"
    echo "     sudo reboot"
else
    echo "###REBOOT_NEEDED### false"
    echo "  ✅ No reboot needed — /boot/config.txt was already up to date."
    echo "     (Services, INDI drivers, and code were already restarted live.)"
fi
echo "##############################################"
rm -f "$warnings_file"

phase "Setup complete"
