# Design-Entscheidungen — PiFinder LX200 INDI-Integration

*[English version](Readme_design_decisions.md)*

Eine kompakte Zusammenfassung der wichtigsten Design-Entscheidungen hinter der [PiFinder LX200
INDI-Integration](Readme_PiFinder_LX200_de.md) (dem Treiber `PiFinder LX200` und der optionalen
`PiFinder Mount Bridge`). Die vollständige Begründung, Code-Referenzen und Diagramme stehen in
diesem Dokument.

## Architektur

- **Standalone-Build statt Fat-Binary/`indi-source`-Checkout**: Die Treiber linken direkt gegen
  System-`libindi` — 13,5 MB → 80 KB, Build in Sekunden statt komplettem INDI-Vollbuild, kein
  Konflikt mit `pacman`.
- **Zwei getrennte Treiber statt einem**: `PiFinder LX200` (immer gleiche Rolle, egal ob eine Mount
  vorhanden ist) und `PiFinder Mount Bridge` (der einzige Baustein, der überhaupt von einer zweiten,
  echten Mount weiß) — unabhängig baubar und aktivierbar, kein Einfluss aufeinander.

## PiFinder LX200 Treiber

- **Bewusst minimale Capability** (`GOTO` + `ABORT`, kein `SYNC`, kein Park/Flip/Tracking-Rate):
  PiFinder hat keinen Motor und kein internes Positionsmodell, das man synchronisieren könnte —
  jedes Sync-Konzept gehört zur Mount, nicht zu PiFinder.
- **GoTo bedeutet Push-to-Weiterleitung**: `Goto()` schreibt nur `:Sr#`/`:Sd#` an PiFinders eigenen
  Server; PiFinders eigene gemeldete Position ändert sich dabei nie — die kommt unabhängig aus dem
  Live-Solve.

## Mount Bridge

- **Nur generische INDI-Properties an die Mount** (`EQUATORIAL_EOD_COORD`/`ON_COORD_SET`), nie ein
  mount-spezifisches Protokoll — macht die Bridge automatisch kompatibel mit jeder INDI-Mount,
  nicht nur mit OnStepX.
- **Embedded INDI-Client** (`INDI::BaseClient`, nach Vorbild `indi_skysafari`) statt eines
  Snoop-Mechanismus im eigenen Treiberprozess — sauber getrennter Zustand.
- **Ein Kopplungsgrad-Dial statt einzelner Schalter** (Off / Verify-Alert / Auto-Correct /
  Goto-Forward): deckt das ganze Spektrum von reinem Push-to bis vollautomatischem GoTo mit einer
  einzigen Property ab.
- **Goto-Forward nutzt die von `INDI::Telescope` bereits bereitgestellte `TARGET_EOD_COORD`** statt
  einer eigenen Property — vermeidet Duplikation (erst nach einer Namenskollision entdeckt).
- **Nach einem Goto-Forward-Slew: Verifikation per Sync, nicht per erneutem Goto** — die Mount ist
  bereits angekommen, ein Restfehler ist ein Kalibrierungsproblem, kein verpasster Slew (sonst
  "Hunting").
- **Settle-Delay (3 Poll-Zyklen) vor der Verifikation** — PiFinder braucht nach der physischen
  Bewegung Zeit für einen frischen Solve.

## Testen & Betrieb

- **Gestufte Teststrategie**: Fake-LX200-Server → `indi_simulator_telescope` → echte EQ5/OnStepX —
  Risiko schrittweise erhöht, nie ungetestet auf echter Hardware.
- **Dokumentation zweisprachig, Englisch als Primärsprache** (die Projektseite ist Englisch),
  Deutsch als Zweitversion mit Sprach-Switcher.
