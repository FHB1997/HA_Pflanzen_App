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


def generate_care_events(
    plant: dict[str, Any],
    start: datetime,
    end: datetime,
    *,
    now: datetime | None = None,
    max_per_kind: int = 10,
) -> list[dict[str, Any]]:
    """Erzeugt Pflege-Termine für eine Pflanze im Zeitraum [start, end).

    Berücksichtigt ``last_watered``/``last_fertilized`` und die Intervalle.
    Wenn die Pflanze noch nie gegossen/gedüngt wurde, fällt der erste
    Termin auf ``start``.

    Wenn ein Pflege-Termin **vor** ``start`` liegt (also versäumt wurde)
    und die ursprüngliche Fälligkeit höchstens 30 Tage zurück ist, wird
    **ein** Backlog-Event bei ``start`` eingefügt mit ``overdue=True``.
    Sonst keine Events vor ``start``.

    Args:
        plant: Plant-Dict aus dem Coordinator.
        start: Inklusiver Anfang des Anzeige-Zeitraums.
        end: Exklusives Ende.
        now: Aktuelle Zeit für Overdue-Bestimmung. Default: ``start``.
        max_per_kind: Maximal so viele Events pro kind (Default 10).

    Returns:
        Liste von Dicts mit ``{plant_id, name, kind, when, overdue, original_when}``,
        sortiert nach ``when`` aufsteigend.
    """
    if now is None:
        now = start
    events: list[dict[str, Any]] = []
    plant_id = plant.get("id", "")
    name = plant.get("name") or plant_id

    for kind, last_key, days_key in (
        ("water", "last_watered", "water_days"),
        ("fertilize", "last_fertilized", "fertilize_days"),
    ):
        days_val = plant.get(days_key)
        if not days_val:
            continue
        try:
            days = int(days_val)
        except (TypeError, ValueError):
            continue
        if days <= 0:
            continue

        last = parse_iso(plant.get(last_key))
        if last is None:
            # Nie gepflegt → erstes Event fällig ab Start.
            due = start
        else:
            due = last + timedelta(days=days)
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
                missed = (start - due).days // days + 1
                due = due + timedelta(days=days * missed)

        count = 0
        while due < end and count < max_per_kind:
            events.append({
                "plant_id": plant_id,
                "name": name,
                "kind": kind,
                "when": due,
                "original_when": due,
                "overdue": due < now,
            })
            due = due + timedelta(days=days)
            count += 1

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
