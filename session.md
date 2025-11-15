## PiFinder INDI Driver Development

**Objective:** Compile and install the `pifinder_lx200` INDI driver.

**Status:**
The development files (`pifinder_lx200.h` and `pifinder_lx200.cpp`) have been copied from the `indi_pifinder` directory to the `indi-source/drivers/telescope` directory. The old build directory and installed driver files have been removed. The project is ready to be built.

**Files Altered:**
*   `indi-source/drivers/telescope/pifinder_lx200.h`: Copied from `indi_pifinder/pifinder_lx200.h`.
*   `indi-source/drivers/telescope/pifinder_lx200.cpp`: Copied from `indi_pifinder/pifinder_lx200.cpp`.
*   `indi_pifinder/pifinder.h`: Renamed to `pifinder_lx200.h`.
*   `indi_pifinder/pifinder.cpp`: Renamed to `pifinder_lx200.cpp`.
*   `indi_pifinder/CMakeLists.txt`: Updated to reflect the new file names.
*   `indi_pifinder/indi_pifinder_driver.xml.in`: Renamed to `indi_pifinder_lx200_driver.xml.in`.

**Key Knowledge & Strategy:**
*   The development files are in the `indi_pifinder` directory.
*   The INDI build system compiles the driver from the `indi-source/drivers/telescope` directory.
*   The development files must be copied to the `indi-source` directory before building.
*   A clean build is necessary to ensure that the correct files are used.

**Next Steps:**
1.  Create a new build directory.
2.  Run CMake to configure the build.
3.  Compile the driver.
4.  Install the driver binary and XML file.
5.  Restart KStars/Ekos and test the driver.

**Files to Re-read for Context:**
*   `session.md`
*   `session_advanced.md`
*   `indi_driver_compile.md`
*   `indi_pifinder/CMakeLists.txt`
*   `indi-source/drivers/telescope/pifinder_lx200.h`
*   `indi-source/drivers/telescope/pifinder_lx200.cpp`
