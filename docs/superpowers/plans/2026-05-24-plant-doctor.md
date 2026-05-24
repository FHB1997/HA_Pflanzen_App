# Pflanzen-Sprechstunde Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI-gestützte Diagnose von Pflanzenproblemen mit Behandlungsplan, Treatment-Tracking und Wiedervorlage-Reminder.

**Architecture:** Neuer AI-Task-Flow nutzt das bestehende `ai_task`-Pattern mit eigenem Prompt + Schema. Treatments werden pro Pflanze als Array persistiert (analog Foto-Verlauf). Sensor-Status bekommt `needs_attention` als höchste Priorität bei offenen, fälligen Treatments. Reminder-Engine versendet bei diesem Status andere Action-Buttons (Resolve/Dismiss/Snooze).

**Tech Stack:** Home Assistant Custom Integration, pytest, ai_task Service, Vanilla-JS-Web-Component.

**Spec:** [docs/superpowers/specs/2026-05-24-plant-doctor-design.md](../specs/2026-05-24-plant-doctor-design.md)

---

### Task 1: Pure Helper + Tests

**Files:**
- Modify: `custom_components/plant_care/_utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1.1: Tests schreiben**

In `tests/test_utils.py`, am Ende:

```python
# --------------------------- Treatment Helper ---------------------------

def test_filter_open_treatments_empty():
    assert filter_open_treatments([]) == []


def test_filter_open_treatments_only_open():
    treatments = [
        {"id": "a", "status": "open"},
        {"id": "b", "status": "resolved"},
        {"id": "c", "status": "dismissed"},
        {"id": "d", "status": "open"},
    ]
    result = filter_open_treatments(treatments)
    assert [t["id"] for t in result] == ["a", "d"]


def test_has_overdue_treatment_no_open():
    treatments = [{"id": "a", "status": "resolved", "follow_up_at": "2025-01-01T00:00:00+00:00"}]
    assert has_overdue_treatment(treatments, NOW) is False


def test_has_overdue_treatment_open_but_not_yet_due():
    future = (NOW + timedelta(days=3)).isoformat()
    treatments = [{"id": "a", "status": "open", "follow_up_at": future}]
    assert has_overdue_treatment(treatments, NOW) is False


def test_has_overdue_treatment_open_and_overdue():
    past = (NOW - timedelta(hours=1)).isoformat()
    treatments = [{"id": "a", "status": "open", "follow_up_at": past}]
    assert has_overdue_treatment(treatments, NOW) is True


def test_has_overdue_treatment_missing_follow_up_treated_as_overdue():
    # Treatment ohne follow_up_at = sofort fällig (sicherer Default).
    treatments = [{"id": "a", "status": "open"}]
    assert has_overdue_treatment(treatments, NOW) is True


def test_parse_treatment_action_id_resolve():
    assert parse_treatment_action_id("PLANTCARE_RESOLVE_abc_xyz123") == (
        "RESOLVE", "abc", "xyz123",
    )


def test_parse_treatment_action_id_dismiss():
    assert parse_treatment_action_id("PLANTCARE_DISMISS_p1_t1") == (
        "DISMISS", "p1", "t1",
    )


def test_parse_treatment_action_id_unknown_returns_none():
    assert parse_treatment_action_id("PLANTCARE_WATER_abc") is None


def test_parse_treatment_action_id_missing_treatment_returns_none():
    assert parse_treatment_action_id("PLANTCARE_RESOLVE_onlyplant") is None
```

Import-Liste aktualisieren:

```python
from _utils import (  # type: ignore[import-not-found]
    cap_photos,
    clean_data,
    compute_snooze_last_notified,
    filter_open_treatments,
    has_overdue_treatment,
    is_in_quiet_hours,
    is_rate_limited,
    migrate_legacy_photo,
    needs_time_based,
    parse_action_id,
    parse_iso,
    parse_time_string,
    parse_treatment_action_id,
    sort_photos,
    try_float,
    utcnow_iso,
)
```

- [ ] **Step 1.2: Tests fail-check**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 1.3: Helper implementieren**

In `_utils.py`, am Ende:

```python
def filter_open_treatments(treatments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Liefert nur Treatments mit ``status='open'``."""
    return [t for t in treatments if t.get("status") == "open"]


def has_overdue_treatment(
    treatments: list[dict[str, Any]], now: datetime
) -> bool:
    """True wenn ein offenes Treatment fällig ist.

    Fehlt ``follow_up_at``, gilt das Treatment als sofort fällig.
    """
    for treatment in treatments:
        if treatment.get("status") != "open":
            continue
        follow_up_iso = treatment.get("follow_up_at")
        if not follow_up_iso:
            return True
        follow_up = parse_iso(follow_up_iso)
        if follow_up is None or now >= follow_up:
            return True
    return False


def parse_treatment_action_id(
    action_id: str,
) -> tuple[str, str, str] | None:
    """Zerlegt ``PLANTCARE_<RESOLVE|DISMISS>_<plant_id>_<treatment_id>``.

    Returns:
        Tuple ``(action, plant_id, treatment_id)`` oder ``None``.
    """
    if not action_id or not action_id.startswith("PLANTCARE_"):
        return None
    parts = action_id.split("_", 3)
    if len(parts) < 4:
        return None
    _, action, plant_id, treatment_id = parts
    if action not in ("RESOLVE", "DISMISS"):
        return None
    if not treatment_id:
        return None
    return (action, plant_id, treatment_id)
```

- [ ] **Step 1.4: Tests grün**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -3`
Expected: alle Tests grün.

- [ ] **Step 1.5: Commit**

```bash
git add custom_components/plant_care/_utils.py tests/test_utils.py
git commit -m "Add Treatment-Helper: filter_open, has_overdue, parse_action_id"
```

---

### Task 2: Const + Coordinator

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/coordinator.py`

- [ ] **Step 2.1: Konstanten**

In `const.py`:

```python
# Status-Werte (existing)
...
STATUS_NEEDS_ATTENTION: Final = "needs_attention"  # höchste Priorität

# Treatment Service-Namen
SERVICE_DIAGNOSE_PLANT: Final = "diagnose_plant"
SERVICE_RESOLVE_TREATMENT: Final = "resolve_treatment"

# Anti-Spam
MIN_DIAGNOSE_INTERVAL_SECONDS: Final = 60
```

`STATUS_*`-Liste auch im Sensor-Modul mit-importieren.

- [ ] **Step 2.2: Imports im Coordinator**

```python
from ._utils import (
    ...
    filter_open_treatments,
    has_overdue_treatment,
    ...
)
```

```python
from .const import (
    ...
    MIN_DIAGNOSE_INTERVAL_SECONDS,
    STATUS_NEEDS_ATTENTION,
    ...
)
```

- [ ] **Step 2.3: Migration in async_load**

In `async_load`, im Block der Felder ergänzt:

```python
            plant.setdefault("treatments", [])
```

- [ ] **Step 2.4: `async_diagnose_plant`**

Nach `async_remove_plant_photo`:

```python
    async def async_diagnose_plant(
        self,
        plant_id: str,
        photo_path: str,
        ai_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Speichert das Ergebnis einer AI-Diagnose als Treatment.

        Der eigentliche AI-Call läuft im Frontend (siehe ai_task.generate_data).
        Diese Methode validiert + persistiert nur.

        Returns:
            Das eingefügte Treatment-Objekt.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")

        plant = self._plants[plant_id]

        # Anti-Spam: ignoriere wenn das letzte Treatment <60s alt ist.
        treatments = list(plant.get("treatments") or [])
        if treatments:
            latest = treatments[-1]
            started = parse_iso(latest.get("started_at"))
            if started is not None:
                age = (datetime.now(timezone.utc) - started).total_seconds()
                if age < MIN_DIAGNOSE_INTERVAL_SECONDS:
                    raise ValueError(
                        f"Bitte mindestens {MIN_DIAGNOSE_INTERVAL_SECONDS}s "
                        "zwischen Diagnose-Anfragen warten"
                    )

        diagnosis = str(ai_response.get("diagnosis") or "").strip()
        if not diagnosis:
            raise ValueError("AI-Antwort enthält keine diagnosis")

        confidence = ai_response.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        steps_raw = ai_response.get("treatment_steps") or []
        if isinstance(steps_raw, str):
            steps = [steps_raw]
        elif isinstance(steps_raw, list):
            steps = [str(s) for s in steps_raw if s]
        else:
            steps = []

        try:
            follow_up_days = int(ai_response.get("follow_up_days") or 7)
        except (TypeError, ValueError):
            follow_up_days = 7
        follow_up_days = max(1, min(30, follow_up_days))

        severity = str(ai_response.get("severity") or "").strip().lower()
        if severity not in ("low", "medium", "high"):
            severity = "medium"

        started_at = datetime.now(timezone.utc)
        treatment_id = uuid.uuid4().hex[:12]
        treatment = {
            "id": treatment_id,
            "started_at": started_at.isoformat(),
            "photo_path": photo_path,
            "diagnosis": diagnosis,
            "confidence": confidence,
            "treatment_steps": steps,
            "follow_up_days": follow_up_days,
            "follow_up_at": (
                started_at + timedelta(days=follow_up_days)
            ).isoformat(),
            "severity": severity,
            "status": "open",
            "resolved_at": None,
        }

        treatments.append(treatment)
        plant["treatments"] = treatments
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.info(
            "Plant Care: Treatment %s für Pflanze %s angelegt (%s)",
            treatment_id,
            plant_id,
            diagnosis[:60],
        )
        return treatment
```

- [ ] **Step 2.5: `async_resolve_treatment`**

```python
    async def async_resolve_treatment(
        self,
        plant_id: str,
        treatment_id: str,
        outcome: str = "resolved",
    ) -> dict[str, Any]:
        """Schließt ein offenes Treatment ab.

        ``outcome`` ist entweder ``"resolved"`` (erfolgreich) oder
        ``"dismissed"`` (User verwirft / war Fehlalarm).
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        if outcome not in ("resolved", "dismissed"):
            raise ValueError(f"Ungültiges outcome: {outcome}")

        plant = self._plants[plant_id]
        treatments = list(plant.get("treatments") or [])

        for treatment in treatments:
            if treatment.get("id") == treatment_id:
                treatment["status"] = outcome
                treatment["resolved_at"] = datetime.now(timezone.utc).isoformat()
                plant["treatments"] = treatments
                await self._async_save_now()
                async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
                _LOGGER.info(
                    "Plant Care: Treatment %s als %s markiert",
                    treatment_id,
                    outcome,
                )
                return treatment

        raise ValueError(
            f"Treatment {treatment_id} nicht in Pflanze {plant_id} gefunden"
        )
```

- [ ] **Step 2.6: Reminder-Engine erweitert (Action-Buttons bei needs_attention)**

In `evaluate_reminders` ist die Status-Detection bisher per Sensor-State.
Erweitere `_build_notification_actions` um eine Verzweigung für
`STATUS_NEEDS_ATTENTION`. Diese braucht aber zusätzlich die treatment_id
für die Action-ID. Anpassung:

```python
def _build_notification_actions(
    plant_id: str,
    status: str,
    open_treatment_id: str | None = None,
) -> list[dict[str, str]]:
    if status == STATUS_NEEDS_ATTENTION and open_treatment_id:
        return [
            {
                "action": f"PLANTCARE_RESOLVE_{plant_id}_{open_treatment_id}",
                "title": "✓ Erledigt",
            },
            {
                "action": f"PLANTCARE_DISMISS_{plant_id}_{open_treatment_id}",
                "title": "✗ Verwerfen",
            },
            {"action": f"PLANTCARE_SNOOZE_{plant_id}", "title": "💤 Snooze 1d"},
        ]
    # bestehende water/fertilize-Logik bleibt
    actions: list[dict[str, str]] = []
    if status in (STATUS_NEEDS_WATER, STATUS_NEEDS_BOTH):
        actions.append({"action": f"PLANTCARE_WATER_{plant_id}", "title": "💧 Gegossen"})
    if status in (STATUS_NEEDS_FERTILIZER, STATUS_NEEDS_BOTH):
        actions.append({"action": f"PLANTCARE_FERTILIZE_{plant_id}", "title": "🌱 Gedüngt"})
    actions.append({"action": f"PLANTCARE_SNOOZE_{plant_id}", "title": "💤 Snooze 1d"})
    return actions
```

In `evaluate_reminders` muss vor dem Build die `open_treatment_id`
gefunden werden:

```python
            open_treatment_id = None
            if state.state == STATUS_NEEDS_ATTENTION:
                open_treatments = filter_open_treatments(plant.get("treatments") or [])
                if open_treatments:
                    # ältestes offenes Treatment ist relevantestes
                    open_treatment_id = open_treatments[0].get("id")

            ...
            payload["data"] = {
                "actions": _build_notification_actions(
                    plant_id, state.state, open_treatment_id
                ),
                ...
            }
```

Auch die Message-Funktion erweitern:

```python
def _build_reminder_message(name: str, status: str) -> str:
    if status == STATUS_NEEDS_ATTENTION:
        return f"🔍 {name}: Treatment-Check fällig."
    if status == STATUS_NEEDS_BOTH:
        return f"🌿 {name} braucht Wasser und Dünger."
    if status == STATUS_NEEDS_WATER:
        return f"🌿 {name} braucht Wasser."
    if status == STATUS_NEEDS_FERTILIZER:
        return f"🌱 {name} braucht Dünger."
    return f"🌿 {name}"
```

- [ ] **Step 2.7: Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/const.py custom_components/plant_care/coordinator.py
git commit -m "Coordinator: async_diagnose_plant + async_resolve_treatment

- treatments[] Persistenz mit ID, Status (open/resolved/dismissed)
- async_diagnose_plant validiert AI-Response, baut Treatment-Entry,
  Anti-Spam-Throttle 60s zwischen Anfragen
- async_resolve_treatment setzt status + resolved_at
- Reminder-Engine baut spezielle Action-Buttons (RESOLVE/DISMISS/
  SNOOZE) bei needs_attention Status, mit Treatment-ID in Action-ID
- _build_reminder_message ergänzt für needs_attention
"
```

---

### Task 3: Sensor-Status erweitern

**Files:**
- Modify: `custom_components/plant_care/sensor.py`

- [ ] **Step 3.1: Imports**

```python
from ._utils import filter_open_treatments, has_overdue_treatment, needs_time_based, try_float
```

```python
from .const import (
    DOMAIN,
    MOISTURE_LOW_PCT,
    MOISTURE_OK_PCT,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    STATUS_NEEDS_ATTENTION,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
)
```

- [ ] **Step 3.2: `native_value`-Logik**

In `PlantSensor.native_value`, vor der `# 1) Zeit-basiert für Wasser`-Zeile:

```python
        # 0) Treatment-Check hat Vorrang
        if has_overdue_treatment(plant.get("treatments") or [], now):
            return STATUS_NEEDS_ATTENTION
```

- [ ] **Step 3.3: Attribute erweitern**

In `extra_state_attributes`, ergänzen:

```python
            "open_treatments_count": len(
                filter_open_treatments(plant.get("treatments") or [])
            ),
            "latest_treatment": (
                (plant.get("treatments") or [])[-1]
                if plant.get("treatments")
                else None
            ),
```

- [ ] **Step 3.4: Compile-Check + Commit**

```bash
python3 -m py_compile custom_components/plant_care/sensor.py
git add custom_components/plant_care/sensor.py
git commit -m "Sensor: needs_attention Status + Treatment-Attribute"
```

---

### Task 4: Services registrieren

**Files:**
- Modify: `custom_components/plant_care/__init__.py`
- Modify: `custom_components/plant_care/services.yaml`
- Modify: `custom_components/plant_care/strings.json` + 2 translations

- [ ] **Step 4.1: Schemas + Handler**

In `__init__.py`:

```python
DIAGNOSE_PLANT_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("photo_path"): cv.string,
        vol.Required("ai_response"): dict,
    }
)

RESOLVE_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("treatment_id"): cv.string,
        vol.Optional("outcome", default="resolved"): vol.In(["resolved", "dismissed"]),
    }
)
```

Handler:

```python
    async def handle_diagnose_plant(call: ServiceCall) -> ServiceResponse:
        return await coord.async_diagnose_plant(
            plant_id=call.data["plant_id"],
            photo_path=call.data["photo_path"],
            ai_response=call.data["ai_response"],
        )

    async def handle_resolve_treatment(call: ServiceCall) -> ServiceResponse:
        result = await coord.async_resolve_treatment(
            plant_id=call.data["plant_id"],
            treatment_id=call.data["treatment_id"],
            outcome=call.data.get("outcome", "resolved"),
        )
        return result
```

Registrierung:

```python
    hass.services.async_register(
        DOMAIN,
        SERVICE_DIAGNOSE_PLANT,
        handle_diagnose_plant,
        schema=DIAGNOSE_PLANT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE_TREATMENT,
        handle_resolve_treatment,
        schema=RESOLVE_TREATMENT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
```

Cleanup-Liste in `async_unload_entry` ergänzen.

- [ ] **Step 4.2: Event-Handler für RESOLVE/DISMISS-Actions**

Im bestehenden `_handle_action_event` erweitern. Nach dem `parse_action_id`-Block:

```python
        # Treatment-Actions (eigenes Format mit treatment_id)
        treatment_parsed = parse_treatment_action_id(raw_id)
        if treatment_parsed is not None:
            t_action, plant_id, treatment_id = treatment_parsed
            async def _dispatch_treatment() -> None:
                try:
                    if t_action == "RESOLVE":
                        await coord.async_resolve_treatment(plant_id, treatment_id, "resolved")
                    elif t_action == "DISMISS":
                        await coord.async_resolve_treatment(plant_id, treatment_id, "dismissed")
                except ValueError:
                    _LOGGER.debug(
                        "Plant Care: Treatment-Action %s für unbekannte ID %s/%s",
                        t_action, plant_id, treatment_id,
                    )
            hass.async_create_task(_dispatch_treatment())
            return
        # … bisheriger Code für WATER/FERTILIZE/SNOOZE
```

Import ergänzen:

```python
from ._utils import parse_action_id, parse_treatment_action_id
```

- [ ] **Step 4.3: services.yaml**

```yaml
diagnose_plant:
  name: Pflanze diagnostizieren
  description: >
    Speichert ein AI-Diagnose-Ergebnis als Treatment-Eintrag. Der
    eigentliche AI-Call (ai_task.generate_data) läuft im Frontend.
  fields:
    plant_id:
      required: true
      selector: { text: }
    photo_path:
      required: true
      selector: { text: }
    ai_response:
      required: true
      selector: { object: }

resolve_treatment:
  name: Behandlung abschließen
  description: Markiert ein offenes Treatment als erledigt oder verworfen.
  fields:
    plant_id:
      required: true
      selector: { text: }
    treatment_id:
      required: true
      selector: { text: }
    outcome:
      selector:
        select:
          options:
            - resolved
            - dismissed
```

- [ ] **Step 4.4: i18n (strings.json + de.json + en.json)**

Analog der vorhandenen Service-Strings ergänzen. Deutsch in
`strings.json` + `de.json`, Englisch in `en.json`.

- [ ] **Step 4.5: Compile + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('OK')" && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/
git commit -m "Services: diagnose_plant + resolve_treatment

Event-Handler routet zusätzlich RESOLVE/DISMISS Mobile-App-Actions
via parse_treatment_action_id (PLANTCARE_RESOLVE_<plant>_<treatment>).
i18n + services.yaml ergänzt.
"
```

---

### Task 5: Frontend – Treatments-Sektion + Diagnose-Flow

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 5.1: Status-Labels erweitern**

Oben in der Datei, im `STATUS_LABEL` und `STATUS_CLASS`:

```javascript
const STATUS_LABEL = {
  ok: "Alles gut",
  needs_water: "Braucht Wasser",
  needs_fertilizer: "Braucht Dünger",
  needs_both: "Wasser + Dünger",
  needs_attention: "🔍 Treatment-Check fällig",
};

const STATUS_CLASS = {
  ok: "ok",
  needs_water: "water",
  needs_fertilizer: "fert",
  needs_both: "both",
  needs_attention: "attention",
};
```

- [ ] **Step 5.2: `_renderTreatments`**

Vor `_renderPhotoHistory`:

```javascript
  _renderTreatments(p) {
    const treatments = Array.isArray(p.treatments) ? p.treatments : [];
    const open = treatments.filter((t) => t.status === "open");
    const closed = treatments.filter((t) => t.status !== "open");
    const aiAvailable = !!this._findAiTaskEntity();

    return `
      <section class="treatments">
        <h3>🔍 Behandlungen</h3>
        <div class="treatment-actions">
          <button
            class="btn ${aiAvailable ? "" : "disabled"}"
            data-action="open-diagnose"
            data-id="${this._escapeAttr(p.plant_id)}"
            ${aiAvailable ? "" : "disabled"}
            title="${aiAvailable ? "" : "AI Task nicht eingerichtet"}"
          >+ Was ist los?</button>
        </div>

        ${open.length === 0 && closed.length === 0 ? `
          <p class="muted small">Noch keine Behandlungen dokumentiert.</p>
        ` : ""}

        ${open.map((t) => this._renderTreatmentCard(p.plant_id, t, false)).join("")}

        ${closed.length > 0 ? `
          <details class="closed-treatments">
            <summary class="muted small">${closed.length} abgeschlossene Behandlung${closed.length === 1 ? "" : "en"}</summary>
            ${closed.map((t) => this._renderTreatmentCard(p.plant_id, t, true)).join("")}
          </details>
        ` : ""}
      </section>
    `;
  }

  _renderTreatmentCard(plantId, t, closed) {
    const dateStr = t.started_at ? this._relativeTime(t.started_at) : "";
    const dueStr = t.follow_up_at && !closed ? this._relativeTime(t.follow_up_at) : "";
    const confidence = typeof t.confidence === "number" ? Math.round(t.confidence * 100) : null;
    return `
      <article class="treatment-card ${closed ? "closed" : "open"}">
        <header>
          <span class="treatment-icon">${closed ? (t.status === "resolved" ? "✓" : "✗") : "⚠"}</span>
          <strong>${this._escape(t.diagnosis)}</strong>
          ${confidence !== null ? `<span class="muted small">(${confidence}% sicher)</span>` : ""}
        </header>
        <p class="muted small">Begonnen: ${this._escape(dateStr)}${dueStr ? ` · Fällig: ${this._escape(dueStr)}` : ""}</p>
        ${Array.isArray(t.treatment_steps) && t.treatment_steps.length > 0 ? `
          <ol class="treatment-steps">
            ${t.treatment_steps.map((s) => `<li>${this._escape(s)}</li>`).join("")}
          </ol>
        ` : ""}
        ${!closed ? `
          <div class="treatment-actions-row">
            <button class="btn primary small" data-action="resolve-treatment" data-id="${this._escapeAttr(plantId)}" data-treatment="${this._escapeAttr(t.id)}">✓ Erledigt</button>
            <button class="btn ghost small" data-action="dismiss-treatment" data-id="${this._escapeAttr(plantId)}" data-treatment="${this._escapeAttr(t.id)}">✗ Verwerfen</button>
          </div>
        ` : ""}
      </article>
    `;
  }
```

- [ ] **Step 5.3: In Detail-View einbinden**

In `_renderDetail`, vor `_renderPhotoHistory(p)`:

```javascript
        ${this._renderTreatments(p)}
```

- [ ] **Step 5.4: Diagnose-Modal**

State:

```javascript
    this._diagnoseModal = null; // { plantId, busy, result?: {...} }
```

Renderer:

```javascript
  _renderDiagnoseModal() {
    if (!this._diagnoseModal) return "";
    const { plantId, busy, result, error } = this._diagnoseModal;
    const plant = this._plantById(plantId);
    if (!plant) return "";

    return `
      <div class="lightbox" data-action="close-diagnose">
        <div class="lightbox-content" data-stop style="max-width:560px">
          <header class="lightbox-header">
            <h3>Diagnose: ${this._escape(plant.name)}</h3>
          </header>
          <div class="lightbox-image" style="padding:16px;background:var(--card-background-color,#fff)">
            ${result ? this._renderDiagnoseResult(plant, result) :
              busy ? `<p>⏳ Foto wird analysiert…</p>` :
              error ? `<p class="error">${this._escape(error)}</p>` :
              `<p class="muted">Bitte ein Foto auswählen.</p>
               <button class="btn primary" data-action="pick-diagnose-photo" data-id="${this._escapeAttr(plantId)}">📷 Foto auswählen</button>
               <input type="file" accept="image/*" id="diagnose-photo-input" style="display:none">`
            }
          </div>
          <footer class="lightbox-footer">
            ${result && result.shouldSave ? `
              <button class="btn primary" data-action="save-diagnose" data-id="${this._escapeAttr(plantId)}">✓ Speichern</button>
            ` : ""}
            <button class="btn ghost" data-action="close-diagnose">Schließen</button>
          </footer>
        </div>
      </div>
    `;
  }

  _renderDiagnoseResult(plant, result) {
    const conf = typeof result.confidence === "number" ? Math.round(result.confidence * 100) : null;
    const healthy = (result.confidence ?? 1) < 0.5 || /keine auffäl/i.test(result.diagnosis || "");
    if (healthy) {
      return `<p style="font-size:1.1rem;color:var(--sage)">✓ Sieht gesund aus!</p>
              <p class="muted">${this._escape(result.diagnosis || "")}</p>`;
    }
    const steps = Array.isArray(result.treatment_steps) ? result.treatment_steps : [];
    return `
      <strong>${this._escape(result.diagnosis || "Diagnose")}</strong>
      ${conf !== null ? `<p class="muted small">Konfidenz: ${conf}%</p>` : ""}
      ${steps.length ? `
        <p style="margin-top:12px"><strong>Empfohlene Schritte:</strong></p>
        <ol>${steps.map((s) => `<li>${this._escape(s)}</li>`).join("")}</ol>
      ` : ""}
      <p class="muted small">Wiedervorlage in ${result.follow_up_days || 7} Tagen.</p>
    `;
  }
```

(`result.shouldSave` wird in `_runDiagnose` gesetzt; siehe nächster Step.)

- [ ] **Step 5.5: Click-Handler**

In `_onClick`, im `switch (action)`-Block:

```javascript
      case "open-diagnose":
        this._diagnoseModal = { plantId: id, busy: false };
        this._setState({});
        break;
      case "close-diagnose":
        if (this._diagnoseModal?.busy) break; // running, don't close
        this._diagnoseModal = null;
        this._setState({});
        break;
      case "pick-diagnose-photo": {
        const input = this.shadowRoot.getElementById("diagnose-photo-input");
        if (input) {
          input.onchange = (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) this._runDiagnose(id, file);
          };
          input.click();
        }
        break;
      }
      case "save-diagnose":
        this._saveDiagnose(id);
        break;
      case "resolve-treatment":
        this._callService("plant_care", "resolve_treatment", {
          plant_id: id,
          treatment_id: target.dataset.treatment,
          outcome: "resolved",
        }).then(() => this._showToast("success", "Behandlung erledigt"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
      case "dismiss-treatment":
        this._callService("plant_care", "resolve_treatment", {
          plant_id: id,
          treatment_id: target.dataset.treatment,
          outcome: "dismissed",
        }).then(() => this._showToast("success", "Behandlung verworfen"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
```

- [ ] **Step 5.6: `_runDiagnose` + `_saveDiagnose`**

Nach `_aiIdentifyFromPhoto`:

```javascript
  async _runDiagnose(plantId, file) {
    if (!file || !file.type.startsWith("image/")) {
      this._showToast("error", "Bitte ein Bild auswählen");
      return;
    }
    const aiEntity = this._findAiTaskEntity();
    if (!aiEntity) {
      this._showToast("error", "AI Task nicht eingerichtet");
      return;
    }
    this._diagnoseModal = { plantId, busy: true };
    this._render();
    try {
      const dataUrl = await this._resizeImage(file);
      const upload = await this._uploadPhotoToBackend(dataUrl);
      const res = await this._callServiceWithResponse(
        "ai_task",
        "generate_data",
        {
          entity_id: aiEntity,
          task_name: "plant_care_diagnose",
          instructions:
            "Du bist erfahrener Botaniker und Pflanzenarzt. Auf dem angehängten Foto " +
            "ist eine Pflanze. Analysiere mögliche Schädlinge, Krankheiten oder " +
            "Pflegefehler. Wenn die Pflanze gesund aussieht: diagnosis='Keine " +
            "Auffälligkeiten erkannt', confidence < 0.5. Antworte ausschließlich " +
            "im vorgegebenen JSON-Schema.",
          attachments: [
            {
              media_content_id: upload.media_content_id,
              media_content_type: upload.media_content_type || "image/jpeg",
            },
          ],
          structure: {
            diagnosis: { selector: { text: { multiline: true } } },
            confidence: { selector: { number: { min: 0, max: 1 } } },
            treatment_steps: { selector: { object: {} } },
            follow_up_days: { selector: { number: { min: 1, max: 30 } } },
            severity: { selector: { select: { options: ["low", "medium", "high"] } } },
          },
        },
      );
      const data = res?.data ?? res?.response?.data ?? res ?? {};
      const healthy = (data.confidence ?? 1) < 0.5 ||
        /keine auffäl/i.test(data.diagnosis || "");
      this._diagnoseModal = {
        plantId,
        busy: false,
        result: { ...data, shouldSave: !healthy, photo_path: upload.path },
      };
    } catch (err) {
      console.error(err);
      this._diagnoseModal = {
        plantId,
        busy: false,
        error: this._fmtErr(err),
      };
    } finally {
      this._render();
    }
  }

  async _saveDiagnose(plantId) {
    const modal = this._diagnoseModal;
    if (!modal?.result?.shouldSave) return;
    try {
      await this._callServiceWithResponse("plant_care", "diagnose_plant", {
        plant_id: plantId,
        photo_path: modal.result.photo_path,
        ai_response: {
          diagnosis: modal.result.diagnosis,
          confidence: modal.result.confidence,
          treatment_steps: modal.result.treatment_steps,
          follow_up_days: modal.result.follow_up_days,
          severity: modal.result.severity,
        },
      });
      this._showToast("success", "Behandlung dokumentiert");
      this._diagnoseModal = null;
      this._setState({});
    } catch (err) {
      this._showToast("error", this._fmtErr(err));
    }
  }
```

- [ ] **Step 5.7: Im `_render` Modal einbinden**

Im finalen `innerHTML`-Template, neben der Lightbox:

```javascript
        ${this._diagnoseModal ? this._renderDiagnoseModal() : ""}
```

Signatur erweitern:

```javascript
      JSON.stringify(this._diagnoseModal || {}),
```

- [ ] **Step 5.8: CSS**

```css
      .status.attention { background: rgba(245, 158, 11, 0.15); color: #b45309; }
      .treatments {
        margin-bottom: 20px;
      }
      .treatments h3 { margin: 0 0 8px; font-size: 1rem; }
      .treatment-card {
        background: rgba(245, 158, 11, 0.08);
        border-left: 3px solid #f59e0b;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
      }
      .treatment-card.closed {
        background: rgba(0,0,0,0.04);
        border-left-color: var(--sage);
        opacity: 0.85;
      }
      .treatment-card header {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 6px;
        flex-wrap: wrap;
      }
      .treatment-icon { font-size: 1.1rem; }
      .treatment-steps { margin: 8px 0; padding-left: 20px; }
      .treatment-steps li { margin: 2px 0; }
      .treatment-actions-row { display: flex; gap: 8px; margin-top: 8px; }
      .closed-treatments { margin-top: 12px; }
      .closed-treatments summary { cursor: pointer; padding: 4px 0; }
```

- [ ] **Step 5.9: Test + Commit**

1. Detail-View → "+ Was ist los?" → File-Picker → Foto auswählen
2. Spinner → Result-View mit Diagnose + Steps
3. "✓ Speichern" → Treatment erscheint in Treatments-Sektion
4. "✓ Erledigt" auf Treatment-Card → status → closed → schiebt in Details-Block

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Treatments-Sektion + Diagnose-Modal + Resolve-Flow

Neue Detail-View-Sektion 'Behandlungen' mit:
- 'Was ist los?'-Button → AI-Diagnose-Modal
- Offene Treatments mit ✓/✗-Buttons
- Eingeklappte Liste der abgeschlossenen Behandlungen
Status needs_attention bekommt orange Badge.
"
```

---

### Task 6: README + finaler Check

**Files:**
- Modify: `README.md`

- [ ] **Step 6.1: README-Sektion**

Nach "Foto-Verlauf":

```markdown
### Pflanzen-Sprechstunde

Sieht eine Pflanze auffällig aus (gelbe Blätter, Schädlinge)? Im
Detail-View **+ Was ist los?** tappen → Foto aufnehmen → die AI
analysiert mögliche Ursachen und schlägt konkrete Behandlungsschritte
vor. Speichern legt eine **Behandlung** mit Foto + Diagnose + Wiedervorlage-Datum an.

Sobald die Wiedervorlage fällig ist, schaltet der Plant-Sensor auf
Status `needs_attention` und Plant Care versendet eine Reminder-
Notification mit den Buttons **✓ Erledigt** / **✗ Verwerfen** /
**💤 Snooze 1d**.

Voraussetzung: AI Task ist konfiguriert (HA 2025.7+).
```

- [ ] **Step 6.2: Final-Check**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

- [ ] **Step 6.3: Commit**

```bash
git add README.md
git commit -m "README: Pflanzen-Sprechstunde Sektion"
```

---

## Self-Review

**Spec coverage:**
- Treatments-Schema → Task 2.3 (Migration) + Task 2.4 (`async_diagnose_plant`)
- AI-Integration mit Schema → Task 5.6 (`_runDiagnose`)
- diagnose_plant Service → Task 4.1
- resolve_treatment Service → Task 4.1
- needs_attention Status → Task 2.6 + Task 3.2
- Reminder mit Resolve/Dismiss-Actions → Task 2.6
- Treatment-Action-Routing → Task 4.2
- Anti-Spam 60s → Task 2.4
- Treatments-Sektion + Diagnose-Modal → Task 5
- README → Task 6.1

**Placeholder scan:** Keine TBDs, alle Code-Blöcke vollständig. ✓

**Type consistency:** `treatments` = `list[dict]` mit konsistentem
Schema. `treatment.id` immer 12-char-hex. `status` enum
`"open"|"resolved"|"dismissed"`. Action-IDs für Treatments folgen
`PLANTCARE_<RESOLVE|DISMISS>_<plant_id>_<treatment_id>` und werden
sowohl in `_build_notification_actions` als auch in
`parse_treatment_action_id` korrekt gebildet/gelesen. ✓
