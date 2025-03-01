#!/bin/bash
sudo chown -R pifinder:pifinder /home/pifinder/PiFinder
find /home/pifinder/PiFinder/python -name '*.pyc' -delete 
sudo find /home/pifinder/PiFinder/python -name '__pycache__' -type d -exec rm -rf {} +
sudo service pifinder stop
sudo service pifinder start
sudo journalctl -u pifinder -n 20
