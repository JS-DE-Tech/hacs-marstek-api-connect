"""The Marstek Venus E integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MODE_STORAGE
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Marstek Venus E integration.
    
    Args:
        hass: Home Assistant instance
        config: Configuration dictionary
        
    Returns:
        True if setup successful
    """
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    # Domain services must be available even when no config entry is loaded,
    # so automations can always be edited and validated.
    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Marstek Venus E from a config entry.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        
    Returns:
        True if setup successful
        
    Raises:
        ConfigEntryNotReady: If device is not ready
    """
    coordinator = MarstekDataUpdateCoordinator(hass, entry)
    # Restore the persistent operating-mode setpoint. Automatic winter mode
    # remains responsible for its own internal Auto/Storage transitions.
    await coordinator.async_load_storage_mode()
    await coordinator.async_load_automatic_storage()
    await coordinator.async_load_desired_operating_mode()
    await coordinator.async_load_diagnostics()
    
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to device: {err}") from err

    try:
        if coordinator.automatic_storage_enabled:
            # The restored winter controller applies its persisted phase below.
            pass
        elif coordinator.desired_operating_mode == MODE_STORAGE:
            await coordinator.async_enable_storage_mode()
        else:
            await coordinator.async_apply_desired_operating_mode()
    except Exception as err:
        _LOGGER.warning(
            "Could not restore operating mode %s while starting: %s",
            coordinator.desired_operating_mode,
            err,
        )

    try:
        await coordinator.async_start_automatic_storage_controller()
    except Exception as err:
        _LOGGER.warning(
            "Could not start automatic storage controller: %s", err
        )

    coordinator.async_start_mode_enforcement()

    initial_setup_store = Store(
        hass, 1, f"{DOMAIN}.{entry.entry_id}.initial_setup"
    )
    initial_setup = await initial_setup_store.async_load()
    if not (initial_setup and initial_setup.get("led_initialized")):
        try:
            await coordinator.async_set_led_state(True)
            await initial_setup_store.async_save({"led_initialized": True})
        except Exception as err:
            _LOGGER.warning(
                "Could not turn on the LED during initial setup: %s", err
            )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup reload listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        
    Returns:
        True if unload successful
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Marstek Venus E.
    
    Args:
        hass: Home Assistant instance
    """
    from .services import async_setup_services as setup_services
    
    await setup_services(hass)
