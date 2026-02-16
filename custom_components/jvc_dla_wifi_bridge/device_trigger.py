"""Device triggers for JVC DLA WiFi Bridge."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_ENTITY_ID, CONF_FOR, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

CONF_READY_TURNED_ON = "ready_turned_on"
CONF_READY_TURNED_OFF = "ready_turned_off"

TRIGGER_TYPES = (CONF_READY_TURNED_ON, CONF_READY_TURNED_OFF)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach trigger for ready binary sensor state changes."""
    to_state = "on" if config[CONF_TYPE] == CONF_READY_TURNED_ON else "off"
    state_config: dict[str, object] = {
        state_trigger.CONF_PLATFORM: "state",
        state_trigger.CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        state_trigger.CONF_TO: to_state,
    }

    if CONF_FOR in config:
        state_config[CONF_FOR] = config[CONF_FOR]

    validated = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass,
        validated,
        action,
        trigger_info,
        platform_type="device",
    )


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List triggers for one projector device."""
    triggers: list[dict[str, str]] = []

    for entry in _ready_entity_entries(hass, device_id):
        triggers.extend(
            [
                {
                    state_trigger.CONF_PLATFORM: "device",
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.id,
                    CONF_TYPE: CONF_READY_TURNED_ON,
                },
                {
                    state_trigger.CONF_PLATFORM: "device",
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.id,
                    CONF_TYPE: CONF_READY_TURNED_OFF,
                },
            ]
        )

    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List trigger capabilities."""
    return {
        "extra_fields": vol.Schema(
            {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
        )
    }


def _ready_entity_entries(
    hass: HomeAssistant, device_id: str
) -> list[er.RegistryEntry]:
    """Return ready binary sensor entities for this integration/device."""
    registry = er.async_get(hass)

    return [
        entry
        for entry in er.async_entries_for_device(registry, device_id)
        if entry.domain == "binary_sensor"
        and entry.platform == DOMAIN
        and bool(entry.unique_id)
        and entry.unique_id.endswith("_ready")
    ]
