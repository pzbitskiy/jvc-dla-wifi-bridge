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
CMD_QUERY_POWER = CONST.CMD_QUERY_POWER
CMD_QUERY_INPUT = CONST.CMD_QUERY_INPUT
COMMAND_PAYLOADS = CONST.COMMAND_PAYLOADS
READY_PROBE_TIMEOUT_SEC = CONST.READY_PROBE_TIMEOUT_SEC
RESPONSE_COMMANDS = CONST.RESPONSE_COMMANDS
UNIT_ID = CONST.UNIT_ID
INPUT_HDMI1 = CONST.INPUT_HDMI1
INPUT_HDMI2 = CONST.INPUT_HDMI2

JvcBridgeCommandError = BRIDGE.JvcBridgeCommandError


def _ack_frame(command: bytes) -> bytes:
    return b"\x06" + UNIT_ID + command + b"\x0A"


def _data_frame(command: bytes, data: bytes) -> bytes:
    return b"\x40" + UNIT_ID + command + data + b"\x0A"


async def _answer_query(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    command_name: str,
    data: bytes,
) -> None:
    """Expect a query command and answer it like the projector: ACK, then data."""
    assert await _read_command(reader) == COMMAND_PAYLOADS[command_name]
    command = RESPONSE_COMMANDS[command_name]
    writer.write(_ack_frame(command) + _data_frame(command, data))
    await writer.drain()


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

            # Initial status refresh: projector in standby.
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x30")
            await _wait_for(lambda: bridge.state.power_on is False)

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

    async def test_status_reflects_projector_power_and_input(self) -> None:
        bridge = JvcBridgeServer(
            "127.0.0.1",
            0,
            log_traffic=False,
            ready_ttl_sec=30,
            ready_probe_interval_sec=60,
            status_poll_interval_sec=60,
        )

        await bridge.async_start()

        assert bridge._server is not None
        listen_port = bridge._server.sockets[0].getsockname()[1]

        writer = None
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)

            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_READY])
            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_READY]))
            await writer.drain()

            # Projector was turned on and switched to HDMI2 outside Home Assistant.
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x31")
            await _answer_query(reader, writer, CMD_QUERY_INPUT, b"\x37")
            await _wait_for(lambda: bridge.state.input_source == INPUT_HDMI2)
            self.assertTrue(bridge.state.power_on)

            # Input switching is allowed based on the queried power state.
            await bridge.async_set_hdmi1()
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_HDMI1])
            self.assertEqual(bridge.state.input_source, INPUT_HDMI1)

            # Unknown input code (e.g. component) is reported as unknown.
            refresh = asyncio.create_task(bridge.async_refresh_status())
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x31")
            await _answer_query(reader, writer, CMD_QUERY_INPUT, b"\x32")
            await refresh
            self.assertIsNone(bridge.state.input_source)

            # Projector cooling down after being turned off with the IR remote.
            refresh = asyncio.create_task(bridge.async_refresh_status())
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x32")
            await refresh
            self.assertFalse(bridge.state.power_on)
            self.assertIsNone(bridge.state.input_source)

            with self.assertRaises(JvcBridgeCommandError):
                await bridge.async_set_hdmi2()
        finally:
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            await bridge.async_stop()

    async def test_status_reply_superseded_by_command_is_ignored(self) -> None:
        bridge = JvcBridgeServer(
            "127.0.0.1",
            0,
            log_traffic=False,
            ready_ttl_sec=30,
            ready_probe_interval_sec=60,
            status_poll_interval_sec=60,
        )

        await bridge.async_start()

        assert bridge._server is not None
        listen_port = bridge._server.sockets[0].getsockname()[1]

        writer = None
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)

            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_READY])
            writer.write(_ack_frame(RESPONSE_COMMANDS[CMD_READY]))
            await writer.drain()
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x30")
            await _wait_for(lambda: bridge.state.power_on is False)

            # Power query in flight when the projector is turned on.
            refresh = asyncio.create_task(bridge.async_refresh_status())
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_QUERY_POWER])
            await bridge.async_turn_on()
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_TURN_ON])

            # Delayed standby reply predates power on.
            command = RESPONSE_COMMANDS[CMD_QUERY_POWER]
            writer.write(_ack_frame(command) + _data_frame(command, b"\x30"))
            await writer.drain()
            await refresh
            self.assertTrue(bridge.state.power_on)

            # Input query in flight when another input is selected.
            refresh = asyncio.create_task(bridge.async_refresh_status())
            await _answer_query(reader, writer, CMD_QUERY_POWER, b"\x31")
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_QUERY_INPUT])
            await bridge.async_set_hdmi1()
            self.assertEqual(await _read_command(reader), COMMAND_PAYLOADS[CMD_HDMI1])

            command = RESPONSE_COMMANDS[CMD_QUERY_INPUT]
            writer.write(_ack_frame(command) + _data_frame(command, b"\x37"))
            await writer.drain()
            await refresh
            self.assertEqual(bridge.state.input_source, INPUT_HDMI1)
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
