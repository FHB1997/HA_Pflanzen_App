# Saison-aware Intervalle — Design

**Status:** Approved (autonom)
**Date:** 2026-05-24
**Scope:** Sprint 5 von 5. Letzter Sprint. Plant-Schema bekommt opt-in
Saisonal-Toggle; Sensor-Status-Logik nutzt saison-justierte Intervalle.

## Ziel

Im Winter wird seltener gegossen und nicht gedüngt – im Sommer mehr.
Plant Care passt die Gieß- und Düngeintervalle automatisch an die
Jahreszeit an, ohne dass der User pro Pflanze etwas tun muss. Pro
Pflanze per Toggle aktivierbar (Default OFF, weil opinionated).

## Nicht-Ziele

- Pro-Pflanze konfigurierbare Multiplier-Tabelle. Wenn ja, dann später.
  Sprint 5 nutzt eine globale Standard-Tabelle, identisch für alle.
- AI-basierte saisonale Anpassung pro Spezies. Wäre 2. Iteration.
- Outdoor-Pflanzen-spezifische Behandlung (Frost, etc.). Aus Sprint 6+.
- Mondkalender / Pflanztermine.

## Saison-Definition

Standard-Jahreszeiten Nordhalbkugel (Default):
- **Frühling:** März, April, Mai
- **Sommer:** Juni, Juli, August
- **Herbst:** September, Oktober, November
- **Winter:** Dezember, Januar, Februar

Optional via OptionsFlow: Hemisphäre `north` (Default) oder `south`.
Bei `south` werden die Saisons um 6 Monate verschoben.

Datum-Quelle: HA-Lokalzeit (`dt_util.now()`), nicht UTC.

## Multiplier-Tabelle

Pro Saison ein Multiplier für `water_days` und `fertilize_days`:

| Saison | Wasser-Multiplier | Dünger-Multiplier |
|---|---|---|
| Frühling | 1.0 | 1.0 |
| Sommer | 0.85 (öfter gießen) | 1.0 |
| Herbst | 1.15 | 1.5 (seltener düngen) |
| Winter | 1.5 (seltener gießen) | 999 (kein Dünger) |

`effective_days = round(base_days * multiplier)`, geclampt auf
`[1, 365]`. Düngen im Winter ist effektiv ausgeschaltet (999 Tage
= praktisch nie).

Diese Tabelle ist Code-Konstante; nicht user-konfigurierbar in Sprint 5.

## Datenmodell

Plant-Dict bekommt **ein** neues Feld:

```python
"seasonal_adjust": False  # Default; per Pflanze opt-in
```

Bestehende `water_days` und `fertilize_days` bleiben unverändert – das
sind die **Basis**-Werte. Die effektiven Werte werden bei jedem
Sensor-Read **berechnet**, nicht persistiert. Das hält den Storage
clean und vermeidet Stale-Werte beim Jahreszeit-Übergang.

Migration in `async_load`: `plant.setdefault("seasonal_adjust", False)`.

## OptionsFlow-Erweiterung

Zwei neue Felder:

- `seasonal_enabled` (bool, Default False) — globaler Master-Toggle.
  Wenn aus, ignoriere alle per-Pflanze-`seasonal_adjust`.
- `hemisphere` (`north` | `south`, Default `north`) — relevant nur
  wenn `seasonal_enabled` true.

Logik im Sensor:
```python
seasonal_active = (
    options.get("seasonal_enabled", False)
    and plant.get("seasonal_adjust", False)
)
```

## Pure Helper (`_utils.py`)

```python
def get_season(now: datetime, hemisphere: str = "north") -> str:
    """Liefert 'spring' | 'summer' | 'autumn' | 'winter'."""

def seasonal_multiplier(
    season: str, kind: str  # "water" | "fertilize"
) -> float:
    """Multiplier aus der globalen Tabelle. Default 1.0 bei Unbekannt."""

def effective_days(
    base_days: int | None,
    season: str | None,
    kind: str,
    seasonal_active: bool,
) -> int | None:
    """Wendet Multiplier an wenn aktiv. ``None`` bleibt ``None``.
    Geclampt auf [1, 365]."""
```

Test-Coverage: ~12 neue Tests.

## Sensor-Integration

Die `_needs_time_based`-Calls in `PlantSensor.native_value` bekommen
nicht mehr `plant.get("water_days")` direkt, sondern den effektiven
Wert. Dazu liest der Sensor aus dem ConfigEntry des Domains:

```python
options = self._entry_options()  # bekommt entry via Coordinator-Binding
seasonal_enabled_global = options.get(CONF_SEASONAL_ENABLED, False)
hemisphere = options.get(CONF_HEMISPHERE, "north")
season = get_season(now, hemisphere)

water_active = seasonal_enabled_global and plant.get("seasonal_adjust", False)
eff_water = effective_days(
    plant.get("water_days"), season, "water", water_active
)
eff_fert = effective_days(
    plant.get("fertilize_days"), season, "fertilize", water_active
)
```

Helper `self._entry_options()` greift via `self._coord._entry.options`
(bereits aus Sprint 1 vorhanden; defensiv mit None-Check).

## Frontend

### Add/Edit-Form

Neue Checkbox `🌗 Saisonal anpassen` direkt neben den Intervall-Feldern.
Wenn aktiv und globaler Toggle ist auch an, wird unter den Intervall-
Feldern in **Klein** angezeigt:

```
Gießintervall: 7 Tage  (aktuell saisonal: 11 Tage – Winter)
Düngeintervall: 30 Tage (aktuell saisonal: aus – Winter)
```

### Detail-View

In der Action-Card "Gießen" bzw. "Düngen" zusätzliche Zeile:

```
Intervall: alle 7 Tage (saisonal: 11 Tage)
```

Wenn Saisonal aktiv und globaler Toggle an. Sonst unverändert.

### OptionsFlow

User configures via HA-UI:
- "Saisonale Anpassung aktivieren" Checkbox
- "Hemisphäre" Dropdown (Nord/Süd)

## Edge Cases

| Fall | Verhalten |
|---|---|
| seasonal_enabled global aus, aber Pflanze hat seasonal_adjust=True | Wird ignoriert; effektive Werte = Basis |
| Pflanze ohne water_days (None) | `effective_days(None, ...)` returnt `None`; bestehendes Verhalten "nie gießen" |
| Jahreszeit-Übergang während HA läuft | Nächster Sensor-Read berechnet neuen Multiplier; kein Reload nötig |
| Hemisphäre wird umgestellt | Sensor-State updated via `SIGNAL_PLANTS_UPDATED`-Dispatch beim nächsten Reload des Entries |
| Multiplier-999 für Dünger im Winter | Sensor bewertet das als "nie fällig"; Düngen wird im Winter nie angemahnt |
| Test-Datum 28. Februar / 1. März | Übergang Winter→Frühling: exakt am 1. März wird Frühling-Multiplier aktiv |

## Dateien

| Datei | Änderung |
|---|---|
| `_utils.py` | + `get_season`, `seasonal_multiplier`, `effective_days` |
| `const.py` | + `CONF_SEASONAL_ENABLED`, `CONF_HEMISPHERE`, Saison-Konstanten |
| `coordinator.py` | + `seasonal_adjust`-Migration |
| `sensor.py` | + Saison-aware Intervall-Berechnung in `native_value` und Attributen |
| `config_flow.py` | + 2 neue Optionen im OptionsFlow |
| `__init__.py` | + `seasonal_adjust` in add/update schemas |
| `services.yaml` | + neues Feld `seasonal_adjust` in `add_plant` / `update_plant` |
| `strings.json` + translations | + i18n für die zwei neuen Optionen |
| `frontend/plant-care-panel.js` | + Checkbox im Form, Saisonal-Anzeige im Detail |
| `tests/test_utils.py` | + ~12 Tests |
| `README.md` | + Saisonal-Sektion |

## Risiken

- **Botanische Korrektheit:** Die Standard-Multiplier sind opinionated.
  Tropische Pflanzen reagieren anders als Sukkulenten. Mitigation:
  Default OFF, User kann es bewusst aktivieren. Spätere Iterationen
  können pro-Spezies-Tabellen hinzufügen.
- **Jahreszeit-Wechsel als "Surprise":** User wundert sich, warum am
  1. März plötzlich häufiger gegossen werden soll. Mitigation: README +
  Detail-View zeigt explizit "saisonal: X Tage".
- **Hemisphäre falsch konfiguriert:** User in Australien vergisst auf
  `south` zu stellen → falsche Intervalle. Mitigation: OptionsFlow zeigt
  Hemisphäre prominent, Default Nord ist offensiver Hinweis für Süd-User.

## Aufwand

Geschätzt 3-4 h: Helper + Tests (~1 h), Coordinator/Sensor-Integration
(~1 h), OptionsFlow-Erweiterung (~30 min), Frontend-Form + Detail-View
(~1 h), README + Test (~30 min).
