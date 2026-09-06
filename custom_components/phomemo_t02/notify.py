"""Notify entity so the printer can be a notification target."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PhomemoConfigEntry
from .composer import LabelState, build_payload
from .const import DEFAULT_ALIGN
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the notify target."""
    async_add_entities([PhomemoNotify(entry.runtime_data)])


class PhomemoNotify(PhomemoEntity, NotifyEntity):
    """Prints notification messages as labels."""

    _attr_translation_key = "notify"
    _attr_icon = "mdi:printer-alert"

    def __init__(self, coordinator: PhomemoCoordinator) -> None:
        """Initialise the notify entity."""
        super().__init__(coordinator, "notify")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Print a notification.

        A title, when given, is printed larger above the message. This renders
        ad-hoc and deliberately leaves the composer's cached preview untouched.
        """
        text = f"{title}\n{message}" if title else message
        state = LabelState(text=text, size="Medium", align=DEFAULT_ALIGN)
        await self.coordinator.async_print_payload(build_payload(state))
