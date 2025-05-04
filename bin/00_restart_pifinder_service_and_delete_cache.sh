#!/bin/bash
find /home/stellarmate/PiFinder/python -name '*.pyc' -delete 
sudo find /home/stellarmate/PiFinder/python -name '__pycache__' -type d -exec rm -rf {} +
sudo service pifinder stop
sudo service pifinder start
sudo journalctl -u pifinder -n f
