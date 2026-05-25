"""Konstanten für die Plant Care Integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "plant_care"
PLATFORMS: Final = ["sensor", "calendar"]

# Storage
STORAGE_KEY: Final = f"{DOMAIN}.plants"
STORAGE_VERSION: Final = 1

# Dispatcher-Signals
SIGNAL_PLANTS_UPDATED: Final = f"{DOMAIN}_plants_updated"
SIGNAL_NEW_PLANT: Final = f"{DOMAIN}_new_plant"
SIGNAL_REMOVE_PLANT: Final = f"{DOMAIN}_remove_plant"

# Frontend / Panel
PANEL_FRONTEND_URL_PATH: Final = "plant-care"
PANEL_STATIC_PATH: Final = "/plant_care_frontend"
PANEL_MODULE_URL: Final = f"{PANEL_STATIC_PATH}/plant-care-panel.js"
PANEL_TITLE: Final = "Plant Care"
PANEL_ICON: Final = "mdi:flower"

# Moisture-Sensor Schwellen (Prozent)
MOISTURE_LOW_PCT: Final = 20
MOISTURE_OK_PCT: Final = 50

# Status-Werte
STATUS_OK: Final = "ok"
STATUS_NEEDS_WATER: Final = "needs_water"
STATUS_NEEDS_FERTILIZER: Final = "needs_fertilizer"
STATUS_NEEDS_BOTH: Final = "needs_both"
STATUS_NEEDS_ATTENTION: Final = "needs_attention"  # höchste Priorität (Treatments)

# Foto-Storage (Phase 2.1 + Scaling-Stub in Phase 1)
PHOTOS_DIRNAME: Final = "plant_care_photos"
PHOTOS_URL_PATH: Final = "/api/plant_care/photos"
UPLOAD_URL_PATH: Final = "/api/plant_care/upload"

# History – muss zum Chart-Span im Frontend passen (plant-care-panel.js
# CHART_DAY_SPAN). Bei einem Event/Tag deckt 90 die volle Chart-Breite ab.
HISTORY_MAX_ENTRIES: Final = 90

# Foto-Verlauf
MAX_PHOTOS_PER_PLANT: Final = 100

# Service-Namen (Foto-Verlauf)
SERVICE_ADD_PLANT_PHOTO: Final = "add_plant_photo"
SERVICE_REMOVE_PLANT_PHOTO: Final = "remove_plant_photo"

# Treatment-Service-Namen
SERVICE_DIAGNOSE_PLANT: Final = "diagnose_plant"
SERVICE_RESOLVE_TREATMENT: Final = "resolve_treatment"

# Calendar-Service
SERVICE_GET_EVENTS: Final = "get_events"

# Anti-Spam für AI-Diagnose
MIN_DIAGNOSE_INTERVAL_SECONDS: Final = 60

# Service-Namen
SERVICE_ADD_PLANT: Final = "add_plant"
SERVICE_UPDATE_PLANT: Final = "update_plant"
SERVICE_REMOVE_PLANT: Final = "remove_plant"
SERVICE_WATER_PLANT: Final = "water_plant"
SERVICE_FERTILIZE_PLANT: Final = "fertilize_plant"
SERVICE_SEND_REMINDERS: Final = "send_reminders"
SERVICE_SEND_TEST_NOTIFICATION: Final = "send_test_notification"

# Options-Flow Helper-Feld (kein persistierter Config-Key)
OPT_SEND_TEST: Final = "send_test"

# Default-Intervalle (Tage)
DEFAULT_WATER_DAYS: Final = 7
DEFAULT_FERTILIZE_DAYS: Final = 30

# Reminder-Options (config_entry.options)
CONF_REMINDERS_ENABLED: Final = "reminders_enabled"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_QUIET_HOURS_START: Final = "quiet_hours_start"
CONF_QUIET_HOURS_END: Final = "quiet_hours_end"
CONF_RATE_LIMIT_HOURS: Final = "rate_limit_hours"
CONF_NOTIFY_TITLE: Final = "notify_title"

DEFAULT_QUIET_HOURS_START: Final = "22:00:00"
DEFAULT_QUIET_HOURS_END: Final = "08:00:00"
DEFAULT_RATE_LIMIT_HOURS: Final = 12
DEFAULT_NOTIFY_TITLE: Final = "Plant Care"

# Wie oft scannt der Hintergrund-Job die Pflanzen?
REMINDER_SCAN_INTERVAL_MINUTES: Final = 30

# Actionable Notifications
ACTION_ID_PREFIX: Final = "PLANTCARE"
SNOOZE_DEFAULT_HOURS: Final = 24

# Standort/Licht (Sprint 6)
LIGHT_LEVELS: Final = ("vollsonne", "hell", "halbschatten", "schatten")
ROOM_TYPES_INDOOR: Final = (
    "wohnzimmer",
    "schlafzimmer",
    "kueche",
    "bad",
    "buero",
    "flur",
    "kinderzimmer",
)
ROOM_TYPES_OUTDOOR: Final = (
    "balkon",
    "terrasse",
    "garten",
    "vorgarten",
    "gewaechshaus",
)
# Union für Schema-Validierung (Reihenfolge egal).
ROOM_TYPES: Final = ROOM_TYPES_INDOOR + ROOM_TYPES_OUTDOOR

# Plant-Kind
PLANT_KIND_INDOOR: Final = "indoor"
PLANT_KIND_OUTDOOR: Final = "outdoor"
PLANT_KINDS: Final = (PLANT_KIND_INDOOR, PLANT_KIND_OUTDOOR)

# Saison-Multiplikatoren – nur für Outdoor-Pflanzen.
# Index = Monat (1-12). Wert wird mit dem konfigurierten *_days multipliziert.
# Winter länger, Sommer kürzer; Düngen pausiert in den Wintermonaten (0).
SEASON_WATER_MULT: Final = {
    1: 3.0, 2: 3.0, 12: 3.0,
    3: 1.2, 4: 1.0, 5: 1.0,
    6: 0.7, 7: 0.7, 8: 0.7,
    9: 1.0, 10: 1.3, 11: 2.0,
}
SEASON_FERTILIZE_MULT: Final = {
    1: 0.0, 2: 0.0, 12: 0.0,
    3: 1.5, 4: 1.0, 5: 1.0,
    6: 1.0, 7: 1.0, 8: 1.0,
    9: 1.2, 10: 2.0, 11: 0.0,
}
WINTER_REST_MONTHS: Final = (12, 1, 2)

# Wetter-Awareness
CONF_WEATHER_ENTITY: Final = "weather_entity"
RAIN_THRESHOLD_MM: Final = 1.0          # ab diesem Tagesniederschlag gilt's als "geregnet"
FROST_THRESHOLD_C: Final = 0.0          # Tief unter diesem Wert → Frost-Alarm
FROST_FORECAST_HOURS: Final = 24        # so weit in die Zukunft schauen
FROST_NOTIFY_COOLDOWN_HOURS: Final = 18 # Rate-Limit pro Pflanze
