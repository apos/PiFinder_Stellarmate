#!/bin/bash

SERVICE_NAME="xvnc_session1.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

echo "➤ Stoppe und deaktiviere den Service falls aktiv..."
sudo systemctl stop "$SERVICE_NAME" || true
sudo systemctl disable "$SERVICE_NAME" || true

echo "➤ Entferne systemd Service-Datei: $SERVICE_PATH"
sudo rm -f "$SERVICE_PATH"

echo "➤ Lade systemd neu"
sudo systemctl daemon-reload

echo "➤ Entferne temporäre Dateien (optional)..."
/bin/rm -f /tmp/x11vnc_display1.log /tmp/.X11-unix/X1 /tmp/.X1-lock

echo "✅ Deinstallation abgeschlossen."