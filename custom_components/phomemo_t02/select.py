"""Select entities for font size and justification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import PhomemoConfigEntry
from .composer import LabelState
from .const import ALIGNMENTS, FONT_SIZES
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


@dataclass(frozen=True, kw_only=True)
class PhomemoSelectDescription(SelectEntityDescription):
    """Describes a composer choice field."""

    get_value: Callable[[LabelState], str]
    set_value: Callable[[LabelState, str], None]


SELECTS: tuple[PhomemoSelectDescription, ...] = (
    PhomemoSelectDescription(
        key="font_size",
        translation_key="font_size",
        icon="mdi:format-size",
        options=list(FONT_SIZES),
        get_value=lambda state: state.size,
        set_value=lambda state, value: setattr(state, "size", value),
    ),
    PhomemoSelectDescription(
        key="align",
        translation_key="align",
        icon="mdi:format-align-center",
        options=ALIGNMENTS,
        get_value=lambda state: state.align,
        set_value=lambda state, value: setattr(state, "align", value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the composer selects."""
    coordinator = entry.runtime_data
    async_add_entities(PhomemoSelect(coordinator, desc) for desc in SELECTS)


class PhomemoSelect(PhomemoEntity, SelectEntity, RestoreEntity):
    """A choice field feeding the label preview."""

    entity_description: PhomemoSelectDescription

    def __init__(
        self, coordinator: PhomemoCoordinator, description: PhomemoSelectDescription
    ) -> None:
        """Initialise the select entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = list(description.options or [])

    @property
    def current_option(self) -> str:
        """Currently selected option."""
        return self.entity_description.get_value(self.coordinator.composer.state)

    async def async_added_to_hass(self) -> None:
        """Restore the last selection."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state in (
            self._attr_options
        ):
            self.entity_description.set_value(self.coordinator.composer.state, last.state)
            await self.coordinator.async_refresh_preview()

    async def async_select_option(self, option: str) -> None:
        """Apply the selection and re-render the preview."""
        self.entity_description.set_value(self.coordinator.composer.state, option)
        await self.coordinator.async_refresh_preview()
