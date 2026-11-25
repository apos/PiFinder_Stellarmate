#! /usr/bin/bash
source /home/pifinder/PiFinder_Stellarmate/bin/functions.sh

git checkout release
if ! git pull
then
    echo "PiFinder software update FAILED: the new version could not be downloaded."
    echo "The currently installed version is unchanged. See the git error above."
    exit 1
fi
source /home/pifinder/PiFinder/pifinder_post_update.sh

# Make some Changes to the downloaded local installation files of PiFinder 
bash ${pifinder_stellarmate_bin}/alter_PiFinder_installation_files.sh

echo "PiFinder software update complete, please restart the Pi"
