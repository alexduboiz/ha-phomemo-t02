"""BLE transport for the Phomemo T02.

Resolves the device through Home Assistant's Bluetooth stack rather than scanning
with bleak directly -- that indirection is what lets the same code work over an
ESPHome Bluetooth proxy and a local adapter without changing anything.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from PIL import Image

from .const import (
    DEFAULT_CHUNK_DELAY_MS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_FEED_LINES,
    DEFAULT_IDLE_DISCONNECT_S,
    NOTIFY_UUID,
    WRITE_UUID,
)
from .protocol import cmd_feed, encode_job

_LOGGER = logging.getLogger(__name__)

MIN_CHUNK = 20
CONNECT_TIMEOUT = 25.0
DRAIN_SECONDS = 1.5


class PrinterUnavailable(HomeAssistantError):
    """The printer could not be reached."""


class PhomemoPrinter:
    """Owns the BLE connection and serialises print jobs."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_delay_ms: int = DEFAULT_CHUNK_DELAY_MS,
        idle_disconnect_s: int = DEFAULT_IDLE_DISCONNECT_S,
    ) -> None:
        self.hass = hass
        self.address = address.upper()
        self.chunk_size = chunk_size
        self.chunk_delay_ms = chunk_delay_ms
        self.idle_disconnect_s = idle_disconnect_s

        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._disconnect_task: asyncio.Task | None = None
        self._available = True
        self._listeners: list[Callable[[], None]] = []

    # --- availability -----------------------------------------------------
    @property
    def available(self) -> bool:
        """Whether the printer was reachable at the last attempt."""
        return self._available

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired when availability changes."""
        self._listeners.append(callback)

        def _remove() -> None:
            self._listeners.remove(callback)

        return _remove

    def _set_available(self, value: bool) -> None:
        if self._available != value:
            self._available = value
            for listener in list(self._listeners):
                listener()

    # --- connection -------------------------------------------------------
    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("T02 %s disconnected", self.address)
        self._client = None

    async def _connect(self) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            return self._client

        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            self._set_available(False)
            raise PrinterUnavailable(
                f"Phomemo T02 ({self.address}) was not found. The printer sleeps to "
                "save battery and stops advertising - press its power button, and "
                "make sure it is in range of a Bluetooth adapter or an ESPHome "
                "proxy with active connections enabled."
            )

        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                self.address,
                self._on_disconnect,
                use_services_cache=True,
                timeout=CONNECT_TIMEOUT,
                max_attempts=3,
            )
        except Exception as err:
            self._set_available(False)
            raise PrinterUnavailable(
                f"Could not connect to the Phomemo T02 ({self.address}): {err}"
            ) from err

        self._client = client
        self._set_available(True)
        return client

    def _schedule_disconnect(self) -> None:
        """Drop the link after an idle period so a proxy slot is not held open."""
        if self._disconnect_task is not None:
            self._disconnect_task.cancel()

        async def _later() -> None:
            try:
                await asyncio.sleep(self.idle_disconnect_s)
                await self.async_disconnect()
            except asyncio.CancelledError:
                pass

        self._disconnect_task = self.hass.async_create_background_task(
            _later(), name=f"phomemo_t02 idle disconnect {self.address}"
        )

    async def async_disconnect(self) -> None:
        """Close the BLE connection if open."""
        if self._disconnect_task is not None:
            self._disconnect_task.cancel()
            self._disconnect_task = None
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except Exception as err:  # noqa: BLE001 - teardown must not raise
                _LOGGER.debug("Error disconnecting from %s: %s", self.address, err)

    # --- writing ----------------------------------------------------------
    @staticmethod
    def _notify_handler(_sender: int, data: bytearray) -> None:
        # The T02 emits 01 01 repeatedly while printing. Logged for diagnostics
        # only; we deliberately do not gate writes on it.
        _LOGGER.debug("T02 notify: %s", data.hex(" "))

    async def _write(self, client: BleakClientWithServiceCache, payload: bytes) -> None:
        char: BleakGATTCharacteristic | None = client.services.get_characteristic(WRITE_UUID)
        if char is None:
            raise PrinterUnavailable(
                f"Write characteristic {WRITE_UUID} is missing - is this really a T02?"
            )

        no_response = "write-without-response" in char.properties
        mtu = getattr(client, "mtu_size", 0) or 23
        chunk = max(MIN_CHUNK, min(self.chunk_size, mtu - 3))
        delay = self.chunk_delay_ms / 1000

        _LOGGER.debug(
            "Sending %d bytes to %s (mtu=%d chunk=%d no_response=%s)",
            len(payload),
            self.address,
            mtu,
            chunk,
            no_response,
        )

        started = time.monotonic()
        for offset in range(0, len(payload), chunk):
            await client.write_gatt_char(
                char, payload[offset : offset + chunk], response=not no_response
            )
            if delay:
                await asyncio.sleep(delay)

        elapsed = time.monotonic() - started
        _LOGGER.debug(
            "Sent %d bytes in %.2fs (%.2f KB/s)",
            len(payload),
            elapsed,
            len(payload) / elapsed / 1024 if elapsed else 0,
        )

    async def _send(self, payload: bytes) -> None:
        async with self._lock:
            client = await self._connect()
            try:
                await client.start_notify(NOTIFY_UUID, self._notify_handler)
            except Exception as err:  # noqa: BLE001 - notifications are optional
                _LOGGER.debug("Notify unavailable on %s: %s", self.address, err)

            try:
                await self._write(client, payload)
            except PrinterUnavailable:
                raise
            except Exception as err:
                self._set_available(False)
                await self.async_disconnect()
                raise PrinterUnavailable(
                    f"Print failed on the Phomemo T02 ({self.address}): {err}"
                ) from err

            # Let the print head drain before the link can drop.
            await asyncio.sleep(DRAIN_SECONDS)
            self._schedule_disconnect()

    # --- public API -------------------------------------------------------
    async def async_print_image(
        self,
        image: Image.Image,
        *,
        copies: int = 1,
        feed_lines: int = DEFAULT_FEED_LINES,
        dither: bool = False,
    ) -> None:
        """Print a rendered image, optionally more than once."""
        payload = encode_job(image, feed_lines=feed_lines, dither=dither)
        for _ in range(max(1, copies)):
            await self._send(payload)

    async def async_feed(self, lines: int) -> None:
        """Advance the paper."""
        await self._send(cmd_feed(lines))
