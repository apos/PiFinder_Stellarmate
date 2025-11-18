## Advanced Strategies & Critical Information

### Build System Deep Dive
The XML handling and log management are now critical parts of the build script.

-   **Direct XML Injection**: The script uses the following `sed` command to add our driver: `sudo sed -i "/<devGroup group=\"Telescopes\">/a ${DRIVER_XML_ENTRY}" "${SYSTEM_DRIVERS_XML}"`. This finds the line containing `<devGroup group="Telescopes">` and **a**ppends our driver's XML block on the next line. The XML block itself is stored in a variable and escaped for `sed`.
-   **Idempotency**: The script prevents duplicate XML entries by first running `grep -qF "PiFinder LX200" "${SYSTEM_DRIVERS_XML}"`. If this command succeeds (meaning the entry is already there), the `sed` command is skipped. This makes the script safe to run multiple times.
-   **No More Separate XML**: The old method of copying `pifinder_lx200_driver.xml` to `/usr/share/indi` is now gone. It was incorrect and has been completely replaced by the injection logic.
-   **KStars Log Management Details**: The script now clears *dated log directories* within `~/.local/share/kstars/logs/` before the 30-second wait. This ensures that only logs relevant to the current test session are captured. After the wait, it dynamically finds the *newest log file* (which will be within a newly created dated subdirectory) and copies it to a timestamped file in `.gemini/tmp/` for easy access and review.

### Debugging Strategy
-   **Driver Not in List**: If the driver is still not visible in Ekos after running the script and restarting the server, the very first step is to manually inspect the main XML file: `cat /usr/share/indi/drivers.xml | grep "PiFinder LX200"`. If the entry is not there, the `sed` command in the build script failed. If it is there, the problem might be with XML syntax or INDI server caching.
-   **Logs are Key**: This remains the most important tool for runtime issues. Run the server from the command line with verbose logging to see driver messages: `indiserver -v -v -v indi_pifinder_lx200`. The automated log copying will provide a snapshot of this output.
-   **Reverting Code**: The "commit-first" rule is a safety net. All changes are committed, so `git checkout` can be used to revert to a known-good state.

### Critical Rules & Saved Memory
-   **Commit After Every Code Change**: Non-negotiable.
-   **The Driver MUST be in `drivers.xml`**: This is the core lesson learned. Separate XML files in `/usr/share/indi` are not sufficient for a driver to appear in the main Ekos list.
-   **Build Strategy is Fixed**: The current `lx200generic` + symlink + direct XML injection model is the correct and final approach.
-   **NEVER use `make install`**: The build script must use the targeted `cp` command for installation.