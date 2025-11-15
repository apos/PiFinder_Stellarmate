# How to Compile or Install the Custom PiFinder INDI Driver

This guide provides a detailed, step-by-step process for either installing a pre-built `pifinder_lx200` INDI driver or compiling it from source on a Raspberry Pi running a Debian-based OS like Stellarmate OS (Bookworm).

The primary goal is to build a minimal INDI driver that:
- Reports the current Right Ascension (RA) and Declination (Dec) from the PiFinder.
- Accepts GoTo commands from INDI clients (like KStars/Ekos) to direct the PiFinder.

This driver does **not** control any motors, tracking, or other mount functions.

---

### Option A: Install Pre-built Driver

If you have a pre-compiled `indi_pifinder_lx200` driver executable and its corresponding XML definition file, you can install them directly without needing to compile from source.

1.  **Copy the pre-built driver executable** to `/usr/bin`.

    ```bash
    sudo cp /path/to/your/prebuilt/indi_pifinder_lx200 /usr/bin/
    ```

2.  **Copy the driver's XML definition file** to `/usr/share/indi`. This file tells INDI clients like Ekos about the new driver.

    ```bash
    sudo cp /path/to/your/prebuilt/indi-source/drivers/telescope/pifinder_lx200.xml /usr/share/indi/
    ```

### Usage of `bin/build_indi_driver.sh`

The script supports several parameters to control its behavior:

```bash
./bin/build_indi_driver.sh [OPTIONS]
```

**Options:**
*   `-a`, `--all`: Performs a full cycle: clones INDI source (if not present), cleans the build directory, compiles the driver, installs it, and then starts an interactive test session.
*   `-c`, `--clean-build`: Removes the existing build directory (`indi-source/build`) before compiling.
*   `-g`, `--get-indi-source`: Clones the official INDI library source code from GitHub into `indi-source/` if it's not already present.
*   `-i`, `--indi-restart`: After a successful build and installation, this option initiates an interactive test session. It will prompt you to start KStars/Ekos, wait for your confirmation, and then capture relevant logs.
*   `-h`, `--help`: Displays the usage instructions and exits.

**Example Workflows:**

1.  **First-time setup (full cycle):**
    ```bash
    ./bin/build_indi_driver.sh --all
    ```

2.  **Clean build and test after code changes:**
    ```bash
    ./bin/build_indi_driver.sh --clean-build --indi-restart
    ```

3.  **Just compile and install (no source download, no test):**
    ```bash
    ./bin/build_indi_driver.sh --clean-build # Or other specific options
    ```
    *(Note: If no options are provided, the script will display help and exit. You must provide at least one option, or use `--clean-build` or `--get-indi-source` or `--indi-restart` for specific actions.)*

---

### Option B: Build the Driver from Source

The `pifinder_lx200` driver can be built and installed using the `build_indi_driver.sh` script located in the `bin/` directory of this project. This script automates all necessary compilation and installation steps, and provides options for managing the INDI source code and performing interactive testing.

---

### Step-by-Step Guide using the Script

1.  **Ensure Prerequisites are Installed:**
    The script assumes you have basic build tools and INDI development libraries installed. If you encounter errors related to missing packages, you may need to install them manually:
    ```bash
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        git \
        cmake \
        libcfitsio-dev \
        libcurl4-gnutls-dev \
        libgsl-dev \
        libjpeg-dev \
        libusb-1.0-0-dev \
        zlib1g-dev \
        libnova-dev # Ensure libnova development files are present
    ```

2.  **Run the Build Script:**
    Navigate to the `PiFinder_Stellarmate` directory and execute the script with your desired options. For a typical development cycle, you might use:
    ```bash
    cd /home/stellarmate/PiFinder_Stellarmate
    ./bin/build_indi_driver.sh --clean-build --indi-restart
    ```
    This will clean the previous build, recompile the driver, install it, and then guide you through the interactive testing phase.

    All script output, including compilation messages and captured KStars logs, will be saved to:
    `/home/stellarmate/PiFinder_Stellarmate/indi_driver_build.log`

---

### Testing the Driver in Ekos (Interactive Session)

If you run the script with the `--indi-restart` option, it will prompt you to manually start KStars/Ekos for testing:

1.  **Follow the script's instructions:** When prompted, open KStars.
2.  **Open the Ekos Profile Wizard** (`Ctrl+P`).
3.  **Create a new equipment profile** or edit an existing one.
4.  In the "Telescope" dropdown, select **"PiFinder LX200"** and click "Add".
5.  Save the profile, then click **"Start INDI"** to launch the INDI server and connect to the driver.
6.  In the INDI Control Panel, go to the "PiFinder LX200" tab, then the "Connection" tab. Ensure the IP address is `10.200.200.3` and the port is `4030` (or your PiFinder's actual IP).
7.  Click **"Connect"**.

If the connection is successful, the driver will connect to the PiFinder's position server, and you should see the RA and Dec values update in the "Main Control" tab. You can then test GoTo commands from the KStars sky map.

After you press ENTER in the script's terminal, it will wait for 30 seconds and then append the KStars log output for the current day to `indi_driver_build.log` for review.