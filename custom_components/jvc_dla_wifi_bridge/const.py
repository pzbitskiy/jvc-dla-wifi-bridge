"""Constants for the JVC DLA WiFi Bridge integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "jvc_dla_wifi_bridge"
NAME: Final = "JVC DLA WiFi Bridge"

PLATFORMS: Final[list[Platform]] = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BINARY_SENSOR,
]

CONF_LISTEN_HOST: Final = "listen_host"
CONF_LISTEN_PORT: Final = "listen_port"
CONF_LOG_TRAFFIC: Final = "log_traffic"
CONF_READY_TTL_SEC: Final = "ready_ttl_sec"

DEFAULT_NAME: Final = "JVC DLA RS40"
DEFAULT_LISTEN_HOST: Final = "0.0.0.0"
DEFAULT_LISTEN_PORT: Final = 20554
DEFAULT_LOG_TRAFFIC: Final = False
DEFAULT_READY_TTL_SEC: Final = 30

MIN_READY_TTL_SEC: Final = 5
MAX_READY_TTL_SEC: Final = 3600

READY_PROBE_INTERVAL_SEC: Final = 15
READY_PROBE_TIMEOUT_SEC: Final = 3

ATTR_PROJECTOR_READY: Final = "projector_ready"
ATTR_CONNECTED_CLIENT: Final = "connected_client"
ATTR_LAST_RESPONSE_AT: Final = "last_response_at"
ATTR_LAST_READY_OK_AT: Final = "last_ready_ok_at"

INPUT_HDMI1: Final = "hdmi1"
INPUT_HDMI2: Final = "hdmi2"
INPUT_OPTIONS: Final[tuple[str, str]] = (INPUT_HDMI1, INPUT_HDMI2)

SERVICE_TURN_ON: Final = "turn_on"
SERVICE_TURN_OFF: Final = "turn_off"
SERVICE_SET_HDMI1: Final = "set_hdmi1"
SERVICE_SET_HDMI2: Final = "set_hdmi2"

CMD_READY: Final = "ready"
CMD_TURN_ON: Final = "turn_on"
CMD_TURN_OFF: Final = "turn_off"
CMD_HDMI1: Final = "hdmi1"
CMD_HDMI2: Final = "hdmi2"

UNIT_ID: Final = b"\x89\x01"

COMMAND_PAYLOADS: Final[dict[str, bytes]] = {
    CMD_READY: b"\x21\x89\x01\x00\x00\x0A",
    CMD_TURN_ON: b"\x21\x89\x01\x50\x57\x31\x0A",
    CMD_TURN_OFF: b"\x21\x89\x01\x50\x57\x30\x0A",
    CMD_HDMI1: b"\x21\x89\x01\x49\x50\x36\x0A",
    CMD_HDMI2: b"\x21\x89\x01\x49\x50\x37\x0A",
}

RESPONSE_COMMANDS: Final[dict[str, bytes]] = {
    CMD_READY: b"\x00\x00",
    CMD_TURN_ON: b"\x50\x57",
    CMD_TURN_OFF: b"\x50\x57",
    CMD_HDMI1: b"\x49\x50",
    CMD_HDMI2: b"\x49\x50",
}
