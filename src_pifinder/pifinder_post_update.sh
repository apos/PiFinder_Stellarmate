source /home/stellarmate/PiFinder_Stellarmate/bin/functions.sh

git submodule update --init --recursive
python3 -m venv /home/stellarmate/PiFinder/python/.venv
source /home/stellarmate/PiFinder/python/.venv/bin/activate
python3 -m venv ${pifinder_dir}/python/.venv
source ${pifinder_dir}/python/.venv/bin/activate
${pifinder_dir}/python/.venv/bin/pip install -r ${pifinder_dir}/python/requirements.txt

# Set up migrations folder if it does not exist
if ! [ -d "${pifinder_data_dir}/migrations" ]
then
    mkdir ${pifinder_data_dir}/migrations
fi

# v1.x.x
# everying prior to selecitve migrations
if ! [ -f "${pifinder_data_dir}/migrations/v1.x.x" ]
then
    source ${pifinder_dir}/migration_source/v1.x.x.sh
    touch ${pifinder_data_dir}/migrations/v1.x.x
fi

# v2.1.0
# Switch to Cedar
if ! [ -f "${pifinder_data_dir}/migrations/v2.1.0" ]
then
    source ${pifinder_dir}/migration_source/v2.1.0.sh
    touch ${pifinder_data_dir}/migrations/v2.1.0
fi

# DONE
echo "Post Update Complete"
