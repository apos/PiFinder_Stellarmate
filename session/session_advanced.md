# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: `add_subdirectory` with Correct Installation

The primary obstacle has been a flawed understanding of the INDI build system. The most effective and correct strategy is to treat our driver as a self-contained CMake project and integrate it into the main INDI build using the standard `add_subdirectory` command, coupled with a proper installation procedure.

**The correct, modern approach is as follows:**

1.  **Self-Contained Driver Project**: The `indi_pifinder` directory contains all necessary source files for the driver, including its own `CMakeLists.txt`.
2.  **Driver `CMakeLists.txt`**: This file must define the driver as a `MODULE` library (`add_library(indi_pifinder_lx200 MODULE ...)`). It is responsible for finding its own dependencies and, most importantly, defining the installation rules using `install()` commands for both the driver library (`.so`) and the XML definition file.
3.  **Integration**: The main `indi-source/drivers/telescope/CMakeLists.txt` is modified by the build script to add a single line: `add_subdirectory(indi_pifinder)`.
4.  **Installation**: The `build_indi_driver.sh` script must use `sudo make install` to trigger the installation rules defined in the driver's `CMakeLists.txt`. Manual `cp` commands are brittle and should be avoided.

## Build System Strategy & CMake Gotchas

*   **Single Source of Truth**: The `build_indi_driver.sh` script is the definitive authority for building the driver. It ensures a reproducible build by managing the creation of the driver subdirectory and the patching of the main `CMakeLists.txt`.
*   **`indi-source` is a Build Artifact**: The `indi-source` directory should be treated as a temporary build location. It should be cleaned (`git reset --hard`) before builds to ensure a pristine state. All source code changes must occur in the local `indi_pifinder` directory.
*   **Problem: `lx200generic.h` not found.**
    *   **Symptom**: `fatal error: lx200generic.h: No such file or directory`.
    *   **Solution**: The `add_subdirectory` command does not automatically propagate include directories from the parent project. The most robust solution is to add an explicit, absolute path to the `indi-source/drivers/telescope` directory in the `include_directories()` command within our driver's `CMakeLists.txt`.
*   **Problem: Installation failures.**
    *   **Symptom**: `cp: cannot stat ... No such file or directory`.
    *   **Solution**: When building a `MODULE`, the output filename is `libindi_pifinder_lx200.so`, not `indi_pifinder_lx200`. Furthermore, manual copying is unreliable. The correct solution is to use `install(TARGETS ...)` in the `CMakeLists.txt` and then run `sudo make install` from the build script.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit -a -m "..."` must be made after every significant and successful code modification. This creates a safety net and allows for easy reversion if a new change introduces a regression.
*   **No Commits in `indi-source`**: The `indi-source` directory is external and temporary. It must never be committed to our local repository. All changes to it must be scripted via `build_indi_driver.sh`.