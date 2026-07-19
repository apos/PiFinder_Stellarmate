# PiFinder auf Stellarmate

*[English version](README.md)*

![PiFinder am Teleskop unter Sternenhimmel](docs/images/readme/PiFinder.jpg)

Dieses Projekt stellt eine Reihe von Skripten bereit, um die [PiFinder](https://www.pifinder.io/)-Software nahtlos in eine [Stellarmate](https://www.stellarmate.com/)-Umgebung zu installieren, zu patchen und zu integrieren. Es automatisiert den gesamten Einrichtungsprozess und sorgt dafür, dass PiFinder korrekt neben den bestehenden Stellarmate-Diensten funktioniert.

Das Hauptziel ist es, Nutzern die leistungsfähigen Plate-Solving- und Objektsuche-Funktionen von PiFinder auf einem Gerät zugänglich zu machen, das gleichzeitig Stellarmate für Astrofotografie, EAA und vollständige Ausrüstungssteuerung betreibt.

> ### ⚠️ **Haftungsausschluss**
>
> * Dies ist ein Community-Projekt und steht in keiner offiziellen Verbindung zu PiFinder oder Stellarmate.
> * Die Nutzung dieser Skripte erfolgt auf eigenes Risiko. Der Autor haftet nicht für Schäden an Hardware oder Software.
> * Dieser Ablauf wurde mit der in `version.txt` angegebenen PiFinder-Version getestet.

> ### ✅ **Aktuelle Version — v1.0.0**
>
> * Gebaut und verifiziert für **PiFinder-Software 2.6.0** auf **StellarMate OS 2.2.1** (Arch Linux).
> * **Raspberry Pi 4**: Vollständig unterstützt — Kamera ✅, Plate-Solve ✅, IMU ✅, GPS ✅. Unter echtem Nachthimmel getestet (2026-07-12).
> * **Raspberry Pi 5**: Unterstützt — GPS ✅, Web-UI ✅, Tastatur ✅, OLED ✅. (Ein monatelanges "OLED bleibt dunkel"-Problem entpuppte sich als defektes HAT-Board, kein Pi5-/Software-Problem — gelöst am 2026-07-17 durch Austausch des physischen HAT-Boards.) Kamera benötigt ein 15-poliges FFC-CSI-Adapterkabel (Pi4 nutzt 22-polig) — beim Testgerät noch nicht verbaut.
> * **INDI-Integration**: eigenständiger LX200-Treiber + optionale Kopplung an eine echte Montierung ("Mount Bridge"), Ende-zu-Ende verifiziert gegen eine echte Skywatcher-EQ5/OnStepX-Montierung — siehe [Readme_PiFinder_LX200_de.md](Readme_PiFinder_LX200_de.md) und [CHANGELOG.md](CHANGELOG.md).

---

## Schnellstart

**1. Browser-Installation (empfohlen)**

```bash
git clone https://github.com/apos/PiFinder_Stellarmate.git
cd PiFinder_Stellarmate
bash gui_installer/launch_setup_gui.sh
```

Öffne die Seite anschließend im Browser — direkt auf dem Pi oder von jedem anderen Gerät im
gleichen Netzwerk aus (keine Desktop-Sitzung auf dem Pi nötig). Details siehe
[Setup-GUI / Control Center](#setup-gui--control-center-empfohlen).

<table>
<tr>
<td align="center">
<a href="docs/images/readme/Setup_via_remote_browser.png"><img src="docs/images/readme/Setup_via_remote_browser.png" width="700"></a><br>
<sub>Die Setup-GUI, von einem anderen Gerät im Netzwerk aus geöffnet</sub>
</td>
</tr>
</table>

**2. Terminal-Installation**

```bash
git clone https://github.com/apos/PiFinder_Stellarmate.git
cd PiFinder_Stellarmate
./pifinder_stellarmate_setup.sh
```

Alle Details: [Installation](#installation).

---

## Hauptfunktionen & Änderungen

Dieses Setup passt die Standard-PiFinder-Installation an, um sie besser mit Stellarmate zu integrieren:

*   **Automatisierte Installation:** Ein einziges Skript kümmert sich um das Herunterladen der richtigen PiFinder-Version, das Anlegen einer Python-Virtual-Environment, die Installation der Abhängigkeiten und das Anwenden aller notwendigen Patches.
*   **INDI-Integration für KStars/Ekos & SkySafari:** Ein eigenständiger `PiFinder LX200`-INDI-Treiber meldet PiFinders gesolvte Position und leitet GoTo-Anfragen als Push-to-Ziel an PiFinder weiter. Ein optionaler `PiFinder Mount Bridge`-Treiber kann diese Position an jeden echten INDI-Mount-Treiber koppeln (Verify/Alert, Auto-Correct bei Drift, oder vollständiges event-basiertes GoTo-Weiterreichen). Linkt direkt gegen System-`libindi` — kein INDI-Source-Checkout, kein kompletter INDI-Build nötig. Wird automatisch vom Haupt-Setup-Skript gebaut und installiert — siehe [Readme_PiFinder_LX200_de.md](Readme_PiFinder_LX200_de.md) für die technische Referenz und bebilderte Einrichtungsschritte (Web-Manager-Profil, INDI Control Panel, KStars/Ekos, SkySafari).
*   **Stellarmate-GPS-Integration:** PiFinder ist so konfiguriert, dass es Stellarmate/KStars als GPS-Quelle nutzt — ein separates GPS-Modul am PiFinder ist damit überflüssig.
*   **Netzwerkverwaltung deaktiviert:** Alle Netzwerk-Konfigurationsoptionen (WLAN-Modus, AP/Client-Umschaltung) wurden aus PiFinders OLED-Menü und Weboberfläche entfernt. Das verhindert Konflikte, da Stellarmate für die gesamte Netzwerkverwaltung zuständig ist.
*   **Robustes Patchen:** Änderungen werden über `diff`-Patches angewendet, was den Prozess zuverlässiger und wartbarer macht als manuelle Dateiänderungen.
*   **Kompatibilität:** Die Skripte sind für Raspberry Pi 4 und Pi 5 unter Stellarmate OS (Arch Linux) ausgelegt. Beide werden vollständig unterstützt — den aktuellen Stand pro Pi siehe Versions-Banner oben.
*   **Umfassende IP-Adress-Anzeige:** Die Weboberfläche und der OLED-Statusbildschirm des Geräts zeigen jetzt alle verfügbaren Nicht-Localhost-IP-Adressen an, was die Netzwerksichtbarkeit verbessert.
*   **Dynamischer Nutzer:** Die Authentifizierung der Weboberfläche wurde so gepatcht, dass sie den aktuellen Systemnutzer (z.B. `stellarmate`) statt eines fest hinterlegten Standardnutzers verwendet.
*   **Passwortgeschützte Setup-GUI:** Der Webserver von `gui_installer/` (destruktive Reinstall/Update/Reboot-Aktionen) verlangt jetzt dasselbe Systemnutzer-Passwort wie PiFinders eigener Remote-Login, geprüft via PAM — kein separates Passwort zu merken.

## Hardware-Anforderungen

### Raspberry Pi 4 *(funktioniert für Basis-Aufgaben)*

| Komponente | Anforderung |
|---|---|
| RAM | ≥ 4 GB (absolutes Minimum — 2 GB nicht möglich) |
| Speicher | USB-3.0-NVMe-HAT (**zwingend** — SD-Karte reicht nicht aus) |
| Strom | Power-HAT ≥ 5 A (**zwingend** — USB-Strom reicht nicht aus) |

### Raspberry Pi 5 *(empfohlen)*

| Komponente | Anforderung |
|---|---|
| RAM | > 4 GB (≥ 8 GB empfohlen) |
| Speicher | NVMe-HAT mit PCIe (**zwingend** — SD-Karte reicht nicht aus) |
| Strom | Power-HAT ≥ 5 A (**zwingend** — USB-C PD 5 A kann funktionieren) |

> **Hinweis zur Kamera (Pi 5):** Der Pi 5 nutzt einen **15-poligen FFC-CSI-Anschluss**, während der Pi 4 22-polig ist. Für den Anschluss des PiFinder-Kameramoduls an einen Pi 5 wird ein Adapterkabel benötigt.

---

## Installation

Der Einrichtungsprozess ist bewusst einfach gehalten. Er führt dich durch eine Neuinstallation oder die Aktualisierung einer bestehenden.

### Voraussetzungen

*   Ein Raspberry Pi 4 oder Pi 5 mit PiFinder-Hardware (Hat, Display, Kamera usw.).
*   Stellarmate OS 2.1.1 (Arch Linux) installiert und laufend.
*   Grundlegende Vertrautheit mit der Linux-Kommandozeile.

### Einrichtungsschritte

1.  **Hardware-Schnittstellen aktivieren:**
    SPI und I2C werden vom Setup-Skript automatisch über `/boot/config.txt` aktiviert. Auf Stellarmate OS (Arch Linux) ist kein manueller Schritt nötig. `raspi-config` ist auf dieser Plattform nicht verfügbar.

2.  **Repository klonen:**
    Öffne ein Terminal auf deinem Stellarmate-Gerät und klone dieses Repository:
    ```bash
    git clone https://github.com/apos/PiFinder_Stellarmate.git
    cd PiFinder_Stellarmate
    ```

3.  **Setup-Skript ausführen:**
    Führe das Haupt-Setup-Skript aus. Es erkennt, ob bereits eine PiFinder-Installation existiert, und bietet dir entsprechende Optionen.
    ```bash
    ./pifinder_stellarmate_setup.sh
    ```

    *   **Falls kein PiFinder gefunden wird:** Das Skript klont das offizielle PiFinder-Repository und wendet alle nötigen Patches an.
    *   **Falls PiFinder gefunden wird:** Du wirst gefragt, ob du:
        *   **1. Von Grund auf neu installieren möchtest:** Löscht das bestehende PiFinder-Verzeichnis vollständig und führt eine Neuinstallation durch.
        *   **2. Aktualisieren möchtest:** Setzt dein lokales PiFinder auf die offizielle `release`-Branch-Version zurück und wendet alle Patches erneut an.

4.  **Python-Virtual-Environment (nur beim ersten Durchlauf):**
    Beim ersten Ausführen des Skripts auf einem frischen System stoppt es, nachdem eine Python-Virtual-Environment (`.venv`) angelegt wurde. Du musst diese manuell aktivieren und das Skript erneut ausführen, um die Installation der Abhängigkeiten abzuschließen. Das Skript zeigt dir die genauen Befehle an, die etwa so aussehen:
    ```bash
    source /home/stellarmate/PiFinder/python/.venv/bin/activate
    ./pifinder_stellarmate_setup.sh
    ```
    Danach wird die Installation abgeschlossen, die PiFinder-Dienste werden gestartet, und die
    PiFinder-LX200- + Mount-Bridge-INDI-Treiber werden automatisch gebaut und installiert — siehe
    [Der INDI-Treiber](#der-indi-treiber) unten für das Web-Manager-Profil-Setup.

### Setup-GUI / Control Center (empfohlen)

Wer nicht die rohe Terminal-Ausgabe beobachten möchte: `gui_installer/` bietet eine kleine lokale
Webseite — das "PiFinder on Stellarmate Control Center" —, die dasselbe Setup-Skript mit einer live
mitscrollenden Statusanzeige im Browser ausführt, inklusive automatischer Behandlung des "venv
aktivieren und neu starten"-Schritts sowie der Reinstall/Update-Auswahl per Button (jeweils mit
Bestätigungsabfrage), sodass nichts mehr an einem Prompt eingetippt werden muss. Über die
Installation/Aktualisierung hinaus dient sie auch als laufendes Dashboard: eine Modus-Kachel zeigt,
ob PiFinder gerade real läuft oder in einer entkoppelten Fake-Hardware-Instanz für Entwicklung/Tests
(mit Umschalt-Button und einer Hardware-Checkliste — Kamera/IMU/GPS, direkt gegen die Hardware
geprüft statt PiFinders eigenem Software-Status vertrauend), ein "Solve Simulation"-Umschalter für
PiFinders eigenen Test-Modus, ein "Toggle Display"-Button für ein optionales kleines SPI-Zweitdisplay
(siehe `test_tools/`) sowie immer verfügbare Reboot-/Shutdown-Buttons für den ganzen Pi. Starten mit:
```bash
bash gui_installer/launch_setup_gui.sh
```
oder `PiFinder Setup.desktop` nach `~/Desktop/` kopieren/verlinken für ein klickbares
Icon. Es ist derselbe Installer darunter — nützlich vor allem, wenn man Installationen/Reinstalls
häufiger wiederholt (z.B. beim Testen).

Der Launcher ist idempotent und gibt immer eine klare Rückmeldung — ein erneuter Aufruf, während
der Webserver schon läuft, meldet das nur, statt einen zweiten zu starten:
```
$ bash gui_installer/launch_setup_gui.sh
Starting setup GUI webserver...
Webserver started.
   Setup GUI reachable at:
     http://192.168.0.105:8765/
     http://10.250.250.1:8765/
   Login: any username, password = your stellarmate system password
   (protects the page itself plus Reinstall/Update/Reboot; /state,
   /log and /shutdown stay reachable without login)
   To stop: gui_installer/launch_setup_gui.sh --shutdown-webserver

$ bash gui_installer/launch_setup_gui.sh
Setup GUI webserver is already running.
   Setup GUI reachable at:
     http://192.168.0.105:8765/
     http://10.250.250.1:8765/
   Login: any username, password = your stellarmate system password
   (protects the page itself plus Reinstall/Update/Reboot; /state,
   /log and /shutdown stay reachable without login)
   To stop: gui_installer/launch_setup_gui.sh --shutdown-webserver
```
*(Die Ausgabe des Skripts selbst ist auf Englisch, konsistent mit dem restlichen Setup.)*
Um den Webserver im Hintergrund wieder zu stoppen:
```bash
bash gui_installer/launch_setup_gui.sh --shutdown-webserver
```

<table>
<tr>
<td align="center" width="50%">
<a href="docs/images/readme/Setup_Browser.png"><img src="docs/images/readme/Setup_Browser.png" width="380"></a><br>
<sub>Live-Fortschrittsbalken, Schritt-Checkliste und Terminal-Ausgabe nebeneinander</sub>
</td>
<td align="center" width="50%">
<a href="docs/images/readme/Setup_Ready.png"><img src="docs/images/readme/Setup_Ready.png" width="380"></a><br>
<sub>Setup abgeschlossen: OLED-Spiegel und Quick-Links-Kachel (PiFinder-Status, INDI-Drivers-Seite, Links dieser Seite selbst, GitHub-Docs)</sub>
</td>
</tr>
</table>

## Nach der Installation: PiFinders "INDI Drivers"-Seite

Sobald PiFinder läuft, bekommt seine eigene Webseite (`/remote`, Standardpasswort `smate`) einen
neuen Menüpunkt **"INDI Drivers"** (`/smos`). Er ist die On-Device-Begleitung zu den zwei manuellen
Schritten unten:

1. **StellarMate Web Manager einrichten** — zeigt denselben Screenshot wie
   [Readme_PiFinder_LX200_de.md](Readme_PiFinder_LX200_de.md) plus direkte Links zum Web Manager
   für jede IP dieses Pi, damit du den Port (`8624`) nicht selbst heraussuchen musst.
2. **PiFinder-Stellarmate-Control-Center-Status/-Steuerung** — zeigt, ob der Webserver von
   `gui_installer/` gerade läuft, mit Start/Stop-Buttons, damit du ihn (z.B. für ein späteres
   PiFinder-Update) ohne Terminal neu starten kannst. Erreichbarkeits-Links für das Control Center
   selbst werden ebenfalls aufgelistet.

Diese Seite braucht kein Login (dieselbe Begründung wie bei PiFinders eigener Startseite — sie muss
direkt nach einem frischen Boot funktionieren) und ist als erste Anlaufstelle nach einer
Neuinstallation, einem Update oder einem Reboot gedacht.

<table>
<tr>
<td align="center" width="50%">
<a href="docs/images/pfinder_lx200/webmanager_profile.png"><img src="docs/images/pfinder_lx200/webmanager_profile.png" width="380"></a><br>
<sub>Karte 1: StellarMate-Web-Manager-Profil mit laufenden PiFinder-LX200- und PiFinder-Mount-Bridge-Treibern</sub>
</td>
<td align="center" width="50%">
<a href="docs/images/readme/Setup_Ready.png"><img src="docs/images/readme/Setup_Ready.png" width="380"></a><br>
<sub>Karte 2: PiFinder-Stellarmate-Control-Center-Status/-Steuerung</sub>
</td>
</tr>
</table>

## Der INDI-Treiber

`pifinder_stellarmate_setup.sh` baut und installiert beide INDI-Treiber für dich (stoppt zuerst
eine ggf. laufende Instanz, startet danach den StellarMate Web Manager neu, damit die
neuen/aktualisierten Treiber in seinem Katalog auftauchen). Die Build-Skripte musst du nur dann
selbst aufrufen, wenn du **nur** die Treiber neu bauen willst, ohne das komplette Setup erneut
laufen zu lassen (z.B. nach dem Pullen einer reinen Treiber-Code-Änderung):

```bash
cd ~/PiFinder_Stellarmate
bash bin/build_indi_driver.sh     # PiFinder LX200
bash bin/build_indi_bridge.sh     # PiFinder Mount Bridge (optional, nur bei echter Montierung)
```

<a href="docs/images/pfinder_lx200/indi_control_panel_tabs_PiFinder_LX200_main.png"><img src="docs/images/pfinder_lx200/indi_control_panel_tabs_PiFinder_LX200_main.png" width="380"></a><br>
<sub>PiFinder LX200s eigener INDI-Control-Panel-Tab, verbunden und mit live gemeldeter, gelöster Position</sub>

Für die vollständige Einrichtungs-Anleitung (StellarMate-Web-Manager-Profil, INDI Control Panel, KStars/Ekos-Remote-Modus, SkySafari), die komplette LX200-Kommando-/Property-Referenz und eine Erklärung der Code- und Deployment-Strategie siehe **[Readme_PiFinder_LX200_de.md](Readme_PiFinder_LX200_de.md)**.

## SMOS-Updates

Stellarmate OS nutzt BTRFS-Snapshot-Resets zur Anwendung von Updates. Das setzt die Root-Partition zurück, wodurch alle manuell installierten Pakete und Konfigurationen (Pacman-Repos, systemd-Dienste, Swap usw.) entfernt werden. Die `/home`-Partition bleibt dabei unversehrt.

Führe nach jedem SMOS-Update das Wiederherstellungs-Skript aus:

```bash
bash ~/PiFinder_Stellarmate/bin/restore_after_smos_update.sh
sudo reboot
```

Dies stellt alles wieder her, was PiFinder benötigt: Pacman-Repos, Systempakete, Hardware-Gruppen, udev-Regeln, `/boot/config.txt`-Overlays, Swapfile und systemd-Dienste.

### Synchronisation von basic-memory / Claude-Kontext mit Nextcloud

Das Post-Update-Skript kümmert sich auch um die Synchronisation des Claude-AI-Gedächtnisses und -Kontexts mit Nextcloud:

```bash
bash ~/PiFinder_Stellarmate/bin/smos-post-update.sh --sync-memory
```

> **Hinweis:** `rclone` wird automatisch von `restore_after_smos_update.sh` installiert. Der Nextcloud-Remote muss vorher in `~/.config/rclone/rclone.conf` konfiguriert sein (Remote-Name: `nextcloud`, WebDAV).

### Versionskompatibilität

| PiFinder | SMOS | Pi 4 | Pi 5 |
|---|---|---|---|
| 2.6.0 | 2.2.1 | ✅ vollständig getestet | ✅ GPS/Web-UI/Tastatur/OLED bestätigt — Kamera-Adapterkabel ausstehend |
| 2.6.0 | 2.1.1 | ✅ getestet | ⚠️ seit dem OLED-Fix nicht erneut verifiziert (hardwarebasiert, sollte also übertragbar sein — siehe Zeile 2.2.1) |
| 2.5.1 | 2.1.1 | ✅ getestet | — |

## Deinstallation

Ein Skript zum sicheren Entfernen der PiFinder-Installation und -Dienste steht bereit.

```bash
~/PiFinder_Stellarmate/bin/uninstall_pifinder_stellarmate.sh
```

Dies stoppt und deaktiviert die `pifinder`-Dienste, entfernt die systemd-Dateien und löscht das `~/PiFinder`-Verzeichnis. Das Verzeichnis `~/PiFinder_data` sowie das `PiFinder_Stellarmate`-Repository selbst werden dabei nicht entfernt.

## Siehe auch

*   **[Readme_PiFinder_LX200_de.md](Readme_PiFinder_LX200_de.md)** — vollständige INDI/Mount-Bridge-Dokumentation: bebilderte Einrichtungsanleitung, LX200-Kommando-/Property-Referenz, Code- und Deployment-Strategie. ([English version](Readme_PiFinder_LX200.md))
*   **[Readme_design_decisions_de.md](Readme_design_decisions_de.md)** — Zusammenfassung der wichtigsten Design-Entscheidungen.
*   **[CHANGELOG.md](CHANGELOG.md)** — Versionshistorie.
*   **[bin/README_compile_indi.md](bin/README_compile_indi.md)** — kurze Build-Referenz für den PiFinder-LX200-Treiber.
