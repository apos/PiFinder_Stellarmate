#! /usr/bin/bash
# StellarMate (PFSM): PiFinder's own post-update migrations are not run here, see pifinder_update.sh.
# What PFSM needs after a PiFinder checkout (the python/tetra3 link, packages, patches) is done by
# pifinder_stellarmate_setup.sh and bin/patch_PiFinder_installation_files.sh.
echo "PiFinder post-update steps are done by the StellarMate setup (Control Center: Install or Update)."
echo "Nothing was changed."
return 1 2>/dev/null || exit 1
