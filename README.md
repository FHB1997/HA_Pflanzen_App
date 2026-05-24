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

## Sprache / Language

Das Sidebar-Panel ist derzeit nur auf Deutsch verfügbar. Config-Flow und
Services nutzen HA-Translations (`de` / `en`); das Panel-UI selbst ist
noch nicht lokalisiert.

> *The sidebar panel UI is currently German-only. The integration's
> config flow and service descriptions are translated (`de` / `en`).*

## Bedienung

Nach der Installation erscheint **Plant Care** in der Sidebar.

### Pflanze hinzufügen

1. Panel öffnen → **Neue Pflanze**
2. Name eingeben (z.B. "Monstera") → **KI-Vorschlag holen** → Form wird automatisch befüllt
3. Optional: Foto hochladen, Moisture-Sensor verknüpfen, Tipps anpassen
4. **Speichern**

### Standort-Q&A

Beim Anlegen kannst du optional **Raum** (Dropdown) und
**Lichtintensität** angeben. Beide Werte fließen in den KI-Vorschlag
ein → die KI passt Gieß- und Düngeintervalle daran an und gibt
zusätzlich Standort-spezifische Tipps zurück. Wenn der gewählte
Standort für die Pflanze ungeeignet ist (z.B. Sukkulente im dunklen
Bad), zeigt der Detail-View oben ein oranges Warnbanner, das du per
✕-Tap ausblenden kannst.

Beide Felder sind optional – Q&A leer lassen funktioniert wie vorher.
Bei späterem Umzug: Felder im Edit-Form ändern, dann KI-Vorschlag
erneut tippen für aktualisierte Intervalle.

### Pflanze per Foto erkennen (ab HA 2025.7)

Im Add-Form auf **📷 Per Foto erkennen** klicken → Foto aufnehmen oder hochladen → die KI identifiziert die Art und schlägt Pflegeintervalle vor.

### Mehrere Pflanzen gleichzeitig erledigen

Auf der List-View **☑ Auswahl** tappen → jede Card wird per Klick
selektiert/deselektiert. In der Bottom-Bar **💧 Gegossen** oder
**🌱 Gedüngt** auslösen. Bei mehr als 5 Pflanzen kommt ein
Bestätigungs-Dialog. Die "Alle"-Checkbox in der Bar bezieht sich auf
die aktuell sichtbaren Pflanzen (Raum-Filter wird respektiert).

### Foto-Verlauf

Im Detail-View einer Pflanze findest du den **📸 Foto-Verlauf** mit
allen jemals hinzugefügten Bildern. "+ Foto hinzufügen" lädt ein neues
Bild hoch und sortiert es nach Aufnahmedatum ein. Tap auf ein Thumbnail
öffnet die Lightbox; dort kannst du blättern oder das Bild löschen.

Cap pro Pflanze: 100 Fotos. Bei Überschreitung wird das älteste Foto
automatisch entfernt (Datei wird mitgelöscht). Beim Löschen einer
Pflanze werden alle ihre Fotos vom Disk entfernt.

### Sensor-Verknüpfung

Im Add/Edit-Formular einen Sensor auswählen. Die Logik:
- Moisture < 20 % → Pflanze braucht Wasser (egal was das Zeit-Intervall sagt)
- Moisture > 50 % → Pflanze braucht **kein** Wasser
- Dazwischen → das Zeit-Intervall entscheidet

## Erinnerungen einrichten

Es gibt zwei Wege – such dir einen aus.

### Variante A (empfohlen): Integrierte Erinnerungen über Options

Eine zentrale Konfiguration, gilt für **alle** Pflanzen, ohne Automation pro Pflanze:

1. **Einstellungen → Geräte & Dienste → Plant Care → ⚙ Konfigurieren**
2. **Erinnerungen aktivieren** anhaken
3. **Notify-Service** eintragen (z.B. `notify.mobile_app_iphone`,
   `notify.notify`, `notify.telegram_bot_123`)
4. Optional: Titel, Ruhezeiten, Mindestabstand zwischen Erinnerungen
5. Speichern

Plant Care prüft jede Pflanze alle 30 Minuten. Bei Status `needs_water` /
`needs_fertilizer` / `needs_both` außerhalb der Ruhezeit und außerhalb des
Rate-Limit-Fensters wird eine Benachrichtigung versendet.

### Actionable Notifications (HA-Mobile-App)

Wenn dein `notify_service` ein HA-Mobile-App-Target ist (Pattern
`notify.mobile_app_*`), bekommt jede Reminder-Notification Action-Buttons
direkt im Notification-Center:

- **💧 Gegossen** → markiert die Pflanze als gegossen, ohne in HA zu wechseln
- **🌱 Gedüngt** → analog für Dünger (nur wenn fällig)
- **💤 Snooze 1d** → verzögert die nächste Notification um mindestens 24 h.
  Der Pflanzen-Status im Panel bleibt unverändert (rot); nur die
  Notification wird unterdrückt.

Andere Notify-Services (Telegram, Persistent Notification, …) bekommen
die Notification ohne Buttons – Plant Care fällt automatisch auf
Plain-Notify zurück.

Manuelle Auslösung jederzeit über den Service **`plant_care.send_reminders`**:

```yaml
service: plant_care.send_reminders
data:
  # Optional: nur diese Pflanze
  plant_id: abc123
  # Optional: Ruhezeit und Rate-Limit ignorieren
  force: true
```

### Variante B: Pro-Pflanze-Automation via Blueprint

Wenn du pro Pflanze einen anderen Notify-Kanal willst (z.B. Wohnzimmer →
Telegram, Schlafzimmer → Push):

1. **Einstellungen → Automatisierungen & Szenen → Blueprints → Blueprint importieren**
2. URL: `https://github.com/FHB1997/HA_Pflanzen_App/blob/main/blueprints/automation/plant_care/water_reminder.yaml`
3. Pflanze, Notify-Service und Ruhezeiten auswählen → **Automatisierung erstellen**
4. Pro Pflanze wiederholen

Beide Varianten dürfen parallel laufen – das Rate-Limit der integrierten
Erinnerungen verhindert nur Mehrfach-Notifications aus der **integrierten**
Variante; der Blueprint hat seine eigene Debounce-Logik.

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
| `plant_care.send_reminders` | Erinnerungen jetzt senden (manuell) | `{sent}` |

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
