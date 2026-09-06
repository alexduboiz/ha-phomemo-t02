"""Text entities for composing a label."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import PhomemoConfigEntry
from .composer import LabelState
from .const import MAX_TEXT_LENGTH
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


@dataclass(frozen=True, kw_only=True)
class PhomemoTextDescription(TextEntityDescription):
    """Describes a composer text field."""

    get_value: Callable[[LabelState], str]
    set_value: Callable[[LabelState, str], None]


TEXTS: tuple[PhomemoTextDescription, ...] = (
    PhomemoTextDescription(
        key="label_text",
        translation_key="label_text",
        icon="mdi:format-text",
        get_value=lambda state: state.text,
        set_value=lambda state, value: setattr(state, "text", value),
    ),
    PhomemoTextDescription(
        key="label_qr",
        translation_key="label_qr",
        icon="mdi:qrcode",
        get_value=lambda state: state.qr,
        set_value=lambda state, value: setattr(state, "qr", value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the composer text fields."""
    coordinator = entry.runtime_data
    async_add_entities(PhomemoText(coordinator, desc) for desc in TEXTS)


class PhomemoText(PhomemoEntity, TextEntity, RestoreEntity):
    """A free-text field feeding the label preview."""

    entity_description: PhomemoTextDescription
    _attr_native_max = MAX_TEXT_LENGTH
    _attr_native_min = 0

    def __init__(
        self, coordinator: PhomemoCoordinator, description: PhomemoTextDescription
    ) -> None:
        """Initialise the text entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str:
        """Current field contents."""
        return self.entity_description.get_value(self.coordinator.composer.state)

    async def async_added_to_hass(self) -> None:
        """Restore the last label so it survives a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state not in (
            None,
            "unknown",
            "unavailable",
        ):
            self.entity_description.set_value(self.coordinator.composer.state, last.state)
            await self.coordinator.async_refresh_preview()

    async def async_set_value(self, value: str) -> None:
        """Update the field and re-render the preview."""
        self.entity_description.set_value(self.coordinator.composer.state, value)
        await self.coordinator.async_refresh_preview()
