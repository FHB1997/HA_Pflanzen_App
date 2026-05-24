# Actionable Push-Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HA-Mobile-App-Reminder bekommen Buttons (💧 Gegossen / 🌱 Gedüngt / 💤 Snooze 1d), die der User direkt aus der Notification heraus tappen kann.

**Architecture:** Reminder-Engine erweitert den `notify`-Service-Call um einen `data.actions`-Block, wenn der Ziel-Service mit `notify.mobile_app_` beginnt. Ein HA-Event-Bus-Listener fängt `mobile_app_notification_action`-Events ab und dispatcht zu den passenden Coordinator-Methoden (`async_water_plant` / `async_fertilize_plant` / `async_snooze_plant`). Snooze setzt `last_notified` in die Zukunft so dass der bestehende Rate-Limit-Mechanismus die nächste Notification um mindestens 24 h verzögert.

**Tech Stack:** Home Assistant Custom Integration (Python 3.11+), pytest, HA Event Bus, HA Mobile App `actions[]`-Payload-Format.

**Spec:** [docs/superpowers/specs/2026-05-24-actionable-notifications-design.md](../specs/2026-05-24-actionable-notifications-design.md)

---

### Task 1: Pure Helper in `_utils.py` (TDD)

**Files:**
- Modify: `custom_components/plant_care/_utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1.1: Failing Tests für `parse_action_id` schreiben**

Hänge an `tests/test_utils.py` an (nach den `is_rate_limited`-Tests, vor `utcnow_iso`):

```python
# --------------------------- parse_action_id ---------------------------

def test_parse_action_id_water():
    assert parse_action_id("PLANTCARE_WATER_abc123") == ("WATER", "abc123")


def test_parse_action_id_fertilize():
    assert parse_action_id("PLANTCARE_FERTILIZE_xy9") == ("FERTILIZE", "xy9")


def test_parse_action_id_snooze():
    assert parse_action_id("PLANTCARE_SNOOZE_abc") == ("SNOOZE", "abc")


def test_parse_action_id_unknown_action_passes_through():
    # Parser ist tolerant – Dispatcher filtert.
    assert parse_action_id("PLANTCARE_FOO_abc") == ("FOO", "abc")


def test_parse_action_id_wrong_prefix_returns_none():
    assert parse_action_id("OTHER_WATER_abc") is None


def test_parse_action_id_too_few_segments_returns_none():
    assert parse_action_id("PLANTCARE_WATER") is None
    assert parse_action_id("PLANTCARE") is None
    assert parse_action_id("") is None


def test_parse_action_id_plant_id_with_underscore():
    # plant_id kann theoretisch Underscores haben → splitten nach max 3 Teilen.
    assert parse_action_id("PLANTCARE_WATER_ab_cd") == ("WATER", "ab_cd")
```

Ergänze die Import-Liste oben in der Datei:

```python
from _utils import (  # type: ignore[import-not-found]
    clean_data,
    compute_snooze_last_notified,
    is_in_quiet_hours,
    is_rate_limited,
    needs_time_based,
    parse_action_id,
    parse_iso,
    parse_time_string,
    try_float,
    utcnow_iso,
)
```

- [ ] **Step 1.2: Failing Tests für `compute_snooze_last_notified` schreiben**

Hänge direkt nach den `parse_action_id`-Tests an:

```python
# --------------------------- compute_snooze_last_notified ---------------------------

def test_compute_snooze_no_rate_limit():
    # Kein Rate-Limit → last_notified muss snooze_hours in die Zukunft.
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=0)
    assert result == NOW + timedelta(hours=24)


def test_compute_snooze_with_smaller_rate_limit():
    # rate_limit=12h, snooze=24h → last_notified=now+12h
    # so dass Rate-Limit-Check bei now+24h gerade nicht mehr greift.
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=12)
    assert result == NOW + timedelta(hours=12)


def test_compute_snooze_with_equal_rate_limit():
    # rate_limit=24h, snooze=24h → last_notified=now
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=24)
    assert result == NOW


def test_compute_snooze_with_larger_rate_limit():
    # rate_limit=48h überschreibt snooze=24h → last_notified=now (clamped)
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=48)
    assert result == NOW


def test_compute_snooze_negative_rate_limit_treated_as_zero():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=-5)
    assert result == NOW + timedelta(hours=24)
```

- [ ] **Step 1.3: Tests ausführen → Fail**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -v 2>&1 | tail -20`
Expected: ImportError für `parse_action_id` und `compute_snooze_last_notified` aus `_utils`.

- [ ] **Step 1.4: Implementierung in `_utils.py`**

Hänge ans Ende von `custom_components/plant_care/_utils.py` an:

```python
def parse_action_id(action_id: str) -> tuple[str, str] | None:
    """Zerlegt ``PLANTCARE_<ACTION>_<plant_id>`` → ``(action, plant_id)``.

    Tolerant gegenüber unbekannten Actions – der Dispatcher entscheidet,
    welche Actions er kennt. Rückgabe ``None`` nur bei Prefix-Mismatch oder
    fehlenden Segmenten.
    """
    if not action_id:
        return None
    parts = action_id.split("_", 2)
    if len(parts) < 3 or parts[0] != "PLANTCARE":
        return None
    return (parts[1], parts[2])


def compute_snooze_last_notified(
    now: datetime, snooze_hours: int, rate_limit_hours: int
) -> datetime:
    """Berechnet den ``last_notified``-Zeitstempel für einen Snooze.

    Strategie: das bestehende Rate-Limit (in ``rate_limit_hours``) abzüglich
    der gewünschten Snooze-Dauer in die Zukunft verschieben. Wenn das
    Rate-Limit größer ist als der Snooze-Wunsch, hat der User-Wunsch keinen
    sichtbaren Effekt – sein Rate-Limit greift länger.
    """
    rate_h = max(0, rate_limit_hours)
    offset_hours = max(0, snooze_hours - rate_h)
    return now + timedelta(hours=offset_hours)
```

- [ ] **Step 1.5: Tests ausführen → Pass**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -v 2>&1 | tail -20`
Expected: alle Tests grün (28 alte + 12 neue = 40).

- [ ] **Step 1.6: Commit**

```bash
git add custom_components/plant_care/_utils.py tests/test_utils.py
git commit -m "Add parse_action_id + compute_snooze_last_notified Helper

Pure Funktionen für die Actionable-Notification-Pipeline:
- parse_action_id zerlegt PLANTCARE_<ACTION>_<plant_id>
- compute_snooze_last_notified berechnet den last_notified-Wert,
  damit der bestehende Rate-Limit-Mechanismus die nächste Reminder
  um mindestens snooze_hours verzögert
"
```

---

### Task 2: Coordinator: `async_snooze_plant` + `bind_entry` + last_notified-Reset

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/coordinator.py`

- [ ] **Step 2.1: Konstanten ergänzen**

In `custom_components/plant_care/const.py`, nach den Service-Namen:

```python
# Actionable Notifications
ACTION_ID_PREFIX: Final = "PLANTCARE"
SNOOZE_DEFAULT_HOURS: Final = 24
```

- [ ] **Step 2.2: Coordinator – Entry-Binding und Snooze-Methode**

In `custom_components/plant_care/coordinator.py`:

(a) Imports erweitern (oben in der Datei). Füge `compute_snooze_last_notified` und `timedelta`, `SNOOZE_DEFAULT_HOURS` hinzu:

```python
from datetime import datetime, timedelta, timezone
```

```python
from ._utils import (
    clean_data,
    compute_snooze_last_notified,
    is_in_quiet_hours,
    is_rate_limited,
    parse_time_string,
    utcnow_iso,
)
```

```python
from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TITLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RATE_LIMIT_HOURS,
    CONF_REMINDERS_ENABLED,
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_NOTIFY_TITLE,
    DEFAULT_WATER_DAYS,
    DOMAIN,
    HISTORY_MAX_ENTRIES,
    PHOTOS_URL_PATH,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    SNOOZE_DEFAULT_HOURS,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
    STORAGE_KEY,
    STORAGE_VERSION,
)
```

(b) Im `__init__` der `PlantCareCoordinator`-Klasse `_entry` als Optional initialisieren:

```python
def __init__(self, hass: HomeAssistant) -> None:
    self.hass = hass
    self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    self._plants: dict[str, dict[str, Any]] = {}
    self._entry: Any = None  # ConfigEntry, lazy bound from __init__.py
```

(c) `bind_entry` direkt nach `__init__`:

```python
def bind_entry(self, entry: Any) -> None:
    """Speichert die ConfigEntry-Referenz für Options-Zugriff.

    Wird vom Integration-Setup aufgerufen. Erlaubt dem Coordinator,
    Options (Rate-Limit etc.) zu lesen, ohne dass jeder Aufruf die
    Werte als Argument durchschleifen muss.
    """
    self._entry = entry
```

(d) `async_water_plant` und `async_fertilize_plant` so anpassen, dass sie `last_notified` zurücksetzen. Vorher:

```python
async def async_water_plant(
    self, plant_id: str, timestamp: datetime | None = None
) -> None:
    """Markiert eine Pflanze als gegossen."""
    if plant_id not in self._plants:
        raise ValueError(f"Pflanze {plant_id} nicht gefunden")
    ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    plant = self._plants[plant_id]
    plant["last_watered"] = ts
    history = plant.setdefault("water_history", [])
    history.insert(0, ts)
    plant["water_history"] = history[:HISTORY_MAX_ENTRIES]
    await self._async_save_now()
    async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
    _LOGGER.debug("Plant Care: Pflanze %s gegossen (%s)", plant_id, ts)
```

Ersetzen durch:

```python
async def async_water_plant(
    self, plant_id: str, timestamp: datetime | None = None
) -> None:
    """Markiert eine Pflanze als gegossen.

    Setzt zusätzlich ``last_notified`` zurück, damit ein zwischenzeitlicher
    Snooze nicht den nächsten regulären Reminder unnötig blockiert.
    """
    if plant_id not in self._plants:
        raise ValueError(f"Pflanze {plant_id} nicht gefunden")
    ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    plant = self._plants[plant_id]
    plant["last_watered"] = ts
    plant["last_notified"] = None
    history = plant.setdefault("water_history", [])
    history.insert(0, ts)
    plant["water_history"] = history[:HISTORY_MAX_ENTRIES]
    await self._async_save_now()
    async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
    _LOGGER.debug("Plant Care: Pflanze %s gegossen (%s)", plant_id, ts)
```

Analog `async_fertilize_plant` – ergänze die Zeile `plant["last_notified"] = None` und passe den Docstring an.

(e) Neue Methode `async_snooze_plant` direkt nach `async_fertilize_plant`:

```python
async def async_snooze_plant(
    self, plant_id: str, hours: int = SNOOZE_DEFAULT_HOURS
) -> None:
    """Verzögert die nächste Reminder-Notification für ``plant_id`` um
    mindestens ``hours`` Stunden (Rate-Limit-Reset-Variante).

    Der Pflanzen-Status (z.B. ``needs_water``) bleibt unverändert. Nur die
    Notification wird unterdrückt.
    """
    if plant_id not in self._plants:
        raise ValueError(f"Pflanze {plant_id} nicht gefunden")
    rate_limit_hours = 0
    if self._entry is not None:
        rate_limit_hours = int(
            self._entry.options.get(CONF_RATE_LIMIT_HOURS) or 0
        )
    new_last_notified = compute_snooze_last_notified(
        now=datetime.now(timezone.utc),
        snooze_hours=hours,
        rate_limit_hours=rate_limit_hours,
    )
    self._plants[plant_id]["last_notified"] = new_last_notified.isoformat()
    await self._async_save_now()
    _LOGGER.info(
        "Plant Care: Pflanze %s für %d h gesnoozed (bis %s)",
        plant_id,
        hours,
        new_last_notified.isoformat(),
    )
```

- [ ] **Step 2.3: Sanity-Check Kompilieren**

Run: `python3 -m py_compile custom_components/plant_care/*.py && echo OK`
Expected: `OK`.

- [ ] **Step 2.4: Tests laufen lassen → bestehende grün**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: 40 passed (12 neue + 28 alte; nichts dazugekommen, nichts gebrochen).

- [ ] **Step 2.5: Commit**

```bash
git add custom_components/plant_care/const.py custom_components/plant_care/coordinator.py
git commit -m "Coordinator: async_snooze_plant, bind_entry, last_notified-Reset

- bind_entry(entry) erlaubt dem Coordinator Zugriff auf entry.options
  ohne Argument-Durchschleifen
- async_snooze_plant nutzt compute_snooze_last_notified und das
  bestehende Rate-Limit-Feld als Snooze-Mechanismus (User-bestätigte
  simple Variante, kein separates snooze_until-Feld)
- async_water_plant / async_fertilize_plant setzen last_notified=None,
  damit ein zwischenzeitlicher Snooze die nächste Pflege-Reminder
  nicht unnötig blockiert
"
```

---

### Task 3: Reminder-Engine: Mobile-App-Payload mit Actions

**Files:**
- Modify: `custom_components/plant_care/coordinator.py`

- [ ] **Step 3.1: Helper-Funktion für Action-Block schreiben**

Am Dateiende von `custom_components/plant_care/coordinator.py`, nach `_build_reminder_message`:

```python
def _build_notification_actions(
    plant_id: str, status: str
) -> list[dict[str, str]]:
    """Action-Buttons für die HA-Mobile-App-Notification.

    Welche Buttons gezeigt werden, hängt vom Status ab. ``snooze`` ist
    immer dabei, ``water`` / ``fertilize`` je nach Bedarf.
    """
    actions: list[dict[str, str]] = []
    if status in (STATUS_NEEDS_WATER, STATUS_NEEDS_BOTH):
        actions.append(
            {"action": f"PLANTCARE_WATER_{plant_id}", "title": "💧 Gegossen"}
        )
    if status in (STATUS_NEEDS_FERTILIZER, STATUS_NEEDS_BOTH):
        actions.append(
            {
                "action": f"PLANTCARE_FERTILIZE_{plant_id}",
                "title": "🌱 Gedüngt",
            }
        )
    actions.append(
        {"action": f"PLANTCARE_SNOOZE_{plant_id}", "title": "💤 Snooze 1d"}
    )
    return actions


def _is_mobile_app_service(notify_service: str) -> bool:
    """``True`` wenn der Service-Name ein HA-Mobile-App-Target ist."""
    return notify_service.startswith("mobile_app_")
```

- [ ] **Step 3.2: `evaluate_reminders` erweitern**

In `evaluate_reminders`, finde den Block, der den `notify`-Service-Call vorbereitet. Vorher:

```python
            message = _build_reminder_message(name, state.state)

            try:
                await self.hass.services.async_call(
                    notify_domain,
                    notify_service,
                    {"title": title, "message": message},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001 – pro Pflanze isolieren
                _LOGGER.warning(
                    "Plant Care: notify %s.%s fehlgeschlagen: %s",
                    notify_domain,
                    notify_service,
                    err,
                )
                continue
```

Ersetzen durch:

```python
            message = _build_reminder_message(name, state.state)
            payload: dict[str, Any] = {"title": title, "message": message}

            if _is_mobile_app_service(notify_service):
                payload["data"] = {
                    "actions": _build_notification_actions(plant_id, state.state),
                    "tag": f"plant_care_{plant_id}",
                    "group": "plant_care",
                }

            try:
                await self.hass.services.async_call(
                    notify_domain,
                    notify_service,
                    payload,
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001 – pro Pflanze isolieren
                _LOGGER.warning(
                    "Plant Care: notify %s.%s fehlgeschlagen: %s",
                    notify_domain,
                    notify_service,
                    err,
                )
                continue
```

- [ ] **Step 3.3: Sanity-Check Kompilieren**

Run: `python3 -m py_compile custom_components/plant_care/coordinator.py && echo OK`
Expected: `OK`.

- [ ] **Step 3.4: Tests laufen lassen**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: 40 passed.

- [ ] **Step 3.5: Commit**

```bash
git add custom_components/plant_care/coordinator.py
git commit -m "Reminder-Engine: actions-Block für HA-Mobile-App anhängen

evaluate_reminders erkennt mobile_app_*-Notify-Services per Prefix
und ergänzt data.actions / tag / group. Andere Notify-Services
(Telegram, Persistent etc.) bekommen den unveränderten Plain-Call.

Buttons je nach Status:
- needs_water:       💧 Gegossen + 💤 Snooze 1d
- needs_fertilizer:  🌱 Gedüngt + 💤 Snooze 1d
- needs_both:        💧 Gegossen + 🌱 Gedüngt + 💤 Snooze 1d
"
```

---

### Task 4: Event-Listener für `mobile_app_notification_action`

**Files:**
- Modify: `custom_components/plant_care/__init__.py`

- [ ] **Step 4.1: Imports erweitern**

In `custom_components/plant_care/__init__.py`, in der Import-Sektion:

```python
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
```

```python
from ._utils import parse_action_id
```

- [ ] **Step 4.2: `bind_entry`-Aufruf + Listener registrieren**

In `async_setup_entry`, direkt **nach** dem Block, der den `_reminder_tick`-Timer registriert (vor `_register_services(...)`):

```python
    coord.bind_entry(entry)

    @callback
    def _handle_action_event(event: Event) -> None:
        raw_id = event.data.get("action", "")
        parsed = parse_action_id(raw_id)
        if parsed is None:
            return  # Event von anderer Integration – ignorieren
        action, plant_id = parsed

        async def _dispatch() -> None:
            try:
                if action == "WATER":
                    await coord.async_water_plant(plant_id)
                elif action == "FERTILIZE":
                    await coord.async_fertilize_plant(plant_id)
                elif action == "SNOOZE":
                    await coord.async_snooze_plant(plant_id)
                else:
                    _LOGGER.debug(
                        "Plant Care: unbekannte Action ignoriert: %s", action
                    )
                    return
            except ValueError:
                _LOGGER.debug(
                    "Plant Care: Action %s für unbekannte Pflanze %s",
                    action,
                    plant_id,
                )

        hass.async_create_task(_dispatch())

    unsub_action_listener = hass.bus.async_listen(
        "mobile_app_notification_action", _handle_action_event
    )
    hass.data[DOMAIN]["unsub_action_listener"] = unsub_action_listener
```

- [ ] **Step 4.3: Listener im Unload deregistrieren**

In `async_unload_entry`, **nach** dem `cancel_tick`-Block:

```python
    unsub_action = hass.data.get(DOMAIN, {}).get("unsub_action_listener")
    if unsub_action is not None:
        unsub_action()
```

- [ ] **Step 4.4: Sanity-Check Kompilieren**

Run: `python3 -m py_compile custom_components/plant_care/*.py && echo OK`
Expected: `OK`.

- [ ] **Step 4.5: Tests laufen lassen**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: 40 passed.

- [ ] **Step 4.6: Commit**

```bash
git add custom_components/plant_care/__init__.py
git commit -m "Event-Listener für mobile_app_notification_action

Plant Care abonniert den HA-Event-Bus nach Mobile-App-Action-Events,
parst die Action-ID via parse_action_id und dispatcht zu den
Coordinator-Methoden:
- WATER → async_water_plant
- FERTILIZE → async_fertilize_plant
- SNOOZE → async_snooze_plant

Unbekannte/fremde Action-IDs werden silent ignoriert (Event-Bus ist
HA-weit). ValueErrors für gelöschte Plant-IDs werden geloggt aber
nicht propagiert.

Cleanup im async_unload_entry.
"
```

---

### Task 5: README + Manual-Test-Verifikation

**Files:**
- Modify: `README.md`

- [ ] **Step 5.1: README-Sektion ergänzen**

In `README.md`, im Abschnitt "Variante A (empfohlen): Integrierte Erinnerungen über Options", **vor** der Zeile "Manuelle Auslösung jederzeit über den Service ..." einfügen:

```markdown
### Actionable Notifications (HA-Mobile-App)

Wenn dein `notify_service` ein HA-Mobile-App-Target ist (Pattern
`notify.mobile_app_*`), bekommt jede Reminder-Notification Action-Buttons
direkt im Notification-Center:

- **💧 Gegossen** → markiert die Pflanze als gegossen, ohne in HA zu wechseln
- **🌱 Gedüngt** → analog für Dünger (nur wenn fällig)
- **💤 Snooze 1d** → verzögert die nächste Notification um mindestens 24 h.
  Der Pflanzen-Status im Panel bleibt unverändert (rot); nur die Notification
  wird unterdrückt.

Andere Notify-Services (Telegram, Persistent Notification, …) bekommen die
Notification ohne Buttons – Plant Care fällt automatisch auf Plain-Notify
zurück.
```

- [ ] **Step 5.2: Final-Sanity-Check (gesamt)**

Run: `python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: `py_compile OK` + `40 passed`.

- [ ] **Step 5.3: Commit**

```bash
git add README.md
git commit -m "README: Actionable-Notifications-Sektion"
```

- [ ] **Step 5.4: Manuelle Verifikation in HA (kein Code, nur Checkliste)**

Diese Schritte führt der User in seiner HA-Instanz aus:

1. **Reload Integration**: Einstellungen → Geräte & Dienste → Plant Care → ⋮ → Neu laden
2. **Options prüfen**: `notify_service` muss auf `notify.mobile_app_<dein_device>` zeigen, Reminder aktiviert
3. **Force-Trigger**:
   ```yaml
   service: plant_care.send_reminders
   data:
     force: true
   ```
4. **Erwartet**: Notification auf dem Handy mit Buttons (💧/🌱/💤)
5. **Tap-Test**: 💧 antippen → in HA prüfen ob `last_watered` der Pflanze auf jetzt steht (Sensor-Attribute oder Panel-Detail)
6. **Snooze-Test**: 💤 antippen → in HA-Log nach `gesnoozed (bis ...)` suchen; nächster `send_reminders force:false`-Call darf für diese Pflanze nichts senden

---

## Self-Review

**Spec coverage:**
- Action-Set (WATER/FERTILIZE/SNOOZE) → Task 3.1 (`_build_notification_actions`)
- Notification-Payload (tag/group/actions) → Task 3.2
- Auto-Detection mobile_app_ → Task 3.2 (`_is_mobile_app_service`)
- Action-Routing per Event-Listener → Task 4.2
- Action-ID-Parsing → Task 1.4 (`parse_action_id`)
- Snooze-Mechanik (Rate-Limit-Reset) → Task 2.2 (`async_snooze_plant`) + Task 1.4 (`compute_snooze_last_notified`)
- Coordinator-Zugriff auf entry.options → Task 2.2 (`bind_entry`)
- Reset von last_notified bei manueller Pflege → Task 2.2 (Edit von `async_water_plant`/`async_fertilize_plant`)
- Tests für die zwei neuen Helper → Task 1.1 + 1.2
- README-Update → Task 5.1

**Placeholder scan:** Keine TBDs, keine vagen "add error handling", alle Code-Blöcke vollständig. ✓

**Type consistency:** `parse_action_id` gibt `tuple[str, str] | None`, wird in Task 4.2 als `parsed = parse_action_id(...)` mit `if parsed is None: return` und `action, plant_id = parsed` unpacked. ✓ `compute_snooze_last_notified` gibt `datetime`, wird in `async_snooze_plant` mit `.isoformat()` zu str konvertiert für Storage. ✓
