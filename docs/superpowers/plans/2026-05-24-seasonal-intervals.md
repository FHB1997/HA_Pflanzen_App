# Saison-aware Intervalle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gieß-/Düngeintervalle werden automatisch an die aktuelle Jahreszeit angepasst (opt-in pro Pflanze + globaler Master-Toggle).

**Architecture:** Pure-Helper berechnen Saison + effektive Tage. Sensor liest Basis-Werte aus dem Plant-Dict, wendet Multiplier dynamisch an. Keine Werte werden persistiert – Berechnung bei jedem Read.

**Tech Stack:** Home Assistant Custom Integration, pytest, Vanilla-JS-Web-Component.

**Spec:** [docs/superpowers/specs/2026-05-24-seasonal-intervals-design.md](../specs/2026-05-24-seasonal-intervals-design.md)

---

### Task 1: Pure Helper + Tests

**Files:**
- Modify: `custom_components/plant_care/_utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1.1: Tests schreiben**

In `tests/test_utils.py`, am Ende:

```python
# --------------------------- get_season ---------------------------

def test_get_season_north_spring():
    assert get_season(datetime(2026, 3, 21, tzinfo=timezone.utc)) == "spring"
    assert get_season(datetime(2026, 5, 31, tzinfo=timezone.utc)) == "spring"


def test_get_season_north_summer():
    assert get_season(datetime(2026, 6, 1, tzinfo=timezone.utc)) == "summer"
    assert get_season(datetime(2026, 8, 15, tzinfo=timezone.utc)) == "summer"


def test_get_season_north_autumn():
    assert get_season(datetime(2026, 9, 5, tzinfo=timezone.utc)) == "autumn"
    assert get_season(datetime(2026, 11, 30, tzinfo=timezone.utc)) == "autumn"


def test_get_season_north_winter():
    assert get_season(datetime(2026, 12, 24, tzinfo=timezone.utc)) == "winter"
    assert get_season(datetime(2026, 1, 15, tzinfo=timezone.utc)) == "winter"


def test_get_season_south_summer_in_january():
    assert get_season(datetime(2026, 1, 15, tzinfo=timezone.utc), "south") == "summer"


def test_get_season_south_winter_in_july():
    assert get_season(datetime(2026, 7, 15, tzinfo=timezone.utc), "south") == "winter"


# --------------------------- seasonal_multiplier ---------------------------

def test_seasonal_multiplier_known_values():
    assert seasonal_multiplier("spring", "water") == 1.0
    assert seasonal_multiplier("summer", "water") == 0.85
    assert seasonal_multiplier("autumn", "fertilize") == 1.5
    assert seasonal_multiplier("winter", "fertilize") == 999


def test_seasonal_multiplier_unknown_returns_one():
    assert seasonal_multiplier("invalid", "water") == 1.0
    assert seasonal_multiplier("winter", "bogus") == 1.0


# --------------------------- effective_days ---------------------------

def test_effective_days_inactive_returns_base():
    assert effective_days(7, "winter", "water", seasonal_active=False) == 7


def test_effective_days_active_applies_multiplier():
    # 7 * 1.5 = 10.5 → round → 11
    assert effective_days(7, "winter", "water", seasonal_active=True) == 11


def test_effective_days_winter_fertilize_clamped_to_max():
    # 30 * 999 = riesig → clamp 365
    assert effective_days(30, "winter", "fertilize", seasonal_active=True) == 365


def test_effective_days_clamped_to_min_1():
    # 1 * 0.85 = 0.85 → round → 1 (floor wäre 0, Clamp greift)
    assert effective_days(1, "summer", "water", seasonal_active=True) == 1


def test_effective_days_none_passes_through():
    assert effective_days(None, "summer", "water", seasonal_active=True) is None
```

Import erweitern:

```python
from _utils import (  # type: ignore[import-not-found]
    cap_photos,
    clean_data,
    compute_snooze_last_notified,
    effective_days,
    filter_open_treatments,
    get_season,
    has_overdue_treatment,
    is_in_quiet_hours,
    is_rate_limited,
    migrate_legacy_photo,
    needs_time_based,
    parse_action_id,
    parse_iso,
    parse_time_string,
    parse_treatment_action_id,
    seasonal_multiplier,
    sort_photos,
    try_float,
    utcnow_iso,
)
```

- [ ] **Step 1.2: Tests fail → expected ImportError**

```bash
/tmp/pc-test/bin/python -m pytest tests/ -q | tail -5
```

- [ ] **Step 1.3: Helper implementieren**

In `_utils.py`, am Ende:

```python
_SEASON_MONTHS_NORTH: dict[int, str] = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "spring", 6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
}

_SEASONAL_MULTIPLIERS: dict[str, dict[str, float]] = {
    "spring": {"water": 1.0,  "fertilize": 1.0},
    "summer": {"water": 0.85, "fertilize": 1.0},
    "autumn": {"water": 1.15, "fertilize": 1.5},
    "winter": {"water": 1.5,  "fertilize": 999},
}


def get_season(now: datetime, hemisphere: str = "north") -> str:
    """Liefert die aktuelle Jahreszeit-Konstante als String.

    Args:
        now: Datetime (Timezone ignoriert; nur Monat relevant).
        hemisphere: "north" (Default) oder "south".
    """
    season = _SEASON_MONTHS_NORTH.get(now.month, "spring")
    if hemisphere == "south":
        # Süd: Verschiebung um 6 Monate
        opposite = {"spring": "autumn", "autumn": "spring",
                    "summer": "winter", "winter": "summer"}
        season = opposite.get(season, season)
    return season


def seasonal_multiplier(season: str, kind: str) -> float:
    """Liefert den Multiplier für (season, kind). Unbekannte Werte → 1.0."""
    return _SEASONAL_MULTIPLIERS.get(season, {}).get(kind, 1.0)


def effective_days(
    base_days: int | None,
    season: str | None,
    kind: str,
    seasonal_active: bool,
) -> int | None:
    """Wendet den saisonalen Multiplier auf ``base_days`` an (wenn aktiv).

    Returns:
        Geclampter int in ``[1, 365]``, oder ``None`` wenn ``base_days``
        bereits ``None`` ist.
    """
    if base_days is None:
        return None
    if not seasonal_active or season is None:
        return int(base_days)
    multiplier = seasonal_multiplier(season, kind)
    raw = round(float(base_days) * multiplier)
    return max(1, min(365, raw))
```

- [ ] **Step 1.4: Tests grün**

```bash
/tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

- [ ] **Step 1.5: Commit**

```bash
git add custom_components/plant_care/_utils.py tests/test_utils.py
git commit -m "Add saisonale Helper: get_season, seasonal_multiplier, effective_days

Standard-Multiplier-Tabelle für Nordhalbkugel (mit Süd-Spiegelung).
Winter-Dünger = 999 (effektiv aus), Sommer-Wasser = 0.85 (öfter).
effective_days clampt auf [1, 365] und lässt None durch.
"
```

---

### Task 2: Konstanten + OptionsFlow

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/config_flow.py`
- Modify: `custom_components/plant_care/strings.json` + 2 translations

- [ ] **Step 2.1: Konstanten**

In `const.py`:

```python
# Saisonale Anpassung
CONF_SEASONAL_ENABLED: Final = "seasonal_enabled"
CONF_HEMISPHERE: Final = "hemisphere"
DEFAULT_HEMISPHERE: Final = "north"
```

- [ ] **Step 2.2: OptionsFlow erweitern**

In `config_flow.py`, im `PlantCareOptionsFlow.async_step_init`, am Ende
des `vol.Schema(...)`-Aufrufs zwei Felder ergänzen:

```python
                vol.Optional(
                    CONF_SEASONAL_ENABLED,
                    default=opts.get(CONF_SEASONAL_ENABLED, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_HEMISPHERE,
                    default=opts.get(CONF_HEMISPHERE, DEFAULT_HEMISPHERE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="north", label="Nordhalbkugel"),
                            selector.SelectOptionDict(value="south", label="Südhalbkugel"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
```

Imports:

```python
from .const import (
    ...
    CONF_HEMISPHERE,
    CONF_SEASONAL_ENABLED,
    DEFAULT_HEMISPHERE,
    ...
)
```

- [ ] **Step 2.3: i18n**

In `strings.json`, `translations/de.json`, `translations/en.json`, im
`options.step.init.data`-Block:

```json
"seasonal_enabled": "Saisonale Anpassung aktivieren",
"hemisphere": "Hemisphäre"
```

(EN: "Enable seasonal adjustment" / "Hemisphere")

- [ ] **Step 2.4: Compile + JSON-Check + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('OK')"
```

```bash
git add custom_components/plant_care/const.py custom_components/plant_care/config_flow.py custom_components/plant_care/strings.json custom_components/plant_care/translations/
git commit -m "OptionsFlow: seasonal_enabled + hemisphere

Globaler Master-Toggle für saisonale Anpassung und Hemisphäre-Auswahl
(Nord/Süd). Wirkt nur in Kombination mit plant.seasonal_adjust=True.
"
```

---

### Task 3: Coordinator Migration + Plant-Schema

**Files:**
- Modify: `custom_components/plant_care/coordinator.py`
- Modify: `custom_components/plant_care/__init__.py`
- Modify: `custom_components/plant_care/services.yaml`

- [ ] **Step 3.1: Migration in async_load**

In `coordinator.py`, in `async_load` Schleife:

```python
            plant.setdefault("seasonal_adjust", False)
```

- [ ] **Step 3.2: Im add_plant das Feld initialisieren**

In `async_add_plant`, im `plant: dict[str, Any] = {...}` ergänzen:

```python
            "seasonal_adjust": bool(cleaned.get("seasonal_adjust", False)),
```

- [ ] **Step 3.3: Service-Schemas erweitern**

In `__init__.py`, `ADD_PLANT_SCHEMA` und `UPDATE_PLANT_SCHEMA` je ein Feld:

```python
        vol.Optional("seasonal_adjust"): cv.boolean,
```

(Bei `UPDATE_PLANT_SCHEMA` ohne `default` und ohne `vol.Required`.)

- [ ] **Step 3.4: services.yaml ergänzen**

In `add_plant` und `update_plant`, im `fields:`-Block:

```yaml
    seasonal_adjust:
      name: Saisonal anpassen
      description: Aktiviert saisonale Multiplier für die Intervalle (nur wirksam wenn global aktiviert).
      default: false
      selector:
        boolean:
```

- [ ] **Step 3.5: Compile + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/coordinator.py custom_components/plant_care/__init__.py custom_components/plant_care/services.yaml
git commit -m "Plant-Schema: seasonal_adjust (opt-in pro Pflanze)

Migration setzt Default False für bestehende Pflanzen. Schema in
add_plant/update_plant erlaubt den Toggle via Service-Call und
Frontend-Form.
"
```

---

### Task 4: Sensor saisonal-aware

**Files:**
- Modify: `custom_components/plant_care/sensor.py`

- [ ] **Step 4.1: Imports**

```python
from ._utils import (
    effective_days,
    filter_open_treatments,
    get_season,
    has_overdue_treatment,
    needs_time_based,
    try_float,
)
```

```python
from .const import (
    CONF_HEMISPHERE,
    CONF_SEASONAL_ENABLED,
    DEFAULT_HEMISPHERE,
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

- [ ] **Step 4.2: Helper für effektive Werte**

In `PlantSensor` direkt vor `native_value` einfügen:

```python
    def _effective_intervals(self, plant: dict[str, Any], now: datetime) -> tuple[int | None, int | None]:
        """Liefert (effective_water_days, effective_fertilize_days).

        Berücksichtigt globalen Master-Toggle + per-Plant ``seasonal_adjust``.
        """
        entry = getattr(self._coord, "_entry", None)
        options = entry.options if entry is not None else {}
        global_enabled = bool(options.get(CONF_SEASONAL_ENABLED, False))
        hemisphere = options.get(CONF_HEMISPHERE, DEFAULT_HEMISPHERE)
        active = global_enabled and bool(plant.get("seasonal_adjust", False))
        season = get_season(now, hemisphere) if active else None
        eff_water = effective_days(plant.get("water_days"), season, "water", active)
        eff_fert = effective_days(plant.get("fertilize_days"), season, "fertilize", active)
        return eff_water, eff_fert
```

- [ ] **Step 4.3: `native_value` umstellen**

In `native_value`, die `needs_time_based`-Calls anpassen. Vorher:

```python
        needs_water = needs_time_based(
            plant.get("last_watered"), plant.get("water_days"), now
        )
        ...
        needs_fertilizer = needs_time_based(
            plant.get("last_fertilized"), plant.get("fertilize_days"), now
        )
```

Ersetzen durch:

```python
        eff_water, eff_fert = self._effective_intervals(plant, now)
        needs_water = needs_time_based(plant.get("last_watered"), eff_water, now)
        ...
        needs_fertilizer = needs_time_based(plant.get("last_fertilized"), eff_fert, now)
```

- [ ] **Step 4.4: Attribute erweitern**

In `extra_state_attributes`:

```python
        eff_water, eff_fert = self._effective_intervals(plant, datetime.now(timezone.utc))
        ...
        return {
            ...
            "water_days_effective": eff_water,
            "fertilize_days_effective": eff_fert,
            "seasonal_adjust": plant.get("seasonal_adjust", False),
        }
```

- [ ] **Step 4.5: Compile + Tests + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/sensor.py
git commit -m "Sensor: saisonale effective_days bei Status-Berechnung

Nutzt _effective_intervals zur Berechnung, ersetzt water_days/
fertilize_days durch effektive Werte in needs_time_based.
Neue Attribute: water_days_effective, fertilize_days_effective,
seasonal_adjust.
"
```

---

### Task 5: Frontend – Toggle im Form + Anzeige im Detail-View

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 5.1: Form-Field hinzufügen**

In `_renderForm`, nach dem `moisture_sensor`-Field im `form-grid`:

```javascript
          <label class="field field-checkbox">
            <input
              type="checkbox"
              name="seasonal_adjust"
              ${draft.seasonal_adjust ? "checked" : ""}
            >
            <span>🌗 Saisonal anpassen (Winter/Sommer-Intervalle)</span>
          </label>
```

CSS für `.field-checkbox`:

```css
      .field-checkbox {
        flex-direction: row;
        align-items: center;
        gap: 8px;
      }
      .field-checkbox input { width: 18px; height: 18px; accent-color: var(--sage); }
```

- [ ] **Step 5.2: Submit-Path: Checkbox als Boolean**

In `_onSubmit`, nach dem Numerik-Cast-Block, vor dem Photo-Block:

```javascript
    // Checkbox-Felder explizit casten (FormData liefert "on" oder fehlt).
    data.seasonal_adjust = formData.has("seasonal_adjust");
```

- [ ] **Step 5.3: Detail-View Effektive Intervalle anzeigen**

In `_renderDetail`, in der `action-card`-Sektion "💧 Gießen", die
"Intervall"-Zeile ergänzen:

```javascript
            <p class="muted small">Intervall: alle ${this._escape(p.water_days)} Tage${
              p.water_days_effective && p.water_days_effective !== p.water_days
                ? ` (saisonal: ${p.water_days_effective})`
                : ""
            }</p>
```

Analog für die "🌱 Düngen"-Card mit `p.fertilize_days_effective`.

- [ ] **Step 5.4: Browser-Test + Commit**

1. Pflanze editieren → "🌗 Saisonal anpassen" anhaken → speichern
2. OptionsFlow: "Saisonale Anpassung aktivieren" + Hemisphäre wählen
3. Detail-View zeigt z.B. "alle 7 Tage (saisonal: 11)" im Winter
4. Globaler Toggle aus → Klammer-Hinweis verschwindet

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Saisonal-Toggle im Form + Effektivwerte im Detail

Checkbox '🌗 Saisonal anpassen' im Add/Edit-Form. Detail-View zeigt
'alle X Tage (saisonal: Y)' wenn der Multiplier abweicht.
"
```

---

### Task 6: README + finaler Check

**Files:**
- Modify: `README.md`

- [ ] **Step 6.1: README-Sektion**

Nach "Pflanzen-Sprechstunde":

```markdown
### Saisonale Intervalle

Die Pflege ändert sich übers Jahr: im Winter wird seltener gegossen,
gar nicht gedüngt, im Sommer öfter. Plant Care kann die Basis-
Intervalle automatisch saisonal anpassen.

**Aktivieren in zwei Schritten:**

1. **Master-Toggle:** Einstellungen → Geräte & Dienste → Plant Care →
   ⚙ Konfigurieren → "Saisonale Anpassung aktivieren". Hemisphäre
   (Nord/Süd) wählen.
2. **Pro Pflanze:** Im Edit-Form **🌗 Saisonal anpassen** aktivieren.

Default ist OFF, damit du nicht überrumpelt wirst. Die effektiven
Intervalle siehst du im Detail-View in Klammern: `alle 7 Tage (saisonal: 11)`.

**Standard-Multiplier** (nicht konfigurierbar in dieser Version):

| Saison | Wasser | Dünger |
|---|---|---|
| Frühling | 1.0× | 1.0× |
| Sommer | 0.85× (öfter) | 1.0× |
| Herbst | 1.15× | 1.5× (seltener) |
| Winter | 1.5× | aus |
```

- [ ] **Step 6.2: Final-Check**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3 && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('OK')"
```

Expected: alle Tests grün, alle JSON-Files valid.

- [ ] **Step 6.3: Commit**

```bash
git add README.md
git commit -m "README: Saisonale Intervalle Sektion"
```

---

## Self-Review

**Spec coverage:**
- get_season Helper → Task 1.3
- seasonal_multiplier Tabelle → Task 1.3
- effective_days Clamping → Task 1.3
- Globaler Master-Toggle + Hemisphäre im OptionsFlow → Task 2.2
- seasonal_adjust pro Pflanze (Migration + Schema) → Task 3.1 + 3.3
- Sensor nutzt effektive Werte → Task 4.3
- Sensor-Attribute zeigen Effektivwerte → Task 4.4
- Frontend-Checkbox im Form → Task 5.1
- Detail-View Anzeige → Task 5.3
- i18n für die zwei neuen Optionen → Task 2.3
- README → Task 6.1

**Placeholder scan:** Alle Code-Blöcke vollständig. ✓

**Type consistency:** `effective_days` returnt `int | None`,
`needs_time_based` akzeptiert `int | None` (war schon so). `get_season`
returnt String, wird durchgehend mit `"spring"/"summer"/"autumn"/"winter"`
verglichen. `_effective_intervals` returnt `tuple[int|None, int|None]`,
konsistent verwendet in `native_value` und `extra_state_attributes`. ✓
