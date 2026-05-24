"""Plant Care – Custom Integration für Home Assistant.

Setup, Service-Registration, Panel-Registration und statische Pfade.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_WATER_DAYS,
    DOMAIN,
    PANEL_FRONTEND_URL_PATH,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_STATIC_PATH,
    PANEL_TITLE,
    PHOTOS_URL_PATH,
    PLATFORMS,
    SERVICE_ADD_PLANT,
    SERVICE_FERTILIZE_PLANT,
    SERVICE_REMOVE_PLANT,
    SERVICE_UPDATE_PLANT,
    SERVICE_WATER_PLANT,
)
from .coordinator import PlantCareCoordinator
from .http import PlantPhotoUploadView, get_photos_dir

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
        vol.Optional("moisture_sensor"): vol.Any(None, cv.entity_id),
        vol.Optional("photo", default=""): cv.string,
        vol.Optional("tips", default=""): cv.string,
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
        vol.Optional("moisture_sensor"): vol.Any(None, cv.entity_id),
        vol.Optional("photo"): cv.string,
        vol.Optional("tips"): cv.string,
    }
)

PLANT_ID_SCHEMA = vol.Schema({vol.Required("plant_id"): cv.string})

WATER_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Optional("timestamp"): cv.datetime,
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

    _register_services(hass, coord)

    return True


def _register_services(hass: HomeAssistant, coord: PlantCareCoordinator) -> None:
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Plant-Care-Instanz entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

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
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)

    hass.data.pop(DOMAIN, None)
    return unload_ok
