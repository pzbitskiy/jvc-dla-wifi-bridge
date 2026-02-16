"""End-to-end tests for bridge runtime with mocked SH-B35W TCP client."""

from __future__ import annotations

import asyncio
import unittest

from tests._bridge_loader import load_bridge_modules

CONST, BRIDGE = load_bridge_modules()

JvcBridgeServer = BRIDGE.JvcBridgeServer

CMD_READY = CONST.CMD_READY
CMD_TURN_ON = CONST.CMD_TURN_ON
CMD_HDMI1 = CONST.CMD_HDMI1
COMMAND_PAYLOADS = CONST.COMMAND_PAYLOADS
READY_PROBE_TIMEOUT_SEC = CONST.READY_PROBE_TIMEOUT_SEC
RESPONSE_COMMANDS = CONST.RESPONSE_COMMANDS
UNIT_ID = CONST.UNIT_ID
INPUT_HDMI1 = CONST.INPUT_HDMI1


def _ack_frame(command: bytes) -> bytes:
    return b"\x06" + UNIT_ID + command + b"\x0A"


async def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.02) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)

    raise AssertionError("Timed out waiting for condition")


async def _read_command(reader: asyncio.StreamReader, timeout: float = 2.0) -> bytes:
    return await asyncio.wait_for(reader.readuntil(b"\x0A"), timeout=timeout)


class TestJvcBridgeEndToEnd(unittest.IsolatedAsyncioTestCase):
    async def test_full_command_flow_with_mocked_tcp_client(self) -> None:
        bridge = JvcBridgeServer(
            "127.0.0.1",
            0,
            log_traffic=False,
            ready_ttl_sec=30,
            ready_probe_interval_sec=60,
        )

        await bridge.async_start()

        assert bridge._server is not None
        listen_port = bridge._server.sockets[0].getsockname()[1]

        reader = None
        writer = None
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)

            # Bridge sends ready probe immediately after connect.
            ready_probe = await _read_command(reader)
            self.assertEqual(ready_probe, COMMAND_PAYLOADS[CMD_READY])

            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_READY]))
            await writer.drain()

            await _wait_for(lambda: bridge.projector_ready)

            await bridge.async_turn_on()
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_TURN_ON])

            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_TURN_ON]))
            await writer.drain()

            await bridge.async_set_hdmi1()
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_HDMI1])

            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_HDMI1]))
            await writer.drain()

            await _wait_for(lambda: bridge.state.input_source == INPUT_HDMI1)
            self.assertTrue(bridge.state.power_on)
            self.assertEqual(bridge.state.input_source, INPUT_HDMI1)
            self.assertTrue(bridge.projector_ready)

            writer.close()
            await writer.wait_closed()
            await _wait_for(lambda: not bridge.connected)
            self.assertFalse(bridge.projector_ready)
        finally:
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            await bridge.async_stop()

    async def test_non_ready_response_can_make_projector_ready(self) -> None:
        bridge = JvcBridgeServer(
            "127.0.0.1",
            0,
            log_traffic=False,
            ready_ttl_sec=30,
            ready_probe_interval_sec=60,
        )

        await bridge.async_start()

        assert bridge._server is not None
        listen_port = bridge._server.sockets[0].getsockname()[1]

        writer = None
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)

            # Consume ready probe and intentionally do not reply.
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_READY])

            await asyncio.sleep(READY_PROBE_TIMEOUT_SEC + 0.2)
            self.assertTrue(bridge.connected)
            self.assertFalse(bridge.projector_ready)

            # Any valid response should count as recent readiness evidence.
            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_TURN_ON]))
            await writer.drain()

            await _wait_for(lambda: bridge.projector_ready)
        finally:
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            await bridge.async_stop()


if __name__ == "__main__":
    unittest.main()
