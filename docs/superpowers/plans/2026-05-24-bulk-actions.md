# Bulk-Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-Select-Mode im Panel mit Bulk-Aktionen "💧 Gegossen" und "🌱 Gedüngt" für mehrere Pflanzen gleichzeitig.

**Architecture:** Pure Frontend-Erweiterung. Neuer UI-Mode mit Checkbox-Overlay auf Cards, Sticky-Bottom-Bar, parallele Service-Calls via `Promise.all`.

**Tech Stack:** Vanilla-JS-Web-Component (`plant-care-panel.js`), keine neuen Dependencies.

**Spec:** [docs/superpowers/specs/2026-05-24-bulk-actions-design.md](../specs/2026-05-24-bulk-actions-design.md)

---

### Task 1: State + Topbar-Toggle

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 1.1: State im Constructor initialisieren**

In `plant-care-panel.js`, im `constructor()` der `PlantCarePanel`-Klasse, nach `this._roomFilter = ROOM_ALL;`:

```javascript
    this._bulkMode = false;
    this._bulkSelection = new Set();
    this._bulkBusy = false;
```

- [ ] **Step 1.2: Bulk-State in Render-Signatur aufnehmen**

In `_render(force = false)`, im `sig`-Array:

Aktuell:

```javascript
    const sig = [
      this._view,
      this._selectedId || "",
      this._addTab,
      this._roomFilter,
      this._aiBusy ? 1 : 0,
      this._toast ? this._toast.msg : "",
      this._signature(plants),
      JSON.stringify(this._draft || {}),
    ].join("|");
```

Ersetzen durch:

```javascript
    const sig = [
      this._view,
      this._selectedId || "",
      this._addTab,
      this._roomFilter,
      this._aiBusy ? 1 : 0,
      this._toast ? this._toast.msg : "",
      this._signature(plants),
      JSON.stringify(this._draft || {}),
      this._bulkMode ? 1 : 0,
      this._bulkBusy ? 1 : 0,
      Array.from(this._bulkSelection).sort().join(","),
    ].join("|");
```

- [ ] **Step 1.3: Topbar-Buttons anpassen**

In `_render`, im `<header class="topbar">`-Block. Aktuell:

```javascript
          ${this._view === "list" ? `
            <button class="btn primary" data-action="new">+ Neue Pflanze</button>
          ` : `
            <button class="btn ghost" data-action="back">← Zurück</button>
          `}
```

Ersetzen durch:

```javascript
          ${this._view === "list" ? (this._bulkMode ? `
            <button class="btn ghost" data-action="bulk-cancel">Abbrechen</button>
          ` : `
            <button class="btn ghost" data-action="bulk-toggle">☑ Auswahl</button>
            <button class="btn primary" data-action="new">+ Neue Pflanze</button>
          `) : `
            <button class="btn ghost" data-action="back">← Zurück</button>
          `}
```

- [ ] **Step 1.4: Click-Handler für die neuen Actions**

In `_onClick(evt)`, im `switch (action)`-Block, vor dem `case "new":`:

```javascript
      case "bulk-toggle":
        this._bulkMode = true;
        this._bulkSelection = new Set();
        this._setState({});
        break;
      case "bulk-cancel":
        this._bulkMode = false;
        this._bulkSelection = new Set();
        this._setState({});
        break;
```

- [ ] **Step 1.5: Sanity-Check + Commit**

Manuelle Code-Inspektion: keine Syntax-Fehler in den geänderten Blöcken. Browser-Cache hard-reload in HA und prüfen ob "☑ Auswahl"-Button erscheint.

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Bulk-Mode: State + Topbar-Toggle

Neuer Bulk-Mode mit _bulkSelection (Set<plant_id>) und _bulkBusy.
Topbar zeigt im List-View je nach Mode entweder
'☑ Auswahl' + '+ Neue Pflanze' oder 'Abbrechen'.
"
```

---

### Task 2: Card-Render mit Checkbox-Overlay

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 2.1: `_renderCard` erweitern**

Finde `_renderCard(p) {` und ersetze die komplette Methode:

```javascript
  _renderCard(p) {
    const status = p.state || "ok";
    const selected = this._bulkMode && this._bulkSelection.has(p.plant_id);
    const cardClass = `card${this._bulkMode ? " bulk" : ""}${selected ? " selected" : ""}`;
    const action = this._bulkMode ? "bulk-toggle-card" : "open-detail";
    return `
      <article class="${cardClass}" data-action="${action}" data-id="${this._escapeAttr(p.plant_id)}">
        ${this._bulkMode ? `
          <div class="bulk-check ${selected ? "checked" : ""}" aria-hidden="true">
            ${selected ? "✓" : ""}
          </div>
        ` : ""}
        <div class="thumb">
          ${p.photo
            ? `<img src="${this._escapeAttr(p.photo)}" alt="">`
            : `<div class="thumb-placeholder">🌱</div>`}
        </div>
        <div class="card-body">
          <h3>${this._escape(p.name)}</h3>
          ${p.species ? `<p class="muted">${this._escape(p.species)}</p>` : ""}
          <p class="status ${STATUS_CLASS[status] || ""}">${this._escape(STATUS_LABEL[status] || status)}</p>
          <p class="muted small">💧 ${this._escape(this._relativeTime(p.last_watered))}</p>
        </div>
      </article>
    `;
  }
```

- [ ] **Step 2.2: Click-Handler für Card-Toggle**

In `_onClick(evt)`, vor dem `case "open-detail":` einfügen:

```javascript
      case "bulk-toggle-card":
        if (!this._bulkMode) break;
        if (this._bulkSelection.has(id)) {
          this._bulkSelection.delete(id);
        } else {
          this._bulkSelection.add(id);
        }
        this._setState({});
        break;
```

- [ ] **Step 2.3: CSS für Checkbox-Overlay**

In `_styles()`, nach den `.card`-Regeln (vor `.card:hover`):

```css
      .card.bulk {
        cursor: pointer;
        user-select: none;
      }
      .card.bulk.selected {
        outline: 3px solid var(--sage);
        outline-offset: -3px;
      }
      .bulk-check {
        position: absolute;
        top: 10px;
        left: 10px;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: var(--card-background-color, #fff);
        border: 2px solid var(--sage);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        font-weight: 700;
        color: var(--sage);
        z-index: 2;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
      }
      .bulk-check.checked {
        background: var(--sage);
        color: #fff;
      }
```

`.card`-Regel braucht zusätzlich `position: relative` (damit das absolut positionierte Overlay daran ausgerichtet ist). Finde die bestehende `.card`-Regel und ergänze die Property:

```css
      .card {
        background: var(--card-background-color, #fff);
        border-radius: 12px;
        overflow: hidden;
        cursor: pointer;
        transition: transform .15s, box-shadow .15s;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        position: relative;
      }
```

(Bestehende Properties beibehalten; nur `position: relative` ist neu. Genauen Selektor in der Datei suchen und ergänzen.)

- [ ] **Step 2.4: Browser-Test (manuell)**

In HA:
1. Hard-Reload (Cmd+Shift+R)
2. "☑ Auswahl" tappen
3. Auf Cards tappen – Outline + ✓-Overlay erscheint/verschwindet
4. "Abbrechen" tappen – alle Overlays weg

- [ ] **Step 2.5: Commit**

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Bulk-Mode: Cards mit Checkbox-Overlay + Toggle-Click

Im Bulk-Mode bekommen Cards einen Checkbox-Overlay top-left,
Outline bei Selektion, und der Card-Click toggelt die Auswahl
statt die Detail-View zu öffnen.
"
```

---

### Task 3: Sticky-Bottom-Action-Bar

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 3.1: Render-Methode hinzufügen**

Nach `_renderEmpty()` (vor `/* ----- Form View ----- */`) einfügen:

```javascript
  _renderBulkActionBar() {
    const visiblePlants = this._visiblePlants();
    const visibleIds = visiblePlants.map((p) => p.plant_id);
    const visibleSelectedCount = visibleIds.filter(
      (id) => this._bulkSelection.has(id),
    ).length;
    const allVisibleSelected =
      visibleIds.length > 0 && visibleSelectedCount === visibleIds.length;
    const totalSelected = this._bulkSelection.size;
    const disabled = totalSelected === 0 || this._bulkBusy;
    const busyMark = this._bulkBusy ? " ⏳" : "";

    return `
      <div class="bulk-bar">
        <label class="bulk-bar-select-all">
          <input
            type="checkbox"
            data-action="bulk-select-all"
            ${allVisibleSelected ? "checked" : ""}
            ${this._bulkBusy ? "disabled" : ""}
          />
          <span>Alle</span>
        </label>
        <span class="bulk-bar-count">
          ${totalSelected} ${totalSelected === 1 ? "Pflanze" : "Pflanzen"} ausgewählt
        </span>
        <div class="bulk-bar-actions">
          <button
            class="btn primary"
            data-action="bulk-water"
            ${disabled ? "disabled" : ""}
          >💧 Gegossen${busyMark}</button>
          <button
            class="btn primary"
            data-action="bulk-fertilize"
            ${disabled ? "disabled" : ""}
          >🌱 Gedüngt${busyMark}</button>
        </div>
      </div>
    `;
  }

  _visiblePlants() {
    const plants = this._plants();
    const filter = this._roomFilter;
    if (filter === ROOM_ALL) return plants;
    return plants.filter((p) => (p.location || "").trim() === filter);
  }
```

- [ ] **Step 3.2: Bar im `_render` einbinden**

In `_render`, am Ende des `innerHTML`-Templates. Finde:

```javascript
        ${this._toast ? this._renderToast() : ""}
        <main class="main">${this._renderView()}</main>
      </div>
    `;
```

Ersetzen durch:

```javascript
        ${this._toast ? this._renderToast() : ""}
        <main class="main">${this._renderView()}</main>
        ${this._bulkMode && this._view === "list" ? this._renderBulkActionBar() : ""}
      </div>
    `;
```

- [ ] **Step 3.3: CSS für Bulk-Bar**

In `_styles()`, am Ende der CSS (vor dem schließenden Backtick):

```css
      .bulk-bar {
        position: sticky;
        bottom: 0;
        margin-top: 16px;
        background: var(--card-background-color, #fff);
        border-top: 1px solid var(--divider-color, rgba(0,0,0,0.1));
        box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
        padding: 12px 16px;
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
        z-index: 5;
      }
      .bulk-bar-select-all {
        display: flex;
        align-items: center;
        gap: 6px;
        cursor: pointer;
        user-select: none;
      }
      .bulk-bar-select-all input[type="checkbox"] {
        width: 18px;
        height: 18px;
        accent-color: var(--sage);
      }
      .bulk-bar-count {
        flex: 1 1 auto;
        color: var(--secondary-text-color, #777);
        font-size: 0.9rem;
        min-width: 0;
      }
      .bulk-bar-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
```

- [ ] **Step 3.4: Click-Handler für `bulk-select-all`**

In `_onClick`, nach `case "bulk-toggle-card":`:

```javascript
      case "bulk-select-all": {
        const visible = this._visiblePlants();
        const visibleIds = visible.map((p) => p.plant_id);
        const allSelected =
          visibleIds.length > 0 &&
          visibleIds.every((id) => this._bulkSelection.has(id));
        if (allSelected) {
          visibleIds.forEach((id) => this._bulkSelection.delete(id));
        } else {
          visibleIds.forEach((id) => this._bulkSelection.add(id));
        }
        this._setState({});
        break;
      }
```

- [ ] **Step 3.5: Browser-Test + Commit**

Manuell prüfen: Bulk-Bar erscheint mit Counter, "Alle"-Toggle markiert alle sichtbaren.

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Bulk-Mode: Sticky-Bottom-Action-Bar mit Counter + Select-All"
```

---

### Task 4: Bulk-Action ausführen

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 4.1: `_executeBulkAction` implementieren**

Nach `_deletePlant(plantId)` einfügen:

```javascript
  async _executeBulkAction(serviceName) {
    const ids = Array.from(this._bulkSelection);
    if (ids.length === 0 || this._bulkBusy) return;
    const labels = {
      water_plant: { confirm: "als gegossen", past: "als gegossen" },
      fertilize_plant: { confirm: "als gedüngt", past: "als gedüngt" },
    };
    const label = labels[serviceName];
    if (!label) return;
    if (ids.length > 5) {
      if (!confirm(`${ids.length} Pflanzen ${label.confirm} markieren?`)) return;
    }
    this._bulkBusy = true;
    this._render();
    try {
      await Promise.all(
        ids.map((id) =>
          this._callService("plant_care", serviceName, { plant_id: id }),
        ),
      );
      this._showToast(
        "success",
        `${ids.length} ${ids.length === 1 ? "Pflanze" : "Pflanzen"} ${label.past} markiert`,
      );
      this._bulkSelection.clear();
      this._bulkMode = false;
    } catch (err) {
      this._showToast(
        "error",
        "Bulk-Action fehlgeschlagen: " + this._fmtErr(err),
      );
    } finally {
      this._bulkBusy = false;
      this._setState({});
    }
  }
```

- [ ] **Step 4.2: Click-Handler verdrahten**

In `_onClick`, nach `case "bulk-select-all":`:

```javascript
      case "bulk-water":
        this._executeBulkAction("water_plant");
        break;
      case "bulk-fertilize":
        this._executeBulkAction("fertilize_plant");
        break;
```

- [ ] **Step 4.3: Browser-Test**

1. 2 Pflanzen auswählen → 💧 tappen → kein Confirm, Toast "2 Pflanzen als gegossen markiert", Bulk-Mode aus
2. 6 Pflanzen auswählen → 💧 tappen → Confirm-Dialog → OK → Aktion läuft
3. 6 Pflanzen auswählen → 💧 tappen → Confirm → Abbrechen → nichts passiert
4. Prüfen ob `last_watered` der betroffenen Pflanzen aktualisiert ist (im Detail-View)

- [ ] **Step 4.4: Commit**

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Bulk-Mode: _executeBulkAction mit Promise.all und Confirm>5

Parallele Service-Calls für alle ausgewählten Pflanzen.
Bei mehr als 5 ausgewählten Pflanzen Browser-Confirm-Dialog.
Erfolg: Success-Toast + Bulk-Mode beenden.
Fehler: Error-Toast (Teilerfolge nicht detailliert).
"
```

---

### Task 5: README + finaler Check

**Files:**
- Modify: `README.md`

- [ ] **Step 5.1: README-Sektion ergänzen**

In `README.md`, im Abschnitt "Bedienung", nach der "Sensor-Verknüpfung"-Sektion einfügen:

```markdown
### Mehrere Pflanzen gleichzeitig erledigen

Auf der List-View **☑ Auswahl** tappen → jede Card wird per Klick
selektiert/deselektiert. In der Bottom-Bar **💧 Gegossen** oder
**🌱 Gedüngt** auslösen. Bei mehr als 5 Pflanzen kommt ein
Bestätigungs-Dialog. Die "Alle"-Checkbox in der Bar bezieht sich auf
die aktuell sichtbaren Pflanzen (Raum-Filter wird respektiert).
```

- [ ] **Step 5.2: Final-Sanity-Check**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

Expected: `py_compile OK` + alle bisherigen Tests grün (Frontend-Änderung
sollte Python-Tests nicht beeinflussen).

- [ ] **Step 5.3: Commit**

```bash
git add README.md
git commit -m "README: Bulk-Actions Sektion"
```

---

## Self-Review

**Spec coverage:**
- Bulk-Mode-Toggle in Topbar → Task 1.3
- Checkbox-Overlay auf Cards → Task 2.1
- Sticky-Bottom-Bar mit Counter + "Alle"-Toggle → Task 3.1 + 3.4
- Action-Buttons 💧 + 🌱 → Task 3.1, gewired in Task 4.2
- Confirmation bei > 5 → Task 4.1
- Parallel Service-Calls → Task 4.1
- Bulk-Mode resettet bei Erfolg → Task 4.1
- Filter-respektierende "Alle"-Selektion → Task 3.4
- README → Task 5.1

**Placeholder scan:** Keine TBDs, alle Code-Blöcke vollständig. ✓

**Type consistency:** `_bulkSelection` ist überall `Set<string>` (plant_id).
`_executeBulkAction` accepts `serviceName: "water_plant"|"fertilize_plant"`.
Render-Methode `_visiblePlants()` ist in Task 3.1 definiert und in 3.4
verwendet. ✓
