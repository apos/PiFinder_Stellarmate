## Tool Usage Strategies

### `replace` Tool
The `replace` tool is extremely sensitive to the `old_string` parameter. It requires an exact, literal match of a unique string in the file.
- **Problem:** Mass-replacing simple strings fails when the string appears multiple times. This has been a major cause of getting stuck in loops.
- **Strategy:** To ensure success, always provide a larger, unique block of text for `old_string`. This usually means including 2-3 lines of surrounding code (before and after) to guarantee the target is unambiguous. Before attempting a complex replacement, it is best practice to `read_file` to get the exact current state of the code to be used as the `old_string`.

## INDI Driver Compilation Strategy (Minimalist Approach)

### Dependency Management
- The system `libindi-dev` package is broken. We are compiling against a full local source build of the INDI library located at `/home/stellarmate/PiFinder_Stellarmate/indi-source`.

### Driver Template Approach
- **Rationale:** Instead of fixing an old, incompatible driver, we are using a known-good, actively maintained driver (`lx200_10micron`) from the official INDI repository as a template.
- **Steps:**
    1.  Copy `.cpp` and `.h` files from the template driver.
    2.  Rename classes and identifiers to the new driver name (`PiFinderLX200`).
    3.  **Strip down the driver to its bare essentials:**
        -   Remove all property definitions and logic related to unsupported features (tracking, parking, guiding, alignment, satellite tracking, etc.) from `initProperties()` and `updateProperties()`.
        -   Simplify `SetTelescopeCapability()` to only include `TELESCOPE_CAN_GOTO` and `TELESCOPE_CAN_SYNC`.
        -   Implement `ReadScopeStatus()` to poll for coordinates using the simple `:GR#` and `:GD#` commands.
        -   Implement the GoTo functionality by overriding the `ISNewRaDec(double ra, double dec)` virtual function.
    4.  Create a new `.xml` file for the driver.
    5.  Integrate the new driver into the `indi-source/drivers/telescope/CMakeLists.txt`.
    6.  Create a custom, stripped-down `pifinder_lx200_generic.cpp` that only loads the `PiFinderLX200` driver to avoid linking errors.
    7.  Compile the single driver using `make indi_pifinder_lx200`.
    8.  Manually install the driver by copying the executable to `/usr/bin` and the `.xml` file to `/usr/share/indi`.

### C++ Error Resolution Patterns
- **`override` Errors:** If a function marked `override` causes a compilation error, it means it does not correctly override a virtual function from a base class. Check the base class headers (e.g., `inditelescope.h`) for the correct function signature. For GoTo functionality, the correct function to override is `ISNewRaDec(double ra, double dec)`.
- **Linker Errors:** Undefined reference errors often mean a function's implementation is missing or its declaration was removed from the header. Ensure that for every function declared in the `.h` file, there is a corresponding implementation in the `.cpp` file, and vice-versa.

## Requirements to Continue/Repeat
- **Installed Packages:** `git`, `cdbs`, `dkms`, `cmake`, `fxload`, `libev-dev`, `libgps-dev`, `libgsl-dev`, `libraw-dev`, `libusb-dev`, `zlib1g-dev`, `libftdi-dev`, `libjpeg-dev`, `libkrb5-dev`, `libnova-dev`, `libtiff-dev`, `libfftw3-dev`, `librtlsdr-dev`, `libcfitsio-dev`, `libgphoto2-dev`, `build-essential`, `libusb-1.0-0-dev`, `libdc1394-dev`, `libboost-regex-dev`, `libcurl4-gnutls-dev`, `libtheora-dev`.
- **INDI Source Location:** `/home/stellarmate/PiFinder_Stellarmate/indi-source`.
- **Test Environment:** Use the pre-installed KStars/Ekos on the Stellarmate device.
- **Troubleshooting Focus:** The primary focus is on fixing the compilation errors by correctly implementing the GoTo functionality and ensuring the driver is stripped of all unsupported features.
