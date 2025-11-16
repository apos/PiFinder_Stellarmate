# PiFinder INDI Driver - Advanced Strategies

This document outlines higher-level strategies and critical technical details for the `pifinder_lx200` driver development.

## Core Strategy: Inherit and Override

The primary obstacle has been API incompatibility and incorrect C++ object orientation. The most effective strategy is to abandon building from a generic base class and instead inherit from the specific `LX200Telescope` class.

**The correct, modern approach is as follows:**

1.  **Inheritance**: The driver class (`PiFinder`) *must* inherit from the appropriate INDI base class (`LX200Telescope`) to gain the necessary telescope functionality and properties. This is the most critical lesson learned.
    *   **Correct:** `class PiFinder : public LX200Telescope`
    *   **Incorrect:** `class PiFinder : public INDI::DefaultDevice`

2.  **Overriding**: Key virtual methods from the base class, such as `Handshake()` and `ReadScopeStatus()`, must be correctly marked with the `virtual` keyword and the `override` specifier in the header file. This ensures the custom implementation is called.

3.  **Property Usage**: Use the properties provided by the base class (e.g., `EqNP`, `Connection`, `EqN`) directly. Do not re-declare them in the child class, as this leads to compilation errors and incorrect behavior.

## Build System Strategy

*   **Single Source of Truth**: The `build_indi_driver.sh` script is the definitive authority for building the driver. It ensures a reproducible build by managing all file copy and patching operations.
*   **No Manual `indi-source` Edits**: To avoid inconsistencies, the `indi-source` directory should be treated as a temporary build artifact. All source code changes must occur in the `indi_pifinder` directory. The build script will handle syncing them to the build location.

## Debugging Strategy

1.  **Reference Implementation**: The `lx200telescope.cpp` and `.h` files serve as the primary reference for the base class implementation, revealing which methods can be overridden and which properties are available.
2.  **Protocol Definition**: The `pos_server.py` script, located in `indi_pifinder/`, is the absolute source of truth for the LX200 command-and-response protocol that the PiFinder expects. The driver must match this protocol.

## Version Control Policy

*   **Atomic Commits**: To prevent the loss of working code, a `git commit -a -m "..."` must be made after every significant and successful code modification. This creates a safety net and allows for easy reversion if a new change introduces a regression. This rule was established after multiple failed refactoring attempts made it difficult to return to a known-good state.
