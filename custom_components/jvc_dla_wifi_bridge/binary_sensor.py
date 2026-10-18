"""Binary sensor entities for JVC DLA WiFi Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CONNECTED_CLIENT,
    ATTR_LAST_READY_OK_AT,
    ATTR_LAST_RESPONSE_AT,
    DOMAIN,
)
from .entity import JvcBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up readiness binary sensor from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JvcBridgeReadyBinarySensor(runtime.coordinator, entry)])


class JvcBridgeReadyBinarySensor(JvcBridgeEntity, BinarySensorEntity):
    """Binary sensor showing whether the projector answers over the bridge."""

    _attr_name = "Ready"
    _attr_translation_key = "ready"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ready")

    @property
    def is_on(self) -> bool:
        """Return projector ready state."""
        return self.coordinator.data.projector_ready

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose connection diagnostics for troubleshooting."""
        return {
            ATTR_CONNECTED_CLIENT: self.coordinator.data.connected_client,
            ATTR_LAST_RESPONSE_AT: self.coordinator.data.last_response_at,
            ATTR_LAST_READY_OK_AT: self.coordinator.data.last_ready_ok_at,
        }
