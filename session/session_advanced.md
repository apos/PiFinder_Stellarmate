## Advanced Strategies & Critical Information

### Build System Deep Dive
The core strategy is to treat the `indi-source` directory as a pristine, read-only build environment that is programmatically and temporarily modified by the `build_indi_driver.sh` script. All driver-specific source code **must** reside in the `indi_pifinder` directory.

-   **CMake Patching**: The `sed` command used to patch the `CMakeLists.txt` is `sed -i "/add_executable(indi_lx200generic/a \    ${SOURCE_ENTRY}" "$TELESCOPE_CMAKE_FILE"`. This injects our source file on a new line immediately after the `add_executable` declaration for the generic driver. While simple, it's effective and avoids complex patching logic. If this fails, it's the first place to debug.
-   **Incremental Build Logic**: The incremental build relies on `git checkout HEAD -- <file>` to revert only the files that the script is about to patch. This is the key to the fast build cycle. It avoids a full `git reset` and preserves the compiled object files in the `build` directory.
-   **XML Installation**: The driver's XML file is installed separately by the script, not by `make install`. It is manually configured with version information scraped from the `indiversion.h` file generated during the build. This decouples our driver's definition from the main `drivers.xml`, preventing conflicts and ensuring our driver is always present without overwriting system configurations.

### Debugging Strategy
-   **Logs are Key**: If the driver fails to load or crashes in Ekos, the first step is always to check the INDI server logs. Run the server from the command line with verbose logging: `indiserver -v -v -v indi_lx200_generic`.
-   **Protocol Ground Truth**: The PiFinder's `pos_server.py` script is the definitive reference for the expected LX200 command-and-response protocol. Any debugging of GoTo, Sync, or status polling should be compared against the implementation in that file.
-   **Reverting Code**: Because the build script now enforces commits within the `indi_pifinder` directory, `git log` and `git checkout <commit_hash>` can be used to easily revert to a last-known-good state if a code change breaks the driver.

### Critical Rules & Saved Memory
-   **NEVER use `add_indi_driver`**: This CMake macro is not for this purpose and will always fail. The correct method is to add the driver's `.cpp` file to the `add_executable(indi_lx200generic ...)` block.
-   **NEVER let `make install` overwrite `drivers.xml`**: The build script now protects against this, but it's a critical failure point to be aware of if the script is ever modified.
-   **DO NOT alter working code without permission**: This applies to the build script itself and any other part of the established workflow.
