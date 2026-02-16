"""Device actions for JVC DLA WiFi Bridge."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import (
    async_get_entity_registry_entry_or_raise,
    async_validate_entity_schema,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_TYPE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from .const import (
    DOMAIN,
    SERVICE_SET_HDMI1,
    SERVICE_SET_HDMI2,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)

ACTION_TYPES = (
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    SERVICE_SET_HDMI1,
    SERVICE_SET_HDMI2,
)

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
    }
)


async def async_validate_action_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate device action config."""
    return await async_validate_entity_schema(hass, config, ACTION_SCHEMA)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List actions for one projector device."""
    registry = er.async_get(hass)

    entries = [
        entry
        for entry in er.async_entries_for_device(registry, device_id)
        if entry.platform == DOMAIN
    ]

    if not entries:
        return []

    # Use one integration entity to route service to the correct config entry.
    target_entry = entries[0]

    return [
        {
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: target_entry.id,
            CONF_TYPE: action_type,
        }
        for action_type in ACTION_TYPES
    ]


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    entry = async_get_entity_registry_entry_or_raise(hass, config[CONF_ENTITY_ID])

    await hass.services.async_call(
        DOMAIN,
        config[CONF_TYPE],
        {ATTR_ENTITY_ID: [entry.entity_id]},
        blocking=True,
        context=context,
    )


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return {}
