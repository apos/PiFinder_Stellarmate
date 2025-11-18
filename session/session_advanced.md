## Advanced Strategies & Critical Information

### Build System Deep Dive
The current build system is the result of several iterations and is designed for stability and speed.

-   **Robust CMake Patching**: The script no longer uses a fragile regex. It finds the exact line number for `add_executable(indi_lx200generic` using `grep -nF` and then uses `sed` to append our source file on the next line (`sed -i "${LINE_NUM}a \    ..."`). This is highly reliable and easy to debug.
-   **Targeted Installation**: The key to the script's speed is the replacement of `make install`. By using `sudo cp "${indi_source_dir}/build/drivers/telescope/indi_lx200generic" "/usr/bin/"`, we bypass the installation of hundreds of unnecessary files (other drivers, headers, documentation) and avoid any risk to the system's `drivers.xml` file.
-   **The Symlink Mechanism**: It is critical to understand that `indi_lx200generic` is a multi-personality executable. It checks the name it was called with (`argv[0]`) to decide which driver-specific code to activate. Our symbolic link (`indi_pifinder_lx200` -> `indi_lx200generic`) is what enables this mechanism for our driver.

### Debugging Strategy
-   **Logs are Key**: This remains the most important tool. Run the server from the command line with verbose logging to see driver messages: `indiserver -v -v -v indi_pifinder_lx200`.
-   **Protocol Ground Truth**: The PiFinder's `pos_server.py` script is the definitive reference for the expected LX200 command-and-response protocol.
-   **Reverting Code**: The "commit-first" rule is a safety net. If a change to the driver's C++ code breaks functionality, use `git log` in the `indi_pifinder` directory to find the last working commit and `git checkout <hash> -- .` to revert the files.

### Critical Rules & Saved Memory
-   **Commit After Every Code Change**: Non-negotiable. This provides a safety net and a clear history of changes.
-   **Build Strategy is Fixed**: The current `lx200generic` + symlink model is the correct and final approach.
-   **NEVER use `make install`**: The build script must use the targeted `cp` command for installation.
-   **NEVER use `add_indi_driver`**: This CMake command is not suitable for this type of driver.
-   **DO NOT alter working code without permission**: This applies especially to the `build_indi_driver.sh` script, which is now in a stable state.