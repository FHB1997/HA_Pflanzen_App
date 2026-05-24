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

from ._utils import needs_time_based, try_float
from .const import (
    DOMAIN,
    MOISTURE_LOW_PCT,
    MOISTURE_OK_PCT,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
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

        # 1) Zeit-basiert für Wasser
        needs_water = needs_time_based(
            plant.get("last_watered"), plant.get("water_days"), now
        )

        # 2) Moisture-Sensor Override
        moisture_pct = self._read_moisture(plant.get("moisture_sensor"))
        if moisture_pct is not None:
            if moisture_pct < MOISTURE_LOW_PCT:
                needs_water = True
            elif moisture_pct > MOISTURE_OK_PCT:
                needs_water = False

        # 3) Zeit-basiert für Dünger
        needs_fertilizer = needs_time_based(
            plant.get("last_fertilized"), plant.get("fertilize_days"), now
        )

        if needs_water and needs_fertilizer:
            return STATUS_NEEDS_BOTH
        if needs_water:
            return STATUS_NEEDS_WATER
        if needs_fertilizer:
            return STATUS_NEEDS_FERTILIZER
        return STATUS_OK

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
            "tips": plant.get("tips", ""),
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
