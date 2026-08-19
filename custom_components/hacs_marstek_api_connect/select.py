"""Select platform for Marstek Venus E."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLED_MODES,
    DOMAIN,
    MODE_MANUAL,
    MODE_PASSIVE,
    MODE_STANDBY,
    MODE_STORAGE,
    SELECTABLE_MODES,
)
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_MODE_TO_OPTION = {mode: mode.lower() for mode in SELECTABLE_MODES}
_OPTION_TO_MODE = {option: mode for mode, option in _MODE_TO_OPTION.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek Venus E select entities.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities
    """
    coordinator: MarstekDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        MarstekOperatingModeSelect(coordinator, entry),
    ]
    
    async_add_entities(entities)


class MarstekOperatingModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for Marstek Venus E operating mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "operating_mode"
    
    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity.
        
        Args:
            coordinator: Data update coordinator
            entry: Configuration entry
        """
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_operating_mode"
        configured_modes = entry.options.get(CONF_ENABLED_MODES, SELECTABLE_MODES)
        if MODE_PASSIVE in configured_modes:
            configured_modes = [
                mode for mode in configured_modes if mode != MODE_PASSIVE
            ] + [MODE_STANDBY, MODE_MANUAL]
        self._configured_options = [
            mode for mode in SELECTABLE_MODES if mode in configured_modes
        ]
        self._attr_icon = "mdi:cog"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Marstek",
            "model": "Venus E",
        }
    
    @property
    def options(self) -> list[str]:
        """Return the configured modes plus Storage while it is active."""
        if (
            self.coordinator.storage_mode_enabled
            and MODE_STORAGE not in self._configured_options
        ):
            modes = [*self._configured_options, MODE_STORAGE]
        else:
            modes = self._configured_options
        return [_MODE_TO_OPTION[mode] for mode in modes]

    @property
    def current_option(self) -> str | None:
        """Return the persistent operating-mode setpoint."""
        if self.coordinator.storage_mode_enabled:
            mode = MODE_STORAGE
        else:
            mode = self.coordinator.desired_operating_mode
        return _MODE_TO_OPTION.get(mode) if mode is not None else None
    
    async def async_select_option(self, option: str) -> None:
        """Change the operating mode.
        
        Args:
            option: New operating mode
        """
        mode = _OPTION_TO_MODE.get(option)
        if mode is None:
            _LOGGER.error("Invalid mode: %s", option)
            return
        
        try:
            await self.coordinator.async_select_operating_mode(mode)
            _LOGGER.info("Changed operating mode to: %s", mode)
        except Exception as err:
            _LOGGER.error("Failed to set mode to %s: %s", mode, err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="mode_not_confirmed",
                translation_placeholders={"mode": mode},
            ) from err
