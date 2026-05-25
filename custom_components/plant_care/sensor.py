"""Sensor-Platform: eine PlantSensor-Entity pro Pflanze."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ._utils import (
    effective_fertilize_days,
    effective_water_days,
    filter_open_treatments,
    has_frost_in_forecast,
    has_overdue_treatment,
    has_recent_rain,
    is_winter_rest_active,
    needs_time_based,
    try_float,
)
from .const import (
    CONF_WEATHER_ENTITY,
    DOMAIN,
    FROST_FORECAST_HOURS,
    FROST_THRESHOLD_C,
    MOISTURE_LOW_PCT,
    MOISTURE_OK_PCT,
    RAIN_THRESHOLD_MM,
    SEASON_FERTILIZE_MULT,
    SEASON_WATER_MULT,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    STATUS_NEEDS_ATTENTION,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
    WINTER_REST_MONTHS,
)
from .coordinator import PlantCareCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Erstellt Sensoren für alle vorhandenen Pflanzen und abonniert Signale."""
    coord: PlantCareCoordinator = hass.data[DOMAIN]["coordinator"]

    entities = [PlantSensor(coord, pid) for pid in coord.plants]
    async_add_entities(entities)

    @callback
    def _handle_new(plant_id: str) -> None:
        async_add_entities([PlantSensor(coord, plant_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_PLANT, _handle_new)
    )


class PlantSensor(SensorEntity):
    """Eine Sensor-Entity pro Pflanze. State = Status-String."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    # Diese Arrays sind groß und ändern sich häufig – nicht in der
    # Recorder-DB persistieren, sonst bläst die SQLite über die Zeit auf.
    _unrecorded_attributes = frozenset(
        {"photos", "treatments", "water_history", "fertilize_history"}
    )

    def __init__(self, coordinator: PlantCareCoordinator, plant_id: str) -> None:
        self._coord = coordinator
        self._plant_id = plant_id
        self._attr_unique_id = f"{DOMAIN}_{plant_id}"
        self._attr_icon = "mdi:flower-outline"

    @property
    def _plant(self) -> dict[str, Any]:
        return self._coord.plants.get(self._plant_id, {})

    @property
    def name(self) -> str:
        plant_name = self._plant.get("name")
        return f"Plant {plant_name or self._plant_id}"

    @property
    def available(self) -> bool:
        return self._plant_id in self._coord.plants

    @property
    def native_value(self) -> str:
        """Berechnet den Status dynamisch (siehe PROJECT PLAN §2)."""
        plant = self._plant
        if not plant:
            return STATUS_OK
        now = datetime.now(timezone.utc)

        # 0) Treatment-Check hat Vorrang
        if has_overdue_treatment(plant.get("treatments") or [], now):
            return STATUS_NEEDS_ATTENTION

        # 0.5) Outdoor + Winterruhe → komplett ok, keine Reminder
        if is_winter_rest_active(plant, now, WINTER_REST_MONTHS):
            return STATUS_OK

        # 1) Zeit-basiert für Wasser (mit Saison-Faktor für Outdoor)
        eff_water = effective_water_days(
            plant, now, season_multipliers=SEASON_WATER_MULT
        )
        needs_water = needs_time_based(
            plant.get("last_watered"), eff_water, now
        )

        # 2) Moisture-Sensor Override (Indoor + Outdoor, gleich behandelt)
        moisture_pct = self._read_moisture(plant.get("moisture_sensor"))
        if moisture_pct is not None:
            if moisture_pct < MOISTURE_LOW_PCT:
                needs_water = True
            elif moisture_pct > MOISTURE_OK_PCT:
                needs_water = False

        # 2.5) Wetter-Override für Outdoor: Regen heute → kein Gießen nötig
        if (plant.get("plant_kind") or "indoor") == "outdoor":
            weather_state = self._read_weather()
            if weather_state is not None and has_recent_rain(
                weather_state, RAIN_THRESHOLD_MM
            ):
                needs_water = False

        # 3) Zeit-basiert für Dünger (mit Saison-Faktor für Outdoor)
        eff_fert = effective_fertilize_days(
            plant, now, season_multipliers=SEASON_FERTILIZE_MULT
        )
        needs_fertilizer = needs_time_based(
            plant.get("last_fertilized"), eff_fert, now
        )

        if needs_water and needs_fertilizer:
            return STATUS_NEEDS_BOTH
        if needs_water:
            return STATUS_NEEDS_WATER
        if needs_fertilizer:
            return STATUS_NEEDS_FERTILIZER
        return STATUS_OK

    def _read_weather(self) -> Any:
        """Holt die HA-Weather-Entity-State, falls in den Options gesetzt."""
        coord = self._coord
        entry = getattr(coord, "_entry", None)
        if entry is None:
            return None
        weather_entity = (entry.options.get(CONF_WEATHER_ENTITY) or "").strip()
        if not weather_entity:
            return None
        return self._coord.hass.states.get(weather_entity)

    def _read_moisture(self, sensor_entity_id: str | None) -> float | None:
        if not sensor_entity_id:
            return None
        state = self._coord.hass.states.get(sensor_entity_id)
        if state is None:
            return None
        return try_float(state.state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = self._plant
        moisture_pct = self._read_moisture(plant.get("moisture_sensor"))
        # Frost-Warnung als Attribut, damit das Frontend einen Banner zeigen kann.
        frost_warning = False
        if (
            (plant.get("plant_kind") or "indoor") == "outdoor"
            and plant.get("frost_sensitive")
        ):
            weather_state = self._read_weather()
            if weather_state is not None:
                forecast = (weather_state.attributes or {}).get("forecast") or []
                frost_warning = has_frost_in_forecast(
                    forecast,
                    datetime.now(timezone.utc),
                    horizon_hours=FROST_FORECAST_HOURS,
                    threshold_c=FROST_THRESHOLD_C,
                )
        return {
            "plant_id": self._plant_id,
            "name": plant.get("name"),
            "species": plant.get("species", ""),
            "common_name": plant.get("common_name", ""),
            "location": plant.get("location", ""),
            "water_days": plant.get("water_days"),
            "fertilize_days": plant.get("fertilize_days"),
            "last_watered": plant.get("last_watered"),
            "last_fertilized": plant.get("last_fertilized"),
            "moisture_sensor": plant.get("moisture_sensor"),
            "moisture_pct": moisture_pct,
            "photo": plant.get("photo", ""),
            "photos": plant.get("photos", []),
            "photos_count": len(plant.get("photos") or []),
            "light_level": plant.get("light_level", ""),
            "room_type": plant.get("room_type", ""),
            "suitability_warning": plant.get("suitability_warning", ""),
            "plant_description": plant.get("plant_description", ""),
            "plant_kind": plant.get("plant_kind", "indoor"),
            "frost_sensitive": bool(plant.get("frost_sensitive", False)),
            "winter_rest": bool(plant.get("winter_rest", False)),
            "frost_warning": frost_warning,
            "treatments": plant.get("treatments", []),
            "open_treatments_count": len(
                filter_open_treatments(plant.get("treatments") or [])
            ),
            "latest_treatment": (
                (plant.get("treatments") or [])[-1]
                if plant.get("treatments")
                else None
            ),
            "water_history": plant.get("water_history", []),
            "fertilize_history": plant.get("fertilize_history", []),
            "created": plant.get("created"),
        }

    async def async_added_to_hass(self) -> None:
        """Verbindet Dispatcher-Signale, wenn Entity hinzugefügt wird."""

        @callback
        def _handle_updated(plant_id: str) -> None:
            if plant_id == self._plant_id:
                self.async_write_ha_state()

        @callback
        def _handle_removed(plant_id: str) -> None:
            if plant_id == self._plant_id:
                self.hass.async_create_task(self.async_remove(force_remove=True))

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PLANTS_UPDATED, _handle_updated)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_REMOVE_PLANT, _handle_removed)
        )
