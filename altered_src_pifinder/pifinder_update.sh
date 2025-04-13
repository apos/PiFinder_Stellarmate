#! /usr/bin/bash
source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh

git checkout release
git pull
source /home/pifinder/PiFinder/pifinder_post_update.sh

# Make some Changes to the downloaded local installation files of PiFinder 
bash ${pifinder_stellarmate_bin}/alter_PiFinder_installation_files.sh

echo "PiFinder software update complete, please restart the Pi"
