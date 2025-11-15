# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: Mimic a Working Reference

The primary obstacle has been API drift between the original driver code and the current `indilib` source. The most effective strategy is to abandon trial-and-error and strictly adhere to the patterns found in a known-good, modern reference driver: `lx200_10micron`.

**The correct, modern approach is as follows:**

1.  **Property Declaration**:
    *   In the driver's header file (`.h`), declare properties as direct C-style struct members, **not** C++ wrapper classes or pointers. This is the most critical lesson learned.
    *   **Correct:** `ISwitchVectorProperty ConnectionSP;`
    *   **Incorrect:** `INDI::PropertySwitch ConnectionSP;`
    *   **Incorrect:** `ISwitchVectorProperty *ConnectionSP;`

2.  **Property Initialization (`initProperties`)**:
    *   Use the `IUFill...` family of helper functions (e.g., `IUFillSwitchVector`) to initialize the struct members.
    *   Pass the properties to these functions using the `&` operator (e.g., `IUFillSwitchVector(&ConnectionSP, ...)`).

3.  **Linking**:
    *   Identify all external library dependencies (like `libnova` for astronomical calculations) by observing the reference driver.
    *   Ensure these libraries are explicitly linked in the `CMakeLists.txt` file via `target_link_libraries`.

## Build System Strategy

*   **Single Source of Truth**: The `build_indi_driver.sh` script is the definitive authority for building the driver. It ensures a reproducible build by managing all file copy and patching operations.
*   **No Manual `indi-source` Edits**: To avoid inconsistencies, the `indi-source` directory should be treated as a temporary build artifact. All source code changes must occur in the `indi_pifinder` directory. The build script will handle syncing them to the build location.

## Debugging Strategy

1.  **Reference Implementation**: The `lx200_10micron` driver, located in `indi-source/drivers/telescope/`, serves as the primary reference for a simple, modern, and functional LX200-style driver.
2.  **Protocol Definition**: The `pos_server.py` script, located in `indi_pifinder/`, is the absolute source of truth for the LX200 command-and-response protocol that the PiFinder expects.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit -a -m "..."` must be made after every significant and successful code modification. This creates a safety net and allows for easy reversion if a new change introduces a regression. This rule was established after multiple failed refactoring attempts made it difficult to return to a known-good state.