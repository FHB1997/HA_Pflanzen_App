"""Konstanten für die Plant Care Integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "plant_care"
PLATFORMS: Final = ["sensor"]

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

# Foto-Storage (Phase 2.1 + Scaling-Stub in Phase 1)
PHOTOS_DIRNAME: Final = "plant_care_photos"
PHOTOS_URL_PATH: Final = "/api/plant_care/photos"
UPLOAD_URL_PATH: Final = "/api/plant_care/upload"

# History – muss zum Chart-Span im Frontend passen (plant-care-panel.js
# CHART_DAY_SPAN). Bei einem Event/Tag deckt 90 die volle Chart-Breite ab.
HISTORY_MAX_ENTRIES: Final = 90

# Service-Namen
SERVICE_ADD_PLANT: Final = "add_plant"
SERVICE_UPDATE_PLANT: Final = "update_plant"
SERVICE_REMOVE_PLANT: Final = "remove_plant"
SERVICE_WATER_PLANT: Final = "water_plant"
SERVICE_FERTILIZE_PLANT: Final = "fertilize_plant"
SERVICE_SEND_REMINDERS: Final = "send_reminders"

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
ROOM_TYPES: Final = (
    "wohnzimmer",
    "schlafzimmer",
    "kueche",
    "bad",
    "buero",
    "flur",
    "kinderzimmer",
)
