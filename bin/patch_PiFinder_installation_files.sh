#!/bin/bash
# Get important functions and paths
source "$(dirname "$0")/functions.sh"

### Checks for Pi-Type (Pi4/Pi5) and OS (Bookworm) and applies patches to PiFinder installation files accordingly
### This script is intended to be run on a Raspberry Pi running Stellarmate with PiFinder installed

# Detect PiFinder version from version.txt
current_pifinder=$(cat "${pifinder_stellarmate_dir}/version.txt" | tr -d '[:space:]')

# Detect current Pi hardware model
hw_model=$(tr -d '\0' < /proc/device-tree/model)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    current_pi="P5"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    current_pi="P4"
else
    current_pi="unknown"
fi

# Detect OS codename (lsb_release on Debian/bookworm, /etc/os-release ID on Arch/SMOS)
current_os=$(lsb_release -sc 2>/dev/null || grep "^ID=" /etc/os-release | cut -d= -f2)

# Helper function to decide whether a patch should apply (safe string splitting)
should_apply_patch() {
    local ok_pifinder="$1"
    local ok_pi="$2"
    local ok_os="$3"

    local match_pifinder="false"
    local match_pi="false"
    local match_os="false"

    # Check PiFinder version
    if [[ "$ok_pifinder" == "general" ]]; then
        match_pifinder="true"
    else
        IFS='|' read -ra vers <<< "$ok_pifinder"
        for v in "${vers[@]}"; do
            [[ "$v" == "$current_pifinder" ]] && match_pifinder="true"
        done
    fi

    # Check Pi model
    if [[ "$ok_pi" == "general" ]]; then
        match_pi="true"
    else
        IFS='|' read -ra pis <<< "$ok_pi"
        for p in "${pis[@]}"; do
            [[ "$p" == "$current_pi" ]] && match_pi="true"
        done
    fi

    # Check OS
    if [[ "$ok_os" == "general" || "$ok_os" == "$current_os" ]]; then
        match_os="true"
    fi

    [[ "$match_pifinder" == "true" && "$match_pi" == "true" && "$match_os" == "true" ]]
}

############################################################
# HELPER Functions
############################################################
show_diff_if_changed() {
    local file="$1"
    local bak="${file}.bak"

    if [[ -f "$file" && -f "$bak" ]] && [[ "$(sha256sum "$file" | awk '{print $1}')" != "$(sha256sum "$bak" | awk '{print $1}')" ]]; then
        echo "🔍 Showing changes for $file:"
        diff --unified "$bak" "$file"
    else
        echo "ℹ️ No changes for $file"
    fi

    rm -f "$bak"
}

############################################################
# MAIN
############################################################

# Copy a new pifinder_setup.sh 
mv "${pifinder_dir}/pifinder_setup.sh" "${pifinder_dir}/pifinder_setup.sh.before.stellarmate"
cp "${pifinder_stellarmate_dir}/pifinder_stellarmate_setup.sh" "${pifinder_dir}/pifinder_setup.sh"
mv "${pifinder_dir}/pifinder_update.sh" "${pifinder_dir}/pifinder_update.sh.before.stellarmate"
cp "${pifinder_stellarmate_dir}/pifinder_update.sh" "${pifinder_dir}/."
mv "${pifinder_dir}/pifinder_post_update.sh" "${pifinder_dir}/pifinder_post_update.sh.before.stellarmate"
cp "${pifinder_stellarmate_dir}/pifinder_post_update.sh" "${pifinder_dir}/."

############################################################
# Check if kstarsrc exists (no symlink needed)
echo "🔍 Checking for ~/.config/kstarsrc ..."
mkdir -p "$pifinder_config_dir"

if [ -f "$kstarsrc_target" ]; then
    echo "✅ Found $kstarsrc_target"
else
    echo "⚠️ $kstarsrc_target not found. Please launch KStars once to create it."
fi


    echo "DEBUG: current_pifinder = $current_pifinder"
    echo "DEBUG: current_pi = $current_pi"
    echo "DEBUG: current_os = $current_os"
    if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
        echo "DEBUG: should_apply_patch returned true for requirements.txt"
    else
        echo "DEBUG: should_apply_patch returned false for requirements.txt"
    fi

echo "------------------------------------"
#######################################################
if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    echo "🔧 Patching Python requirements in $python_requirements ..."
    cp "$python_requirements" "$python_requirements.bak"

    # Ensure additional requirements are appended if not already present
    while IFS= read -r dep; do
        if ! grep -Fxq "$dep" "$python_requirements"; then
            echo "$dep" >> "$python_requirements"
            echo "✅ Added $dep to requirements.txt"
        else
            echo "ℹ️ $dep already present in requirements.txt"
        fi
    done < "$python_requirements_additional"

    show_diff_if_changed "$python_requirements"
    python3 -m py_compile "$python_requirements" 2>/dev/null && echo "✅ Syntax OK" || echo "ℹ️ Text file – no syntax check needed"
echo "------------------------------------"

    # Unpin packages that are incompatible with Python 3.13+/3.14 or numpy 2.0
    # Each sed only acts if the pinned version is still present (idempotent)
    echo "🔧 Unpinning incompatible package versions for Python 3.13+/numpy 2.0 ..."

    # numpy: 1.26.x does not build on Python 3.14; numpy 2.0 removed numpy.float_
    sed -i 's/^numpy==.*/numpy>=2.0/' "$python_requirements" && echo "  ✅ numpy unpinned (>=2.0)"

    # pandas: old pinned version fails to build on Python 3.14
    sed -i 's/^pandas==.*/pandas/' "$python_requirements" && echo "  ✅ pandas unpinned"

    # pillow: unpin for Python 3.14 compatibility
    sed -i 's/^pillow==.*/pillow/' "$python_requirements" && echo "  ✅ pillow unpinned"

    # scikit-learn: old version has build issues
    sed -i 's/^scikit-learn==.*/scikit-learn/' "$python_requirements" && echo "  ✅ scikit-learn unpinned"

    # grpcio: pinned version fails to build on Python 3.14
    sed -i 's/^grpcio==.*/grpcio/' "$python_requirements" && echo "  ✅ grpcio unpinned"

    # protobuf: metaclass incompatibility with Python 3.14
    sed -i 's/^protobuf==.*/protobuf/' "$python_requirements" && echo "  ✅ protobuf unpinned"

    # skyfield: uses numpy.float_ which was removed in numpy 2.0
    sed -i 's/^skyfield==.*/skyfield/' "$python_requirements" && echo "  ✅ skyfield unpinned"

    # bottle: uses cgi module which was removed in Python 3.13
    sed -i 's/^bottle==.*/bottle/' "$python_requirements" && echo "  ✅ bottle unpinned"

    # timezonefinder: requires numpy<2, conflicts with numpy>=2.0
    sed -i 's/^timezonefinder==.*/timezonefinder/' "$python_requirements" && echo "  ✅ timezonefinder unpinned"

    # python-libinput: 0.3.0a0 not available; uses removed 'imp' module (Python 3.12+)
    # Installed manually as 0.1.0 with patched setup.py — must not be in requirements.txt
    sed -i 's/^python-libinput/# python-libinput/' "$python_requirements" && echo "  ✅ python-libinput commented out (installed manually as 0.1.0)"

    show_diff_if_changed "$python_requirements"
    else
        echo "⏩ Skipping requirements.txt patch: ❌ incompatible version/pi/os"
    fi
    echo "------------------------------------"
    ############################################################
    # PiFinder Services – patch dynamic paths from template
echo "🔧 Patching systemd service templates ..."

service_files=(
    "${pifinder_stellarmate_dir}/pi_config_files/pifinder.service"
    "${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service"
)

for service_file in "${service_files[@]}"; do
    cp "$service_file" "$service_file.bak"

    sed -i "s|__PYTHON_EXEC__|${pifinder_dir}/python/.venv/bin/python|g" "$service_file"
    sed -i "s|__PIFINDER_USER__|${USER}|g" "$service_file"
    sed -i "s|__PIFINDER_STELLARMATE_DIR__|${pifinder_stellarmate_dir}|g" "$service_file"

        echo "✅ Patched placeholders in $service_file"

    done

    echo "------------------------------------"

    

    

    

    ######################################################

    # config.json and default_config.json – set gps_type to gpsd (we do not use ublox, only stellarmate/KStars GPS)
echo "🔧 Updating gps_type in config files ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    for cfg in "$config_default_json" "$config_json"; do
        echo "🔍 Patching $cfg ..."
        cp "$cfg" "$cfg.bak"
        if grep -q '"gps_type": "ublox"' "$cfg"; then
            sed -i 's|"gps_type": "ublox"|"gps_type": "stellarmate"|' "$cfg"
            echo "✅ Replaced 'ublox' with 'stellarmate' in $cfg"
        elif grep -q '"gps_type": "gpsd"' "$cfg"; then
            sed -i 's|"gps_type": "gpsd"|"gps_type": "stellarmate"|' "$cfg"
            echo "✅ Replaced 'gpsd' with 'stellarmate' in $cfg"
        else
            echo "ℹ️ No 'ublox' or 'gpsd' GPS type found to replace in $cfg"
        fi
        show_diff_if_changed "$cfg"
    done
else
    echo "⏩ Skipping gps_type patch in config files: ❌ incompatible version/pi/os"
fi
echo "------------------------------------"

############################################################
# Copy gps_stellarmate.py module
echo "🔧 Copying Stellarmate GPS module..."
cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_dir}/python/PiFinder/"
echo "✅ Copied gps_stellarmate.py"

# Ensure __init__.py exists in the python directory for package recognition
if [ ! -f "${pifinder_dir}/python/__init__.py" ]; then
    touch "${pifinder_dir}/python/__init__.py"
    echo "✅ Created empty __init__.py in ${pifinder_dir}/python/"
else
        echo "ℹ️ __init__.py already exists in ${pifinder_dir}/python/"
    fi
    echo "------------------------------------"
    
    #######################################
    # Patch displays.py for Pi5 SPI GPIO
echo "🔧 Updating displays.py for Pi5 SPI compatibility ..."
cp "$display_py" "$display_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0" "P5" "bookworm"; then
    if ! grep -q 'from luma.core.interface.serial import noop' "$display_py"; then
        sed -i '1i from luma.core.interface.serial import noop' "$display_py"
        echo "✅ Import für noop hinzugefügt"
    fi

    sed -i 's|serial = spi(device=0, port=0, |serial = spi(gpio=noop(), device=0, port=10, |' "$display_py"
    echo "✅ Patched all 'serial = spi(...)' calls for Pi5"
else
    echo "⏩ Skipping patch for displays.py: ✅ not required on Pi4 + Bookworm"
fi

show_diff_if_changed "$display_py"
python3 -m py_compile "$display_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

#######################################
# Patch keyboard_pi.py for Pi 5
echo "🔧 Updating keyboard_pi.py for Pi5 GPIO compatibility ..."
cp "$keyboard_py" "$keyboard_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0" "P5" "bookworm"; then
    if grep -q 'import RPi.GPIO as GPIO' "$keyboard_py"; then
        sed -i '/import RPi.GPIO as GPIO/i\
import types\n\
GPIO = types.SimpleNamespace()\n\
GPIO.IN = None\n\
GPIO.OUT = None\n\
GPIO.PUD_UP = None\n\
GPIO.BCM = None\n\
GPIO.setmode = lambda mode: None\n\
GPIO.setup = lambda pin, mode, pull_up_down=None, initial=None: None\n\
GPIO.input = lambda pin: False\n\
GPIO.LOW = 0\n\
GPIO.HIGH = 1\n\
GPIO_STUB_FOR_PI5 = True\n' "$keyboard_py"
        sed -i '/import RPi.GPIO as GPIO/d' "$keyboard_py"
        echo "✅ GPIO stub inserted and import removed for Pi5"
    else
        echo "ℹ️ GPIO stub already present in keyboard_pi.py"
    fi
else
    echo "⏩ Skipping patch for keyboard_pi.py: ✅ not required on Pi4 + Bookworm"
fi

show_diff_if_changed "$keyboard_py"
python3 -m py_compile "$keyboard_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"



########################################
# Raspberry Pi 4
#########################################

echo "------------------------------------"
#######################################
# Patch solver.py

echo "🔧 Updating solver.py ..."
cp "$solver_py" "$solver_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    if grep -q 'sys.path.append(str(utils.tetra3_dir))' "$solver_py"; then
        sed -i 's|sys.path.append(str(utils.tetra3_dir))|sys.path.append(str(utils.tetra3_dir.parent))|' "$solver_py"
    fi

    if grep -q '^import tetra3$' "$solver_py"; then
        sed -i 's|^import tetra3$|from tetra3 import main|' "$solver_py"
        sed -i 's|tetra3\.Tetra3|main.Tetra3|' "$solver_py"
        sed -i 's|tetra3\.get_centroids_from_image|main.get_centroids_from_image|g' "$solver_py"
    fi

    if ! grep -q "from tetra3 import cedar_detect_client" "$solver_py"; then
        sed -i '/from tetra3 import main/a from tetra3 import cedar_detect_client' "$solver_py"
    fi


else
    echo "⏩ Skipping patch for solver.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$solver_py"
python3 -m py_compile "$solver_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"



#######################################
# Fix Tetra3 at various places
echo "🔧 Updating __init__.py ..."
cp "$init_py" "$init_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    if grep -q 'from .tetra3 import Tetra3' "$init_py"; then
        sed -i 's|from .tetra3 import Tetra3|from .main import Tetra3|' "$init_py"
    fi
else
    echo "⏩ Skipping patch for __init__.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$init_py"
python3 -m py_compile "$init_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

echo "🔧 Updating cedar_detect_client.py ..."
cp "$client_py" "$client_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    if grep -q 'from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc' "$client_py"; then
        sed -i 's|from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc|from . import cedar_detect_pb2, cedar_detect_pb2_grpc|' "$client_py"
    fi
else
    echo "⏩ Skipping patch for cedar_detect_client.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$client_py"
python3 -m py_compile "$client_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

echo "🔧 Updating cedar_detect_pb2_grpc.py ..."
cp "$grpc_py" "$grpc_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    if grep -q '^import cedar_detect_pb2 as cedar__detect__pb2$' "$grpc_py"; then
        sed -i 's|^import cedar_detect_pb2 as cedar__detect__pb2$|from . import cedar_detect_pb2 as cedar__detect__pb2|' "$grpc_py"
    fi
else
    echo "⏩ Skipping patch for cedar_detect_pb2_grpc.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$grpc_py"

python3 -m py_compile "$grpc_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

echo "------------------------------------"





echo "📄 Checking for tetra3.py -> main.py rename ..."
if [ -f "${t3_dir}/tetra3.py" ]; then
    mv "${t3_dir}/tetra3.py" "${t3_dir}/main.py"
    echo "✅ Renamed tetra3.py → main.py"
else
    echo "ℹ️ File tetra3.py already renamed or does not exist"
fi
echo "------------------------------------"



#######################################
# Patch ui/marking_menus.py
echo "🔧 Updating ui/marking_menus.py ..."
cp "$ui_file" "$ui_file.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    if grep -q '^from dataclasses import dataclass$' "$ui_file"; then
        sed -i 's|^from dataclasses import dataclass$|from dataclasses import dataclass, field|' "$ui_file"
    fi
    if grep -q 'up: MarkingMenuOption = MarkingMenuOption(label="HELP")' "$ui_file"; then
        sed -i 's|up: MarkingMenuOption = MarkingMenuOption(label="HELP")|up: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP"))|' "$ui_file"
    fi
else
    echo "⏩ Skipping patch for ui/marking_menus.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$ui_file"
python3 -m py_compile "$ui_file" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"



#######################################
# Patch camera.py

echo "🔧 Updating camera_pi.py ..."
cp "$camera_file" "$camera_file.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    camera_insert="from picamera2 import Picamera"
    if ! grep -q "$camera_insert" "$camera_file"; then
        awk -v insert="$camera_insert" '
        /^import numpy as np$/ {
            print;
            print insert;
            next
        }
        { print }
        ' "$camera_file.bak" > "$camera_file"
    fi
else
    echo "⏩ Skipping patch for camera_pi.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$camera_file"
python3 -m py_compile "$camera_file" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"



##################################################
# PiFinder  main.py

echo "🔧 Updating main.py ..."
cp "$main_py" "$main_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

    patch -N "$main_py" < "${pifinder_stellarmate_dir}/diffs/main_py.diff"
show_diff_if_changed "$main_py"
python3 -m py_compile "$main_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

##################################################
# PiFinder server.py
server_py="${pifinder_dir}/python/PiFinder/server.py"
echo "🔧 Updating server.py ..."
cp "$server_py" "$server_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    # Replace hardcoded 'pifinder' with dynamic username in login function
    sed -i "s|sys_utils.verify_password(\"pifinder\", password)|sys_utils.verify_password(\"$(whoami)\", password)|" "$server_py"
    # Replace hardcoded 'pifinder' with dynamic username in password_change function
    sed -i "s|sys_utils.change_password(\"pifinder\", current_password, new_passworda)|sys_utils.change_password(\"$(whoami)\", current_password, new_passworda)|" "$server_py"
else
    echo "⏩ Skipping patch for server.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$server_py"
python3 -m py_compile "$server_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

##################################################
# PiFinder index.tpl
echo "🔧 Updating index.tpl ..."
cp "$index_tpl" "$index_tpl.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

    patch -N "$index_tpl" < "${pifinder_stellarmate_dir}/diffs/index_tpl.diff"
show_diff_if_changed "$index_tpl"
echo "------------------------------------"

##################################################
# PiFinder header.tpl
echo "🔧 Updating header.tpl ..."
cp "$header_tpl" "$header_tpl.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

    patch -N "$header_tpl" < "${pifinder_stellarmate_dir}/diffs/header_tpl.diff"
show_diff_if_changed "$header_tpl"
echo "------------------------------------"

# #####################################################
# menu_structure.py
echo "🔧 Updating menu_structure.py ..."
cp "$menu_py" "$menu_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.3.0|2.5.1" "P4|P5" "general"; then
    patch -N "$menu_py" < "${pifinder_stellarmate_dir}/diffs/menu_structure_py.diff"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

############################################################
# SMOS (Arch Linux) specific patches
############################################################

#######################################
# Patch keyboard_pi.py for SMOS (python-libinput 0.1.0 API)
echo "🔧 Updating keyboard_pi.py for SMOS (python-libinput 0.1.0 API) ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "general" "P4|P5" "arch"; then
    cp "$keyboard_py" "$keyboard_py.bak"
    if grep -q 'context_type=libinput.ContextType.UDEV' "$keyboard_py"; then
        patch -N "$keyboard_py" < "${pifinder_stellarmate_dir}/diffs/keyboard_pi_smos.diff"
        echo "✅ Patched keyboard_pi.py for python-libinput 0.1.0"
    else
        echo "ℹ️ keyboard_pi.py already patched or pattern not found"
    fi
    show_diff_if_changed "$keyboard_py"
    python3 -m py_compile "$keyboard_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
else
    echo "⏩ Skipping keyboard_pi.py SMOS patch: not on Arch Linux"
fi
echo "------------------------------------"

#######################################
# Patch picamera2 drm_preview.py for SMOS (pykms not available on Arch)
echo "🔧 Patching picamera2 drm_preview.py for SMOS (no pykms) ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "general" "P4|P5" "arch"; then
    # Use find instead of Python import (import fails without pykms)
    drm_preview_py=$(find "${python_venv}" -name "drm_preview.py" 2>/dev/null | head -1)
    if [ -n "$drm_preview_py" ]; then
        if grep -q '_pykms_available' "$drm_preview_py"; then
            echo "ℹ️ drm_preview.py already patched"
        else
            cp "$drm_preview_py" "$drm_preview_py.bak"
            patch -N "$drm_preview_py" < "${pifinder_stellarmate_dir}/diffs/drm_preview_smos.diff"
            echo "✅ Patched drm_preview.py for missing pykms"
            show_diff_if_changed "$drm_preview_py"
        fi
    else
        echo "⚠️ picamera2 not installed in venv, skipping drm_preview.py patch"
    fi
else
    echo "⏩ Skipping drm_preview.py patch: not on Arch Linux"
fi
echo "------------------------------------"

#######################################
# Patch skyfield starlib.py for numpy 2.0 (isnan on object dtype)
echo "🔧 Patching skyfield starlib.py for numpy 2.0 compatibility ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "general" "P4|P5" "arch"; then
    starlib_py=$(find "${python_venv}" -name "starlib.py" -path "*/skyfield/*" 2>/dev/null | head -1)
    if [ -n "$starlib_py" ]; then
        if grep -q "numpy 2.0" "$starlib_py"; then
            echo "ℹ️ starlib.py already patched"
        else
            cp "$starlib_py" "$starlib_py.bak"
            patch -N "$starlib_py" < "${pifinder_stellarmate_dir}/diffs/starlib_numpy2_smos.diff"
            echo "✅ Patched starlib.py for numpy 2.0"
            show_diff_if_changed "$starlib_py"
        fi
    else
        echo "⚠️ skyfield not installed in venv, skipping starlib.py patch"
    fi
else
    echo "⏩ Skipping starlib.py patch: not on Arch Linux"
fi
echo "------------------------------------"

# catalogs.py — background loader: os.nice(15), smaller batches, longer yield
echo "🔧 Patching catalogs.py (background loader CPU throttling) ..."
if [ -f "$catalogs_py" ]; then
    cp "$catalogs_py" "$catalogs_py.bak"
    patch -N "$catalogs_py" < "${pifinder_stellarmate_dir}/diffs/catalogs_py.diff"
    echo "✅ Patched catalogs.py (os.nice + yield_time)"
    show_diff_if_changed "$catalogs_py"
else
    echo "⚠️ catalogs.py not found, skipping"
fi
echo "------------------------------------"

