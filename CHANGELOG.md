# Changelog

All notable changes to this project are documented in this file. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Control Center warning on devices that boot from NVMe/USB (root label `SM_ROOT*` but not `SM_ROOT`): a SMOS update can rewrite `cmdline.txt`/`fstab` to `LABEL=SM_ROOT`, which such a disk does not carry, so the device never boots again unless `bin/smos-post-update.sh` ran before the reboot (seen on a Pi 4, SMOS 2.3.0 -> 2.4.0, #561). The card names the script and `--updatesd`, and the SD/USB rescue path

### Fixed

- The post-SMOS-update guard page: an empty password field now says to enter the stellarmate system password (it used to send the request and answer "Wrong password."), a hint names the password, and browser autofill is switched off so a saved password for another device is not filled in
- `bin/restore_after_smos_update.sh` (Pi path) now also installs the post-SMOS-update guard user unit; previously only the setup did, so a Pi that was only ever restored with this script had no guard for its next SMOS update
- Install/Update tile: the step list (the 10 phases with check marks) could stay hidden for a whole run when the page's one-time init fetch of `/state` happened while the Control Center was still restarting - the labels were never loaded again. `/log` now also carries `phases` and every poll refreshes the labels
- INDI driver install (`build_indi_driver.sh`, `build_indi_bridge.sh`, `build_indi_simulator.sh`, `build_indi_onstep_fix.sh`) failed intermittently with `cp: cannot create regular file ...: Text file busy` when something respawned the just-stopped driver before the copy (seen on the UTM during a post-update restore, a different driver each time, so the driver build reported CRITICAL WARNINGS and the SMOS version was rightly not recorded). The binary is now copied next to the target and renamed over it, which does not need the old file to be idle
- The SMOS post-update notice's "Run post-update restore" button stayed clickable while the restore (or any install/update run) was already running; it is now disabled and relabelled "Restore running…" for the duration
- The recorded SMOS version (post-update notice) is now also updated by the `--mode=indi_only` setup path - which exits before the final "Setup complete" block and therefore never recorded it, leaving a Control host on SMOS x86 with a notice that never went away - and only after a run without CRITICAL WARNINGS, so a failed driver build keeps the notice. The post-update guard unit is installed in `indi_only` mode too (it was only installed by the full path)
- `bin/restore_after_smos_update.sh` on x86 now also restores `rclone` (basic-memory/Nextcloud sync) next to `gh`; only the Pi path used to install it, so after a SMOS update on the UTM the sync silently stopped ("rclone not found")

### Added

- SMOS update notice with a one-click post-update restore (yellow card "SMOS was updated (X -> Y)" + "Run post-update restore" button). The setup/restore records the SMOS version it completed against (`.smos_version_restored`, in the repo checkout under /home, which a SMOS root reset leaves alone); when `/etc/stellarmate/version` differs, the Control Center shows the card and the button runs `bin/restore_after_smos_update.sh` through the normal run/terminal machinery (`GET /api/smos_update_status`, `POST /api/smos_post_update_restore`). Because the update also removes the Control Center service itself, a small user-level guard unit (`pifinder-smos-update-guard.service`, `bin/smos_update_guard.py`, installed under `~/.config/systemd/user` by the setup) serves the same notice on the Control Center port when the version changed and the Control Center is gone, runs the restore on request (password-protected) and hands the port back

### Changed

- The Control Center now listens on port **8777** instead of 8765 (#481): KStars/Ekos's new native MCP server, and its AI assistant ("Stella"), default to 8765 too, so the two collided on any device running both. All references were migrated (server, launcher, setup script, PiFinder's PFSM page link, docs). Another Control Center that has not been updated yet is still reached on the legacy port as a fallback. Existing bookmarks to `:8765` need updating

## [2.0.1] - 2026-10-10

> Patch release on top of 2.0.0, found while recovering the UTM after the SMOS 2.4.0 update. Known issue unchanged: the Control Center's port 8765 collides with Ekos's native MCP server / AI assistant "Stella" - [#481](https://github.com/apos/PiFinder_Stellarmate/issues/481).

### Changed

- `bin/restore_after_smos_update.sh` now works on non-Pi (x86) SMOS machines (Control host, UTM dev VM) instead of hard-failing: the Pi-specific steps (ARM repos, config.txt overlays, swapfile, picamera2 patch) are skipped and it hands over to the setup's own non-interactive update path (`--action=update`, `--mode=full` or `indi_only` depending on whether a PiFinder venv exists), after best-effort restoring the GitHub CLI. A SMOS update wipes the Control Center service, INDI drivers, hardware groups and the GSC catalog there too

### Fixed

- Setup/Update now restores the GSC guide-star catalog (`/usr/local/bin/gsc` + `/usr/share/GSC`, copied from the KStars Flatpak) whenever it is missing. A SMOS update resets the root filesystem and wiped the earlier manual copy, which silently left Ekos guiding/plate-solve align/autofocus without a star field and made the Control Center's "runs entirely from System INDI drivers" card fire again
- Mount Bridge driver restart/stop helpers (`indi_client._mount_bridge_pids()`/`restart_mount_bridge_driver()`, `stop_indi_driver_and_wait`, the driver-build script's pre-kill) matched with a bare `pgrep/pkill -f <name>`, which also hits any process that merely contains the driver name in its command line - notably the C++ compiler building the driver itself (`.../indi_pifinder_mount_bridge.dir/...cpp.o`). A running Control Center "recovering" a missing Mount Bridge therefore SIGKILLed the build mid-compile (seen as `make: *** Killed`), so the driver could never be rebuilt while the Control Center was up. The match is now anchored to the process's argv[0]

### Documentation

- Reconstructed the three lost concept docs (#60, #61, #62) and expanded the Nix section of the upstream-packaging concept doc

## [2.0.0] - 2026-10-06

> Released deliberately early, before everything could be tested under a real sky: field-tested in PiFinder
> host mode; Control host mode is tested in basic form but not yet fully reliable; no HowTo/video guide yet.
> Known issue: the Control Center's port 8765 collides with Ekos's native MCP server (and thus Ekos's AI
> assistant "Stella") - [#481](https://github.com/apos/PiFinder_Stellarmate/issues/481).

### Added

- Mount Bridge: a mount's `TIME_UTC` is only snooped from KStars once, at connect time, so it silently drifts from the real (NTP-synced) clock in any long session. The Control Center's readiness watchdog now pulses KStars' own `clock_realtime` D-Bus action (off/on) once the property is more than 10 minutes stale, which forces a fresh push - no phone/EkosLive re-trigger needed (#483)
- Control Center: a per-CC "Profile health" self-check (new `/api/profile_health`, row in the Setup checklist) of the device's own active Web Manager profile - connected devices, unexpected foreign drivers; the colored "INDI WM"/"EKOS" icon badges on checklist steps 4/5 were replaced by plain "(INDI WM Profile)"/"(EKOS Profile)" label text (#478, #488)
- Control Center: surfaces System-vs-Flatpak driver-source gaps generically - a profile containing any PiFinder driver launches every driver from System sources regardless of the Driver Source dropdown, silently dropping Flatpak-only extras (e.g. the GSC star catalog); an extensible known-gaps registry shows a showstopper card only when something is actually missing (#536)
- "PiFinder Client" role: always uses a dedicated minimal Web Manager profile (instead of whatever profile was selected in step 1), and Host and Client now each remember and restore their own last-running profile across role switches and restarts (#449, #450, #451)
- Control Center: native Web Manager profile autostart after a reboot (#441, #444)
- Control host: a configured remote PiFinder that stays unreachable for 15s+ now shows a red dot with explicit "not reachable" text, plus an inline "Change address" button (#467, #468)
- Camera/IMU presence, system load and Mount Type/Screen Direction badges now reach a Control Host over the already network-transparent INDI layer instead of a password-assuming Control-Center-to-Control-Center HTTP proxy (#471)
- Control Center: the run status/"finished" banner now reflects the setup script's own "CRITICAL WARNINGS" block (e.g. a driver build killed by the OOM killer) instead of reporting plain green "Success" from a 0 exit code (#473)
- Mount Bridge: new `EXTERNAL_HOLD` driver switch (#372) - while Ekos reports guiding active, a Control Center watchdog engages it, suppressing every acting behavior (Auto-correct's Sync/Goto, Goto-Forward, Reposition-Detection's reaction, Sync-on-PiFinder-Align) regardless of the selected Coupling mode, while drift keeps being computed/logged; releases automatically once guiding has been idle 15s. Status page shows a neutral "⏸ Paused" indicator while held. Not persisted - a live-driven state, not a saved setting
- PiFinder `/api/nearby_bright_stars`: Multi-Point Alignment candidates are now selected by greedy max-min angular separation within a brightness-bounded pool instead of pure brightness ranking - avoids handing back a set of stars that all cluster in the same patch of sky, which fits OnStep's real multi-point alignment model poorly (#191 follow-up) (#531)
- Mount Bridge: Multi-Point Alignment's progress display now shows the star names being solved/synced, not just point counts - "1/2 points" -> "1/2 points (Vega)", "completed - 2/2 point(s) verified and synced." -> "completed - 2/2 point(s) verified and synced (Vega, Capella)" (new `ALIGN_PROGRESS_NAMES` INDI property) (#526)
- Ekos optical trains (Mount/Camera/Guider/Focuser/Filter Wheel/Rotator/Dust Cap/Light Box) now stay in sync with the active mount device instead of silently keeping stale references - a manual "Sync optical trains to this mount" action (new `/api/optical_train_sync` route + button, for a mount driver switched by hand) and an automatic one tied to the Full Simulation on/off toggle (snapshots and restores per-field, defensive against a manual change made while Full Simulation was active); every one of the 8 device-role fields is checked generically by its current value, not by assumed meaning, since e.g. "Guide via" can validly hold either a real guide camera or the mount's own name (pulse-guiding) (#519)
- Full Simulation: the PiFinder IMU Injector (prevents Mount Bridge's drift-plausibility check from flagging Full Simulation's own discrete fake-solve jumps as an implausible external reposition) now starts/stops automatically alongside the Truth Injector, instead of needing to be run manually as an undocumented second script
- Control Host: new warning card when the mirrored PiFinder's own device also has its own local Mount Bridge actively coupled (GoTo/Auto-correct) to its own mount - PiFinder isn't purely read-only (a confirmed external reposition gets written back into it), so two independently active Bridges can cross-talk through it, each mistaking the other's mount motion for a real external reposition of its own target
- Mount Bridge: Sync the mount on a confirmed PiFinder Align, any Coupling mode (#313)
- Mount Bridge: singleton guard (flock-based) against duplicate driver instances under the same indiserver (#303)
- Extending the singleton guard to `LX200_PIFINDER`/`PiFinderSimulator` tracked as a follow-up (#306)
- Mount Bridge GUI: "Quick Actions" split into its own group, gated on active Coupling mode (#305)
- Mount Bridge: default Coupling is now Verify/Alert only, not Off, on a fresh install, with a self-heal for a stale saved config with no switch active at all
- Mount Bridge GUI: self-heals a disconnected Ekos session automatically instead of just reporting it, reusing Autoconnect's own profile-start logic
- Mount Bridge: pushes confirmed external mount repositions (hand paddle, SkySafari, KStars) back to PiFinder's own push-to display (#300)
- Mount Bridge: new manual "Goto Held Target" button - re-sends the held `ORIGINAL_TARGET` independent of PiFinder's current (possibly disturbed) live position
- Mount Bridge: new manual "Align to Held Target" button - re-sends the held target to PiFinder itself so a later restart doesn't re-adopt a stale target
- Setup checklist: Profile and Mount steps visually emphasized with a box/border and star icon (#267)
- Sticky, hostname-aware page header showing the device's hostname and type; compacts on narrow widths (#268)
- PiFinder Simulator: mount-following via a new `FOLLOW_MOUNT_DEVICE` property, dead-reckoning along with a coupled mount's slews (#239)
- New always-visible "PiFinder" orientation status badge, fed directly from PiFinder's own `/api/orientation_status`
- Drift badge (Mount Bridge diagram) restyled to match every other ampel badge's height/padding/labeling
- OLED-mirror wait overlay now reflects `pifinder.service`'s actual systemd state instead of only inferring from `/image` probe failures (#192)
- Solve badge / Mount Bridge freshness: added tooltips clarifying the two badges can legitimately disagree (#193)
- Injected Solve (Dead Reckoning): a real, visible simulation mode, renamed and reworked from the earlier internal "Fake-Solve" (#106, #128)
- "Mount is source" coupling mode: reverses the usual direction, injecting the mount's own position into PiFinder as an Injected Solve (#130)
- Gate Auto-correct on a fresh, camera-sourced PiFinder solve instead of continuously-interpolated LX200 positions (#79)
- The three simulation/testing concepts (Fake Mode, Solve Simulation, Injected Solve) consolidated into one always-visible "Simulation and testing" section; every collapsible section now persists open/closed state
- Autoconnect's step 5 (start the Ekos profile) can now be triggered from the Control Center via KStars/Ekos's own D-Bus interface
- The Fake-Solve simulation feature and the #107 fix are now installed/updated via the patch script instead of existing only as unpatched live edits
- Control Center: automatic recovery from the "PiFinder LX200" stale-connection bug via a background reconnect watchdog (#118; in-driver alternative closed as wontfix, #139)
- Control Center: project logo added to the page footer alongside the existing HeyApos/AVVP logos
- Control Center GUI restructure: larger Install/Update hero photo, page-wide footer, Quick Links dissolved into a new "PiFinder" glance tile plus a "Links" section, tile reordering - pure layout, no behavior change
- Control Center: a system load indicator (Normal/High, percentage, CPU temperature) next to the PiFinder-reachability row
- `pifinder.service` now runs with `Nice=5`/`CPUWeight=50` as a coarse mitigation for CPU contention under load (precise fix tracked upstream in #148)
- `indi_pifinder`: LX200 driver now uses TCP keepalive and retries a slow (not dead) `:GR#`/`:GD#` read up to 3 times at a shorter timeout
- PiFinder now pinned to a fixed release tag for every install/update path instead of tracking upstream `release`'s moving HEAD; version check made purely informational
- PiFinder tile: a "Quick keys" compact keypad (D-pad/grid/per-device layouts) driving PiFinder's OLED menu without switching to the Remote page (follow-up reaction-time work tracked in #155)
- Mount Bridge, PiFinder Mode, and Install/Update tiles are now collapsible as a whole, state persisted in `localStorage`
- Quick Links gained INDI Web Manager, StellarMate Dashboard, and StellarMate Web VNC entries
- A Night mode toggle renders all page text/icons in glowing red for dark-adapted eyes, persisted in `localStorage`
- Install hero photo moved to the page bottom with HeyApos/AVVP logos; README footer gained the same two logos
- Every action button's accent color changed from blue to dark red for consistency (semantic status colors left alone)
- Threshold number input restyled to match the dark theme
- Mount Bridge tile renamed "INDI Mount Bridge"; a GUI consistency pass (status dots instead of emoji, role-card-styled Coupling presets, tightened checklist/status layout, corrected help.html sections)
- Mount Bridge's connection diagram and mode-caption/reject-warning rows moved into the "PiFinder" tile as fixed-height dot+label rows with an opt-in Details toggle
- Mount Bridge's drift readout now shows degrees+arcmin past 60' instead of raw arcminutes
- Quick Links: added an OnStep Web UI row (mount's own IP), converted every IP-list row to compact buttons, added an "Open all links" button and split GitHub/Discord links out
- Quick keys D-pad: a failed press now flashes red instead of the same look as a successful one; LONG button on layout A resized/repositioned per feedback

### Changed

- Mount Bridge tile: "One-Click Setup" restyled from a plain small button into an LED tile matching Real Hardware/Full Simulation/Fake Mode above it - status dot, title, short explanation (#529)
- Combined-role ("StellarMate + PiFinder") hardware warning text relativized, reflecting this session's CPU/memory root-cause fixes instead of the original, now-overstated "needs a powerful Pi... 8 GB RAM minimum" wording (#525)
- Mount Bridge tile: manual one-shot seed moved into Quick Actions, one row, no on/off toggle - `Re-seed from mount`/`Set position` each activate Injected Solve themselves (#319)
- Mode cards + readiness line moved from the "Simulation, Test and Power" tile into the Mount Bridge tile, between Role and Setup checklist (#267)
- Mount Bridge tile: Multi-Point Alignment moved below Setup checklist & diagnostics, pure reordering (#266)
- Timeout values for background INDI polls consolidated into named tiers instead of scattered bare literals
- README/README_de hero photo replaced with a new real-world photo (same file paths, no reference changes needed)

### Fixed

- Control Center: page-load crash on the Control host and PiFinder Client pages (`Cannot access 'wmSelectedProfile' before initialization`) - an early top-level `refreshMountBridgeStatus()` call read a `let` still in its temporal dead zone; now deferred (#477)
- Mount Bridge: the readiness self-heal's Check 3 treated "wrong device linked" and "right device linked but disconnected" alike and only re-linked - a no-op for the latter, leaving PiFinder LX200 disconnected forever behind an endless "re-linked" log. It now sends a real connect (#479)
- Control Center: "Re-seed from mount" switched Injected Solve off again ~2s after seeding it in Full Simulation (a deliberate real-hardware safety release that never accounted for Full Simulation having no real camera); now skipped there (#480)
- Mount Bridge: `PIFINDER_HORIZON_STATUS.ALTITUDE_DEG` froze (often at 0) and `DRIFT_STATUS` silently kept its last value whenever no fresh PiFinder solve was available, although the sky keeps moving. The altitude now falls back to the last known PiFinder position with `IPS_BUSY` marking it stale, and `DRIFT_STATUS` explicitly publishes `IPS_IDLE`; Sync/Goto/drift-correction and reposition detection deliberately still require a fresh solve (#482)
- "PiFinder Client": its role didn't survive a reboot/reinstall (Check 2.5 "re-added" the Bridge to a profile that is meant to have none), "+ Couple a mount" was offered although a Client has no local mount, and a stale "below the horizon"/"Re-seed from mount" showstopper lingered from earlier in the page load (#443, #444, #446, #448)
- Update/Reinstall/setup runs rebuild the INDI drivers, which left the Web Manager profile stopped, so the Coupling default never applied after an Update; the profile is now restored after driver rebuilds (#445)
- Control Center: a leftover `fake_solve_active` flag (and a stale truth-injector desire) survived a Control Center restart and kept feeding a wrong position with no "below horizon" warning; cleared on startup (#447)
- Control Center: a stale "Could not apply: Failed to fetch" error was kept although the change had actually been applied server-side; now reconciled against the real driver state (#469)
- `bin/self_update.sh` hard-aborted with a misleading "diverged from '@{u}'" error when the branch's upstream ref had been deleted (routine after a PR merge); now skips cleanly (#472)
- Mount Bridge: the issue #385 slow-query watchdog logged on every 5s tick for as long as indiserver stayed slow; now only on the state change (#474)
- Control host: the top Camera/IMU badges stayed grey because the passive hardware poll bypassed the shared dot helper (#476)
- Mount Bridge: `EXTERNAL_HOLD` (#372, same session regression) could get stuck permanently engaged - Ekos's Guide module reports GuideState 0 (idle, not guiding) whenever it's simply loaded, which wasn't in the live-confirmed safe-states list, so the watchdog's own fail-safe design correctly-but-wrongly held Mount Bridge's acting behavior the entire time it wasn't actively guiding. Live-caught on real hardware after several days stuck held; 0 added to the safe list (#537)
- Mount Bridge: a Control Center restart left a genuine `EXTERNAL_HOLD` stuck on forever - the CC and the driver are separate processes, so a fresh watchdog's own "not held" belief after restart never saw the transition needed to release a hold the driver was still actually holding from before. The watchdog now adopts the driver's actual live state on its first tick instead of assuming released (#539)
- Full Simulation: "Re-seed from mount"/"Set position" toggled the Truth Injector off, injected a one-shot fake solve (which itself sets `fake_solve_active`), then re-toggled it back on if still off - but that second, undirected toggle's own "OFF ist OFF" auto-detect read the just-injected `fake_solve_active=true` as "already on, this click means stop", turning it off again instead of restarting it. Full Simulation was left silently, permanently without its position feed after every single one-shot seed click. `/api/truth_injector_toggle` now accepts an explicit `direction=on|off` bypassing the ambiguous auto-detect (#523)
- Optical train device sync (#519, same session regression): the automatic Full-Simulation-entry snapshot swapped ANY field not already "Telescope Simulator", clobbering `camera`/`focuser`/`guider` fields legitimately pointing at their own unrelated simulator devices; now scoped to the real mount's exact device name (read from Mount Bridge's `ACTIVE_DEVICES.ACTIVE_MOUNT`) (#523)
- Control Center: the "Sync optical trains to this mount" result/error status line stayed visible indefinitely instead of auto-clearing like other transient status indicators (#520)
- Mount Bridge: Multi-Point Alignment's candidate stars (PiFinder's `/api/nearby_bright_stars`, J2000) were sent to the mount unprecessed - every other PiFinder-sourced coordinate in this driver already gets precessed to JNow at the source, this one call site was missed, producing a systematic (not random) pointing offset on every alignment point of tens of arcminutes at the current epoch (#521)
- Control Center: "Sync mount from PiFinder" silently did nothing whenever Mount Bridge had an open, unconfirmed `REPOSITION_CONFIRM` prompt - now auto-resolves it (Adopt) before syncing, since an explicit user-initiated Sync click already is the confirmation (#518)
- Mount Bridge: `handleRepositionDetection()`'s `weCommandedIt` check only looked at the forward/correct state machines' SLEWING flag, missing the case where its own Sync-then-Goto sequence (#227) or a same-tick-completing simulated Goto moved the mount before/without ever registering as SLEWING - misread as an external reposition, re-triggering `REPOSITION_CONFIRM` up to several times per second under real tracking load; now also exempts any mount move within a few seconds of Mount Bridge's own last-sent command (#517)
- Mount Bridge: `fetchFreshPiFinderPosition()`'s 5s failure cooldown (meant to protect against a genuinely unresponsive PiFinder HTTP server, issue #238) armed on ANY "not fresh" verdict, including a perfectly healthy response that simply wasn't a fresh CAM solve yet (an isolated `CAM_FAILED` frame, routine on real camera hardware) - blacking out `DRIFT_STATUS`/auto-correct for a full 5s after a completely ordinary moment; now only arms on a genuine HTTP-level failure of both the primary and fallback URL (#516)
- Control Center: the "No solve active" banner used a fixed `last_solve_attempt_age_sec > 5s` timeout, unreliable against real (as opposed to synthetic-image) solve timing variance; replaced with change detection (a fresh attempt makes the age drop, no timing assumption) and a self-calibrating stall threshold derived from the unit's own recently observed solve cadence instead of a hardcoded number (#515)
- `test_tools/pifinder_imu_injector.py`/`pifinder_truth_injector.py`: read INDI properties by spawning a fresh `indi_getprop` process (and TCP handshake) on every poll - the IMU injector had no interval cap at all, producing continuous, unbounded indiserver connection churn and measurable CPU load, a contributing factor in issue #385. Replaced with a persistent INDI connection reused across reads; the IMU injector's poll interval now defaults to 0.15s (~6.7 Hz) instead of running as fast as `indi_getprop`'s own round-trip happened to allow (#514)
- Pi camera: any live exposure/gain change while the camera was running (auto-exposure adjustments, "Align (Day)") could crash libcamera's IPA proxy outright (`FATAL ... A list of V4L2 controls requires a ControlInfoMap`), killing camera capture until the process was restarted - found on a Pi4 after a camera swap, reproducible independent of exposure/gain values or system state. `set_camera_config()`/`set_native_ae()` now stop the camera, apply controls, then restart instead of changing them on-the-fly, guarded by a lock against a related concurrency bug with in-flight captures (#512)
- `/api/mount_bridge_status` reported `running: false` (a confirmed fact, blanking the whole Mount Bridge diagram/badges) whenever the underlying INDI query merely failed (timeout/connection refused during issue #385's periodic stall) - the driver itself is typically still healthy the whole time. Now reports `running: None` on a query failure instead, reusing the frontend's existing "unconfirmed" pulse state instead of a false all-clear-to-red flip (#506)
- Mount Bridge GUI: the drift badge showed the frozen number plus the literal word "(stale)" during issue #385's stall, reading as an error with no sense that it resolves on its own; now shows a calm pulsing "Reconnecting…" state instead, last known value dimmed but still visible
- Mount Bridge GUI: switching the Web Manager profile to one that never had a mount driver left the "Mount" setup step/readiness-line entry showing green from a leftover mount name remembered from a PREVIOUS profile, directly contradicting the "No mount driver in this profile yet" text next to it; the underlying self-heal also retried connecting to that same nonexistent device forever, spamming the log. Both now check the mount name against the actually-running profile's real driver list
- Mount Bridge GUI: the Ekos auto-heal step's 3-attempt budget was only ever reset on success, never on a profile switch - a budget already exhausted against an old (e.g. mount-less) profile carried over to a freshly-selected, perfectly viable one, showing "start it yourself" with no real attempt ever made against the new profile, even after Mount Bridge's own unrelated self-heal had already reconnected every driver
- Control Center: the PiFinder Client readiness checklist ("Drivers"/"Mount") required a Mount Bridge and an active mount unconditionally, which a PiFinder Client structurally never has - a correctly-configured Client could never show fully ready. Also highlights the "Reset to minimal Client set" button when the profile actually carries a stray Mount Bridge or other unrelated driver, instead of looking the same whether or not there is anything to fix
- Mount Bridge: the PiFinder-solve freshness check (`ageSeconds`) compared a whole-seconds integer "now" against a sub-second-precision solve timestamp - a solve landing less than a second before the check could make the age spuriously negative and get rejected as "not fresh", intermittently ("mal geht's, mal nicht") blocking GoTo-Forward/reposition-detection even on a solve under a second old
- Mount Bridge: `syncOrientationStatus()` was missing the #238 cooldown guard already applied elsewhere, running an unconditional blocking HTTP round trip on every tick with no backoff
- Mount Bridge GUI: switching the role card to "Control host" never cleared a stale "PiFinder host"/"PiFinder Client" choice from before, so that role's card stayed stuck highlighted (alongside the now-correct "Control host" card), and its "profile carries more than it needs" showstopper/Reset button both wrongly reappeared, even though the profile's driver shape had already moved to the unambiguous Control-host form
- Mount Bridge readiness watchdog: "PiFinder Simulator"'s FOLLOW_MOUNT_DEVICE was only ever kept in sync with the linked mount while Full Simulation's truth-injector actively targeted the Simulator - a value set during an earlier Simulation session (e.g. "Telescope Simulator") survived unnoticed into later Real Hardware use with a real mount linked, showing a stale, misleading marker on the sky map. Nothing else in the system cross-checks this (the Setup checklist's Mount step only validates the Bridge's own `ACTIVE_MOUNT`). Now kept in sync in every mode, skipped only if Shadow Sync is enabled and targets the same device (avoids two independent mechanisms fighting over the same device's position)
- Mount Bridge GUI: a role switch needing two driver changes (e.g. add PiFinder LX200 + remove Mount Bridge) sent them as two separate requests, each restarting indiserver on its own - the second restart collaterally killed/relaunched drivers the request itself never touched, causing a visible Coupling-mode "Off" flash (TF-7) and a window where the role could be misdetected as "Control host, no PiFinder configured" (TF-8). Both changes now go in one batched request (`/api/webmanager/pifinder_drivers?changes=driver|action|remote,...`), one stop/restart cycle total
- Mount Bridge GUI (TF-8, continued): the "Control host: no PiFinder configured yet" prompt stayed force-shown forever once a role switch had triggered it, even after picking Host/Client instead - now cleared whenever a non-Control-host role is chosen
- Self-heal never flagged or repaired a missing Mount Bridge on a Host-role profile that genuinely needs one (a mount linked/desired but no Bridge driver in the profile at all) - both the readiness self-heal and the profile-health check now cover this case
- Full Simulation: "Re-seed from mount"/"Set position" left the Truth Injector permanently off after every use - the temporary toggle-off meant to avoid a race was never undone, silently killing Full Simulation's position feed on every one-shot seed action
- `/api/profile_health` never checked whether "PiFinder Simulator" was actually connected, only PiFinder LX200/Mount Bridge
- Maintenance Mode turned a profile's INDI/KStars processes off but left its Web Manager Auto Start/Auto Connect flags on, letting the Web Manager's own boot-time/post-launch logic silently re-arm the very profile Maintenance Mode had just stopped
- `indi_pifinder_simulator`: `CONNECTION_NONE` (no physical serial/TCP link - this is a pure in-memory value holder) was set from `initProperties()`, too late to prevent `INDI::Telescope`'s own base-class `initProperties()` from already registering a Serial/Network "Port Auswahl" UI for it; moved to the constructor
- Mount Bridge on a Control Host: every HTTP call to PiFinder's own REST API was hardcoded to `127.0.0.1`, so drift/orientation stayed permanently `Idle`/stale whenever PiFinder ran on a different device; the real remote host is now pushed to the driver on every readiness-watchdog tick (#453, PR #452)
- PiFinder `POST /api/fake_solve` returned an arbitrary RA near the celestial pole (JNow→J2000 `atan2` degeneracy); now keeps the caller's RA for `|dec| >= 89.9` (#343; upstream brickbots/PiFinder#645)
- Mount Bridge: Multi-Point Alignment's own GoTos misclassified as external repositions, triggering a spurious extra GoTo per alignment point (#309)
- Mount Bridge GUI: collapsed hardware-mode summary showed a white dot for active "Real Hardware" instead of green
- `bin/build_indi_bridge.sh` was never executable (mode 644 since its first commit)
- `build_indi_*.sh` scripts could fail with "Text file busy" if the Web Manager respawned a just-killed driver mid-build; each now stops and waits immediately before its own `cp`
- Mount Bridge GUI: "Link telescope mount" error text vanished after 1.5s regardless of whether the underlying problem was resolved
- Mount Bridge: `handleRepositionDetection()` could adopt a still-in-flight mount position as final; now requires 3 consecutive stationary ticks
- A PiFinder echo could slip past the reposition-notification guard and trigger a redundant Goto; widened the echo-match threshold to 1.0'
- `test_tools/pifinder_truth_injector.py`: fixed a hardcoded port-8080 default and an `::1`/nginx collision by auto-detecting PiFinder's actual port
- `pifinder_truth_injector.py`'s port auto-detect could still lock onto nginx's catch-all 200 response; now also requires `fake_solve_active` in the body
- Mount Bridge: Goto-Forward's drift readout silently froze on a stale solve instead of admitting it couldn't verify; now shows "Position unverified"
- Mount Bridge: `MaxSyncDriftN` sanity cap only checked mount-vs-PiFinder disagreement, never PiFinder-vs-held-target disagreement, letting a stale target slew the mount with no warning (#282, HIGH PRIORITY/SAFETY)
- Mount Bridge: "Goto Held Target" could crawl at an inherited, arbitrarily slow rate; now sets an appropriate slew rate first
- `pifinder_pre_start.sh`: `pifinder.service` crash-looped forever after reboot from the same `/etc/group`/`/etc/passwd` newline gap fixed elsewhere (#270, #276)
- `camera_pi.py`: "Align (Day)" rendered fully white/clipped from an unexpected 16-bit capture container; added a scale-mismatch guard
- Pi5: OLED went completely dark from an `RPi.GPIO`/`rpi-lgpio` pip-install ordering conflict; now explicitly uninstalls the real package first and detects `rpi-lgpio` via `hasattr`
- `restore_after_smos_update.sh`/`pifinder_stellarmate_setup.sh`: `pacman -S libcamera libcamera-ipa` always failed on SMOS (no such split package there); dropped `libcamera-ipa`
- `restore_after_smos_update.sh` had the same `/etc/group`/`/etc/passwd` newline gap fixed in PR #270; ported the same guard
- `restore_after_smos_update.sh`: `gh` found entirely missing after a SMOS update; added a best-effort, non-fatal reinstall
- `pos_server.py` served only one LX200 client at a time; fixed with one thread per connection, thread-local state, and a per-IP connection cap
- Status dots turned egg-shaped ("Ostereier") on window resize from a missing `flex-shrink: 0`
- `/etc/group`/`/etc/passwd` missing trailing newline silently broke `spi`/`gpio` group creation; now newline-terminated and hard-aborts if group setup still fails
- Stale version banners across README/Readme_*.md/_de fixed to reflect the actual 2.6.3/2.3.0 pin; removed an untracked, untagged "v2.0.0" label
- Setup never rebuilt the "PiFinder Simulator" INDI driver, letting it silently go stale relative to the other two; now built/installed together with a bounded self-heal retry
- PiFinder Simulator: unvalidated snooped mount coordinates could produce a NaN position at Dec 90; added an `isUsableCoordinate()` gate
- Mount Bridge: same unvalidated snooped-coordinate gap as the Simulator, but feeding real mount-commanding logic; added `isUsableCoordinateForWarn()`
- x86: `python-libcamera` pin silently failed and misreported success in the summary; now skipped on x86_64, exit code checked on aarch64
- Missing `nlohmann-json` package broke all three INDI driver builds on a fresh install; added to the package list
- Mount Bridge: PiFinder solve position wasn't precessed to JNow, so J2000→JNow precession read as permanent drift that never converged (#232)
- PiFinder Simulator now follows a forwarded GoTo instead of freezing during Goto-Forward, by also snooping the mount's `TARGET_EOD_COORD` (#177, #232 follow-up)
- Added a coordinate-pipeline reference doc mapping epoch/unit/frame at every hop between PiFinder (J2000) and the mount (JNow)
- `picamera2`/`drm_preview.py` patch drift against a newer 0.3.37 release broke the whole camera import; diff regenerated and `picamera2` pinned explicitly
- Goto-Forward silently ignored the first Goto after any BridgeMode switch or driver restart (#194)
- `DriftThresholdNP`/`MaxSyncDriftNP`/`SolveFreshnessMaxAgeNP` never called `saveConfig()`, so none survived a driver restart (#195)
- OLED-mirror tile looked dead for 3-60+s after a real reboot before PiFinder's web server was reachable; added an explicit waiting overlay (#187)
- Startup hardware test's Cam/GPS check could leave a stale "unreachable" result after a slow reboot; now retries indefinitely (#188, dup of #167)
- Static OLED-mirror placeholder showed the original blue splash instead of the documented red-converted version; now generated and cached from PiFinder's own venv
- `bin/functions.sh`: `kstarsrc` path pointed at a location that never exists on StellarMate OS (KStars ships as a Flatpak); fixed the path
- `diffs/state_py.diff` and `diffs/camera_interface_py.diff` had drifted out of sync with actual upstream v2.6.0 content; regenerated and verified
- venv-bootstrap re-exec's resume guard only armed on first-ever venv creation, not a pre-existing venv, causing a full duplicate re-run of the script
- Installation Summary's "PiFinder:" line showed the live upstream version instead of what was actually installed
- `_camera_hardware_present()`'s `rpicam-hello` probe timeout (10s) too short under load; raised to 25s
- Mount Bridge's "Mount is source" preset button was missing from the coupling-gate enable list, staying permanently disabled (#130/#131)
- `_imu_hardware_present()`'s I2C scan could race PiFinder's own IMU polling and misreport "not detected"; now retries up to 3 times
- x86: "Installing system packages" failed with `target not found` on a freshly provisioned device under StellarMate's Atomic Updates lock (#257)
- Control Center: Start Install/Reinstall/Update buttons vanished permanently after a rejected (409) start; now re-renders the choice screen

### Documentation

- New concept doc: one-click Debug Mode + Bug Report workflow - INDI DEBUG logging toggle for Mount Bridge + the active mount device, offset-based log slicing/verification against indiserver's own log, GitHub issue hand-off (#533)
- README, install guide, and screenshots rebuilt end-to-end (EN+DE): TOC, mandatory Web Manager step, version matrix/roadmap consolidated, basic-memory references dropped, stale status headers fixed (#336, #337, #338, #339, #349, #350, #351, #352, #353, #354, #355)
- New Control Center "Status Badges & Colours" reference, with per-badge headings and images (#341, #342)
- New PFSM overview presentation deck (LaTeX Beamer, EN+DE, light/dark builds): badge legend, hyperlinked links slide, Web Manager/role-card/control-host slides, wiring diagram (#356, #357, #358, #359, #360, #361, #362, #363, #364, #365, #366, #376, #377)
- New concept docs: Realmode Sky Simulation, guiding detection via Ekos Optical Train, a native Ekos module for PiFinder, Mount Bridge `EXTERNAL_HOLD` (#345, #369, #371, #373)
- LX200/Ekos/Web Manager walkthroughs (INDI Control Panel, KStars sky-map right-click ops) and an inventory of upstream `pos_server.py`'s multi-client rework (#346, #348, #367, #368)
- `Readme_UTM_dev_X86.md`/`_de.md`: new section on optional WireGuard access to the device fleet, for reaching a fleet device (e.g. a Pi5) when the bridged NIC isn't on the same network - anonymized, includes the "handshake succeeds but no traffic routes" AllowedIPs gotcha (2026-09-15)

### Control-host hardware badge mirroring

- Control host now mirrors the remote PiFinder's own OLED instead of the local host's (#417)
- Fixed the OLED discovery loop never picking up a later-known remote host (#418)
- Control host: fixed remote Quick keys, clarified role-pill wording (#419)
- Badge sizing/color matched across the page; added Ekos/INDI Web Manager badges; wrote the badges-mirroring concept doc (#420)
- Moved Ekos/INDI WM badges onto the Bridge node; added icons to profile tags (#421)
- Added icons to checklist group headings; Configured badge now green when true (#422)
- Solve and GPS badges made Control-host-aware (badges-mirroring, phase 2a) (#424)
- Fixed a misleading green orientation badge on Control host; added Pi5 diagnostics (#425)
- Built the Control-Center-to-Control-Center proxy for badge mirroring (badges-mirroring, phase 2b) (#426)
- Migrated Camera/IMU/System-Load/Mount-Type/Screen-Direction badge mirroring off that
  Control-Center-to-Control-Center proxy onto INDI: new `/api/hardware_status` on PiFinder's own
  REST API, four new INDI properties on "PiFinder LX200" (`HARDWARE_PRESENCE`,
  `PIFINDER_SYSTEM_LOAD`, `PIFINDER_ORIENTATION`, `PIFINDER_MODE`) - already network-transparent, no
  password/fleet-same-password assumption needed for these anymore (badges-mirroring, phase 2c,
  2026-09-15). `pifinder_mode`'s own control path stays on the proxy (it's Control Center
  orchestration state, not a device fact) but is now also mirrored read-only into `PIFINDER_MODE`
  for free visibility in EKOS/the StellarMate App.
- Control host: `_cc_proxy_get()` (now only used by `pifinder_mode`) retries with the well-known
  fleet default password before giving up, instead of silently reporting "unavailable" the moment
  two devices don't happen to share a password (2026-09-15)

### "PiFinder Client" role

- Concept: "PiFinder Client" role naming, reviewed alongside the INDI Setup section (#428)
- Concept: decided "PiFinder Client" as a manual third role card (#430)
- Implemented "PiFinder Client" as an explicit third role card, alongside PiFinder host and Control host (#434)
- Retired the self-contradicting PiFinder-Client mismatch warning per direct feedback; the stale choice is now auto-cleared server-side instead (#440)

### Mount Bridge self-heal & robustness

- Fixed `TimerHit()` blocking on a slow PiFinder; added a Control-Center single-host lock (#379)
- Exposed PiFinder's own horizon status; gated the Sync button on it (#381)
- "Re-seed from mount" now checks `mount_connected`, not just a configured mount name (#383)
- Mount Bridge now trusts the mount's own position across a Bridge-only restart (#384)
- Logged indiserver latency in the readiness watchdog (issue #385) (#394)
- Sim-mismatch warning now stays resolved across driver restarts (#399)
- Added a self-heal for Mount Bridge profile-bookkeeping desync (new check 2.5) (#415)
- Self-heal now confirms a device actually connected, not just that CONNECT was sent (#427)
- Logged when the stray-`pifinder.service` self-heal can't check right now (#433)
- Fixed `self_update.sh` re-exec failing on a bare relative invocation (#437)
- Persisted the last-known LX200 remote so the stray-service self-heal survives a reboot (#438)
- Coupling-mode-always-active self-heal now runs on every connect, not just the first (#439)
- Fixed the readiness watchdog skipping `pifinder.service` sync entirely when indiserver was down (#440)
- Added a self-heal that auto-starts a previously-running Web Manager profile after a reboot (#441)

### Control Center GUI polish

- Mount Bridge now verifies PiFinder LX200's connection mode before an Ekos connect; Control-host address box made mandatory (#378)
- Host-lock client id scoped per browser tab; `checkPageVersion` kept always on (#380)
- Solve status dot now checks staleness, not just last-known `solve_source` (#387)
- No-solve showstopper banner now also checks staleness (#388)
- No-solve banner no longer fires on a cloud with a healthy camera (#389)
- "Re-seed from mount" no longer permanently blocks real solving (#390)
- PiFinder-below-horizon warning no longer requires a sim mismatch (#391)
- Solve-freshness age now computed server-side instead of client `Date.now()` (#392)
- "Sync mount from PiFinder" now also moves the PiFinder Simulator (#393)
- Sim-mismatch card now checks live drift instead of a frozen startup snapshot (#395)
- Exposed a Reposition-Confirm revert; fixed stale Drift badge coloring (#396)
- Reboot/Shutdown buttons now show the actual hostname (#397)
- Added Maintenance mode, keeping Mount Bridge/PiFinder LX200 disconnected during driver work (#398)
- Redesigned the Install/Update section with a device-type choice; synced `pifinder.service` with the LX200 target (#402)
- Added a Control Center self-restart button (#403)
- Merged the PiFinder-host/All-in-one role cards; added tile location+role display (#404)
- Replaced native `confirm()`/`alert()` dialogs with the inline banner pattern (#405)
- Fixed Update/Reinstall/INDI-only card text so all three self-update this repo too (#406)
- Guaranteed a Control Center restart after any setup run; added click feedback for banners (#407)
- Made the Terminal panel collapsible, defaulting to 15 lines with a show-all toggle (#408)
- Moved Reset to the end of the Advanced/troubleshooting list (#409)
- Device-type selector now matches the established green selected-state color (#410)
- Removed the generic "Waiting for PiFinder..." message (#411)
- Bundled both welcome placeholder images instead of depending on the device (#413)
- Fixed the red welcome image being nearly invisible (#414)
- Fixed Full Simulation targeting the wrong device; grouped Local/Remote status (#429)
- Mount Bridge tile now shows its own hostname; fixed broken doc links (#432)
- Added a Real Hardware tile toggle; gave the Mount Bridge heading more visual weight (#435)
- Added header banners for "update running"/"update just finished", moved from the bottom of the Install/Update tile into the sticky header (#436)

### Misc fixes

- Fixed GUI-triggered updates racing their own end-of-script restart to death (#423)

## [1.4.0] - 2026-08-02

### Added

- Reset and Uninstall are now first-class actions (setup script menu options 4/5, plus Control Center buttons), streaming live into the shared Terminal
- Control Center's "Solve" status now reflects a genuine plate-solve success/failure signal, separate from Solve Simulation
- New "Decouple" button next to the Coupling status text
- Stale-page detection: `GET /page_version` content hash plus a "Reload now" banner for already-open tabs
- A one-time banner now shows the outcome of the last Install/Update/Reinstall run after the Control Center's own post-success restart
- New `GET /state` diagnostic fields exposing every mutex-guard flag
- New Test Case GitHub issue template

### Changed

- Reset/Uninstall regrouped to match actual scope (Reset under "PiFinder", Uninstall under "PiFinder Stellarmate")
- Uninstall confirmation dialog now explicitly names the repo path and warns it's permanent
- `uninstall_pifinder_stellarmate.sh`'s stop/disable/remove loops now emit progress per unit with a pause between them
- README/Readme_ControlCenter docs now document the Reset/Uninstall feature

### Fixed

- Adding/removing a Mount Bridge device silently wiped a remote PiFinder LX200 driver's config
- `--reset` was silently running the full uninstall block first
- venv two-pass re-exec used a bare `$0`, breaking a non-`./` invocation
- Missing `try`/`finally` around four background "is running" flags left them stuck on an uncaught exception
- Uninstall's live-output connection dropped before the first poll, or before enough log lines had landed
- Uninstall triggered from the Control Center could kill its own systemd unit before removing the repo (two bugs in the `--selfmove` handoff)
- Setup script could leave the Control Center "enabled but stopped"; the fix then over-corrected and could kill a Control-Center-driven run via SIGPIPE
- Solve badge fix initially read its fields from the wrong JSON path, so it never actually left "unknown"

## [1.3.1] - 2026-07-29

### Added

- Control Center now restarts itself automatically after a successful Install/Update run, with a lock overlay during the restart
- Mount Bridge/PiFinder Mode tile now distinguish "still starting" (45s grace, pulsing yellow) from a genuine "not detected"
- Static OLED-mirror placeholder is now a pre-converted red version of PiFinder's splash image

### Changed

- Consolidated every "still checking" indicator across the Control Center onto one forced-yellow pulsing-dot pattern
- Mount Bridge status polling now gated on the device's actual role; PiFinder-host devices show "not used in this role" instead of a misleading diagram

## [1.3.0] - 2026-07-29

### Added

- `--mode=indi_only` for the setup script and an "INDI-only" checkbox in the Control Center: installs just the INDI build deps and PiFinder's two INDI drivers
- `bin/os_detect.sh`: package-manager abstraction (pacman/apt/nix) with StellarMate Atomic Updates handling, used by INDI-only mode
- Mount Bridge: role cards (All-in-one / PiFinder host / Control host) as an explicit choice at the top of Setup checklist & diagnostics
- Remote PiFinder support via INDI remote drivers (`label@host:port`), enabling split-host coupling across two physical devices
- `bin/build_and_install_indi_drivers.sh`: INDI driver build/install sequence extracted and shared between full and INDI-only modes
- Mount Bridge: a compact, always-visible hardware status strip (Camera/Solve/IMU/GPS); detailed rows collapsed by default

### Changed

- Role model moved from device-level to profile-level, replacing two earlier rejected designs
- Phase checklist in the Install tile is now mode-aware (INDI-only shows only its own three phases)
- Mount Bridge status tile: a poll miss now keeps showing the last confirmed state marked "(unconfirmed)" instead of blanking to a synthetic "off"
- Mount Bridge's drift readout now updates via its own 2000ms poll instead of the slower, gated connection-status poll

### Fixed

- Changing the Threshold field while Verify/Alert or Auto-correct was active had no effect on the driver; now pushes live

## [1.2.0] - 2026-07-26

### Added

- Control Center: a branch picker ("Install from") for Reinstall/Update
- A "Run Again" button, replacing the earlier combined Cancel/Close-Setup flow
- Mount Bridge: a persistent, tile-wide status line for the duration of any in-flight action
- Mount Bridge: a "Manual: Sync mount from PiFinder" one-shot button, independent of the active Coupling preset
- Mount Bridge: a "Setup" button that runs the profile/drivers/connect sequence without applying a Coupling preset

### Changed

- Install/Update flow simplified: removed the confusing Cancel button, then Close Setup too
- Ekos wording matched to KStars' own two-step terminology, later simplified to name the active profile directly
- Coupling: split the combined Auto-correct dropdown into four explicit preset buttons grouped Visual vs GoTo
- Mount Bridge tile reorganized into priority tiers (always-visible essentials vs collapsed setup/diagnostics); layout-shift fixed for transient banners
- Setup checklist regrouped by where you'd actually go to do each step (INDI Web Manager vs Ekos/KStars)
- Goto-Forward's post-arrival check now iteratively refines (sync + re-goto, up to 3 times) instead of a single Sync

### Fixed

- Branch picker preferred a stale prior selection over what's actually checked out
- Auto-correct (Goto & Track) repeatedly aborted the mount mid-slew by re-issuing a fresh Goto every poll tick
- Control Center's "Install from: main" branch picker was silently ignored on an existing checkout on another branch
- Setup script's `git clone`/`reset --hard`+`pull` had no exit-code check, silently leaving a broken install on failure

## [1.1.0] - 2026-07-26

### Added

- Mount Bridge web integration: a guided Coupling Dial workflow in a new Mount Bridge tile (numbered checklist, Autoconnect, Ekos D-Bus gate, auto mount-driver detection, connection diagram, help.html), built on a new minimal INDI client module (see `docs/concepts/mount_bridge_web_integration.md`, #38)
- "Test Hardware" button: deep functional checks for Camera/IMU/GPS, classified as hardware/driver/Python failures; also runs automatically once on every Control Center start
- Full documentation for the Control Center and Keyboard Bridge (`Readme_ControlCenter.md`, `Readme_KeyboardBridge.md`, EN+DE)
- Setup Wizard control + auto idle-shutdown: start/stop the Setup GUI webserver from the browser; auto-shuts-down after 60s idle
- "First Steps" page (`/first-steps`): checklist of network addresses and StellarMate Web Manager setup links for right after a fresh install
- Automatic Mount Type sync: Mount Bridge pushes the connected mount's own `TELESCOPE_MOUNT_TYPE` to PiFinder's Mount Type setting
- Comprehensive IP address display: Web UI and OLED now show every non-loopback IPv4 address, not just one
- Setup GUI (`gui_installer/`): a stdlib-only local web page running the setup script with a live status view, 10-step progress bar, OLED mirror, and a Close Setup button
- Control Center: Fake/Real Mode switch tile with a hardware checklist (camera/IMU/GPS), a Test Mode toggle, and always-available Reboot/Shutdown buttons
- Hardware-free dev/test tooling (`test_tools/`): `fake_mode.sh`, `keypad_gpio_matrix_test.py`, `fb_screen_mirror.py`, `fb_keyboard_bridge.py` for SPI display + USB numpad testing
- Self-update: both entry points now `git pull` this repo before doing anything else, skipping safely on a dirty tree
- Waveshare LCD overlay made reboot-toggleable from the Control Center, with matching autostart/exclusion systemd units
- Numpad bridge made its own independent, permanently-on toggle backed by a new systemd service
- Numpad remapped to put navigation entirely off NumLock
- Camera process now falls back to the debug/synthetic camera instead of crashing when no hardware is detected

### Removed

- "Software Upd" removed from the OLED Tools menu (incompatible with a StellarMate-managed install)

### Fixed

- Control Center login could reject a correct password (`pam_acct_mgmt()` bug); also added per-IP rate limiting
- `pifinder.service` could crash right after cold boot on a PWM sysfs permission race; added a retry plus `Restart=on-failure`
- `launch_setup_gui.sh`'s self-update only fast-forwarded the git checkout, not the systemd units derived from it
- Installation Summary always reported "picamera2: unknown"; now reads the version via `importlib.metadata`
- Reinstall/update left stale state behind: a running Fake Mode instance survived `rm -rf`, and `pf_remote.py`'s own fixes weren't tracked through the diff system
- Setup script unconditionally told the user to reboot even when nothing required it; now tracks whether `config.txt` actually changed
- `keyboard_pi.py` crashed on every keypress once python-libinput 0.1.0 changed `get_key()` to return a plain `Enum`
- Solve Simulation status display drifted out of sync with the real internal toggle state in two layered ways
- Control Center's hardware-status tile always said "camera" in its degraded-mode label regardless of which part failed
- Setup GUI/Control Center's post-run success screen could show a stale Web Manager restart status
- `uninstall_pifinder_stellarmate.sh` had drifted badly out of date (missing units, INDI drivers, udev rules); rewritten to cover everything and print what's deliberately left in place

### Changed

- PiFinder's own `/smos` page nav entry renamed "PFSM", restructured to put Control Center status front and center
- Control Center now asks for confirmation before a destructive Reinstall/Update/Reboot/Shutdown action
- Setup script now builds and installs the PiFinder LX200 and Mount Bridge INDI drivers automatically
- Control Center status rows unified to a dot-then-label-then-status layout; Solve Simulation toggle moved into the hardware-status tile
- `smos.html`/README got an updated Control Center screenshot and previously-missing INDI Drivers screenshots
- README accuracy fixes: clarified the basic-memory/Nextcloud section as a personal maintainer workflow; noted the Pi 5 keyboard/UPS-shield GPIO conflict; updated the Uninstallation section
- `Readme_PiFinder_LX200.md`/`_de.md`: made the Web-Manager-only driver-catalog requirement much harder to miss

## [1.0.0] - 2026-07-16

**First tagged release.** Built and verified for **PiFinder 2.6.0** on **StellarMate OS 2.2.1**
(Arch Linux).

### Added

- PiFinder LX200 INDI driver (`indi_pifinder_lx200`): standalone driver reporting PiFinder's plate-solved position as push-to targets; works with KStars/Ekos and SkySafari
- PiFinder Mount Bridge (`indi_pifinder_mount_bridge`): optional auxiliary driver coupling PiFinder to any INDI mount via four coupling modes (Off/Verify-Alert/Auto-correct/Goto-Forward) plus a manual Sync/Goto Now trigger
- `Readme_PiFinder_LX200.md` (+ German): full setup/reference docs for the INDI/Mount-Bridge integration
- This changelog
- End-to-end verification against a real Skywatcher EQ5 + OnStepX controller

### Changed

- Ported the PiFinder LX200 driver from a fat-binary `LX200Generic` build to a standalone build against the system `LX200Telescope` base class
- Trimmed the driver's capabilities to GoTo + Abort only, matching what PiFinder actually has
- INDI driver build is a separate manual step, not part of the automated setup script

### Fixed

- Symlink name mismatch that prevented the old driver from loading under its expected name
- 6-10 second lag on every position update from `tty_read()` blocking for the full timeout; replaced with `tty_nread_section()`
- A property-name collision between a custom `TARGET_EOD_COORD` and `INDI::Telescope`'s own published property
- `ISGetProperties()` called `loadConfig()` on every client connection, silently reverting the user's chosen Coupling mode

---

## Pre-1.0.0 (condensed history)

The project didn't maintain a changelog before v1.0.0. This section summarizes the major
milestones from the git history for context; see `git log` for full detail.

### PiFinder 2.6.0 / StellarMate OS 2.2.1

- Upgraded target PiFinder version to 2.6.0 (web template extension change `.tpl` → `.html`,
  `numpy-quaternion` unpinned for numpy 2.0 compatibility, patch version-gate updates).
- SMOS version pinning and compatibility checks (`smos_version_stable`) added to the setup script.
- `smos-post-update.sh` / `restore_after_smos_update.sh`: restore pacman repos, system packages,
  hardware groups, udev rules, `/boot/config.txt` overlays, swapfile, and systemd services after a
  StellarMate OS BTRFS-snapshot update (which wipes the root partition).

### Raspberry Pi 4 stability

- Fixed WirePlumber blocking the IMX296 camera (masked PipeWire/WirePlumber for camera stability).
- Fixed a WDS catalog out-of-memory kill via `os.nice()`, batch size, and yield-time tuning.
- Smart power-management sleep state machine (WARMUP → SLEEP → RETRY → SOLVED).
- Fixed GPS time being off by the local UTC offset (`datetime.now()` → `datetime.now(timezone.utc)`).
- Fixed a `numpy` 2.0 incompatibility in the bundled Tetra3 solver (`np.math.factorial` →
  `math.factorial`).

### Raspberry Pi 5 (partial support)

- `rpi-lgpio` support and a `uart3`/SPI0 overlay conflict fix (GPIO9 conflict on RP1).
- GPS and Web UI confirmed working.
- OLED display: not yet working — under investigation (SPI driver difference between Pi 5's
  `spi_dw_mmio` and Pi 4's `spi_bcm2835`).
- Camera requires a 15-pin FFC CSI adapter cable (Pi 5 uses a different connector than Pi 4).

### StellarMate-specific integration

- PiFinder configured to use StellarMate/KStars as its GPS and time source instead of a dedicated
  GPS module.
- Network configuration UI (WiFi mode, AP/Client switching) removed from PiFinder's own OLED menu
  and web interface — StellarMate owns all network management.
- Web interface IP display and authentication patched for StellarMate's dynamic user setup.
