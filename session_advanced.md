### PiFinder INDI Driver Development

This document outlines advanced strategies and key learnings from the development of the `pifinder_lx200` INDI driver.

#### 1. Development Workflow
The development workflow for the `pifinder_lx200` driver has been clarified. All development should be done in the `indi_pifinder` directory. Before building, the development files must be copied to the `indi-source/drivers/telescope` directory.

#### 2. Clean Build
A clean build is essential to ensure that the correct files are used. A clean build consists of removing the build directory, the installed driver binary, and the installed driver XML file.

#### 3. File Naming
The files in the `indi_pifinder` directory should be named `pifinder_lx200.h`, `pifinder_lx200.cpp`, and `indi_pifinder_lx200_driver.xml.in` to match the naming convention expected by the INDI build system.
