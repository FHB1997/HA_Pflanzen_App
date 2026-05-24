# Plant Care – Home Assistant Custom Integration

Verwalte deine Zimmerpflanzen direkt in Home Assistant. Plant Care besteht aus einem Python-Backend, das Pflanzen als HA-Entitäten verwaltet, und einem eigenen Sidebar-Panel als Web Component.

## Features

- Sidebar-Panel mit Listen-, Detail- und Bearbeitungsansicht
- KI-Vorschläge für Pflegeintervalle und Pflanzenarten über HAs natives AI Task System
- Foto-basierte Pflanzenerkennung (ab HA 2025.7)
- Optionale Verknüpfung mit Bodenfeuchte-Sensoren (übersteuert das Zeit-Intervall)
- Pflanzen-Bibliothek mit ~50 häufigen Zimmerpflanzen
- Verlaufsdiagramme für Gieß- und Düngevorgänge
- Räume-Filter
- Pflege-Erinnerungen via Blueprint
- Lovelace Custom Card für reguläre Dashboards

## Installation via HACS

1. HACS → Integrations → Drei-Punkte-Menü → **Custom repositories**
2. Repository-URL eintragen, Kategorie **Integration**
3. "Plant Care" suchen → **Download**
4. Home Assistant **neu starten**
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → "Plant Care"

## Voraussetzungen

- Home Assistant **2024.6.0** oder neuer
- Für KI-Funktionen: HA **2025.7+** mit konfiguriertem AI Task (Anthropic, OpenAI, Gemini oder Ollama)
- Optional: Bodenfeuchte-Sensor mit `device_class: moisture` oder `unit_of_measurement: %`

## Bedienung

Nach der Installation erscheint **Plant Care** in der Sidebar.

### Pflanze hinzufügen

1. Panel öffnen → **Neue Pflanze**
2. Name eingeben (z.B. "Monstera") → **KI-Vorschlag holen** → Form wird automatisch befüllt
3. Optional: Foto hochladen, Moisture-Sensor verknüpfen, Tipps anpassen
4. **Speichern**

### Pflanze per Foto erkennen (ab HA 2025.7)

Im Add-Form auf **📷 Per Foto erkennen** klicken → Foto aufnehmen oder hochladen → die KI identifiziert die Art und schlägt Pflegeintervalle vor.

### Sensor-Verknüpfung

Im Add/Edit-Formular einen Sensor auswählen. Die Logik:
- Moisture < 20 % → Pflanze braucht Wasser (egal was das Zeit-Intervall sagt)
- Moisture > 50 % → Pflanze braucht **kein** Wasser
- Dazwischen → das Zeit-Intervall entscheidet

## Erinnerungen einrichten

Plant Care liefert einen Blueprint mit. Importieren:

1. Im Home Assistant: **Einstellungen → Automatisierungen & Szenen → Blueprints → Blueprint importieren**
2. URL: `https://github.com/<user>/HA_Pflanzen_App/blob/main/blueprints/automation/plant_care/water_reminder.yaml`
3. Pflanze, Notify-Service und Ruhezeiten auswählen → **Automatisierung erstellen**

Du bekommst dann eine Push-Benachrichtigung, sobald die Pflanze Wasser/Dünger braucht.

## Lovelace Custom Card

Eine kompakte Karte für reguläre Dashboards.

1. **Einstellungen → Dashboards → Ressourcen → Hinzufügen**
2. URL: `/plant_care_frontend/plant-care-card.js`, Typ: **JavaScript-Modul**
3. Im Dashboard eine Karte hinzufügen → "Plant Care Card" → Pflanze auswählen

## Services

| Service | Beschreibung | Response |
|---|---|---|
| `plant_care.add_plant` | Pflanze hinzufügen | `{plant_id}` |
| `plant_care.update_plant` | Pflanze ändern | – |
| `plant_care.remove_plant` | Pflanze löschen | – |
| `plant_care.water_plant` | "Jetzt gegossen" markieren | – |
| `plant_care.fertilize_plant` | "Jetzt gedüngt" markieren | – |

## Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| Panel fehlt in Sidebar | Setup-Fehler | HA-Log prüfen, ggf. Integration neu hinzufügen |
| AI-Vorschlag liefert nichts | AI Task nicht konfiguriert | Einstellungen → Sprachassistenten → KI-Aufgabe → Standard setzen |
| `customElements.define` Fehler im Browser | Hot-Reload | Hard-Reload (Cmd+Shift+R / Strg+F5) |
| Pflanze taucht nach Speichern nicht auf | Sensor-Plattform nicht geladen | HA neu starten |

### Debug-Logs aktivieren

```yaml
logger:
  default: info
  logs:
    custom_components.plant_care: debug
```

## Lizenz

MIT
