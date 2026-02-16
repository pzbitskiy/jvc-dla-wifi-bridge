"""Device conditions for JVC DLA WiFi Bridge."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import (
    CONF_CONDITION,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FOR,
    CONF_STATE,
    CONF_TYPE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import condition, config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

CONF_IS_READY = "is_ready"
CONF_IS_NOT_READY = "is_not_ready"

CONDITION_TYPES = (CONF_IS_READY, CONF_IS_NOT_READY)

CONDITION_SCHEMA = cv.DEVICE_CONDITION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(CONDITION_TYPES),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


async def async_get_conditions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List conditions for one projector device."""
    conditions: list[dict[str, str]] = []

    for entry in _ready_entity_entries(hass, device_id):
        conditions.extend(
            [
                {
                    CONF_CONDITION: "device",
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.id,
                    CONF_TYPE: CONF_IS_READY,
                },
                {
                    CONF_CONDITION: "device",
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.id,
                    CONF_TYPE: CONF_IS_NOT_READY,
                },
            ]
        )

    return conditions


@callback
def async_condition_from_config(
    hass: HomeAssistant, config: ConfigType
) -> condition.ConditionCheckerType:
    """Create a condition checker from config."""
    target_state = "on" if config[CONF_TYPE] == CONF_IS_READY else "off"
    state_config: dict[str, object] = {
        CONF_CONDITION: "state",
        CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        CONF_STATE: target_state,
    }

    if CONF_FOR in config:
        state_config[CONF_FOR] = config[CONF_FOR]

    validated = cv.STATE_CONDITION_SCHEMA(state_config)
    validated = condition.state_validate_config(hass, validated)
    return condition.state_from_config(validated)


async def async_get_condition_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List condition capabilities."""
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
