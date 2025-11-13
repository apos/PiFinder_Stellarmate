### PiFinder INDI Driver Development

This document outlines advanced strategies and key learnings from the development of the `pifinder_lx200` INDI driver.

#### 1. The Golden Rule: Emulate, Don't Guess
When working within a large, established framework like INDI, the most effective strategy for implementing new functionality is to find a similar, working example and adapt its patterns. Attempting to deduce complex API usage from header files alone is inefficient and prone to error.

*   **Problem:** Incorrectly handling JNow-to-J2000 coordinate conversion.
*   **Failed Approach:** Manually implementing the conversion using `libnova` within the driver.
*   **Successful Strategy:** Analyzing the parent class (`lx200telescope.cpp`) revealed that the base framework handles the conversion automatically when the `NewRaDec()` function is called. This simplified the driver logic immensely.

#### 2. Trace Implementation Logic Up the Inheritance Chain
When a child class overrides a virtual function (like `ReadScopeStatus`), the parent class's implementation of that same function is the best possible reference for correct API usage. The base implementation reveals the expected sequence of operations, the correct property names, and the proper functions to call for updating the framework.

#### 3. Targeted Compilation for Efficiency
The INDI build system is large. Compiling the entire project is time-consuming, especially on resource-constrained devices like a Raspberry Pi. To accelerate the development cycle, compile only the specific target you are working on.

*   **Command:** `make <target_name>`
*   **Example:** `make indi_pifinder_lx200`

#### 4. Understanding Linker Errors
"Undefined reference" errors during the linking phase mean that a function was declared in a header file but never defined in a source file.

*   **Problem:** `undefined reference to 'PiFinderLX200::updateProperties()'`
*   **Solution:** The `updateProperties()` function was declared in `pifinder_lx200.h` but had been removed from `pifinder_lx200.cpp`. Removing the declaration from the header file resolved the issue.