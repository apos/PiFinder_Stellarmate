#! /usr/bin/bash
# StellarMate (PFSM): PiFinder's own updater is not used here.
# It would `git checkout release && git pull` - the newest PiFinder release, not the version PFSM
# pins and tests - and then run upstream's migrations (sudo, /boot/config.txt, systemd) which are
# written for a stock PiFinder image. PiFinder is updated through the StellarMate Control Center
# (Install or Update), which installs the pinned version and re-applies the StellarMate patches.
echo "PiFinder software update is done through the StellarMate Control Center (Install or Update)."
echo "Nothing was changed."
exit 1
