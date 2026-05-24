"""Coordinator: Datenhaltung und Persistenz für Plant Care."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_WATER_DAYS,
    HISTORY_MAX_ENTRIES,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY_SECONDS = 1.0


def _utcnow_iso() -> str:
    """Aktueller UTC-Zeitstempel als ISO-8601 String."""
    return datetime.now(timezone.utc).isoformat()


class PlantCareCoordinator:
    """Hält den Plants-Dict im Speicher und persistiert via HA Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._plants: dict[str, dict[str, Any]] = {}

    @property
    def plants(self) -> dict[str, dict[str, Any]]:
        """Liefert den aktuellen Plants-Dict (read-only Sicht)."""
        return self._plants

    async def async_load(self) -> None:
        """Lädt Pflanzen aus dem Store."""
        data = await self._store.async_load() or {}
        plants = data.get("plants", {}) if isinstance(data, dict) else {}
        # Safety-Net: fehlende Felder ergänzen, falls alte Storage-Daten existieren.
        for pid, plant in plants.items():
            plant.setdefault("id", pid)
            plant.setdefault("water_history", [])
            plant.setdefault("fertilize_history", [])
            plant.setdefault("water_days", DEFAULT_WATER_DAYS)
            plant.setdefault("fertilize_days", DEFAULT_FERTILIZE_DAYS)
        self._plants = plants
        _LOGGER.info("Plant Care: %d Pflanzen geladen", len(self._plants))

    def _data_to_save(self) -> dict[str, Any]:
        return {"plants": self._plants}

    async def _async_save_now(self) -> None:
        """Sofortiges Speichern (für User-Events wie water/fertilize)."""
        await self._store.async_save(self._data_to_save())

    def _async_save_delayed(self) -> None:
        """Verzögertes Speichern (coalesced Form-Edits)."""
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_SECONDS)

    @staticmethod
    def _new_plant_id() -> str:
        return uuid.uuid4().hex[:8]

    @staticmethod
    def _clean(data: dict[str, Any]) -> dict[str, Any]:
        """Entfernt None-Werte und leere Strings aus eingehenden Daten."""
        return {k: v for k, v in data.items() if v is not None and v != ""}

    async def async_add_plant(self, data: dict[str, Any]) -> str:
        """Legt eine neue Pflanze an. Gibt die plant_id zurück."""
        plant_id = self._new_plant_id()
        now = _utcnow_iso()
        cleaned = self._clean(data)
        plant: dict[str, Any] = {
            "id": plant_id,
            "name": cleaned.get("name", "Unbenannte Pflanze"),
            "species": cleaned.get("species", ""),
            "common_name": cleaned.get("common_name", ""),
            "location": cleaned.get("location", ""),
            "water_days": int(cleaned.get("water_days", DEFAULT_WATER_DAYS)),
            "fertilize_days": int(cleaned.get("fertilize_days", DEFAULT_FERTILIZE_DAYS)),
            "moisture_sensor": cleaned.get("moisture_sensor"),
            "photo": cleaned.get("photo", ""),
            "tips": cleaned.get("tips", ""),
            "last_watered": cleaned.get("last_watered"),
            "last_fertilized": cleaned.get("last_fertilized"),
            "water_history": [],
            "fertilize_history": [],
            "created": now,
        }
        self._plants[plant_id] = plant
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_NEW_PLANT, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s angelegt (%s)", plant_id, plant["name"])
        return plant_id

    async def async_update_plant(self, plant_id: str, data: dict[str, Any]) -> None:
        """Aktualisiert Felder einer Pflanze (Merge)."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        cleaned = self._clean({k: v for k, v in data.items() if k != "plant_id"})
        # int-Felder typisieren
        for k in ("water_days", "fertilize_days"):
            if k in cleaned:
                cleaned[k] = int(cleaned[k])
        self._plants[plant_id].update(cleaned)
        self._async_save_delayed()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s aktualisiert", plant_id)

    async def async_remove_plant(self, plant_id: str) -> None:
        """Löscht eine Pflanze."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        del self._plants[plant_id]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_REMOVE_PLANT, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s entfernt", plant_id)

    async def async_water_plant(
        self, plant_id: str, timestamp: datetime | None = None
    ) -> None:
        """Markiert eine Pflanze als gegossen."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        plant = self._plants[plant_id]
        plant["last_watered"] = ts
        history = plant.setdefault("water_history", [])
        history.insert(0, ts)
        plant["water_history"] = history[:HISTORY_MAX_ENTRIES]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s gegossen (%s)", plant_id, ts)

    async def async_fertilize_plant(
        self, plant_id: str, timestamp: datetime | None = None
    ) -> None:
        """Markiert eine Pflanze als gedüngt."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        plant = self._plants[plant_id]
        plant["last_fertilized"] = ts
        history = plant.setdefault("fertilize_history", [])
        history.insert(0, ts)
        plant["fertilize_history"] = history[:HISTORY_MAX_ENTRIES]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s gedüngt (%s)", plant_id, ts)
