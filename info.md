# Plant Care

Verwalte deine Zimmerpflanzen direkt in Home Assistant – mit eigener Sidebar, KI-gestützten Pflegevorschlägen und optionaler Sensor-Anbindung.

## Highlights

- **Eigenes Sidebar-Panel** mit Listen-, Detail- und Bearbeitungsansicht
- **Zwei Listen-Modi**: Kacheln oder kompakte Liste (umschaltbar, persistent)
- **Quick-Actions** (💧 / 🌱) direkt auf jeder Pflanzen-Karte
- **KI-Vorschläge** über HAs natives AI Task System – kein eigener API-Key nötig (Standort + Licht fließen in den Prompt ein)
- **Foto-Erkennung** der Pflanzenart per Bild (ab HA 2025.7)
- **Konsolidierte Pflanzen-Beschreibung** (4-6 Sätze: Herkunft + Pflege + Standort in einem Text)
- **Behandlungs-Feature**: KI-Foto-Diagnose *oder* manuelle Textbeschreibung
- **KI-Chat im Detail-View**: Fragen im Kontext der Pflanze, Multi-Turn via HA Conversation
- **Indoor / Outdoor** als getrennte Tabs, mit Saison-bewussten Reminder-Intervallen, Regen-Awareness und Frost-Warnung für frostempfindliche Outdoor-Pflanzen
- **Sensor-Übersteuerung**: Bodenfeuchte-Sensor übersteuert die Zeit-Heuristik (<20% / >50%)
- **Sensoren optional** – funktioniert auch komplett ohne Hardware
- **Foto-Verlauf** pro Pflanze (max. 100, FIFO)
- **Kalender / Agenda** kommender Pflege-Termine + HA-Calendar-Entity
- **Pflege-Erinnerungen** integriert oder via Blueprint, inkl. Test-Benachrichtigung
- **Komplett lokal** – keine externe Cloud, keine externe Datenbank

## Voraussetzungen

- Home Assistant 2024.6.0 oder neuer
- Für KI-Funktionen: HA 2025.7+ mit eingerichtetem AI Task (Anthropic, OpenAI, Gemini oder Ollama)
- Optional: Bodenfeuchte-Sensor (z.B. Mi Flora, Xiaomi)
