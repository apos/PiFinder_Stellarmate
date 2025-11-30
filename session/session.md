# PiFinder INDI Driver Development Session

## Main Requirements and Goal
The primary objective is to develop a stable, minimal INDI driver named `pifinder_lx200` that allows astronomical software like KStars/Ekos to interface with the PiFinder's telescope position server (`pos_server.py`).

## Current Status
The `pifinder_lx200` driver has been renamed to `lx200_pifinder`, integrated into the `indi_lx200generic` build target, and committed. The focus is now solely on getting correct RA and DEC positions from the PiFinder.

## Next Steps
1.  **Analyze RA/DEC:** Examine `lx200_pifinder.cpp`, `lx200_pifinder.h`, and `tmp/pos_server.py` to understand current RA/DEC handling and identify necessary modifications.