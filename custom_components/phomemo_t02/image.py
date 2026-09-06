"""Live preview of the composed label."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PhomemoConfigEntry
from .const import DOTS_PER_LINE
from .coordinator import PhomemoCoordinator
from .entity import PhomemoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhomemoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the preview image."""
    async_add_entities([PhomemoPreview(hass, entry.runtime_data)])


class PhomemoPreview(PhomemoEntity, ImageEntity):
    """Renders exactly the bitmap that will be printed.

    The frontend refetches whenever `image_last_updated` changes, so the
    coordinator bumps that timestamp after each render -- never this entity, and
    never inside `async_image()`.
    """

    _attr_translation_key = "preview"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator: PhomemoCoordinator) -> None:
        """Initialise the preview entity."""
        PhomemoEntity.__init__(self, coordinator, "preview")
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated = coordinator.preview_updated

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the new render timestamp, which makes the frontend refetch.

        `image_last_updated` is a cached property on ImageEntity backed by this
        attribute, so it is set here rather than overridden.
        """
        self._attr_image_last_updated = self.coordinator.preview_updated
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, float | int]:
        """Expose how much paper this label will use."""
        cached = self.coordinator.composer.cached
        if cached is None:
            return {}
        return {
            "width_dots": DOTS_PER_LINE,
            "height_dots": cached.height_px,
            "paper_mm": round(cached.paper_mm, 1),
        }

    async def async_image(self) -> bytes | None:
        """Return the cached PNG, rendering one if needed."""
        rendered = await self.coordinator.async_current_label()
        return rendered.png
