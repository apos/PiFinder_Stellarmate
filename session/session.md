## PiFinder LX200 INDI Driver - Session State

### Main Requirements and goal (do not change or alter)
- PiFinder is a device which can do live platesolving an has an python server which implements parts of the LX200 protkoll: it reports the position, can accept a GoTo and an align. 
- Stellarmate is an debian based OS which uses INDI to communicate with devices. This is done by indi-server which is under the command of a running KStars/EKOS. 
- There is an INDI driver that partially works with PiFinder: 10micron_lx200. But this only the case for the basic functionality, like beeing adhered from lx200_generic, establishing the connection over network, getting a posistion. 10micron has a lot of functionality which PiFinder not has, also some funcitons like goto or align do not work out of the box and need refactoring to match PiFinders pos_server.py. 

### Current Status
**COURSE CORRECTION:** The previous strategy of integrating the driver into `indi_lx200generic` was incorrect and has been abandoned.

The new, primary goal is to build a **standalone `pifinder_lx200` INDI driver**. This driver should be a separate executable, modeled after the existing `lx200_10micron` driver in the INDI source tree.

### Altered Files & Rationale
- All previous changes related to the `lx200generic` integration strategy are now considered obsolete and will be reverted or replaced.

### Key Concepts & Strategies
- **Build Strategy**: The new strategy is to define our driver as a standalone executable within the INDI build system. This will involve:
    1.  Creating a `CMakeLists.txt` file in the `indi_pifinder` directory that correctly defines the `pifinder_lx200` executable and its dependencies.
    2.  Modifying the `build_indi_driver.sh` script to use CMake's `add_subdirectory` command to include our driver in the main `indi-source` build process.
    3.  Ensuring the driver's XML file (`indi_pifinder_lx200_driver.xml.in`) points to the correct standalone executable name.
- **Model Driver**: The `lx200_10micron` driver will be used as the reference for the correct C++ class structure and CMake configuration.

### Requirements to Continue
- **Dependencies**: `git`, `build-essential`, `cmake`. The INDI library source must be present in `indi-source`.
- **Environment**: The `indi-source` directory must be a git repository.

### Files to Re-read for Context
- `session/session.md` (this file)
- `session/session_advanced.md` (for deeper strategy details)
- `indi-source/drivers/telescope/lx200_10micron.cpp` (as a model)
- `indi-source/drivers/telescope/CMakeLists.txt` (to understand how standalone drivers are built)
- `indi_pifinder/pifinder_lx200.cpp` and `pifinder_lx200.h` (the driver source code)

### Next Steps
1.  **Analyze**: Thoroughly examine the `lx200_10micron` driver's source and CMake configuration.
2.  **Plan**: Formulate a detailed plan to adapt our `pifinder_lx200` driver and build scripts to match the standalone model.
3.  **Propose**: Present the plan to you for approval before implementing any changes.