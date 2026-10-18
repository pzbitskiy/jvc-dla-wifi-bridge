"""TCP bridge runtime for JVC DLA RS40 over SH-B35W."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
import logging
from time import monotonic
from typing import Deque

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CMD_HDMI1,
    CMD_HDMI2,
    CMD_QUERY_INPUT,
    CMD_QUERY_POWER,
    CMD_READY,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    COMMAND_PAYLOADS,
    INPUT_CODES,
    INPUT_HDMI1,
    INPUT_HDMI2,
    POWER_STATE_ON,
    READY_PROBE_INTERVAL_SEC,
    READY_PROBE_TIMEOUT_SEC,
    RESPONSE_COMMANDS,
    RESULT_ACK,
    RESULT_DATA,
    STATUS_POLL_INTERVAL_SEC,
    UNIT_ID,
)

_LOGGER = logging.getLogger(__name__)

# Response frames are matched to requests by (result code, command code).
WaiterKey = tuple[int, bytes]


class JvcBridgeError(HomeAssistantError):
    """Base integration command/runtime error."""


class JvcBridgeNotConnectedError(JvcBridgeError):
    """Raised when SH-B35W client is not connected."""


class JvcBridgeCommandError(JvcBridgeError):
    """Raised when the command cannot be executed."""


@dataclass(frozen=True, slots=True)
class BridgeState:
    """Current runtime snapshot for entities and services."""

    connected: bool
    connected_client: str | None
    projector_ready: bool
    power_on: bool | None
    input_source: str | None
    last_response_at: datetime | None
    last_ready_ok_at: datetime | None


class JvcBridgeServer:
    """Owns TCP listener and command transport state."""

    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        *,
        log_traffic: bool,
        ready_ttl_sec: int,
        ready_probe_interval_sec: int = READY_PROBE_INTERVAL_SEC,
        status_poll_interval_sec: int = STATUS_POLL_INTERVAL_SEC,
    ) -> None:
        self.listen_host = listen_host
        self.listen_port = listen_port
        self._log_traffic = log_traffic
        self._ready_ttl_sec = ready_ttl_sec
        self._ready_probe_interval_sec = ready_probe_interval_sec
        self._status_poll_interval_sec = status_poll_interval_sec

        self._server: asyncio.AbstractServer | None = None

        self._active_reader: asyncio.StreamReader | None = None
        self._active_writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None

        self._ready_probe_task: asyncio.Task[None] | None = None
        self._status_poll_task: asyncio.Task[None] | None = None

        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

        self._waiters: dict[WaiterKey, Deque[asyncio.Future[bytes]]] = defaultdict(deque)

        self._connected_client: str | None = None
        # bumped by every operation command, status replies older than it are stale
        self._command_seq = 0
        self._power_on: bool | None = None
        self._input_source: str | None = None

        self._last_response_at: datetime | None = None
        self._last_response_monotonic: float | None = None
        self._last_ready_ok_at: datetime | None = None
        self._last_ready_ok_monotonic: float | None = None

    @property
    def state(self) -> BridgeState:
        """Return immutable state snapshot."""
        return BridgeState(
            connected=self.connected,
            connected_client=self._connected_client,
            projector_ready=self.projector_ready,
            power_on=self._power_on,
            input_source=self._input_source,
            last_response_at=self._last_response_at,
            last_ready_ok_at=self._last_ready_ok_at,
        )

    @property
    def connected(self) -> bool:
        """Return whether SH-B35W TCP client is connected."""
        return self._active_writer is not None and not self._active_writer.is_closing()

    @property
    def projector_ready(self) -> bool:
        """Projector is ready iff connected and we have recent readiness evidence."""
        if not self.connected:
            return False

        now = monotonic()
        return self._is_recent(now, self._last_ready_ok_monotonic) or self._is_recent(
            now, self._last_response_monotonic
        )

    async def async_start(self) -> None:
        """Start listening for SH-B35W TCP client connections."""
        if self._server is not None:
            return

        self._server = await asyncio.start_server(
            self._async_handle_client,
            host=self.listen_host,
            port=self.listen_port,
        )

        self._ready_probe_task = asyncio.create_task(
            self._async_ready_probe_loop(),
            name="jvc_dla_wifi_bridge_ready_probe",
        )
        self._status_poll_task = asyncio.create_task(
            self._async_status_poll_loop(),
            name="jvc_dla_wifi_bridge_status_poll",
        )

        _LOGGER.info(
            "Listening for SH-B35W TCP client on %s:%s",
            self.listen_host,
            self.listen_port,
        )

    async def async_stop(self) -> None:
        """Stop TCP listener and clean up all runtime tasks."""
        for task in (self._ready_probe_task, self._status_poll_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._ready_probe_task = None
        self._status_poll_task = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        async with self._connection_lock:
            await self._async_close_active_client_locked()

    async def async_turn_on(self) -> None:
        """Send power on command."""
        await self._async_send_command(CMD_TURN_ON)
        self._power_on = True

    async def async_turn_off(self) -> None:
        """Send power off command."""
        await self._async_send_command(CMD_TURN_OFF)
        self._power_on = False

    async def async_set_hdmi1(self) -> None:
        """Switch input to HDMI1 if cached power state allows it."""
        self._assert_can_switch_input()
        await self._async_send_command(CMD_HDMI1)
        self._input_source = INPUT_HDMI1

    async def async_set_hdmi2(self) -> None:
        """Switch input to HDMI2 if cached power state allows it."""
        self._assert_can_switch_input()
        await self._async_send_command(CMD_HDMI2)
        self._input_source = INPUT_HDMI2

    async def async_probe_ready(self) -> bool:
        """Send ready command and update readiness cache from response."""
        if await self._async_request(CMD_READY, RESULT_ACK) is None:
            return False

        self._last_ready_ok_monotonic = monotonic()
        self._last_ready_ok_at = dt_util.utcnow()
        return True

    async def async_refresh_status(self) -> None:
        """Query projector power state and, when powered on, its input source.

        Cached values are kept when the projector does not answer, or when a
        command was sent meanwhile: the reply may predate it.
        """
        seq = self._command_seq
        power = await self._async_request(CMD_QUERY_POWER, RESULT_DATA)
        if power is None or seq != self._command_seq:
            return

        self._power_on = power == POWER_STATE_ON
        if not self._power_on:
            # input can only be queried in power on state
            self._input_source = None
            return

        source = await self._async_request(CMD_QUERY_INPUT, RESULT_DATA)
        if source is not None and seq == self._command_seq:
            self._input_source = INPUT_CODES.get(source)

    async def _async_send_command(self, command_name: str) -> None:
        """Send an operation command, superseding status queries in flight."""
        self._command_seq += 1
        await self._async_send_payload(COMMAND_PAYLOADS[command_name], command_name)

    async def _async_request(self, command_name: str, result_code: int) -> bytes | None:
        """Send a command and wait for its response frame with the given result code.

        Return the response data, or None when not connected or not answered.
        """
        async with self._request_lock:
            if not self.connected:
                return None

            key = (result_code, RESPONSE_COMMANDS[command_name])
            waiter = self._register_waiter(key)

            try:
                await self._async_send_payload(COMMAND_PAYLOADS[command_name], command_name)
                response = await asyncio.wait_for(waiter, timeout=READY_PROBE_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                self._remove_waiter(key, waiter)
                _LOGGER.debug("No response to %s", command_name)
                return None
            except JvcBridgeNotConnectedError:
                self._remove_waiter(key, waiter)
                return None
            except Exception:
                self._remove_waiter(key, waiter)
                _LOGGER.exception("Unexpected error while sending %s", command_name)
                return None

            return response[3 + len(key[1]) : -1]

    async def _async_handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle newly accepted SH-B35W client."""
        connected_client = self._format_peer_name(writer.get_extra_info("peername"))

        async with self._connection_lock:
            if self._active_writer is not None and self._active_writer is not writer:
                _LOGGER.warning(
                    "Replacing active SH-B35W client %s with %s",
                    self._connected_client,
                    connected_client,
                )
                await self._async_close_active_client_locked()

            self._active_reader = reader
            self._active_writer = writer
            self._connected_client = connected_client

            self._reader_task = asyncio.create_task(
                self._async_reader_loop(reader, writer),
                name="jvc_dla_wifi_bridge_reader",
            )

        _LOGGER.info("SH-B35W client connected: %s", connected_client)
        asyncio.create_task(self._async_refresh_on_connect())

    async def _async_refresh_on_connect(self) -> None:
        """Probe readiness and fetch projector status for a new client."""
        if await self.async_probe_ready():
            await self.async_refresh_status()

    async def _async_reader_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Read projector responses and resolve pending command waiters."""
        try:
            while True:
                response = await reader.readuntil(separator=b"\x0A")
                if self._log_traffic:
                    _LOGGER.info("RX %s", response.hex(" "))
                self._process_response(response)
        except asyncio.IncompleteReadError:
            _LOGGER.info("SH-B35W client disconnected")
        except (ConnectionError, OSError):
            _LOGGER.info("SH-B35W client connection dropped")
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected reader loop error")
        finally:
            await self._async_clear_client_if_active(writer)

    def _process_response(self, response: bytes) -> None:
        """Validate and process one newline-terminated response frame."""
        if not self._is_valid_response(response):
            _LOGGER.debug("Ignoring invalid projector frame: %s", response.hex(" "))
            return

        self._last_response_monotonic = monotonic()
        self._last_response_at = dt_util.utcnow()
        self._resolve_waiters(response)

    def _is_valid_response(self, response: bytes) -> bool:
        """Return True for valid response frame for this projector unit ID."""
        if len(response) < 4:
            return False

        if response[-1] != 0x0A:
            return False

        result_code = response[0]
        if result_code not in (0x06, 0x40):
            return False

        if response[1:3] != UNIT_ID:
            return False

        return True

    async def _async_ready_probe_loop(self) -> None:
        """Periodically refresh readiness cache while connected."""
        try:
            while True:
                await asyncio.sleep(self._ready_probe_interval_sec)
                if self.connected:
                    await self.async_probe_ready()
        except asyncio.CancelledError:
            return

    async def _async_status_poll_loop(self) -> None:
        """Periodically refresh projector power and input while connected."""
        try:
            while True:
                await asyncio.sleep(self._status_poll_interval_sec)
                if self.connected:
                    await self.async_refresh_status()
        except asyncio.CancelledError:
            return

    async def _async_send_payload(self, payload: bytes, command_name: str) -> None:
        """Write one command payload to active TCP client."""
        async with self._send_lock:
            writer = self._active_writer
            if writer is None or writer.is_closing():
                raise JvcBridgeNotConnectedError("No SH-B35W TCP client connected")

            if self._log_traffic:
                _LOGGER.info("TX %s: %s", command_name, payload.hex(" "))

            writer.write(payload)

            try:
                await writer.drain()
            except (ConnectionError, OSError) as err:
                await self._async_clear_client_if_active(writer)
                raise JvcBridgeNotConnectedError(
                    "SH-B35W TCP client disconnected during write"
                ) from err

    async def _async_clear_client_if_active(self, writer: asyncio.StreamWriter) -> None:
        """Clear active client state if writer matches current active client."""
        async with self._connection_lock:
            if writer is not self._active_writer:
                return
            await self._async_close_active_client_locked()

    async def _async_close_active_client_locked(self) -> None:
        """Close and clear active client state.

        Caller must hold _connection_lock.
        """
        current_task = asyncio.current_task()
        reader_task = self._reader_task

        if reader_task is not None and reader_task is not current_task:
            reader_task.cancel()
            reader_task.add_done_callback(self._consume_task_result)

        self._reader_task = None

        if self._active_writer is not None:
            self._active_writer.close()
            with suppress(ConnectionError, OSError, RuntimeError):
                await self._active_writer.wait_closed()

        self._active_reader = None
        self._active_writer = None
        self._connected_client = None

        self._fail_all_waiters(JvcBridgeNotConnectedError("TCP client disconnected"))

    def _consume_task_result(self, task: asyncio.Task[None]) -> None:
        """Consume task result to avoid unhandled task exceptions."""
        with suppress(asyncio.CancelledError):
            task.exception()

    def _assert_can_switch_input(self) -> None:
        """Reject HDMI commands when cached power state is not on."""
        if self._power_on is not True:
            raise JvcBridgeCommandError(
                "Cannot switch input while cached projector power state is not on"
            )

    def _is_recent(self, now_monotonic: float, value_monotonic: float | None) -> bool:
        """Return True when timestamp exists and is within ready TTL."""
        if value_monotonic is None:
            return False

        return (now_monotonic - value_monotonic) <= self._ready_ttl_sec

    def _register_waiter(self, key: WaiterKey) -> asyncio.Future[bytes]:
        """Add a response waiter for a specific result code and command."""
        waiter: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._waiters[key].append(waiter)
        return waiter

    def _remove_waiter(self, key: WaiterKey, waiter: asyncio.Future[bytes]) -> None:
        """Remove a waiter if still pending in waiter queue."""
        queued = self._waiters.get(key)
        if not queued:
            return

        with suppress(ValueError):
            queued.remove(waiter)

        if not queued:
            self._waiters.pop(key, None)

    def _resolve_waiters(self, response: bytes) -> None:
        """Resolve the oldest waiter for the response result code and command.

        A query is answered with an ACK frame followed by a DATA frame with the
        same command, so the result code is part of the match.
        """
        for (result_code, expected_cmd), queued in list(self._waiters.items()):
            if not queued:
                continue

            if response[0] != result_code:
                continue

            if response[3 : 3 + len(expected_cmd)] != expected_cmd:
                continue

            waiter = queued.popleft()
            if not queued:
                self._waiters.pop((result_code, expected_cmd), None)

            if not waiter.done():
                waiter.set_result(response)
            return

    def _fail_all_waiters(self, error: Exception) -> None:
        """Fail all outstanding response waiters."""
        for queued in self._waiters.values():
            while queued:
                waiter = queued.popleft()
                if not waiter.done():
                    waiter.set_exception(error)
        self._waiters.clear()

    def _format_peer_name(self, peername: object) -> str | None:
        """Format asyncio peername into human-readable host:port form."""
        if peername is None:
            return None

        if isinstance(peername, tuple) and len(peername) >= 2:
            return f"{peername[0]}:{peername[1]}"

        return str(peername)
