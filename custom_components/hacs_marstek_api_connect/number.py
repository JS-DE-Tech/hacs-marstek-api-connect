"""Number entities for the Marstek Venus E integration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MarstekDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the persistent manual-power slider."""
    coordinator: MarstekDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MarstekManualPowerNumber(coordinator, entry)])


class MarstekManualPowerNumber(CoordinatorEntity, NumberEntity):
    """Persistent direct charge/discharge power target."""

    _attr_has_entity_name = True
    _attr_translation_key = "manual_power"
    _attr_icon = "mdi:battery-sync"
    _attr_native_min_value = -2400
    _attr_native_max_value = 2400
    _attr_native_step = 100
    _attr_native_unit_of_measurement = "W"
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_manual_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Marstek",
            "model": "Venus E",
        }

    @property
    def native_value(self) -> float:
        """Return the persistent manual power target."""
        return self.coordinator.manual_power

    async def async_set_native_value(self, value: float) -> None:
        """Persist and, while Manual is active, apply a new target."""
        await self.coordinator.async_set_manual_power(int(value))
