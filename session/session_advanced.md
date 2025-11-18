# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: Integration with `indi_lx200generic`

The primary obstacle in this project was the incorrect assumption that our driver, which inherits from the `LX200Generic` class, could be built as a standalone executable and linked against a `lx200generic` library. This is not how the INDI build system is structured.

**The correct, robust approach is as follows:**

1.  **Source Integration**: The `LX200Generic` class and its related drivers are compiled into a single, monolithic executable called `indi_lx200generic`. The correct way to add a new driver of this type is to add its source file to the list of files that make up this executable.
2.  **Automated Patching**: The `build_indi_driver.sh` script is the cornerstone of this strategy. It treats the `indi-source` directory as a temporary build environment and programmatically modifies its `CMakeLists.txt` file. This is achieved using `sed` commands that add our `pifinder_lx200.cpp` file to the `add_executable(indi_lx200generic ...)` definition.
3.  **XML Registration**: The driver's XML file (`indi_pifinder_lx200_driver.xml.in`) must define a new *device* (e.g., "PiFinder LX200"), but point to the existing *driver* executable, which is `LX200 Generic`. The build script then adds this device entry to the main `/usr/share/indi/drivers.xml` file. This allows KStars to display our specific device name while launching the correct shared executable.

## Build System Strategy & CMake Gotchas

*   **`indi-source` is a Build Artifact**: The `indi-source` directory should always be treated as a temporary build location. It should be cleaned (`git reset --hard` and `sudo rm -rf build`) before builds to ensure a pristine state. All source code changes must occur in the local `indi_pifinder` directory.
*   **Problem: Linker Errors (`undefined reference to LX200Generic`)**
    *   **Symptom**: The build fails during the linking stage with errors indicating that the `LX200Generic` class methods are not found.
    *   **Root Cause**: This occurs when attempting to build the driver as a standalone executable (`add_executable`) and link it against a non-existent `lx200generic` library.
    *   **Solution**: The correct solution is not to find a library to link against, but to abandon the standalone executable approach entirely and integrate the source code into the `indi_lx200generic` build target as described in the Core Strategy.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit -a -m "..."` must be made after every significant and successful code modification. This creates a safety net and allows for easy reversion if a new change introduces a regression.
*   **No Commits in `indi-source`**: The `indi-source` directory is external and temporary. It must never be committed to our local repository. All changes to it must be scripted via `build_indi_driver.sh`.