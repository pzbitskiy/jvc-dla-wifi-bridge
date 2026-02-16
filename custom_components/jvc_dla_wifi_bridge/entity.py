"""Base entity for JVC DLA WiFi Bridge."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bridge import JvcBridgeServer
from .const import DEFAULT_NAME, DOMAIN
from .coordinator import JvcBridgeCoordinator


class JvcBridgeEntity(CoordinatorEntity[JvcBridgeCoordinator]):
    """Base entity bound to one bridge runtime/coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JvcBridgeCoordinator,
        entry: ConfigEntry,
        unique_key: str,
    ) -> None:
        super().__init__(coordinator)

        name = entry.title or entry.data.get(CONF_NAME, DEFAULT_NAME)

        self._attr_unique_id = f"{entry.entry_id}_{unique_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="JVC / SH-B35W",
            model="DLA-RS40 via RS232-to-WiFi",
            name=name,
        )

    @property
    def bridge(self) -> JvcBridgeServer:
        """Return bridge runtime."""
        return self.coordinator.bridge
