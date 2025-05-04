#!/bin/bash

# Skript nur mit sudo ausführen
if [ "$EUID" -ne 0 ]; then
  echo "Dieses Skript muss mit sudo ausgeführt werden."
  exit 1
fi

# Achtung: Nur ausführen, wenn der User pifinder wirklich nicht mehr gebraucht wird!

USER_TO_REMOVE="pifinder"

# Services stoppen (optional)
echo "Beende alle laufenden Prozesse des Benutzers $USER_TO_REMOVE ..."
pkill -u "$USER_TO_REMOVE"
sleep 2

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

  # Versuche die gleichnamige Gruppe zu löschen, falls leer
  if getent group "$USER_TO_REMOVE" >/dev/null; then
    echo "Prüfe, ob Gruppe $USER_TO_REMOVE leer ist und gelöscht werden kann ..."
    if [ -z "$(getent group "$USER_TO_REMOVE" | cut -d: -f4)" ]; then
      echo "Gruppe $USER_TO_REMOVE ist leer – wird gelöscht ..."
      sudo groupdel "$USER_TO_REMOVE"
    else
      echo "Gruppe $USER_TO_REMOVE ist nicht leer – wird nicht gelöscht."
    fi
  fi

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