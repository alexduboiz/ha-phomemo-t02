"""Shared base entity for the Phomemo T02."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .coordinator import PhomemoCoordinator


class PhomemoEntity(Entity):
    """Common device info, naming and change subscription."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: PhomemoCoordinator, key: str) -> None:
        """Initialise the entity."""
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = coordinator.device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """React to a coordinator change. Subclasses may extend this."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_listener(self._handle_coordinator_update)
        )
