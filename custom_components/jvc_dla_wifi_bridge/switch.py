"""Switch entities for JVC DLA WiFi Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CONNECTED_CLIENT,
    ATTR_LAST_READY_OK_AT,
    ATTR_LAST_RESPONSE_AT,
    ATTR_PROJECTOR_READY,
    DOMAIN,
)
from .entity import JvcBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up power switch entity from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JvcBridgePowerSwitch(runtime.coordinator, entry)])


class JvcBridgePowerSwitch(JvcBridgeEntity, SwitchEntity):
    """Power switch for projector on/off actions."""

    _attr_name = "Power"
    _attr_translation_key = "power"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "power")

    @property
    def is_on(self) -> bool:
        """Return cached power state."""
        return self.coordinator.data.power_on is True

    @property
    def available(self) -> bool:
        """Entity is available when bridge client is connected."""
        return self.coordinator.data.connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose readiness and connection diagnostics."""
        return {
            ATTR_PROJECTOR_READY: self.coordinator.data.projector_ready,
            ATTR_CONNECTED_CLIENT: self.coordinator.data.connected_client,
            ATTR_LAST_RESPONSE_AT: self.coordinator.data.last_response_at,
            ATTR_LAST_READY_OK_AT: self.coordinator.data.last_ready_ok_at,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send projector power on command."""
        await self.bridge.async_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send projector power off command."""
        await self.bridge.async_turn_off()
        await self.coordinator.async_request_refresh()
