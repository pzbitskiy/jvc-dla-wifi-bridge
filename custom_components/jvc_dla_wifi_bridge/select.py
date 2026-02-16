"""Select entities for JVC DLA WiFi Bridge."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INPUT_HDMI1, INPUT_HDMI2, INPUT_OPTIONS
from .entity import JvcBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up input select entity from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JvcBridgeInputSelect(runtime.coordinator, entry)])


class JvcBridgeInputSelect(JvcBridgeEntity, SelectEntity):
    """Input source selector for HDMI1/HDMI2."""

    _attr_name = "Input"
    _attr_translation_key = "input"
    _attr_options = list(INPUT_OPTIONS)

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input")

    @property
    def current_option(self) -> str | None:
        """Return current cached input source."""
        return self.coordinator.data.input_source

    @property
    def available(self) -> bool:
        """Entity is available when bridge client is connected."""
        return self.coordinator.data.connected

    async def async_select_option(self, option: str) -> None:
        """Select projector input."""
        if option not in INPUT_OPTIONS:
            raise HomeAssistantError(f"Unsupported input option: {option}")

        if option == INPUT_HDMI1:
            await self.bridge.async_set_hdmi1()
        elif option == INPUT_HDMI2:
            await self.bridge.async_set_hdmi2()

        await self.coordinator.async_request_refresh()
