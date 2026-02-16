"""Coordinator for JVC DLA WiFi Bridge runtime state."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bridge import BridgeState, JvcBridgeServer
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class JvcBridgeCoordinator(DataUpdateCoordinator[BridgeState]):
    """Periodic snapshot coordinator for bridge runtime state."""

    def __init__(self, hass: HomeAssistant, bridge: JvcBridgeServer) -> None:
        self.bridge = bridge
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{bridge.listen_host}:{bridge.listen_port}",
            update_interval=timedelta(seconds=1),
        )

    async def _async_update_data(self) -> BridgeState:
        """Return latest in-memory runtime state."""
        return self.bridge.state
