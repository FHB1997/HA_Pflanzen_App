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
