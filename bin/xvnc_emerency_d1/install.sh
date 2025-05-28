#!/bin/bash

set -e

TARGET_DIR="$HOME/Stellarmate_xvnc_setup"
SERVICE_FILE="xvnc_session1.service"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_FILE"

echo "➤ Installiere Xvnc Service nach $SERVICE_TARGET"
sudo cp "$TARGET_DIR/$SERVICE_FILE" "$SERVICE_TARGET"
sudo chmod 644 "$SERVICE_TARGET"

echo "➤ Setze Ausführbarkeit für start_xvnc_session1.sh"
chmod +x "$TARGET_DIR/start_xvnc_session1.sh"

echo "➤ Lade systemd neu und aktiviere den Dienst"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_FILE"
sudo systemctl restart "$SERVICE_FILE"
sudo systemctl status "$SERVICE_FILE" --no-pager