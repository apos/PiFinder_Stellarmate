# PiFinder INDI Driver Development Session

## Main Requirements and Goal
The primary objective is to develop a stable, minimal INDI driver named `pifinder_lx200` that allows astronomical software like KStars/Ekos to interface with the PiFinder's telescope position server (`pos_server.py`).

## Current Status
Longitude getter (`:Gg#`) and setters for longitude (`:Sg...#`) and UTC offset (`:SG...#`) have been implemented in `pos_server.py`. The updated `pos_server.py` has been copied to the PiFinder installation and the `pifinder` service has been restarted.

## Next Steps
1.  **Rebuild INDI Driver:** Rebuild the INDI driver to incorporate the new commands.
2.  **Test INDI Driver:** Verify that RA, DEC, Longitude, and UTC offset are all correctly communicated via Ekos.