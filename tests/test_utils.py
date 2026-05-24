"""Smoke-Tests für custom_components.plant_care._utils.

Diese Tests laufen ohne Home-Assistant-Stack, da ``_utils`` bewusst
keine HA-Imports enthält. ``conftest.py`` legt den passenden sys.path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from _utils import (  # type: ignore[import-not-found]
    clean_data,
    needs_time_based,
    parse_iso,
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

def test_utcnow_iso_returns_parseable_utc_string():
    s = utcnow_iso()
    parsed = parse_iso(s)
    assert parsed is not None
    assert parsed.tzinfo is not None
    # Sollte recht aktuell sein.
    delta = abs((parsed - datetime.now(timezone.utc)).total_seconds())
    assert delta < 5
