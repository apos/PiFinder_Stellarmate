### PiFinder INDI Driver Development: Advanced Strategy

This document outlines the key strategic decisions and workflow patterns established during the development of the `pifinder_lx200` INDI driver.

#### 1. Driver Architecture: Standalone vs. Generic Plugin
The correct architecture for the `pifinder_lx200` driver is a **standalone executable**. This is necessary because the PiFinder `pos_server.py` implements a custom variation of the LX200 command set.

**Implementation:**
*   Create a dedicated `add_executable(indi_pifinder_lx200 ...)` entry in the `indi-source/drivers/telescope/CMakeLists.txt`.
*   Link this executable with the necessary base LX200 implementation files (`lx200driver.cpp`, `lx200telescope.cpp`) to provide the core communication functions.

#### 2. Class Inheritance Strategy
The `PiFinderLX200` class inherits from `LX200Telescope`. This provides the essential LX200 properties and helper functions while allowing for the necessary overrides to implement the PiFinder's specific protocol.

#### 3. Protocol-Driven Development
The most critical lesson learned is that the driver's logic must be dictated by the server-side implementation (`pos_server.py`). Assumptions about standard LX200 commands (like the GoTo sequence or RA/DEC format) proved to be a major source of errors.

**Key Protocol Differences in `pos_server.py`:**
*   **GoTo Sequence:** A GoTo is initiated by sending the target RA (`:Sr...#`) followed by the target DEC (`:Sd...#`). The `Sd` command itself triggers the action. There is **no** separate Slew (`:MA#`) command.
*   **RA Format:** `:SrHH:MM:SS#` (with colons).
*   **DEC Format:** `:Sd[sign]DD*MM:SS#` (e.g., `:Sd+12*34:56#`).

The development process must involve reading and understanding the target server's code to ensure compatibility.

#### 4. Development Workflow
A strict separation is maintained between the development directory (`indi_pifinder`) and the INDI build directory (`indi-source`).

*   **Development Directory:** `/home/stellarmate/PiFinder_Stellarmate/indi_pifinder/` (Version-controlled source code).
*   **Build Directory:** `/home/stellarmate/PiFinder_Stellarmate/indi-source/` (INDI repository clone for compilation).

Before compiling, finalized source files are **copied** from the development directory into `indi-source/drivers/telescope/`. This ensures a clean and reproducible build process.

#### 5. Direct Serial I/O and Thread Safety
When a high-level API (like the methods in `LX200Telescope`) does not support a device's specific command protocol, it is necessary to drop down to a lower level of control.

*   **Low-Level Function:** The correct function for sending raw command strings to the serial port is `tty_write_string`, which is defined in `indicom.h` and implemented in `lx200driver.cpp`.
*   **Thread Safety:** It is **critical** that all calls to `tty_write_string` or any other function performing direct serial I/O are protected by a mutex. The INDI LX200 drivers use a global mutex named `lx200CommsLock`. Every write operation must be wrapped in a `std::unique_lock<std::mutex> guard(lx200CommsLock);` block to prevent race conditions and ensure the driver remains stable under concurrent operations. This is a fundamental pattern for robust INDI driver development.
