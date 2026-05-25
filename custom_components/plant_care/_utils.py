"""Pure Hilfsfunktionen ohne Home-Assistant-Imports.

Liegt in einem eigenen Modul, damit Unit-Tests die Logik ohne
HA-Test-Infrastruktur abdecken können.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any


def utcnow_iso() -> str:
    """Aktueller UTC-Zeitstempel als ISO-8601 String."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """ISO-8601 → datetime. Gibt None bei ungültiger Eingabe zurück."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def try_float(value: Any) -> float | None:
    """Best-effort float-Cast. None statt Exception."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_data(data: dict[str, Any]) -> dict[str, Any]:
    """Entfernt None-Werte und leere Strings aus eingehenden Daten.

    Wird vom Coordinator nur für ``add_plant`` benutzt, damit Default-Werte
    greifen können. Für ``update_plant`` ist leerer String ein gültiger Wert
    ("Feld explizit leeren") und darf NICHT gefiltert werden.
    """
    return {k: v for k, v in data.items() if v is not None and v != ""}


def needs_time_based(
    last_iso: str | None, days: int | None, now: datetime
) -> bool:
    """Prüft, ob eine zeit-basierte Pflege-Aktion fällig ist.

    - last_iso=None bedeutet "noch nie" → True (braucht Pflege).
    - days falsy (0/None) → False (Intervall deaktiviert), sofern jemals
      ausgeführt; wenn noch nie ausgeführt, gilt der None-Fall darüber.
    """
    last = parse_iso(last_iso)
    if last is None:
        return last_iso is None
    if not days:
        return False
    due = last + timedelta(days=int(days))
    return now >= due


def parse_time_string(value: str | None) -> dt_time | None:
    """Parst ``HH:MM`` oder ``HH:MM:SS``; gibt None bei ungültiger Eingabe."""
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def is_in_quiet_hours(
    now: dt_time, start: dt_time | None, end: dt_time | None
) -> bool:
    """True, wenn ``now`` im Quiet-Hours-Fenster [start, end) liegt.

    Wenn ``start > end``, wrappt das Fenster über Mitternacht
    ([start, 24:00) ∪ [00:00, end)). Werden ``start`` oder ``end``
    nicht gesetzt (oder sind gleich), gibt es keine Ruhezeit.
    """
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def is_rate_limited(
    last_notified_iso: str | None, hours: int, now: datetime
) -> bool:
    """True, wenn die letzte Notification weniger als ``hours`` Stunden her ist."""
    if hours <= 0 or not last_notified_iso:
        return False
    last = parse_iso(last_notified_iso)
    if last is None:
        return False
    return (now - last) < timedelta(hours=hours)


def parse_action_id(action_id: str) -> tuple[str, str] | None:
    """Zerlegt ``PLANTCARE_<ACTION>_<plant_id>`` → ``(action, plant_id)``.

    Tolerant gegenüber unbekannten Actions – der Dispatcher entscheidet,
    welche Actions er kennt. Rückgabe ``None`` nur bei Prefix-Mismatch
    oder fehlenden Segmenten.
    """
    if not action_id:
        return None
    parts = action_id.split("_", 2)
    if len(parts) < 3 or parts[0] != "PLANTCARE":
        return None
    return (parts[1], parts[2])


def parse_notify_targets(value: str | None) -> list[tuple[str, str]]:
    """Parst ein Komma-separates Notify-Target-Feld.

    ``"notify.foo, notify.bar"`` → ``[("notify", "foo"), ("notify", "bar")]``.
    Leere und Einträge ohne ``.`` werden silent verworfen.
    """
    if not value:
        return []
    targets: list[tuple[str, str]] = []
    for raw in value.split(","):
        cleaned = raw.strip()
        if not cleaned or "." not in cleaned:
            continue
        domain, service = cleaned.split(".", 1)
        if domain and service:
            targets.append((domain, service))
    return targets


def _next_month_start(when_dt: datetime) -> datetime:
    """Liefert den 1. des nächsten Monats (gleiche Stunde/Tz). Hilfsfunktion
    für saisonales Skipping in :func:`generate_care_events`.
    """
    if when_dt.month == 12:
        return when_dt.replace(year=when_dt.year + 1, month=1, day=1)
    return when_dt.replace(month=when_dt.month + 1, day=1)


def generate_care_events(
    plant: dict[str, Any],
    start: datetime,
    end: datetime,
    *,
    now: datetime | None = None,
    max_per_kind: int = 10,
    season_water_mult: dict[int, float] | None = None,
    season_fert_mult: dict[int, float] | None = None,
    winter_rest_months: tuple[int, ...] = (12, 1, 2),
) -> list[dict[str, Any]]:
    """Erzeugt Pflege-Termine für eine Pflanze im Zeitraum [start, end).

    Berücksichtigt ``last_watered``/``last_fertilized`` und die Intervalle.
    Wenn die Pflanze noch nie gegossen/gedüngt wurde, fällt der erste
    Termin auf ``start``.

    Wenn ein Pflege-Termin **vor** ``start`` liegt (also versäumt wurde)
    und die ursprüngliche Fälligkeit höchstens 30 Tage zurück ist, wird
    **ein** Backlog-Event bei ``start`` eingefügt mit ``overdue=True``.
    Sonst keine Events vor ``start``.

    Outdoor-Pflanzen (``plant_kind == "outdoor"``) werden saisonal angepasst,
    wenn ``season_*_mult`` übergeben wird: Multiplikator 0 in einem Monat
    überspringt diesen komplett (Springer-Logik auf 1. des Folgemonats);
    ``winter_rest=True`` springt von Dez/Jan/Feb direkt auf 1. März.
    Damit stimmt der Kalender wieder mit ``PlantSensor.native_value`` überein.

    Args:
        plant: Plant-Dict aus dem Coordinator.
        start: Inklusiver Anfang des Anzeige-Zeitraums.
        end: Exklusives Ende.
        now: Aktuelle Zeit für Overdue-Bestimmung. Default: ``start``.
        max_per_kind: Maximal so viele Events pro kind (Default 10).
        season_water_mult: Optional Outdoor-Saison-Tabelle für Wasser.
        season_fert_mult: Optional Outdoor-Saison-Tabelle für Dünger.
        winter_rest_months: Monate (1-12), in denen ``winter_rest`` greift.

    Returns:
        Liste von Dicts mit ``{plant_id, name, kind, when, overdue, original_when}``,
        sortiert nach ``when`` aufsteigend.
    """
    if now is None:
        now = start
    events: list[dict[str, Any]] = []
    plant_id = plant.get("id", "")
    name = plant.get("name") or plant_id
    is_outdoor = (plant.get("plant_kind") or "indoor") == "outdoor"
    winter_rest = bool(plant.get("winter_rest")) and is_outdoor

    for kind, last_key, days_key, mult_table in (
        ("water", "last_watered", "water_days",
         season_water_mult if is_outdoor else None),
        ("fertilize", "last_fertilized", "fertilize_days",
         season_fert_mult if is_outdoor else None),
    ):
        days_val = plant.get(days_key)
        if not days_val:
            continue
        try:
            base_days = int(days_val)
        except (TypeError, ValueError):
            continue
        if base_days <= 0:
            continue

        def advance(current: datetime) -> datetime:
            """Liefert das Datum des nächsten Events nach ``current``,
            unter Berücksichtigung von Winterruhe und Saison-Multiplikator.
            """
            # Winterruhe → springe an 1. März
            if winter_rest and current.month in winter_rest_months:
                if current.month == 12:
                    return current.replace(year=current.year + 1, month=3, day=1)
                return current.replace(month=3, day=1)
            # Saison-Multiplikator (nur Outdoor)
            if mult_table:
                mult = mult_table.get(current.month, 1.0)
                if mult <= 0:
                    return _next_month_start(current)
                delta = max(1, round(base_days * mult))
            else:
                delta = base_days
            return current + timedelta(days=delta)

        # "Aktuell pausiert" – wenn weder Vergangenheit noch Zukunft passt,
        # vorwärts schieben bis die nächste Saison wieder Events liefert.
        def skip_inactive(due: datetime) -> datetime:
            for _ in range(13):  # max. 1 Jahr im Voraus
                in_rest = (
                    winter_rest and due.month in winter_rest_months
                )
                paused = bool(mult_table) and mult_table.get(due.month, 1.0) <= 0
                if not in_rest and not paused:
                    return due
                due = advance(due)
            return due  # Safety

        last = parse_iso(plant.get(last_key))
        if last is None:
            # Nie gepflegt → erstes Event fällig ab Start.
            due = skip_inactive(start)
        else:
            due = advance(last)
            if due < start:
                # Backlog-Event bei start, falls nicht zu lange her.
                if due < now and due >= start - timedelta(days=30):
                    events.append({
                        "plant_id": plant_id,
                        "name": name,
                        "kind": kind,
                        "when": start,
                        "original_when": due,
                        "overdue": True,
                    })
                # Vorwärts springen bis >= start, max. 400 Schritte als
                # Endlosschleifen-Schutz.
                for _ in range(400):
                    if due >= start:
                        break
                    nxt = advance(due)
                    if nxt <= due:
                        break
                    due = nxt
                due = skip_inactive(due)

        count = 0
        for _ in range(max_per_kind * 4):  # Loop-Schutz mit Saisons-Skipping
            if due >= end or count >= max_per_kind:
                break
            events.append({
                "plant_id": plant_id,
                "name": name,
                "kind": kind,
                "when": due,
                "original_when": due,
                "overdue": due < now,
            })
            count += 1
            nxt = advance(due)
            if nxt <= due:
                break
            due = nxt

    events.sort(key=lambda e: e["when"])
    return events


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


def sort_photos(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sortiert Fotos descending nach ``taken_at`` (neuestes zuerst).

    Fotos ohne ``taken_at`` landen ans Ende.
    """
    def _key(photo: dict[str, Any]) -> tuple[int, str]:
        ts = photo.get("taken_at")
        if not ts:
            return (0, "")
        return (1, ts)
    return sorted(photos, key=_key, reverse=True)


def migrate_legacy_photo(plant: dict[str, Any]) -> bool:
    """Bringt eine Plant-Storage-Entry auf das neue Photo-Array-Schema."""
    if "photos" in plant and isinstance(plant.get("photos"), list):
        return False
    legacy = plant.get("photo") or ""
    if legacy and isinstance(legacy, str):
        plant["photos"] = [
            {
                "path": legacy,
                "taken_at": plant.get("created") or utcnow_iso(),
                "note": "",
            }
        ]
    else:
        plant["photos"] = []
    return True


def cap_photos(
    photos: list[dict[str, Any]], max_count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Kürzt die DESC-sortierte Foto-Liste auf ``max_count``.

    Returns ``(kept, removed)`` damit der Caller die Files
    der entfernten Einträge vom Disk räumen kann.
    """
    if max_count <= 0 or len(photos) <= max_count:
        return list(photos), []
    return list(photos[:max_count]), list(photos[max_count:])


def effective_water_days(
    plant: dict[str, Any],
    now: datetime,
    *,
    season_multipliers: dict[int, float] | None = None,
) -> int:
    """Rechnet das saisonal angepasste Gieß-Intervall für eine Pflanze.

    Für ``plant_kind == "outdoor"`` wird ``water_days`` mit dem Monats-
    Multiplikator gewichtet. Für Indoor-Pflanzen unverändert durchgereicht.
    Rückgabe: ``0`` heißt "Intervall ausgesetzt" (z.B. Winter-Faktor 0).
    """
    base = int(plant.get("water_days") or 0)
    if base <= 0:
        return 0
    if (plant.get("plant_kind") or "indoor") != "outdoor":
        return base
    table = season_multipliers if season_multipliers is not None else {}
    mult = table.get(now.month, 1.0)
    if mult <= 0:
        return 0
    return max(1, round(base * mult))


def effective_fertilize_days(
    plant: dict[str, Any],
    now: datetime,
    *,
    season_multipliers: dict[int, float] | None = None,
) -> int:
    """Wie ``effective_water_days``, nur für ``fertilize_days``."""
    base = int(plant.get("fertilize_days") or 0)
    if base <= 0:
        return 0
    if (plant.get("plant_kind") or "indoor") != "outdoor":
        return base
    table = season_multipliers if season_multipliers is not None else {}
    mult = table.get(now.month, 1.0)
    if mult <= 0:
        return 0
    return max(1, round(base * mult))


def is_winter_rest_active(
    plant: dict[str, Any], now: datetime, winter_months: tuple[int, ...] = (12, 1, 2)
) -> bool:
    """True, wenn Outdoor-Pflanze mit ``winter_rest=True`` in einem Wintermonat ist."""
    if (plant.get("plant_kind") or "indoor") != "outdoor":
        return False
    if not plant.get("winter_rest"):
        return False
    return now.month in winter_months


def precipitation_within_hours(
    forecast: list[dict[str, Any]] | None,
    now: datetime,
    *,
    horizon_hours: int,
) -> float:
    """Summiert das ``precipitation``-Feld aller Forecast-Einträge im
    Fenster ``[now, now + horizon_hours)``.

    Akzeptiert sowohl Stunden- als auch Tages-Forecasts. Naive ``datetime``-
    Werte werden als UTC interpretiert (analog zu :func:`has_frost_in_forecast`).
    Einträge vor ``now`` oder jenseits des Horizonts werden ignoriert.

    Rückgabe: Gesamtniederschlag in mm. Bei leerer/fehlender Liste 0.0.
    """
    if not forecast:
        return 0.0
    cutoff = now + timedelta(hours=horizon_hours)
    total = 0.0
    for entry in forecast:
        when_iso = entry.get("datetime") or entry.get("date")
        when = parse_iso(when_iso) if when_iso else None
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < now or when > cutoff:
            continue
        value = entry.get("precipitation")
        if value is None:
            continue
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return total


def has_frost_in_forecast(
    forecast: list[dict[str, Any]] | None,
    now: datetime,
    *,
    horizon_hours: int,
    threshold_c: float,
) -> bool:
    """Sucht in der HA-Weather-Forecast-Liste nach einem Tief unter ``threshold_c``.

    Berücksichtigt nur Einträge mit ``datetime`` im Fenster ``[now, now + horizon_hours)``.
    Bei Tages-Forecasts vergleicht es ``templow``, bei Stunden-Forecasts ``temperature``.

    Robust gegen naive ``datetime``-Werte (z.B. ``date: "2026-01-15"`` aus daily
    forecasts): werden als UTC behandelt statt zu crashen.
    """
    if not forecast:
        return False
    cutoff = now + timedelta(hours=horizon_hours)
    for entry in forecast:
        when_iso = entry.get("datetime") or entry.get("date")
        when = parse_iso(when_iso) if when_iso else None
        if when is None:
            continue
        # Naive Forecast-Timestamps als UTC interpretieren, sonst kracht
        # der Vergleich gegen das tz-aware `cutoff` mit TypeError.
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < now or when > cutoff:
            continue
        # templow für Daily-Forecasts, temperature als Fallback für Hourly.
        temp_val = entry.get("templow")
        if temp_val is None:
            temp_val = entry.get("temperature")
        if temp_val is None:
            continue
        try:
            if float(temp_val) < threshold_c:
                return True
        except (TypeError, ValueError):
            continue
    return False


def compute_snooze_last_notified(
    now: datetime, snooze_hours: int, rate_limit_hours: int
) -> datetime:
    """Berechnet ``last_notified`` so, dass Rate-Limit für ``snooze_hours`` greift.

    Strategie: das bestehende Rate-Limit (``rate_limit_hours``) abzüglich
    der gewünschten Snooze-Dauer in die Zukunft verschieben. Wenn das
    Rate-Limit größer ist als der Snooze-Wunsch, hat der User-Wunsch
    keinen sichtbaren Effekt – sein Rate-Limit greift länger.
    """
    rate_h = max(0, rate_limit_hours)
    offset_hours = max(0, snooze_hours - rate_h)
    return now + timedelta(hours=offset_hours)
