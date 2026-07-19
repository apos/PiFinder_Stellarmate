#####################################
# Paths
#####################################
pifinder_home="/home/${SUDO_USER:-${USER}}"
pifinder_stellarmate_dir="${pifinder_home}/PiFinder_Stellarmate"
pifinder_stellarmate_bin="${pifinder_stellarmate_dir}/bin"
pifinder_dir="${pifinder_home}/PiFinder"
pifinder_data_dir="${pifinder_home}/PiFinder_data"
python_venv="${pifinder_dir}/python/.venv"
pifinder_config_dir="${pifinder_home}/.config"
kstarsrc_source="${pifinder_config_dir}/kstarsrc"
kstarsrc_target="${pifinder_config_dir}/kstarsrc"
indi_pifinder_dir="${pifinder_stellarmate_dir}/indi_pifinder"



# The files need to be patched for Pi4
python_requirements="${pifinder_dir}/python/requirements.txt" # Pfad zur requirements.txt
python_requirements_additional="${pifinder_stellarmate_bin}/requirements_additional.txt" # Pfad zur requirements_additional.txt
main_py="${pifinder_dir}/python/PiFinder/main.py"
state_py="${pifinder_dir}/python/PiFinder/state.py"
camera_interface_py="${pifinder_dir}/python/PiFinder/camera_interface.py"
api_extensions_py="${pifinder_dir}/python/PiFinder/api_extensions.py"
gps_py="${pifinder_dir}/python/PiFinder/gps_gpsd.py"
solver_py="${pifinder_dir}/python/PiFinder/solver.py"
init_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/__init__.py"
client_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_client.py"
grpc_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/cedar_detect_pb2_grpc.py"
t3_dir="${pifinder_dir}/python/PiFinder/tetra3/tetra3"
ui_file="${pifinder_dir}/python/PiFinder/ui/marking_menus.py"
post_update_file="${pifinder_dir}/pifinder_post_update.sh"
camera_file="${pifinder_dir}/python/PiFinder/camera_pi.py"
menu_py="${pifinder_dir}/python/PiFinder/ui/menu_structure.py"
catalogs_py="${pifinder_dir}/python/PiFinder/catalogs.py"
tetra3_main_py="${pifinder_dir}/python/PiFinder/tetra3/tetra3/main.py"
status_py="${pifinder_dir}/python/PiFinder/ui/status.py"
sys_utils_py="${pifinder_dir}/python/PiFinder/sys_utils.py"
sys_utils_fake_py="${pifinder_dir}/python/PiFinder/sys_utils_fake.py"
index_tpl="${pifinder_dir}/python/views/index.tpl"
header_tpl="${pifinder_dir}/python/views/header.tpl"
config_default_json="${pifinder_dir}/default_config.json"
config_json="${pifinder_data_dir}/config.json"

# For Pi5
display_py="${pifinder_dir}/python/PiFinder/displays.py"
keyboard_py="${pifinder_dir}/python/PiFinder/keyboard_pi.py"

############################################################
# FUNCTIONS
#############################################################

# Function to insert lines after a matched line
insert_lines_after_search() {
  local file_path="$1"
  local search_pattern="$2"
  local lines_to_insert="$3"

  # Check whether the file exists
  if [ -f "${file_path}" ]; then
    # Insert the lines after the target line using sed
    sed -i "/${search_pattern}/a ${lines_to_insert}" "${file_path}"
    echo "Lines successfully inserted after '${search_pattern}' in '${file_path}'."
  else
    echo "File '${file_path}' not found."
    exit 1
  fi
}

############################################################
# Function to create the file and insert lines at the top
create_dir_file_and_insert_lines() {
  local dir_path="$1"
  local file_name="$2"
  local lines_to_insert="$3"

  # Create the directory if it doesn't exist
  mkdir -p "${dir_path}"

  # Create the file if it doesn't exist
  if [ ! -f "${dir_path}" ]; then
    touch "${dir_path}/${file_name}"
  fi

  # Insert the lines at the top of the file
  {
    echo -e "${lines_to_insert}"
    cat ""${dir_path}/${file_name}""
  } > temp_file && mv temp_file ""${dir_path}/${file_name}""

  echo "Lines successfully inserted at the top of '"${dir_path}/${file_name}"'."
}

############################################################
# Function to comment out a line
comment_out_line() {
  local file_path="$1"
  local line_to_comment="$2"
  local commented_line="# COMMENTED" # Hardcoded commented_line for debugging

  if [ -f "${file_path}" ]; then
    # Use sudo sed with simplified command and line_to_comment variable
    sed -i "s|^[[:space:]]*\"${line_to_comment}\"|${commented_line}|" "${file_path}"
    echo "Line successfully commented out in '${file_path}'."
  else
    echo "File '${file_path}' not found."
    exit 1
  fi
}


comment_out_line_awk() {
  local file_path="$1"
  local line_to_comment="$2"
  local commented_line="# COMMENTED " # Trailing space for better readability

  if [ -f "${file_path}" ]; then
    # Use awk to comment out the line, preserving indentation

    awk_command='
      BEGIN {line_to_find = ENVIRON["line_to_comment"]}  # Pass line_to_comment in as a variable
      {
        if ($0 ~ "^[[:space:]]*" line_to_find) {        # Look for the line, keeping indentation
          sub(/^[[:space:]]*/, "&" ENVIRON["commented_line"], $0) # Comment it out, keep indentation
        }
        print $0                                          # Print every line (changed or not)
      }
    '
    export line_to_comment commented_line # Export variables for awk

    awk "${awk_command}" "${file_path}" > /tmp/solver.py.new && sudo mv /tmp/solver.py.new "${file_path}"

    echo "Line successfully commented out in '${file_path}' using awk."
  else
    echo "File '${file_path}' not found."
    exit 1
  fi
}

############################################################
append_line_to_file() {
  local file_path="$1"
  local line_to_append="$2"

  # Check if the file exists
  if [ -f "${file_path}" ]; then
    # Append the line to the file
    echo "${line_to_append}" >> "${file_path}"
    echo "Line successfully appended to '${file_path}'."
    return 0 # True: line appended successfully
  else
    echo "File '${file_path}' not found."
    return 1 # False: file not found
  fi
}


############################################################
check_line_exists() {
  local file_path="$1"
  local line_to_check="$2"

  if [ -f "${file_path}" ]; then
    grep -qF -- "${line_to_check}" "${file_path}"
    if [ $? -eq 0 ]; then
      echo "Line '${line_to_check}' already exists in '${file_path}'."
      return 0 # True: line exists
    else
      echo "Line '${line_to_check}' does not exist in '${file_path}'."
      return 1 # False: line does not exist
    fi
  else
    echo "File '${file_path}' not found."
    return 2 # File not found (different exit code to distinguish from line not existing in existing file)
  fi
}


############################################################
check_user_exists() {
  local username="$1"
  id -u "${username}" > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "User '${username}' exists."
    return 0 # True: user exists
  else
    echo "User '${username}' does NOT exist."
    return 1 # False: user does not exist
  fi
}


############################################################
is_venv_active() {
  local venv_path="$1"

  if [ -n "${VIRTUAL_ENV}" ] && [ "${VIRTUAL_ENV}" = "${venv_path}" ]; then
    echo "Python venv '${venv_path}' is active."
    return 0 # True: venv is active
  else
    echo "Python venv '${venv_path}' is NOT active."
    return 1 # False: venv is not active
  fi
}

############################################################
check_venv_exists() {
  local venv_path="$1"
  if [ -d "${venv_path}" ]; then
    echo "Python venv directory '${venv_path}' exists."
    return 0 # True: venv directory exists
  else
    echo "Python venv directory '${venv_path}' does NOT exist."
    return 1 # False: venv directory does not exist
  fi
}

############################################################
create_venv() {
  local venv_path="$1"
  echo "Creating Python venv in '${venv_path}'..."
  /usr/bin/python3 -m venv "${venv_path}" --system-site-packages
  if [ $? -eq 0 ]; then
    echo "Python venv successfully created in '${venv_path}'."
    return 0 # True: venv created successfully
  else
    echo "Error creating Python venv in '${venv_path}'."
    return 1 # False: venv creation failed
  fi
}

############################################################
# Warnings collected across both this script and
# patch_PiFinder_installation_files.sh (run as a separate bash process, so
# it needs the same variable/function via functions.sh rather than
# inheriting them from the calling script's shell). pifinder_stellarmate_
# setup.sh clears this file at the start of a fresh run and prints/removes
# it in the final summary; add_warning() just appends to whatever's there.
warnings_file="${pifinder_stellarmate_dir}/.setup_warnings"

add_warning() {
  echo "  ⚠️  $1"
  echo "$1" >> "$warnings_file"
}

############################################################
# Wraps `patch -N` so a partially-failed patch (upstream PiFinder changed
# lines near ours, breaking the context - see 00014_workflow-regeln-
# update-install.md) is a loud, unmissable warning in the final summary,
# not just a "N out of M hunks FAILED" line buried in the scroll-by log.
apply_patch_or_warn() {
  local target_file="$1"
  local diff_file="$2"
  rm -f "${target_file}.rej"
  patch -N "$target_file" < "$diff_file"
  if [ -f "${target_file}.rej" ]; then
    add_warning "Patch didn't fully apply: $(basename "$diff_file") -> $target_file (see ${target_file}.rej) - upstream PiFinder likely changed nearby lines; the diff needs regenerating."
  fi
}

############################################################
install_requirements() {
  local requirements_file="$1"
  echo "Installing Python Requirements from '${requirements_file}'..."
  # nice -n 15: reduce CPU priority to prevent system overload during compilation
  # ionice -c 3: idle I/O class so system stays responsive during long builds
  nice -n 15 ionice -c 3 pip install -r "${requirements_file}"
  if [ $? -eq 0 ]; then
    echo "Python Requirements installed successfully."
    return 0
  else
    echo "Error installing Python Requirements."
    return 1
  fi
}
