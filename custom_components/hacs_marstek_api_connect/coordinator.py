"""Data update coordinator for Marstek Venus E."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FAST_SCAN_INTERVAL,
    CONF_IP_ADDRESS,
    CONF_MODE_SCAN_INTERVAL,
    CONF_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MODE_AUTO,
    STORAGE_AUTO_START_SOC,
    STORAGE_CHARGE_POWER,
    STORAGE_CHARGE_START_SOC,
    STORAGE_TARGET_SOC,
)
from .udp_client import MarstekUDPClient

_LOGGER = logging.getLogger(__name__)


class MarstekDataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Marstek Venus E."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance
            entry: Configuration entry
        """
        # ES.GetStatus contains the live grid/battery power values and is polled
        # quickly. Slower endpoints are throttled separately below.
        scan_interval_seconds = entry.options.get(
            CONF_FAST_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        
        self.entry = entry
        self.client = MarstekUDPClient(
            ip_address=entry.data[CONF_IP_ADDRESS],
            port=entry.data.get(CONF_PORT, 30000),
        )
        self.data: dict[str, Any] = {}
        # Storage for manual API call results
        self.battery_data: dict[str, Any] = {}
        self.mode_data: dict[str, Any] = {}
        self.device_data: dict[str, Any] = {}
        self.wifi_data: dict[str, Any] = {}
        self.ble_data: dict[str, Any] = {}
        # Track last battery data update (every 60 minutes instead of 30 seconds)
        self._last_battery_update: datetime | None = None
        self._battery_update_interval = timedelta(minutes=60)
        self._last_mode_update: datetime | None = None
        self._mode_update_interval = timedelta(
            seconds=entry.options.get(CONF_MODE_SCAN_INTERVAL, 60)
        )
        self.storage_mode_enabled = False
        self._storage_phase: str | None = None
        self.led_state: bool | None = None
        self._storage = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.storage_mode"
        )
        self.automatic_storage_enabled = False
        self._automatic_controller_state = "observing"
        self._automatic_controller_ready = False
        self._low_soc_days = 0
        self._full_soc_days = 0
        self._tracking_day: date | None = None
        self._tracking_max_soc: float | None = None
        self._tracking_first_seen: datetime | None = None
        self._tracking_last_seen: datetime | None = None
        self._automatic_storage = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.automatic_storage"
        )

    async def async_load_storage_mode(self) -> None:
        """Restore whether the virtual storage mode was active."""
        stored = await self._storage.async_load()
        self.storage_mode_enabled = bool(
            stored and stored.get("enabled", False)
        )

    async def async_load_automatic_storage(self) -> None:
        """Restore the automatic winter controller and its counters."""
        stored = await self._automatic_storage.async_load() or {}
        self.automatic_storage_enabled = bool(stored.get("enabled", False))
        self._automatic_controller_state = stored.get("state", "observing")
        self._low_soc_days = int(stored.get("low_soc_days", 0))
        self._full_soc_days = int(stored.get("full_soc_days", 0))
        try:
            tracking_day = stored.get("tracking_day")
            self._tracking_day = date.fromisoformat(tracking_day) if tracking_day else None
            self._tracking_max_soc = stored.get("tracking_max_soc")
            first_seen = stored.get("tracking_first_seen")
            last_seen = stored.get("tracking_last_seen")
            self._tracking_first_seen = datetime.fromisoformat(first_seen) if first_seen else None
            self._tracking_last_seen = datetime.fromisoformat(last_seen) if last_seen else None
        except (TypeError, ValueError):
            self._reset_day_tracking()

    def _automatic_storage_data(self) -> dict[str, Any]:
        """Return serializable automatic-storage state."""
        return {
            "enabled": self.automatic_storage_enabled,
            "state": self._automatic_controller_state,
            "low_soc_days": self._low_soc_days,
            "full_soc_days": self._full_soc_days,
            "tracking_day": self._tracking_day.isoformat() if self._tracking_day else None,
            "tracking_max_soc": self._tracking_max_soc,
            "tracking_first_seen": self._tracking_first_seen.isoformat() if self._tracking_first_seen else None,
            "tracking_last_seen": self._tracking_last_seen.isoformat() if self._tracking_last_seen else None,
        }

    def _schedule_automatic_storage_save(self) -> None:
        """Persist controller data without writing on every 10-second sample."""
        self._automatic_storage.async_delay_save(
            self._automatic_storage_data, 300
        )

    def _reset_day_tracking(self, now: datetime | None = None) -> None:
        """Start or clear daily SOC tracking."""
        self._tracking_day = now.date() if now else None
        self._tracking_max_soc = None
        self._tracking_first_seen = now
        self._tracking_last_seen = now

    @property
    def automatic_storage_status(self) -> str:
        """Return the status of the automatic winter controller."""
        if not self.automatic_storage_enabled:
            return "Deaktiviert"
        if self._automatic_controller_state == "observing":
            return f"Automatik - Beobachtung ({self._low_soc_days}/5 Tage)"

        today_full = bool(
            self._tracking_max_soc is not None
            and self._tracking_max_soc >= 99
        )
        if today_full:
            count = min(2, self._full_soc_days + 1)
            return f"Lagerung - Vollladung erkannt ({count}/2 Tage)"
        return {
            "charging": "Lagerung - Laden",
            "holding": "Lagerung - Halten",
            "auto": "Lagerung - Entladen",
        }.get(self._storage_phase, "Lagerung - Halten")

    @property
    def operation_status(self) -> str | None:
        """Return a user-facing charge/discharge/storage status."""
        if self.storage_mode_enabled:
            return {
                "charging": "Lagerung - Laden",
                "holding": "Lagerung - Halten",
                "auto": "Lagerung - Entladen",
            }.get(self._storage_phase)

        battery_power = self.data.get("bat_power") if self.data else None
        invert_power = False
        if battery_power is None and self.data:
            # Venus E 3.0 firmware commonly omits bat_power. Its ongrid_power
            # reports the inverter flow with the opposite sign: negative while
            # charging and positive while discharging.
            battery_power = self.data.get("ongrid_power")
            invert_power = True
        if battery_power is None:
            return None
        try:
            power = float(battery_power)
        except (TypeError, ValueError):
            return None

        if invert_power:
            power = -power

        if power > 10:
            return "Laden"
        if power < -10:
            return "Entladen"
        return "Standby"

    @property
    def battery_power(self) -> float | None:
        """Return normalized battery power (positive charging)."""
        value = self.data.get("bat_power") if self.data else None
        if value is None and self.data:
            value = self.data.get("ongrid_power")
            if value is not None:
                try:
                    return -float(value)
                except (TypeError, ValueError):
                    return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def battery_available_capacity(self) -> float | None:
        """Return remaining charge capacity in Wh."""
        soc = self.data.get("bat_soc") if self.data else None
        rated = self.battery_data.get("rated_capacity")
        try:
            return round((100 - float(soc)) * float(rated) / 100, 1)
        except (TypeError, ValueError):
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device.
        
        Returns:
            Dictionary containing device data
            
        Raises:
            UpdateFailed: If data fetch fails
        """
        try:
            # Get energy system status - this includes all live power metrics.
            data = await self.client.get_energy_system_status()

            if self._automatic_controller_ready:
                await self._async_update_automatic_storage(data.get("bat_soc"))
            if self.storage_mode_enabled:
                await self._async_update_storage_mode(data.get("bat_soc"))
            
            # Get battery details only at the slower battery interval.
            now = datetime.now()
            if self._last_battery_update is None or (now - self._last_battery_update) >= self._battery_update_interval:
                try:
                    self.battery_data = await self.client.get_battery_status()
                    for field in ("bat_voltage", "bat_current"):
                        value = self.battery_data.get(field)
                        if value is not None:
                            try:
                                self.battery_data[field] = round(
                                    float(value) / 100, 2
                                )
                            except (TypeError, ValueError):
                                _LOGGER.debug(
                                    "Invalid %s value received: %r", field, value
                                )
                    try:
                        self.device_data = await self.client.get_device_info()
                        self.device_data.setdefault(
                            "ip", self.entry.data.get(CONF_IP_ADDRESS)
                        )
                    except Exception as device_err:
                        _LOGGER.debug("Failed to get device info: %s", device_err)
                    try:
                        self.wifi_data = await self.client.get_wifi_status()
                    except Exception as wifi_err:
                        _LOGGER.debug("Failed to get WiFi status: %s", wifi_err)
                    try:
                        self.ble_data = await self.client.get_ble_status()
                    except Exception as ble_err:
                        _LOGGER.debug("Failed to get Bluetooth status: %s", ble_err)
                    self._last_battery_update = now
                    _LOGGER.debug("Battery data updated: %s", self.battery_data)
                except Exception as battery_err:
                    _LOGGER.debug("Failed to get battery data: %s", battery_err)
                    # Battery data is optional, don't fail the entire update
            
            # ES.GetMode and EM.GetStatus change less frequently than live power
            # values and are intentionally limited to once per minute.
            update_mode_data = (
                self._last_mode_update is None
                or (now - self._last_mode_update) >= self._mode_update_interval
            )
            if update_mode_data:
                try:
                    self.mode_data = await self.client.get_energy_system_mode()
                    self._last_mode_update = now
                # Add mode to main data for easy access
                    if "mode" in self.mode_data:
                        data["mode"] = self.mode_data["mode"]
                
                # Add CT meter data to mode_data (ES.GetMode includes it)
                # Apply scaling for energy values (*0.1 as per API documentation)
                    if "input_energy" in self.mode_data:
                        self.mode_data["input_energy"] = round(self.mode_data.get("input_energy", 0) * 0.1, 1)
                    if "output_energy" in self.mode_data:
                        self.mode_data["output_energy"] = round(self.mode_data.get("output_energy", 0) * 0.1, 1)
                except Exception as mode_err:
                    _LOGGER.warning("Failed to get mode data: %s", mode_err)
                    # Don't fail the entire update if mode fetch fails
            
            # Also try to get EM status for additional meter data
            if update_mode_data:
                try:
                    em_data = await self.client.get_energy_meter_status()
                # Merge EM data into mode_data if available
                    if em_data:
                    # Apply scaling for EM energy values too
                        if "input_energy" in em_data:
                            em_data["input_energy"] = round(em_data.get("input_energy", 0) * 0.1, 1)
                        if "output_energy" in em_data:
                            em_data["output_energy"] = round(em_data.get("output_energy", 0) * 0.1, 1)
                    
                    # Merge with mode_data
                    # For CT power data (a_power, b_power, c_power, total_power), prefer EM.GetStatus
                    # as ES.GetMode may return zeros if CT is not in active mode
                        if self.mode_data:
                            ct_fields = {
                                "ct_state",
                                "a_power",
                                "b_power",
                                "c_power",
                                "total_power",
                            }
                            for k, v in em_data.items():
                            # Prefer EM data for CT fields, otherwise prefer mode_data
                                if k not in self.mode_data or (k in ct_fields and self.mode_data.get(k) == 0):
                                    self.mode_data[k] = v
                        else:
                            self.mode_data = em_data
                except Exception as em_err:
                    _LOGGER.debug("Failed to get EM status (expected if not available): %s", em_err)
                    # EM.GetStatus is optional and may not be available on all devices

            # Preserve the cached mode in the fast coordinator data between the
            # slower ES.GetMode updates.
            if "mode" in self.mode_data:
                data["mode"] = self.mode_data["mode"]
            
            return data
        except Exception as err:
            _LOGGER.error("Failed to get device data: %s", err)
            raise UpdateFailed(f"Failed to update data: {err}")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        await super().async_shutdown()

    async def set_mode(self, mode: str) -> None:
        """Set operating mode.
        
        Args:
            mode: Operating mode
        """
        result = await self.client.set_mode(mode)
        if result.get("set_result") is False:
            raise ValueError(f"Device rejected operating mode {mode}")

        # Reflect the requested value immediately. Venus E firmware may need a
        # few seconds before ES.GetMode reports a newly selected mode; an
        # immediate coordinator refresh would otherwise restore the old value
        # in the select entity and make it appear as if the command failed.
        self.mode_data["mode"] = mode
        if self.data is not None:
            self.data["mode"] = mode
        self.async_update_listeners()

        await asyncio.sleep(3)
        confirmed_mode_data = await self.client.get_energy_system_mode()
        confirmed_mode = confirmed_mode_data.get("mode")
        if confirmed_mode != mode:
            _LOGGER.warning(
                "Device did not confirm operating mode %s (reported: %s)",
                mode,
                confirmed_mode,
            )
            # Keep the actual device state visible and report the failed write
            # to Home Assistant instead of silently jumping back.
            if confirmed_mode is not None:
                self.mode_data.update(confirmed_mode_data)
                self.data["mode"] = confirmed_mode
                self.async_update_listeners()
            raise ValueError(
                f"Device did not confirm operating mode {mode}; reported {confirmed_mode}"
            )

        self.mode_data.update(confirmed_mode_data)
        self.data["mode"] = mode
        self.async_update_listeners()

    async def async_enable_storage_mode(self) -> None:
        """Enable storage/winter mode and evaluate its first action."""
        self.storage_mode_enabled = True
        self._storage_phase = None
        await self._storage.async_save({"enabled": True})
        soc = self.data.get("bat_soc") if self.data else None
        await self._async_update_storage_mode(soc)
        self.async_update_listeners()

    async def async_disable_storage_mode(self) -> None:
        """Disable storage/winter mode."""
        self.storage_mode_enabled = False
        self._storage_phase = None
        await self._storage.async_save({"enabled": False})

    async def async_start_automatic_storage_controller(self) -> None:
        """Start automatic evaluation after initial Auto mode was requested."""
        self._automatic_controller_ready = True
        if not self.automatic_storage_enabled:
            return
        self.storage_mode_enabled = self._automatic_controller_state == "storage"
        soc = self.data.get("bat_soc") if self.data else None
        await self._async_update_automatic_storage(soc)
        if self.storage_mode_enabled:
            await self._async_update_storage_mode(soc)
        self.async_update_listeners()

    async def async_set_automatic_storage(
        self, enabled: bool, *, set_auto: bool = True
    ) -> None:
        """Enable or disable automatic winter operation."""
        self.automatic_storage_enabled = enabled
        self._automatic_controller_state = "observing"
        self._low_soc_days = 0
        self._full_soc_days = 0
        self.storage_mode_enabled = False
        self._storage_phase = None
        self._reset_day_tracking(dt_util.now() if enabled else None)
        await self._storage.async_save({"enabled": False})
        await self._automatic_storage.async_save(self._automatic_storage_data())
        if set_auto:
            await self.set_mode(MODE_AUTO)
        self.async_update_listeners()

    async def _async_update_automatic_storage(self, soc: Any) -> None:
        """Update daily counters and switch between Auto and Storage."""
        if not self.automatic_storage_enabled or soc is None:
            return
        try:
            soc_value = float(soc)
        except (TypeError, ValueError):
            return

        now = dt_util.now()
        if self._tracking_day is None:
            self._reset_day_tracking(now)
        elif now.date() != self._tracking_day:
            await self._async_finalize_tracking_day(now.date())
            self._reset_day_tracking(now)

        self._tracking_last_seen = now
        if self._tracking_max_soc is None or soc_value > self._tracking_max_soc:
            self._tracking_max_soc = soc_value

        # The second consecutive full-charge day is complete as soon as the
        # threshold is reached; there is no reason to wait until midnight.
        if (
            self._automatic_controller_state == "storage"
            and self._full_soc_days >= 1
            and self._tracking_max_soc >= 99
        ):
            await self._async_exit_automatic_storage()
            return
        self._schedule_automatic_storage_save()

    async def _async_exit_automatic_storage(self) -> None:
        """Return the automatic controller to Auto observation."""
        self._automatic_controller_state = "observing"
        self.storage_mode_enabled = False
        self._storage_phase = None
        self._low_soc_days = 0
        self._full_soc_days = 0
        await self._storage.async_save({"enabled": False})
        await self.set_mode(MODE_AUTO)
        await self._automatic_storage.async_save(self._automatic_storage_data())

    async def _async_finalize_tracking_day(self, new_day: date) -> None:
        """Evaluate a completed, sufficiently observed local calendar day."""
        if (
            self._tracking_day is None
            or self._tracking_first_seen is None
            or self._tracking_last_seen is None
            or self._tracking_max_soc is None
        ):
            return

        consecutive_day = new_day == self._tracking_day + timedelta(days=1)
        observed_for = self._tracking_last_seen - self._tracking_first_seen
        valid_day = consecutive_day and observed_for >= timedelta(hours=20)
        if not valid_day:
            self._low_soc_days = 0
            self._full_soc_days = 0
            return

        if self._automatic_controller_state == "observing":
            if self._tracking_max_soc < 50:
                self._low_soc_days += 1
            else:
                self._low_soc_days = 0
            if self._low_soc_days >= 5:
                self._automatic_controller_state = "storage"
                self.storage_mode_enabled = True
                self._storage_phase = None
                self._full_soc_days = 0
                await self._storage.async_save({"enabled": True})
        else:
            if self._tracking_max_soc >= 99:
                self._full_soc_days += 1
            else:
                self._full_soc_days = 0
            if self._full_soc_days >= 2:
                await self._async_exit_automatic_storage()

        await self._automatic_storage.async_save(self._automatic_storage_data())

    async def _async_update_storage_mode(self, soc: Any) -> None:
        """Keep the battery near 50 percent using a hysteresis state machine."""
        if soc is None:
            return

        try:
            soc_value = float(soc)
        except (TypeError, ValueError):
            _LOGGER.warning("Storage mode received invalid SOC value: %s", soc)
            return

        next_phase = self._storage_phase
        if self._storage_phase == "charging":
            if soc_value >= STORAGE_TARGET_SOC:
                next_phase = "holding"
        elif self._storage_phase == "auto":
            if soc_value <= STORAGE_TARGET_SOC:
                next_phase = "holding"
        elif soc_value <= STORAGE_CHARGE_START_SOC:
            next_phase = "charging"
        elif soc_value >= STORAGE_AUTO_START_SOC:
            next_phase = "auto"
        else:
            next_phase = "holding"

        if next_phase == self._storage_phase:
            return

        if next_phase == "charging":
            result = await self.client.set_passive_mode(
                power=STORAGE_CHARGE_POWER, cd_time=0
            )
        elif next_phase == "auto":
            result = await self.client.set_mode(MODE_AUTO)
        else:
            result = await self.client.set_passive_mode(power=0, cd_time=0)

        if result.get("set_result") is False:
            raise ValueError(f"Device rejected storage phase {next_phase}")

        _LOGGER.info(
            "Storage mode changed phase from %s to %s at %.1f%% SOC",
            self._storage_phase,
            next_phase,
            soc_value,
        )
        self._storage_phase = next_phase
        self.async_update_listeners()

    async def set_manual_schedule(
        self,
        time_num: int,
        start_time: str,
        end_time: str,
        week_set: int,
        power: int,
        enable: bool = True,
    ) -> None:
        """Set manual schedule.
        
        Args:
            time_num: Time slot number
            start_time: Start time
            end_time: End time
            week_set: Week bitmask
            power: Power in watts
            enable: Enable schedule
        """
        await self.client.set_manual_schedule(
            time_num=time_num,
            start_time=start_time,
            end_time=end_time,
            week_set=week_set,
            power=power,
            enable=enable,
        )
        await self.async_request_refresh()

    async def set_passive_mode(self, power: int, cd_time: int = 0) -> None:
        """Set passive mode.
        
        Args:
            power: Target power
            cd_time: Countdown time
        """
        await self.client.set_passive_mode(power=power, cd_time=cd_time)
        await self.async_request_refresh()

    async def clear_all_manual_schedules(self) -> dict[str, Any]:
        """Clear all manual schedules.
        
        Returns:
            Dictionary with operation results
        """
        results = await self.client.clear_all_manual_schedules()
        await self.async_request_refresh()
        return results

    async def refresh_battery_data(self) -> dict[str, Any]:
        """Manually refresh battery data.
        
        Returns:
            Battery data dictionary
        """
        self.battery_data = await self.client.get_battery_status()
        self.async_update_listeners()
        return self.battery_data

    async def refresh_mode_data(self) -> dict[str, Any]:
        """Manually refresh mode and CT data.
        
        Returns:
            Mode data dictionary
        """
        self.mode_data = await self.client.get_energy_system_mode()
        self.async_update_listeners()
        return self.mode_data
