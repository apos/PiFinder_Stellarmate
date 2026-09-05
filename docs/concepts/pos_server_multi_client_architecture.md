# Concept: `pos_server.py` multi-client architecture

## 1. Grundlagen — was dieser Server ist und wofür

`PiFinder/python/PiFinder/pos_server.py` (Port 4030, TCP) ist PiFinders eigener LX200-Protokoll-Server:
er lässt beliebige Planetariumssoftware PiFinder als generisches "Teleskop" ansprechen — Position
auslesen (`:GR#`/`:GD#`), PushTo/GoTo-Ziele senden (`:Sr#`/`:Sd#`), Standort/Uhrzeit abgleichen.
Laut Dateikopfkommentar explizit für SkySafari (iOS/iPadOS) gebaut, wird aber von mehreren,
tatsächlich unabhängigen Client-Typen gleichzeitig angesprochen:

| Client | Wie er andockt |
|---|---|
| **SkySafari** (iOS/iPadOS) | direkt per LX200/TCP gegen Port 4030 |
| **Stellarium** | direkt per LX200/TCP gegen Port 4030 (sendet zusätzlich das ACK-Byte, s. `is_stellarium`) |
| **KStars/EKOS** | indirekt — der eigene `PiFinder LX200`-INDI-Treiber (`indi_pifinder_lx200`, PiFinder_Stellarmate) verbindet sich SEINERSEITS als Client gegen Port 4030 und veröffentlicht das Ergebnis als INDI-Property |
| **StellarMate-App (SMOS)** | **korrigiert (User-Hinweis)**: die SMOS-App ist selbst ein generischer **INDI-Client** — sie kann jedes beliebige, an `indiserver` angeschlossene INDI-Teleskop ansprechen, exakt wie KStars. Sie nutzt also denselben Pfad wie KStars (über `PiFinder LX200`/`PiFinder Mount Bridge` als INDI-Gerät), keinen separaten, eigenen Draht zu Port 4030. Das ist keine offene Verifikationsfrage mehr (anders als in der Vorversion dieses Dokuments dargestellt) — indiserver fächert Property-Updates an beliebig viele gleichzeitig angeschlossene INDI-Clients (KStars, SMOS-App, beide gleichzeitig) auf, ohne dass `indi_pifinder_lx200` dafür mehr als seine eine bestehende TCP-Verbindung zu `pos_server.py` braucht. Für `pos_server.py` selbst ändert eine zusätzliche SMOS-App also **nichts** an der Zahl der Verbindungen auf Port 4030 |

**Kernpunkt, der dieses Konzept auslöst**: das sind keine sich gegenseitig ausschließenden
Betriebsmodi, sondern **potenziell gleichzeitig aktive Verbindungen** — genau das vom User
benannte Szenario: *"Wir haben das auch noch wo anders: Client SkySafari, Client KStars, Client
SMate App. Alle würden darauf zugreifen. Entscheidend ist ja, dass mehrere Clients darauf
zugreifen."*

## 2. Bereits bestehende Erweiterungen dieser Datei — Ausgangslage, nicht grüne Wiese

**Explizit geprüft, nachdem der User zurecht nachgefragt hat, ob das berücksichtigt wurde.**
`pos_server.py` ist bereits zweifach verändert, beide Ebenen müssen in jede Umsetzung einfließen:

1. **`diffs/pos_server_py.diff`** (PiFinder_Stellarmate, existiert bereits, wird von
   `bin/patch_PiFinder_installation_files.sh` bei jedem Setup/Reinstall angewendet) — Fix für
   Issue #107: `get_telescope_ra()`/`get_telescope_dec()` geben bei fehlender Lösung `None` statt
   der früheren `"+00*00'01"`-Fake-Koordinate zurück, UND `parse_sd_command()` verbraucht
   `sr_result` bereits **consume-once** (`ra_result, sr_result = sr_result, None`). **Korrektur
   gegenüber der Vorversion dieses Dokuments**: [[00108_upstream-bug-pos-server-sr-result-stale-global-2026-09-03]]s
   Kernaussage "`sr_result` wird nie zurückgesetzt" ist damit **bereits teilweise veraltet** — das
   Zurücksetzen NACH Gebrauch ist bereits gefixt. Was tatsächlich noch offen bleibt (und worauf sich
   dieses Konzept beschränkt): `sr_result` ist weiterhin ein **Modul-Global ohne Verbindungs-Scope**
   — bei zwei gleichzeitig verbundenen Clients teilen sie sich trotz Consume-once-Logik dieselbe
   Variable (s. Eventualität 3 in §3 unten). bm-Notiz 00108 muss entsprechend korrigiert werden
   (s. §11, Schritt 3).
2. **Der heutige `_call_with_timeout()`-Fix** (in dieser Session direkt im laufenden Checkout
   ergänzt, noch NICHT als Diff extrahiert) — begrenzt `shared_state.solution()`/`.datetime()` auf
   eine feste Wartezeit über einen zusätzlichen `ThreadPoolExecutor(max_workers=2)`. **Wird durch
   dieses Konzept ersetzt, nicht nur ergänzt** — s. §5.3, der User hat zurecht in Frage gestellt, ob
   dieser Mechanismus in seiner jetzigen Form (fester Pool, `max_workers`-Tuning) neben echtem
   Threading überhaupt noch sinnvoll ist.

**Konsequenz für die Umsetzung**: die künftige `diffs/pos_server_py.diff` muss alle DREI Schichten
gleichzeitig abbilden (#107-Fix + heutiger Timeout-Fix in seiner überarbeiteten Form + die
Threading-Änderung aus diesem Konzept) als EIN zusammenhängender Diff gegen die unveränderte
Upstream-Datei — nicht nur die neueste Schicht isoliert generieren (s. §11, Schritt 1).

## 3. Eventualitäten bei gleichzeitigem Zugriff — vollständig, nicht nur die drei genannten Apps

Das Requirement ist nicht "drei bestimmte Apps unterstützen", sondern **jede Form von
Nebenläufigkeit auf diesem Server muss sicher sein**. Systematisch durchgegangen, nicht nur die
augenfälligen Fälle:

| # | Eventualität | Tritt heute (Single-Client) wie auf? | Mit dem Fix in §5-§7 |
|---|---|---|---|
| 1 | 3 verschiedene Client-Typen gleichzeitig verbunden (SkySafari + Stellarium + KStars via `PiFinder LX200`) | nur der zuerst verbundene wird bedient, alle anderen bekommen keine Antwort (s. §4 live-Beleg) | alle drei parallel bedient, siehe §4.3 |
| 2 | **Derselbe** Client reconnected, ohne die alte Verbindung sauber zu schließen (App-Neustart, WLAN-Aussetzer) — die alte Verbindung hängt bis zu 60s im Socket-Timeout | die neue Verbindung wird bis zu 60s lang gar nicht bedient, obwohl es "nur" ein Client ist, keine drei | neue Verbindung bekommt sofort einen eigenen Thread — UND wird von der Entprellung in §5.2 als "derselbe Client, wahrscheinlich Reconnect" erkannt |
| 3 | Zwei Clients senden **gleichzeitig einen Goto** (`:Sr#`+`:Sd#`) | nicht möglich (nur einer ist überhaupt verbunden) — aber sobald mehrere verbunden sein können, ist das ohne Fix der exakte Mechanismus aus [[00108_upstream-bug-pos-server-sr-result-stale-global-2026-09-03]] (RA von Client A + Dec von Client B verschmelzen) — s. §2 zur Korrektur, was an 00108 bereits gefixt ist und was nicht | pro Verbindung isolierter `sr_result` (thread-local) — kann nicht mehr passieren |
| 4 | Ein Client ist Stellarium (ACK gesendet), ein anderer zeitgleich verbunden ist es nicht | nicht möglich (Single-Client) — mit einfachem `threading` ohne weitere Vorkehrung würde der zweite Client fälschlich `is_stellarium=True` sehen | thread-local `is_stellarium`, jede Verbindung sieht nur ihren eigenen Wert |
| 5 | Zwei Clients pushen gleichzeitig ein Ziel (`handle_goto_command`) — `sequence`-Zähler für die `object_id` | nicht möglich (Single-Client) | `threading.Lock()` um Inkrement+Read; `ra`/`dec`/`comp_ra`/`comp_dec` sind Stack-lokale Variablen je Aufruf, ohnehin nie geteilt — kein zusätzlicher Schutz nötig |
| 6 | **Viele kurzlebige Verbindungen/Reconnect-Sturm eines fehlerhaften Clients — vom User als kritisch eingestuft** | jede wartet einfach in der Kernel-Backlog-Queue, keine Ressourcen-Eskalation, aber auch keine bedient — ein naiver "Thread pro `accept()`"-Ansatz OHNE Entprellung würde das dagegen in unbegrenztes Thread-/Verbindungswachstum übersetzen | **Entprellung + Plausibilitätscheck vor dem Thread-Start**, s. §5.2 — kein Blindes "jede Verbindung sofort bedienen" |
| 7 | Ein Client sendet fehlerhafte/kaputte Daten, die einen Handler zum Werfen bringen, während andere Clients verbunden sind | nicht möglich (Single-Client) — aber naiv mit `threading` würde eine unbehandelte Exception nur den einen Thread beenden UND den Socket lecken, ohne die anderen zu stören (das wäre schon kein Regressions-Risiko) | zusätzlich per `try/except/finally` (§7) sauber geschlossen und geloggt, statt lautlos zu lecken |
| 8 | Prozess wird beendet (Service-Neustart), während mehrere Clients mitten in einer Anfrage stecken | nicht möglich (Single-Client, höchstens einer betroffen) | Daemon-Threads sterben mit dem Prozess — ein Client kann eine abgeschnittene/unvollständige Antwort sehen, exakt dasselbe Verhalten wie ein heutiger Verbindungsabbruch durch Service-Neustart (kein neues Risiko, nur jetzt potenziell mehrere Clients gleichzeitig statt einem) |

Zeilen 3-5 sind der eigentliche Kern des Requirements: **nicht nur "mehrere dürfen gleichzeitig
lesen"**, sondern **"mehrere dürfen gleichzeitig schreiben/interagieren, ohne sich gegenseitig zu
korrumpieren"**. Zeile 6 (vom User als kritisch markiert) ist der Grund, warum §5 unten NICHT nur
"Thread pro `accept()`" vorschlägt, sondern eine vorgeschaltete Entprellung/Plausibilitätsprüfung.

## 4. Problem — live gefunden, nicht hypothetisch

Heute (2026-09-05, PiFinder_Stellarmate Mount-Bridge-Livetest am echten OnStep-Mount) beim Versuch,
PiFinders aktuelle Position per einer eigenen, zweiten Testverbindung direkt abzufragen, während
`PiFinder LX200`s eigener INDI-Treiber bereits verbunden war:

```
TimeoutError: timed out
```

Ursache, per Code bestätigt (`setup_server_socket()`/`run_server()`):

```python
server_socket.listen(1)
...
while True:
    client_socket, address = server_socket.accept()
    logger.debug("New connection from %s", address)
    handle_client(client_socket, shared_state)   # <- blockiert INLINE im accept-Loop
```

`run_server()` ruft `handle_client()` **synchron im selben Loop** auf, der auch `accept()`
aufruft. Solange ein Client verbunden bleibt (bis zu 60s Timeout oder Disconnect), wird `accept()`
schlicht nicht erneut aufgerufen — jede weitere TCP-Verbindung landet zwar im Kernel-Backlog
(`listen(1)`, ein Slot), bekommt aber **keine Antwort auf irgendein gesendetes Kommando**, bis der
aktuelle Client die Verbindung beendet. Aus Client-Sicht: eine erfolgreiche TCP-Handshake, dann
Stille — exakt das oben beobachtete `TimeoutError`.

### Verhältnis zu bereits bekannten, verwandten Bugs/Fixes

| # | Bug/Fix | Verhältnis zu diesem Konzept |
|---|---|---|
| [[00108_upstream-bug-pos-server-sr-result-stale-global-2026-09-03]] | `sr_result` ist Modul-Global ohne Verbindungs-Scope — s. §2 für die Korrektur, was davon bereits gefixt ist | **Der verbleibende Teil (kein Scope) wird durch dieses Konzept gelöst.** Notiz muss vor dem Schließen korrigiert werden (s. §11, Schritt 3) |
| Issue [#118](https://github.com/apos/PiFinder_Stellarmate/issues/118) | `PiFinder LX200`-Treiber erkennt eine tote TCP-Verbindung zu `pos_server.py` nicht (`CONNECTION=On` lügt) | **Verwandt, aber orthogonal** — #118 ist ein Erkennungsproblem auf Client-Seite nach einem Server-Neustart; dieses Konzept ist ein Kapazitätsproblem auf Server-Seite bei mehreren *gleichzeitig* lebenden Verbindungen |
| Heutiger `_call_with_timeout()`-Fix | begrenzt die Wartezeit auf `shared_state.solution()`/`.datetime()` pro Request über einen separaten `ThreadPoolExecutor` | **Wird überarbeitet, s. §5.3** — löst das Kapazitätsproblem (ein Client blockiert alle) nicht, das macht erst das Threading selbst; der bewusst begrenzte Pool wird als eigenständiges Kapazitätsrisiko ersetzt |

## 5. Design-Entscheidung (ADR-Stil)

### 5.1 Kern: Thread pro Verbindung

**Kontext**: mehrere echte, unabhängige Clients (SkySafari, Stellarium, KStars via eigenem
LX200-Treiber) müssen PiFinders Position gleichzeitig lesen können, ohne sich gegenseitig zu
blockieren. Der Server ist aktuell strikt single-connection.

**Entscheidung**: `run_server()`s Accept-Loop startet pro akzeptierter Verbindung einen eigenen
`daemon=True`-Thread (`threading.Thread(target=handle_client, ...)`) statt `handle_client()` inline
aufzurufen — aber erst NACH der Prüfung in §5.2. `listen(1)` → `listen(5)` (Backlog-Puffer für
kurze Verbindungsspitzen).

**Konsequenzen — was das an geteiltem Zustand berührt**: jede bisher als Modul-Global gehaltene,
pro-Verbindung gedachte Variable wird zur echten Race Condition, sobald zwei Threads gleichzeitig
laufen. Lösung: `threading.local()` für alles, was laut Kommentar im Code ohnehin "stirbt mit der
Connection" gedacht war — dieselbe Reset-Semantik wie bisher, nur jetzt pro Thread statt pro
Prozess:

```python
_session = threading.local()

def _reset_session_state():
    """Per-connection state - thread-local, weil jede Verbindung jetzt ihren
    eigenen handle_client()-Thread bekommt (s. docs/concepts/
    pos_server_multi_client_architecture.md). Ersetzt die bisherigen
    Modul-Globals is_stellarium/stellarium_latitude/stellarium_longitude/
    sr_result 1:1 in ihrer Reset-Semantik - nur nicht mehr crossverbindungs-
    weit geteilt."""
    _session.is_stellarium = False
    _session.stellarium_latitude = ""
    _session.stellarium_longitude = ""
    _session.sr_result = None
```

### 5.2 Entprellung + Plausibilitätscheck vor dem Thread-Start (User: "das ist kritisch")

Reines "ein Thread pro `accept()`" wäre naiv — ein fehlerhafter Client in einer Reconnect-Schleife
(Eventualität 6, §3) würde unbegrenzt Threads/Sockets/Manager-Verbindungen erzeugen. Zwei
zusammenwirkende Schutzmechanismen, BEVOR ein neuer Thread gestartet wird:

1. **Debounce pro Remote-IP**: eine Map `{ip: letzte_annahme_zeit}`. Kommt von derselben IP
   innerhalb von `RECONNECT_DEBOUNCE_SEC` (Vorschlag: 2s — deutlich kürzer als das normale
   1-2s-Polling-Intervall eines legitimen Clients auf EINER bestehenden Verbindung, aber lang genug,
   um einen echten Reconnect-Sturm von einer zufälligen zweiten, echten Verbindung von derselben
   Adresse zu unterscheiden) eine weitere neue Verbindung, UND ist die vorherige Verbindung von
   dieser IP noch offen: das deutet auf denselben Client, der hastig neu verbindet, ohne die alte
   Verbindung geschlossen zu haben (Eventualität 2) — die **alte** Verbindung wird aktiv geschlossen
   (der Client hat sie erkennbar selbst aufgegeben), die neue normal bedient. Kein Ablehnen der
   neuen Verbindung — nur Aufräumen der wahrscheinlich verwaisten alten.
2. **Plausibilitäts-/Obergrenzen-Check**: zwei Zähler, je mit Log-Zeile (rate-limited, gleiches
   Muster wie die `BAD_COORD_WARN_INTERVAL_SEC`-Rate-Limits von heute Nacht):
   - **Pro-IP-Obergrenze** (Vorschlag: 3 gleichzeitig offene Verbindungen je Remote-IP) — mehr als
     das ist kein plausibles "3 verschiedene Apps", sondern mit hoher Wahrscheinlichkeit ein
     fehlerhafter/schleifender Client. Über der Grenze: neue Verbindung von dieser IP wird sofort
     wieder geschlossen (kein Thread gestartet), mit einer geloggten Warnung.
   - **Globale Obergrenze** (Vorschlag: 8 gleichzeitig offene Verbindungen insgesamt — großzügig
     über den heute bekannten ~3-4 realistischen Clients, s. §1) als zweiter, harter Deckel gegen
     jedes unvorhergesehene Szenario, unabhängig von der Quelladresse.

   Beide Grenzen sind bewusst konfigurierbare Konstanten, keine hartkodierten Magic Numbers ohne
   Namen — und bewusst **kein** ausgefeilter Rate-Limiter (Token-Bucket o. ä.): das wäre mehr
   Komplexität, als der tatsächliche Kontext (eine Handvoll bekannter Client-Typen) rechtfertigt
   (Prinzip [[00029_bm-standards-als-basis-iteration-als-korrektiv]]).

Dieser Check läuft **im Accept-Loop selbst**, vor dem `threading.Thread(...).start()` — er ersetzt
nicht die Thread-lokale Zustandstrennung aus §5.1, sondern verhindert, dass overhaupt zu viele
Threads/Manager-Verbindungen entstehen. Damit ist auch das in §10 diskutierte
"Manager-Verbindungen pro Thread"-Risiko strukturell begrenzt, nicht nur beobachtet.

### 5.3 `_call_with_timeout()` wird ersetzt — kein separater, größenlimitierter Pool mehr

**Berechtigte Frage vom User: brauchen wir den heutigen Timeout-Fix noch, und ist `max_workers`
2→8 nicht selbst ein Kapazitätsrisiko?** Beide Punkte treffen zu:

- Der heutige Fix existierte, um das **einzige** damalige Problem zu lindern: eine langsame
  `shared_state`-Antwort blockierte den EINZIGEN Server-Thread und damit ALLE Clients. Mit echtem
  Threading (§5.1) ist genau dieses Problem strukturell gelöst — ein langsamer Manager-Call
  blockiert jetzt nur noch den einen betroffenen Client-Thread, nicht mehr die anderen.
- Der bestehende `ThreadPoolExecutor(max_workers=N)`-Ansatz braucht trotzdem eine korrekt geschätzte
  Poolgröße — zu klein, und der Pool selbst wird bei mehreren gleichzeitig langsamen Calls zum
  neuen Nadelöhr (genau der Verdacht des Users bei "2 → 8"); zu groß, und es werden unnötig viele
  zusätzliche OS-Threads/Manager-Verbindungen vorgehalten, unabhängig davon, ob sie gebraucht werden.

**Neuer Ansatz — kein geteilter Pool, sondern ein Thread pro tatsächlich langsamem Call:**

```python
def _call_with_timeout(fn, timeout: float = STATE_CALL_TIMEOUT_SEC):
    """Ersetzt den ThreadPoolExecutor-Ansatz: kein geteilter, größenlimitierter
    Pool mehr (der selbst zum Nadelöhr werden könnte, s. docs/concepts/
    pos_server_multi_client_architecture.md §5.3) - jeder Aufruf bekommt bei
    Bedarf seinen eigenen, kurzlebigen Daemon-Thread. Die Gesamtzahl
    gleichzeitig laufender Aufrufe ist durch die Verbindungs-Obergrenzen aus
    §5.2 ohnehin bereits gedeckelt, eine zusätzliche Pool-Größe zum Tunen
    entfällt komplett."""
    result: dict = {}

    def _run():
        try:
            result["value"] = fn()
        except Exception:
            logger.exception("shared_state call raised")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning(
            "shared_state call timed out after %.1fs - reporting no data for this request.",
            timeout,
        )
        return None
    return result.get("value")
```

Kein `max_workers`-Tuning mehr nötig — die worst-case-Anzahl gleichzeitig offener, potenziell
langsamer Aufrufe ist durch §5.2s Verbindungs-Obergrenze (8 global) bereits begrenzt, ohne eine
zweite, unabhängige Grenze pflegen zu müssen.

## 6. Concurrency-Sicherheits-Referenz — jede geteilte Ressource einzeln geprüft

Rigoros geprüft statt pauschal behauptet (genau die Art Nachweis, die für den ersten
Timeout-Fix in dieser Session bereits eingefordert wurde):

| Ressource | Heute (Modul-Global) | Race bei mehreren Threads? | Fix |
|---|---|---|---|
| `is_stellarium` | ja, `global` | **Ja** — Client A (Stellarium) setzt es, Client B (SkySafari) liest plötzlich `True` und bekommt falsche `:D#`/`:Q#`-Antworten | → `_session.is_stellarium` (thread-local) |
| `stellarium_latitude`/`_longitude` | ja, `global` | **Ja** — ein Client sieht den vom anderen Client gesetzten Standort | → `_session.stellarium_latitude`/`_longitude` |
| `sr_result` | ja, `global` — Consume-once bereits gefixt (#107, s. §2), aber weiterhin ohne Verbindungs-Scope | **Ja** — Client A's `:Sr#` kann mit Client B's `:Sd#` zu einem Goto verschmelzen, den keiner der beiden je so gesendet hat | → `_session.sr_result`, per Verbindung isoliert |
| `sequence` (Goto-Zähler) | ja, `global`, `+= 1` ohne Lock | **Ja, aber selten relevant** (nur bei zwei zeitgleichen Goto-Pushes) — `+=` ist trotz GIL nicht atomar (LOAD/ADD/STORE als getrennte Bytecodes) | `threading.Lock()` um Inkrement+Read |
| `ui_queue` (`multiprocessing.Queue`) | geteilt | **Nein** — für genau diesen Zweck gebaut, intern threadsicher | keine Änderung nötig |
| `shared_state` (Manager-Proxy) | geteilt, ein Objekt für alle Aufrufer | **Nein** — `multiprocessing.managers.BaseProxy` hält pro aufrufendem Thread automatisch eine eigene Verbindung zum Manager-Prozess (`self._tls`, CPython-intern) | keine Änderung nötig, Anzahl der Verbindungen aber durch §5.2 gedeckelt |
| `_call_with_timeout()` (überarbeitet, §5.3) | kein geteilter Pool mehr | **Nein** — je ein eigener, kurzlebiger Daemon-Thread pro Aufruf | keine Poolgröße mehr zu pflegen |
| Verbindungs-/IP-Zähler aus §5.2 | neu, geteilt über alle Accept-Aufrufe | **Ja, wenn ungeschützt** — der Accept-Loop selbst ist aber weiterhin einsträngig (nur `run_server()`s Haupt-Thread ruft `accept()` auf und wertet die Zähler aus), Schreibzugriff aus den Client-Threads selbst nur beim Schließen (Dekrement) — braucht ein einfaches `threading.Lock()` um die beiden Zähler-Dicts | `threading.Lock()` um die Debounce-/Zähler-Struktur aus §5.2 |
| `client_socket` je Verbindung | lokal, ein Objekt pro `handle_client()`-Aufruf | **Nein**, bereits pro Verbindung isoliert | keine Änderung |
| `logger`/`logging` | geteilt | **Nein** — Python-`logging` ist intern threadsicher | keine Änderung — zusätzlich Thread-/Client-Kennung ins Log-Format aufnehmen (User: "ja"), s. §7 |

## 7. Fehler-Isolation + Log-Nachvollziehbarkeit

Bisher propagierte eine unerwartete Exception in `handle_client()` (etwas außerhalb der schon
behandelten `socket.timeout`/`ConnectionResetError`) bis zu `run_server()`s äußerem `try/except`
hoch — das riss den **gesamten** Server-Loop ab (Neustart nach 5s, aber währenddessen: alle
Clients getrennt). Mit Thread-pro-Verbindung würde eine unbehandelte Exception ansonsten nur den
Thread beenden, aber **den Socket nie schließen** (Leak) und den Traceback nur an Pythons
Default-Excepthook für Threads durchreichen, nicht an unseren Logger. Deshalb zusätzlich:

```python
def handle_client(client_socket, shared_state, address):
    threading.current_thread().name = f"pos_server-{address[0]}:{address[1]}"
    _reset_session_state()
    client_socket.settimeout(60)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        while True:
            ...  # wie bisher
    except Exception:
        logger.exception("Unexpected error handling client - closing this connection only.")
    finally:
        client_socket.close()
```

**Thread-Name mit Client-Adresse** (User: "ja") — jede Log-Zeile aus `logger`/`logging` trägt
standardmäßig keinen Thread-Namen, es sei denn das Format-String nutzt `%(threadName)s`. Zwei
Teile nötig: (1) den Thread-Namen wie oben beim Start jeder Verbindung setzen, (2) das
Log-Format (wo `logger`/`MultiprocLogging` konfiguriert wird) um `%(threadName)s` ergänzen, falls
noch nicht enthalten — damit im `pifinder.service`-Journal sofort erkennbar ist, welche Log-Zeile
zu welcher Verbindung/welchem Client gehört, statt raten zu müssen.

Ergebnis: ein fehlerhafter Client trennt nur sich selbst, alle anderen Verbindungen und der Server
insgesamt laufen unbeeinflusst weiter — vorher war "ein Client crasht" gleichbedeutend mit "alle
Clients werden für 5s getrennt".

## 8. API-/Protokoll-Referenz (unverändert durch dieses Konzept, zur Vollständigkeit)

| Kommando | Handler | Bedeutung |
|---|---|---|
| `:GR#` | `get_telescope_ra` | aktuelle RA lesen |
| `:GD#` | `get_telescope_dec` | aktuelle Dec lesen |
| `:D#` | `get_distance_bars` | Slew-Fortschritt (PiFinder slewt nie selbst) |
| `:Sr<RA>#` | `parse_sr_command` | RA für bevorstehenden Goto merken (jetzt: pro Verbindung) |
| `:Sd<Dec>#` | `parse_sd_command` | Dec setzen + Goto auslösen (verbraucht das gemerkte `:Sr#`) |
| `:Q#` | `abort_slew` | Slew abbrechen (No-Op, PiFinder slewt nie) |
| `:St#`/`:Sg#` | `set_latitude`/`set_longitude` | Standort vom Client übernehmen (nur zum Echo, jetzt: pro Verbindung) |
| `:Gt#`/`:Gg#` | `get_latitude`/`get_longitude` | Standort zurückgeben |
| `:GC#`/`:GL#`/`:GG#` | Datum/Zeit/UTC-Offset lesen | unverändert, liest `shared_state.local_datetime()` |
| ACK (`\x06`) | `handle_frame` | markiert die Verbindung als Stellarium (jetzt: pro Verbindung, nicht global) |

## 9. Testplan

Kein automatisierter Test existiert aktuell für `pos_server.py` (`python/tests/` hat keine
`test_pos_server*`-Datei). Konkrete, exakte Schritte statt vager Ziele (s.
[[00025_bm-testplaene-brauchen-exakte-schritte-nicht-vage-ziele]]):

### Manuell (sofort nach Umsetzung, ohne laufenden Live-Test zu stören)

1. `pifinder.service` neu starten (bereits akzeptierte Disruption, s. heutiger erster Fix).
2. Zwei parallele rohe Socket-Verbindungen aus zwei Terminals öffnen:
   ```bash
   python3 -c "
   import socket, time
   s = socket.create_connection(('127.0.0.1', 4030), timeout=5)
   for _ in range(5):
       s.sendall(b':GR#'); print('A RA:', s.recv(64)); time.sleep(1)
   "
   ```
   (zweites Terminal identisch, aber `print('B RA:', ...)`) — **Erwartung**: beide bekommen
   innerhalb von ~1s Antworten, keines wartet auf das Ende des anderen.
3. Cross-Contamination-Test: Terminal A sendet das Stellarium-ACK-Byte (`\x06`) und danach `:D#`
   (erwartet `""`, weil `is_stellarium` gesetzt ist); Terminal B (ohne ACK) sendet ebenfalls `:D#`
   zeitgleich (erwartet `\x7f`, weil B's `is_stellarium` **nicht** gesetzt sein darf). Bekommt B
   fälschlich `""`, ist die Thread-Local-Trennung kaputt.
4. Goto-Interleaving-Test (deckt den verbliebenen Teil von 00108 ab): Terminal A sendet nur
   `:Sr12:00:00#` (kein `:Sd#` danach), Terminal B sendet unabhängig `:Sd+45*00:00#`.
   **Erwartung**: B bekommt `"0"` (kein `sr_result` in seinem eigenen Session-State) — NICHT einen
   Goto zu RA 12h/Dec 45° aus A's Rest.
5. **Reconnect-Sturm-Test (Eventualität 6, §3 - vom User als kritisch markiert)**: ein Skript öffnet
   und schließt von derselben IP 10x hintereinander in schneller Folge (< 2s Abstand) eine
   Verbindung. **Erwartung**: laut Log wird ab der 4. gleichzeitig offenen Verbindung von dieser IP
   (Pro-IP-Obergrenze, §5.2) die weitere Annahme mit einer Warnung abgelehnt, kein
   Thread-/Verbindungs-Wachstum ohne Obergrenze.
6. Fehler-Isolations-Test: einer der beiden Clients sendet bewusst kaputte Daten (z. B. rohe
   Binärdaten statt eines Frames), die einen Handler zum Werfen bringen (falls reproduzierbar) —
   **Erwartung**: nur diese eine Verbindung bricht ab, `journalctl -u pifinder.service` zeigt den
   Traceback über `logger.exception(...)` samt Thread-Namen (Client-Adresse erkennbar, §7), der
   andere Client bleibt unbeeinträchtigt verbunden.

### Automatisiert (Vorschlag, nicht Teil dieses Konzepts' unmittelbarem Scope)

Ein `python/tests/test_pos_server.py` mit `pytest -m integration`, das `run_server()` mit einem
Fake-`shared_state` in einem Hintergrund-Thread startet und Schritte 2-5 oben als echte
Assertions nachbildet — sinnvoller Folgeauftrag, da dieses Modul aktuell komplett ungetestet ist.

## 10. Risiken / offene Fragen

- **Manager-Verbindungen pro Thread**: durch die Verbindungs-Obergrenzen aus §5.2 strukturell
  gedeckelt (max. 8 gleichzeitige Verbindungen insgesamt → max. 8 gleichzeitige
  Manager-Verbindungen) statt nur beobachtet — **kein offenes Risiko mehr**, sondern durch das
  Design in §5.2 aktiv adressiert.
- **StellarMate-App als LX200-Client**: **geklärt** (User-Korrektur, s. §1) — die SMOS-App ist ein
  generischer INDI-Client, nutzt denselben `PiFinder LX200`/`PiFinder Mount Bridge`-Pfad wie
  KStars, keine separate, unverifizierte Verbindung zu Port 4030. Keine offene Frage mehr.
- **Thread-Name mit Client-Adresse im Log**: **umgesetzt** (User: "ja") — s. §7, kein offener
  Punkt mehr, sondern Teil des Designs.
- **Root-Cause, warum `shared_state`-Aufrufe gelegentlich langsam sind — untersucht, wie vom User
  gefordert** (nicht länger als "außerhalb des Scopes" beiseitegelassen):
  - `SharedStateObj.solution()`/`.datetime()` selbst sind triviale Attribut-Getter ohne Lock, ohne
    teure Berechnung (`state.py:505-568`, geprüft) — die Langsamkeit liegt nicht in der Methode
    selbst.
  - Der Manager läuft laut `main.py:558`/`main.py:170-176` (`with StateManager() as manager:`,
    `StateManager(BaseManager)`) als **eigener, dedizierter Kindprozess** von `main.py` — nicht im
    selben Prozess wie die UI-Loop.
  - **Konkret gemessen, heute Nacht, live**: `nproc` liefert **4** (Pi4, 4 Kerne). Zeitgleich
    liefen **13** von `PiFinder.main` gestartete Prozesse (GPS, Keyboard, Webserver, Camera, Solver,
    IMU, Integrator, Position Server, der StateManager-Kindprozess selbst, plus
    Hilfs-/Resource-Tracker-Prozesse — per `ps aux` gezählt). Load Average während der heutigen
    Session lag mehrfach gemessen bei **3.49 bis 5.65** — also durchgehend über der
    4-Kern-Kapazität, nicht nur kurz beim Start.
  - **Schlussfolgerung, evidenzbasiert statt vermutet**: der StateManager-Kindprozess konkurriert mit
    12 weiteren aktiven Prozessen um 4 Kerne. Seine eigene Arbeit (eine Attribut-Rückgabe) ist
    trivial - die gelegentliche Verzögerung entsteht, wenn der Linux-Scheduler ihn unter dieser
    Überzeichnung seltener zum Zug kommen lässt, nicht durch einen Fehler in `SharedStateObj`
    selbst. Dasselbe Phänomen erklärt bereits dokumentiert die `indi_getprop`-Hänger unter Last
    (bm 00089/00102) — kein Einzelfall, sondern **ein wiederkehrendes Symptom einer einzigen
    zugrunde liegenden Ursache**: strukturelle CPU-Überzeichnung auf dem Pi4.
  - **Das ist NICHT durch dieses Konzept behoben** (dieses Konzept löst die Kapazitätsfrage
    "mehrere Clients gleichzeitig", nicht die CPU-Kontention selbst) — aber jetzt mit konkreter
    Ursache statt offener Frage. Als eigener, priorisierter Folgeschritt in §11 aufgenommen
    (Scheduling-Priorität für den StateManager-Prozess, z. B. `nice`/`chrt`, oder Reduktion der
    Solver-CPU-Last), nicht länger nur als Fußnote abgetan.
- **Log-Interleaving**: mit mehreren Threads können Log-Zeilen verschiedener Verbindungen
  zeitlich verschränkt erscheinen (kosmetisch, `logging` selbst ist zeilenweise atomar) — mit der
  Thread-Namen-Ergänzung aus §7 jetzt aber pro Zeile eindeutig einer Verbindung zuordenbar, damit
  kein echtes Problem mehr.

## 11. Strategische Umsetzung

Abhängigkeiten: 1 muss vor 2 stehen (Kern-Umsetzung zuerst, dann Tests dagegen); 3 hängt vom
Erfolg von 1+2 ab; 6 (CPU-Kontention) ist unabhängig und kann parallel laufen.

| # | Schritt | Aufwand | Priorität | Abhängigkeit |
|---|---|---|---|---|
| 1 | `run_server()`/`handle_client()`/geteilter State (§5.1) + Entprellung/Plausibilitätscheck (§5.2) + überarbeiteter `_call_with_timeout()` (§5.3) + Thread-Namen im Log (§7) umsetzen | M | P0 | keine |
| 2 | Manuelle Testschritte aus §9 durchführen, inkl. Reconnect-Sturm-Test | S | P0 | 1 |
| 3 | [[00108_upstream-bug-pos-server-sr-result-stale-global-2026-09-03]] korrigieren (Consume-once ist bereits gefixt, s. §2) und nach erfolgreicher Umsetzung schließen (s. [[00087_bm-bugfix-notiz-sofort-loeschen-bei-issue-abschluss]]) | XS | P1 | 1, 2 erfolgreich |
| 4 | `diffs/pos_server_py.diff` neu generieren — muss #107-Fix + überarbeiteten Timeout-Fix + Threading-Änderung als EINEN zusammenhängenden Diff abbilden (s. §2) | S | P0 | 1, 2 erfolgreich |
| 5 | `python/tests/test_pos_server.py` (automatisierter Integrationstest, §9) | M | P2 | 1 |
| 6 | **CPU-Kontention auf dem Pi4 untersuchen/mindern** (s. §10) — z. B. `nice`/`chrt` für den StateManager-Kindprozess, oder Profiling (`py-spy`/`austin`) während einer Live-Session, um zu bestätigen, welcher konkrete Prozess/Thread den StateManager tatsächlich verdrängt | M | P1 | keine (unabhängig) |
| 7 | StellarMate-App-Pfad (INDI-Client über `PiFinder LX200`) einmal live mit tatsächlich verbundener SMOS-App verifizieren, jetzt wo der Pfad geklärt ist (§1) | XS | P2 | keine (unabhängig) |

**Freigabe-Gate**: dieses Dokument ist reine Konzeption (s.
[[00020_bm-cpt-command-system]] Schritt 5) — Schritt 1 (die eigentliche Code-Änderung) läuft nach
Freigabe im normalen Feature-Branch-+-PR-Workflow gegen das PiFinder-Repo (`main`, s. dessen
eigenes `CLAUDE.md`), mit anschließender Diff-Extraktion nach PiFinder_Stellarmate (Schritt 4 oben)
wie beim `_call_with_timeout()`-Fix zuvor in dieser Session.

## 12. Bezug

- [[00108_upstream-bug-pos-server-sr-result-stale-global-2026-09-03]] — der Bug, den dieses
  Konzept strukturell mitlöst; muss vor dem Schließen korrigiert werden (s. §2, §11 Schritt 3).
- Issue [#118](https://github.com/apos/PiFinder_Stellarmate/issues/118) — verwandtes, aber
  orthogonales Problem (tote Verbindung wird nicht erkannt).
- `diffs/pos_server_py.diff` — bereits bestehender Patch (#107-Fix), muss bei der Umsetzung um die
  Threading-Änderung erweitert, nicht separat daneben gepflegt werden (s. §2, §11 Schritt 4).
- [[00020_bm-cpt-command-system]] / [[00021_bm-documentation-depth-standard]] — Format-Vorgabe
  für dieses Dokument.
- [[00025_bm-testplaene-brauchen-exakte-schritte-nicht-vage-ziele]] — Format-Vorgabe für §9.
- [[00029_bm-standards-als-basis-iteration-als-korrektiv]] — Begründung für die bewusst einfache
  (kein Token-Bucket) Entprellung in §5.2.
- `PiFinder/python/PiFinder/pos_server.py`, `PiFinder/python/PiFinder/state.py`,
  `PiFinder/python/PiFinder/main.py` (§10, Root-Cause-Recherche) — die untersuchten Dateien.
