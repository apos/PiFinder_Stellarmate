#!/bin/bash

### Checks for Pi-Type (Pi4/Pi5) and OS (Bookworm) and applies patches to PiFinder installation files accordingly
### This script is intended to be run on a Raspberry Pi running Stellarmate with PiFinder installed

# go to main working dir
cd /home/pifinder

# Get im portant functions and paths
source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh

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

# Detect OS codename
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
mv ${pifinder_dir}/pifinder_setup.sh ${pifinder_dir}/pifinder_setup.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_stellarmate_setup.sh ${pifinder_dir}/pifinder_setup.sh
mv ${pifinder_dir}/pifinder_update.sh ${pifinder_dir}/pifinder_update.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_update.sh ${pifinder_dir}/.
mv ${pifinder_dir}/pifinder_post_update.sh ${pifinder_dir}/pifinder_post_update.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_post_update.sh ${pifinder_dir}/.

############################################################
# Ensure kstarsrc symlink exists for PiFinder user 
echo "🔗 Ensuring ~/.config/kstarsrc symlink for PiFinder ..."
mkdir -p "$pifinder_config_dir"

if [ -L "$kstarsrc_target" ]; then
    echo "ℹ️ Symlink already exists: $kstarsrc_target"
elif [ -e "$kstarsrc_target" ]; then
    echo "⚠️ $kstarsrc_target exists but is not a symlink. Please resolve manually."
else
    ln -s "$kstarsrc_source" "$kstarsrc_target"
    echo "✅ Symlink created: $kstarsrc_target → $kstarsrc_source"
fi

############################################################
# PiFinder Service
# Copy over services
cp -r ${pifinder_stellarmate_dir}/pi_config_files ${pifinder_dir}/.

python_file="${pifinder_dir}/pi_config_files/pifinder.service"
comment_out_line_content="ExecStart=/usr/bin/python"
commented_line="/home/pifinder/PiFinder/python/.venv/bin/python"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    sed -i 's|/usr/bin/python|/home/pifinder/PiFinder/python/.venv/bin/python|' "${python_file}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


python_file="${pifinder_dir}/pi_config_files/pifinder_splash.service"
comment_out_line_content="/usr/bin/python"
commented_line="/home/pifinder/PiFinder/python/.venv/bin/python"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    sed -i 's|/usr/bin/python|/home/pifinder/PiFinder/python/.venv/bin/python|' "${python_file}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi

############################################################
# KStars location service
# Kopieren nach systemd
sudo cp /home/pifinder/PiFinder_Stellarmate/pi_config_files/pifinder_kstars_location_writer.service /etc/systemd/system/

# Aktivieren beim Boot
sudo systemctl enable pifinder_kstars_location_writer.service

# Starten (sofort)
sudo systemctl start pifinder_kstars_location_writer.service

# Status prüfen
systemctl status pifinder_kstars_location_writer.service


#######################################
# pifinder_post_update.sh
echo "🔧 Updating pifinder_post_update.sh ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
cp "$post_update_file" "$post_update_file.bak"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    insert_block="python3 -m venv /home/pifinder/PiFinder/python/.venv\nsource /home/pifinder/PiFinder/python/.venv/bin/activate"
    if ! grep -q "/home/pifinder/PiFinder/python/.venv/bin/activate" "$post_update_file"; then
        awk -v insert="$insert_block" '
        /git submodule update --init --recursive/ {
            print;
            print insert;
            next
        }
        { print }
        ' "$post_update_file.bak" > "$post_update_file"
    fi
else
    echo "⏩ Skipping patch for pifinder_post_update.sh: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$post_update_file"



######################################################
# config.json and default_config.json – set gps_type to gpsd (we do not use ublox, only stellarmate/KStars GPS)
echo "🔧 Updating gps_type in config files ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    for cfg in "$config_default_json" "$config_json"; do
        echo "🔍 Patching $cfg ..."
        cp "$cfg" "$cfg.bak"
        if grep -q '"gps_type": "ublox"' "$cfg"; then
            sed -i 's|"gps_type": "ublox"|"gps_type": "gpsd"|' "$cfg"
            echo "✅ Replaced 'ublox' with 'gpsd' in $cfg"
        else
            echo "ℹ️ No 'ublox' GPS type found in $cfg"
        fi
        show_diff_if_changed "$cfg"
    done
else
    echo "⏩ Skipping gps_type patch in config files: ❌ incompatible version/pi/os"
fi

#######################################
# Patch displays.py for Pi5 SPI GPIO
echo "🔧 Updating displays.py for Pi5 SPI compatibility ..."
cp "$display_py" "$display_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P5" "bookworm"; then
    if ! grep -q 'from luma.core.interface.serial import noop' "$display_py"; then
        sed -i '1i from luma.core.interface.serial import noop' "$display_py"
        echo "✅ Import für noop hinzugefügt"
    fi

    sed -i 's|serial = spi(device=0, port=0, |serial = spi(gpio=noop(), device=0, port=10, |' "$display_py"
    echo "✅ Patched all 'serial = spi(...)' calls for Pi5"
else
    echo "⏩ Skipping patch for displays.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$display_py"
python3 -m py_compile "$display_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

#######################################
# Patch keyboard_pi.py for Pi 5
echo "🔧 Updating keyboard_pi.py for Pi5 GPIO compatibility ..."
cp "$keyboard_py" "$keyboard_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P5" "bookworm"; then
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
    echo "⏩ Skipping patch for keyboard_pi.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$keyboard_py"
python3 -m py_compile "$keyboard_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

#######################################
# Patch keyboard_pi.py for Pi 5
echo "🔧 Updating keyboard_pi.py for Pi5 GPIO compatibility ..."
cp "$keyboard_py" "$keyboard_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P5" "bookworm"; then
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
    echo "⏩ Skipping patch for keyboard_pi.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$keyboard_py"
python3 -m py_compile "$keyboard_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"


########################################
# Raspberry Pi 4
#########################################

#######################################
# Patch solver.py

echo "🔧 Updating solver.py ..."
cp "$solver_py" "$solver_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q 'sys.path.append(str(utils.tetra3_dir))' "$solver_py"; then
        sed -i 's|sys.path.append(str(utils.tetra3_dir))|sys.path.append(str(utils.tetra3_dir.parent))|' "$solver_py"
    fi

    if grep -q '^import tetra3$' "$solver_py"; then
        sed -i 's|^import tetra3$|from tetra3 import main|' "$solver_py"
    fi

    if ! grep -q "from tetra3 import cedar_detect_client" "$solver_py"; then
        sed -i '/from tetra3 import main/a from tetra3 import cedar_detect_client' "$solver_py"
    fi

    sed -i 's|from tetra3 import main|import tetra3.main as main|' "$solver_py"
    sed -i 's|tetra3\.Tetra3|main.Tetra3|' "$solver_py"
else
    echo "⏩ Skipping patch for solver.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$solver_py"
python3 -m py_compile "$solver_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"



#######################################
# Fix Tetra3 at various places
echo "🔧 Updating __init__.py ..."
cp "$init_py" "$init_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q 'from .tetra3 import Tetra3' "$init_py"; then
        sed -i 's|from .tetra3 import Tetra3|from .main import Tetra3|' "$init_py"
    fi
else
    echo "⏩ Skipping patch for __init__.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$init_py"
python3 -m py_compile "$init_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

echo "🔧 Updating cedar_detect_client.py ..."
cp "$client_py" "$client_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q 'from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc' "$client_py"; then
        sed -i 's|from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc|from . import cedar_detect_pb2, cedar_detect_pb2_grpc|' "$client_py"
    fi
else
    echo "⏩ Skipping patch for cedar_detect_client.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$client_py"
python3 -m py_compile "$client_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

echo "🔧 Updating cedar_detect_pb2_grpc.py ..."
cp "$grpc_py" "$grpc_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q '^import cedar_detect_pb2 as cedar__detect__pb2$' "$grpc_py"; then
        sed -i 's|^import cedar_detect_pb2 as cedar__detect__pb2$|from . import cedar_detect_pb2 as cedar__detect__pb2|' "$grpc_py"
    fi
else
    echo "⏩ Skipping patch for cedar_detect_pb2_grpc.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$grpc_py"
python3 -m py_compile "$grpc_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"


echo "📄 Checking for tetra3.py -> main.py rename ..."
if [ -f "${t3_dir}/tetra3.py" ]; then
    mv "${t3_dir}/tetra3.py" "${t3_dir}/main.py"
    echo "✅ Renamed tetra3.py → main.py"
else
    echo "ℹ️ File tetra3.py already renamed or does not exist"
fi



#######################################
# Patch ui/marking_menus.py
echo "🔧 Updating ui/marking_menus.py ..."
cp "$ui_file" "$ui_file.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
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



#######################################
# Patch camera.py

echo "🔧 Updating camera_pi.py ..."
cp "$camera_file" "$camera_file.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
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



##################################################
#  PiFinder  main.py

echo "🔧 Updating main.py ..."
cp "$main_py" "$main_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q 'gps_content\["lat"\] \+ gps_content\["lon"\] != 0' "$main_py"; then
        sed -i 's|gps_content\["lat"\] \+ gps_content\["lon"\] != 0|gps_content["lat"] != 0.0 or gps_content["lon"] != 0.0|' "$main_py"
        echo "✅ GPS-Kondition gepatcht in main.py"
    fi

    if ! grep -q 'from PiFinder import gps_gpsd as gps_monitor' "$main_py"; then
        sed -i '/from PiFinder.multiproclogging import MultiprocLogging/a from PiFinder import gps_gpsd as gps_monitor' "$main_py"
        echo "✅ Import von gps_gpsd als gps_monitor eingefügt"
    else
        echo "ℹ️ Import gps_gpsd bereits vorhanden"
    fi
else
    echo "⏩ Skipping patch for main.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$main_py"
python3 -m py_compile "$main_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"


######################################################
# gps_gpsd.py

echo "🔧 Updating gps_gpsd.py for KStars-only support ..."
cp "$gps_py" "$gps_py.bak"
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"

if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    if grep -q 'KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"' "$gps_py"; then
        echo "ℹ️ gps_gpsd.py already contains KStars GPS block"
    else
        # Remove previous gps_main and gps_monitor implementations
        sed -i '/^async def gps_main/,/^def gps_monitor/ d' "$gps_py"
        sed -i '/^# To run the GPS monitor/,/^$/d' "$gps_py"
        sed -i '/^async def read_kstars_location_file/,/^EOF/ d' "$gps_py"

        # Append KStars-only implementation
        cat <<'EOF' >> "$gps_py"

import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

async def read_kstars_location_file(gps_queue):
    logger.info("KStars reader started (gps_gpsd.py)")
    last_line = ""
    while True:
        try:
            if os.path.exists(KSTARS_LOCATION_FILE):
                with open(KSTARS_LOCATION_FILE, "r") as f:
                    line = f.readline().strip()
                    if not line or line == last_line or line.startswith("ERROR"):
                        await asyncio.sleep(5)
                        continue

                    parts = line.split(",")
                    if len(parts) >= 6:
                        lat = float(parts[2])
                        lon = float(parts[3])
                        alt = float(parts[4])
                        time_utc = parts[5]

                        msg = (
                            "fix",
                            {
                                "lat": lat,
                                "lon": lon,
                                "altitude": alt,
                                "source": "KStars",
                                "lock": True,
                                "error_in_m": 10,
                            },
                        )

                        parsed_time = datetime.fromisoformat(time_utc)
                        time_msg = ("time", {"time": parsed_time})

                        gps_queue.put(msg)
                        gps_queue.put(time_msg)

                        logger.info(f"KStars GPS fix injected: {msg}")
                        last_line = line
        except Exception as e:
            logger.warning(f"KStars GPS reader error: {e}")
        await asyncio.sleep(5)

async def gps_main(gps_queue, console_queue, log_queue):
    MultiprocLogging.configurer(log_queue)
    logger.info("GPS main started – using ONLY KStars")

    try:
        await read_kstars_location_file(gps_queue)
    except Exception as e:
        logger.error(f"Error in GPS monitor: {e}")
        await asyncio.sleep(5)

def gps_monitor(gps_queue, console_queue, log_queue):
    asyncio.run(gps_main(gps_queue, console_queue, log_queue))
EOF

        echo "✅ gps_gpsd.py patched with KStars-only GPS logic"
    fi
else
    echo "⏩ Skipping patch for gps_gpsd.py: ❌ incompatible version/pi/os"
fi

show_diff_if_changed "$gps_py"
python3 -m py_compile "$gps_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"


# #####################################################
# menu_structure.py (patching menu blocks individually with version checks)
cp "$menu_py" "$menu_py.bak"

# ---- Remove "GPS Status" block ----
echo "🔧 Removing 'GPS Status' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    gps_status_line=$(grep -n '"name": "GPS Status"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$gps_status_line" ]]; then
        start=$((gps_status_line - 1))
        end=$((gps_status_line + 20))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed GPS Status block and cleaned up Align section"
    else
        echo "ℹ️ No GPS Status block found"
    fi
else
    echo "⏩ Skipping patch for 'GPS Status': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

# ---- Remove "Place & Time" block ----
echo "🔧 Removing 'Place & Time' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    place_line=$(grep -n '"name": "Place & Time"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$place_line" ]]; then
        start=$((place_line - 1))
        end=$((place_line + 20))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed 'Place & Time' block from Tools menu"
    else
        echo "ℹ️ No 'Place & Time' block found"
    fi
else
    echo "⏩ Skipping patch for 'Place & Time': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

# ---- Remove "UBlox" item from GPS Type menu ----
echo "🔧 Removing 'UBlox' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    ublox_line=$(grep -n '"name": "UBlox"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$ublox_line" ]]; then
        start=$((ublox_line - 1))
        end=$((ublox_line + 2))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed 'UBlox' item from GPS Type menu"
    else
        echo "ℹ️ No 'UBlox' entry found in GPS Type menu"
    fi
else
    echo "⏩ Skipping patch for 'UBlox': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

# ---- Remove "WiFi Mode" block ----
echo "🔧 Removing 'WiFi Mode' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    wifi_line=$(grep -n '"name": "WiFi Mode"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$wifi_line" ]]; then
        start=$((wifi_line - 1))
        end=$((wifi_line + 16))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed 'WiFi Mode' block from menu_structure.py"
    else
        echo "ℹ️ No 'WiFi Mode' block found"
    fi
else
    echo "⏩ Skipping patch for 'WiFi Mode': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

# ---- Remove "GPS Type" block ----
echo "🔧 Removing 'GPS Type' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    gps_type_line=$(grep -n '"name": "GPS Type"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$gps_type_line" ]]; then
        start=$((gps_type_line - 1))
        end=$((gps_type_line + 12))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed 'GPS Type' block from menu_structure.py"
    else
        echo "ℹ️ No 'GPS Type' block found"
    fi
else
    echo "⏩ Skipping patch for 'GPS Type': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"

# ---- Remove "Software Upd" entry ----
echo "🔧 Removing 'Software Upd' from menu_structure.py ..."
echo "➡️ Detected Version Combo: $current_pifinder / $current_pi / $current_os"
if should_apply_patch "2.2.0" "P4|P5" "bookworm"; then
    line=$(grep -n '"name": "Software Upd"' "$menu_py" | cut -d: -f1 | head -n1)
    if [[ -n "$line" ]]; then
        start=$((line))
        end=$((line))
        sed -i "${start},${end}d" "$menu_py"
        echo "✅ Removed 'Software Upd' block (lines ${start}-${end})"
    else
        echo "ℹ️  No 'Software Upd' entry found (maybe already removed)"
    fi
else
    echo "⏩ Skipping patch for 'Software Upd': ❌ incompatible version/pi/os"
fi
show_diff_if_changed "$menu_py"
python3 -m py_compile "$menu_py" && echo "✅ Syntax OK" || echo "❌ Syntax ERROR due to patch"
