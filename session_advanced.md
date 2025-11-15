# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: API Modernization

The primary obstacle has been the API drift between the original, functional driver code and the current `indilib` source tree. The old code relied on direct struct member manipulation (e.g., `Property.name = "..."`, `Property.s = IPS_OK`), a practice that has been deprecated and removed.

**The correct, modern approach is as follows:**

1.  **Initialization (`initProperties`)**:
    *   Use the `IUFill...` family of helper functions (e.g., `IUFillSwitchVector`, `IUFillNumberVector`) to define and initialize properties and their elements. This is the most robust method for creating the required data structures.
    *   Use `setDriverInterface(TELESCOPE_INTERFACE)` to declare the driver's primary capability instead of the old `SetCapability` method.
    *   Register the properties with the driver using `defineSwitch()` and `defineNumber()`.

2.  **State Management (e.g., `ISNewSwitch`)**:
    *   Do not modify property state directly (e.g., `ConnectionS[0].s = ISS_ON`).
    *   Instead, read the incoming desired state from the `states` array using helpers like `IUFindSwitch(states, names, n, "SWITCH_NAME")`.
    *   After performing the driver logic (e.g., `Handshake()`), update the property's state variable (`ConnectionSP.s = IPS_OK`).
    *   Finally, notify the INDI server of the change using `IDSetSwitch(&ConnectionSP, nullptr)`.

## Build System Strategy

*   **Single Source of Truth**: The `build_indi_driver.sh` script is the definitive authority for building the driver. It ensures a reproducible build by managing all file copy and patching operations.
*   **No Manual `indi-source` Edits**: To avoid inconsistencies, the `indi-source` directory should be treated as a temporary build artifact. All source code changes must occur in the `indi_pifinder` directory. The build script will handle syncing them to the build location.

## Debugging Strategy

1.  **Reference Implementation**: The `lx200_10micron` driver, located in `indi-source/drivers/telescope/`, serves as the primary reference for a simple, modern, and functional LX200-style driver. When encountering API usage errors or logical issues, compare the `pifinder_lx200.cpp` implementation to `lx200_10micron.cpp`.
2.  **Protocol Definition**: The `pos_server.py` script, provided by the user and located in `indi_pifinder/`, is the absolute source of truth for the LX200 command-and-response protocol that the PiFinder expects. All commands sent by the driver (e.g., `:GR#`, `:GD#`, `:Sr...#`) must exactly match the format parsed by this script.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit` must be made after every significant and successful change. This creates a safety net and allows for easy reversion if a new change introduces a regression. This rule was established after a near-loss of the original working C++ file.
