"""The JVC DLA WiFi Bridge integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .bridge import JvcBridgeServer
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
    PLATFORMS,
    SERVICE_SET_HDMI1,
    SERVICE_SET_HDMI2,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from .coordinator import JvcBridgeCoordinator

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.entity_ids})

YAML_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_LISTEN_HOST, default=DEFAULT_LISTEN_HOST): cv.string,
        vol.Optional(CONF_LISTEN_PORT, default=DEFAULT_LISTEN_PORT): cv.port,
        vol.Optional(CONF_LOG_TRAFFIC, default=DEFAULT_LOG_TRAFFIC): cv.boolean,
        vol.Optional(CONF_READY_TTL_SEC, default=DEFAULT_READY_TTL_SEC): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_READY_TTL_SEC, max=MAX_READY_TTL_SEC),
        ),
    }
)

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): YAML_SCHEMA}, extra=vol.ALLOW_EXTRA)


@dataclass(slots=True)
class JvcBridgeRuntimeData:
    """Runtime objects for one config entry."""

    bridge: JvcBridgeServer
    coordinator: JvcBridgeCoordinator


CommandCallable = Callable[[JvcBridgeServer], Awaitable[None]]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up domain and trigger YAML import flow when configured."""
    hass.data.setdefault(DOMAIN, {})

    if imported := config.get(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=imported,
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from config entry."""
    settings = _entry_settings(entry)

    if entry.title != settings[CONF_NAME]:
        hass.config_entries.async_update_entry(entry, title=settings[CONF_NAME])

    bridge = JvcBridgeServer(
        listen_host=settings[CONF_LISTEN_HOST],
        listen_port=settings[CONF_LISTEN_PORT],
        log_traffic=settings[CONF_LOG_TRAFFIC],
        ready_ttl_sec=settings[CONF_READY_TTL_SEC],
    )

    try:
        await bridge.async_start()
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Unable to bind TCP server on {settings[CONF_LISTEN_HOST]}:"
            f"{settings[CONF_LISTEN_PORT]}"
        ) from err

    coordinator = JvcBridgeCoordinator(hass, bridge)
    await coordinator.async_config_entry_first_refresh()

    runtime = JvcBridgeRuntimeData(bridge=bridge, coordinator=coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = hass.data[DOMAIN].pop(entry.entry_id)
    await runtime.bridge.async_stop()

    if not hass.data[DOMAIN]:
        _async_unregister_services(hass)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _entry_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Merge config entry data and options with defaults."""
    merged: dict[str, Any] = {
        CONF_NAME: DEFAULT_NAME,
        CONF_LISTEN_HOST: DEFAULT_LISTEN_HOST,
        CONF_LISTEN_PORT: DEFAULT_LISTEN_PORT,
        CONF_LOG_TRAFFIC: DEFAULT_LOG_TRAFFIC,
        CONF_READY_TTL_SEC: DEFAULT_READY_TTL_SEC,
    }
    merged.update(entry.data)
    merged.update(entry.options)
    return merged


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_TURN_ON):
        return

    async def _handle_turn_on(call: ServiceCall) -> None:
        await _async_dispatch_command(hass, call, lambda bridge: bridge.async_turn_on())

    async def _handle_turn_off(call: ServiceCall) -> None:
        await _async_dispatch_command(hass, call, lambda bridge: bridge.async_turn_off())

    async def _handle_set_hdmi1(call: ServiceCall) -> None:
        await _async_dispatch_command(hass, call, lambda bridge: bridge.async_set_hdmi1())

    async def _handle_set_hdmi2(call: ServiceCall) -> None:
        await _async_dispatch_command(hass, call, lambda bridge: bridge.async_set_hdmi2())

    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_ON,
        _handle_turn_on,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_OFF,
        _handle_turn_off,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HDMI1,
        _handle_set_hdmi1,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HDMI2,
        _handle_set_hdmi2,
        schema=SERVICE_SCHEMA,
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister domain services when no entries remain."""
    for service in (
        SERVICE_TURN_ON,
        SERVICE_TURN_OFF,
        SERVICE_SET_HDMI1,
        SERVICE_SET_HDMI2,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


async def _async_dispatch_command(
    hass: HomeAssistant,
    call: ServiceCall,
    command: CommandCallable,
) -> None:
    """Execute command against selected runtime(s)."""
    runtimes = _resolve_target_runtimes(hass, call)

    errors: list[str] = []
    for runtime in runtimes:
        try:
            await command(runtime.bridge)
        except HomeAssistantError as err:
            errors.append(str(err))
        finally:
            await runtime.coordinator.async_request_refresh()

    if errors:
        raise HomeAssistantError("; ".join(errors))


def _resolve_target_runtimes(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[JvcBridgeRuntimeData]:
    """Resolve runtime objects from service target entity_id or singleton entry."""
    runtimes: dict[str, JvcBridgeRuntimeData] = hass.data.get(DOMAIN, {})
    if not runtimes:
        raise HomeAssistantError("No configured JVC DLA WiFi Bridge entries")

    target_entity_ids = call.data.get(ATTR_ENTITY_ID)
    if target_entity_ids is None:
        if len(runtimes) != 1:
            raise HomeAssistantError(
                "Multiple JVC DLA WiFi Bridge entries configured; please target entity_id"
            )
        return [next(iter(runtimes.values()))]

    entity_registry = er.async_get(hass)
    entry_ids: set[str] = set()

    for entity_id in cv.ensure_list(target_entity_ids):
        reg_entry = entity_registry.async_get(entity_id)
        if reg_entry is None:
            raise HomeAssistantError(f"Unknown entity_id: {entity_id}")

        entry_id = reg_entry.config_entry_id
        if entry_id is None or entry_id not in runtimes:
            raise HomeAssistantError(
                f"Entity {entity_id} does not belong to {DOMAIN}"
            )

        entry_ids.add(entry_id)

    return [runtimes[entry_id] for entry_id in entry_ids]
