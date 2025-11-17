# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: Standard System Installation

The primary obstacle has been a series of incorrect assumptions about the INDI build system and standard installation paths on a pre-configured system like Stellarmate. Manual installation via `cp` and using non-standard paths like `/usr/local` proved to be fragile and incorrect.

**The correct, robust approach is as follows:**

1.  **Self-Contained Driver Project**: The `indi_pifinder` directory contains all necessary source files for the driver, including its own `CMakeLists.txt`.
2.  **Integration**: The main `indi-source/drivers/telescope/CMakeLists.txt` is modified by the build script to add a single line: `add_subdirectory(indi_pifinder)`.
3.  **Configuration**: The `build_indi_driver.sh` script **must** configure the build using `cmake -DCMAKE_INSTALL_PREFIX=/usr ..`. This flag tells CMake to prepare the build for installation into the standard system directories (`/usr/lib`, `/usr/share`, etc.), which aligns with the existing `apt`-managed INDI installation.
4.  **Installation**: The script must use `sudo make install`. This is the canonical way to install a CMake project. It correctly places all files (libraries, XML definitions, headers) into the appropriate subdirectories defined by the install prefix and the INDI build system's own logic.

## Build System Strategy & CMake Gotchas

*   **`indi-source` is a Build Artifact**: The `indi-source` directory should be treated as a temporary build location. It should be cleaned (`git reset --hard` and `sudo rm -rf build`) before builds to ensure a pristine state. All source code changes must occur in the local `indi_pifinder` directory.
*   **Problem: Driver not visible in Ekos.**
    *   **Symptom**: The build succeeds, `make install` reports that the driver's `.so` and `.xml` files are installed, but the driver does not appear in the Ekos device list.
    *   **Root Cause**: A corrupted, empty, or malformed `..._driver.xml.in` template file. CMake's `configure_file` command can fail silently on a bad input, resulting in an empty output XML file. The INDI server will see this empty file and simply ignore it without an error message.
    *   **Solution**: Ensure the `.xml.in` file contains a valid `<drivers>` structure with the correct executable path variable (e.g., `@CMAKE_INSTALL_FULL_LIBDIR@/libindi_pifinder_lx200.so`).
*   **Problem: `make install` builds all drivers.**
    *   **Symptom**: The build process is very slow on the first run after a clean.
    *   **Explanation**: This is the expected and unavoidable behavior of the INDI build system's `install` target. It has a dependency on the `all` target, which builds every defined component.
    *   **Mitigation**: This is a one-time cost. Subsequent builds without the `--clean-build` flag will be incremental and much faster, as `make` will only recompile the files that have actually changed. This is the necessary trade-off for a correct and robust installation that respects the existing system.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit -a -m "..."` must be made after every significant and successful code modification. This creates a safety net and allows for easy reversion if a new change introduces a regression.
*   **No Commits in `indi-source`**: The `indi-source` directory is external and temporary. It must never be committed to our local repository. All changes to it must be scripted via `build_indi_driver.sh`.
