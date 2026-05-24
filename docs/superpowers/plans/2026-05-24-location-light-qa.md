# Standort-Q&A im Add-Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add/Edit-Form fragt strukturiert nach Raum + Lichtintensität; die Werte fließen in den KI-Prompt ein und die KI liefert zusätzlich Standort-Tipps + ggf. Eignungs-Warnung.

**Architecture:** Vier neue String-Felder im Plant-Dict (idempotent migriert). Frontend erweitert das Form um Dropdown + Radio-Group, baut den AI-Prompt situativ um, rendert eine neue Detail-View-Sektion + ein dismissbares Warning-Banner. Keine Backend-Pure-Helper.

**Tech Stack:** Home Assistant Custom Integration, Vanilla-JS-Web-Component.

**Spec:** [docs/superpowers/specs/2026-05-24-location-light-qa-design.md](../specs/2026-05-24-location-light-qa-design.md)

---

### Task 1: Konstanten + Coordinator-Migration

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/coordinator.py`

- [ ] **Step 1.1: Konstanten in const.py**

Am Ende von `custom_components/plant_care/const.py`:

```python
# Standort/Licht (Sprint 6)
LIGHT_LEVELS: Final = ("vollsonne", "hell", "halbschatten", "schatten")
ROOM_TYPES: Final = (
    "wohnzimmer",
    "schlafzimmer",
    "kueche",
    "bad",
    "buero",
    "flur",
    "kinderzimmer",
)
```

- [ ] **Step 1.2: Migration in `async_load`**

In `coordinator.py`, in der Schleife in `async_load`, **nach** der bestehenden Migration-Zeile für `last_notified` ergänzen:

```python
            plant.setdefault("light_level", "")
            plant.setdefault("room_type", "")
            plant.setdefault("location_tips", "")
            plant.setdefault("suitability_warning", "")
```

- [ ] **Step 1.3: Felder im `async_add_plant` initialisieren**

In `async_add_plant`, im `plant: dict[str, Any] = {...}`-Literal nach `"tips": ...,`:

```python
            "light_level": cleaned.get("light_level", ""),
            "room_type": cleaned.get("room_type", ""),
            "location_tips": cleaned.get("location_tips", ""),
            "suitability_warning": cleaned.get("suitability_warning", ""),
```

- [ ] **Step 1.4: Sanity-Check + Commit**

Run: `python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3`
Expected: alle Tests grün (Migration ist additiv).

```bash
git add custom_components/plant_care/const.py custom_components/plant_care/coordinator.py
git commit -m "Plant-Schema: light_level + room_type + location_tips + suitability_warning

Vier neue String-Felder, alle Optional/Default leer. Migration in
async_load via setdefault. Konstanten LIGHT_LEVELS und ROOM_TYPES
in const.py.
"
```

---

### Task 2: Service-Schemas + services.yaml + i18n

**Files:**
- Modify: `custom_components/plant_care/__init__.py`
- Modify: `custom_components/plant_care/services.yaml`
- Modify: `custom_components/plant_care/strings.json`
- Modify: `custom_components/plant_care/translations/de.json`
- Modify: `custom_components/plant_care/translations/en.json`

- [ ] **Step 2.1: Imports + Schema in `__init__.py`**

Import-Block ergänzen:

```python
from .const import (
    ...
    LIGHT_LEVELS,
    ...
)
```

`ADD_PLANT_SCHEMA` erweitern (vor dem schließenden `)`):

```python
        vol.Optional("light_level", default=""): vol.In(["", *LIGHT_LEVELS]),
        vol.Optional("room_type", default=""): cv.string,
        vol.Optional("location_tips", default=""): cv.string,
        vol.Optional("suitability_warning", default=""): cv.string,
```

`UPDATE_PLANT_SCHEMA` analog (ohne `default`, weil Optional-Updates):

```python
        vol.Optional("light_level"): vol.In(["", *LIGHT_LEVELS]),
        vol.Optional("room_type"): cv.string,
        vol.Optional("location_tips"): cv.string,
        vol.Optional("suitability_warning"): cv.string,
```

- [ ] **Step 2.2: services.yaml**

In `services.yaml`, im `add_plant`-Block (nach dem `tips`-Feld) ergänzen:

```yaml
    light_level:
      name: Lichtintensität
      description: vollsonne / hell / halbschatten / schatten
      selector:
        select:
          options:
            - vollsonne
            - hell
            - halbschatten
            - schatten
    room_type:
      name: Raum
      description: Strukturierter Raum-Typ (Wohnzimmer, Schlafzimmer, …).
      selector:
        text:
    location_tips:
      name: Standort-Tipps
      description: Optional, wird normalerweise von der KI gefüllt.
      selector:
        text:
          multiline: true
    suitability_warning:
      name: Eignungs-Warnung
      description: Optional, wird normalerweise von der KI gefüllt.
      selector:
        text:
          multiline: true
```

Im `update_plant`-Block dieselben Einträge wiederholen.

- [ ] **Step 2.3: strings.json**

In `strings.json`, im `services.add_plant.fields`-Block:

```json
"light_level": { "name": "Light level", "description": "vollsonne | hell | halbschatten | schatten" },
"room_type": { "name": "Room type", "description": "Structured room category" },
"location_tips": { "name": "Location tips", "description": "Usually filled by AI" },
"suitability_warning": { "name": "Suitability warning", "description": "Usually filled by AI" }
```

Analog im `update_plant.fields`-Block.

- [ ] **Step 2.4: Übersetzungen**

In `translations/en.json` dieselben Strings (englisch), in
`translations/de.json` deutsche Varianten:

```json
"light_level": { "name": "Lichtintensität", "description": "vollsonne / hell / halbschatten / schatten" },
"room_type": { "name": "Raum", "description": "Strukturierter Raum-Typ" },
"location_tips": { "name": "Standort-Tipps", "description": "Wird i.d.R. von der KI gefüllt" },
"suitability_warning": { "name": "Eignungs-Warnung", "description": "Wird i.d.R. von der KI gefüllt" }
```

- [ ] **Step 2.5: JSON-Check + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('OK')"
```

```bash
git add custom_components/plant_care/__init__.py custom_components/plant_care/services.yaml custom_components/plant_care/strings.json custom_components/plant_care/translations/
git commit -m "Services: light_level, room_type, location_tips, suitability_warning

Erweitert add_plant + update_plant Service-Schemas und services.yaml
um die 4 neuen Felder. i18n in DE + EN.
"
```

---

### Task 3: Sensor-Attribute

**Files:**
- Modify: `custom_components/plant_care/sensor.py`

- [ ] **Step 3.1: 4 neue Attribute**

In `PlantSensor.extra_state_attributes`, im return-Dict (nach `"tips"`):

```python
            "light_level": plant.get("light_level", ""),
            "room_type": plant.get("room_type", ""),
            "location_tips": plant.get("location_tips", ""),
            "suitability_warning": plant.get("suitability_warning", ""),
```

- [ ] **Step 3.2: Compile + Commit**

```bash
python3 -m py_compile custom_components/plant_care/sensor.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/sensor.py
git commit -m "Sensor: light_level + room_type + location_tips + suitability_warning Attribute"
```

---

### Task 4: Frontend – Q&A-Felder im Form

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 4.1: Label-Maps**

Oben in der Datei, nach den existierenden `STATUS_LABEL`/`STATUS_CLASS`-Constants:

```javascript
const ROOM_LABELS = {
  wohnzimmer: "Wohnzimmer",
  schlafzimmer: "Schlafzimmer",
  kueche: "Küche",
  bad: "Bad",
  buero: "Büro",
  flur: "Flur",
  kinderzimmer: "Kinderzimmer",
};

const LIGHT_LABELS = {
  vollsonne: "Vollsonne (Südfenster)",
  hell: "Hell (am Fenster, nicht direkt)",
  halbschatten: "Halbschatten (1-2m vom Fenster)",
  schatten: "Schatten (weit vom Fenster)",
};
```

- [ ] **Step 4.2: Render-Methode für Q&A-Block**

Nach `_renderLibraryPicker()` einfügen:

```javascript
  _renderLocationLightFields(draft) {
    const roomValue = draft.room_type || "";
    const roomIsStandard = !roomValue || Object.prototype.hasOwnProperty.call(ROOM_LABELS, roomValue);
    const roomSelectValue = roomIsStandard ? roomValue : "__other__";
    const lightValue = draft.light_level || "";

    return `
      <div class="form-grid location-grid">
        <label class="field">
          <span>📍 Raum (optional)</span>
          <select name="room_type_select" data-action="set-room">
            <option value="">– nicht angegeben –</option>
            ${Object.entries(ROOM_LABELS).map(([val, label]) => `
              <option value="${this._escapeAttr(val)}" ${roomSelectValue === val ? "selected" : ""}>${this._escape(label)}</option>
            `).join("")}
            <option value="__other__" ${roomSelectValue === "__other__" ? "selected" : ""}>Andere…</option>
          </select>
          ${roomSelectValue === "__other__" ? `
            <input name="room_type_other" type="text" placeholder="Raum-Bezeichnung" value="${this._escapeAttr(roomValue)}" autocomplete="off">
          ` : ""}
        </label>

        <fieldset class="field">
          <legend>☀ Licht (optional)</legend>
          <div class="radio-group">
            <label><input type="radio" name="light_level" value=""             ${lightValue === ""             ? "checked" : ""}> Weiß nicht</label>
            <label><input type="radio" name="light_level" value="vollsonne"    ${lightValue === "vollsonne"    ? "checked" : ""}> ${LIGHT_LABELS.vollsonne}</label>
            <label><input type="radio" name="light_level" value="hell"         ${lightValue === "hell"         ? "checked" : ""}> ${LIGHT_LABELS.hell}</label>
            <label><input type="radio" name="light_level" value="halbschatten" ${lightValue === "halbschatten" ? "checked" : ""}> ${LIGHT_LABELS.halbschatten}</label>
            <label><input type="radio" name="light_level" value="schatten"     ${lightValue === "schatten"     ? "checked" : ""}> ${LIGHT_LABELS.schatten}</label>
          </div>
        </fieldset>
      </div>
    `;
  }
```

- [ ] **Step 4.3: Q&A in `_renderForm` einbinden**

In `_renderForm`, **vor** dem `<label class="field"><span>Spezies</span>`-Block (= vor dem bestehenden `form-grid`):

```javascript
        ${this._renderLocationLightFields(draft)}

        ${(draft.location_tips || draft.suitability_warning) ? `
          <div class="location-tips-card">
            ${draft.suitability_warning ? `
              <div class="warning-banner inline">
                <strong>⚠ Achtung</strong>
                <p>${this._escape(draft.suitability_warning)}</p>
              </div>
            ` : ""}
            ${draft.location_tips ? `
              <div class="info-banner">
                <strong>💡 Standort-Tipps</strong>
                <p>${this._escape(draft.location_tips)}</p>
              </div>
            ` : ""}
          </div>
        ` : ""}
```

- [ ] **Step 4.4: Submit-Logic für Q&A-Felder**

In `_onSubmit`, **nach** der bestehenden `for (const [k, v] of formData.entries())`-Schleife, vor dem Numerik-Cast:

```javascript
    // Room aus Dropdown/Other-Input zusammenführen
    const roomSelect = formData.get("room_type_select");
    if (roomSelect === "__other__") {
      data.room_type = (formData.get("room_type_other") || "").toString();
    } else if (roomSelect !== null) {
      data.room_type = roomSelect.toString();
    }
    delete data.room_type_select;
    delete data.room_type_other;

    // Q&A-Antworten + KI-Ergebnisse aus dem Draft übernehmen,
    // damit sie persistiert werden.
    if (this._draft && "location_tips" in this._draft) {
      data.location_tips = this._draft.location_tips || "";
    }
    if (this._draft && "suitability_warning" in this._draft) {
      data.suitability_warning = this._draft.suitability_warning || "";
    }
```

- [ ] **Step 4.5: `set-room`-Click-Handler (Andere-Dropdown-Toggle)**

In `_onClick`, im `switch (action)`-Block kein Eintrag nötig, weil das
über `_onChange` läuft. Im `_onChange` (vor dem bestehenden
`if (t.type === "file" ...)`-Block) ergänzen:

```javascript
    if (t.dataset && t.dataset.action === "set-room") {
      const val = t.value;
      if (val === "__other__") {
        this._draft = { ...(this._draft || {}), room_type: this._draft?.room_type || "" };
      } else {
        this._draft = { ...(this._draft || {}), room_type: val };
      }
      this._render();
      return;
    }
    if (t.name === "room_type_other") {
      this._draft = { ...(this._draft || {}), room_type: t.value };
      // Kein Re-Render, sonst Cursor weg
      return;
    }
    if (t.name === "light_level") {
      this._draft = { ...(this._draft || {}), light_level: t.value };
      return;
    }
```

- [ ] **Step 4.6: CSS**

In `_styles()` am Ende:

```css
      .location-grid {
        margin-bottom: 12px;
      }
      .location-grid .field legend {
        font-size: 0.9rem;
        margin-bottom: 4px;
        color: var(--primary-text-color);
        padding: 0;
      }
      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .radio-group label {
        display: flex;
        gap: 6px;
        align-items: center;
        font-size: 0.9rem;
        cursor: pointer;
      }
      .radio-group input[type="radio"] {
        accent-color: var(--sage);
      }

      .location-tips-card {
        margin: 12px 0;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .info-banner,
      .warning-banner {
        border-radius: 8px;
        padding: 10px 12px;
      }
      .info-banner {
        background: rgba(126, 174, 110, 0.12);
        border-left: 3px solid var(--sage);
      }
      .info-banner strong { display: block; margin-bottom: 4px; }
      .info-banner p { margin: 0; white-space: pre-wrap; }
      .warning-banner.inline,
      .warning-banner {
        background: rgba(245, 158, 11, 0.12);
        border-left: 3px solid #f59e0b;
      }
      .warning-banner strong { display: block; margin-bottom: 4px; color: #b45309; }
      .warning-banner p { margin: 0; white-space: pre-wrap; }
```

- [ ] **Step 4.7: Browser-Test + Commit**

1. "+ Neue Pflanze" → Q&A-Block oben sichtbar
2. Room-Dropdown zeigt 7 Optionen + "Andere…"
3. "Andere…" wählen → Textfeld erscheint
4. Licht-Radio anwählen → Auswahl bleibt nach Re-Render
5. Speichern ohne Q&A funktioniert weiterhin
6. Edit-Form einer bestehenden Pflanze: leer (weil Migration leer)

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Q&A-Felder Raum + Licht im Add/Edit-Form

Dropdown mit 7 Standard-Räumen + 'Andere…'-Freitext, Radio-Group
für 4 Licht-Level + 'Weiß nicht'. Werte landen via _onChange im
Draft und werden im _onSubmit ans Backend übergeben.
"
```

---

### Task 5: Frontend – KI-Prompts erweitern

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 5.1: Helper für den Q&A-Kontext-Block**

Nach `_suggestStructure()` einfügen:

```javascript
  _qaContextString(draft) {
    const room = draft.room_type ? (ROOM_LABELS[draft.room_type] || draft.room_type) : "nicht angegeben";
    const light = draft.light_level ? (LIGHT_LABELS[draft.light_level] || draft.light_level) : "nicht angegeben";
    return `\n- Standort: ${room}\n- Lichtintensität: ${light}`;
  }

  _suggestStructureWithLocation() {
    return {
      ...this._suggestStructure(),
      location_tips: { selector: { text: { multiline: true } } },
      suitability_warning: { selector: { text: { multiline: true } } },
    };
  }
```

- [ ] **Step 5.2: `_aiSuggestFromName` Prompt anpassen**

Im bestehenden Aufruf von `ai_task.generate_data` im `_aiSuggestFromName`. Vorher:

```javascript
          instructions:
            `Du bist Botaniker. Für die Zimmerpflanze "${name}": ` +
            `Gib Spezies (botanisch), deutschen Trivialnamen, empfohlene Gieß- und Düngeintervalle ` +
            `in Tagen sowie kurze Pflegetipps zurück. Antworte ausschließlich im vorgegebenen JSON-Schema.`,
          structure: this._suggestStructure(),
```

Ersetzen durch:

```javascript
          instructions:
            `Du bist Botaniker. Für die Zimmerpflanze "${name}":` +
            this._qaContextString(this._draft || {}) +
            `\n\nGib zurück:\n` +
            `- Spezies (botanisch), deutscher Trivialname\n` +
            `- Gieß- und Düngeintervalle in Tagen, passend zum genannten Licht-Level (bei wenig Licht seltener, bei Vollsonne öfter)\n` +
            `- Allgemeine Pflegetipps\n` +
            `- Standort-spezifische Tipps (was ist beim genannten Raum + Licht zu beachten?)\n` +
            `- Wenn der genannte Standort für diese Art ungeeignet ist: kurze Begründung. Sonst leeres Feld.\n` +
            `Antworte ausschließlich im vorgegebenen JSON-Schema.`,
          structure: this._suggestStructureWithLocation(),
```

- [ ] **Step 5.3: `_aiIdentifyFromPhoto` Prompt anpassen**

Analog: Im Aufruf von `ai_task.generate_data` in `_aiIdentifyFromPhoto`:

```javascript
          instructions:
            `Welche Zimmerpflanze ist auf dem angehängten Bild zu sehen?` +
            this._qaContextString(this._draft || {}) +
            `\n\nGib Spezies (botanisch), deutschen Trivialnamen, eine Konfidenz zwischen 0 und 1, ` +
            `empfohlene Gieß- und Düngeintervalle in Tagen passend zum genannten Licht-Level, ` +
            `Pflegetipps generell, Standort-spezifische Tipps und (falls Standort ungeeignet) eine kurze Begründung. ` +
            `Antworte ausschließlich im vorgegebenen JSON-Schema.`,
          attachments: [...]
          structure: {
            ...this._suggestStructureWithLocation(),
            confidence: { selector: { number: { min: 0, max: 1 } } },
          },
```

- [ ] **Step 5.4: Browser-Test + Commit**

1. "Neue Pflanze" → Name "Monstera" + Raum "Wohnzimmer" + Licht "Hell" → `✨ KI-Vorschlag`
2. Erwarte: `species`, `common_name`, `water_days`, `fertilize_days`, `tips`, sowie `location_tips` und ggf. `suitability_warning` in der KI-Antwort
3. Q&A-leer + KI-Vorschlag → fällt auf "nicht angegeben" zurück
4. Foto-Identify mit gewähltem Standort → analog

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: KI-Prompts berücksichtigen Q&A-Standort + Licht

_qaContextString baut den Kontext-Block, _suggestStructureWithLocation
ergänzt das JSON-Schema um location_tips und suitability_warning.
Suggest- und Identify-Pfade nutzen beide.
"
```

---

### Task 6: Frontend – Detail-View Standort-Sektion + Warning-Banner

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 6.1: Renderer für Standort-Sektion**

Vor `_renderHistorySection(p)`:

```javascript
  _renderLocationSection(p) {
    const room = p.room_type ? (ROOM_LABELS[p.room_type] || p.room_type) : "";
    const light = p.light_level ? (LIGHT_LABELS[p.light_level] || p.light_level) : "";
    const position = p.location || "";
    if (!room && !light && !position && !p.location_tips) return "";

    const facts = [
      room ? `Raum: ${room}` : "",
      light ? `Licht: ${light}` : "",
      position ? `Position: ${this._escape(position)}` : "",
    ].filter(Boolean).join(" · ");

    return `
      <section class="location-section">
        <h3>📍 Standort</h3>
        ${facts ? `<p class="muted small">${this._escape(facts)}</p>` : ""}
        ${p.location_tips ? `
          <div class="info-banner">
            <strong>💡 Standort-Tipps</strong>
            <p>${this._escape(p.location_tips)}</p>
          </div>
        ` : ""}
      </section>
    `;
  }
```

- [ ] **Step 6.2: Renderer für Warning-Banner oben**

Direkt nach `_renderLocationSection`:

```javascript
  _renderSuitabilityWarning(p) {
    if (!p.suitability_warning) return "";
    return `
      <div class="warning-banner detail-warning">
        <button class="warning-dismiss" data-action="dismiss-warning" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Warnung ausblenden">✕</button>
        <strong>⚠ Achtung</strong>
        <p>${this._escape(p.suitability_warning)}</p>
      </div>
    `;
  }
```

- [ ] **Step 6.3: In Detail-View einbinden**

In `_renderDetail`, **direkt nach** dem öffnenden `<article class="detail">` und **vor** der `<header class="detail-header">`-Zeile:

```javascript
        ${this._renderSuitabilityWarning(p)}
```

Und **nach** dem `detail-grid`, **vor** der `tips`-Sektion:

```javascript
        ${this._renderLocationSection(p)}
```

- [ ] **Step 6.4: Dismiss-Click-Handler**

In `_onClick`, im `switch (action)`-Block:

```javascript
      case "dismiss-warning":
        this._callService("plant_care", "update_plant", {
          plant_id: id,
          suitability_warning: "",
        })
          .then(() => this._showToast("success", "Warnung ausgeblendet"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
```

- [ ] **Step 6.5: CSS für Detail-Warning**

```css
      .location-section {
        margin-bottom: 20px;
      }
      .location-section h3 { margin: 0 0 6px; font-size: 1rem; }
      .detail-warning {
        position: relative;
        margin-bottom: 16px;
      }
      .warning-dismiss {
        position: absolute;
        top: 6px;
        right: 8px;
        background: none;
        border: none;
        font-size: 1rem;
        cursor: pointer;
        color: var(--secondary-text-color, #777);
        line-height: 1;
        padding: 4px 6px;
      }
      .warning-dismiss:hover { color: var(--primary-text-color); }
```

- [ ] **Step 6.6: Browser-Test + Commit**

1. Pflanze mit `room_type` + `light_level` öffnen → Standort-Sektion sichtbar
2. Pflanze mit `location_tips` → Info-Banner in der Sektion
3. Pflanze mit `suitability_warning` → orangener Banner ganz oben + ✕-Button
4. ✕ tappen → Banner verschwindet, kein Reload nötig (next render aktualisiert)

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Standort-Sektion + dismissbares Warning-Banner

Detail-View bekommt zwischen detail-grid und tips eine 📍 Standort-
Sektion (nur wenn Daten vorhanden), Pflanzen mit suitability_warning
zeigen oben einen orangen Banner mit ✕-Dismiss-Button (ruft
update_plant mit leerem Warning auf).
"
```

---

### Task 7: README + finaler Check

**Files:**
- Modify: `README.md`

- [ ] **Step 7.1: README-Sektion**

Im Abschnitt "Bedienung", **nach** der "Pflanze hinzufügen"-Section,
neuen Absatz:

```markdown
### Standort-Q&A

Beim Anlegen kannst du optional **Raum** und **Lichtintensität** angeben.
Beide Werte fließen in den KI-Vorschlag ein → die KI passt die Gieß-
und Düngeintervalle daran an und gibt zusätzlich Standort-spezifische
Tipps zurück. Wenn der genannte Standort für die Pflanze ungeeignet
ist (z.B. Sukkulente im dunklen Bad), zeigt der Detail-View oben ein
oranges Warnbanner, das du jederzeit ausblenden kannst.

Beide Felder sind optional – Q&A leer lassen funktioniert wie vorher.
Bei späterem Umzug der Pflanze: Felder im Edit-Form ändern, dann KI-
Vorschlag erneut tippen für aktualisierte Intervalle.
```

- [ ] **Step 7.2: Final-Sanity**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3 && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('OK')"
```

Expected: 40 passed, JSON OK.

- [ ] **Step 7.3: Commit**

```bash
git add README.md
git commit -m "README: Standort-Q&A Sektion"
```

---

## Self-Review

**Spec coverage:**
- Schema-Migration → Task 1.2
- Service-Schema-Erweiterung → Task 2.1
- services.yaml + i18n → Task 2.2 + 2.3 + 2.4
- Sensor-Attribute → Task 3.1
- Form-UI mit Room-Dropdown + Light-Radios + Andere-Fallback → Task 4.2 + 4.3
- Q&A → Draft → Submit-Path → Task 4.4 + 4.5
- KI-Prompt-Erweiterung (suggest + identify) → Task 5.2 + 5.3
- Detail-View Standort-Sektion → Task 6.1 + 6.3
- Dismissbares Warning-Banner → Task 6.2 + 6.4
- README → Task 7.1

**Placeholder scan:** Keine TBDs, alle Code-Blöcke vollständig. ✓

**Type consistency:** `light_level` und `room_type` sind durchgehend
strings. `ROOM_LABELS` und `LIGHT_LABELS` sind JS-Objekte mit
stringbasierten Keys, konsistent verwendet in Form-Render und
Detail-Render. `_qaContextString` returnt String, wird in `instructions`
beider AI-Calls eingefügt. `_suggestStructureWithLocation` returnt
Schema-Dict, wird ohne Type-Mismatch in `structure` übergeben. ✓
