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

# Detect OS codenameTh
current_os=$(lsb_release -sc)

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
    if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
        echo "DEBUG: should_apply_patch returned true for requirements.txt"
    else
        echo "DEBUG: should_apply_patch returned false for requirements.txt"
    fi

echo "------------------------------------"
#######################################################
if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

    # Upgrade scikit-learn to the latest version to avoid build issues on Bookworm
    echo "🔧 Upgrading scikit-learn version in $python_requirements ..."
    sed -i 's/scikit-learn==1.2.2/scikit-learn/' "$python_requirements"
        echo "✅ Changed scikit-learn to latest version."
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
    if grep -q 'sys.path.append(str(utils.tetra3_dir))' "$solver_py"; then
        sed -i 's|sys.path.append(str(utils.tetra3_dir))|sys.path.append(str(utils.tetra3_dir.parent))|' "$solver_py"
    fi

    if grep -q '^import tetra3$' "$solver_py"; then
        sed -i 's|^import tetra3$|from tetra3 import main|' "$solver_py"
        sed -i 's|tetra3\.Tetra3|main.Tetra3|' "$solver_py"
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
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

# Patch GPS type handling in main.py
if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
    STELLARMATE_GPS_LINE_1='        elif gps_type == "stellarmate":'
    STELLARMATE_GPS_LINE_2='            gps_monitor = importlib.import_module("PiFinder.gps_stellarmate")'
    if ! grep -qF "$STELLARMATE_GPS_LINE_1" "$main_py"; then
        echo "🔧 Patching GPS type handling in $main_py"
        sed -i "/gps_monitor = importlib.import_module(\"PiFinder.gps_ubx\")/a \\${STELLARMATE_GPS_LINE_1}\\n\\${STELLARMATE_GPS_LINE_2}" "$main_py"
        echo "✅ Successfully added 'stellarmate' GPS type handling in $main_py"
    else
        echo "ℹ️ 'stellarmate' GPS type handling already present in main.py – skipping"
    fi
else
    echo "⏩ Skipping GPS type patch in main.py: ❌ incompatible version/pi/os"
fi

if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
    # Check for the new condition first to make the script idempotent
    if grep -q 'gps_content\["lat"\] != 0.0 or gps_content\["lon"\] != 0.0' "$main_py"; then
        echo "ℹ️ GPS condition already patched in main.py – skipping"
    else
        # If new condition not found, check for old and replace
        if grep -q 'gps_content\["lat"\] + gps_content\["lon"\] != 0' "$main_py"; then
            sed -i 's/gps_content\["lat"\] + gps_content\["lon"\] != 0/gps_content["lat"] != 0.0 or gps_content["lon"] != 0.0/' "$main_py"
            echo "✅ GPS condition patched in main.py"
        else
            echo "ℹ️ Could not find old GPS condition to patch in main.py"
        fi
    fi
else
    echo "⏩ Skipping patch for main.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$main_py"
python3 -m py_compile "$main_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
echo "------------------------------------"

# #####################################################
# menu_structure.py (overwrite with known-good version)
cp "$menu_py" "$menu_py.bak"
echo "🔧 Updating menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.3.0" "P4|P5" "bookworm"; then
    if grep -q '"value": "stellarmate"' "$menu_py"; then
        echo "ℹ️ 'Stellarmate' GPS option already present in menu_structure.py – skipping"
    else
        cp "/home/stellarmate/PiFinder_BAK/python/PiFinder/ui/menu_structure.py" "$menu_py"
        echo "✅ Successfully overwrote menu_structure.py with known-good version."
    fi
else
    echo "⏩ Skipping overwrite for menu_structure.py: ❌ incompatible version/pi/os"
fi

