#!/bin/bash
find /home/stellarmate/PiFinder/python -name '*.pyc' -delete 
sudo find /home/stellarmate/PiFinder/python -name '__pycache__' -type d -exec rm -rf {} +
sudo systemctl restart pifinder
sudo journalctl -u pifinder -n 100
