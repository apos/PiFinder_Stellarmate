#!/bin/bash

cd /home/pifinder

source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh


############################################################
# ALTER FILES
############################################################

# Copy pifinder_setup and update

mv ${pifinder_dir}/pifinder_setup.sh ${pifinder_dir}/pifinder_setup.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_stellarmate_setup.sh ${pifinder_dir}/pifinder_setup.sh
mv ${pifinder_dir}/pifinder_update.sh ${pifinder_dir}/pifinder_update.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_update.sh ${pifinder_dir}/.
mv ${pifinder_dir}/pifinder_post_update.sh ${pifinder_dir}/pifinder_post_update.sh.before.stellarmate
cp ${pifinder_stellarmate_dir}/pifinder_post_update.sh ${pifinder_dir}/.


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


# KStars location service
# Kopieren nach systemd
sudo cp /home/pifinder/PiFinder_Stellarmate/pi_config_files/pifinder_kstars_location_writer.service /etc/systemd/system/

# Aktivieren beim Boot
sudo systemctl enable pifinder_kstars_location_writer.service

# Starten (sofort)
sudo systemctl start pifinder_kstars_location_writer.service

# Status prüfen
systemctl status pifinder_kstars_location_writer.service


# Add requirements
append_line_requirements="picamera2"
if ! check_line_exists "${python_requirements}" "${append_line_requirements}"; then
    append_line_to_file "${python_requirements}" "${append_line_requirements}"  
else
    echo "Line '${append_line_requirements}' already exists in '${python_requirements}'. No need to append."
fi


# Some other ffles need to be changed
solver_py="${pifinder_dir}/python/PiFinder/solver.py"
init_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/__init__.py"
client_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_client.py"
grpc_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_pb2_grpc.py"
t3_dir="${pifinder_dir}/python/PiFinder/tetra3/tetra3"
ui_file="${pifinder_dir}/python/PiFinder/ui/marking_menus.py"
post_update_file="${pifinder_dir}/pifinder_post_update.sh"
camera_file="${pifinder_dir}/python/PiFinder/camera_pi.py"

# --------------
# Helper function
# --------------
show_diff_if_changed() {
    local file="$1"
    if ! cmp -s "${file}.bak" "$file"; then
        echo "🔍 Showing changes for $file:"
        diff --unified "${file}.bak" "$file" || echo "(No changes)"
    else
        echo "ℹ️ No changes for $file"
    fi
    rm -f "${file}.bak"
}

# -----------------
# Process each file
# -----------------

echo "🔧 Updating solver.py ..."
cp "$solver_py" "$solver_py.bak"

if grep -q 'sys.path.append(str(utils.tetra3_dir))' "$solver_py"; then
    sed -i 's|sys.path.append(str(utils.tetra3_dir))|sys.path.append(str(utils.tetra3_dir.parent))|' "$solver_py"
fi

if grep -q '^import tetra3$' "$solver_py"; then
    sed -i 's|^import tetra3$|from tetra3 import main|' "$solver_py"
fi

if ! grep -q "from tetra3 import cedar_detect_client" "$solver_py"; then
    sed -i '/from tetra3 import main/a from tetra3 import cedar_detect_client' "$solver_py"
fi

show_diff_if_changed "$solver_py"


echo "🔧 Patching solver.py for consistent Tetra3 access ..."

solver_py="${pifinder_dir}/python/PiFinder/solver.py"
cp "$solver_py" "$solver_py.bak"

# Ersetze 'from tetra3 import main' → 'import tetra3.main as main'
sed -i 's|from tetra3 import main|import tetra3.main as main|' "$solver_py"

# Ersetze 'tetra3.Tetra3' → 'main.Tetra3'
sed -i 's|tetra3\.Tetra3|main.Tetra3|' "$solver_py"

show_diff_if_changed "$solver_py"





echo "🔧 Updating __init__.py ..."
cp "$init_py" "$init_py.bak"
if grep -q 'from .tetra3 import Tetra3' "$init_py"; then
    sed -i 's|from .tetra3 import Tetra3|from .main import Tetra3|' "$init_py"
fi
show_diff_if_changed "$init_py"

echo "🔧 Updating cedar_detect_client.py ..."
cp "$client_py" "$client_py.bak"
if grep -q 'from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc' "$client_py"; then
    sed -i 's|from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc|from . import cedar_detect_pb2, cedar_detect_pb2_grpc|' "$client_py"
fi
show_diff_if_changed "$client_py"

echo "🔧 Updating cedar_detect_pb2_grpc.py ..."
cp "$grpc_py" "$grpc_py.bak"
if grep -q '^import cedar_detect_pb2 as cedar__detect__pb2$' "$grpc_py"; then
    sed -i 's|^import cedar_detect_pb2 as cedar__detect__pb2$|from . import cedar_detect_pb2 as cedar__detect__pb2|' "$grpc_py"
fi
show_diff_if_changed "$grpc_py"

echo "📄 Checking for tetra3.py -> main.py rename ..."
if [ -f "${t3_dir}/tetra3.py" ]; then
    mv "${t3_dir}/tetra3.py" "${t3_dir}/main.py"
    echo "✅ Renamed tetra3.py → main.py"
else
    echo "ℹ️ File tetra3.py already renamed or does not exist"
fi

echo "🔧 Updating ui/marking_menus.py ..."
cp "$ui_file" "$ui_file.bak"
if grep -q '^from dataclasses import dataclass$' "$ui_file"; then
    sed -i 's|^from dataclasses import dataclass$|from dataclasses import dataclass, field|' "$ui_file"
fi
if grep -q 'up: MarkingMenuOption = MarkingMenuOption(label="HELP")' "$ui_file"; then
    sed -i 's|up: MarkingMenuOption = MarkingMenuOption(label="HELP")|up: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP"))|' "$ui_file"
fi
show_diff_if_changed "$ui_file"

echo "🔧 Updating pifinder_post_update.sh ..."
cp "$post_update_file" "$post_update_file.bak"
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
show_diff_if_changed "$post_update_file"

echo "🔧 Updating camera_pi.py ..."
cp "$camera_file" "$camera_file.bak"
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
show_diff_if_changed "$camera_file"

echo "🔧 Updating requirements.txt ..."
cp "$python_requirements" "$python_requirements.bak"
if ! grep -q '^picamera2$' "$python_requirements"; then
    echo "picamera2" >> "$python_requirements"
fi
show_diff_if_changed "$python_requirements"

echo "✅ All changes applied and shown."


##################################################
#  PiFinder  main.py

echo "🔧 Patching main.py for KStars GPS support ..."
main_py="/home/pifinder/PiFinder/python/PiFinder/main.py"
cp "$main_py" "$main_py.bak"

# Patch veraltete Prüfzeile
if grep -q 'gps_content\["lat"\] \+ gps_content\["lon"\] != 0' "$main_py"; then
    sed -i 's|gps_content\["lat"\] \+ gps_content\["lon"\] != 0|gps_content["lat"] != 0.0 or gps_content["lon"] != 0.0|' "$main_py"
    echo "✅ GPS-Kondition gepatcht in main.py"
fi

show_diff_if_changed "$main_py"

echo "🔧 Ensuring gps_gpsd import in main.py ..."
main_py="/home/pifinder/PiFinder/python/PiFinder/main.py"

# Import prüfen und ggf. einfügen
if ! grep -q 'from PiFinder import gps_gpsd as gps_monitor' "$main_py"; then
    sed -i '/from PiFinder.multiproclogging import MultiprocLogging/a from PiFinder import gps_gpsd as gps_monitor' "$main_py"
    echo "✅ Import von gps_gpsd als gps_monitor eingefügt"
else
    echo "ℹ️ Import gps_gpsd bereits vorhanden"
fi


######################################################
# gps_gpsd.py

echo "🔧 Patching gps_gpsd.py for KStars-only support ..."

gps_py="${pifinder_dir}/python/PiFinder/gps_gpsd.py"
cp "$gps_py" "$gps_py.bak"

# Remove previous gps_main and gps_monitor implementations
sed -i '/^async def gps_main/,/^def gps_monitor/ d' "$gps_py"
sed -i '/^# To run the GPS monitor/,/^$/d' "$gps_py"

# Remove old read_kstars_location_file if present
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
show_diff_if_changed "$gps_py"


######################################################
# menu_structure.py – remove GPS Status entry safely

menu_py="${pifinder_dir}/python/PiFinder/ui/menu_structure.py"
cp "$menu_py" "$menu_py.bak"

# Ziel: sichere Entfernung von "GPS Status"-Einträgen und defekter Klammer danach

# Zeilennummer finden, an der "GPS Status" auftaucht
gps_line=$(grep -n '"name": "GPS Status"' "$menu_py" | cut -d: -f1 | head -n1)

if [[ -n "$gps_line" ]]; then
    start=$((gps_line - 1))    # öffnende {
    end=$((gps_line + 2))      # bis einschließlich schließender }

    # Lösche { + "name": "GPS Status" + "class": ... + },
    sed -i "${start},${end}d" "$menu_py"

    # Entferne überzählige öffnende Klammer direkt nach "Align"
    sed -i '/"name": "Align"/,/preload/ {
        /preload/ {
            n
            /{/d
        }
    }' "$menu_py"

    # Entferne überflüssiges Komma nach "Align"-Block
    sed -i '/"name": "Align"/,/preload/ {
        /preload/ {
            n
            s|},[[:space:]]*|}|
        }
    }' "$menu_py"

    echo "✅ Removed GPS Status block and cleaned up Align section"
else
    echo "ℹ️ No GPS Status block found"
fi

show_diff_if_changed "$menu_py"


