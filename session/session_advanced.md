## PiFinder INDI Driver - Advanced Session Details

## Core Architecture & Build Strategy
The `pifinder_lx200` driver is architected as a subclass of the `LX200Generic` class provided by the core INDI library. Our build process injects the `lx200_pifinder.cpp` source file directly into the `add_executable()` command for the existing `indi_lx200generic` target in the main INDI `CMakeLists.txt`. The INDI server then uses a symbolic link (`/usr/bin/indi_pifinder_lx200` -> `/usr/bin/indi_lx200generic`) to invoke the generic executable under a different name. The executable checks the name it was called with and dynamically loads the corresponding driver class—in our case, `LX200_PIFINDER`.

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
    -   When a function in our driver is not behaving as expected (e.g., `Handshake`, `getBasicData`, `ReadScopeStatus`), the first step is to compare its implementation to the corresponding function in the `lx200_10micron` files. This helps understand expected LX200 commands and responses.

## Development Cycle (Modified)
The established development cycle is as follows, with a critical change in focus:
1.  **Identify Issue:** Observe a bug or plan a new feature.
2.  **Analyze (`pos_server.py` and `lx200_pifinder.cpp`):** Examine the relevant sections of `pos_server.py` and `lx200_pifinder.cpp` (the C++ driver is *read-only* from now on) to understand the expected LX200 command/response patterns.
3.  **Modify Code (`tmp/pos_server.py` only):** Make the necessary changes *only* to `tmp/pos_server.py` to correctly handle the LX200 commands. No modifications to `lx200_pifinder.cpp`.
4.  **Copy and Restart PiFinder:** Copy the modified `tmp/pos_server.py` to the PiFinder installation (`/home/stellarmate/PiFinder/python/PiFinder/pos_server.py`) and restart the `pifinder` service (`sudo systemctl restart pifinder`). This ensures the PiFinder is running the latest Python code.
5.  **Commit Changes:** Run `git commit -a -m "feat(pos_server): Descriptive message"` to save the state of `tmp/pos_server.py` and session files. **This is a mandatory step for `pos_server.py` changes.**
6.  **Build INDI Driver:** Run `bin/build_indi_driver.sh`. This recompiles the *unmodified* C++ driver and ensures the latest `pos_server.py` is in use.
7.  **Test:** Connect via Ekos and observe behavior. Specifically, verify that new commands are handled without errors and that existing RA/DEC polling is stable.
8.  **Repeat:** Continue the cycle until the objective is met.

## Current Status and Next Steps
All previous modifications to `indi_pifinder/lx200_pifinder.cpp` have been reverted, ensuring the C++ driver is in its original state. The `pos_server.py` now needs to be robustly updated to correctly respond to all LX200 commands sent by the INDI driver, particularly for getting and setting location and time, as current implementations are causing errors.

**Next Steps:**
1.  **Re-read `tmp/pos_server.py`:** Confirm current content, including existing implementations for `Gg`, `SG`, and `Sg`.
2.  **Re-verify `get_telescope_ra` and `get_telescope_dec`:** Ensure these functions in `tmp/pos_server.py` are robust and correctly formatted, addressing the `CMD read ERROR -4` for RA.
3.  **Implement `get_telescope_latitude` (`:Gt#`):** Add this function to `tmp/pos_server.py` to return the current latitude from `shared_state.location().lat`.
4.  **Implement `get_telescope_local_time` (`:GL#`):** Add this function to `tmp/pos_server.py` to return the current local time from `shared_state.datetime()`.
5.  **Implement `get_telescope_utc_date` (`:GG#`):** Add this function to `tmp/pos_server.py` to return the current UTC date from `shared_state.datetime()`.
6.  **Refine `parse_sg_command` (`:SG...#`) and `parse_s_g_command` (`:Sg...#`):** Ensure these functions in `tmp/pos_server.py` correctly use `shared_state.set_local_datetime()` and `shared_state.set_location()` respectively, and provide proper LX200 responses (e.g., "1" for success) to prevent INDI driver errors.
7.  **Update `lx_command_dict`:** Add mappings for all new `GET` and `SET` commands.
8.  **Copy and Restart PiFinder:** Copy the modified `tmp/pos_server.py` to the PiFinder installation (`/home/stellarmate/PiFinder/python/PiFinder/pos_server.py`) and restart the `pifinder` service (`sudo systemctl restart pifinder`).
9.  **Rebuild and Test INDI Driver:** Rebuild the INDI driver (`./bin/build_indi_driver.sh`) and conduct thorough functional testing with Ekos. Check `indi_driver_build.log` and KStars logs for success/failure.