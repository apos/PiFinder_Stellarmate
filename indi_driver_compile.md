# How to Compile the Custom PiFinder INDI Driver

This guide provides a detailed, step-by-step process for downloading the required dependencies, preparing the source code, and compiling the `pifinder_lx200` INDI driver on a Raspberry Pi running a Debian-based OS like Stellarmate OS (Bookworm).

The primary goal is to build a minimal INDI driver that:
- Reports the current Right Ascension (RA) and Declination (Dec) from the PiFinder.
- Accepts GoTo commands from INDI clients (like KStars/Ekos) to direct the PiFinder.

This driver does **not** control any motors, tracking, or other mount functions.

---

### Step 1: Install Prerequisites

First, you must install the necessary build tools and development libraries. These are required to compile the INDI library and the custom driver.

Execute the following command in your terminal:

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
    libnova-dev \
    libusb-1.0-0-dev \
    zlib1g-dev
```

---

### Step 2: Download the Full INDI Library Source Code

The driver must be compiled against the complete source code of the INDI library.

1.  **Clone the official INDI repository.** We will place it in your home directory in a folder named `indi-source`.

    ```bash
git clone https://github.com/indilib/indi.git ~/indi-source
```

---

### Step 3: Prepare the Custom Driver Files

The `PiFinder_Stellarmate` project contains the source code for the custom `pifinder_lx200` driver. These files need to be copied into the INDI source tree you just downloaded.

1.  **Navigate to your `PiFinder_Stellarmate` project directory.**

2.  **Copy the `indi_pifinder` directory** into the telescope drivers section of the INDI source code. This directory contains the C++ source (`.cpp`), header (`.h`), and XML definition file for our driver.

    ```bash
cp -r indi_pifinder/* ~/indi-source/drivers/telescope/
```

---

### Step 4: Build the Driver

Now we will configure the build system and compile only our specific driver.

1.  **Create a build directory** inside the `indi-source` folder and change into it.

    ```bash
mkdir -p ~/indi-source/build
cd ~/indi-source/build
```

2.  **Run CMake to prepare the build files.** This command analyzes your system and the INDI source code to generate the necessary Makefiles.

    ```bash
cmake ..
```

3.  **Compile the `pifinder_lx200` driver.** This command will build just our driver, which is much faster than building the entire INDI library.

    ```bash
make indi_pifinder_lx200
```

    If successful, you will find the compiled driver executable at `~/indi-source/build/drivers/telescope/indi_pifinder_lx200`.

---

### Step 5: Install the Driver

After a successful compilation, the driver files must be copied to the system-wide INDI directories so that the INDI server can find and use them.

1.  **Copy the compiled driver executable** to `/usr/bin`.

    ```bash
sudo cp drivers/telescope/indi_pifinder_lx200 /usr/bin/
```

2.  **Copy the driver's XML definition file** to `/usr/share/indi`. This file tells INDI clients like Ekos about the new driver.

    ```bash
sudo cp ../drivers/telescope/pifinder_lx200.xml /usr/share/indi/
```

---

### Step 6: Test the Driver in Ekos

The driver is now installed. You can test it using KStars and Ekos.

1.  **Start KStars.**
2.  **Open the Ekos Profile Wizard** (`Ctrl+P`).
3.  **Create a new equipment profile.**
4.  In the "Telescope" dropdown, select **"PiFinder LX200"** and click "Add".
5.  Save the profile, then click **"Start INDI"**.
6.  In the INDI Control Panel, go to the "PiFinder LX200" tab, then the "Connection" tab. Ensure the IP address is `127.0.0.1` and the port is `4030`.
7.  Click **"Connect"**.

If the connection is successful, the driver will connect to the PiFinder's position server, and you should see the RA and Dec values update in the "Main Control" tab. You can then test GoTo commands from the KStars sky map.
