"""Buttons: print the composed label, feed paper, print a self-test."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PhomemoConfigEntry
from .composer import LabelState, build_payload
from .const import DEFAULT_FEED_LINES
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


async def _print_current(coordinator: PhomemoCoordinator) -> None:
    await coordinator.async_print_current()


async def _feed(coordinator: PhomemoCoordinator) -> None:
    await coordinator.async_feed(DEFAULT_FEED_LINES * 4)


async def _test_print(coordinator: PhomemoCoordinator) -> None:
    """Print a fixed label that exercises text and QR rendering together."""
    state = LabelState(
        text="Phomemo T02 ready", qr="https://www.home-assistant.io", size="Medium"
    )
    await coordinator.async_print_payload(build_payload(state))


@dataclass(frozen=True, kw_only=True)
class PhomemoButtonDescription(ButtonEntityDescription):
    """Describes a button action."""

    action: Callable[[PhomemoCoordinator], Coroutine[Any, Any, None]]


BUTTONS: tuple[PhomemoButtonDescription, ...] = (
    PhomemoButtonDescription(
        key="print_label",
        translation_key="print_label",
        icon="mdi:printer",
        action=_print_current,
    ),
    PhomemoButtonDescription(
        key="test_print",
        translation_key="test_print",
        icon="mdi:printer-check",
        action=_test_print,
    ),
    PhomemoButtonDescription(
        key="feed",
        translation_key="feed",
        icon="mdi:arrow-down-bold-box-outline",
        action=_feed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(PhomemoButton(coordinator, desc) for desc in BUTTONS)


class PhomemoButton(PhomemoEntity, ButtonEntity):
    """A one-shot printer action."""

    entity_description: PhomemoButtonDescription

    def __init__(
        self, coordinator: PhomemoCoordinator, description: PhomemoButtonDescription
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Run the button's action."""
        await self.entity_description.action(self.coordinator)
