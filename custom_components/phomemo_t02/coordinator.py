"""Coordinates label state, rendering and printing for one T02."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.util import dt as dt_util
from PIL import Image

from .composer import LabelComposer, RenderedLabel
from .const import DEFAULT_FEED_LINES, DOMAIN, MANUFACTURER, MODEL
from .printer import PhomemoPrinter

_LOGGER = logging.getLogger(__name__)


class PhomemoCoordinator:
    """Owns the composer and printer, and notifies entities of changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        printer: PhomemoPrinter,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.printer = printer
        self.composer = LabelComposer()

        self._listeners: list[Callable[[], None]] = []
        self.preview_updated = dt_util.utcnow()

    @property
    def address(self) -> str:
        """The printer's Bluetooth address."""
        return self.printer.address

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry shared by every platform."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            connections={(CONNECTION_BLUETOOTH, self.address)},
            name=self.entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    # --- listeners --------------------------------------------------------
    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to preview/state changes."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --- rendering --------------------------------------------------------
    async def async_refresh_preview(self) -> RenderedLabel:
        """Re-render the current label state and wake up the preview entity.

        `image_last_updated` is bumped here rather than inside the image
        entity's `async_image()`, per Home Assistant's documented pattern -- that
        is what makes the frontend refetch.
        """
        rendered = await self.hass.async_add_executor_job(self.composer.render)
        self.preview_updated = dt_util.utcnow()
        self._notify()
        return rendered

    async def async_current_label(self) -> RenderedLabel:
        """The cached render, producing one first if needed."""
        if (cached := self.composer.cached) is not None:
            return cached
        return await self.async_refresh_preview()

    # --- printing ---------------------------------------------------------
    async def async_print_current(self) -> None:
        """Print exactly the bitmap that is currently previewed."""
        rendered = await self.async_current_label()
        await self.printer.async_print_image(
            rendered.bitmap, copies=self.composer.state.copies
        )

    async def async_print_payload(
        self,
        payload: list[dict],
        *,
        height: int | None = None,
        dither: bool = False,
        copies: int = 1,
    ) -> None:
        """Render and print an ad-hoc imagespec payload (used by services)."""
        image: Image.Image = await self.hass.async_add_executor_job(
            lambda: self.composer.render_once(payload, height=height, dither=dither)
        )
        await self.printer.async_print_image(image, copies=copies, dither=False)

    async def async_feed(self, lines: int = DEFAULT_FEED_LINES) -> None:
        """Advance the paper."""
        await self.printer.async_feed(lines)

    async def async_shutdown(self) -> None:
        """Release the BLE connection."""
        await self.printer.async_disconnect()
