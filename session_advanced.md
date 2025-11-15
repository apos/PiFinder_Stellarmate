### PiFinder INDI Driver Development: Advanced Strategy

This document outlines the key strategic decisions and workflow patterns established during the development of the `pifinder_lx200` INDI driver.

#### 1. Driver Architecture: Standalone vs. Generic Plugin
The initial attempt to integrate the `pifinder_lx200` driver into the `lx200generic` executable was incorrect. This approach is designed for drivers that are minor variations of the standard LX200 protocol and can be selected at runtime by the `lx200generic` loader.

The correct and final architecture for the `pifinder_lx200` driver is a **standalone executable**. This is necessary because the PiFinder `pos_server.py` implements a custom variation of the LX200 command set (e.g., the RA format in the GoTo command).

**Implementation:**
*   Create a dedicated `add_executable(indi_pifinder_lx200 ...)` entry in the `indi-source/drivers/telescope/CMakeLists.txt`.
*   Link this executable with the necessary base LX200 implementation files (`lx200driver.cpp`, `lx200telescope.cpp`) to provide the core communication functions.

#### 2. Class Inheritance Strategy
To avoid re-implementing the entire LX200 protocol from scratch, the `PiFinderLX200` class inherits from `LX200Telescope`.

*   **`LX200Telescope` (Correct):** This base class provides the essential LX200 functions (`setObjectDEC`, `Slew`, `ReadScopeStatus`, etc.) and properties without the dynamic loading mechanism of its child, `LX200Generic`. This is the ideal parent class for a standalone driver that speaks a variant of the LX200 protocol.
*   **`LX200Generic` (Incorrect for this use case):** This class is designed to be a multi-purpose driver that loads other LX200 variants. Inheriting from it pulls in unnecessary complexity and is counter to the standalone driver goal.
*   **`INDI::Telescope` (Incorrect for this use case):** Inheriting directly from the base telescope class would require re-implementing all LX200 command parsing and formatting from the ground up, which is inefficient.

#### 3. Development Workflow
A strict separation is maintained between the development directory and the INDI build directory.

*   **Development Directory:** `/home/stellarmate/PiFinder_Stellarmate/indi_pifinder/`
    *   This directory is under version control (git).
    *   All coding, modifications, and testing of the driver's C++ and XML files occur here.
*   **Build Directory:** `/home/stellarmate/PiFinder_Stellarmate/indi-source/`
    *   This is a clone of the official INDI repository, used as the build environment.
    *   Before compiling, the finalized source files (`pifinder_lx200.cpp`, `pifinder_lx200.h`, `indi_pifinder_lx200_driver.xml.in`) are **copied** from the development directory into `indi-source/drivers/telescope/`.
    *   The `CMakeLists.txt` within `indi-source` is modified to include the driver in the build.

This workflow ensures that the development files remain clean and version-controlled, while the build environment can be easily updated or reset without affecting the source code.