"""Plant Care – Custom Integration für Home Assistant.

Setup, Service-Registration, Panel-Registration und statische Pfade.
"""
from __future__ import annotations

import logging
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from ._utils import parse_action_id, parse_treatment_action_id
from .const import (
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_WATER_DAYS,
    DOMAIN,
    LIGHT_LEVELS,
    PANEL_FRONTEND_URL_PATH,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_STATIC_PATH,
    PANEL_TITLE,
    PHOTOS_URL_PATH,
    PLATFORMS,
    REMINDER_SCAN_INTERVAL_MINUTES,
    SERVICE_ADD_PLANT,
    SERVICE_ADD_PLANT_PHOTO,
    SERVICE_DIAGNOSE_PLANT,
    SERVICE_FERTILIZE_PLANT,
    SERVICE_GET_EVENTS,
    SERVICE_REMOVE_PLANT,
    SERVICE_REMOVE_PLANT_PHOTO,
    SERVICE_RESOLVE_TREATMENT,
    SERVICE_SEND_REMINDERS,
    SERVICE_UPDATE_PLANT,
    SERVICE_WATER_PLANT,
)
from .coordinator import PlantCareCoordinator
from .http import PlantPhotoUploadView, get_photos_dir, save_uploaded_photo

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ADD_PLANT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("species", default=""): cv.string,
        vol.Optional("common_name", default=""): cv.string,
        vol.Optional("location", default=""): cv.string,
        vol.Optional("water_days", default=DEFAULT_WATER_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=90)
        ),
        vol.Optional("fertilize_days", default=DEFAULT_FERTILIZE_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=180)
        ),
        vol.Optional("moisture_sensor"): vol.Any(None, "", cv.entity_id),
        vol.Optional("photo", default=""): cv.string,
        vol.Optional("tips", default=""): cv.string,
        vol.Optional("light_level", default=""): vol.In(["", *LIGHT_LEVELS]),
        vol.Optional("room_type", default=""): cv.string,
        vol.Optional("location_tips", default=""): cv.string,
        vol.Optional("suitability_warning", default=""): cv.string,
    }
)

UPDATE_PLANT_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("species"): cv.string,
        vol.Optional("common_name"): cv.string,
        vol.Optional("location"): cv.string,
        vol.Optional("water_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
        vol.Optional("fertilize_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
        vol.Optional("moisture_sensor"): vol.Any(None, "", cv.entity_id),
        vol.Optional("photo"): cv.string,
        vol.Optional("tips"): cv.string,
        vol.Optional("light_level"): vol.In(["", *LIGHT_LEVELS]),
        vol.Optional("room_type"): cv.string,
        vol.Optional("location_tips"): cv.string,
        vol.Optional("suitability_warning"): cv.string,
    }
)

PLANT_ID_SCHEMA = vol.Schema({vol.Required("plant_id"): cv.string})

WATER_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Optional("timestamp"): cv.datetime,
    }
)

SEND_REMINDERS_SCHEMA = vol.Schema(
    {
        vol.Optional("plant_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

ADD_PLANT_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Exclusive("path", "source"): cv.string,
        vol.Exclusive("image_base64", "source"): cv.string,
        vol.Optional("mime", default="image/jpeg"): cv.string,
        vol.Optional("note", default=""): cv.string,
        vol.Optional("taken_at"): cv.datetime,
    }
)

REMOVE_PLANT_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("path"): cv.string,
        vol.Optional("keep_file", default=False): cv.boolean,
    }
)

DIAGNOSE_PLANT_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("photo_path"): cv.string,
        vol.Required("ai_response"): dict,
    }
)

RESOLVE_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("treatment_id"): cv.string,
        vol.Optional("outcome", default="resolved"): vol.In(["resolved", "dismissed"]),
    }
)

GET_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Optional("start"): cv.datetime,
        vol.Optional("end"): cv.datetime,
        vol.Optional("plant_id"): cv.string,
        vol.Optional("days", default=14): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup einer Plant-Care-Instanz."""
    coord = PlantCareCoordinator(hass)
    await coord.async_load()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coord
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    # Sensor-Plattform laden
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Static Paths registrieren (Frontend-JS + Foto-Verzeichnis)
    component_dir = pathlib.Path(__file__).parent
    frontend_dir = component_dir / "frontend"
    photos_dir = get_photos_dir(hass)

    def _ensure_photos_dir() -> None:
        photos_dir.mkdir(parents=True, exist_ok=True)

    await hass.async_add_executor_job(_ensure_photos_dir)

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(PANEL_STATIC_PATH, str(frontend_dir), cache_headers=False),
            StaticPathConfig(PHOTOS_URL_PATH, str(photos_dir), cache_headers=False),
        ]
    )

    # HTTP-View (Phase 2.1) registrieren
    hass.http.register_view(PlantPhotoUploadView(hass))

    # Periodischer Scan für integrierte Pflege-Erinnerungen.
    async def _reminder_tick(_now: Any) -> None:
        try:
            await coord.evaluate_reminders(entry.options)
        except Exception:  # noqa: BLE001 – Tick darf nie crashen
            _LOGGER.exception("Plant Care: Reminder-Scan fehlgeschlagen")

    cancel_tick = async_track_time_interval(
        hass,
        _reminder_tick,
        timedelta(minutes=REMINDER_SCAN_INTERVAL_MINUTES),
    )
    hass.data[DOMAIN]["cancel_tick"] = cancel_tick

    # Coordinator braucht entry-Zugriff für async_snooze_plant.
    coord.bind_entry(entry)

    @callback
    def _handle_action_event(event: Event) -> None:
        raw_id = event.data.get("action", "")

        # Treatment-Actions zuerst prüfen (eigenes ID-Format mit treatment_id).
        treatment_parsed = parse_treatment_action_id(raw_id)
        if treatment_parsed is not None:
            t_action, plant_id_t, treatment_id_t = treatment_parsed
            outcome = "resolved" if t_action == "RESOLVE" else "dismissed"
            async def _dispatch_treatment() -> None:
                try:
                    await coord.async_resolve_treatment(
                        plant_id_t, treatment_id_t, outcome
                    )
                except ValueError:
                    _LOGGER.debug(
                        "Plant Care: Treatment-Action %s für unbekannte ID %s/%s",
                        t_action, plant_id_t, treatment_id_t,
                    )
            hass.async_create_task(_dispatch_treatment())
            return

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

    # Panel registrieren
    try:
        frontend.async_register_built_in_panel(
            hass,
            "custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_FRONTEND_URL_PATH,
            config={
                "_panel_custom": {
                    "name": "plant-care-panel",
                    "module_url": PANEL_MODULE_URL,
                    "embed_iframe": False,
                    "trust_external": False,
                },
            },
            require_admin=False,
        )
    except ValueError:
        _LOGGER.debug("Panel war bereits registriert")

    _register_services(hass, entry, coord)

    return True


def _register_services(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: PlantCareCoordinator,
) -> None:
    """Registriert die Plant-Care-Services."""

    async def handle_add_plant(call: ServiceCall) -> ServiceResponse:
        plant_id = await coord.async_add_plant(dict(call.data))
        return {"plant_id": plant_id}

    async def handle_update_plant(call: ServiceCall) -> None:
        data = dict(call.data)
        plant_id = data.pop("plant_id")
        await coord.async_update_plant(plant_id, data)

    async def handle_remove_plant(call: ServiceCall) -> None:
        await coord.async_remove_plant(call.data["plant_id"])

    async def handle_water_plant(call: ServiceCall) -> None:
        await coord.async_water_plant(
            call.data["plant_id"], call.data.get("timestamp")
        )

    async def handle_fertilize_plant(call: ServiceCall) -> None:
        await coord.async_fertilize_plant(
            call.data["plant_id"], call.data.get("timestamp")
        )

    async def handle_send_reminders(call: ServiceCall) -> ServiceResponse:
        sent = await coord.evaluate_reminders(
            entry.options,
            only_plant_id=call.data.get("plant_id"),
            force=bool(call.data.get("force", False)),
        )
        return {"sent": sent}

    async def handle_add_plant_photo(call: ServiceCall) -> ServiceResponse:
        data = dict(call.data)
        plant_id = data["plant_id"]
        path = data.get("path")
        image_base64 = data.get("image_base64")
        if not path and not image_base64:
            raise vol.Invalid("Entweder path oder image_base64 muss gesetzt sein")
        if not path and image_base64:
            try:
                path = await save_uploaded_photo(
                    hass, image_base64, data.get("mime", "image/jpeg")
                )
            except ValueError as err:
                raise vol.Invalid(str(err)) from err
        return await coord.async_add_plant_photo(
            plant_id=plant_id,
            path=path,
            note=data.get("note", ""),
            taken_at=data.get("taken_at"),
        )

    async def handle_remove_plant_photo(call: ServiceCall) -> None:
        await coord.async_remove_plant_photo(
            plant_id=call.data["plant_id"],
            path=call.data["path"],
            keep_file=bool(call.data.get("keep_file", False)),
        )

    async def handle_diagnose_plant(call: ServiceCall) -> ServiceResponse:
        return await coord.async_diagnose_plant(
            plant_id=call.data["plant_id"],
            photo_path=call.data["photo_path"],
            ai_response=call.data["ai_response"],
        )

    async def handle_resolve_treatment(call: ServiceCall) -> ServiceResponse:
        return await coord.async_resolve_treatment(
            plant_id=call.data["plant_id"],
            treatment_id=call.data["treatment_id"],
            outcome=call.data.get("outcome", "resolved"),
        )

    async def handle_get_events(call: ServiceCall) -> ServiceResponse:
        data = dict(call.data)
        now = datetime.now(timezone.utc)
        start = data.get("start") or now
        end = data.get("end")
        if end is None:
            end = start + timedelta(days=int(data.get("days", 14) or 14))
        # Naive datetimes → als UTC interpretieren (HA's cv.datetime liefert
        # je nach Eingabe; wir normalisieren defensiv).
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        events = coord.get_care_events(
            start, end, only_plant_id=data.get("plant_id")
        )
        return {
            "events": [
                {
                    "plant_id": e["plant_id"],
                    "name": e["name"],
                    "kind": e["kind"],
                    "when": e["when"].isoformat(),
                    "original_when": e["original_when"].isoformat(),
                    "overdue": e["overdue"],
                }
                for e in events
            ]
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PLANT,
        handle_add_plant,
        schema=ADD_PLANT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_PLANT, handle_update_plant, schema=UPDATE_PLANT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_PLANT, handle_remove_plant, schema=PLANT_ID_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WATER_PLANT, handle_water_plant, schema=WATER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FERTILIZE_PLANT, handle_fertilize_plant, schema=WATER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_REMINDERS,
        handle_send_reminders,
        schema=SEND_REMINDERS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PLANT_PHOTO,
        handle_add_plant_photo,
        schema=ADD_PLANT_PHOTO_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PLANT_PHOTO,
        handle_remove_plant_photo,
        schema=REMOVE_PLANT_PHOTO_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DIAGNOSE_PLANT,
        handle_diagnose_plant,
        schema=DIAGNOSE_PLANT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE_TREATMENT,
        handle_resolve_treatment,
        schema=RESOLVE_TREATMENT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_EVENTS,
        handle_get_events,
        schema=GET_EVENTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Plant-Care-Instanz entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    cancel_tick = hass.data.get(DOMAIN, {}).get("cancel_tick")
    if cancel_tick is not None:
        cancel_tick()

    unsub_action = hass.data.get(DOMAIN, {}).get("unsub_action_listener")
    if unsub_action is not None:
        unsub_action()

    try:
        frontend.async_remove_panel(hass, PANEL_FRONTEND_URL_PATH)
    except (KeyError, ValueError):
        _LOGGER.debug("Panel war nicht registriert")

    for service in (
        SERVICE_ADD_PLANT,
        SERVICE_UPDATE_PLANT,
        SERVICE_REMOVE_PLANT,
        SERVICE_WATER_PLANT,
        SERVICE_FERTILIZE_PLANT,
        SERVICE_SEND_REMINDERS,
        SERVICE_ADD_PLANT_PHOTO,
        SERVICE_REMOVE_PLANT_PHOTO,
        SERVICE_DIAGNOSE_PLANT,
        SERVICE_RESOLVE_TREATMENT,
        SERVICE_GET_EVENTS,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)

    hass.data.pop(DOMAIN, None)
    return unload_ok
