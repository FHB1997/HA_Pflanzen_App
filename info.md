# Plant Care

Verwalte deine Zimmerpflanzen direkt in Home Assistant – mit eigener Sidebar, KI-gestützten Pflegevorschlägen und optionaler Sensor-Anbindung.

## Highlights

- **Eigenes Sidebar-Panel** mit Listen-, Detail- und Bearbeitungsansicht
- **KI-Vorschläge** über HAs natives AI Task System – kein eigener API-Key nötig
- **Foto-Erkennung** der Pflanzenart per Bild (ab HA 2025.7)
- **Sensor-Übersteuerung**: Bodenfeuchte-Sensor übersteuert die Zeit-Heuristik (<20% / >50%)
- **Sensoren optional** – funktioniert auch komplett ohne Hardware
- **Pflege-Erinnerungen** via mitgeliefertem Blueprint
- **Komplett lokal** – keine externe Cloud, keine externe Datenbank

## Voraussetzungen

- Home Assistant 2024.6.0 oder neuer
- Für KI-Funktionen: HA 2025.7+ mit eingerichtetem AI Task (Anthropic, OpenAI, Gemini oder Ollama)
- Optional: Bodenfeuchte-Sensor (z.B. Mi Flora, Xiaomi)
