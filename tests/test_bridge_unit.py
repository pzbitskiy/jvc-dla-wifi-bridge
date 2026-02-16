"""Unit tests for bridge runtime behavior."""

from __future__ import annotations

import unittest

from tests._bridge_loader import load_bridge_modules

CONST, BRIDGE = load_bridge_modules()

JvcBridgeServer = BRIDGE.JvcBridgeServer
JvcBridgeCommandError = BRIDGE.JvcBridgeCommandError
UNIT_ID = CONST.UNIT_ID


class _FakeWriter:
    def is_closing(self) -> bool:
        return False


def _ack_frame(command: bytes) -> bytes:
    return b"\x06" + UNIT_ID + command + b"\x0A"


class TestJvcBridgeUnit(unittest.IsolatedAsyncioTestCase):
    async def test_hdmi_requires_cached_power_on(self) -> None:
        bridge = JvcBridgeServer("127.0.0.1", 0, log_traffic=False, ready_ttl_sec=30)

        with self.assertRaises(JvcBridgeCommandError):
            await bridge.async_set_hdmi1()

        with self.assertRaises(JvcBridgeCommandError):
            await bridge.async_set_hdmi2()

    async def test_valid_response_marks_projector_ready_when_connected(self) -> None:
        bridge = JvcBridgeServer("127.0.0.1", 0, log_traffic=False, ready_ttl_sec=30)
        bridge._active_writer = _FakeWriter()

        self.assertFalse(bridge.projector_ready)

        bridge._process_response(_ack_frame(b"\x50\x57"))

        self.assertTrue(bridge.projector_ready)
        self.assertIsNotNone(bridge.state.last_response_at)

    async def test_invalid_response_does_not_update_readiness(self) -> None:
        bridge = JvcBridgeServer("127.0.0.1", 0, log_traffic=False, ready_ttl_sec=30)
        bridge._active_writer = _FakeWriter()

        # wrong result code and wrong unit id
        bridge._process_response(b"\x01\x99\x99\x50\x57\x0A")

        self.assertFalse(bridge.projector_ready)
        self.assertIsNone(bridge.state.last_response_at)

    async def test_readiness_ttl_expires(self) -> None:
        bridge = JvcBridgeServer("127.0.0.1", 0, log_traffic=False, ready_ttl_sec=1)
        bridge._active_writer = _FakeWriter()

        bridge._process_response(_ack_frame(b"\x00\x00"))
        self.assertTrue(bridge.projector_ready)

        # Simulate passage of time beyond TTL.
        assert bridge._last_response_monotonic is not None
        bridge._last_response_monotonic -= 2.0

        self.assertFalse(bridge.projector_ready)


if __name__ == "__main__":
    unittest.main()
