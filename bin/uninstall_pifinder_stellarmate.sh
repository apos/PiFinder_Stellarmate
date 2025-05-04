#!/usr/bin/env bash

# Call with "--selfmove" to run from /tmp in background: ./uninstall_pifinder_stellarmate.sh --selfmove

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


if [[ "$1" == "--selfmove" ]]; then
    echo "🧪 Copying script to /tmp and executing in background ..."
    tmp_script="/tmp/uninstall_pifinder_stellarmate.sh"
    cp "$0" "$tmp_script"
    chmod +x "$tmp_script"
    echo "cd / && nohup \"$tmp_script\" --run > /tmp/uninstall_pifinder.log 2>&1 < /dev/null & disown" | bash
    echo "ℹ️  Script is now running in background from /tmp. Monitor with:"
    echo "    tail -f /tmp/uninstall_pifinder.log"
    exit 0
fi

# --reset mode: clean install and config, but keep user data and repo
if [[ "$1" == "--reset" ]]; then
    echo "♻️  Resetting PiFinder installation ..."
    sleep 1
    cd /

    echo "🔧 Stopping PiFinder services ..."
    sudo systemctl stop pifinder.service
    sudo systemctl stop pifinder_splash.service
    sudo systemctl stop pifinder_kstars_location_writer.service

    echo "🧹 Disabling services ..."
    sudo systemctl disable pifinder.service
    sudo systemctl disable pifinder_splash.service
    sudo systemctl disable pifinder_kstars_location_writer.service

    echo "🗑️ Removing systemd unit files ..."
    sudo rm -f /etc/systemd/system/pifinder.service
    sudo rm -f /etc/systemd/system/pifinder_splash.service
    sudo rm -f /etc/systemd/system/pifinder_kstars_location_writer.service

    echo "🔄 Reloading systemd ..."
    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload

    echo "🧹 Cleaning Python virtual environment ..."
    sudo rm -rf /home/stellarmate/PiFinder/python/.venv

    echo "🧽 Removing leftover build artifacts and logs ..."
    sudo rm -rf /home/stellarmate/PiFinder/python/build
    sudo rm -rf /home/stellarmate/PiFinder/python/dist
    sudo rm -rf /home/stellarmate/PiFinder/python/*.egg-info
    sudo find /home/stellarmate/PiFinder/python -name __pycache__ -exec rm -rf {} +

    echo "♻️  PiFinder reset complete. You can now re-run the setup script:"
    echo "    ./pifinder_stellarmate_setup.sh"
    exit 0
fi

if [[ "$1" == "--run" ]]; then
    echo "🔁 Running uninstall from /tmp ..."
    sleep 1
    cd /

    echo "🔧 Stopping PiFinder services ..."
    sudo systemctl stop pifinder.service
    sudo systemctl stop pifinder_splash.service
    sudo systemctl stop pifinder_kstars_location_writer.service

    echo "🧹 Disabling services ..."
    sudo systemctl disable pifinder.service
    sudo systemctl disable pifinder_splash.service
    sudo systemctl disable pifinder_kstars_location_writer.service

    echo "🗑️ Removing systemd unit files ..."
    sudo rm -f /etc/systemd/system/pifinder.service
    sudo rm -f /etc/systemd/system/pifinder_splash.service
    sudo rm -f /etc/systemd/system/pifinder_kstars_location_writer.service

    echo "🔄 Reloading systemd ..."
    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload

    echo "🗂️ Deleting PiFinder installation directory ..."
    sudo rm -rf /home/stellarmate/PiFinder
    sudo rm -rf /home/stellarmate/PiFinder_Stellarmate

    echo "⚠️  NOTE: The folder /home/stellarmate/PiFinder_data was NOT removed."
    echo "    You can delete it manually if needed."

    echo "✅ Uninstall complete."
    exit 0
fi
