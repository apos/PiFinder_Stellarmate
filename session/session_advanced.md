## Advanced Strategies & Critical Information

### Build System Deep Dive (Standalone Driver)
The new strategy requires a more robust integration with the INDI build system than the previous file-copying approach.

-   **`add_subdirectory`**: The core of the new build process will be to use the `add_subdirectory` command in the main `indi-source/drivers/telescope/CMakeLists.txt`. This command will tell CMake to descend into our `indi_pifinder` directory and process its own `CMakeLists.txt` file. This is the standard, correct way to add a new component to a CMake-based project.
-   **Driver `CMakeLists.txt`**: The `indi_pifinder/CMakeLists.txt` file will be responsible for:
    -   Defining the executable: `add_executable(pifinder_lx200 pifinder_lx200.cpp)`
    -   Linking against the necessary INDI libraries: `target_link_libraries(pifinder_lx200 PRIVATE INDI::INDI_LX200_GENERIC)` (or similar, based on analysis).
    -   Installing the executable to the correct location.
-   **Build Script (`build_indi_driver.sh`)**: The script's role will change significantly. Instead of copying source files, it will be responsible for:
    1.  Temporarily adding the `add_subdirectory(indi_pifinder)` line to the main `CMakeLists.txt`.
    2.  Running `cmake` and `make` from the `indi-source/build` directory.
    3.  Installing the final driver XML file.
    4.  Using `git` to manage the temporary changes to the `indi-source` tree, ensuring it remains clean between builds.

### Debugging Strategy
-   **Logs are Key**: This remains unchanged. Verbose logs from `indiserver` are the primary tool for debugging runtime issues.
-   **Compilation Errors**: Debugging will now be focused on the `indi_pifinder/CMakeLists.txt` file and the C++ source. Linker errors will indicate missing `target_link_libraries`, and compiler errors will point to issues in the `.cpp`/`.h` files.

### CRITICAL RULES & SAVED MEMORY (PRESERVED)
-   **Standalone is the Goal**: The driver **must** be built as its own executable.
-   **Use the Build System**: Do not manually copy files into the `indi-source` tree. Use CMake's features (`add_subdirectory`) to integrate the driver correctly.
-   **Reference `lx200_10micron`**: When in doubt about C++ implementation or CMake configuration, refer to the `lx200_10micron` driver as the ground truth.
-   **NEVER use `add_indi_driver`**: This CMake macro is not for this purpose and will always fail. The correct method is to add the driver's `.cpp` file to the `add_executable(indi_lx200generic ...)` block.
-   **NEVER let `make install` overwrite `drivers.xml`**: The build script now protects against this, but it's a critical failure point to be aware of if the script is ever modified.
-   **DO NOT alter working code without permission**: This applies to the build script itself and any other part of the established workflow.