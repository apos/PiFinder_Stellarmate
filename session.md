## Overall Goal
Compile a custom INDI driver for the PiFinder to allow INDI-compatible software to control it, and test it within the existing Stellarmate/Ekos environment.

## Current Status
The `pifinder_lx200` driver has been heavily modified to be a minimal driver, but the compilation is failing. The `GoTo` function was incorrectly marked with `override`, and several unsupported function implementations were not fully removed, leading to linker errors.

## Key Knowledge & State
- **Minimal Driver:** The driver's sole purpose is to report the PiFinder's current RA/Dec and to accept GoTo commands. All other functionality (tracking, parking, guiding, alignment, etc.) is unsupported.
- **GoTo Implementation:** The correct way to handle a GoTo command is to override the `ISNewRaDec(double ra, double dec)` virtual function from the `INDI::Telescope` base class. This function is triggered when a client sends new coordinates.
- **Build Dependency:** We are compiling against the full INDI source code located at `/home/stellarmate/PiFinder_Stellarmate/indi-source`.
- **Test Environment:** All testing is conducted using the standard INDI server provided by the Stellarmate OS, controlled via Ekos/KStars.

## Files Created
- `indi-source/drivers/telescope/pifinder_lx200.cpp`: The main source file for the new driver.
- `indi-source/drivers/telescope/pifinder_lx200.h`: The header file for the new driver.
- `indi-source/drivers/telescope/pifinder_lx200.xml`: The XML file that describes the driver to the INDI system.
- `indi-source/drivers/telescope/pifinder_lx200_generic.cpp`: A custom, simplified version of `lx200generic.cpp` to ensure only the `pifinder_lx200` driver is loaded.

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
1.  **Fix Compilation Errors:**
    -   Remove the incorrect `GoTo(double ra, double dec)` declaration and implementation.
    -   Add the correct `ISNewRaDec(double ra, double dec) override` declaration to `pifinder_lx200.h`.
    -   Implement `ISNewRaDec` in `pifinder_lx200.cpp` to send the `:Sr#` and `:Sd#` commands.
    -   Ensure all other unsupported function implementations are fully removed.
2.  **Recompile and Install:**
    -   Run `make indi_pifinder_lx200` in the build directory.
    -   Copy the compiled driver to `/usr/bin/`.
3.  **Test the Driver in Ekos:**
    -   Verify that the driver connects and correctly reports RA/Dec.
    -   Test the GoTo functionality by slewing to a target in KStars.
