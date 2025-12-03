## PiFinder INDI Driver - Advanced Session Details

## Core Architecture & Build Strategy
The `pifinder_lx200` driver is architected as a subclass of the `LX200Generic` class, which in turn inherits from `INDI::Telescope`. Our build process injects the `lx200_pifinder.cpp` source file directly into the `add_executable()` command for the existing `indi_lx200generic` target in the main INDI `CMakeLists.txt`. The INDI server uses a symbolic link (`/usr/bin/indi_pifinder_lx200` -> `/usr/bin/indi_lx200generic`) to invoke the generic executable, which then dynamically loads our `LX200_PIFINDER` class based on the invocation name. This method is efficient and avoids code duplication. The `bin/build_indi_driver.sh` script automates the entire workflow.

## Debugging Workflow - The Refined Development Loop
Our systematic debugging and development workflow adheres to the following sequence:
1.  **Build INDI Driver:** Initiate a build by running `bin/build_indi_driver.sh`.
2.  **Check and Correct Code:**
    *   **Build Failures:** Immediately after a build, examine `indi_driver_build.log` for compiler errors.
    *   **Runtime/Connection Failures:** For issues after a successful build, `indi_driver_build.log` will contain appended KStars/INDI runtime logs.
3.  **Git Commit:** After *every atomic, logical code change*, commit the modifications to the `indi_pifinder/` directory with a descriptive message.
4.  **Update Session:** Maintain an up-to-date record of the current status, new insights, and the precise next steps in `session/session.md` and `session/session_advanced.md`.
5.  **Test and Verify:** After a successful build, perform functional testing using Ekos.

## Current Status and Next Steps - **VERSION 2.0 STABLE**
The driver's core RA/DEC polling and connection handling is now stable and working as intended. This milestone has been formally marked by merging the development branch (`pi4_lx200_v2.0_base_10micron_alpha`) into `main`.

Development has now moved to a new branch, `pi4_lx200_2.1_base_10micron_beta`, for the implementation of new features.

**Next Steps:**
The project is now ready for the next phase of development. Please provide the next set of instructions or features to implement on the new branch.