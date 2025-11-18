# PiFinder INDI Driver - Advanced Session Details

## Core Architecture & Build Strategy
The `pifinder_lx200` driver is architected as a subclass of the `LX200Generic` class provided by the core INDI library. This approach is standard for devices that are mostly compliant with the LX200 protocol but have specific custom behaviors.

Our build process leverages this inheritance by not creating a new, standalone INDI executable. Instead, we inject the `pifinder_lx200.cpp` source file directly into the `add_executable()` command for the existing `indi_lx200generic` target in the main INDI `CMakeLists.txt`. The INDI server then uses a symbolic link (`/usr/bin/indi_pifinder_lx200` -> `/usr/bin/indi_lx200generic`) to invoke the generic executable under a different name. The executable checks the name it was called with and dynamically loads the corresponding driver class—in our case, `LX200_PIFINDER`.

This method is efficient as it avoids duplicating the common LX200 code and results in a much faster, incremental build process. The entire workflow is automated by the `bin/build_indi_driver.sh` script.

## Debugging Workflow
A systematic approach is crucial for debugging driver issues.

1.  **Build Failures:** If the compilation itself fails, the primary log is the script's output, captured in `/home/stellarmate/PiFinder_Stellarmate/indi_driver_build.log`. This log will contain the specific C++ compiler errors from `make`.

2.  **Runtime/Connection Failures:**
    -   The `build_indi_driver.sh` script is configured to automatically find the latest INDI log file from either `~/.indi/logs/` or `~/.local/share/kstars/logs/` after a 30-second pause.
    -   It appends this runtime log to the end of the `indi_driver_build.log`. This provides a single file containing both the build and the most recent test run's output.
    -   **Always check the bottom of `indi_driver_build.log` first for runtime errors.**

3.  **Reference Implementation:**
    -   The source code for the `lx200_10micron` driver has been saved to `tmp/lx200_10micron.cpp` and `.h`.
    -   When a function in our driver is not behaving as expected (e.g., `Handshake`, `getBasicData`, `ReadScopeStatus`), the first step is to compare its implementation to the corresponding function in the `lx200_10micron` files. This has proven to be the most effective strategy for resolving issues related to the `LX200Generic` base class.

## Development Cycle
The established development cycle is as follows:
1.  **Identify Issue:** Observe a bug or plan a new feature/reduction.
2.  **Analyze:** Examine logs and compare the relevant code section in `indi_pifinder/` with the `lx200_10micron` reference.
3.  **Modify Code:** Make the necessary changes to `pifinder_lx200.cpp` and/or `pifinder_lx200.h`.
4.  **Commit Changes:** Run `git commit -a -m "feat(driver): Descriptive message"` to save the state. **This is a mandatory step.**
5.  **Build:** Run `bin/build_indi_driver.sh`.
6.  **Test:** Connect via Ekos and observe behavior.
7.  **Repeat:** Continue the cycle until the objective is met.

## Next Iteration Strategy (ACK Failure)
The "Telescope is not responding to ACK!" error persists because the parent `LX200Generic` class sends an ACK character (`0x06`) to probe the connection *before* our overridden `Handshake()` or `getBasicData()` methods are called. The PiFinder `pos_server.py` does not respond to this character, causing the connection to fail.

The `lx200_10micron` driver succeeds because the 10micron mount hardware *does* respond to the ACK.

**New Plan:**
The `LX200Generic` class has a protected method `Connect()`. The most robust solution is to override this method in our `LX200_PIFINDER` class. We will copy the original `Connect()` implementation from `lx200generic.cpp` and simply **remove the section that performs the ACK check**. This will bypass the problematic probe while keeping the rest of the essential connection logic intact. This is a more targeted approach than trying to guess handshake commands and should definitively solve the connection failure.