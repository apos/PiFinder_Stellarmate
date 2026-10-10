# AKTUELLER STAND (2026-10-10, spätabends) - ToDos für die Pi4-Sitzung

> Diese Datei wird mit "read ctx.md and load" geladen. **Der folgende Abschnitt ist der aktuelle Stand.**
> Alles ab "# PiFinder INDI Driver Development Session" weiter unten ist ein alter Stand (Dez. 2025,
> Treiber-Entwicklung) und nur noch Historie. Ausführlicher Kontext: basic-memory
> `pifinder-stellarmate/00196_...`, `00000_projekt-fakten-checkliste.md` (Abschnitt "SMOS-Update auf NVMe"),
> `00005_smos-post-update.md`, `00197_...`; Issue [#561](https://github.com/apos/PiFinder_Stellarmate/issues/561).

## Was passiert ist
- Pi4 (NVMe über USB, `SM_ROOT_NVM`) wurde per SMOS-App von 2.3.0 auf **2.4.0** aktualisiert und bootete nicht
  mehr. Ursache: `cmdline.txt`/`fstab` (+ Vorlage `etc/stellarmate/boot/cmdline.txt`) standen auf
  `LABEL=SM_ROOT`, die NVMe heißt `SM_ROOT_NVM`. `bin/smos-post-update.sh` (fix_uuids, `--updatesd`) war vor dem
  Reboot nicht gelaufen.
- Repariert vom SD-Boot aus: UUIDs in den drei Dateien (Sicherungen `*.bak-20261010` neben den Dateien auf der
  NVMe). Danach Boot von NVMe, `restore_after_smos_update.sh` und `pifinder_stellarmate_setup.sh --action=update
  --mode=full` liefen sauber (3m31s, keine Warnungen). Control Center und `pifinder` aktiv, Treiber installiert.
- `dev` @ `4268521`: Control Center jetzt auf **Port 8777**, SMOS-Update-Karte + Wächter (User-Unit), NVMe-Warnkarte.

## ToDos (Reihenfolge einhalten)
1. **`git pull --ff-only origin dev`** im Checkout (der Pi4-Stand ist älter als dev).
2. **Reboot von NVMe und prüfen**: bootet ohne SD-Eingriff? `cat /proc/cmdline` (root=UUID=...),
   `systemctl is-active pifinder pifinder-control-center`, Control Center auf `http://<pi4>:8777/`,
   Kamera/IMU/GPS ("Test hardware" im Control Center), `pacman -Q libcamera python-libcamera`.
3. **Issue #561 abarbeiten** (dringend): `smos-post-update.sh` gegen SMOS 2.4.0 verifizieren (NVMe- UND SD-Boot);
   `~/bin/smos-post-update.sh` ist eine alte Kopie (31.05.) - eine kanonische Kopie (Symlink auf das Repo-Skript
   bzw. vom Setup installiert); automatischer Hook beim Herunterfahren (vor dem Reboot, solange das alte System
   läuft); Rettungs-Doku. Details und Akzeptanzkriterien stehen im Issue.
4. **`--updatesd`**: Die SD-Karte hat SMOS 2.3.0 und ist der Notfall-Zugang. Sie wird NUR auf ausdrückliche
   Anweisung des Users aktualisiert (genau dafür gibt es `--updatesd`), sonst nichts darauf installieren oder
   ändern. Mountpunkte nie unter `/mnt` der SD anlegen (tmpfs `/run` nehmen).
5. **PFSM-Design-Lücke**: der Pi-Pfad von `restore_after_smos_update.sh` zeichnet die SMOS-Version auf, obwohl
   Control Center und INDI-Treiber dort nicht wiederhergestellt werden (nur das Setup-Update tut das). Der
   Pi-Pfad sollte am Ende - wie der x86-Pfad - das Setup-Update aufrufen (`--action=update --mode=full`).
6. **bm-Sync auf dem Pi4**: `rclone` ist wieder installiert, `~/.config/rclone/rclone.conf` prüfen, dann
   `bash ~/basic-memory/basic-memory/scripts/sync_basic_memory.sh`.
7. **Pi5**: zurückgestellt, frühestens in 2 Wochen. Nichts vorbereiten oder anstoßen. Wenn er dran ist: erst
   Daten sichern, dann ursachenklärend lesen (Checkliste in bm `00196`/`00195`); gleiche Ursache vermuten, aber
   nicht annehmen.
8. **Release**: #551-#562 (Port 8777, Wächter, Restore-/Install-Fixes, Warnkarte) stehen unter `[Unreleased]`;
   2.1.0 vorbereiten erst nach Rücksprache (Pi-Verifikation steht aus).

## Regeln, die hier gelten
- SSH auf allen Flotten-Geräten: **Port 5624**, nicht 22. Auf der UTM gibt es den Alias `smate-pi4`.
- Kein `Co-Authored-By: Claude` in Commits; `git push`/`gh`-Ausgaben mit `grep -v ghp_` filtern.
- Nichts verändern, was der User nicht ausdrücklich freigegeben hat; Boot-Konfiguration nur mit Sicherung und Go.
- Keine Werkzeuge neu erfinden, die es schon gibt (z. B. `smos-post-update.sh`); erst im Repo/bm suchen.

---

# PiFinder INDI Driver Development Session

## Main Requirements and Goal
The primary objective is to develop a stable, minimal INDI driver named `piffinder_lx200` that allows astronomical software like KStars/Ekos to interface with the PiFinder's telescope position server (`pos_server.py`).

## Current Status - **VERSION 2.0 STABLE**
The driver is now considered **stable for its core RA/DEC polling functionality**. The previous development branch (`pi4_lx200_v2.0_base_10micron_alpha`) has been successfully merged into the `main` branch to mark this milestone.

A new branch, `pi4_lx200_2.1_base_10micron_beta`, has been created to begin the next phase of development.

## Key Knowledge & Strategy - The Refined Development Loop
Our successful development loop involves the following steps, which will be strictly adhered to:
1.  **Build INDI Driver:** Execute `bin/build_indi_driver.sh`.
2.  **Check and Correct Code:** Analyze the `indi_driver_build.log` for any compilation or runtime errors. If errors exist, identify the root cause and make necessary code corrections in the `indi_pifinder/` directory.
3.  **Git Commit:** After *every* logical code change, commit the changes with a clear and concise message.
4.  **Update Session:** Reflect the current status, new knowledge, and next steps in `session/session.md` and `session/session_advanced.md`.
5.  **Test and Verify:** Connect to the driver in Ekos, verify logs (KStars/INDI), and confirm functionality.

This iterative process ensures systematic progress and proper documentation of changes.

-   **Core Development Strategy:** The driver should only implement functionality supported by the PiFinder. Unsupported commands must be overridden with empty functions that return success to prevent errors.
-   **PiFinder Protocol:** The `pos_server.py` script is the definitive source for supported LX200 commands.

## Files to re-read to resume session
To fully restore the context of this session, the following files should be read:
1.  `session/session.md` (this file)
2.  `session/session_advanced.md`
3.  `bin/build_indi_driver.sh` (to understand the build process)
4.  `indi_pifinder/lx200_pifinder.cpp` (the main driver implementation)
5.  `indi_pifinder/lx200_pifinder.h` (the driver's header file)
6.  `tmp/pos_server.py` (PiFinder command handler)

## Next Steps
The project is now ready for the next phase of development. Please provide the next set of instructions or features to implement.