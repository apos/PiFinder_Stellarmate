## Advanced Strategies & Critical Information

### Core Strategy: Inheritance for Compatibility
The fundamental issue with the driver was that it was a clone of the `lx200_10micron` driver and therefore used many proprietary commands that the PiFinder's `pos_server.py` does not understand. The connection failed immediately after the handshake when the driver tried to query the mount status with a 10Micron-specific command (`#:Ginfo#`).

The definitive solution is to force the `pifinder_lx200` driver to behave as a true generic LX200 device. This is achieved by modifying our child class (`LX200_PIFINDER`) to call the parent class's (`LX200Generic`) methods for core functionality, rather than using its own overridden, specialized versions.

-   **`getBasicData()`**: This function is called once upon connection. The specialized version in our driver was full of unsupported commands. It will be replaced with a simple call to `LX200Generic::getBasicData();`.
-   **`ReadScopeStatus()`**: This function is called repeatedly to get the telescope's position. The specialized version used the `#:Ginfo#` command. It will be replaced with a call to `return LX200Generic::ReadScopeStatus();`, which correctly uses the standard `:GR#` (Get RA) and `:GD#` (Get Dec) commands.

### Debugging Strategy
-   **Log Analysis**: The primary debugging tool remains the KStars/INDI logs. After the next build, the logs should show the driver sending standard `:GR#` and `:GD#` commands. If the connection still fails, the logs will be essential to see the server's response or lack thereof.
-   **Clean Builds**: Because the build system can cache compiled objects, it is critical to use the `--clean-build` flag with the build script after making code changes to ensure they are actually compiled and linked.

### Critical Rules & Saved Memory
-   **Commit After Every Code Change**: Non-negotiable.
-   **Use Generic LX200 Commands**: The driver must not use any commands that are not part of the basic LX200 protocol supported by the PiFinder server. Relying on the `LX200Generic` parent class is the safest way to ensure this.