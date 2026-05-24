"""Smoke-Tests für custom_components.plant_care._utils.

Diese Tests laufen ohne Home-Assistant-Stack, da ``_utils`` bewusst
keine HA-Imports enthält. ``conftest.py`` legt den passenden sys.path.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone

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


# --------------------------- parse_iso ---------------------------

def test_parse_iso_none_returns_none():
    assert parse_iso(None) is None


def test_parse_iso_empty_string_returns_none():
    assert parse_iso("") is None


def test_parse_iso_garbage_returns_none():
    assert parse_iso("nicht-ein-datum") is None


def test_parse_iso_valid_utc():
    result = parse_iso("2026-05-24T12:34:56+00:00")
    assert result == datetime(2026, 5, 24, 12, 34, 56, tzinfo=timezone.utc)


# --------------------------- try_float ---------------------------

def test_try_float_valid():
    assert try_float("42.5") == 42.5
    assert try_float(7) == 7.0


def test_try_float_invalid():
    assert try_float("unavailable") is None
    assert try_float(None) is None
    assert try_float("") is None


# --------------------------- clean_data ---------------------------

def test_clean_data_strips_none_and_empty():
    out = clean_data({"a": "x", "b": "", "c": None, "d": 0, "e": False})
    # 0 und False sind gültige Werte und müssen erhalten bleiben.
    assert out == {"a": "x", "d": 0, "e": False}


def test_clean_data_empty_input():
    assert clean_data({}) == {}


# --------------------------- needs_time_based ---------------------------

NOW = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_needs_time_based_never_watered_returns_true():
    assert needs_time_based(None, 7, NOW) is True


def test_needs_time_based_garbage_iso_returns_false():
    # Unparseable → "wir haben irgendwas, gehen davon aus dass gepflegt wurde"
    assert needs_time_based("kaputt", 7, NOW) is False


def test_needs_time_based_days_zero_returns_false():
    # Intervall=0 → Pflege deaktiviert, sofern jemals durchgeführt.
    ts = (NOW - timedelta(days=100)).isoformat()
    assert needs_time_based(ts, 0, NOW) is False


def test_needs_time_based_days_none_returns_false_when_watered():
    ts = (NOW - timedelta(days=100)).isoformat()
    assert needs_time_based(ts, None, NOW) is False


def test_needs_time_based_not_yet_due():
    ts = (NOW - timedelta(days=3)).isoformat()
    assert needs_time_based(ts, 7, NOW) is False


def test_needs_time_based_exactly_due():
    ts = (NOW - timedelta(days=7)).isoformat()
    assert needs_time_based(ts, 7, NOW) is True


def test_needs_time_based_overdue():
    ts = (NOW - timedelta(days=14)).isoformat()
    assert needs_time_based(ts, 7, NOW) is True


# --------------------------- utcnow_iso ---------------------------

# --------------------------- parse_time_string ---------------------------

def test_parse_time_string_hhmm():
    assert parse_time_string("22:00") == dt_time(22, 0)


def test_parse_time_string_hhmmss():
    assert parse_time_string("08:15:30") == dt_time(8, 15, 30)


def test_parse_time_string_invalid():
    assert parse_time_string(None) is None
    assert parse_time_string("") is None
    assert parse_time_string("abc") is None
    assert parse_time_string("25:00") is None


# --------------------------- is_in_quiet_hours ---------------------------

def test_quiet_hours_disabled_when_unset():
    assert is_in_quiet_hours(dt_time(3, 0), None, dt_time(8, 0)) is False
    assert is_in_quiet_hours(dt_time(3, 0), dt_time(22, 0), None) is False


def test_quiet_hours_disabled_when_equal():
    # start == end → kein Fenster
    assert is_in_quiet_hours(dt_time(12, 0), dt_time(8, 0), dt_time(8, 0)) is False


def test_quiet_hours_simple_daytime_window():
    # Quiet 08:00–22:00 (kein Wrap)
    start, end = dt_time(8, 0), dt_time(22, 0)
    assert is_in_quiet_hours(dt_time(7, 59), start, end) is False
    assert is_in_quiet_hours(dt_time(8, 0), start, end) is True
    assert is_in_quiet_hours(dt_time(15, 0), start, end) is True
    assert is_in_quiet_hours(dt_time(21, 59), start, end) is True
    assert is_in_quiet_hours(dt_time(22, 0), start, end) is False


def test_quiet_hours_wrap_over_midnight():
    # Quiet 22:00–08:00 (Wrap)
    start, end = dt_time(22, 0), dt_time(8, 0)
    assert is_in_quiet_hours(dt_time(22, 0), start, end) is True
    assert is_in_quiet_hours(dt_time(23, 30), start, end) is True
    assert is_in_quiet_hours(dt_time(0, 0), start, end) is True
    assert is_in_quiet_hours(dt_time(7, 59), start, end) is True
    assert is_in_quiet_hours(dt_time(8, 0), start, end) is False
    assert is_in_quiet_hours(dt_time(12, 0), start, end) is False
    assert is_in_quiet_hours(dt_time(21, 59), start, end) is False


# --------------------------- is_rate_limited ---------------------------

def test_rate_limit_disabled_when_zero_hours():
    assert is_rate_limited("2026-05-24T11:00:00+00:00", 0, NOW) is False


def test_rate_limit_disabled_when_never_notified():
    assert is_rate_limited(None, 12, NOW) is False
    assert is_rate_limited("", 12, NOW) is False


def test_rate_limit_within_window():
    last = (NOW - timedelta(hours=3)).isoformat()
    assert is_rate_limited(last, 12, NOW) is True


def test_rate_limit_outside_window():
    last = (NOW - timedelta(hours=13)).isoformat()
    assert is_rate_limited(last, 12, NOW) is False


def test_rate_limit_garbage_returns_false():
    assert is_rate_limited("kaputt", 12, NOW) is False


# --------------------------- utcnow_iso ---------------------------

# --------------------------- parse_action_id ---------------------------

def test_parse_action_id_water():
    assert parse_action_id("PLANTCARE_WATER_abc123") == ("WATER", "abc123")


def test_parse_action_id_fertilize():
    assert parse_action_id("PLANTCARE_FERTILIZE_xy9") == ("FERTILIZE", "xy9")


def test_parse_action_id_snooze():
    assert parse_action_id("PLANTCARE_SNOOZE_abc") == ("SNOOZE", "abc")


def test_parse_action_id_unknown_action_passes_through():
    # Parser tolerant – Dispatcher filtert.
    assert parse_action_id("PLANTCARE_FOO_abc") == ("FOO", "abc")


def test_parse_action_id_wrong_prefix_returns_none():
    assert parse_action_id("OTHER_WATER_abc") is None


def test_parse_action_id_too_few_segments_returns_none():
    assert parse_action_id("PLANTCARE_WATER") is None
    assert parse_action_id("PLANTCARE") is None
    assert parse_action_id("") is None


def test_parse_action_id_plant_id_with_underscore():
    assert parse_action_id("PLANTCARE_WATER_ab_cd") == ("WATER", "ab_cd")


# --------------------- compute_snooze_last_notified ---------------------

def test_compute_snooze_no_rate_limit():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=0)
    assert result == NOW + timedelta(hours=24)


def test_compute_snooze_with_smaller_rate_limit():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=12)
    assert result == NOW + timedelta(hours=12)


def test_compute_snooze_with_equal_rate_limit():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=24)
    assert result == NOW


def test_compute_snooze_with_larger_rate_limit():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=48)
    assert result == NOW


def test_compute_snooze_negative_rate_limit_treated_as_zero():
    result = compute_snooze_last_notified(NOW, snooze_hours=24, rate_limit_hours=-5)
    assert result == NOW + timedelta(hours=24)


# --------------------------- sort_photos ---------------------------

def test_sort_photos_empty():
    assert sort_photos([]) == []


def test_sort_photos_descending_by_taken_at():
    photos = [
        {"path": "/a.jpg", "taken_at": "2026-01-01T00:00:00+00:00"},
        {"path": "/b.jpg", "taken_at": "2026-05-01T00:00:00+00:00"},
        {"path": "/c.jpg", "taken_at": "2026-03-01T00:00:00+00:00"},
    ]
    result = sort_photos(photos)
    assert [p["path"] for p in result] == ["/b.jpg", "/c.jpg", "/a.jpg"]


def test_sort_photos_missing_taken_at_goes_last():
    photos = [
        {"path": "/old.jpg", "taken_at": "2026-01-01T00:00:00+00:00"},
        {"path": "/notime.jpg"},
        {"path": "/new.jpg", "taken_at": "2026-05-01T00:00:00+00:00"},
    ]
    result = sort_photos(photos)
    assert [p["path"] for p in result] == ["/new.jpg", "/old.jpg", "/notime.jpg"]


# --------------------- migrate_legacy_photo ---------------------

def test_migrate_legacy_photo_no_photo_creates_empty_list():
    plant = {"name": "X"}
    assert migrate_legacy_photo(plant) is True
    assert plant["photos"] == []


def test_migrate_legacy_photo_with_path_creates_entry():
    plant = {"name": "X", "photo": "/api/p.jpg", "created": "2026-01-01T00:00:00+00:00"}
    assert migrate_legacy_photo(plant) is True
    assert plant["photos"] == [
        {"path": "/api/p.jpg", "taken_at": "2026-01-01T00:00:00+00:00", "note": ""}
    ]


def test_migrate_legacy_photo_idempotent():
    plant = {"name": "X", "photos": [{"path": "/x.jpg", "taken_at": "2026-01-01T00:00:00+00:00", "note": ""}]}
    assert migrate_legacy_photo(plant) is False


# --------------------------- cap_photos ---------------------------

def test_cap_photos_under_limit():
    photos = [{"path": f"/{i}.jpg"} for i in range(3)]
    kept, removed = cap_photos(photos, max_count=5)
    assert kept == photos
    assert removed == []


def test_cap_photos_over_limit_keeps_newest():
    photos = [
        {"path": "/new.jpg"},
        {"path": "/mid.jpg"},
        {"path": "/old1.jpg"},
        {"path": "/old2.jpg"},
    ]
    kept, removed = cap_photos(photos, max_count=2)
    assert [p["path"] for p in kept] == ["/new.jpg", "/mid.jpg"]
    assert [p["path"] for p in removed] == ["/old1.jpg", "/old2.jpg"]


# --------------------------- Treatments ---------------------------

def test_filter_open_treatments_empty():
    assert filter_open_treatments([]) == []


def test_filter_open_treatments_only_open():
    treatments = [
        {"id": "a", "status": "open"},
        {"id": "b", "status": "resolved"},
        {"id": "c", "status": "open"},
    ]
    result = filter_open_treatments(treatments)
    assert [t["id"] for t in result] == ["a", "c"]


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


def test_parse_treatment_action_id_unknown_action_returns_none():
    assert parse_treatment_action_id("PLANTCARE_WATER_abc") is None


def test_parse_treatment_action_id_missing_treatment_returns_none():
    assert parse_treatment_action_id("PLANTCARE_RESOLVE_onlyplant") is None


def test_utcnow_iso_returns_parseable_utc_string():
    s = utcnow_iso()
    parsed = parse_iso(s)
    assert parsed is not None
    assert parsed.tzinfo is not None
    # Sollte recht aktuell sein.
    delta = abs((parsed - datetime.now(timezone.utc)).total_seconds())
    assert delta < 5
