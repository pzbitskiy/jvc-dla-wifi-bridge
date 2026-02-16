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
    CMD_READY,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    COMMAND_PAYLOADS,
    INPUT_HDMI1,
    INPUT_HDMI2,
    READY_PROBE_INTERVAL_SEC,
    READY_PROBE_TIMEOUT_SEC,
    RESPONSE_COMMANDS,
    UNIT_ID,
)

_LOGGER = logging.getLogger(__name__)


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
    ) -> None:
        self.listen_host = listen_host
        self.listen_port = listen_port
        self._log_traffic = log_traffic
        self._ready_ttl_sec = ready_ttl_sec
        self._ready_probe_interval_sec = ready_probe_interval_sec

        self._server: asyncio.AbstractServer | None = None

        self._active_reader: asyncio.StreamReader | None = None
        self._active_writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None

        self._ready_probe_task: asyncio.Task[None] | None = None

        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._probe_lock = asyncio.Lock()

        self._waiters: dict[bytes, Deque[asyncio.Future[bytes]]] = defaultdict(deque)

        self._connected_client: str | None = None
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

        _LOGGER.info(
            "Listening for SH-B35W TCP client on %s:%s",
            self.listen_host,
            self.listen_port,
        )

    async def async_stop(self) -> None:
        """Stop TCP listener and clean up all runtime tasks."""
        if self._ready_probe_task is not None:
            self._ready_probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._ready_probe_task
            self._ready_probe_task = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        async with self._connection_lock:
            await self._async_close_active_client_locked()

    async def async_turn_on(self) -> None:
        """Send power on command."""
        await self._async_send_payload(COMMAND_PAYLOADS[CMD_TURN_ON], CMD_TURN_ON)
        self._power_on = True

    async def async_turn_off(self) -> None:
        """Send power off command."""
        await self._async_send_payload(COMMAND_PAYLOADS[CMD_TURN_OFF], CMD_TURN_OFF)
        self._power_on = False

    async def async_set_hdmi1(self) -> None:
        """Switch input to HDMI1 if cached power state allows it."""
        self._assert_can_switch_input()
        await self._async_send_payload(COMMAND_PAYLOADS[CMD_HDMI1], CMD_HDMI1)
        self._input_source = INPUT_HDMI1

    async def async_set_hdmi2(self) -> None:
        """Switch input to HDMI2 if cached power state allows it."""
        self._assert_can_switch_input()
        await self._async_send_payload(COMMAND_PAYLOADS[CMD_HDMI2], CMD_HDMI2)
        self._input_source = INPUT_HDMI2

    async def async_probe_ready(self) -> bool:
        """Send ready command and update readiness cache from response."""
        async with self._probe_lock:
            if not self.connected:
                return False

            expected_cmd = RESPONSE_COMMANDS[CMD_READY]
            waiter = self._register_waiter(expected_cmd)

            try:
                await self._async_send_payload(COMMAND_PAYLOADS[CMD_READY], CMD_READY)
                await asyncio.wait_for(waiter, timeout=READY_PROBE_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                self._remove_waiter(expected_cmd, waiter)
                _LOGGER.debug("Ready probe timed out")
                return False
            except JvcBridgeNotConnectedError:
                self._remove_waiter(expected_cmd, waiter)
                return False
            except Exception:
                self._remove_waiter(expected_cmd, waiter)
                _LOGGER.exception("Unexpected error while probing projector readiness")
                return False

            self._last_ready_ok_monotonic = monotonic()
            self._last_ready_ok_at = dt_util.utcnow()
            return True

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
        asyncio.create_task(self.async_probe_ready())

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

    def _register_waiter(self, expected_cmd: bytes) -> asyncio.Future[bytes]:
        """Add a response waiter for a specific command marker."""
        waiter: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._waiters[expected_cmd].append(waiter)
        return waiter

    def _remove_waiter(self, expected_cmd: bytes, waiter: asyncio.Future[bytes]) -> None:
        """Remove a waiter if still pending in waiter queue."""
        queued = self._waiters.get(expected_cmd)
        if not queued:
            return

        with suppress(ValueError):
            queued.remove(waiter)

        if not queued:
            self._waiters.pop(expected_cmd, None)

    def _resolve_waiters(self, response: bytes) -> None:
        """Resolve one pending waiter whose expected command matches response."""
        for expected_cmd, queued in list(self._waiters.items()):
            if not queued:
                continue

            if response[3 : 3 + len(expected_cmd)] != expected_cmd:
                continue

            waiter = queued.popleft()
            if not queued:
                self._waiters.pop(expected_cmd, None)

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
