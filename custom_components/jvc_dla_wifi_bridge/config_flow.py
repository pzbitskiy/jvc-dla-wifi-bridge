"""Config flow for JVC DLA WiFi Bridge."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_LISTEN_HOST,
    CONF_LISTEN_PORT,
    CONF_LOG_TRAFFIC,
    CONF_READY_TTL_SEC,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_LOG_TRAFFIC,
    DEFAULT_NAME,
    DEFAULT_READY_TTL_SEC,
    DOMAIN,
    MAX_READY_TTL_SEC,
    MIN_READY_TTL_SEC,
)

_LOGGER = logging.getLogger(__name__)


def _settings_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build config/option schema using provided defaults."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_LISTEN_HOST,
                default=defaults.get(CONF_LISTEN_HOST, DEFAULT_LISTEN_HOST),
            ): str,
            vol.Required(
                CONF_LISTEN_PORT,
                default=defaults.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT),
            ): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_LOG_TRAFFIC,
                default=defaults.get(CONF_LOG_TRAFFIC, DEFAULT_LOG_TRAFFIC),
            ): bool,
            vol.Required(
                CONF_READY_TTL_SEC,
                default=defaults.get(CONF_READY_TTL_SEC, DEFAULT_READY_TTL_SEC),
            ): vol.All(int, vol.Range(min=MIN_READY_TTL_SEC, max=MAX_READY_TTL_SEC)),
        }
    )


def _normalize_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize settings from config flow or YAML import."""
    return {
        CONF_NAME: str(settings[CONF_NAME]),
        CONF_LISTEN_HOST: str(settings[CONF_LISTEN_HOST]),
        CONF_LISTEN_PORT: int(settings[CONF_LISTEN_PORT]),
        CONF_LOG_TRAFFIC: bool(settings[CONF_LOG_TRAFFIC]),
        CONF_READY_TTL_SEC: int(settings[CONF_READY_TTL_SEC]),
    }


def _settings_differ(existing: Mapping[str, Any], imported: Mapping[str, Any]) -> bool:
    """Return True when persisted settings differ from imported YAML settings."""
    keys = (
        CONF_NAME,
        CONF_LISTEN_HOST,
        CONF_LISTEN_PORT,
        CONF_LOG_TRAFFIC,
        CONF_READY_TTL_SEC,
    )
    return any(existing.get(key) != imported.get(key) for key in keys)


class JvcBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for JVC DLA WiFi Bridge."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle user initiated setup."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            settings = _normalize_settings(user_input)
            return self.async_create_entry(title=settings[CONF_NAME], data=settings)

        return self.async_show_form(
            step_id="user",
            data_schema=_settings_schema({}),
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Handle YAML import."""
        imported = _normalize_settings(user_input)

        if current_entries := self._async_current_entries():
            current_entry = current_entries[0]
            persisted = {**current_entry.data, **current_entry.options}
            if _settings_differ(persisted, imported):
                _LOGGER.warning(
                    "YAML configuration for %s differs from existing config entry; "
                    "keeping existing config entry values",
                    DOMAIN,
                )
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=imported[CONF_NAME], data=imported)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> JvcBridgeOptionsFlow:
        """Return options flow for this handler."""
        return JvcBridgeOptionsFlow(config_entry)


class JvcBridgeOptionsFlow(OptionsFlow):
    """Handle options for JVC DLA WiFi Bridge."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=_normalize_settings(user_input))

        defaults = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_settings_schema(defaults),
        )
