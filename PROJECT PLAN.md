# Plant Care HA – Project Plan für Claude Code

> **Hinweis für Claude Code:** Dieses Dokument ist die Ground Truth für das Projekt. Lies es komplett bevor du Änderungen machst. Wenn du Architektur-Entscheidungen änderst, aktualisiere auch dieses Dokument.

-----

## 1. Projektüberblick

**Plant Care** ist eine Custom Integration für Home Assistant zur Verwaltung von Zimmerpflanzen. Sie besteht aus zwei Teilen:

- **Backend (Python):** Custom Integration die Pflanzen als HA-Entitäten verwaltet, Daten persistiert und Services bereitstellt
- **Frontend (JavaScript):** Eigenes Sidebar-Panel als Web Component, das die UI rendert

Die Installation erfolgt via **HACS** als Custom Repository. KI-Funktionen laufen über Home Assistants natives **AI Task System** – kein zusätzlicher API-Key in der App nötig.

### Kern-Designprinzipien

1. **HA-First:** Alles was geht über HA-eigene Mechanismen (Storage, Services, AI Task, Entitäten). Keine externe Cloud, keine separate Datenbank.
1. **Sensoren sind optional:** App funktioniert vollständig ohne Sensoren. Wenn vorhanden, wird die Bodenfeuchte als Übersteuerung des Zeit-Intervalls genutzt.
1. **Eine HACS-Installation:** Backend + Frontend liegen zusammen in einer Integration. Kein separates Card-Repository.
1. **Keine Build-Pipeline:** Frontend ist Vanilla JS Web Component – kein npm, kein Bundler, kein TypeScript-Compile-Schritt.

-----

## 2. Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                      Home Assistant                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Frontend Panel (plant-care-panel.js)                │    │
│  │  ─ Web Component <plant-care-panel>                  │    │
│  │  ─ Liest entities aus hass.states                    │    │
│  │  ─ Ruft Services über hass.callService()             │    │
│  │  ─ AI über ai_task.generate_data Service             │    │
│  └────────────────┬─────────────────────────────────────┘    │
│                   │ HA Service Calls                         │
│  ┌────────────────▼─────────────────────────────────────┐    │
│  │  Backend (custom_components/plant_care/)             │    │
│  │                                                       │    │
│  │  __init__.py        ← Setup, Services, Panel-Reg.    │    │
│  │  coordinator.py     ← Persistenz (HA Store)          │    │
│  │  sensor.py          ← Plant→Entity Mapping           │    │
│  │  config_flow.py     ← UI-Setup                       │    │
│  └────────────────┬─────────────────────────────────────┘    │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────────────┐    │
│  │  HA Core: Store (JSON in .storage/plant_care.plants) │    │
│  │           State Machine (sensor.plant_*)             │    │
│  │           AI Task Service (Anthropic/OpenAI/Ollama)  │    │
│  │           Notify Service                             │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### Datenfluss: Pflanze hinzufügen

```
1. User klickt "Neue Pflanze" im Panel
2. User gibt "Monstera deliciosa" ein → klickt "Vorschlag holen"
3. Panel ruft ai_task.generate_data mit Structure
4. KI antwortet: {species, common_name, water_days, fertilize_days, tips}
5. Panel füllt Form-Felder vor
6. User klickt "Speichern"
7. Panel ruft plant_care.add_plant Service
8. Backend (handle_add_plant):
   - Generiert UUID
   - Speichert in coordinator.plants (dict)
   - Persistiert via Store
   - Sendet SIGNAL_NEW_PLANT
9. sensor.py reagiert auf Signal → erstellt PlantSensor Entity
10. HA-State-Update → Panel rendert neue Karte
```

### Datenfluss: Sensor übersteuert Intervall

```
sensor.plant_monstera.state berechnet sich in PlantSensor.native_value:

1. Berechne needs_water aus letzem Gießdatum + Intervall (zeitbasiert)
2. Wenn moisture_sensor verknüpft:
   - Lese aktuellen Sensor-Wert
   - moisture < 20% → needs_water = True (egal was Intervall sagt)
   - moisture > 50% → needs_water = False (egal was Intervall sagt)
   - dazwischen: Zeitbasiert bleibt gültig
3. Berechne needs_fertilizer (rein zeitbasiert)
4. Kombiniere zu Status: ok | needs_water | needs_fertilizer | needs_both
```

-----

## 3. Dateistruktur

```
plant-care-ha/
├── hacs.json                              # HACS-Metadaten (Name, Min-HA-Version)
├── README.md                              # User-Doku (Installation, Bedienung)
├── info.md                                # HACS-Anzeige-Text
├── .gitignore
│
└── custom_components/plant_care/
    ├── manifest.json                      # Integration-Metadaten
    ├── __init__.py                        # Setup + Services + Panel-Registration
    ├── config_flow.py                     # UI für "Integration hinzufügen"
    ├── const.py                           # Alle Konstanten zentral
    ├── coordinator.py                     # PlantCareCoordinator: Datenhaltung
    ├── sensor.py                          # PlantSensor Entity-Klasse
    ├── services.yaml                      # Service-Beschreibungen für HA-UI
    ├── strings.json                       # Default-Texte (englisch)
    │
    ├── frontend/
    │   └── plant-care-panel.js            # ALLES UI: Web Component + Styles
    │
    └── translations/
        ├── de.json                        # Deutsche Übersetzungen
        └── en.json
```

### Datei-Verantwortlichkeiten

|Datei                |Was passiert dort                                          |Was NICHT                               |
|---------------------|-----------------------------------------------------------|----------------------------------------|
|`__init__.py`        |Setup, Service-Registration, Panel-Registration            |Keine Pflanzen-Logik (siehe coordinator)|
|`coordinator.py`     |Plants-Dict halten, Store-IO, CRUD                         |Keine HA-Entity-Logik                   |
|`sensor.py`          |PlantSensor Entity, Status-Berechnung, Sensor-Übersteuerung|Keine Persistenz                        |
|`config_flow.py`     |UI-Setup (minimal, eine Instanz)                           |Keine Optionen                          |
|`services.yaml`      |Beschreibung für HA Developer Tools                        |Keine Logik                             |
|`plant-care-panel.js`|Komplette UI, alle Views, Styles, Events, AI-Calls         |Keine Persistenz-Annahmen               |

-----

## 4. Stand: Was funktioniert (Phase 1 – DONE)

### Backend

- ✅ Config Flow (einmalige Einrichtung)
- ✅ Storage-Persistenz via `homeassistant.helpers.storage.Store`
- ✅ 5 Services: `add_plant`, `update_plant`, `remove_plant`, `water_plant`, `fertilize_plant`
- ✅ `add_plant` mit `SupportsResponse.OPTIONAL` → gibt `plant_id` zurück
- ✅ Sensor-Entities pro Pflanze mit dynamischer Status-Berechnung
- ✅ Sensor-Übersteuerung (<20% / >50%) für moisture_sensor
- ✅ Panel-Registration mit `module_url` (ESM)
- ✅ Statischer Pfad für Frontend-JS und Foto-Uploads
- ✅ Dispatcher-Signals für Updates (`SIGNAL_PLANTS_UPDATED`, `SIGNAL_NEW_PLANT`)
- ✅ Translations DE/EN

### Frontend

- ✅ Listenansicht (Grid) mit Pflanzenkarten
- ✅ Add-Formular mit Foto-Upload (Resize auf 600px, JPEG 0.82)
- ✅ Edit-Formular
- ✅ Detail-Ansicht mit Gieß-/Düngekarten + Live-Feuchtebar
- ✅ Empty-State mit SVG-Illustration
- ✅ KI-Vorschlag-Button via `ai_task.generate_data` (Structured Output)
- ✅ Toast-Notifications (success/error/info)
- ✅ Auto-Detection von AI-Task-Entitäten + Moisture-Sensoren
- ✅ Responsive (Mobile-Breakpoint 640px)
- ✅ HA-Theme-Variable-kompatibel (Light/Dark Mode)
- ✅ Botanisches Design (sage-grüner Akzent, organische Touches)

-----

## 5. Phase 2: Geplante Features (TODO)

Diese Features sind die nächsten Bauschritte. Priorität-Reihenfolge ist sinnvoll, aber nicht zwingend.

### 2.1 Foto-basierte Pflanzenerkennung (HOCH)

**Was:** User schießt Foto → KI erkennt die Art automatisch.

**Wo:** `plant-care-panel.js` im Add-Form. Aktuell ist `ai-input` ein Text-Feld. Es soll zusätzlich ein Button „📷 Per Foto erkennen” geben.

**Umsetzung:**

- `ai_task.generate_data` unterstützt `attachments`-Parameter mit Media-IDs
- Foto muss zuerst irgendwo abgelegt werden, wo HA es als Media findet
- Optionen:
  - (a) Backend HTTP-View die Base64-Bilder annimmt und in `media_source` ablegt
  - (b) Direkt als `media_content_id` mit data-URI? (Untestiert, vermutlich nicht supported)
  - (c) Über `image_processing` Component?

**Empfehlung:** Option (a). Backend-View `POST /api/plant_care/upload` die Base64 → Datei in `www/plant_care/<uuid>.jpg` schreibt und `local/plant_care/<uuid>.jpg` als URL zurückgibt. Diese URL kann dann als Attachment für AI Task verwendet werden.

**Service-Call dann etwa:**

```javascript
hass.callService("ai_task", "generate_data", {
  task_name: "plant_id_from_photo",
  instructions: "Welche Pflanze ist auf diesem Bild? Antworte mit JSON...",
  attachments: [{media_content_id: "media-source://local/plant_care/abc.jpg",
                 media_content_type: "image/jpeg"}],
  structure: {...}
}, undefined, true, true);
```

### 2.2 Verlaufsdiagramme (MITTEL)

**Was:** Anzeige “Wann wurde gegossen/gedüngt” über die letzten Wochen/Monate.

**Datenquelle:** Aktuell speichern wir nur `last_watered` und `last_fertilized` als Strings. Wir brauchen eine History.

**Optionen:**

- (a) HAs eingebaute Recorder/Statistics nutzen – `sensor.plant_*` State-Changes werden eh schon in `recorder` gespeichert
- (b) Eigene Liste in coordinator: `plant["water_history"] = ["2026-05-20T10:00:00Z", ...]`

**Empfehlung:** Beides. (a) für „Live”-Diagramme über HAs `history-graph` Card. (b) für UI-Verlauf in unserem Panel (max. 50 Einträge).

**Frontend:** Im Detail-View nach `detail-grid` eine neue Sektion „Verlauf” mit SVG-Linechart über die letzten 90 Tage.

### 2.3 Pflege-Erinnerungen (HOCH)

**Was:** Push-Benachrichtigung wenn Pflanze Wasser/Dünger braucht.

**Optionen:**

- (a) Pre-built Blueprint im Repo unter `blueprints/automation/plant_care/water_reminder.yaml` – User importiert nach Bedarf
- (b) Built-in Automatisierung via `automation.async_create` beim Setup (zu invasiv)
- (c) Notification-Service direkt aus Backend triggern (auch zu invasiv)

**Empfehlung:** (a). Blueprint erstellen, in README dokumentieren.

**Blueprint-Beispiel:**

```yaml
blueprint:
  name: Plant Care - Pflege-Erinnerung
  description: Benachrichtigung wenn eine Pflanze Wasser/Dünger braucht
  domain: automation
  input:
    plant_entity:
      name: Pflanze
      selector: {entity: {domain: sensor, integration: plant_care}}
    notify_service:
      name: Notify-Service
      selector: {text: {}}
    quiet_hours_start: ...
    quiet_hours_end: ...
trigger:
  - platform: state
    entity_id: !input plant_entity
    to: needs_water
  - platform: state
    entity_id: !input plant_entity
    to: needs_both
condition:
  - condition: time
    after: !input quiet_hours_end
    before: !input quiet_hours_start
action:
  - service: !input notify_service
    data:
      message: "🌿 {{ trigger.to_state.attributes.friendly_name }} braucht Wasser!"
```

### 2.4 Lovelace Custom Card (NIEDRIG)

**Was:** Mini-Karte für reguläre HA-Dashboards die eine oder mehrere Pflanzen kompakt anzeigt.

**Wo:** Neue Datei `custom_components/plant_care/frontend/plant-care-card.js`.

**Wichtig:** Eigene Custom Element, NICHT das gleiche wie das Panel. Custom Cards in HA müssen `setConfig(config)` implementieren und sich bei `customCards` registrieren.

**Boilerplate:**

```javascript
class PlantCareCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity ist erforderlich");
    this._config = config;
  }
  set hass(hass) { /* render */ }
  static getStubConfig() { return { entity: "sensor.plant_monstera" }; }
}
customElements.define("plant-care-card", PlantCareCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "plant-care-card",
  name: "Plant Care Card",
  description: "Zeigt eine Pflanze von Plant Care",
});
```

Card muss in `__init__.py` auch als Static Path registriert und in `manifest.json` aufgeführt werden.

### 2.5 Mehrere Pflanzen-Gruppen / Räume (NIEDRIG)

**Was:** Pflanzen gruppieren nach Raum, Gießplan etc. Aktuell ist `location` nur ein Freitext-Feld.

**Umsetzung:** Im Frontend Filter-Tabs oben in der Liste („Alle | Wohnzimmer | Schlafzimmer | …”). Auto-Generation aus den vorhandenen `location`-Werten.

### 2.6 Pflanzen-Bibliothek (NIEDRIG)

**Was:** Vorgefertigte Pflanzenprofile (Top 50 Zimmerpflanzen) mit empfohlenen Intervallen. Schnelle Auswahl ohne KI.

**Wo:** Statisches JSON `frontend/plant_library.json` mit `{species, common_name, water_days, fertilize_days, image_url, tips}` für ~50 häufige Arten.

-----

## 6. Phase 3: Ideen für später

- 📷 **Krankheitserkennung** per KI-Foto-Analyse (gelbe Blätter, Schädlinge etc.)
- 🌡️ **Mehr Sensor-Typen:** Licht, Temperatur, Nährstoffe (Mi Flora hat alles)
- 🤝 **Pflanzen-Tausch-Feature** – Empfehlungen wann Stecklinge möglich
- 📅 **Urlaubsmodus** – pausiert Benachrichtigungen, sendet Liste an Pflanzensitter
- 🎙️ **Voice-Integration** – „Hey Nabu, hab grad die Monstera gegossen” → Service-Call

-----

## 7. Technische Notizen / Gotchas

### HA-Version-Anforderungen

- **Minimum:** HA 2024.6.0 (wegen `StaticPathConfig` API)
- **AI Task:** Nur verfügbar ab HA 2025.7+ – Frontend prüft via `_findAiTaskEntity()` und zeigt graceful Fallback

### Service Response Pattern

`add_plant` nutzt `SupportsResponse.OPTIONAL`. Im Frontend wird der Service über `execute_script`-WS-Call mit `response_variable` abgerufen, weil das das robusteste Pattern für Service-Responses aus WebSocket-Clients ist.

**Alternative die getestet werden sollte:**

```javascript
const result = await hass.callService("plant_care", "add_plant", data,
                                       undefined, true, true);
// result.response sollte den Wert haben
```

Falls das funktioniert, kann `_callService` deutlich vereinfacht werden.

### Foto-Speicherung

Aktuell: Base64-Data-URLs direkt im Plant-Object. **Funktioniert** für ~50 Pflanzen mit je ~50KB resized JPEGs (= 2,5 MB im Storage).

**Skalierungs-Plan:** Wenn das zu groß wird, separates File-Storage. Stub im Backend gibt’s schon:

- `plant_care_photos/` Verzeichnis wird beim Setup angelegt
- Static Path `/api/plant_care/photos/` ist registriert
- Es fehlt nur die HTTP-View die Uploads annimmt

### Entity-IDs

Pflanze “Monstera” → `sensor.plant_monstera`. Wenn zwei Pflanzen denselben Namen haben, hängt HA `_2`, `_3` etc. an. Das ist OK aber für die User-Verständlichkeit nicht ideal.

**Mögliche Verbesserung:** Pflanzen-ID im Entity-ID verwenden: `sensor.plant_a3f7b2c1`. Macht die Entity-IDs unleserlicher aber kollisionsfrei. **Aktuelle Entscheidung:** Lassen wie es ist.

### AI Task – Strukturiertes Output

`ai_task.generate_data` mit `structure`-Parameter zwingt das LLM zu JSON-Output mit definiertem Schema. Funktioniert mit allen großen Providern (Anthropic, OpenAI, Gemini, Ollama mit unterstützten Modellen).

**Wichtig:** `selector` im Structure-Schema muss valides HA-Selector-Format sein:

```python
structure: {
  "water_days": {"selector": {"number": {"min": 1, "max": 90}}},
  "tips": {"selector": {"text": {}}},
}
```

-----

## 8. Test- & Debug-Workflow

### Lokales HA-Test-Setup

1. HA-Container/-VM mit Volume-Mount auf das Repo:

```bash
docker run -d --name homeassistant \
  -v $PWD/custom_components:/config/custom_components \
  -v $PWD/test-config:/config \
  --network=host ghcr.io/home-assistant/home-assistant:stable
```

1. Bei Änderungen:
- Python: HA-Restart nötig (`Entwicklerwerkzeuge → Steuerung → Server neu starten`)
- JS-Frontend: Browser-Hard-Reload (Cmd+Shift+R) reicht

### Logs prüfen

```yaml
# configuration.yaml für Debug-Output
logger:
  default: info
  logs:
    custom_components.plant_care: debug
```

In den Logs sollte beim Setup stehen:

```
INFO  Plant Care: 0 Pflanzen geladen
```

### Häufige Fehler

|Fehler                                          |Ursache                           |Fix                                                                                              |
|------------------------------------------------|----------------------------------|-------------------------------------------------------------------------------------------------|
|Panel taucht nicht in Sidebar auf               |`panel_custom` Config-Error       |HA-Log prüfen, in `__init__.py` der `async_register_built_in_panel` Call                         |
|`customElements.define` Fehler “already defined”|Hot-Reload des JS-Files           |Browser-Hard-Reload oder `delete customElements.get('plant-care-panel')`                         |
|AI-Vorschlag liefert nichts                     |`ai_task` Entity nicht gefunden   |In HA: Sprachassistenten → KI-Aufgabe → Standard setzen                                          |
|`sensor.plant_*` taucht nicht auf               |Sensor-Plattform nicht geforwarded|`await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)` in `__init__.py` checken|

-----

## 9. Code-Konventionen

### Python

- Type Hints überall (PEP 604 Union-Syntax: `str | None`)
- `from __future__ import annotations` in jeder Datei
- Docstrings auf Deutsch (User-Sprache)
- Logger-Modul-Name pattern: `_LOGGER = logging.getLogger(__name__)`
- Konstanten in `const.py`, nicht inline

### JavaScript

- Vanilla JS, KEIN React/Vue/Svelte
- Private Methoden mit `_` prefix
- Web Component muss isoliert funktionieren (Shadow DOM)
- HTML in Template-Literals; `_escape()` / `_escapeAttr()` für User-Input!
- CSS in `_styles()` method – nutzt HA-CSS-Variables wo möglich

### Sicherheit

- ⚠️ **HTML-Injection:** Alle User-Inputs durch `_escape()` für Text-Content oder `_escapeAttr()` für Attribute. Code-Review-Punkt bei jedem neuen Template.
- ✅ XSS-Schutz: Shadow DOM isoliert von HA-Frontend, aber `innerHTML` mit User-Daten ist trotzdem riskant – immer escapen.

-----

## 10. Release-Checklist

Vor einem neuen Release auf GitHub:

- [ ] Version in `manifest.json` hochzählen
- [ ] CHANGELOG.md aktualisieren (falls noch nicht vorhanden anlegen)
- [ ] README aktuell halten (neue Features dokumentieren)
- [ ] Lokal mit echter HA-Instanz getestet
- [ ] Lokal mit AI Task getestet (mindestens ein Provider)
- [ ] GitHub Release mit Tag (`v0.2.0`) erstellen – HACS nutzt Tags

-----

## 11. Was Claude Code beim ersten Lauf prüfen sollte

Wenn du frisch in dieses Projekt einsteigst:

1. **Repo-Struktur prüfen:** Stimmt sie mit Abschnitt 3 überein?
1. **Phase-1-Funktionen prüfen:** Lies `__init__.py`, `coordinator.py`, `sensor.py` und das JS. Mach dir ein Bild.
1. **Was ist das gewünschte nächste Feature?** Frag den User, oder schau in Abschnitt 5 nach Priorität.
1. **Setup-Test:** Falls möglich, das ZIP entpacken in eine Test-HA-Instanz laden und manuell durchklicken.

### Was du NICHT tun solltest

- Architektur ändern ohne mit dem User zu sprechen (z.B. React einführen, Build-Pipeline hinzufügen, externe Datenbank nutzen)
- Die Sensor-Optionalität aufgeben (sie ist ein Kern-Designprinzip)
- KI-Provider hart-coden (alles muss über HA AI Task laufen)
- Pflanzen-Daten in localStorage/IndexedDB speichern (Persistenz läuft über HA Store)

-----

## 12. Kontext für KI-gestützte Entwicklung

**User-Sprache:** Deutsch. Alle UI-Texte, Service-Beschreibungen und Docstrings sind auf Deutsch. Code-Kommentare können Englisch sein.

**User-Setup:**

- Arbeitet professionell, hat React-Erfahrung
- Bevorzugt konkrete Beispiele statt abstrakter Konzepte
- Mag es wenn Komplexität reduziert wird – kein Over-Engineering

**Phase 1 wurde gebaut in einer einzigen Session.** Die Codebasis ist klein genug, dass du sie komplett im Context halten kannst (~1500 Zeilen Python + JS).

-----

*Stand: Mai 2026 · Phase 1 abgeschlossen · Bereit für Phase 2*