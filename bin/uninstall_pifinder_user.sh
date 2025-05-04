#!/bin/bash

# Achtung: Nur ausführen, wenn der User pifinder wirklich nicht mehr gebraucht wird!

USER_TO_REMOVE="pifinder"

# Services stoppen (optional)
echo "Stopping PiFinder services (falls vorhanden)..."
systemctl --user stop pifinder_kstars_location_writer.service 2>/dev/null
systemctl stop pifinder_kstars_location_writer.service 2>/dev/null

# Home-Verzeichnis löschen
if [ -d "/home/$USER_TO_REMOVE" ]; then
  echo "Deleting /home/$USER_TO_REMOVE ..."
  sudo rm -rf "/home/$USER_TO_REMOVE"
else
  echo "Directory /home/$USER_TO_REMOVE not found."
fi

# User aus Gruppen entfernen und löschen
if id "$USER_TO_REMOVE" &>/dev/null; then
  echo "Removing user $USER_TO_REMOVE from system..."
  sudo deluser "$USER_TO_REMOVE"
else
  echo "User $USER_TO_REMOVE does not exist."
fi

# Optional: Gruppen löschen, die nur für pifinder erstellt wurden
for grp in dialout i2c video gpio; do
  if grep -q "^$grp:.*$USER_TO_REMOVE" /etc/group; then
    echo "Removing $USER_TO_REMOVE from group $grp..."
    sudo gpasswd -d "$USER_TO_REMOVE" "$grp"
  fi
done

echo "Done."