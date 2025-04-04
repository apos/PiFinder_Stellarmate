
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


# PiFinder Service
# Copy over services
# cp ${pifinder_stellarmate_dir}/pi_config_files ${pifinder_dir}/.
python_file="${pifinder_dir}/pi_config_files/pifinder.service"
comment_out_line_content="ExecStart=/usr/bin/python"
commented_line="/home/pifinder/PiFinder/python/.venv/bin/python"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    sed -i 's|/usr/bin/python|/home/pifinder/PiFinder/python/.venv/bin/python|' "${python_file}"
    #comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


python_file="${pifinder_dir}/pi_config_files/pifinder_splash.service"
comment_out_line_content="/usr/bin/python"
commented_line="/home/pifinder/PiFinder/python/.venv/bin/python"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    sed -i 's|/usr/bin/python|/home/pifinder/PiFinder/python/.venv/bin/python|' "${python_file}"
    # comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


# Add requirements
append_line_requirements="picamera2"
if ! check_line_exists "${python_requirements}" "${append_line_requirements}"; then
    append_line_to_file "${python_requirements}" "${append_line_requirements}"  
else
    echo "Line '${append_line_requirements}' already exists in '${python_requirements}'. No need to append."
fi


# Alter main.py
python_file="${pifinder_dir}/python/PiFinder/main.py"
search_line="import os"
insert_lines="# PFinder on Stellarmate\nimport sys\nsys.path.append('/usr/lib/python3/dist-packages')"
if ! check_line_exists "${python_file}" "sys.path.append('/usr/lib/python3/dist-packages')"; then
    insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"
else
    echo "Line '${insert_lines}' already exists in '${python_file}'. No need to append."
fi

############################################################
# Create a __init.py_ for tetra
python_dir="${pifinder_dir}/python/PiFinder/tetra3"
python_file_name="__init__.py"
python_file_init_py="${python_dir}/${python_file_name}"
insert_lines="from .tetra3 import cedar_detect_client"
if ! check_line_exists "${python_file_init_py}" "${insert_lines}"; then
    create_dir_file_and_insert_lines "${python_dir}" "${python_file_name}" "${insert_lines}"
else 
    echo "Line '${insert_lines}' already exists in '${python_file_init_py}'. No need to append."
fi


############################################################
# Alter solver.py
python_file="${pifinder_dir}/python/PiFinder/solver.py"
comment_out_line_content="match_max_error="
commented_line="# COMMENTED match_max_error="
if ! check_line_exists "${python_file}" "${commented_line}"; then
    # awk '{if ($0 ~ /^[[:space:]]*match_max_error=0.005,/) {sub(/match_max_error=0.005/, "# DEPRECIATED match_max_error=0.005", $0)} print $0}' /home/pifinder/PiFinder/python/PiFinder/solver.py > /tmp/solver.py.new && sudo mv /tmp/solver.py.new /home/pifinder/PiFinder/python/PiFinder/solver.py
    comment_out_line_awk "${python_file}" "${comment_out_line_content}" "${commented_line}"
    #cat -vte /home/pifinder/PiFinder/python/PiFinder/solver.py | grep "match_max_error"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


############################################################
# Alter camera_pi.py
python_file="${pifinder_dir}/python/PiFinder/camera_pi.py"
search_line="import numpy as np"
insert_lines="# PFinder on Stellarmate\nfrom picamera2 import Picamera2\nimport libcamera"
if ! check_line_exists "${python_file}" "from picamera2 import Picamera"; then
    insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"
else
    echo "Line '${insert_lines}' already exists in '${python_file}'. No need to append."
fi


############################################################
# Alter ui/marking_menus.py
python_file="${pifinder_dir}/python/PiFinder/ui/marking_menus.py"
comment_out_line_content='up: MarkingMenuOption = MarkingMenuOption(label="HELP")'
commented_line='up: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP")'
if ! check_line_exists "${python_file}" "${commented_line}"; then
    # We need to do this manually via sed 
    
    # comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
    sed -i 's/MarkingMenuOption(label="HELP")/MarkingMenuOption(label="HELP"))/' "${python_file}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi

# Alter ui/marking_menus.py
python_file="${pifinder_dir}/python/PiFinder/ui/marking_menus.py"
comment_out_line_content='from dataclasses import dataclass'
commented_line='from dataclasses import dataclass, field'
if ! check_line_exists "${python_file}" "${commented_line}"; then
    comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


############################################################
# Alter python/PiFinder/tetra3/tetra3/cedar_detect_client.py
python_file="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_client.py"
comment_out_line_content="from PiFinder.tetra3.tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc"
commented_line="from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi

############################################################
# Alter main.py
python_file="${pifinder_dir}/pifinder_post_update.sh"
search_line="git submodule update --init --recursive"
insert_lines="python3 -m venv /home/pifinder/PiFinder/python/.venv\nsource /home/pifinder/PiFinder/python/.venv/bin/activate\n"
if ! check_line_exists "${python_file}" "/home/pifinder/PiFinder/python/.venv/bin/activate"; then
    insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"
else
    echo "Line '${insert_lines}' already exists in '${python_file}'. No need to append."
fi

############################################################
# Alter python/PiFinder/tetra3/tetra3/tetra3.py
python_file="${pifinder_dir}/python/PiFinder/tetra3/tetra3/tetra3.py"

comment_out_line_content="from PiFinder.tetra3.tetra3.breadth_first_combinations import breadth_first_combinations"
commented_line="from tetra3.breadth_first_combinations import breadth_first_combinations"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi


comment_out_line_content="from PiFinder.tetra3.tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density"
commented_line="from tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density"
if ! check_line_exists "${python_file}" "${commented_line}"; then
    comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"
else
    echo "Line '${commented_line}' already exists in '${python_file}'. No need to append."
fi









