# FAQ

[English](FAQ.md) · [README](../README_de.md)

## Läuft PFSM weiter, wenn das Handy-Display gesperrt ist?

**Ja.** Alles, was steuert, läuft auf dem Pi: die Mount Bridge (ein INDI-Treiber) und der Dienst des Control Centers, samt der
Pause bei Guiding und Alignment und der Selbstreparatur. Die Webseite zeigt nur an und gibt deine Klicks weiter.

- Bei gesperrtem Display friert der Browser die Seite ein. Nach dem Entsperren aktualisiert sie sich und holt sich das
  Bedienrecht zurück (das Control Center gibt es immer nur einem Browser und gibt es nach 15 Sekunden Funkstille frei).
- Die regelmäßigen Abfragen der Seite senden keine Befehle.
- **Eine Ausnahme:** Das *One-Click Setup* (auch von einem Kopplungs-Knopf ausgelöst, solange die Einrichtung nicht fertig ist)
  läuft Schritt für Schritt **im Browser**. Wird das Display währenddessen gesperrt, bleibt es stehen oder bricht ab: Display
  eingeschaltet lassen, bis es fertig ist.

KStars/Ekos und die Montierung hängen nicht am Handy.
