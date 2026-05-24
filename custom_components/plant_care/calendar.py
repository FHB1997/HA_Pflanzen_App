"""Calendar-Platform: aggregiert Pflege-Termine als HA-Calendar-Events."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
)
from .coordinator import PlantCareCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Eine einzelne Plant-Care-Calendar-Entity registrieren."""
    coord: PlantCareCoordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities([PlantCareCalendar(coord)])


class PlantCareCalendar(CalendarEntity):
    """Aggregierter Pflege-Kalender für alle Plant-Care-Pflanzen."""

    _attr_name = "Plant Care"
    _attr_icon = "mdi:flower"
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, coordinator: PlantCareCoordinator) -> None:
        self._coord = coordinator
        self._attr_unique_id = f"{DOMAIN}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """Nächstes anstehendes Pflege-Event (für die State-Card)."""
        now = datetime.now(timezone.utc)
        events = self._coord.get_care_events(now, now + timedelta(days=30))
        if not events:
            return None
        return self._to_calendar_event(events[0])

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Events im angefragten Zeitraum für Calendar-Card-Views."""
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        events = self._coord.get_care_events(start_date, end_date)
        return [self._to_calendar_event(e) for e in events]

    async def async_added_to_hass(self) -> None:
        """Bei Plant-Mutationen den Kalender re-rendern lassen."""

        @callback
        def _refresh(_event: Any = None) -> None:
            self.async_write_ha_state()

        for signal in (SIGNAL_NEW_PLANT, SIGNAL_PLANTS_UPDATED, SIGNAL_REMOVE_PLANT):
            self.async_on_remove(
                async_dispatcher_connect(self.hass, signal, _refresh)
            )

    @staticmethod
    def _to_calendar_event(event: dict[str, Any]) -> CalendarEvent:
        kind = event["kind"]
        icon = "💧" if kind == "water" else "🌱"
        action = "gießen" if kind == "water" else "düngen"
        summary = f"{icon} {event['name']} {action}"
        if event.get("overdue"):
            summary = f"⚠ {summary}"
        when = event["when"]
        return CalendarEvent(
            start=when,
            end=when + timedelta(minutes=30),
            summary=summary,
            description=f"Pflanze: {event['name']} (ID: {event['plant_id']})",
        )
