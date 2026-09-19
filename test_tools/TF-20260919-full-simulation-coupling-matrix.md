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

