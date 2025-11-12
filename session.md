## Overall Goal
Compile a custom INDI driver for the PiFinder to allow INDI-compatible software to control it, and test it within the existing Stellarmate/Ekos environment.

## Current Status
The `pifinder_lx200` driver has been successfully compiled and installed to the system directories (`/usr/bin` and `/usr/share/indi`). The driver has been stripped down to its minimal functionality: reporting current RA/Dec and handling GoTo commands. A detailed compilation guide (`indi_driver_compile.md`) has been created.

## Key Knowledge & State
- **Minimal Driver:** The driver's sole purpose is to report the PiFinder's current RA/Dec and to accept GoTo commands. All other functionality (tracking, parking, guiding, alignment, etc.) is unsupported.
- **GoTo Implementation:** GoTo commands are handled by the `ISNewRaDec(double ra, double dec)` function, which sends `:Sr#` and `:Sd#` commands to the PiFinder's `pos_server.py`.
- **Build Dependency:** We are compiling against the full INDI source code located at `/home/stellarmate/PiFinder_Stellarmate/indi-source`.
- **Test Environment:** All testing is conducted using the standard INDI server provided by the Stellarmate OS, controlled via Ekos/KStars.

## Files Created
- `indi-source/drivers/telescope/pifinder_lx200.cpp`: The main source file for the new driver.
- `indi-source/drivers/telescope/pifinder_lx200.h`: The header file for the new driver.
- `indi-source/drivers/telescope/pifinder_lx200.xml`: The XML file that describes the driver to the INDI system.
- `indi-source/drivers/telescope/pifinder_lx200_generic.cpp`: A custom, simplified version of `lx200generic.cpp` to ensure only the `pifinder_lx200` driver is loaded.
- `indi_driver_compile.md`: A detailed guide on how to compile and install the driver.

## Files Altered
- `indi-source/drivers/telescope/CMakeLists.txt`: Modified to add the `pifinder_lx200` as a new build target.
- `indi-source/drivers.xml`: Modified to include the new `pifinder_lx200` driver.
- `indi-source/drivers/telescope/pifinder_lx200.cpp`: Heavily modified to remove unsupported functions and simplify logic.
- `indi-source/drivers/telescope/pifinder_lx200.h`: Modified to remove declarations for unsupported functions and correct the GoTo implementation.

## Files to Re-read on Resume
To fully restore context, the following files should be read:
1. `session.md` and `session_advanced.md` (for strategy and status).
2. `indi-source/drivers/telescope/pifinder_lx200.h` (the new driver's header).
3. `indi-source/drivers/telescope/pifinder_lx200.cpp` (the new driver's source code).
4. `indi-source/libs/indidriver/inditelescope.h` (to understand the base class virtual functions).

## Next Steps
1.  **Test the Driver in Ekos:**
    -   Start KStars/Ekos.
    -   Create a new equipment profile.
    -   Select the "PiFinder LX200" driver for the telescope.
    -   Start the INDI server through Ekos and connect to the driver.
    -   Verify that the driver connects and correctly reports RA/Dec.
    -   Test the GoTo functionality by slewing to a target in KStars.
2.  **Finetune and Clean:**
    -   Address any remaining issues or unexpected behavior.
    -   Ensure the driver is stable and efficient.