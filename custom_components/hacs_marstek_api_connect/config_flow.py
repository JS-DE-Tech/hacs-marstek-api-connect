"""Config flow for Marstek Venus E integration."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_BLE_MAC,
    CONF_FAST_SCAN_INTERVAL,
    CONF_MODE_SCAN_INTERVAL,
    CONF_ENABLED_MODES,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_SURPLUS_OFF_MINUTES,
    CONF_SOLAR_SURPLUS_OFF_W,
    CONF_SOLAR_SURPLUS_ON_MINUTES,
    CONF_SOLAR_SURPLUS_ON_W,
    CONF_STORAGE_RECHARGE_END,
    CONF_STORAGE_RECHARGE_START,
    CONF_STORAGE_OBSERVATION_DAYS,
    DEFAULT_SOLAR_SURPLUS_OFF_MINUTES,
    DEFAULT_SOLAR_SURPLUS_OFF_W,
    DEFAULT_SOLAR_SURPLUS_ON_MINUTES,
    DEFAULT_SOLAR_SURPLUS_ON_W,
    DEFAULT_STORAGE_RECHARGE_END,
    DEFAULT_STORAGE_RECHARGE_START,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MODE_MANUAL,
    MODE_STANDBY,
    SELECTABLE_MODES,
    STORAGE_OBSERVATION_DAYS,
)
from .logic import (
    device_selection_options,
    normalize_ipv4,
    week_set_from_days,
)
from .udp_client import MarstekUDPClient

_LOGGER = logging.getLogger(__name__)

ACTION_MANUAL = "manual"
ACTION_RETRY_DISCOVERY = "retry_discovery"
MODE_OPTION_TO_MODE = {mode.lower(): mode for mode in SELECTABLE_MODES}


class MarstekConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Marstek Venus E."""

    VERSION = 1
    
    def __init__(self):
        """Initialize config flow."""
        super().__init__()
        self.discovered_devices: list[tuple[str, int, dict[str, Any]]] = []
    
    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MarstekOptionsFlow:
        """Get the options flow for this handler."""
        return MarstekOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start device discovery immediately when the flow opens."""
        return await self.async_step_discovery()

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle discovery step.
        
        Attempts to discover Marstek devices on the local network.
        
        Args:
            user_input: Input from the user
            
        Returns:
            Config flow result
        """
        errors: dict[str, str] = {}
        
        # Attempt automatic discovery
        try:
            _LOGGER.debug("Starting Marstek device discovery...")
            self.discovered_devices = await MarstekUDPClient.discover(
                timeout=15.0, port=DEFAULT_PORT
            )
            _LOGGER.debug("Found %d device(s)", len(self.discovered_devices))
        except Exception as err:
            _LOGGER.error("Device discovery failed: %s", err)
            self.discovered_devices = []

        if not self.discovered_devices:
            _LOGGER.warning(
                "No Marstek devices responded to broadcast discovery; "
                "falling back to manual IP entry"
            )
            return await self.async_step_manual_ip()

        # Move to selection step
        return await self.async_step_select_device()

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection step.
        
        Allows user to select from discovered devices or enter IP manually.
        
        Args:
            user_input: Input from the user
            
        Returns:
            Config flow result
        """
        errors: dict[str, str] = {}
        
        if user_input is not None:
            selected = user_input.get(CONF_IP_ADDRESS)
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            ble_mac = user_input.get(CONF_BLE_MAC, "")

            _LOGGER.debug("User selected device value: %s (port %s)", selected, port)

            if selected == ACTION_RETRY_DISCOVERY:
                return await self.async_step_discovery()

            # If user chose manual entry, present a dedicated form
            if selected == ACTION_MANUAL:
                return await self.async_step_manual_ip()

            # Otherwise selected should be an IP (from device_options) or direct input
            ip_address = selected

            if not ip_address:
                errors["base"] = "no_device_selected"
            else:
                # For discovered devices, extract BLE MAC from the discovery response
                # A discovery response proves reachability even though this
                # firmware does not answer unicast connection checks.
                for disc_ip, _disc_port, payload in self.discovered_devices:
                    device_info = payload.get("result", {})
                    discovered_ip = normalize_ipv4(
                        device_info.get("ip") or disc_ip
                    )
                    if discovered_ip == ip_address:
                        if not ble_mac:
                            ble_mac = device_info.get("ble_mac", "")
                        break
                
                # Check if already configured
                await self.async_set_unique_id(ip_address)
                self._abort_if_unique_id_configured()
                
                # Store the data for potential schedule clearing
                self.context["ip_address"] = ip_address
                self.context["port"] = port
                self.context["ble_mac"] = ble_mac
                
                # Ask if user wants to clear schedules
                return await self.async_step_clear_schedules()
        
        try:
            translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "selector",
                {DOMAIN},
            )
        except Exception as err:
            _LOGGER.debug(
                "Could not load setup action translations: %s", err
            )
            translations = {}
        translation_prefix = (
            f"component.{DOMAIN}.selector.device_selection.options"
        )
        device_options = device_selection_options(
            self.discovered_devices,
            [
                (
                    ACTION_RETRY_DISCOVERY,
                    translations.get(
                        f"{translation_prefix}.{ACTION_RETRY_DISCOVERY}",
                        "Search again",
                    ),
                ),
                (
                    ACTION_MANUAL,
                    translations.get(
                        f"{translation_prefix}.{ACTION_MANUAL}",
                        "Enter IP address manually",
                    ),
                ),
            ],
        )
        
        # Build schema
        schema = {}
        
        if device_options:
            schema[vol.Required(CONF_IP_ADDRESS)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=device_options,
                )
            )
        else:
            schema[vol.Required(CONF_IP_ADDRESS)] = str
        
        schema[vol.Optional(CONF_PORT, default=DEFAULT_PORT)] = int
        schema[vol.Optional(CONF_BLE_MAC, default="")] = str
        
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "device_count": str(len(self.discovered_devices)),
            },
        )

    async def async_step_manual_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual IP entry when user chooses to enter an IP manually.
        
        Note: Connection validation is skipped for manual entry since the device
        only responds to UDP broadcasts, not to unicast requests. The connection
        will be verified when the integration attempts to retrieve data after
        configuration is saved.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input.get(CONF_IP_ADDRESS)
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            ble_mac = user_input.get(CONF_BLE_MAC, "")

            _LOGGER.debug("Manual IP provided: %s:%s", ip_address, port)

            try:
                ipaddress.ip_address(ip_address or "")
            except ValueError:
                errors["base"] = "invalid_ip"
            else:
                # Check if already configured
                await self.async_set_unique_id(
                    ble_mac.lower() if ble_mac else ip_address
                )
                self._abort_if_unique_id_configured()
                
                # Store the data for potential schedule clearing
                self.context["ip_address"] = ip_address
                self.context["port"] = port
                self.context["ble_mac"] = ble_mac
                
                # Ask if user wants to clear schedules
                return await self.async_step_clear_schedules()

        schema = vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_BLE_MAC, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="manual_ip",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_clear_schedules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask user if they want to clear all manual schedules.
        
        Args:
            user_input: Input from the user
            
        Returns:
            Config flow result
        """
        errors: dict[str, str] = {}
        
        if user_input is not None:
            clear_schedules = user_input.get("clear_schedules", False)
            
            # Get device info from context
            ip_address = self.context.get("ip_address")
            port = self.context.get("port", DEFAULT_PORT)
            ble_mac = self.context.get("ble_mac", "")
            
            # If user wants to clear schedules, do it now
            if clear_schedules:
                try:
                    _LOGGER.info(
                        "Clearing all manual schedules for %s:%s",
                        ip_address,
                        port,
                    )
                    client = MarstekUDPClient(ip_address, port, timeout=10.0)
                    results = await client.clear_all_manual_schedules()
                    _LOGGER.info(
                        "Cleared schedules: %d/%d slots disabled",
                        results["success_count"],
                        results["total_slots"],
                    )
                except Exception as err:
                    _LOGGER.error("Failed to clear schedules: %s", err)
                    errors["base"] = "clear_failed"
            
            if not errors:
                # Create the config entry
                return self.async_create_entry(
                    title=f"Marstek Venus E ({ip_address})",
                    data={
                        CONF_IP_ADDRESS: ip_address,
                        CONF_PORT: port,
                        CONF_BLE_MAC: ble_mac,
                    },
                )
        
        schema = vol.Schema(
            {
                vol.Optional("clear_schedules", default=False): bool,
            }
        )
        
        return self.async_show_form(
            step_id="clear_schedules",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Import config from configuration.yaml.
        
        Args:
            import_data: Configuration data to import
            
        Returns:
            Config flow result
        """

        return await self.async_step_select_device(import_data)


class MarstekOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Marstek Venus E."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self.current_schedule: dict[str, Any] = {}
    
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - show menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "configure_manual_mode",
                "configure_update_interval",
                "configure_operating_modes",
                "configure_solar_surplus",
                "configure_storage_recharge",
            ],
        )

    async def async_step_configure_storage_recharge(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the local-time period for automatic storage recharge."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                user_input[CONF_STORAGE_RECHARGE_START]
                == user_input[CONF_STORAGE_RECHARGE_END]
            ):
                errors["base"] = "storage_recharge_times_must_differ"
            else:
                new_options = {**self._config_entry.options, **user_input}
                return self.async_create_entry(title="", data=new_options)

        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STORAGE_RECHARGE_START,
                    default=options.get(
                        CONF_STORAGE_RECHARGE_START,
                        DEFAULT_STORAGE_RECHARGE_START,
                    ),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_STORAGE_RECHARGE_END,
                    default=options.get(
                        CONF_STORAGE_RECHARGE_END,
                        DEFAULT_STORAGE_RECHARGE_END,
                    ),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_STORAGE_OBSERVATION_DAYS,
                    default=options.get(
                        CONF_STORAGE_OBSERVATION_DAYS,
                        STORAGE_OBSERVATION_DAYS,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        unit_of_measurement="d",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="configure_storage_recharge",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_configure_solar_surplus(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the solar source and surplus hysteresis."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                user_input[CONF_SOLAR_SURPLUS_ON_W]
                <= user_input[CONF_SOLAR_SURPLUS_OFF_W]
            ):
                errors["base"] = "solar_on_must_exceed_off"
            else:
                new_options = {**self._config_entry.options, **user_input}
                if not user_input.get(CONF_SOLAR_POWER_ENTITY):
                    new_options.pop(CONF_SOLAR_POWER_ENTITY, None)
                return self.async_create_entry(title="", data=new_options)

        options = self._config_entry.options
        schema_fields: dict[Any, Any] = {}
        solar_entity = options.get(CONF_SOLAR_POWER_ENTITY)
        entity_key = vol.Optional(CONF_SOLAR_POWER_ENTITY)
        if solar_entity:
            entity_key = vol.Optional(
                CONF_SOLAR_POWER_ENTITY, default=solar_entity
            )
        schema_fields[entity_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                device_class="power",
            )
        )
        for key, default, minimum, maximum, step, unit in (
            (
                CONF_SOLAR_SURPLUS_ON_W,
                options.get(
                    CONF_SOLAR_SURPLUS_ON_W, DEFAULT_SOLAR_SURPLUS_ON_W
                ),
                0,
                20000,
                100,
                "W",
            ),
            (
                CONF_SOLAR_SURPLUS_OFF_W,
                options.get(
                    CONF_SOLAR_SURPLUS_OFF_W, DEFAULT_SOLAR_SURPLUS_OFF_W
                ),
                0,
                20000,
                100,
                "W",
            ),
            (
                CONF_SOLAR_SURPLUS_ON_MINUTES,
                options.get(
                    CONF_SOLAR_SURPLUS_ON_MINUTES,
                    DEFAULT_SOLAR_SURPLUS_ON_MINUTES,
                ),
                1,
                30,
                1,
                "min",
            ),
            (
                CONF_SOLAR_SURPLUS_OFF_MINUTES,
                options.get(
                    CONF_SOLAR_SURPLUS_OFF_MINUTES,
                    DEFAULT_SOLAR_SURPLUS_OFF_MINUTES,
                ),
                1,
                60,
                1,
                "min",
            ),
        ):
            schema_fields[vol.Required(key, default=default)] = (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=minimum,
                        max=maximum,
                        step=step,
                        unit_of_measurement=unit,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            )

        return self.async_show_form(
            step_id="configure_solar_surplus",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_configure_operating_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which operating modes are offered by the entity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected_options = user_input.get(CONF_ENABLED_MODES, [])
            if not selected_options:
                errors["base"] = "select_at_least_one_mode"
            else:
                enabled_modes = [
                    MODE_OPTION_TO_MODE[option]
                    for option in selected_options
                ]
                new_options = {**self._config_entry.options}
                new_options[CONF_ENABLED_MODES] = enabled_modes
                return self.async_create_entry(title="", data=new_options)

        current_modes = self._config_entry.options.get(
            CONF_ENABLED_MODES, SELECTABLE_MODES
        )
        if "Passive" in current_modes:
            current_modes = [
                mode for mode in current_modes if mode != "Passive"
            ] + [MODE_STANDBY, MODE_MANUAL]
        current_mode_options = [
            mode.lower() for mode in current_modes if mode in SELECTABLE_MODES
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLED_MODES, default=current_mode_options
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(MODE_OPTION_TO_MODE),
                        translation_key="operating_mode_options",
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="configure_operating_modes",
            data_schema=schema,
            errors=errors,
        )
    
    async def async_step_configure_manual_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure manual mode schedules."""
        if user_input is not None:
            # Save the schedule configuration
            time_num = user_input.get("time_slot")
            
            # Get coordinator to send the configuration
            coordinator = self.hass.data[DOMAIN].get(self._config_entry.entry_id)
            if coordinator:
                try:
                    await coordinator.set_manual_schedule(
                        time_num=time_num,
                        start_time=user_input.get("start_time"),
                        end_time=user_input.get("end_time"),
                        week_set=week_set_from_days(
                            user_input.get("days", [])
                        ),
                        power=user_input.get("power"),
                        enable=user_input.get("enable", True),
                    )
                    return self.async_create_entry(title="", data={})
                except Exception as err:
                    _LOGGER.error("Error setting manual schedule: %s", err)
                    return self.async_abort(reason="schedule_failed")
        
        # Define the form schema
        schema = vol.Schema(
            {
                vol.Required("time_slot", default=0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=9,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required("start_time"): selector.TimeSelector(),
                vol.Required("end_time"): selector.TimeSelector(),
                vol.Required("days", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "monday",
                            "tuesday",
                            "wednesday",
                            "thursday",
                            "friday",
                            "saturday",
                            "sunday",
                        ],
                        translation_key="weekdays",
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("power", default=-500): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-2500,
                        max=2500,
                        step=100,
                        unit_of_measurement="W",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("enable", default=True): selector.BooleanSelector(),
            }
        )
        
        return self.async_show_form(
            step_id="configure_manual_mode",
            data_schema=schema,
        )
    
    async def async_step_configure_update_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the update interval."""
        if user_input is not None:
            fast_interval = user_input[CONF_FAST_SCAN_INTERVAL]
            mode_interval = user_input[CONF_MODE_SCAN_INTERVAL]
            
            # Update the options
            new_options = {**self._config_entry.options}
            new_options[CONF_FAST_SCAN_INTERVAL] = fast_interval
            new_options[CONF_MODE_SCAN_INTERVAL] = mode_interval
            
            # Get coordinator and update its interval
            coordinator = self.hass.data.get(DOMAIN, {}).get(
                self._config_entry.entry_id
            )
            if coordinator:
                from datetime import timedelta
                coordinator.update_interval = timedelta(seconds=fast_interval)
                coordinator._mode_update_interval = timedelta(seconds=mode_interval)
                _LOGGER.info(
                    "Update intervals changed: live=%d seconds, mode/CT=%d seconds",
                    fast_interval,
                    mode_interval,
                )
            
            return self.async_create_entry(title="", data=new_options)
        
        # Get current interval (in minutes, converting from seconds if stored that way)
        current_fast_interval = self._config_entry.options.get(
            CONF_FAST_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL,
        )
        current_mode_interval = self._config_entry.options.get(
            CONF_MODE_SCAN_INTERVAL,
            60,
        )
        
        # Define the form schema
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FAST_SCAN_INTERVAL,
                    default=current_fast_interval,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=300,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MODE_SCAN_INTERVAL,
                    default=current_mode_interval,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=10,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="configure_update_interval",
            data_schema=schema,
        )
