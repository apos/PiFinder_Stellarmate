## PiFinder LX200 INDI Driver - Session State

### Main Requirements and goal (do not change or alter)
- PiFinder is a device which can do live platesolving an has an python server which implements parts of the LX200 protkoll: it reports the position, can accept a GoTo and an align. 
- Stellarmate is an debian based OS which uses INDI to communicate with devices. This is done by indi-server which is under the command of a running KStars/EKOS. 
- There is an INDI driver that partially works with PiFinder: 10micron_lx200. But this only the case for the basic functionality, like beeing adhered from lx200_generic, establishing the connection over network, getting a posistion. 10micron has a lot of functionality which PiFinder not has, also some funcitons like goto or align do not work out of the box and need refactoring to match PiFinders pos_server.py.

### Current Status

The previous fix to the `Handshake()` function was incorrect. A test with the official `LX200 10micron` driver showed that it connects successfully, proving the `ACK` handshake is not the root cause of the connection failure. The actual problem is that our `pifinder_lx200` driver, being a copy, is using numerous 10Micron-specific commands (e.g., `#:Ginfo#`) that the PiFinder's simple LX200 server does not support. The driver is failing immediately after the handshake when it tries to get the mount's status using these custom commands.



The new, correct strategy is to strip out all 10Micron-specific functionality and make the driver behave like a true `LX200Generic` device.



### Altered Files & Rationale

- **`indi_pifinder/pifinder_lx200.cpp`**:

    - **Why (Handshake Revert):** The previous change to `Handshake()` was reverted because it was based on a wrong diagnosis. The original handshake logic is kept.

    - **Why (New Plan):** The functions `getBasicData()` and `ReadScopeStatus()` will be modified to call their parent `LX200Generic` implementations. This will force the driver to use standard LX200 commands (`:GR#`, `:GD#`) which are supported by the PiFinder server, instead of the unsupported 10Micron commands.



### Key Concepts & Strategies

- **Inheritance Over Implementation**: Instead of using the copied, specialized 10Micron code, we will rely on the robust, standard implementation from the `LX200Generic` parent class for core telescope functions. This is the key to compatibility.

- **Command Compatibility**: The driver must only use commands that are explicitly supported by the target device (`pos_server.py`).



### Next Steps

1.  **Modify `getBasicData()`**: In `pifinder_lx200.cpp`, replace the entire body of the `getBasicData()` function with a single call to the parent version: `LX200Generic::getBasicData();`.

2.  **Modify `ReadScopeStatus()`**: In `pifinder_lx200.cpp`, replace the entire body of the `ReadScopeStatus()` function with a single call to the parent version: `return LX200Generic::ReadScopeStatus();`.

3.  Commit the changes.

4.  Run a `--clean-build` to ensure the new logic is compiled.

5.  Test the connection in Ekos.