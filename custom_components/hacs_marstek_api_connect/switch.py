"""Switch platform for Marstek Venus E."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek Venus E switch entities.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities
    """
    coordinator: MarstekDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        MarstekLedSwitch(coordinator, entry),
        MarstekAutomaticStorageSwitch(coordinator, entry),
    ]
    
    async_add_entities(entities)


class MarstekLedSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch entity for Marstek Venus E LED control."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "led_ctrl"
    _attr_assumed_state = False

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch.
        
        Args:
            coordinator: Data update coordinator
            entry: Configuration entry
        """
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_led_ctrl"
        self._attr_icon = "mdi:led-on"
        self._is_on: bool | None = None
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Marstek",
            "model": "Venus E",
        }
    
    @property
    def is_on(self) -> bool | None:
        """Return True if LED is on."""
        if self.coordinator.led_state is not None:
            return self.coordinator.led_state
        return self._is_on

    async def async_added_to_hass(self) -> None:
        """Restore the last state known to Home Assistant.

        The Marstek Open API Rev 2.0 exposes Led.Ctrl only as a write command
        and provides no method for reading the physical LED state.
        """
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if self.coordinator.led_state is None and last_state is not None:
            self._is_on = last_state.state == STATE_ON
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LED on."""
        try:
            result = await self.coordinator.client.set_led_ctrl(True)
            if result.get("set_result") is False:
                raise ValueError("Device rejected LED on command")
            self._is_on = True
            self.coordinator.led_state = True
            _LOGGER.info("LED control: Command ON sent to Marstek device at %s", self.coordinator.client.ip_address)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to turn on LED: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off."""
        try:
            result = await self.coordinator.client.set_led_ctrl(False)
            if result.get("set_result") is False:
                raise ValueError("Device rejected LED off command")
            self._is_on = False
            self.coordinator.led_state = False
            _LOGGER.info("LED control: Command OFF sent to Marstek device at %s", self.coordinator.client.ip_address)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to turn off LED: %s", err)
            raise


class MarstekAutomaticStorageSwitch(CoordinatorEntity, SwitchEntity):
    """Enable weather-adaptive automatic storage/winter operation."""

    _attr_has_entity_name = True
    _attr_translation_key = "automatic_storage"
    _attr_icon = "mdi:snowflake-thermometer"

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_automatic_storage"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Marstek",
            "model": "Venus E",
        }

    @property
    def is_on(self) -> bool:
        """Return whether automatic winter operation is enabled."""
        return self.coordinator.automatic_storage_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable automatic winter operation and begin observation."""
        await self.coordinator.async_set_automatic_storage(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable automatic winter operation and return to Auto."""
        await self.coordinator.async_set_automatic_storage(False)
