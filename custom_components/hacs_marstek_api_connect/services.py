"""Service handlers for the Marstek Venus E integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SELECTABLE_MODES
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CONF_CONFIG_ENTRY_ID = "config_entry_id"


def _translated_error(
    key: str, placeholders: dict[str, str] | None = None
) -> HomeAssistantError:
    """Build a localized Home Assistant service error."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


def _service_schema(fields: dict[Any, Any] | None = None) -> vol.Schema:
    """Build a service schema with explicit config-entry targeting."""
    return vol.Schema(
        {
            vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
            **(fields or {}),
        }
    )


SERVICE_SET_MODE_SCHEMA = _service_schema(
    {vol.Required("mode"): vol.In(SELECTABLE_MODES)}
)

SERVICE_SET_MANUAL_SCHEDULE_SCHEMA = _service_schema(
    {
        vol.Required("time_num"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=9)
        ),
        vol.Required("start_time"): cv.time,
        vol.Required("end_time"): cv.time,
        vol.Required("week_set"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=127)
        ),
        vol.Required("mode"): vol.In(
            ["charging", "discharging", "Charging", "Discharging"]
        ),
        vol.Required("power"): vol.All(
            vol.Coerce(int), vol.Range(min=100, max=2500)
        ),
        vol.Optional("enable", default=True): cv.boolean,
    }
)

SERVICE_CLEAR_ALL_SCHEDULES_SCHEMA = _service_schema()
SERVICE_SET_BLE_ADV_SCHEMA = _service_schema(
    {vol.Required("enable"): cv.boolean}
)
SERVICE_SET_LED_CTRL_SCHEMA = _service_schema(
    {vol.Required("enabled"): cv.boolean}
)


def _coordinators_for_call(
    hass: HomeAssistant, call: ServiceCall
) -> list[MarstekDataUpdateCoordinator]:
    """Return the explicitly selected coordinator or the only configured one."""
    coordinators = hass.data.get(DOMAIN, {})
    entry_id = call.data[CONF_CONFIG_ENTRY_ID]
    coordinator = coordinators.get(entry_id)
    if coordinator is None:
        raise _translated_error(
            "unknown_config_entry", {"entry_id": entry_id}
        )
    return [coordinator]


def _ensure_command_accepted(result: dict[str, Any]) -> None:
    """Raise a visible service error when the device rejects a command."""
    if result.get("set_result") is False:
        raise ValueError("Device rejected command")


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once for the domain."""
    if hass.services.has_service(DOMAIN, "set_mode"):
        return

    async def set_mode_handler(call: ServiceCall) -> None:
        mode = call.data["mode"]
        for coordinator in _coordinators_for_call(hass, call):
            try:
                await coordinator.async_select_operating_mode(mode)
            except Exception as err:
                if isinstance(err, HomeAssistantError):
                    raise
                raise _translated_error(
                    "mode_set_failed", {"mode": mode}
                ) from err
        _LOGGER.info("Persistent operating mode set to %s", mode)

    async def set_manual_schedule_handler(call: ServiceCall) -> None:
        start_time = call.data["start_time"].strftime("%H:%M")
        end_time = call.data["end_time"].strftime("%H:%M")
        power_magnitude = call.data["power"]
        power = (
            -power_magnitude
            if call.data["mode"].lower() == "charging"
            else power_magnitude
        )
        for coordinator in _coordinators_for_call(hass, call):
            try:
                await coordinator.set_manual_schedule(
                    time_num=call.data["time_num"],
                    start_time=start_time,
                    end_time=end_time,
                    week_set=call.data["week_set"],
                    power=power,
                    enable=call.data["enable"],
                )
            except Exception as err:
                raise _translated_error("schedule_set_failed") from err

    async def clear_all_schedules_handler(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            try:
                results = await coordinator.clear_all_manual_schedules()
            except Exception as err:
                raise _translated_error("schedules_clear_failed") from err
            if results["failed_slots"]:
                raise _translated_error(
                    "schedule_slots_failed",
                    {
                        "slots": ", ".join(
                            str(slot) for slot in results["failed_slots"]
                        )
                    },
                )
            _LOGGER.info(
                "Cleared %d manual schedule slots", results["success_count"]
            )

    async def set_ble_adv_handler(call: ServiceCall) -> None:
        enabled = call.data["enable"]
        for coordinator in _coordinators_for_call(hass, call):
            try:
                result = await coordinator.client.set_ble_adv(enabled)
                _ensure_command_accepted(result)
            except Exception as err:
                raise _translated_error("ble_set_failed") from err

    async def set_led_ctrl_handler(call: ServiceCall) -> None:
        enabled = call.data["enabled"]
        for coordinator in _coordinators_for_call(hass, call):
            try:
                await coordinator.async_set_led_state(enabled)
            except Exception as err:
                if isinstance(err, HomeAssistantError):
                    raise
                raise _translated_error("led_set_failed") from err

    hass.services.async_register(
        DOMAIN, "set_mode", set_mode_handler, schema=SERVICE_SET_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        "set_manual_schedule",
        set_manual_schedule_handler,
        schema=SERVICE_SET_MANUAL_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_all_schedules",
        clear_all_schedules_handler,
        schema=SERVICE_CLEAR_ALL_SCHEDULES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "set_ble_adv",
        set_ble_adv_handler,
        schema=SERVICE_SET_BLE_ADV_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "set_led_ctrl",
        set_led_ctrl_handler,
        schema=SERVICE_SET_LED_CTRL_SCHEMA,
    )
    _LOGGER.debug("Services registered for %s", DOMAIN)
