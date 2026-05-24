# Actionable Push-Notifications — Design

**Status:** Approved
**Date:** 2026-05-24
**Scope:** Sprint 1 von 5 nach Feature-Brainstorming (siehe README §Features).
**Verwandt:** Baut auf der integrierten Reminder-Engine (`coordinator.evaluate_reminders`)
auf, die in Commit `2eabf0a`+Folge-Commits eingeführt wurde.

## Ziel

Reminder-Notifications auf dem HA-Mobile-App-Handy bekommen Action-Buttons,
mit denen der User die Pflege direkt aus der Notification quittieren kann
(💧 Gegossen / 🌱 Gedüngt) oder die Notification um 24 h vertagen kann
(💤 Snooze 1d) — ohne in die HA-App wechseln zu müssen.

## Nicht-Ziele

- Deep-Link von der Notification ins Plant-Care-Panel.
  HA-Mobile-Deep-Links zu Custom-Panels sind unzuverlässig; out of scope.
- Multi-Notify-Targets (z.B. iPhone + Telegram gleichzeitig). Bleibt
  Single-Target wie heute.
- Konfigurierbare Snooze-Dauer. Fix 24 h für diesen Sprint.
- Sichtbarer "Snooze"-Status im Panel. Pflanze bleibt rot bis tatsächlich
  gegossen/gedüngt wird; der Snooze unterdrückt nur die Notification.

## UX

Notification-Format auf dem Handy:

```
🌿 Plant Care
Monstera braucht Wasser.

[💧 Gegossen]  [💤 Snooze 1d]
```

Welche Buttons gezeigt werden, hängt vom Sensor-Status der Pflanze ab:

| Status | Buttons |
|---|---|
| `needs_water` | 💧 Gegossen, 💤 Snooze 1d |
| `needs_fertilizer` | 🌱 Gedüngt, 💤 Snooze 1d |
| `needs_both` | 💧 Gegossen, 🌱 Gedüngt, 💤 Snooze 1d |

Tap auf den Notification-Body ohne Button-Tap macht nichts (öffnet
die HA-App auf der Startseite, wie HA-default).

## Architektur

### Notification-Payload

Der bisherige `notify`-Service-Call in `coordinator.evaluate_reminders`
wird erweitert: falls die Ziel-Service-Domain `notify.mobile_app_*` ist,
wird ein `data:`-Block mit Action-Definitionen angehängt. Andere Notify-
Services (Telegram, Persistent, etc.) erhalten den unveränderten
`{title, message}`-Call und ignorieren den `data`-Block respektive
bekommen ihn gar nicht erst.

```yaml
service: notify.mobile_app_iphone
data:
  title: Plant Care
  message: "🌿 Monstera braucht Wasser."
  data:
    actions:
      - action: PLANTCARE_WATER_abc123
        title: "💧 Gegossen"
      - action: PLANTCARE_SNOOZE_abc123
        title: "💤 Snooze 1d"
    tag: plant_care_abc123
    group: plant_care
```

Felder:
- `actions[]` — bis zu drei Actions pro Notification, je nach Status
- `tag` — gleiche Pflanze ⇒ vorhandene Notification ersetzen, kein Stack
- `group` — alle Plant-Care-Notifications werden im Notification-Center
  gruppiert dargestellt (iOS / Android)

Auto-Detection in der Reminder-Engine:

```python
is_mobile_app = notify_domain == "notify" and notify_service.startswith("mobile_app_")
```

Beim aktuellen Schema (`notify_service` = `"notify.mobile_app_iphone"`)
wird der String an `"."` gesplittet → `domain="notify"`,
`service="mobile_app_iphone"`. Die Prüfung erfolgt auf den Service-Teil.

### Action-Routing

Beim `async_setup_entry` registriert die Integration einen HA-Event-Bus-
Listener:

```python
unsub = hass.bus.async_listen(
    "mobile_app_notification_action", _handle_notification_action
)
hass.data[DOMAIN]["unsub_action_listener"] = unsub
```

Der Handler:

1. liest `event.data["action"]` (z.B. `"PLANTCARE_WATER_abc123"`)
2. parst die ID mit `parse_action_id()` aus `_utils.py`
3. validiert: Pflanze existiert noch im Coordinator
4. dispatcht:
   - `WATER` → `coord.async_water_plant(plant_id)`
   - `FERTILIZE` → `coord.async_fertilize_plant(plant_id)`
   - `SNOOZE` → `coord.async_snooze_plant(plant_id, hours=24)`

Unbekannte/fremde Action-IDs (z.B. von anderen Integrationen) werden
silent ignoriert — der Event-Bus ist HA-weit, nicht integrationsspezifisch.

Cleanup: Der Listener wird in `async_unload_entry` deregistriert
(`unsub()`).

### Snooze-Semantik

Neue Coordinator-Methode `async_snooze_plant(plant_id, hours=24)`:

```python
async def async_snooze_plant(self, plant_id: str, hours: int = 24) -> None:
    """Verzögert die nächste Notification um mindestens `hours` Stunden."""
    if plant_id not in self._plants:
        raise ValueError(f"Pflanze {plant_id} nicht gefunden")
    rate_h = int(self._entry_options.get(CONF_RATE_LIMIT_HOURS) or 0)
    last_notified = compute_snooze_last_notified(
        now=datetime.now(timezone.utc),
        snooze_hours=hours,
        rate_limit_hours=rate_h,
    )
    self._plants[plant_id]["last_notified"] = last_notified.isoformat()
    await self._async_save_now()
    _LOGGER.info(
        "Plant Care: Pflanze %s für %d h gesnoozed", plant_id, hours
    )
```

Die Logik in `_utils.py`:

```python
def compute_snooze_last_notified(
    now: datetime, snooze_hours: int, rate_limit_hours: int
) -> datetime:
    """`last_notified` so setzen, dass Rate-Limit für ``snooze_hours`` greift."""
    offset_hours = max(0, snooze_hours - max(0, rate_limit_hours))
    return now + timedelta(hours=offset_hours)
```

Verhalten:

| `rate_limit_hours` | `snooze_hours=24` | Wirkung |
|---|---|---|
| 0 | offset = 24 | `last_notified = now+24h`; nächste Notification frühestens in 24 h |
| 12 | offset = 12 | `last_notified = now+12h`; rate_limit von 12h greift bis now+24h |
| 24 | offset = 0 | `last_notified = now`; rate_limit von 24h greift bis now+24h |
| 48 | offset = 0 | `last_notified = now`; rate_limit greift länger als 24h — User wollte aber explizit 48h Rate-Limit |

**Wichtig:** Das ist die `(a) Rate-Limit-Reset`-Variante, die der User
explizit gewählt hat. Der Pflanzen-Status (`needs_water`) im Panel bleibt
unverändert rot — der Snooze unterdrückt nur die Reminder-Notification.

Falls in Zukunft ein sichtbarer "💤 vertagt bis morgen"-Status im Panel
gewünscht ist, würde man ein dediziertes `snooze_until`-Feld einführen
und sowohl `evaluate_reminders` als auch `PlantSensor.native_value`
darauf prüfen. Bewusst out-of-scope für diesen Sprint.

### Coordinator-Zugriff auf Options

Damit `async_snooze_plant` den aktuellen `rate_limit_hours`-Wert lesen
kann, braucht der Coordinator Zugriff auf `entry.options`. Optionen:

- **a)** `entry`-Referenz im Coordinator speichern (im `__init__` injecten).
- **b)** Options als Argument an `async_snooze_plant` durchreichen.

**Entscheidung: (a).** Cleaner für den Action-Handler in `__init__.py`,
der bei jedem Action-Event nicht erst Options auflesen muss. Setter in
`__init__.async_setup_entry`:

```python
coord.bind_entry(entry)  # speichert self._entry, lazily liest options
```

## Datenmodell-Änderungen

Keine Schema-Änderungen am Plant-Dict. `last_notified` existiert bereits
und wird nur in die Zukunft verschoben statt nur auf "jetzt".

## Neue Pure-Helper (`_utils.py`)

```python
def parse_action_id(action_id: str) -> tuple[str, str] | None:
    """Zerlegt "PLANTCARE_<ACTION>_<plant_id>" → (action, plant_id) oder None."""

def compute_snooze_last_notified(
    now: datetime, snooze_hours: int, rate_limit_hours: int
) -> datetime:
    """Berechnet den Zeitstempel für `last_notified` nach Snooze."""
```

## Tests

Neu in `tests/test_utils.py`:

- `parse_action_id` mit gültigen IDs (`WATER`/`FERTILIZE`/`SNOOZE`)
- `parse_action_id` mit Prefix-Mismatch (`OTHER_WATER_abc`)
- `parse_action_id` mit zu wenig Segmenten (`PLANTCARE_WATER`)
- `parse_action_id` mit unbekannter Action (`PLANTCARE_FOO_abc`) →
  Entscheidung: gibt `("FOO", "abc")` zurück; Dispatcher ignoriert unbekannte
  Actions. Filterung in der Handler-Logik, nicht im Parser.
- `compute_snooze_last_notified` für die 4 Tabellenfälle oben

Coverage-Ziel: 5 neue Tests. Bestehende 28 müssen unverändert grün bleiben.

## Edge Cases

| Fall | Verhalten |
|---|---|
| Notify-Service ist Telegram → Buttons unsichtbar | Notification wird normal gesendet; User muss in HA wechseln |
| User tappt Action für gelöschte Pflanze | Coordinator wirft `ValueError`; Handler loggt `_LOGGER.debug` und ignoriert |
| User tappt mehrfach (langsames Netz / Doppelt-Tap) | `tag: plant_care_<id>` ersetzt vorherige Notif; mehrfach-Service-Call ist idempotent für Water/Fertilize (History-Cap = 90) |
| Action-Event kommt während HA-Restart | HA-Mobile-App buffert; Event kommt nach Reboot — kein Spezial-Handling |
| Fremde `mobile_app_notification_action`-Events (andere Integration) | Action-ID matched nicht `PLANTCARE_` → silent skip |
| Snooze-Tap, aber `rate_limit_hours > 24` | Snooze hat keinen sichtbaren Effekt; User-Konfiguration hat Vorrang. Im Log Hinweis. |
| User snoozed, danach manuell gegossen vom Panel | `last_watered = now`, Status wird OK. `last_notified` aus der Zukunft bleibt aber drin — beim nächsten neuen Pflege-Bedarf ist die Pflanze ggf. zu lange rate-limited. **Mitigation:** `async_water_plant` und `async_fertilize_plant` setzen `last_notified = None` als Teil der Operation. |

## Dateien

| Datei | Änderung |
|---|---|
| `custom_components/plant_care/_utils.py` | + `parse_action_id`, `compute_snooze_last_notified` |
| `custom_components/plant_care/const.py` | + `ACTION_ID_PREFIX = "PLANTCARE"`, `SNOOZE_DEFAULT_HOURS = 24` |
| `custom_components/plant_care/coordinator.py` | + `bind_entry`, `async_snooze_plant`; `evaluate_reminders` baut Mobile-App-Payload; `async_water_plant` / `async_fertilize_plant` resetten `last_notified` |
| `custom_components/plant_care/__init__.py` | + `mobile_app_notification_action`-Listener; Cleanup in Unload |
| `tests/test_utils.py` | + 5 Tests |
| `README.md` | + Hinweis dass Mobile-App-Notify Buttons hat |

## Risiken

- **HA-Mobile-App-Action-Schema-Drift:** Das `data.actions`-Format ist
  laut HA-Docs stabil seit 2021, gilt aber als App-Feature, nicht Core.
  Bei Breaking Change in HA müssten wir nachziehen. Mitigation: dieses
  Risiko ist Core-Bestandteil aller HA-Integrationen mit Actionable
  Notifications und damit akzeptabel.
- **Action-ID-Kollision mit anderer Integration:** Andere Custom-Integration
  könnte zufällig `PLANTCARE_...`-Actions verwenden. Mitigation: Prefix
  `PLANTCARE_` ist projektspezifisch; Kollision unwahrscheinlich. Sollte
  es passieren, ist der Parser tolerant und der Dispatcher prüft auf
  Plant-Existenz.

## Aufwand

Geschätzt 2–3 h: Coordinator-Erweiterung (~1 h), Event-Listener inkl.
Handler (~30 min), Helper + 5 Tests (~30 min), README + manuelles HA-Test
(~30–60 min).
