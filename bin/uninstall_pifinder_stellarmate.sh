#!/usr/bin/env bash

echo "🚫 Uninstalling PiFinder (Stellarmate version) ..."

echo "🔧 Stopping PiFinder services ..."
sudo systemctl stop pifinder.service
sudo systemctl stop pifinder_splash.service
sudo systemctl stop pifinder_kstars_location_writer.service

echo "🧹 Disabling services ..."
sudo systemctl disable pifinder.service
sudo systemctl disable pifinder_splash.service
sudo systemctl disable pifinder_kstars_location_writer.service

echo "Removing systemd unit files ..."
sudo rm -f /etc/systemd/system/pifinder.service
sudo rm -f /etc/systemd/system/pifinder_splash.service
sudo rm -f /etc/systemd/system/pifinder_kstars_location_writer.service

echo "🔄 Reloading systemd ..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload

echo "🗂️ Deleting PiFinder installation directory ..."
sudo rm -rf /home/stellarmate/PiFinder

echo "⚠️  NOTE: The folder /home/stellarmate/PiFinder_data was NOT removed."
echo "    You can delete it manually if needed."

echo "📦 Optional: You may now remove the repository clone with:"
echo "    rm -rf /home/stellarmate/PiFinder_Stellarmate"

echo "✅ Uninstall complete."

