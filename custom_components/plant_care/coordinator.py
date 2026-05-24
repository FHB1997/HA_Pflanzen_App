"""Coordinator: Datenhaltung und Persistenz für Plant Care."""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ._utils import (
    clean_data,
    compute_snooze_last_notified,
    is_in_quiet_hours,
    is_rate_limited,
    parse_time_string,
    utcnow_iso,
)
from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TITLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RATE_LIMIT_HOURS,
    CONF_REMINDERS_ENABLED,
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_NOTIFY_TITLE,
    DEFAULT_WATER_DAYS,
    DOMAIN,
    HISTORY_MAX_ENTRIES,
    PHOTOS_URL_PATH,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    SNOOZE_DEFAULT_HOURS,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .http import get_photos_dir

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY_SECONDS = 1.0


class PlantCareCoordinator:
    """Hält den Plants-Dict im Speicher und persistiert via HA Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._plants: dict[str, dict[str, Any]] = {}
        self._entry: Any = None  # ConfigEntry, lazy bound via bind_entry

    def bind_entry(self, entry: Any) -> None:
        """Speichert die ConfigEntry-Referenz für Options-Zugriff.

        Wird vom Integration-Setup aufgerufen, damit der Coordinator
        Options (z.B. rate_limit_hours) lesen kann, ohne dass jeder
        Aufruf die Werte als Argument durchschleifen muss.
        """
        self._entry = entry

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
            plant.setdefault("last_notified", None)
            plant.setdefault("light_level", "")
            plant.setdefault("room_type", "")
            plant.setdefault("location_tips", "")
            plant.setdefault("suitability_warning", "")
        self._plants = plants

        migrated = await self._migrate_data_url_photos()
        if migrated:
            await self._async_save_now()
            _LOGGER.info(
                "Plant Care: %d data-URL-Fotos zu Dateien migriert", migrated
            )

        _LOGGER.info("Plant Care: %d Pflanzen geladen", len(self._plants))

    async def _migrate_data_url_photos(self) -> int:
        """Wandelt legacy ``data:image/...``-Fotos in echte Dateien um.

        Frühere Versionen haben Fotos als Base64-data-URL direkt im Plant-Dict
        abgelegt. Das bläst das Storage-JSON unnötig auf. Beim Laden werden
        diese Einträge einmalig in das Foto-Verzeichnis ausgelagert.
        """
        candidates = [
            (pid, plant)
            for pid, plant in self._plants.items()
            if isinstance(plant.get("photo"), str)
            and plant["photo"].startswith("data:image/")
        ]
        if not candidates:
            return 0

        photos_dir = get_photos_dir(self.hass)

        def _write_all() -> dict[str, str]:
            photos_dir.mkdir(parents=True, exist_ok=True)
            result: dict[str, str] = {}
            for pid, plant in candidates:
                data_url: str = plant["photo"]
                try:
                    header, b64 = data_url.split(",", 1)
                    mime = header.split(";", 1)[0].removeprefix("data:")
                    ext = (
                        "jpg"
                        if mime in ("image/jpeg", "image/jpg")
                        else mime.split("/", 1)[-1] or "bin"
                    )
                    payload = base64.b64decode(b64, validate=True)
                    fname = f"{uuid.uuid4().hex}.{ext}"
                    (photos_dir / fname).write_bytes(payload)
                    result[pid] = f"{PHOTOS_URL_PATH}/{fname}"
                except Exception as err:  # noqa: BLE001 – pro Pflanze isolieren
                    _LOGGER.warning(
                        "Plant Care: data-URL-Migration für %s fehlgeschlagen: %s",
                        pid,
                        err,
                    )
            return result

        new_paths = await self.hass.async_add_executor_job(_write_all)
        for pid, path in new_paths.items():
            self._plants[pid]["photo"] = path
        return len(new_paths)

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

    async def async_add_plant(self, data: dict[str, Any]) -> str:
        """Legt eine neue Pflanze an. Gibt die plant_id zurück."""
        plant_id = self._new_plant_id()
        now = utcnow_iso()
        cleaned = clean_data(data)
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
            "light_level": cleaned.get("light_level", ""),
            "room_type": cleaned.get("room_type", ""),
            "location_tips": cleaned.get("location_tips", ""),
            "suitability_warning": cleaned.get("suitability_warning", ""),
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
        """Aktualisiert Felder einer Pflanze (Merge).

        Im Gegensatz zu add_plant werden leere Strings hier NICHT gefiltert –
        sie bedeuten "User hat das Feld bewusst geleert". Nur ``None`` (= Feld
        gar nicht im Service-Call enthalten) wird ignoriert.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        cleaned: dict[str, Any] = {
            k: v for k, v in data.items() if k != "plant_id" and v is not None
        }
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
        """Markiert eine Pflanze als gegossen.

        Setzt zusätzlich ``last_notified`` zurück, damit ein zwischen-
        zeitlicher Snooze die nächste reguläre Reminder-Notification
        nicht unnötig blockiert.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        plant = self._plants[plant_id]
        plant["last_watered"] = ts
        plant["last_notified"] = None
        history = plant.setdefault("water_history", [])
        history.insert(0, ts)
        plant["water_history"] = history[:HISTORY_MAX_ENTRIES]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s gegossen (%s)", plant_id, ts)

    async def async_fertilize_plant(
        self, plant_id: str, timestamp: datetime | None = None
    ) -> None:
        """Markiert eine Pflanze als gedüngt.

        Setzt zusätzlich ``last_notified`` zurück, damit ein zwischen-
        zeitlicher Snooze die nächste reguläre Reminder-Notification
        nicht unnötig blockiert.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        plant = self._plants[plant_id]
        plant["last_fertilized"] = ts
        plant["last_notified"] = None
        history = plant.setdefault("fertilize_history", [])
        history.insert(0, ts)
        plant["fertilize_history"] = history[:HISTORY_MAX_ENTRIES]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s gedüngt (%s)", plant_id, ts)

    async def async_snooze_plant(
        self, plant_id: str, hours: int = SNOOZE_DEFAULT_HOURS
    ) -> None:
        """Verzögert die nächste Reminder-Notification um mind. ``hours``.

        Rate-Limit-Reset-Variante: setzt ``last_notified`` so weit in
        die Zukunft, dass der bestehende Rate-Limit-Mechanismus die
        nächste Notification um ``hours`` Stunden verzögert. Der
        Pflanzen-Status bleibt unverändert.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        rate_limit_hours = 0
        if self._entry is not None:
            rate_limit_hours = int(
                self._entry.options.get(CONF_RATE_LIMIT_HOURS) or 0
            )
        new_last_notified = compute_snooze_last_notified(
            now=datetime.now(timezone.utc),
            snooze_hours=hours,
            rate_limit_hours=rate_limit_hours,
        )
        self._plants[plant_id]["last_notified"] = new_last_notified.isoformat()
        await self._async_save_now()
        _LOGGER.info(
            "Plant Care: Pflanze %s für %d h gesnoozed (bis %s)",
            plant_id,
            hours,
            new_last_notified.isoformat(),
        )

    # ------------------------- Reminders / Notifications -------------------------

    async def evaluate_reminders(
        self,
        options: Mapping[str, Any],
        *,
        only_plant_id: str | None = None,
        force: bool = False,
    ) -> int:
        """Sendet Notifications für Pflanzen, die Pflege brauchen.

        Liest den aktuellen Status aus den Sensor-Entities (inklusive
        Moisture-Override) und respektiert Ruhezeiten + Rate-Limit
        aus den ConfigEntry-Options. ``force=True`` überspringt beide.

        Returns:
            Anzahl tatsächlich versendeter Notifications.
        """
        notify_service_full = (options.get(CONF_NOTIFY_SERVICE) or "").strip()
        enabled = options.get(CONF_REMINDERS_ENABLED, False)

        if not notify_service_full or "." not in notify_service_full:
            if force:
                _LOGGER.warning(
                    "Plant Care: notify_service ist nicht konfiguriert"
                )
            return 0
        if not enabled and not force:
            return 0

        notify_domain, notify_service = notify_service_full.split(".", 1)
        title = options.get(CONF_NOTIFY_TITLE) or DEFAULT_NOTIFY_TITLE

        now_utc = datetime.now(timezone.utc)
        now_local_time = dt_util.as_local(now_utc).time()
        quiet_start = parse_time_string(options.get(CONF_QUIET_HOURS_START))
        quiet_end = parse_time_string(options.get(CONF_QUIET_HOURS_END))
        rate_hours = int(options.get(CONF_RATE_LIMIT_HOURS) or 0)

        if not force and is_in_quiet_hours(now_local_time, quiet_start, quiet_end):
            _LOGGER.debug("Plant Care: Quiet-Hours aktiv – keine Notifications")
            return 0

        registry = er.async_get(self.hass)

        if only_plant_id is not None:
            if only_plant_id not in self._plants:
                return 0
            candidates = [(only_plant_id, self._plants[only_plant_id])]
        else:
            candidates = list(self._plants.items())

        sent = 0
        for plant_id, plant in candidates:
            if not force and is_rate_limited(
                plant.get("last_notified"), rate_hours, now_utc
            ):
                continue
            unique_id = f"{DOMAIN}_{plant_id}"
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state == STATUS_OK:
                continue

            name = plant.get("name") or plant_id
            message = _build_reminder_message(name, state.state)
            payload: dict[str, Any] = {"title": title, "message": message}

            if _is_mobile_app_service(notify_service):
                payload["data"] = {
                    "actions": _build_notification_actions(plant_id, state.state),
                    "tag": f"plant_care_{plant_id}",
                    "group": "plant_care",
                }

            try:
                await self.hass.services.async_call(
                    notify_domain,
                    notify_service,
                    payload,
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001 – pro Pflanze isolieren
                _LOGGER.warning(
                    "Plant Care: notify %s.%s fehlgeschlagen: %s",
                    notify_domain,
                    notify_service,
                    err,
                )
                continue

            plant["last_notified"] = now_utc.isoformat()
            sent += 1

        if sent:
            await self._async_save_now()
            _LOGGER.info("Plant Care: %d Erinnerung(en) versendet", sent)
        return sent


def _build_reminder_message(name: str, status: str) -> str:
    if status == STATUS_NEEDS_BOTH:
        return f"🌿 {name} braucht Wasser und Dünger."
    if status == STATUS_NEEDS_WATER:
        return f"🌿 {name} braucht Wasser."
    if status == STATUS_NEEDS_FERTILIZER:
        return f"🌱 {name} braucht Dünger."
    return f"🌿 {name}"


def _build_notification_actions(
    plant_id: str, status: str
) -> list[dict[str, str]]:
    """Action-Buttons für die HA-Mobile-App-Notification.

    Welche Buttons gezeigt werden, hängt vom Status ab. ``snooze`` ist
    immer dabei, ``water`` / ``fertilize`` je nach Bedarf.
    """
    actions: list[dict[str, str]] = []
    if status in (STATUS_NEEDS_WATER, STATUS_NEEDS_BOTH):
        actions.append(
            {"action": f"PLANTCARE_WATER_{plant_id}", "title": "💧 Gegossen"}
        )
    if status in (STATUS_NEEDS_FERTILIZER, STATUS_NEEDS_BOTH):
        actions.append(
            {"action": f"PLANTCARE_FERTILIZE_{plant_id}", "title": "🌱 Gedüngt"}
        )
    actions.append(
        {"action": f"PLANTCARE_SNOOZE_{plant_id}", "title": "💤 Snooze 1d"}
    )
    return actions


def _is_mobile_app_service(notify_service: str) -> bool:
    """``True`` wenn der Service-Name ein HA-Mobile-App-Target ist."""
    return notify_service.startswith("mobile_app_")
