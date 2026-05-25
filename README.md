# Plant Care – Home Assistant Custom Integration

Verwalte deine Zimmerpflanzen direkt in Home Assistant. Plant Care besteht aus einem Python-Backend, das Pflanzen als HA-Entitäten verwaltet, und einem eigenen Sidebar-Panel als Web Component.

## Features

- Sidebar-Panel mit Listen-, Detail- und Bearbeitungsansicht
- KI-Vorschläge für Pflegeintervalle und Pflanzenarten über HAs natives AI Task System (Standort + Licht fließen in den Prompt ein)
- Foto-basierte Pflanzenerkennung (ab HA 2025.7)
- Konsolidierte „Über diese Pflanze"-Beschreibung (4-6 Sätze: Herkunft + Pflege + Standort-Hinweise als ein Text)
- Behandlungs-Feature („Was ist los?") mit KI-Foto-Diagnose **oder** manueller Textbeschreibung
- KI-Chat in der Detail-Ansicht: stell Fragen im Kontext der Pflanze, Multi-Turn via HA Conversation-Agent
- Indoor- und Outdoor-Pflanzen getrennt: zwei Tabs in der Übersicht, eigene Räume (Balkon, Garten, Terrasse, …), saison-bewusste Reminder-Intervalle und Wetter-Awareness (kein Gießen wenn's geregnet hat)
- Frost-Warnung (Banner + Push-Notification) für frost­empfindliche Outdoor-Pflanzen
- Optionale Verknüpfung mit Bodenfeuchte-Sensoren (übersteuert das Zeit-Intervall)
- Verlaufsdiagramme für Gieß- und Düngevorgänge
- Foto-Verlauf pro Pflanze (max. 100, FIFO)
- Räume-Filter + Bulk-Aktionen für mehrere Pflanzen
- Zwei Listen-Ansichten: Kacheln (Standard) oder Kompakte Liste (umschaltbar via ☰/▦ in der Topbar, Auswahl wird in localStorage gespeichert)
- Quick-Action-Buttons (💧 / 🌱) direkt auf jeder Pflanzen-Karte
- Pflege-Erinnerungen integriert *oder* via Blueprint, inkl. Test-Benachrichtigung
- Lovelace Custom Card für reguläre Dashboards
- Cache-Buster für das Panel-JS via Manifest-Version

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

1. Panel öffnen → **+ Neue Pflanze**
2. Name eingeben (z.B. "Monstera") → **✨ KI-Vorschlag** → Form wird automatisch befüllt
3. Optional: Foto hochladen (oder per **📷 Per Foto erkennen** identifizieren lassen), Moisture-Sensor verknüpfen, Tipps anpassen
4. **Speichern**

### Standort-Q&A

Beim Anlegen kannst du optional **Raum** (Dropdown) und
**Lichtintensität** angeben. Beide Werte fließen in den KI-Vorschlag
ein → die KI passt Gieß- und Düngeintervalle daran an und liefert im
Feld **Über diese Pflanze** einen zusammenhängenden 4-6-Satz-Text mit
Herkunft/Familie, den wichtigsten Pflegehinweisen *und* dem, was beim
genannten Raum + Licht zu beachten ist. Wenn der gewählte Standort
für die Pflanze ungeeignet ist (z.B. Sukkulente im dunklen Bad),
zeigt der Detail-View oben ein oranges Warnbanner.

Beide Felder sind optional – Q&A leer lassen funktioniert wie vorher.
Bei späterem Umzug: Felder im Edit-Form ändern, dann KI-Vorschlag
erneut tippen für aktualisierte Intervalle und Beschreibung.

### Listenansicht umschalten

In der Topbar oben rechts gibt es ein ☰/▦-Toggle: Standard ist die
**Kachel-Ansicht** mit großen Karten. Ein Klick wechselt in die
**Kompakte Liste** – kleine runde Vorschau, Name, Status und
Quick-Actions auf einer Zeile. Die Auswahl wird per localStorage
gemerkt, also bleibt zwischen Sessions erhalten.

### Pflanze per Foto erkennen (ab HA 2025.7)

Im Add-Form auf **📷 Per Foto erkennen** klicken → Foto aufnehmen oder hochladen → die KI identifiziert die Art und schlägt Pflegeintervalle vor.

### Quick-Actions auf der Karte

Jede Pflanzen-Karte in der Übersicht hat rechts unten zwei runde
Icon-Buttons: **💧** markiert sofort als gegossen, **🌱** als gedüngt.
Ein Toast bestätigt; die Detail-Ansicht muss dafür nicht geöffnet
werden. Im Bulk-Modus sind die Buttons ausgeblendet.

### Mehrere Pflanzen gleichzeitig erledigen

Auf der List-View **☑ Auswahl** tappen → jede Card wird per Klick
selektiert/deselektiert. In der Bottom-Bar **💧 Gegossen** oder
**🌱 Gedüngt** auslösen. Bei mehr als 5 Pflanzen kommt ein
Bestätigungs-Dialog. Die "Alle"-Checkbox in der Bar bezieht sich auf
die aktuell sichtbaren Pflanzen (Raum-Filter wird respektiert).

### Kalender / Agenda

Im Panel oben rechts auf **📅 Kalender** tappen → chronologische Liste
aller anstehenden Pflege-Termine der nächsten 14 Tage, gruppiert nach
Tag. **HEUTE/MORGEN** sind hervorgehoben, überfällige Termine bekommen
einen orangenen Akzent. Für heute fällige und überfällige Pflanzen gibt
es einen direkten **✓**-Button zum Quittieren. "Mehr anzeigen" erweitert
den Zeitraum um jeweils 14 Tage.

Parallel registriert die Integration eine Calendar-Entity
`calendar.plant_care` — du kannst sie mit HA's Built-in Calendar-Card auf
jedem Dashboard zeigen.

### Foto-Verlauf

Im Detail-View einer Pflanze findest du den **📸 Foto-Verlauf** mit
allen jemals hinzugefügten Bildern. "+ Foto hinzufügen" lädt ein neues
Bild hoch und sortiert es nach Aufnahmedatum ein. Tap auf ein Thumbnail
öffnet die Lightbox; dort kannst du blättern oder das Bild löschen.

Cap pro Pflanze: 100 Fotos. Bei Überschreitung wird das älteste Foto
automatisch entfernt (Datei wird mitgelöscht). Beim Löschen einer
Pflanze werden alle ihre Fotos vom Disk entfernt.

### Pflanzen-Sprechstunde

Sieht eine Pflanze auffällig aus (gelbe Blätter, Schädlinge)? Im Detail-View
**+ Was ist los?** tappen → es öffnet sich ein Modal mit zwei Wegen:

- **📷 Foto-Diagnose** – KI analysiert ein hochgeladenes Bild und schlägt
  konkrete Behandlungsschritte vor (HA 2025.7+ mit AI Task).
- **✏️ Selbst beschreiben** – manuelles Formular für Diagnose, Schritte,
  Wiedervorlage und Schweregrad. Kein AI Task nötig.

Beide Wege legen eine **Behandlung** mit Wiedervorlage-Datum an. Sobald
diese fällig ist, schaltet der Plant-Sensor auf Status `needs_attention`
und Plant Care versendet eine Reminder-Notification mit den Buttons
**✓ Erledigt** / **✗ Verwerfen** / **💤 Snooze 1d**.

Anti-Spam-Throttle: mindestens 60s zwischen Diagnose-Einträgen pro Pflanze.

### KI-Chat zur Pflanze

Im Detail-View gibt's eine **💬 Frag die KI**-Sektion. Du tippst eine
Frage („Warum fallen die Blätter ab?", „Reicht das Licht am
Ostfenster?", „Wann umtopfen?") und HA's Conversation-Agent
antwortet. Der erste Prompt bekommt automatisch einen Plant-Context-
Vorspann (Name, Spezies, Raum, Licht, Position, Pflege-Intervalle,
Wiki-Beschreibung). Folgenachrichten laufen über `conversation_id`,
sodass die KI den Verlauf kennt.

Voraussetzung: HA hat einen Conversation-Agent konfiguriert
(Einstellungen → Sprachassistenten → Standard). Ohne LLM-Agent
antwortet HA mit dem internen Regex-Agent, der für freie Fragen
naturgemäß keine sinnvollen Antworten gibt. Empfohlen: derselbe
Provider wie für AI Task (Anthropic, OpenAI, Gemini, Ollama).

„Verlauf löschen" startet eine neue Konversation. Der Verlauf ist
nur im Browser gespeichert – beim Neuladen des Panels verfällt er.

### Indoor vs. Outdoor

Die Übersicht hat oben zwei Tabs: **🪴 Indoor** und **🌳 Outdoor**. Beim
Anlegen einer Pflanze wird per Radio festgelegt, was es ist — die Raum-
Liste passt sich an (Indoor: Wohnzimmer/Bad/…, Outdoor: Balkon/Garten/
Terrasse/Vorgarten/Gewächshaus). Outdoor-Pflanzen bekommen zwei
zusätzliche Toggles:

- **❄️ Frostempfindlich** — löst Warnung + Push aus, wenn Frost in den
  nächsten 24 h vorhergesagt ist
- **😴 Winterruhe (Dez–Feb)** — pausiert Reminder komplett in den
  Wintermonaten

Die Saison-Logik passt für Outdoor-Pflanzen die Gieß- und Düngeintervalle
automatisch an (Sommer öfter, Winter seltener; Düngen im Winter pausiert).
Wenn in den Integration-Optionen eine **Wetter-Entity** hinterlegt ist,
suppressed Plant Care die „Gießen"-Reminder solange für heute
Niederschlag > 1 mm gemeldet ist. Indoor-Pflanzen sind davon nicht
betroffen.

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
3. **Notify-Service(s)** eintragen. Mehrere Geräte/Kanäle gleichzeitig
   per Komma trennen (z.B.
   `notify.mobile_app_iphone, notify.mobile_app_ipad, notify.telegram_bot`).
   Jede Notification wird an alle Targets parallel verschickt; Mobile-App-
   Targets bekommen automatisch die Action-Buttons.
4. Optional: Titel, Ruhezeiten, Mindestabstand zwischen Erinnerungen
5. **Test-Benachrichtigung beim Speichern senden** anhaken, falls du
   die eingetragenen Targets direkt verifizieren willst – ein statischer
   Test-Push geht raus, bevor gespeichert wird. Die Option resettet sich
   nach dem Save automatisch.
6. Speichern

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
| `plant_care.send_test_notification` | Test-Push an alle konfigurierten Notify-Targets | `{targets, errors}` |
| `plant_care.add_plant_photo` | Foto in den Foto-Verlauf einfügen | `{photo_id}` |
| `plant_care.remove_plant_photo` | Foto aus dem Verlauf löschen | – |
| `plant_care.diagnose_plant` | Behandlung anlegen (KI-Foto **oder** manuell – `photo_path` optional) | `{treatment_id}` |
| `plant_care.resolve_treatment` | Offene Behandlung quittieren / verwerfen | – |
| `plant_care.get_events` | Kommende Pflege-Termine als Liste | `{events}` |

## Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| Panel fehlt in Sidebar | Setup-Fehler | HA-Log prüfen, ggf. Integration neu hinzufügen |
| AI-Vorschlag liefert nichts | AI Task nicht konfiguriert | Einstellungen → Sprachassistenten → KI-Aufgabe → Standard setzen |
| UI-Änderungen kommen nach Update nicht an | Panel-JS aus Browser-Cache | Hard-Reload (Cmd+Shift+R / Strg+F5). Cache-Buster zieht beim nächsten manifest.json-Bump automatisch. |
| `customElements.define` Fehler im Browser | Hot-Reload | Hard-Reload (Cmd+Shift+R / Strg+F5) |
| Pflanze taucht nach Speichern nicht auf | Sensor-Plattform nicht geladen | HA neu starten |
| Test-Benachrichtigung schlägt fehl | Notify-Service-Name falsch oder leer | Notify-Service genau wie in HA-Diensten heißt (ohne `notify.`-Prefix raten – komplett angeben) |
| Tastatur klappt auf Handy zu beim Tippen | (Behoben in 0.2.3) | HACS-Update + HA-Neustart |

### Debug-Logs aktivieren

```yaml
logger:
  default: info
  logs:
    custom_components.plant_care: debug
```

## Lizenz

MIT
