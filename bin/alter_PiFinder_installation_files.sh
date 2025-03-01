
#!/bin/bash

cd /home/pifinder

source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh

############################################################
# ALTER FILES
############################################################

# PiFinder Service
# Copy over services
# cp ${pifinder_stellarmate_dir}/pi_config_files ${pifinder_dir}/.
python_file="${pifinder_dir}/python/pi_config_files/pifinder.service"
comment_out_line_content="ExecStart=/usr/bin/python -m PiFinder.main"
commented_line="ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder.main"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"

python_file="${pifinder_dir}/python/pi_config_files/pifinder_splash.service"
comment_out_line_content="ExecStart=/usr/bin/python -m PiFinder.main"
commented_line="ExecStart=/home/pifinder/PiFinder/python/.venv/bin/python -m PiFinder_splash.main"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"

# Add requirements
append_line_requirements="picamera2"
append_line_to_file "${python_requirements}" "${append_line_requirements}"

# Alter main.py
python_file="${pifinder_dir}/python/PiFinder/main.py"
search_line="import os"
insert_lines="# PFinder on Stellarmate\nimport sys\nsys.path.append('/usr/lib/python3/dist-packages')"
insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"


############################################################
# Create a __init.py_ for tetra
python_dir="${pifinder_dir}/python/PiFinder/tetra3"
python_file_name="__init__.py"
python_file_init_py="${python_dir}/${python_file_name}"
insert_lines="from .tetra3 import cedar_detect_client"
create_dir_file_and_insert_lines "${python_dir}" "${python_file_name}" "${insert_lines_tetra3}"


############################################################
# Alter solver.py
python_file="${pifinder_dir}/python/PiFinder/solver.py"
comment_out_line_content="match_max_error=0.005,"
commented_line="# OBSOLET ${comment_out_line_content}"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"


############################################################
# Alter camera_pi.py
python_file="${pifinder_dir}/python/PiFinder/camera_pi.py"
search_line="import numpy as np"
insert_lines="# PFinder on Stellarmate\nfrom picamera2 import Picamera2\nimport libcamera"
insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"

############################################################
# Alter ui/marking_menus.py
python_file="${pifinder_dir}/ui/marking_menus.py"
comment_out_line_content="up: MarkingMenuOption = "
commented_line="#p: MarkingMenuOption = field(default_factory=lambda: MarkingMenuOption(label="HELP"))"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"


############################################################
# Alter python/PiFinder/tetra3/tetra3/cedar_detect_client.py
python_file="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_client.py"
comment_out_line_content="from PiFinder.tetra3.tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc"
commented_line="from tetra3 import cedar_detect_pb2, cedar_detect_pb2_grpc"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"

############################################################
# Alter main.py
python_file="${pifinder_dir}/pifinder_post_update.sh"
search_line="git submodule update --init --recursive"
insert_lines="python3 -m venv /home/pifinder/PiFinder/python/.venv\nsource /home/pifinder/PiFinder/python/.venv/bin/activate\n"
insert_lines_after_search "${python_file}" "${search_line}" "${insert_lines}"

############################################################
# Alter python/PiFinder/tetra3/tetra3/tetra3.py
python_file="${pifinder_dir}/python/PiFinder/tetra3/tetra3/tetra3.py"

comment_out_line_content="from PiFinder.tetra3.tetra3.breadth_first_combinations import breadth_first_combinations"
commented_line="from tetra3.breadth_first_combinations import breadth_first_combinations"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"

comment_out_line_content="from PiFinder.tetra3.tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density"
commented_line="from tetra3.fov_util import fibonacci_sphere_lattice, num_fields_for_sky, separation_for_density"
comment_out_line "${python_file}" "${comment_out_line_content}" "${commented_line}"








