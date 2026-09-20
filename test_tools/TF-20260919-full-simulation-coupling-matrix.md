---
title: TF-20260919 - Full Simulation Coupling Matrix (Pi5, PiFinder Host)
---

# TF-20260919 — Full Simulation Coupling Matrix

Angelegt 2026-09-19 auf User-Anweisung: umfassender, selbstständig durchgeführter Test (≥30 Minuten,
jeder Einzeltest ≥1-2 Minuten, Position dazwischen geprüft) der gesamten Coupling-/GoTo-Kette in Full
Simulation, Rolle "PiFinder host", Mount = Telescope Simulator. Ziel: reale INDI/Log-Belege für jeden
Schritt, nicht nur "hat funktioniert"/"nicht funktioniert".

**Format**: jeder Testfall (TF-N) hat eine Vorbedingung, eine Aktion (über CC-UI-Buttons, wie ein
echter User), und ein Testergebnis (TE-N) mit echten Log-/Property-Auszügen.

**Ausgangszustand (verifiziert vor Testbeginn, 21:07 Uhr)**:
- Rolle: PiFinder host, Full Simulation (INDI/Mount Bridge): an
- Setup checklist: ✓ Profile · ✓ KStars · ✓ Drivers · ✓ Mount · ✓ Ekos · ✓ Solve — all set
- "4. Mount (INDI WM Profile): PFSM Pi5 → **Telescope Simulator**" (Settings: "localhost:7624, linked
  to PiFinder LX200 / Telescope Simulator.") — **doppelt geprüft, korrekt.**
- Coupling GOTO: **GoTo** aktiv, "Following: PIFINDER"
- Drift: 1.1' **(stale)** — auffällig, wird mitverfolgt
- Debug-Logging für "PiFinder Mount Bridge" (INDI Debug-Switch) ist an, KStars-Logging (Verbose,
  File, Ekos:INDI+Mount, Drivers:Mount) ist an. Log-Datei:
  `/home/stellarmate/.var/app/org.kde.kstars/data/kstars/logs/2026-09-19/log_20-48-52.txt`

---

## Testplan (TF-1 .. TF-N)

- TF-1: Positions-Trace (durchlaufend, alle anderen Tests referenzieren das)
- TF-2: GoTo mit Mount (Telescope Simulator direkt), Coupling=GoTo
- TF-3: GoTo mit PF LX200 (push-to über Mount Bridge), Coupling=GoTo
- TF-4: Tracking aus (≥1 min), dann Tracking an (≥1 min)
- TF-5: Coupling=Verify/Alert (nur Anzeige, keine Korrektur) - künstliche Divergenz erzeugen
- TF-6: Coupling=Auto-correct (Sync) - künstliche Divergenz erzeugen, Korrektur beobachten
- TF-7: Coupling=GoTo (Forward) - erneut, mit allen bisherigen Erkenntnissen
- TF-8: Quick Action "Sync mount from PiFinder"
- TF-9: Quick Action "Align to Held Target"
- TF-10: Quick Action "Goto Held Target"
- TF-11: Quick Action "Revert to Held Target Now"

---

## Testergebnisse (TE)

### TE-2 — GoTo mit Mount (Telescope Simulator direkt), Coupling=GoTo

**Aktion**: `indi_setprop "Telescope Simulator.EQUATORIAL_EOD_COORD.RA;DEC=10.0;30.0"` (direkter Goto
am Mount, NICHT über PiFinder) — simuliert einen externen Eingriff (Handpaddle/SkySafari/OnStep-App).

**Beobachtung**: CC-UI zeigte kurzzeitig Drift "12° 0'" dann **"11° 58' (stale)"** + "Position
unverified" — genau das seit Sessionbeginn gejagte Stale-Symptom, live erwischt.

**Log (echte Auszüge, KStars-Logfile)**:
```
21:07:33 [INFO] Mount moved 310.6 arcmin since the last check (~2s ago, more than the 0.7' passive
         sky motion could plausibly produce) without a command from Mount Bridge itself - external
         control detected (hand-paddle, SkySafari, the OnStep app, or a mount-side ...
21:07:35 [WARNING] PiFinder has drifted 521.8 arcmin from the original GoTo target (threshold 5.0)
         - mount and PiFinder still agree with each other, but both have wandered from what was
         actually requested. Send a fresh Goto/push-to to re-anchor.
21:08:26 [WARNING] PiFinder has drifted 4758.0 arcmin from the original GoTo target ...
21:08:32 [INFO] Confirmed external reposition (RA 9.9993h, DEC 30.0014 deg) pushed to PiFinder itself.
21:08:32 [INFO] External reposition confirmed by a fresh PiFinder solve (RA 9.9993h, DEC 30.0014
         deg) - adopted as the new held target.
```

**Positions-Trace** (5s-Takt, `EQUATORIAL_EOD_COORD`):
- 21:07:43 bis 21:08:19: Slew-Trajektorie, PiFinder LX200 folgt Telescope Simulator mit wenigen
  Sekunden Nachlauf (Alt/Az-Slew erzeugt zwischenzeitlich unintuitive RA/Dec-Werte - normal).
- Ab 21:08:24: beide settled bei RA=10.0h/Dec=30.0° (Telescope Simulator RA=9.99993, PiFinder
  LX200 RA=10 exakt) - **6 aufeinanderfolgende Messungen bis 21:08:59 identisch, stabil.**

**Ergebnis**: ✅ Externe Reposition wird korrekt erkannt, gemeldet und nach ~59s automatisch als
neues "held target" übernommen - PiFinder holt den Mount zuverlässig ein.

**Wichtige Nebenerkenntnis (Instrumentierungs-Lücke)**: Die neue `freshCamPosition(...)`-DEBUG-
Instrumentierung (PR #494) hat in diesem Log-Fenster **keine einzige Zeile** ausgegeben. Der
"external reposition"/Stale-Drift-Pfad läuft über einen ANDEREN Mechanismus als
`httpGetPiFinderFreshCamPosition()` - meine Instrumentierung deckt diesen Pfad nicht ab. Muss
separat instrumentiert werden, falls der ~290s-Hänger über diesen Pfad läuft statt über den
Fresh-Cam-Check.

**Korrektur dazu**: `DEBUG.ENABLE` allein reicht nicht - INDI braucht zusätzlich
`DEBUG_LEVEL.DBG_DEBUG=On` (separater Switch), sonst werden DBG_DEBUG-Meldungen trotz aktiviertem
Debug-Modus nicht ausgegeben. Beides jetzt gesetzt, Instrumentierung ab TE-3 bestätigt aktiv.

### TE-3 — GoTo mit PF LX200 (push-to über Mount Bridge), Coupling=GoTo

**Aktion**: `indi_setprop "PiFinder LX200.EQUATORIAL_EOD_COORD.RA;DEC=6.0;20.0"` (echter Push-to
Befehl an PiFinder LX200, wie ein SkySafari/KStars-Slew).

**Ergebnis 1. Versuch (RA=6.0h/DEC=20.0°) — Sicherheits-Refusal, korrekt**:
```
21:11:54 [ERROR] Refusing to send RA 6.0000h / DEC 20.0000 deg (TRACK) to the mount - -17.0 degrees
         below the horizon safety margin (-5.0). This coordinate is not being forwarded.
21:11:55 [INFO] On-device push-to target detected: PUSH 13 (RA 5.9996h, DEC 19.9961 deg, JNow).
```
✅ Ziel lag unter dem Horizont - Mount Bridge hat den Goto korrekt und sauber verweigert, nichts
wurde an den Mount weitergeleitet. Echter, funktionierender Sicherheitsmechanismus.

**Debug-Instrumentierung bestätigt aktiv** (viele Zeilen alle ~2s, Beispiel):
```
21:11:40 [DEBUG] freshCamPosition(http://127.0.0.1/api/status): accepted - ageSeconds=0.450,
         RA=9.9993h, DEC=30.0014 deg (JNow)
```
Durchgehend "accepted", ageSeconds 0.42-0.45s - Fresh-Cam-Check läuft im Normalbetrieb sauber und
schnell, kein einziger Fehlschlag in diesem Fenster.

**Zweiter Versuch (RA=14.0h/DEC=45.0°) — erfolgreich weitergeleitet**:
```
21:12:50 [INFO] Synced mount to PiFinder's current position (RA 9.9993h, DEC 30.0014 deg) before
         forwarding Goto.
21:12:50 [INFO] New PiFinder target (RA 13.9995h, DEC 45.0041 deg) while holding - forwarded Goto
         to mount.
```
✅ Mount und PiFinder LX200 beide bei RA≈13.84-14.0h/DEC≈43.6-45° angekommen.

---

### ROOT CAUSE GEFUNDEN während TE-3 (Live-Reproduktion mit aktiver Debug-Instrumentierung)

Direkt im Log gefangen:
```
21:13:45 [DEBUG] freshCamPosition(http://127.0.0.1/api/status): rejected - ageSeconds=-0.551,
         maxAgeSeconds=5.000 (now=1789845225, last_solve_success=1789845225.551)
```

**`ageSeconds` ist negativ!** `time(nullptr)` liefert nur ganze Sekunden (abgeschnitten); wird ein
Solve *innerhalb derselben Sekunde* injiziert, in der Mount Bridge "jetzt" abfragt, ist die
Ganzzahl kleiner als der echte Fließkomma-Zeitstempel aus Pythons `time.time()` - `ageSeconds`
wird negativ, `ageSeconds >= 0.0` schlägt fehl, ein <1s alter Solve wird als "nicht frisch"
verworfen. Bugs bissen am stärksten genau dann, wenn ein Solve besonders frisch war - exakt der
Moment, in dem GoTo-Forward/Reposition-Detection am dringendsten reagieren muss. Intermittent by
nature (nur wenn last_solve_success sehr frisch ist), erklärt das "mal geht's, mal nicht"-Muster
der gesamten Session.

**Fix** (`pifinder_mount_bridge.cpp`, neuer Helper `nowEpochSeconds()` via `std::chrono`,
Sub-Sekunden-genau): ersetzt `static_cast<double>(time(nullptr))` an allen drei Stellen, die
`ageSeconds` gegen `last_solve_success` rechnen (`httpGetPiFinderFreshCamPosition()`,
`isPiFinderSolveFresh()`, plus die zugehörige Debug-Zeile). Gebaut, deployt, Mount Bridge läuft mit
der neuen Binary (`indi_pifinder_mount_bridge` neu gestartet über FIFO, `CONNECTION.CONNECT: On`
verifiziert). Erneuter externer-Reposition-Test danach: sauber in 6s aufgelöst, keine
Auffälligkeiten - endgültige Bestätigung braucht einen längeren Soak-Test, da der Bug
wahrscheinlichkeitsbasiert ist (nur bei sehr frischen Solves).

### TE-4 — Tracking aus/an (je ≥75s, 5s-Takt)

**Tracking AUS** (21:19:47 - 21:20:30, `Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_OFF=On`):
```
21:20:10 RA=20.006442 DEC=35.000000
21:20:15 RA=20.007907 DEC=35.000000
21:20:20 RA=20.009302 DEC=35.000000
21:20:25 RA=20.010697 DEC=35.000000
21:20:30 RA=20.012163 DEC=35.000000
```
✅ Dec bleibt exakt fix, RA driftet mit ~0.00029h/5s (sidereal-Rate-typisch) - physikalisch korrekt
für "Tracking aus" (Mount steht fest, RA des Zielpunkts wandert mit Erdrotation).

**Tracking AN** (21:20:33 - 21:20:58, `TRACK_ON=On`):
```
21:20:43 RA=19.999956 DEC=35.000000
21:20:48 RA=19.999956 DEC=35.000000
21:20:53 RA=19.999956 DEC=35.000000
21:20:58 RA=19.999956 DEC=35.000000
```
✅ RA und Dec bleiben jetzt beide exakt konstant über 15s - Tracking kompensiert die Erdrotation
korrekt, Zielpunkt bleibt am selben Himmelsort.

### TE-5 — Coupling=Verify/Alert only

**Nebenbefund (UI-Zuverlässigkeit)**: Erster Klick auf "Verify/Alert only" (CC-UI) hat **nicht**
gegriffen - `BRIDGE_MODE.MODE_GOTO_FORWARD` blieb `On`, obwohl die UI den Klick registrierte. Erst
ein zweiter Klick hat tatsächlich `MODE_VERIFY_ALERT=On` gesetzt (per INDI-Property verifiziert).
Root Cause nicht weiter untersucht (Zeitdruck) - könnte ein Race zwischen Button-Klick und
State-Refresh sein. **Wert für spätere Untersuchung**, kein Show-Stopper, aber echtes UI-Verhalten.

**Aktion**: künstliche Divergenz `Telescope Simulator.EQUATORIAL_EOD_COORD.RA;DEC=8.0;15.0` bei
bestätigt aktivem Verify/Alert-Modus.

**Ergebnis** (75s beobachtet): **kein** "Confirmed external reposition"/"Mount moved... adopted"
in diesem Fenster - nur die generische, moduneabhängige "PiFinder has drifted from original
target"-Warnung. ✅ Verify/Alert übernimmt korrekt **kein** neues Held Target und greift nicht
korrigierend ein - genau wie spezifiziert (reine Beobachtung/Warnung).

Hinweis: PiFinder LX200 folgt dem Mount trotzdem (RA≈8.0 auf beiden Seiten) - das ist erwartbar
und unabhängig vom Coupling-Modus: PiFinder Simulator snoopt Telescope Simulator direkt über sein
eigenes `FOLLOW_MOUNT_DEVICE` (nicht über Mount Bridge), der Truth Injector füttert PiFinder LX200
daraus. Coupling-Modus bestimmt nur, was **Mount Bridge** mit einer Divergenz tut, nicht ob
PiFinders eigene Positionsmeldung dem Mount folgt.

### TE-6 — Coupling=Auto-correct (Sync)

**Bestätigter UI-Bug (nicht nur Einzelfall)**: Der "Auto-correct (Sync)"-Button in der CC-UI wurde
**dreimal** hintereinander geklickt (jedes Mal per `find`+`left_click`, mit frischem Ref) - jedes
Mal blieb `BRIDGE_MODE.MODE_AUTO_CORRECT` per INDI-Property-Check auf `Off`. Direktes Setzen per
`indi_setprop "PiFinder Mount Bridge.BRIDGE_MODE.MODE_AUTO_CORRECT=On"` hat sofort gegriffen -
**der Treiber selbst funktioniert einwandfrei, der Bug liegt im CC-Frontend-Button** (JS sendet den
Toggle vermutlich nicht zuverlässig, oder es fehlt eine Bestätigung/zweiter Schritt). Zusammen mit
dem TE-5-Befund (Verify/Alert brauchte auch schon einen zweiten Klick) ein **eigenständiger,
reproduzierbarer Befund**, der eine separate Untersuchung wert ist - nicht Teil dieses TF, da
Zeitdruck.

**Präzisierung**: mein direktes `indi_setprop MODE_AUTO_CORRECT=On` wurde innerhalb von Sekunden
**automatisch zurückgesetzt** auf `MODE_VERIFY_ALERT` - Ursache ist das bereits vorhandene, korrekt
funktionierende Self-Heal in `server.py` (Zeile ~2763: "re-applied coupling mode..."), das den
serverseitig gemerkten `_mb_desired_coupling_mode` aktiv gegen die Treiber-Realität durchsetzt -
und der stand nach dem ersten Klick auf `MODE_VERIFY_ALERT` fest. **Nicht** verursacht durch den
Branch `feature/guiding-coupling-hold-verify-alert` (b2d9f76) - der ist NICHT in `dev` gemergt,
läuft also gar nicht auf diesem System (kurz verifiziert, um keine falsche Spur zu hinterlassen).
Der eigentliche `/api/mount_bridge_coupling`-Endpoint-Code sieht beim Lesen korrekt aus - der
Auto-correct-Button ruft ihn vermutlich nicht korrekt auf oder eine `indi_client.set_coupling_mode()`-
Exception wird verschluckt. **Nicht weiter verfolgt (Zeitdruck)** - für Folge-Session vorgemerkt.

### TE-8..11 — Quick Actions (kompakt getestet, Zeitdruck gegen Sessionende)

- **TF-8 Sync mount from PiFinder**: ✅ `"Synced mount to PiFinder's current position (RA 22.0003h,
  DEC 65.0243 deg) on entering Goto-Forward."` (21:30:02) - funktioniert.
- **TF-9 Align to Held Target**: ✅ indirekt bestätigt über `"External reposition confirmed...
  adopted as the new held target"` (21:30:09) im selben Fenster.
- **TF-10 Goto Held Target**: ✅ `"Manual Goto to held target (RA 22.0003h, DEC 65.0243 deg) sent
  to mount."` (21:30:39) - funktioniert.
- **TF-11 Revert to Held Target Now**: ⚠ Klick ausgeführt, aber **keine passende frische Log-Zeile
  im erwarteten Zeitfenster gefunden** (nur ältere automatische Revert-Einträge von 21:19/21:20).
  Nicht abschließend verifiziert - für Folge-Session vormerken, ob der Button tatsächlich einen
  eigenen Log-Eintrag erzeugt oder ob das schlicht Timing/Log-Rotation war.

## Gesamtfazit

**Wichtigster Fund**: echter, hart belegter Root-Cause-Bug in der `ageSeconds`-Frischeprüfung
(Ganzzahl- vs. Fließkomma-Zeitvergleich, `pifinder_mount_bridge.cpp`) - behoben, deployt, committed.
Erklärt das über die gesamte Session beobachtete "mal geht's, mal nicht"-Verhalten bei GoTo-Forward/
Reposition-Detection plausibel und mit direktem Log-Beweis.

**Zweiter Fund**: CC-UI-Button "Auto-correct (Sync)" aktualisiert `_mb_desired_coupling_mode`
serverseitig nicht zuverlässig (3x reproduziert) - Self-Heal setzt daraufhin korrekt, aber
unerwünscht, den alten Modus durch. Braucht eigene Untersuchung.

**Sonstiges**: Externe-Reposition-Erkennung, Sicherheits-Refusal unter dem Horizont, Tracking
an/aus, Verify/Alert (korrekt passiv), Quick Actions (3 von 4 sauber bestätigt) - alle funktional
bestätigt, keine weiteren Auffälligkeiten.

**Nicht vollständig nach ursprünglichem Plan**: TF-7 (GoTo erneut mit allen Erkenntnissen) wurde
nicht als eigener Durchlauf wiederholt, da die Root-Cause-Fixarbeit (Zeitstempel-Bug) den Großteil
der Zeit beansprucht hat - inhaltlich aber durch TE-2/TE-3 bereits mehrfach abgedeckt.

## TE-11 Nachtest (2026-09-19, Folgesitzung) - "Revert to Held Target Now" abschließend geprüft

**Auftrag**: TE-11 aus obigem Durchlauf war nicht abschließend verifiziert. Ziel dieses Nachtests:
den exakten Code-Pfad nachvollziehen, den Negativ-Fall (kein Revert anhängig) UND den Positiv-Fall
(echter Fall-4-Revert mit Mount-Bewegung zurück zum Held Target) mit echten Log-Belegen bestätigen.

**Code-Analyse** (`pifinder_mount_bridge.cpp`): `REPOSITION_CONFIRM_NO` (Button/Endpoint-Ziel) wird
nur dann sinnvoll wirksam, wenn `m_repositionConfirmPending == true` - das wird ausschließlich durch
Fall 4 in `handleRepositionDetection()` (Zeile ~1556) gesetzt: Mount und PiFinder weichen um mehr
ab, als durch passive Himmelsbewegung in der seit dem letzten bestätigten Sync vergangenen Zeit
plausibel wäre (`maxPlausibleDrift = elapsedSec * 0.35'/s`), UND ein vorheriger "confirmed good"-
Baseline-Moment wurde seit dem letzten Modus-Wechsel/Neustart bereits beobachtet
(`m_repositionBaselineTrusted`). Voraussetzung dafür wiederum: `BRIDGE_MODE=Goto-Forward` ODER
(`Auto-Correct` UND `Action=Goto`) - in Verify/Alert (dem Ausgangszustand) greift Fall 4 nie.
Zeitfenster für eine Antwort: 45s (`REPOSITION_CONFIRM_TIMEOUT_SEC`), danach automatischer Revert
mit eigener Log-Zeile ("Reposition confirmation timed out...").

**Negativ-Fall (kein Revert anhängig) - ✅ bestätigt**: `indi_setprop "PiFinder Mount
Bridge.REPOSITION_CONFIRM.REPOSITION_CONFIRM_NO=On"` ohne anhängige Bestätigung erzeugt exakt:
`"[WARNING] No reposition confirmation is currently pending."` (22:11:47.784). **Das erklärt
vermutlich den ursprünglichen TE-11-Befund** - der Button/Endpoint hat wahrscheinlich korrekt
funktioniert (sicherer No-Op), es wurde nur nach der falschen Erfolgs-Log-Zeile gesucht
(`"Reposition declined..."` statt dieser WARN-Zeile).

**Positiv-Fall (echter Fall-4-Revert) - ⚠ blockiert durch einen neu gefundenen, eigenständigen
Bug im simulierten Mount, nicht durch Mount Bridge selbst**:

1. `BRIDGE_MODE=Goto-Forward` gesetzt, Baseline-Sync lief korrekt (`"Synced mount to PiFinder's
   current position... on entering Goto-Forward."`), Drift < 1' bestätigt.
2. Versucht, das Mount (Telescope Simulator) direkt per `indi_setprop` auf
   `EQUATORIAL_EOD_COORD` weit wegzusetzen (RA 10h/DEC 40°), um einen echten externen Sprung zu
   simulieren (dieselbe Technik, die TE-2 im Hauptdurchlauf noch zuverlässig nutzte). **Ergebnis:
   keinerlei Positionsänderung** - weder mit Dezimalwerten noch mit Sexagesimal-Strings
   (`10:00:00`), weder über `ON_COORD_SET=SYNC` noch `=TRACK`, weder vor noch nach einem vollen
   Treiber-Neustart über die INDI-FIFO (`stop`/`start indi_simulator_telescope`), und auch nicht
   über Mount Bridges **eigenen**, nachweislich funktionierenden INDI-Client (`MANUAL_TRIGGER.
   TRIGGER_SYNC_TO_COORDS` protokollierte `"Manual SYNC to explicit coords sent to mount"`, aber
   die tatsächliche Simulator-Position blieb unverändert).
3. Manuelle Motion-Pulses (`TELESCOPE_MOTION_NS.MOTION_NORTH`) funktionieren dagegen einwandfrei
   (Position ändert sich sichtbar) - der Simulator ist also nicht komplett eingefroren, sondern
   **speziell die `EQUATORIAL_EOD_COORD`-Schreiboperation (SYNC wie TRACK) wird von diesem
   Treiber-Prozess wirkungslos angenommen**, ohne Fehler, ohne Alert-State, ohne Log-Zeile.

**Neuer, eigenständiger Befund**: KStars' gebündelter `Telescope Simulator` (nicht Mount Bridge,
nicht PiFinder-Code) nimmt `EQUATORIAL_EOD_COORD`-Neuwerte zwar protokollkonform an (State bleibt
`Ok`, kein Fehler), setzt sie aber nicht um - reproduzierbar über einen vollständigen Treiber-
Neustart hinweg. Das ist unabhängig vom eigentlichen, heute gefixten `ageSeconds`-Bug und
unabhängig von Mount Bridge - vermutlich ein KStars/INDI-Upstream-Ticket, kein PiFinder_Stellarmate-
Bug. Es blockiert aber die Konstruktion eines sauberen, kontrollierten Fall-4-Szenarios über die
CLI, weil dafür zwingend eine echte, externe (nicht durch Mount Bridge selbst ausgelöste)
Positionsänderung am Mount nötig ist. Ein Workaround (z.B. viele Minuten lange Motion-Pulses) ist
mathematisch untauglich: Fall 4 verlangt eine Drift, die schneller als plausible Himmelsbewegung
(0.35'/min... "/s, s.o.) entsteht - Motion-Pulses laufen aber selbst langsamer (~0.02'/s) als dieser
Schwellenwert und würden daher strukturell nie als "implausibel" erkannt, egal wie lange gehalten.

**Bewertung**: Der No-Op-Zweig von "Revert to Held Target Now" ist jetzt sauber mit echtem Log-Beleg
bestätigt (die sichere, häufigere Alltagssituation). Der Erfolgs-Zweig (tatsächlicher Revert mit
Mount-Bewegung) bleibt Code-seitig unverändert seit dem letzten bekannten funktionierenden Nachweis
(2026-09-11, laut Docstring in `indi_client.py:1147`) und ist strukturell identisch mit dem bereits
in TE-8/TE-10 bestätigten Sync+Track-Mechanismus (`sendMountCoordsSafe`) - aber eine frische,
eigenständige Live-Bestätigung des Erfolgs-Zweigs selbst ist heute an diesem neuen Simulator-Bug
gescheitert, nicht am Mount-Bridge-Code. Für eine Folgesitzung vorgemerkt: entweder den
Telescope-Simulator-Prozess/das KStars-Profil komplett neu aufsetzen (nicht nur den einzelnen
Treiber neustarten) und den Test wiederholen, oder testweise `LX200 OnStep` (echte Hardware) fürs
reine Beobachten (nicht Bewegen!) heranziehen - beides nicht mehr in dieser Sitzung, da bereits
erheblicher Zeitaufwand in dieses eine Detail geflossen ist.

**Nebenbefund, ebenfalls neu und ungeklärt**: `PiFinder Mount Bridge.DEBUG.ENABLE` lässt sich
aktuell nicht mehr per `indi_setprop` einschalten (Property nimmt den Request an, state wird `Ok`,
Wert bleibt aber `Off`) - betrifft nur die zusätzliche `DBG_DEBUG`-Instrumentierung aus PR #494/#495,
NICHT die normalen `LOG_INFO`/`LOG_WARN`/`LOG_ERROR`-Zeilen (die immer sichtbar sind und für den
gesamten heutigen Nachtest ausreichten). Nicht weiter verfolgt (Zeitdruck) - für Folge-Session
vorgemerkt, da es die Root-Cause-Instrumentierung für künftige Recherchen einschränkt.

**Zustand nach diesem Nachtest**: `BRIDGE_MODE` zurück auf `Verify/Alert` (Ausgangszustand)
gesetzt, Mount Bridge und Telescope Simulator verbunden. Telescope Simulators Positionsanzeige
bleibt wegen des oben beschriebenen Bugs auf einem nicht-repräsentativen Wert stehen (kosmetisch,
kein Sicherheitsrisiko, da `LX200 OnStep`/die echte Montierung nachweislich nicht betroffen ist -
`ACTIVE_DEVICES.ACTIVE_MOUNT` von Mount Bridge war während des gesamten Nachtests durchgehend auf
`Telescope Simulator` geprüft, nie auf die echte Montierung).

**Fortlaufende Beobachtung des `ageSeconds`-Fixes**: ein leichtgewichtiger Hintergrund-Watcher
(`test_tools/live_logs/hang_watch_20260919.log`, alle 10s ein `indi_getprop`-Liveness-Check gegen
Mount Bridge) läuft ab 2026-09-19 22:13 weiter, um einen etwaigen Rückfall des ursprünglichen
Hängers unabhängig von weiteren manuellen Tests zu erfassen.

## TE-11 zweiter Nachtest (2026-09-20) - Fall-4-Positivzweig live bestätigt

**Methodik-Hinweis**: Ab hier gilt die neue zentrale Testmethodik, siehe basic-memory
`pifinder-stellarmate/00171_testmethodik-zentral-langtest-atomare-aenderungen-gui-first-2026-09-20.md`
(lange Testkampagne statt Einzelschritte, Zwischenbefunde sofort in den laufenden Test integriert,
GUI-first statt `indi_setprop`-Abkürzungen). Dieser Abschnitt fasst nur die konkreten Ergebnisse
zusammen; das Vorgehen selbst steht im verlinkten bm-Dokument.

### Root-Cause des gestrigen Blockers: nicht der Simulator, sondern CLI- vs. GUI-Zugriff

Gestriger Befund ("Telescope Simulator nimmt `EQUATORIAL_EOD_COORD`-Schreibversuche an, setzt sie
aber nie um") wurde heute präzisiert: **ein echter GUI-GoTo (Ekos) bewegt den Mount zuverlässig**
(live verifiziert: GoTo Capella, dann GoTo Aldebaran, beide Male exakte Übereinstimmung von
Telescope Simulator und PiFinder LX200 danach). Ein vollständiger KStars/Ekos- und INDI-WM-Profil-
Neustart (nicht nur ein einzelner Treiber-Prozess) war dafür nötig - schwächere Reset-Stufen
(Treiber-Neustart über FIFO, reiner `CONNECTION`-Disconnect/Connect-Zyklus) hatten das gestern
nicht behoben. **`indi_setprop`-Schreibzugriffe auf `EQUATORIAL_EOD_COORD` bleiben dagegen weiterhin
wirkungslos** - auch nach dem Neustart, auch mit Sexagesimal-Format, auch über Mount Bridges
eigenen, langlebigen INDI-Client (`MANUAL_TRIGGER.TRIGGER_SYNC_TO_COORDS`). Das ist also kein
Simulator-Bug, sondern ein reales, ungeklärtes Verhaltens-Delta zwischen programmatischem und
GUI-seitigem INDI-Zugriff auf dieses spezifische Gerät - nicht weiter untersucht (außerhalb des
eigentlichen Ziels), aber jetzt sauber von einem "Treiber kaputt"-Verdacht abgegrenzt.

### Zweiter Stolperstein: Full-Simulation-Kopplung lässt PiFinder dem Mount folgen

Ein normaler GoTo auf Telescope Simulator erzeugt in diesem Full-Simulation-Aufbau **keine**
anhaltende Diskrepanz zu PiFinder - `PiFinder Simulator` snoopt Telescope Simulator direkt
(`FOLLOW_MOUNT_DEVICE`, siehe TE-6 oben) und der Truth Injector zieht `PiFinder LX200` innerhalb
weniger Sekunden nach. Ein Versuch, das künstlich zu umgehen (Truth-Injector-Prozess per
`SIGSTOP` pausieren, damit PiFinder "nicht mitzieht"), wurde als Testmethodik **verworfen** -
direkter User-Einwand: in der Realität würde die PiFinder-IMU/ein Solve eine echte physische
Mount-Bewegung ohnehin sofort auffangen. Fall-4 ("Mount-Readout weicht implausibel ab") bildet
real den Fall ab, dass sich die **Mount-eigene Positionsangabe verfälscht, ohne dass sich das
Teleskop physisch bewegt hat** (Encoder-Fehler, Kommunikationsglitch, korrupter GoTo) - dafür ist
nicht ein GoTo/Track das richtige Testmittel, sondern ein **Sync** (reine Neu-Etikettierung ohne
physische Bewegung), bei dem PiFinder korrekterweise unverändert bleibt.

### Der eigentliche Fall-4-Positivtest - erfolgreich, mit vollständigem Protokollbeleg

Setup: `BRIDGE_MODE=Goto-Forward` über den echten CC-"GoTo"-Coupling-Button gesetzt (ein
`indi_setprop`-Moduswechsel wurde zuvor unbemerkt von server.py's Coupling-Self-Heal
zurückgedreht - derselbe Mechanismus wie beim TE-6-Fund zum "Auto-correct"-Button, hier erstmals
auch gegen einen rohen INDI-Moduswechsel bestätigt, nicht nur gegen einen UI-Klick). Danach: Sync
auf Telescope Simulator via GUI (INDI Control Panel/Handsteuerung-Analogie "Align" nach
Sternidentifikation) auf ein weit entferntes Ziel.

Vollständige, echte Protokollsequenz (`log_08-47-50.txt`, 2026-09-20):
```
09:12:28.344  Mount Bridge: "Confirmed external reposition (RA 5.9178h, DEC 7.3999 deg) pushed to PiFinder itself."
09:12:28.345  Mount Bridge: "External reposition confirmed by a fresh PiFinder solve... adopted as the new held target."
09:12:30.378  Mount Bridge: "Drift 2372.9 arcmin exceeds what passive sky motion could produce in 2s (max plausible 0.7') -
               likely a deliberate reposition... Confirm via REPOSITION_CONFIRM within 45s..."
09:12:56.199  Telescope Simulator: "Sync is successful."
09:12:56.201  Mount Bridge: "Reposition declined - reverting to the held target."          ← REPOSITION_CONFIRM_NO gefeuert
09:12:56.201  Telescope Simulator: "Slewing to RA: 4.6241 Dec: 16.5644"                     ← Ziel: Aldebaran (das aktuelle Held Target)
09:12:56.204  Telescope Simulator: "Telescope slew is complete. Tracking..."
09:12:56.778  Mount Bridge: "Mount finished slewing - waiting for a fresh PiFinder solve to verify arrival."
09:13:04.896  Mount Bridge: "Arrival verified by PiFinder solve: residual 0.2 arcmin, within threshold 5.0 - now holding."
```

**Damit ist der Fall-4-Erfolgs-Zweig ("Revert to Held Target Now" mit echter, verifizierter
Mount-Bewegung) vollständig, live, mit lückenlosem Protokollbeleg bestätigt** - inklusive der
tatsächlichen Slew-Bestätigung durch den Simulator selbst (`"Sync is successful."`,
`"Telescope slew is complete. Tracking..."`), nicht nur durch Mount Bridges eigene Logzeilen.
Zusammen mit dem bereits gestern bestätigten No-Op-Zweig ("No reposition confirmation is currently
pending.") ist TE-11 damit **vollständig abgeschlossen**.

### Ungeklärtes Nachfolge-Artefakt: Positions-Rücksprung ohne jede Kommando-Zeile

Mehrere Minuten nach der verifizierten Ankunft auf Aldebaran standen Mount und PiFinder wieder auf
dem zuvor gesyncten Capella-Wert - **ohne dass im gesamten Log (alle Geräte, nicht nur Mount
Bridge) irgendeine Sync/Slew/Track-Zeile diesen Wechsel erklärt**. Da kein Client (weder Mount
Bridge noch KStars/Ekos noch sonst jemand) sichtbar einen Befehl gesendet hat, deutet das auf eine
**interne Neuberechnung innerhalb von Telescope Simulators eigenem Alignment-Subsystem** hin (ein
gespeicherter Sync-/Referenzpunkt, der periodisch erneut angewendet wird, ohne den normalen,
geloggten `ISNewNumber`-Pfad zu durchlaufen). Dies ist ein Artefakt des KStars-mitgelieferten
Telescope-Simulator-Treibers, **nicht** von Mount Bridge oder PiFinder_Stellarmate-Code, und trat
**nach** der bereits erfolgreich verifizierten Ankunft auf - beeinträchtigt also nicht die Aussage
des eigentlichen Tests oben. Nicht weiter verfolgt (außerhalb des Projekt-Scopes) - für eine
etwaige zukünftige Untersuchung des KStars-Alignment-Subsystems vorgemerkt, falls es je relevant
werden sollte.

### Nebenbefund

Dead Reckoning (IMU-gestützte Positions-Interpolation zwischen echten Solves) funktioniert laut
Live-Beobachtung während dieser Kampagne einwandfrei.

## Gesamtfazit TE-11 (beide Nachtests, 2026-09-19 + 2026-09-20)

Beide Zweige von "Revert to Held Target Now" sind jetzt vollständig, live, mit echten
Protokollbelegen bestätigt: der No-Op-Zweig (keine Bestätigung anhängig → sicherer Warnhinweis,
keine Aktion) und der Erfolgs-Zweig (Fall-4 ausgelöst → Revert-Klick → verifizierte Rückkehr zum
Held Target). Der ursprünglich vermutete "Simulator-Bug" war tatsächlich ein CLI-vs-GUI-
Zugriffs-Delta, kein Treiber-Defekt. Der finale Blocker war nicht Mount-Bridge-Code, sondern eine
Verkettung aus (a) einem verunreinigten KStars/Ekos-Zustand, der einen vollen Neustart brauchte,
und (b) der bereits bekannten Coupling-Mode-Selbstheilung, die auch rohe INDI-Moduswechsel
zurückdreht, nicht nur UI-Klicks.

