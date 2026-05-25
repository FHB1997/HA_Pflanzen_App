"""Config Flow für Plant Care – einmalige Einrichtung + Options."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TITLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RATE_LIMIT_HOURS,
    CONF_REMINDERS_ENABLED,
    DEFAULT_NOTIFY_TITLE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RATE_LIMIT_HOURS,
    DOMAIN,
    OPT_SEND_TEST,
    PANEL_TITLE,
)

_LOGGER = logging.getLogger(__name__)


class PlantCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-Instance Config Flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initialer Setup-Schritt."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

        return self.async_create_entry(title=PANEL_TITLE, data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PlantCareOptionsFlow(config_entry)


class PlantCareOptionsFlow(OptionsFlow):
    """Konfiguriert die integrierten Pflege-Erinnerungen."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            send_test = bool(user_input.pop(OPT_SEND_TEST, False))
            if send_test:
                # Auf den gerade abgesendeten (noch nicht persistierten)
                # Werten testen, damit User vor dem Save validieren können.
                coord = self.hass.data.get(DOMAIN, {}).get("coordinator")
                if coord is None:
                    errors["base"] = "test_failed"
                    return self._show_form(user_input, errors=errors)
                try:
                    await coord.send_test_notification(user_input)
                except ValueError:
                    errors[CONF_NOTIFY_SERVICE] = "notify_service_empty"
                    return self._show_form(user_input, errors=errors)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Plant Care: Test-Benachrichtigung fehlgeschlagen: %s", err
                    )
                    errors["base"] = "test_failed"
                    return self._show_form(user_input, errors=errors)
            # Leerer Notify-Service deaktiviert das Feature implizit.
            return self.async_create_entry(title="", data=user_input)

        return self._show_form(None)

    def _show_form(
        self,
        user_input: dict[str, Any] | None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        opts = user_input if user_input is not None else self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REMINDERS_ENABLED,
                    default=opts.get(CONF_REMINDERS_ENABLED, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=opts.get(CONF_NOTIFY_SERVICE, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_NOTIFY_TITLE,
                    default=opts.get(CONF_NOTIFY_TITLE, DEFAULT_NOTIFY_TITLE),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_QUIET_HOURS_START,
                    default=opts.get(
                        CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    CONF_QUIET_HOURS_END,
                    default=opts.get(
                        CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    CONF_RATE_LIMIT_HOURS,
                    default=opts.get(
                        CONF_RATE_LIMIT_HOURS, DEFAULT_RATE_LIMIT_HOURS
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=168,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                ),
                vol.Optional(
                    OPT_SEND_TEST,
                    default=False,
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors or {}
        )
