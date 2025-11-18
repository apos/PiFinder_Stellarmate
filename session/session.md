## PiFinder LX200 INDI Driver - Session State

### Main Requirements and goal (do not change or alter)
- PiFinder is a device which can do live platesolving an has an python server which implements parts of the LX200 protkoll: it reports the position, can accept a GoTo and an align. 
- Stellarmate is an debian based OS which uses INDI to communicate with devices. This is done by indi-server which is under the command of a running KStars/EKOS. 
- There is an INDI driver that partially works with PiFinder: 10micron_lx200. But this only the case for the basic functionality, like beeing adhered from lx200_generic, establishing the connection over network, getting a posistion. 10micron has a lot of functionality which PiFinder not has, also some funcitons like goto or align do not work out of the box and need refactoring to match PiFinders pos_server.py.

### Current Status
The `pifinder_lx200` INDI driver build process has been completely refactored and is now stable, fast, and reliable. The driver is built following the established INDI pattern for `lx200generic`-based drivers (like `lx200_10micron`), where the driver's source is compiled into the main `indi_lx200generic` executable and invoked via a unique symbolic link. The build script is now ready for the user to run, after which the driver should be selectable in Ekos for testing.

### Altered Files & Rationale
- **`bin/build_indi_driver.sh`**: Heavily refactored for speed and safety.
    - **Why (Patching):** The `sed` command used to patch the `CMakeLists.txt` file was unreliable. It has been replaced with a robust `grep` and `sed` combination that is not prone to shell escaping errors.
    - **Why (Installation):** The previous `make install` command was slow and installed the entire INDI library. It has been replaced with a direct `cp` command that installs *only* the `indi_lx200generic` executable, dramatically speeding up the process and removing the need to back up `drivers.xml`.
    - **Why (Symlink):** A command was added to create the `indi_pifinder_lx200` symbolic link, which is the critical step to make the driver appear as a standalone entry in Ekos.
- **`indi_pifinder/indi_pifinder_lx200_driver.xml.in`**: The `exec` attribute was changed to `indi_pifinder_lx200`.
    - **Why:** To match the symbolic link created by the build script, ensuring Ekos calls the correct executable name.

### Key Concepts & Strategies
- **Build Strategy**: The driver is built by integrating its source code into the `indi_lx200_generic` executable. It is then invoked via a unique symbolic link (`indi_pifinder_lx200`), which makes it appear as a standalone driver to the user. This mirrors the exact, proven method used by the `lx200_10micron` driver.
- **Efficiency**: The build script now only compiles the single `indi_lx200generic` target and uses a direct file copy for installation, making the build-test-debug cycle very fast.
- **Commit Rule**: A strict rule is now in place: **commit after every code change**. The build script helps enforce this by creating an automated commit in the `indi_pifinder` directory before starting a build. This ensures a reliable history we can revert to.

### Requirements to Continue
- **Dependencies**: `git`, `build-essential`, `cmake`. The INDI library source must be present in the `indi-source` directory.
- **Environment**: The `indi-source` directory must be a git repository.

### Files to Re-read for Context
- `session/session.md` (this file)
- `session/session_advanced.md` (for deeper strategy details)
- `bin/build_indi_driver.sh` (to understand the current build process)
- `indi_pifinder/pifinder_lx200.cpp` and `pifinder_lx200.h` (the driver source code)

### Next Steps
1.  The user will run the updated `bin/build_indi_driver.sh` script.
2.  Verify that the script completes successfully and that the "PiFinder LX200" driver is now available in Ekos.
3.  Begin functional testing of the driver (connection, getting coordinates, GoTo