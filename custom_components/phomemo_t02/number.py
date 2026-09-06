"""Number entity for the copy count."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import PhomemoConfigEntry
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the copies control."""
    async_add_entities([PhomemoCopies(entry.runtime_data)])


class PhomemoCopies(PhomemoEntity, NumberEntity, RestoreEntity):
    """How many times to print the composed label."""

    _attr_translation_key = "copies"
    _attr_icon = "mdi:content-duplicate"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PhomemoCoordinator) -> None:
        """Initialise the copies entity."""
        super().__init__(coordinator, "copies")

    @property
    def native_value(self) -> float:
        """Current copy count."""
        return self.coordinator.composer.state.copies

    async def async_added_to_hass(self) -> None:
        """Restore the last copy count."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self.coordinator.composer.state.copies = int(float(last.state))
            except (TypeError, ValueError):
                pass  # Unknown/unavailable restores keep the default of 1.

    async def async_set_native_value(self, value: float) -> None:
        """Set the copy count.

        No re-render: copies do not change the bitmap, only how many times it is
        sent, so the cached preview stays valid.
        """
        self.coordinator.composer.state.copies = int(value)
        self.async_write_ha_state()
