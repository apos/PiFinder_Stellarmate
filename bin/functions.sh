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


# The files need to be patched for Pi4
python_requirements="${pifinder_dir}/python/requirements.txt" # Pfad zur requirements.txt
python_requirements_additional="${pifinder_stellarmate_bin}/requirements_additional.txt" # Pfad zur requirements_additional.txt
main_py="${pifinder_dir}/python/PiFinder/main.py"
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
status_py="${pifinder_dir}/python/PiFinder/ui/status.py"
config_default_json="${pifinder_dir}/default_config.json"
config_json="${pifinder_data_dir}/config.json"

# For Pi5
display_py="${pifinder_dir}/python/PiFinder/displays.py"
keyboard_py="${pifinder_dir}/python/PiFinder/keyboard_pi.py"

############################################################
# FUNCTIONS
#############################################################

# Funktion zum Einfügen von Zeilen definieren
insert_lines_after_search() {
  local file_path="$1"
  local search_pattern="$2"
  local lines_to_insert="$3"

  # Überprüfen, ob die Datei existiert
  if [ -f "${file_path}" ]; then
    # Mit sed die Zeilen nach der Zielzeile einfügen
    sed -i "/${search_pattern}/a ${lines_to_insert}" "${file_path}"
    echo "Zeilen erfolgreich nach '${search_pattern}' in '${file_path}' eingefügt."
  else
    echo "Datei '${file_path}' nicht gefunden."
    exit 1
  fi
}

############################################################
# Funktion zum Erstellen der Datei und Einfügen von Zeilen definieren (korrigiert und erweitert)
create_dir_file_and_insert_lines() {
  local dir_path="$1"
  local file_name="$2"
  local lines_to_insert="$3"

  # Verzeichnis erstellen, falls es nicht existiert (Korrektur 2: mkdir -p verwenden)
  mkdir -p "${dir_path}"

  # Datei erstellen, falls sie nicht existiert (Korrektur 3: Datei __init__.py erstellen)
  if [ ! -f "${dir_path}" ]; then
    touch "${dir_path}/${file_name}"
  fi

  # Zeilen am Anfang der Datei einfügen
  {
    echo -e "${lines_to_insert}"
    cat ""${dir_path}/${file_name}""
  } > temp_file && mv temp_file ""${dir_path}/${file_name}""

  echo "Zeilen erfolgreich am Anfang der Datei '"${dir_path}/${file_name}"' eingefügt."
}

############################################################
# Funktion zum Auskommentieren einer Zeile definieren
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
  local commented_line="# COMMENTED " # Leerzeichen am Ende für bessere Lesbarkeit

  if [ -f "${file_path}" ]; then
    # Use awk to comment out the line, preserving indentation

    awk_command='
      BEGIN {line_to_find = ENVIRON["line_to_comment"]}  # Übergebe line_to_comment als Variable
      {
        if ($0 ~ "^[[:space:]]*" line_to_find) {        # Suche nach der Zeile mit Einzug
          sub(/^[[:space:]]*/, "&" ENVIRON["commented_line"], $0) # Kommentiere aus, Einzug erhalten
        }
        print $0                                          # Gib jede Zeile aus (geändert oder nicht)
      }
    '
    export line_to_comment commented_line # Exportiere Variablen für awk

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
install_requirements() {
  local requirements_file="$1"
  echo "Installing Python Requirements from '${requirements_file}'..."
  pip install -r "${requirements_file}" --break-system-packages
  if [ $? -eq 0 ]; then
    echo "Python Requirements installed successfully."
    return 0 # True: requirements installed successfully
  else
    echo "Error installing Python Requirements."
    return 1 # False: requirements installation failed
  fi
}
