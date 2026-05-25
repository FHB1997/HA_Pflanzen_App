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
├── PROJECT PLAN.md                        # Dieses Dokument (Ground Truth)
├── pytest.ini, requirements_test.txt
├── .gitignore
│
├── blueprints/automation/plant_care/
│   └── water_reminder.yaml                # Pro-Pflanze-Reminder-Blueprint
│
├── tests/                                 # Pytest-Suite für _utils.py
│   ├── conftest.py, test_utils.py, ...
│
└── custom_components/plant_care/
    ├── manifest.json                      # Integration-Metadaten (Version!)
    ├── __init__.py                        # Setup + alle Service-Handler + Panel-Reg
    ├── config_flow.py                     # ConfigFlow + OptionsFlow (mit Test-Toggle)
    ├── const.py                           # Alle Konstanten zentral
    ├── coordinator.py                     # PlantCareCoordinator: Daten + Reminders
    ├── sensor.py                          # PlantSensor Entity-Klasse
    ├── calendar.py                        # PlantCareCalendar Entity (Pflege-Termine)
    ├── http.py                            # PlantPhotoUploadView + Foto-Helfer
    ├── _utils.py                          # Pure Helpers (isolierte Unit-Tests)
    ├── services.yaml                      # Service-Beschreibungen für HA-UI
    ├── strings.json                       # Default-Texte (englisch)
    │
    ├── frontend/
    │   ├── plant-care-panel.js            # Sidebar-Panel (Web Component + Styles)
    │   └── plant-care-card.js             # Lovelace Custom Card
    │
    └── translations/
        ├── de.json                        # Deutsche Übersetzungen
        └── en.json
```

### Datei-Verantwortlichkeiten

|Datei                |Was passiert dort                                          |Was NICHT                               |
|---------------------|-----------------------------------------------------------|----------------------------------------|
|`__init__.py`        |Setup, Service-Registration, Panel-Registration mit `?v=` Cache-Buster |Keine Pflanzen-Logik (siehe coordinator)|
|`coordinator.py`     |Plants-Dict halten, Store-IO, CRUD, Reminder-Eval, Migrations |Keine HA-Entity-Logik                |
|`sensor.py`          |PlantSensor Entity, Status-Berechnung, Sensor-Übersteuerung|Keine Persistenz                        |
|`calendar.py`        |PlantCareCalendar-Entity mit kommenden Pflege-Events       |Keine Eventschreibung                   |
|`http.py`            |HTTP-View für Foto-Upload, Storage-Pfade                   |Keine Pflanzen-Logik                    |
|`_utils.py`          |Pure Helpers (ISO-Parse, Quiet-Hours, Notify-Target-Parser, …) – unit-getestet|Kein I/O, kein HA-State |
|`config_flow.py`     |UI-Setup + Options-Flow inkl. Test-Benachrichtigungs-Toggle|Keine Service-Logik                     |
|`services.yaml`      |Beschreibung für HA Developer Tools                        |Keine Logik                             |
|`plant-care-panel.js`|Komplette Panel-UI, alle Views, Styles, Events, AI-Calls   |Keine Persistenz-Annahmen               |
|`plant-care-card.js` |Eigenständige Lovelace-Card (nicht das Panel)              |Keine Edit-/Setup-Flows                 |

-----

## 4. Stand: Was funktioniert

### Backend

- ✅ Config Flow (einmalige Einrichtung) + Options-Flow mit Test-Benachrichtigung
- ✅ Storage-Persistenz via `homeassistant.helpers.storage.Store`
- ✅ One-Time-Migrationen: `location_tips` → `tips` → `plant_description` (alles in der konsolidierten Beschreibung)
- ✅ Services: `add_plant`, `update_plant`, `remove_plant`, `water_plant`, `fertilize_plant`, `send_reminders`, `send_test_notification`, `add_plant_photo`, `remove_plant_photo`, `diagnose_plant` (KI **oder** manuell), `resolve_treatment`, `get_events`
- ✅ Sensor-Entities pro Pflanze mit dynamischer Status-Berechnung
- ✅ Sensor-Übersteuerung (<20% / >50%) für moisture_sensor
- ✅ Calendar-Platform: `calendar.plant_care` mit anstehenden Pflege-Terminen
- ✅ Panel-Registration mit `module_url` (ESM) + `?v=<manifest.version>` Cache-Buster
- ✅ Statische Pfade für Frontend-JS und Foto-Uploads
- ✅ Dispatcher-Signals für Updates (`SIGNAL_PLANTS_UPDATED`, `SIGNAL_NEW_PLANT`, `SIGNAL_REMOVE_PLANT`)
- ✅ Translations DE/EN inkl. Options-Errors
- ✅ Anti-Spam-Throttle für Diagnose-Anfragen (60s)
- ✅ Multi-Notify-Targets (komma-separiert, parallel) + Actionable Notifications
- ✅ Foto-Verlauf mit FIFO-Cap (100 / Pflanze)

### Frontend

- ✅ Listenansicht in zwei Modi: Grid (Kacheln) und Compact (Row-List mit kleinem Round-Photo); Auswahl via localStorage persistent
- ✅ Quick-Actions (💧/🌱) auf jeder Karte in beiden Modi
- ✅ Detail-Ansicht mit kompaktem Header (Raum / Licht / Position inline), aufgehübschten Gradient-Quick-Actions, einer einzigen "Über diese Pflanze"-Sektion (4-6 Sätze konsolidiert), Treatments-Block, Foto-Verlauf, Verlaufsdiagrammen
- ✅ Add-/Edit-Formular mit Foto-Upload (Resize auf 600px, JPEG 0.82)
- ✅ KI-Vorschlag via `ai_task.generate_data` (Structured Output) – konsolidierte Beschreibung in `plant_description` (Herkunft + Pflege + Standort)
- ✅ Foto-Erkennung mit Konfidenz-Anzeige
- ✅ Behandlungs-Modal mit Mode-Picker (📷 Foto-Diagnose / ✏️ Manuell)
- ✅ Bulk-Modus für Mehrfach-Selektion (Gegossen / Gedüngt)
- ✅ Räume-Filter mit Auto-Generation aus den vorhandenen Räumen
- ✅ Kalender-View / Agenda mit Heute/Morgen-Hervorhebung
- ✅ Empty-State mit SVG-Illustration
- ✅ Toast-Notifications (success/error/info)
- ✅ Auto-Detection von AI-Task-Entitäten + Moisture-Sensoren
- ✅ Responsive (Mobile-Breakpoint 640px)
- ✅ HA-Theme-Variable-kompatibel (Light/Dark Mode)
- ✅ Botanisches Design (sage-grüner Akzent, organische Touches)
- ✅ Mobile-Tastatur-Fix: `_render()` überspringt re-renders, solange ein Input fokussiert ist (sonst Keyboard-Dismiss bei jedem HA-State-Update)

### Lovelace

- ✅ Plant Care Custom Card (`plant-care-card.js`) für reguläre Dashboards
- ✅ Pflege-Erinnerungs-Blueprint (`blueprints/automation/plant_care/water_reminder.yaml`)

-----

## 5. Phase 2: Done

Alle Phase-2-Features sind ausgeliefert. Kurzer Abriss + jeweilige
aktuelle Stelle im Code:

| Feature | Status | Wo |
|---|---|---|
| Foto-basierte Pflanzenerkennung | ✅ | `_aiIdentifyFromPhoto` in `plant-care-panel.js`, Upload-View in `http.py` |
| Verlaufsdiagramme (SVG-Linechart, 90 Tage) | ✅ | `_renderHistorySection` in `plant-care-panel.js`, `water_history`/`fertilize_history` im Coordinator |
| Pflege-Erinnerungen | ✅ | Integriert (Options-Flow + Scan-Tick in `coordinator.evaluate_reminders`) **und** Blueprint (`blueprints/automation/plant_care/water_reminder.yaml`) |
| Lovelace Custom Card | ✅ | `frontend/plant-care-card.js` |
| Räume-Filter | ✅ | `ROOM_TYPES` in `const.py`, Filter-Pills in der Listenansicht |
| Behandlungen / Krankheitserkennung | ✅ | Diagnose-Modal mit Foto-KI **und** manuellem Text-Pfad |
| Mehrere Notify-Targets parallel | ✅ | `parse_notify_targets` in `_utils.py`, Multi-Send in `coordinator.evaluate_reminders` |
| Test-Benachrichtigung | ✅ | `coordinator.send_test_notification` + Options-Flow-Toggle |
| Foto-Verlauf pro Pflanze | ✅ | `MAX_PHOTOS_PER_PLANT` (100, FIFO) im Coordinator, Lightbox im Panel |
| Kalender-Platform | ✅ | `calendar.py` mit `calendar.plant_care`-Entity + In-Panel-Agenda |

### Bewusst nicht gebaut: Statische Pflanzen-Bibliothek

Ursprünglich war eine `plant_library.json` mit ~50 vorgefertigten Profilen
geplant. **Entfernt in Version 0.2.0:** Der KI-Vorschlag liefert für
beliebige Arten bessere Daten (Wiki-Beschreibung, Standort-Kontext,
Foto-Erkennung) – die statische Liste war redundant.

-----

## 6. Phase 3: Ideen für später

- ✅ **Outdoor-Pflanzen mit Season + Weather Awareness** (Version 0.3.0) –
  Indoor/Outdoor-Tabs, Saison-Multiplikatoren für Outdoor-Intervalle,
  Wetter-Entity-Hook (Regen-Suppression), Frost-Warnung mit Banner und
  Push. Per-Pflanze-Toggles: `frost_sensitive`, `winter_rest`. Hook
  Points: `effective_*_days` in `_utils.py`, `is_winter_rest_active`,
  `has_recent_rain`, `has_frost_in_forecast`; `evaluate_frost_warnings`
  im Coordinator.
- 🌡️ **Mehr Sensor-Typen:** Licht, Temperatur, Nährstoffe (Mi Flora hat alles) – aktuell nur Bodenfeuchte
- 🤝 **Pflanzen-Tausch-Feature** – Empfehlungen wann Stecklinge möglich
- 📅 **Urlaubsmodus** – pausiert Benachrichtigungen, sendet Liste an Pflanzensitter
- 🎙️ **Voice-Integration** – „Hey Nabu, hab grad die Monstera gegossen" → Service-Call
- 🌍 **Frontend-Lokalisierung** – Panel ist derzeit nur Deutsch
- 📊 **Statistik-Dashboard** – Wasser-/Düngerverbrauch über Monate, Anzeichen von Stress

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

**Implementiert als File-Storage** (nicht mehr Data-URLs):

- Uploads gehen via `PlantPhotoUploadView` (`POST /api/plant_care/upload`) in `<config>/plant_care_photos/<plant_id>/<uuid>.jpg`
- Static-Path `/api/plant_care/photos/` serviert das Verzeichnis
- Plant-Object speichert nur den relativen Pfad, nicht die Bilddaten
- Alte Data-URL-Storage-Einträge werden beim Coordinator-Load via `_migrate_data_url_photos` automatisch in Dateien überführt
- Foto-Verlauf: bis zu 100 Fotos pro Pflanze, FIFO. Löschen einer Pflanze räumt alle ihre Bilder vom Disk weg

### Cache-Buster fürs Panel-JS

Browser cachen `plant-care-panel.js` aggressiv. Beim Panel-Register hängt
`__init__.py` daher `?v=<integration.version>` an `module_url`. Jeder
Bump in `manifest.json` invalidiert automatisch den Cache. **Daher:
bei jeder UI-relevanten Änderung manifest.json mitbumpen.**

### Render-Skipping bei fokussiertem Input

`set hass(hass)` triggert auf jedes HA-State-Update einen Render. Solange
ein `<input>`/`<textarea>`/`<select>` im Shadow-Root den Fokus hat, bricht
`_render()` ohne `force=true` ab – sonst zerstört `innerHTML = …` den
Input und Mobile-Browser blenden die On-Screen-Tastatur aus. Explizite
Renders (Submit, View-Wechsel, AI-Suggest) laufen trotzdem.

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

- [ ] Version in `manifest.json` hochzählen (auch bei reinen Frontend-Änderungen → triggert den `?v=`-Cache-Buster)
- [ ] CHANGELOG.md aktualisieren (falls noch nicht vorhanden anlegen)
- [ ] README + info.md + PROJECT PLAN aktuell halten (neue Features dokumentieren)
- [ ] `python -m pytest tests/ -q` grün
- [ ] `node --check custom_components/plant_care/frontend/plant-care-panel.js` grün
- [ ] Lokal mit echter HA-Instanz getestet (mind. Add/Edit/Detail-Flow)
- [ ] Lokal mit AI Task getestet (mindestens ein Provider) – sowohl Name-Vorschlag als auch Foto-Erkennung
- [ ] Test-Benachrichtigung via Options-Flow ausgelöst
- [ ] GitHub Release mit Tag (`v0.2.x`) erstellen – HACS nutzt Tags

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

**Phase 1 wurde gebaut in einer einzigen Session.** Inzwischen ist auch
Phase 2 komplett ausgeliefert (siehe Abschnitt 5). Die Codebasis ist
gewachsen (Panel-JS ~2.7k Zeilen, Coordinator ~750 Zeilen) – für gezielte
Arbeit weiterhin gut im Context haltbar, für Quer-Lesungen lieber mit
`grep` / `Read`-Ranges arbeiten.

-----

*Stand: Mai 2026 · Phase 1 + Phase 2 + Outdoor-Awareness ausgeliefert (Version 0.3.0) · Sammelbecken Phase 3 in Abschnitt 6*