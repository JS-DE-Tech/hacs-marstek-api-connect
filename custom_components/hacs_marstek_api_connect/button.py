"""Button platform for Marstek Venus E."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek Venus E button entities."""
    coordinator: MarstekDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Remove registry entries created by versions that exposed manual refresh
    # buttons. The coordinator now updates all of these values automatically.
    entity_registry = er.async_get(hass)
    for legacy_suffix in (
        "refresh_battery",
        "refresh_energy_status",
        "refresh_mode",
    ):
        entity_id = entity_registry.async_get_entity_id(
            "button", DOMAIN, f"{entry.entry_id}_{legacy_suffix}"
        )
        if entity_id is not None:
            entity_registry.async_remove(entity_id)

    async_add_entities([MarstekClearSchedulesButton(coordinator, entry)])


class MarstekClearSchedulesButton(CoordinatorEntity, ButtonEntity):
    """Button to clear all manual schedules."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_has_entity_name = True
    _attr_translation_key = "clear_schedules"

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_clear_schedules"
        self._attr_name = None
        self._attr_icon = "mdi:calendar-remove"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Marstek Venus E",
            "manufacturer": "Marstek",
            "model": "Venus E",
        }

    async def async_press(self) -> None:
        """Clear every manual schedule slot."""
        try:
            _LOGGER.info("Clearing all manual schedules via button")
            results = await self.coordinator.clear_all_manual_schedules()
            _LOGGER.info(
                "Cleared manual schedules: %d/%d slots disabled",
                results["success_count"],
                results["total_slots"],
            )
            if results["failed_slots"]:
                slots = ", ".join(
                    str(slot) for slot in results["failed_slots"]
                )
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="schedule_slots_failed",
                    translation_placeholders={"slots": slots},
                )
        except Exception as err:
            _LOGGER.error("Error clearing manual schedules: %s", err)
            if isinstance(err, HomeAssistantError):
                raise
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="schedules_clear_failed",
            ) from err
