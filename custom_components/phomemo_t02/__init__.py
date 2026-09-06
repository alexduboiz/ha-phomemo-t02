"""The Phomemo T02 integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
import homeassistant.helpers.device_registry as dr

from .composer import LabelState, build_payload
from .const import (
    ALIGNMENTS,
    ATTR_ALIGN,
    ATTR_CAPTION,
    ATTR_COPIES,
    ATTR_DATA,
    ATTR_DITHER,
    ATTR_HEIGHT,
    ATTR_LINES,
    ATTR_PAYLOAD,
    ATTR_SIZE,
    ATTR_TEXT,
    CONF_CHUNK_DELAY_MS,
    CONF_CHUNK_SIZE,
    CONF_IDLE_DISCONNECT_S,
    DEFAULT_ALIGN,
    DEFAULT_CHUNK_DELAY_MS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_FEED_LINES,
    DEFAULT_FONT_SIZE,
    DEFAULT_IDLE_DISCONNECT_S,
    DOMAIN,
    FONT_SIZES,
    SERVICE_FEED,
    SERVICE_PRINT,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_TEXT,
)
from .coordinator import PhomemoCoordinator
from .printer import PhomemoPrinter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
]

type PhomemoConfigEntry = ConfigEntry[PhomemoCoordinator]

# Services accept a device_id or entity_id so several printers can coexist.
_TARGET_SCHEMA = {
    vol.Optional("device_id"): vol.Any(cv.string, [cv.string]),
    vol.Optional("entity_id"): cv.entity_ids,
}

PRINT_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_PAYLOAD): vol.All(cv.ensure_list, [dict]),
        vol.Optional(ATTR_HEIGHT): vol.All(vol.Coerce(int), vol.Range(min=8, max=4000)),
        vol.Optional(ATTR_DITHER, default=False): cv.boolean,
        vol.Optional(ATTR_COPIES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    }
)

PRINT_TEXT_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_SIZE, default=DEFAULT_FONT_SIZE): vol.In(list(FONT_SIZES)),
        vol.Optional(ATTR_ALIGN, default=DEFAULT_ALIGN): vol.In(ALIGNMENTS),
        vol.Optional(ATTR_COPIES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    }
)

PRINT_QR_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_DATA): cv.string,
        vol.Optional(ATTR_CAPTION, default=""): cv.string,
        vol.Optional(ATTR_SIZE, default=DEFAULT_FONT_SIZE): vol.In(list(FONT_SIZES)),
        vol.Optional(ATTR_ALIGN, default=DEFAULT_ALIGN): vol.In(ALIGNMENTS),
        vol.Optional(ATTR_COPIES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    }
)

FEED_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_LINES, default=DEFAULT_FEED_LINES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=255)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: PhomemoConfigEntry) -> bool:
    """Set up a Phomemo T02 from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    options = entry.options

    printer = PhomemoPrinter(
        hass,
        address,
        chunk_size=options.get(CONF_CHUNK_SIZE, DEFAULT_CHUNK_SIZE),
        chunk_delay_ms=options.get(CONF_CHUNK_DELAY_MS, DEFAULT_CHUNK_DELAY_MS),
        idle_disconnect_s=options.get(CONF_IDLE_DISCONNECT_S, DEFAULT_IDLE_DISCONNECT_S),
    )
    coordinator = PhomemoCoordinator(hass, entry, printer)

    # Render an initial preview so the dashboard has something to show at once.
    try:
        await coordinator.async_refresh_preview()
    except Exception as err:  # noqa: BLE001 - rendering must not block setup
        raise ConfigEntryNotReady(f"Could not render the initial preview: {err}") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: PhomemoConfigEntry) -> None:
    """Reload when options change so new BLE tuning takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PhomemoConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_PRINT):
        return

    def _coordinators(call: ServiceCall) -> list[PhomemoCoordinator]:
        """Resolve the targeted printers, defaulting to all configured ones."""
        entries: list[PhomemoConfigEntry] = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None) is not None
        ]
        wanted: set[str] = set()

        if device_ids := call.data.get("device_id"):
            device_reg = dr.async_get(hass)
            for device_id in cv.ensure_list(device_ids):
                if device := device_reg.async_get(device_id):
                    wanted.update(device.config_entries)

        if entity_ids := call.data.get("entity_id"):
            entity_reg = er.async_get(hass)
            for entity_id in entity_ids:
                if (entity := entity_reg.async_get(entity_id)) and entity.config_entry_id:
                    wanted.add(entity.config_entry_id)

        resolved = [
            entry.runtime_data for entry in entries if not wanted or entry.entry_id in wanted
        ]
        if not resolved:
            raise HomeAssistantError("No Phomemo T02 printer matched this service call")
        return resolved

    async def _handle_print(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            await coordinator.async_print_payload(
                call.data[ATTR_PAYLOAD],
                height=call.data.get(ATTR_HEIGHT),
                dither=call.data[ATTR_DITHER],
                copies=call.data[ATTR_COPIES],
            )

    async def _handle_print_text(call: ServiceCall) -> None:
        state = LabelState(
            text=call.data[ATTR_TEXT],
            size=call.data[ATTR_SIZE],
            align=call.data[ATTR_ALIGN],
        )
        for coordinator in _coordinators(call):
            await coordinator.async_print_payload(
                build_payload(state), copies=call.data[ATTR_COPIES]
            )

    async def _handle_print_qr(call: ServiceCall) -> None:
        state = LabelState(
            text=call.data[ATTR_CAPTION],
            qr=call.data[ATTR_DATA],
            size=call.data[ATTR_SIZE],
            align=call.data[ATTR_ALIGN],
        )
        for coordinator in _coordinators(call):
            await coordinator.async_print_payload(
                build_payload(state), copies=call.data[ATTR_COPIES]
            )

    async def _handle_feed(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            await coordinator.async_feed(call.data[ATTR_LINES])

    hass.services.async_register(DOMAIN, SERVICE_PRINT, _handle_print, PRINT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT, _handle_print_text, PRINT_TEXT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_QR, _handle_print_qr, PRINT_QR_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FEED, _handle_feed, FEED_SCHEMA)
