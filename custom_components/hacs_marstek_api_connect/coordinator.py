"""Data update coordinator for Marstek Venus E."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FAST_SCAN_INTERVAL,
    CONF_IP_ADDRESS,
    CONF_MODE_SCAN_INTERVAL,
    CONF_PORT,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_START_SOURCE,
    CONF_STORAGE_RECHARGE_START_SOC,
    CONF_STORAGE_RECHARGE_STOP_SOC,
    CONF_CT_EXPORT_START_W,
    CONF_CT_START_MINUTES,
    DEFAULT_CT_EXPORT_START_W,
    DEFAULT_CT_START_MINUTES,
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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MODE_AUTO,
    MODE_PASSIVE,
    MODE_MANUAL,
    MODE_SCHEDULE,
    MODE_STANDBY,
    MODE_STORAGE,
    SELECTABLE_MODES,
    STORAGE_AUTO_START_SOC,
    STORAGE_CHARGE_POWER,
    STORAGE_CHARGE_START_SOC,
    STORAGE_EXIT_FULL_CHARGE_DAYS,
    STORAGE_OBSERVATION_DAYS,
    STORAGE_PHASE_STATES,
    STORAGE_TARGET_SOC,
    BATTERY_POWER_THRESHOLD_W,
    BATTERY_POWER_AVERAGE_SECONDS,
    MODE_ENFORCEMENT_RECOVERY_SECONDS,
    MODE_ENFORCEMENT_RETRY_SECONDS,
    PASSIVE_CD_TIME_SECONDS,
    PASSIVE_KEEPALIVE_SECONDS,
    SOLAR_CHARGING_EXIT_W,
    SOLAR_CHARGE_CONFIRMATION_SECONDS,
    SOLAR_CHECK_COOLDOWN_SECONDS,
    SOLAR_CHECK_MAX_SECONDS,
    SOLAR_DISCHARGE_ABORT_SECONDS,
    SOLAR_DISCHARGE_THRESHOLD_W,
    STORAGE_FULL_CHARGE_ARM_SOC,
    STORAGE_FULL_CHARGE_SOC,
    STORAGE_VALID_DAY_HOURS,
)
from .logic import (
    available_battery_capacity,
    append_sample,
    automatic_storage_next_phase,
    expected_physical_mode,
    is_new_dropout,
    manual_storage_next_phase,
    mode_feedback_confirmed,
    normalize_ipv4,
    normalized_battery_power,
    operation_status_from_power,
    storage_command_required,
    storage_phase_command,
    storage_phase_changes_command,
    time_in_window,
    time_weighted_average,
)
from .udp_client import MarstekUDPClient
from .logic import CTExportStart

_LOGGER = logging.getLogger(__name__)


def _configured_time(value: Any, fallback: str) -> time:
    """Parse a stored time selector value and safely fall back."""
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return time.fromisoformat(fallback)


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
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
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
        self._tracking_min_soc: float | None = None
        self._tracking_had_solar_charge = False
        self._tracking_full_charge_event = False
        self._tracking_first_seen: datetime | None = None
        self._tracking_last_seen: datetime | None = None
        self._automatic_storage = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.automatic_storage"
        )
        self.desired_operating_mode = MODE_AUTO
        self._mode_enforcement_ready = False
        self._mode_enforcement_failures = 0
        self._mode_enforcement_error = False
        self._mode_enforcement_next_attempt: datetime | None = None
        self._last_mode_enforcement_check: datetime | None = None
        self._last_mode_feedback_at: datetime | None = None
        self._mode_confirmation_required_after: datetime | None = None
        self._pending_storage_phase: str | None = None
        self._mode_enforcement_interval = timedelta(minutes=2)
        self._desired_mode_store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.desired_operating_mode"
        )
        self.manual_power = 0
        self._standby_zero_samples = 0
        self._manual_power_store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.manual_power"
        )
        self._passive_keepalive_due: datetime | None = None
        self._last_passive_renewal: datetime | None = None
        self._last_successful_update: datetime | None = None
        self._mode_dropouts: deque[tuple[datetime, str]] = deque(maxlen=100)
        self._active_mode_dropout: str | None = None
        self._solar_sensor_problem: str | None = None
        self._last_invalid_tracking_day: tuple[str, str] | None = None
        self._diagnostics_store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.diagnostics"
        )
        self.solar_power_entity = entry.options.get(CONF_SOLAR_POWER_ENTITY)
        self.solar_start_source = entry.options.get(CONF_SOLAR_START_SOURCE, "solar")
        self.storage_recharge_start_soc = float(entry.options.get(
            CONF_STORAGE_RECHARGE_START_SOC, STORAGE_CHARGE_START_SOC))
        self.storage_recharge_stop_soc = float(entry.options.get(
            CONF_STORAGE_RECHARGE_STOP_SOC, STORAGE_TARGET_SOC))
        self.ct_export_start_w = float(entry.options.get(
            CONF_CT_EXPORT_START_W, DEFAULT_CT_EXPORT_START_W))
        self.ct_start_minutes = int(entry.options.get(
            CONF_CT_START_MINUTES, DEFAULT_CT_START_MINUTES))
        self._ct_export_start = CTExportStart()
        self.solar_surplus_on_w = float(
            entry.options.get(
                CONF_SOLAR_SURPLUS_ON_W, DEFAULT_SOLAR_SURPLUS_ON_W
            )
        )
        self.solar_surplus_off_w = float(
            entry.options.get(
                CONF_SOLAR_SURPLUS_OFF_W, DEFAULT_SOLAR_SURPLUS_OFF_W
            )
        )
        self.solar_surplus_on_minutes = int(
            entry.options.get(
                CONF_SOLAR_SURPLUS_ON_MINUTES,
                DEFAULT_SOLAR_SURPLUS_ON_MINUTES,
            )
        )
        self.solar_surplus_off_minutes = int(
            entry.options.get(
                CONF_SOLAR_SURPLUS_OFF_MINUTES,
                DEFAULT_SOLAR_SURPLUS_OFF_MINUTES,
            )
        )
        self.storage_recharge_start = _configured_time(
            entry.options.get(
                CONF_STORAGE_RECHARGE_START,
                DEFAULT_STORAGE_RECHARGE_START,
            ),
            DEFAULT_STORAGE_RECHARGE_START,
        )
        self.storage_recharge_end = _configured_time(
            entry.options.get(
                CONF_STORAGE_RECHARGE_END,
                DEFAULT_STORAGE_RECHARGE_END,
            ),
            DEFAULT_STORAGE_RECHARGE_END,
        )
        self.storage_observation_days = max(
            1,
            min(
                30,
                int(
                    entry.options.get(
                        CONF_STORAGE_OBSERVATION_DAYS,
                        STORAGE_OBSERVATION_DAYS,
                    )
                ),
            ),
        )
        self.solar_power: float | None = None
        self.solar_surplus = False
        self._solar_samples: deque[tuple[datetime, float]] = deque()
        self._battery_power_samples: deque[tuple[datetime, float]] = deque()
        self._solar_check_started: datetime | None = None
        self._solar_discharge_started: datetime | None = None
        self._solar_check_cooldown_until: datetime | None = None
        self._storage_command_due: datetime | None = None

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
        stored_state = stored.get("state", "observing")
        self._automatic_controller_state = (
            stored_state
            if stored_state in ("observing", "storage")
            else "observing"
        )
        stored_phase = stored.get("storage_phase")
        self._storage_phase = (
            "holding"
            if stored_phase == "solar_check"
            else stored_phase
            if isinstance(stored_phase, str)
            and stored_phase in STORAGE_PHASE_STATES
            else None
        )
        try:
            self._low_soc_days = max(
                0,
                min(
                    self.storage_observation_days,
                    int(stored.get("low_soc_days", 0)),
                ),
            )
            self._full_soc_days = max(
                0,
                min(
                    STORAGE_EXIT_FULL_CHARGE_DAYS,
                    int(stored.get("full_soc_days", 0)),
                ),
            )
            tracking_day = stored.get("tracking_day")
            self._tracking_day = (
                date.fromisoformat(tracking_day) if tracking_day else None
            )
            tracking_max_soc = stored.get("tracking_max_soc")
            tracking_min_soc = stored.get("tracking_min_soc")
            self._tracking_max_soc = (
                float(tracking_max_soc)
                if tracking_max_soc is not None
                else None
            )
            self._tracking_min_soc = (
                float(tracking_min_soc)
                if tracking_min_soc is not None
                else None
            )
            self._tracking_had_solar_charge = bool(
                stored.get("tracking_had_solar_charge", False)
            )
            self._tracking_full_charge_event = bool(
                stored.get("tracking_full_charge_event", False)
            )
            first_seen = stored.get("tracking_first_seen")
            last_seen = stored.get("tracking_last_seen")
            self._tracking_first_seen = (
                datetime.fromisoformat(first_seen) if first_seen else None
            )
            self._tracking_last_seen = (
                datetime.fromisoformat(last_seen) if last_seen else None
            )
            cooldown_until = stored.get("solar_check_cooldown_until")
            self._solar_check_cooldown_until = (
                datetime.fromisoformat(cooldown_until)
                if cooldown_until
                else None
            )
            if (
                self._tracking_first_seen is not None
                and self._tracking_last_seen is not None
                and self._tracking_last_seen < self._tracking_first_seen
            ):
                raise ValueError("Invalid automatic-storage observation range")
        except (TypeError, ValueError, OverflowError):
            self._low_soc_days = 0
            self._full_soc_days = 0
            self._reset_day_tracking()

        if not self.automatic_storage_enabled:
            self._automatic_controller_state = "observing"
            self._storage_phase = None
            self._low_soc_days = 0
            self._full_soc_days = 0
            self._solar_check_cooldown_until = None
            self._reset_day_tracking()
        elif self._automatic_controller_state == "observing":
            self._storage_phase = None
            self._full_soc_days = 0

    async def async_load_desired_operating_mode(self) -> None:
        """Restore the persistent operating-mode setpoint."""
        stored = await self._desired_mode_store.async_load() or {}
        mode = stored.get("mode", MODE_AUTO)
        if mode == MODE_PASSIVE:
            mode = MODE_STANDBY
        self.desired_operating_mode = (
            mode if mode in (*SELECTABLE_MODES,) else MODE_AUTO
        )
        power_data = await self._manual_power_store.async_load() or {}
        try:
            power = int(power_data.get("power", 0))
        except (TypeError, ValueError):
            power = 0
        self.manual_power = max(-2400, min(2400, power))

    async def async_load_diagnostics(self) -> None:
        """Restore mode-deviation events recorded during the last 24 hours."""
        stored = await self._diagnostics_store.async_load() or {}
        cutoff = datetime.now() - timedelta(hours=24)
        restored: list[tuple[datetime, str]] = []
        for item in stored.get("mode_dropouts", []):
            try:
                timestamp = datetime.fromisoformat(item["timestamp"])
                reason = str(item["reason"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp >= cutoff:
                restored.append((timestamp, reason))
        self._mode_dropouts.extend(restored[-100:])

    def _diagnostics_data(self) -> dict[str, Any]:
        """Return persistent diagnostic history."""
        return {
            "mode_dropouts": [
                {"timestamp": timestamp.isoformat(), "reason": reason}
                for timestamp, reason in self._mode_dropouts_last_24h(
                    datetime.now()
                )
            ]
        }

    def _reset_mode_enforcement(self) -> None:
        """Grant a controller change a fresh set of restore attempts."""
        self._mode_enforcement_failures = 0
        self._mode_enforcement_error = False
        self._mode_enforcement_next_attempt = None
        self._mode_confirmation_required_after = None
        self._pending_storage_phase = None
        self._active_mode_dropout = None

    def _schedule_mode_enforcement_retry(self, now: datetime) -> None:
        """Apply the shared retry policy after a failed mode attempt."""
        if self._mode_enforcement_failures >= 5:
            self._mode_enforcement_error = True
            delay = MODE_ENFORCEMENT_RECOVERY_SECONDS
        else:
            delay = MODE_ENFORCEMENT_RETRY_SECONDS
        self._mode_enforcement_next_attempt = now + timedelta(seconds=delay)

    async def async_set_desired_operating_mode(self, mode: str) -> None:
        """Persist a new operating-mode setpoint and reset enforcement."""
        if mode not in SELECTABLE_MODES:
            raise ValueError(f"Unsupported desired operating mode: {mode}")
        self.desired_operating_mode = mode
        self._reset_mode_enforcement()
        self._standby_zero_samples = 0
        await self._desired_mode_store.async_save({"mode": mode})
        self.async_update_listeners()

    async def async_select_operating_mode(self, mode: str) -> None:
        """Persist and apply a user-facing operating-mode selection."""
        await self.async_set_desired_operating_mode(mode)
        if self.automatic_storage_enabled:
            await self.async_set_automatic_storage(False, set_auto=False)
        if mode == MODE_STORAGE:
            await self.async_enable_storage_mode()
            return
        await self.async_disable_storage_mode()
        await self.async_apply_desired_operating_mode()

    async def async_set_manual_power(self, power: int) -> None:
        """Persist the manual power target and apply it while Manual is active."""
        if power < -2400 or power > 2400:
            raise ValueError("Manual power must be between -2400 and 2400 W")
        self.manual_power = int(power)
        await self._manual_power_store.async_save({"power": self.manual_power})
        self._reset_mode_enforcement()
        if (
            self.desired_operating_mode == MODE_MANUAL
            and not self.automatic_storage_enabled
            and not self.storage_mode_enabled
        ):
            await self.async_apply_desired_operating_mode()
        self.async_update_listeners()

    async def async_apply_desired_operating_mode(self) -> None:
        """Apply the persistent UI mode to the physical device."""
        if self.desired_operating_mode == MODE_STANDBY:
            result = await self.client.set_passive_mode(
                power=0, cd_time=PASSIVE_CD_TIME_SECONDS
            )
            physical_mode = MODE_PASSIVE
        elif self.desired_operating_mode == MODE_MANUAL:
            result = await self.client.set_passive_mode(
                power=self.manual_power, cd_time=PASSIVE_CD_TIME_SECONDS
            )
            physical_mode = MODE_PASSIVE
        elif self.desired_operating_mode == MODE_SCHEDULE:
            self._passive_keepalive_due = None
            await self.set_mode(MODE_MANUAL)
            return
        else:
            self._passive_keepalive_due = None
            await self.set_mode(self.desired_operating_mode)
            return

        if result.get("set_result") is False:
            raise ValueError(
                f"Device rejected {self.desired_operating_mode} mode"
            )

        # Do not treat the accepted UDP command as proof that the device kept
        # the mode. Confirm the physical Passive mode through ES.GetMode.
        confirmed_mode_data: dict[str, Any] = {}
        confirmed_mode = None
        for _attempt in range(5):
            await asyncio.sleep(2)
            confirmed_mode_data = await self.client.get_energy_system_mode()
            confirmed_mode = confirmed_mode_data.get("mode")
            if confirmed_mode == physical_mode:
                break
        if confirmed_mode != physical_mode:
            if confirmed_mode_data:
                self.mode_data.update(confirmed_mode_data)
                if self.data is not None and confirmed_mode is not None:
                    self.data["mode"] = confirmed_mode
                self.async_update_listeners()
            raise ValueError(
                f"Device did not confirm {self.desired_operating_mode} mode "
                f"(reported: {confirmed_mode})"
            )

        self._passive_keepalive_due = datetime.now() + timedelta(
            seconds=PASSIVE_KEEPALIVE_SECONDS
        )
        self._last_passive_renewal = datetime.now()
        self.mode_data.update(confirmed_mode_data)
        self.mode_data["mode"] = physical_mode
        if self.data is not None:
            self.data["mode"] = physical_mode
        self.async_update_listeners()

    def async_start_mode_enforcement(self) -> None:
        """Enable operating-mode supervision after startup setup."""
        self._mode_enforcement_ready = True

    def _automatic_storage_data(self) -> dict[str, Any]:
        """Return serializable automatic-storage state."""
        return {
            "enabled": self.automatic_storage_enabled,
            "state": self._automatic_controller_state,
            "storage_phase": self._storage_phase,
            "low_soc_days": self._low_soc_days,
            "full_soc_days": self._full_soc_days,
            "tracking_day": (
                self._tracking_day.isoformat() if self._tracking_day else None
            ),
            "tracking_max_soc": self._tracking_max_soc,
            "tracking_min_soc": self._tracking_min_soc,
            "tracking_had_solar_charge": self._tracking_had_solar_charge,
            "tracking_full_charge_event": self._tracking_full_charge_event,
            "tracking_first_seen": (
                self._tracking_first_seen.isoformat()
                if self._tracking_first_seen
                else None
            ),
            "tracking_last_seen": (
                self._tracking_last_seen.isoformat()
                if self._tracking_last_seen
                else None
            ),
            "solar_check_cooldown_until": (
                self._solar_check_cooldown_until.isoformat()
                if self._solar_check_cooldown_until
                else None
            ),
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
        self._tracking_min_soc = None
        self._tracking_had_solar_charge = False
        self._tracking_full_charge_event = False
        self._tracking_first_seen = now
        self._tracking_last_seen = now

    @property
    def automatic_storage_status(self) -> str:
        """Return the translated state of the automatic winter controller."""
        if not self.automatic_storage_enabled:
            return "disabled"
        if self._automatic_controller_state == "observing":
            return "observing"
        if self._tracking_full_charge_event:
            return "full_charge_detected"
        return STORAGE_PHASE_STATES.get(self._storage_phase, "storage_holding")

    @property
    def storage_status_attributes(self) -> dict[str, Any]:
        """Return the day counters behind the automatic winter state."""
        full_soc_days = self._full_soc_days
        if self._tracking_full_charge_event:
            full_soc_days = min(
                STORAGE_EXIT_FULL_CHARGE_DAYS, self._full_soc_days + 1
            )
        return {
            "storage_phase": self._storage_phase,
            "low_soc_days": self._low_soc_days,
            "low_soc_days_required": self.storage_observation_days,
            "full_soc_days": full_soc_days,
            "full_soc_days_required": STORAGE_EXIT_FULL_CHARGE_DAYS,
            "recharge_start": self.storage_recharge_start.isoformat(),
            "recharge_start_soc": self.storage_recharge_start_soc,
            "recharge_stop_soc": self.storage_recharge_stop_soc,
            "recharge_end": self.storage_recharge_end.isoformat(),
            "recharge_window_active": time_in_window(
                dt_util.now().time(),
                self.storage_recharge_start,
                self.storage_recharge_end,
            ),
        }

    @property
    def operation_status(self) -> str | None:
        """Return a user-facing charge/discharge/storage state."""
        storage_state = (
            STORAGE_PHASE_STATES.get(self._storage_phase)
            if self.storage_mode_enabled
            else None
        )
        return operation_status_from_power(
            self.battery_power,
            mode_error=self._mode_enforcement_error,
            storage_state=storage_state,
        )

    @property
    def battery_power(self) -> float | None:
        """Return normalized battery power (positive charging)."""
        return normalized_battery_power(self.data)

    @property
    def battery_available_capacity(self) -> float | None:
        """Return remaining charge capacity in Wh."""
        soc = self.data.get("bat_soc") if self.data else None
        rated = self.battery_data.get("rated_capacity")
        return available_battery_capacity(soc, rated)

    def _update_solar_measurement(self, now: datetime) -> None:
        """Read and evaluate the configured Home Assistant solar sensor."""
        if not self.solar_power_entity:
            self._solar_sensor_problem = None
            self.solar_power = None
            self.solar_surplus = False
            self._solar_samples.clear()
            return

        state = self.hass.states.get(self.solar_power_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            self._solar_sensor_problem = (
                f"Sensor {self.solar_power_entity} is unavailable"
            )
            self.solar_power = None
            self.solar_surplus = False
            self._solar_samples.clear()
            return
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            self._solar_sensor_problem = (
                f"Sensor {self.solar_power_entity} has no numeric state"
            )
            self.solar_power = None
            self.solar_surplus = False
            self._solar_samples.clear()
            return

        unit = str(state.attributes.get("unit_of_measurement", "W")).lower()
        if unit == "kw":
            value *= 1000
        elif unit != "w":
            self._solar_sensor_problem = (
                f"Unit '{unit}' is not supported"
            )
            self.solar_power = None
            self.solar_surplus = False
            self._solar_samples.clear()
            return

        self._solar_sensor_problem = None
        self.solar_power = round(value, 1)
        keep = timedelta(
            minutes=max(
                self.solar_surplus_on_minutes,
                self.solar_surplus_off_minutes,
            )
        )
        append_sample(self._solar_samples, now, value, keep)
        if not self.solar_surplus:
            average = time_weighted_average(
                self._solar_samples,
                now,
                timedelta(minutes=self.solar_surplus_on_minutes),
            )
            if average is not None and average >= self.solar_surplus_on_w:
                self.solar_surplus = True
        else:
            average = time_weighted_average(
                self._solar_samples,
                now,
                timedelta(minutes=self.solar_surplus_off_minutes),
            )
            if average is not None and average < self.solar_surplus_off_w:
                self.solar_surplus = False

    def _record_battery_power(
        self, data: dict[str, Any], now: datetime
    ) -> float | None:
        """Record normalized battery power, positive while charging."""
        raw = data.get("bat_power")
        invert = False
        if raw is None:
            raw = data.get("ongrid_power")
            invert = True
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if invert:
            value = -value
        if value == 0:
            value = 0.0
        append_sample(
            self._battery_power_samples,
            now,
            value,
            timedelta(minutes=5),
        )
        return value

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
            now = datetime.now()
            self._update_solar_measurement(now)
            battery_power = self._record_battery_power(data, now)
            if self.solar_start_source == "ct":
                ct_power = None
                phase = self._storage_phase if self.storage_mode_enabled else None
                if phase == "holding" and battery_power is not None and abs(battery_power) <= 10:
                    try:
                        meter = await self.client.get_energy_meter_status()
                        ct_power = meter.get("total_power") if meter else None
                    except Exception as err:
                        _LOGGER.debug("CT start measurement unavailable: %s", err)
                self.solar_surplus = self._ct_export_start.update(
                    datetime.now(), ct_power, phase,
                    self.ct_export_start_w, self.ct_start_minutes,
                    max(90, self.update_interval.total_seconds() * 2),
                )

            if self._automatic_controller_ready:
                await self._async_update_automatic_storage(data.get("bat_soc"))
            if self.storage_mode_enabled:
                await self._async_update_storage_mode(
                    data.get("bat_soc"), now, battery_power
                )
            
            # Get battery details only at the slower battery interval.
            if (
                self._last_battery_update is None
                or (now - self._last_battery_update)
                >= self._battery_update_interval
            ):
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
                            "ip",
                                normalize_ipv4(
                                self.entry.data.get(CONF_IP_ADDRESS)
                            ),
                        )
                        if "ip" in self.device_data:
                            self.device_data["ip"] = normalize_ipv4(
                                self.device_data["ip"]
                            )
                    except Exception as device_err:
                        _LOGGER.debug("Failed to get device info: %s", device_err)
                    try:
                        self.wifi_data = await self.client.get_wifi_status()
                        for field in ("sta_ip", "sta_gate", "sta_mask", "sta_dns"):
                            if field in self.wifi_data:
                                self.wifi_data[field] = normalize_ipv4(
                                    self.wifi_data[field]
                                )
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
                    self._last_mode_feedback_at = datetime.now()
                    self._last_mode_update = now
                # Add mode to main data for easy access
                    if "mode" in self.mode_data:
                        data["mode"] = self.mode_data["mode"]
                
                # Add CT meter data to mode_data (ES.GetMode includes it)
                # Apply scaling for energy values (*0.1 as per API documentation)
                    if "input_energy" in self.mode_data:
                        self.mode_data["input_energy"] = round(
                            self.mode_data.get("input_energy", 0) * 0.1,
                            1,
                        )
                    if "output_energy" in self.mode_data:
                        self.mode_data["output_energy"] = round(
                            self.mode_data.get("output_energy", 0) * 0.1,
                            1,
                        )
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
                            em_data["input_energy"] = round(
                                em_data.get("input_energy", 0) * 0.1,
                                1,
                            )
                        if "output_energy" in em_data:
                            em_data["output_energy"] = round(
                                em_data.get("output_energy", 0) * 0.1,
                                1,
                            )
                    
                    # Merge with mode_data
                    # Prefer EM.GetStatus for CT power data because ES.GetMode
                    # can return zero while CT is not in the active mode.
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
                                if k not in self.mode_data or (
                                    k in ct_fields
                                    and self.mode_data.get(k) == 0
                                ):
                                    self.mode_data[k] = v
                        else:
                            self.mode_data = em_data
                except Exception as em_err:
                    _LOGGER.debug(
                        "Failed to get optional EM status: %s", em_err
                    )
                    # EM.GetStatus is optional and may not be available on all devices

            # Preserve the cached mode in the fast coordinator data between the
            # slower ES.GetMode updates.
            if "mode" in self.mode_data:
                data["mode"] = self.mode_data["mode"]

            self._update_standby_confirmation(data)
            await self._async_passive_keepalive()
            await self._async_enforce_operating_mode()
            
            self._last_successful_update = datetime.now()
            return data
        except Exception as err:
            _LOGGER.error("Failed to get device data: %s", err)
            self._ct_export_start.samples.clear()
            raise UpdateFailed(f"Failed to update data: {err}")

    async def _async_enforce_operating_mode(self) -> None:
        """Restore the persistent mode setpoint after external changes."""
        if (
            not self._mode_enforcement_ready
            or self.storage_mode_enabled
            or self.desired_operating_mode == MODE_STORAGE
        ):
            return

        actual_mode = self.mode_data.get("mode")
        if actual_mode is None:
            return

        now = datetime.now()
        if (
            self._last_mode_enforcement_check is not None
            and (now - self._last_mode_enforcement_check)
            < self._mode_enforcement_interval
        ):
            return
        self._last_mode_enforcement_check = now

        expected_mode = expected_physical_mode(self.desired_operating_mode)
        if actual_mode != expected_mode:
            self._standby_zero_samples = 0

        feedback_confirmed = mode_feedback_confirmed(
            self.desired_operating_mode,
            actual_mode,
            self._standby_zero_samples,
        )
        feedback_is_newer_than_restore = (
            self._mode_confirmation_required_after is None
            or (
                self._last_mode_feedback_at is not None
                and self._last_mode_feedback_at
                > self._mode_confirmation_required_after
            )
        )
        if feedback_confirmed and feedback_is_newer_than_restore:
            self._active_mode_dropout = None
            self._mode_enforcement_failures = 0
            self._mode_enforcement_error = False
            self._mode_enforcement_next_attempt = None
            self._mode_confirmation_required_after = None
            return
        if feedback_confirmed:
            # The write was confirmed immediately, but only a later regular
            # ES.GetMode poll proves that the device retained the setpoint.
            return

        if (
            self._mode_enforcement_next_attempt is not None
            and now < self._mode_enforcement_next_attempt
        ):
            return

        self._mode_enforcement_failures += 1
        attempt = self._mode_enforcement_failures
        if attempt >= 5:
            # Keep reporting the error but retry every 30 minutes instead of
            # stopping permanently, so a temporary outage heals on its own.
            self._mode_enforcement_error = True
            self._mode_enforcement_next_attempt = now + timedelta(
                seconds=MODE_ENFORCEMENT_RECOVERY_SECONDS
            )
        else:
            self._mode_enforcement_next_attempt = now + timedelta(
                seconds=MODE_ENFORCEMENT_RETRY_SECONDS
            )
        if actual_mode != expected_mode:
            self._record_mode_dropout(
                now, f"Mode {actual_mode} instead of {expected_mode}"
            )
        else:
            self._record_mode_dropout(now, "Standby power is outside tolerance")
        _LOGGER.warning(
            "Operating mode differs from setpoint (actual=%s, desired=%s); "
            "restore attempt %d",
            actual_mode,
            self.desired_operating_mode,
            attempt,
        )
        try:
            if self.desired_operating_mode == MODE_STANDBY:
                self._standby_zero_samples = 0
            await self.async_apply_desired_operating_mode()
        except Exception as err:
            _LOGGER.warning(
                "Operating-mode restore attempt %d failed: %s", attempt, err
            )
            if self._mode_enforcement_error:
                self.async_update_listeners()
            return

        # Do not clear the incident or attempt counter based on the immediate
        # response to the write. A later independent polling cycle must prove
        # that the device retained the requested mode.
        self._mode_confirmation_required_after = datetime.now()

    def _update_standby_confirmation(self, data: dict[str, Any]) -> None:
        """Track three consecutive fast samples confirming neutral Standby."""
        if (
            not self._mode_enforcement_ready
            or self.storage_mode_enabled
            or self.desired_operating_mode != MODE_STANDBY
            or self.mode_data.get("mode") != MODE_PASSIVE
        ):
            self._standby_zero_samples = 0
            return
        try:
            grid_power = float(data.get("ongrid_power"))
        except (TypeError, ValueError):
            self._standby_zero_samples = 0
            return
        if abs(grid_power) <= 30:
            self._standby_zero_samples = min(
                3, self._standby_zero_samples + 1
            )
        else:
            self._standby_zero_samples = 0

    async def _async_passive_keepalive(self) -> None:
        """Renew persistent Standby/Manual before the Passive countdown ends.

        Checked on every fast update cycle because the two-minute enforcement
        interval cannot guarantee a renewal within the device countdown.
        """
        if (
            not self._mode_enforcement_ready
            or self.automatic_storage_enabled
            or self.storage_mode_enabled
            or self.desired_operating_mode not in (MODE_STANDBY, MODE_MANUAL)
            or self._passive_keepalive_due is None
        ):
            return
        now = datetime.now()
        if now < self._passive_keepalive_due:
            return
        try:
            await self.async_apply_desired_operating_mode()
        except Exception as err:
            self._passive_keepalive_due = now + timedelta(seconds=60)
            _LOGGER.warning("Passive keepalive failed: %s", err)

    def _record_mode_dropout(self, now: datetime, reason: str) -> None:
        """Remember one event per continuous setpoint deviation."""
        if not is_new_dropout(self._active_mode_dropout):
            return
        self._active_mode_dropout = reason
        self._mode_dropouts.append((now, reason))
        self._diagnostics_store.async_delay_save(self._diagnostics_data, 10)

    def _mode_dropouts_last_24h(
        self, now: datetime
    ) -> list[tuple[datetime, str]]:
        """Return the deviations recorded during the last 24 hours."""
        cutoff = now - timedelta(hours=24)
        return [item for item in self._mode_dropouts if item[0] >= cutoff]

    def health_report(self) -> dict[str, Any]:
        """Run the internal self-tests and return status plus details."""
        now = datetime.now()
        checks: dict[str, dict[str, str]] = {}

        def add(name: str, status: str, detail: str) -> None:
            checks[name] = {"status": status, "detail": detail}

        # Connectivity: the device must have answered recently.
        interval = (
            self.update_interval.total_seconds() if self.update_interval else 60
        )
        if self._last_successful_update is None:
            if self.last_update_success:
                add("device_connection", "ok", "First update is running")
            else:
                add("device_connection", "error", "Device is not responding")
        else:
            age = (now - self._last_successful_update).total_seconds()
            if not self.last_update_success or age > max(3 * interval, 60):
                add(
                    "device_connection",
                    "error",
                    f"Last response {int(age)} seconds ago",
                )
            else:
                add(
                    "device_connection",
                    "ok",
                    f"Last response {int(age)} seconds ago",
                )

        # Operating-mode supervision.
        if self._mode_enforcement_error:
            add(
                "operating_mode",
                "error",
                "The requested mode could not be restored repeatedly",
            )
        elif self._mode_enforcement_failures > 0:
            add(
                "operating_mode",
                "warning",
                "Restore is running "
                f"(attempt {self._mode_enforcement_failures})",
            )
        else:
            add("operating_mode", "ok", "Requested mode is active")

        # Passive renewal for persistent Standby/Manual.
        if (
            self.desired_operating_mode in (MODE_STANDBY, MODE_MANUAL)
            and not self.storage_mode_enabled
            and not self.automatic_storage_enabled
            and self._last_passive_renewal is not None
        ):
            renewal_age = (now - self._last_passive_renewal).total_seconds()
            if renewal_age > PASSIVE_CD_TIME_SECONDS:
                add(
                    "passive_renewal",
                    "error",
                    f"Last renewal {int(renewal_age)} seconds ago; "
                    "Passive mode may have expired",
                )
            elif renewal_age > PASSIVE_KEEPALIVE_SECONDS + 120:
                add(
                    "passive_renewal",
                    "warning",
                    f"Renewal is overdue ({int(renewal_age)} seconds)",
                )
            else:
                add(
                    "passive_renewal",
                    "ok",
                    f"Last renewal {int(renewal_age)} seconds ago",
                )

        # Mode deviations within the last 24 hours.
        dropouts = self._mode_dropouts_last_24h(now)
        if dropouts:
            last_time, last_reason = dropouts[-1]
            detail = (
                f"{len(dropouts)} incident(s), latest at "
                f"{last_time.strftime('%H:%M')}: {last_reason}"
            )
            add(
                "mode_dropouts_24h",
                "warning" if len(dropouts) >= 3 else "ok",
                detail,
            )
        else:
            add("mode_dropouts_24h", "ok", "No incidents")

        # Solar sensor used by the automatic winter controller.
        if self.solar_power_entity and self.solar_start_source == "solar":
            if self._solar_sensor_problem:
                add("solar_sensor", "warning", self._solar_sensor_problem)
            else:
                add(
                    "solar_sensor",
                    "ok",
                    f"{self.solar_power_entity} provides data",
                )
        elif self.automatic_storage_enabled and self.solar_start_source == "solar":
            add(
                "solar_sensor",
                "warning",
                "Automatic winter operation has no configured solar sensor",
            )

        # Day tracking of the automatic winter controller.
        if self.automatic_storage_enabled:
            if self._last_invalid_tracking_day:
                day, reason = self._last_invalid_tracking_day
                add(
                    "day_tracking",
                    "warning",
                    f"Day {day} was not counted: {reason}",
                )
            else:
                add(
                    "day_tracking",
                    "ok",
                    "Observation days are complete",
                )

        statuses = [check["status"] for check in checks.values()]
        if "error" in statuses:
            status = "error"
        elif "warning" in statuses:
            status = "warning"
        else:
            status = "ok"
        return {"status": status, "checks": checks}

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        await super().async_shutdown()

    async def set_mode(self, mode: str) -> None:
        """Set operating mode.
        
        Args:
            mode: Operating mode
        """
        # Venus E 3.0 does not reliably accept Passive without a passive_cfg.
        # Local test: request a neutral 0 W target with a firmware-compatible
        # countdown; the persistent UI modes refresh it before expiry.
        if mode == MODE_PASSIVE:
            result = await self.client.set_passive_mode(
                power=0, cd_time=PASSIVE_CD_TIME_SECONDS
            )
        else:
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

        attempts = 5 if mode == MODE_PASSIVE else 1
        delay = 2 if mode == MODE_PASSIVE else 3
        confirmed_mode_data: dict[str, Any] = {}
        confirmed_mode = None
        for _attempt in range(attempts):
            await asyncio.sleep(delay)
            confirmed_mode_data = await self.client.get_energy_system_mode()
            confirmed_mode = confirmed_mode_data.get("mode")
            if confirmed_mode == mode:
                break
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
                "Device did not confirm operating mode "
                f"{mode}; reported {confirmed_mode}"
            )

        self.mode_data.update(confirmed_mode_data)
        self.data["mode"] = mode
        self.async_update_listeners()

    async def async_enable_storage_mode(self) -> None:
        """Enable storage/winter mode and evaluate its first action."""
        self.storage_mode_enabled = True
        self._storage_phase = None
        self._reset_mode_enforcement()
        await self._storage.async_save({"enabled": True})
        soc = self.data.get("bat_soc") if self.data else None
        await self._async_update_storage_mode(
            soc, datetime.now()
        )
        self.async_update_listeners()

    async def async_disable_storage_mode(self) -> None:
        """Disable storage/winter mode."""
        self.storage_mode_enabled = False
        self._storage_phase = None
        self._solar_check_started = None
        self._solar_discharge_started = None
        self._solar_check_cooldown_until = None
        self._storage_command_due = None
        self._reset_mode_enforcement()
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
            await self._async_update_storage_mode(
                soc, datetime.now()
            )
        else:
            await self.set_mode(MODE_AUTO)
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
        self._solar_check_started = None
        self._solar_discharge_started = None
        self._solar_check_cooldown_until = None
        self._storage_command_due = None
        self._reset_mode_enforcement()
        self._reset_day_tracking(dt_util.now() if enabled else None)
        await self._storage.async_save({"enabled": False})
        await self._automatic_storage.async_save(self._automatic_storage_data())
        if set_auto:
            await self.async_set_desired_operating_mode(MODE_AUTO)
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
        if self._tracking_min_soc is None or soc_value < self._tracking_min_soc:
            self._tracking_min_soc = soc_value

        # Count only a genuinely new solar-assisted full charge. A battery that
        # simply remains at 99% overnight must not count as another day.
        if (
            self._automatic_controller_state == "storage"
            and self._tracking_had_solar_charge
            and self._tracking_min_soc is not None
            and self._tracking_min_soc <= STORAGE_FULL_CHARGE_ARM_SOC
            and soc_value >= STORAGE_FULL_CHARGE_SOC
        ):
            self._tracking_full_charge_event = True
        if (
            self._automatic_controller_state == "storage"
            and self._full_soc_days >= STORAGE_EXIT_FULL_CHARGE_DAYS - 1
            and self._tracking_full_charge_event
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
        self._solar_check_started = None
        self._solar_discharge_started = None
        self._solar_check_cooldown_until = None
        self._storage_command_due = None
        self._reset_mode_enforcement()
        self._reset_day_tracking(dt_util.now())
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
        valid_day = consecutive_day and observed_for >= timedelta(
            hours=STORAGE_VALID_DAY_HOURS
        )
        if not valid_day:
            reason = (
                "gap between observation days"
                if not consecutive_day
                else f"observed for only {int(observed_for.total_seconds() // 3600)} h"
            )
            self._last_invalid_tracking_day = (
                self._tracking_day.isoformat(),
                reason,
            )
            self._low_soc_days = 0
            self._full_soc_days = 0
            return
        self._last_invalid_tracking_day = None

        if self._automatic_controller_state == "observing":
            if self._tracking_max_soc < STORAGE_TARGET_SOC:
                self._low_soc_days += 1
            else:
                self._low_soc_days = 0
            if self._low_soc_days >= self.storage_observation_days:
                self._automatic_controller_state = "storage"
                self.storage_mode_enabled = True
                self._storage_phase = None
                self._reset_mode_enforcement()
                self._full_soc_days = 0
                await self._storage.async_save({"enabled": True})
        else:
            if self._tracking_full_charge_event:
                self._full_soc_days += 1
            else:
                self._full_soc_days = 0
            if self._full_soc_days >= STORAGE_EXIT_FULL_CHARGE_DAYS:
                await self._async_exit_automatic_storage()

        await self._automatic_storage.async_save(self._automatic_storage_data())

    async def _async_apply_storage_phase(self, phase: str) -> None:
        """Apply and confirm the physical mode required by a storage phase."""
        expected_mode, passive_power = storage_phase_command(
            phase, STORAGE_CHARGE_POWER
        )
        if expected_mode == MODE_PASSIVE:
            assert passive_power is not None
            result = await self.client.set_passive_mode(
                power=passive_power, cd_time=PASSIVE_CD_TIME_SECONDS
            )
        else:
            result = await self.client.set_mode(MODE_AUTO)
        if result.get("set_result") is False:
            raise ValueError(f"Device rejected storage phase {phase}")

        confirmed: dict[str, Any] = {}
        for _attempt in range(5):
            await asyncio.sleep(2)
            confirmed = await self.client.get_energy_system_mode()
            if confirmed.get("mode") == expected_mode:
                break
        if confirmed.get("mode") != expected_mode:
            if confirmed:
                self.mode_data.update(confirmed)
            raise ValueError(
                f"Device did not confirm storage phase {phase}; "
                f"reported {confirmed.get('mode')}"
            )

        self.mode_data.update(confirmed)
        self.mode_data["mode"] = expected_mode
        if self.data is not None:
            self.data["mode"] = expected_mode
        self._storage_command_due = (
            datetime.now() + timedelta(seconds=PASSIVE_KEEPALIVE_SECONDS)
            if expected_mode == MODE_PASSIVE
            else None
        )

    async def _async_update_storage_mode(
        self,
        soc: Any,
        now: datetime | None = None,
        battery_power: float | None = None,
    ) -> None:
        """Keep the battery near 50 percent and use verified solar output."""
        soc_value: float | None = None
        try:
            if soc is not None:
                soc_value = float(soc)
        except (TypeError, ValueError):
            _LOGGER.debug("Storage mode received invalid SOC value: %s", soc)

        # Without a first valid SOC there is no safe phase to choose. Once a
        # phase is active, however, its command must still be supervised and
        # renewed while SOC feedback is temporarily unavailable.
        if soc_value is None and self._storage_phase is None:
            return

        now = now or datetime.now()
        recharge_window_active = time_in_window(
            dt_util.now().time(),
            self.storage_recharge_start,
            self.storage_recharge_end,
        )
        if (
            self._storage_phase in ("solar_check", "solar_charging")
            and battery_power is not None
            and battery_power < -SOLAR_DISCHARGE_THRESHOLD_W
        ):
            if self._solar_discharge_started is None:
                self._solar_discharge_started = now
        else:
            self._solar_discharge_started = None
        continuous_discharge_seconds = (
            (now - self._solar_discharge_started).total_seconds()
            if self._solar_discharge_started is not None
            else 0
        )
        battery_average = time_weighted_average(
            self._battery_power_samples,
            now,
            timedelta(seconds=BATTERY_POWER_AVERAGE_SECONDS),
        )

        # Manually selected Storage keeps the original self-contained
        # 45/50/55 hysteresis. Solar-assisted states belong exclusively to the
        # automatic winter controller.
        if soc_value is None:
            next_phase = self._storage_phase
            assert next_phase is not None
            solar_cycle_aborted = False
        elif not self.automatic_storage_enabled:
            next_phase = manual_storage_next_phase(
                self._storage_phase,
                soc_value,
                STORAGE_CHARGE_START_SOC,
                STORAGE_TARGET_SOC,
                STORAGE_AUTO_START_SOC,
            )
        else:
            elapsed_seconds = (
                (now - self._solar_check_started).total_seconds()
                if self._solar_check_started
                else 0
            )
            cooldown_active = (
                self._solar_check_cooldown_until is not None
                and now < self._solar_check_cooldown_until
            )
            next_phase = automatic_storage_next_phase(
                self._storage_phase,
                soc_value,
                solar_surplus=self.solar_surplus,
                cooldown_active=cooldown_active,
                recharge_window_active=recharge_window_active,
                recharge_start_soc=self.storage_recharge_start_soc,
                recharge_stop_soc=self.storage_recharge_stop_soc,
                solar_check_elapsed_seconds=elapsed_seconds,
                continuous_discharge_seconds=continuous_discharge_seconds,
                battery_average=battery_average,
                target_soc=self.storage_recharge_stop_soc,
                charge_threshold_w=BATTERY_POWER_THRESHOLD_W,
                charge_exit_w=SOLAR_CHARGING_EXIT_W,
                charge_confirmation_seconds=(
                    SOLAR_CHARGE_CONFIRMATION_SECONDS
                ),
                solar_check_max_seconds=SOLAR_CHECK_MAX_SECONDS,
                discharge_abort_seconds=SOLAR_DISCHARGE_ABORT_SECONDS,
            )
            if next_phase == "solar_charging":
                self._tracking_had_solar_charge = True
            solar_cycle_aborted = (
                self._storage_phase in ("solar_check", "solar_charging")
                and next_phase not in ("solar_check", "solar_charging")
            )
        if not self.automatic_storage_enabled:
            solar_cycle_aborted = False

        previous_phase = self._storage_phase
        phase_changed = next_phase != previous_phase
        next_command = storage_phase_command(
            next_phase, STORAGE_CHARGE_POWER
        )
        expected_mode = next_command[0]
        planned_command_change = (
            phase_changed
            and storage_phase_changes_command(
                previous_phase, next_phase, STORAGE_CHARGE_POWER
            )
        )
        actual_mode = self.mode_data.get("mode")
        mode_mismatch = actual_mode not in (None, expected_mode)
        keepalive_due = (
            self._storage_command_due is not None
            and now >= self._storage_command_due
        )

        feedback_is_newer_than_restore = (
            self._mode_confirmation_required_after is not None
            and self._last_mode_feedback_at is not None
            and self._last_mode_feedback_at
            > self._mode_confirmation_required_after
        )
        confirmed_pending_transition = (
            planned_command_change
            and actual_mode == expected_mode
            and feedback_is_newer_than_restore
        )
        if actual_mode == expected_mode and feedback_is_newer_than_restore:
            self._active_mode_dropout = None
            self._mode_enforcement_failures = 0
            self._mode_enforcement_error = False
            self._mode_enforcement_next_attempt = None
            self._mode_confirmation_required_after = None
            self.async_update_listeners()

        # A planned change to a different physical command starts with a fresh
        # retry budget. Logical transitions that keep the same command (for
        # example solar_check -> solar_charging) do not touch supervision.
        if (
            planned_command_change
            and self._pending_storage_phase != next_phase
        ):
            self._reset_mode_enforcement()
            self._pending_storage_phase = next_phase
        elif not phase_changed and self._pending_storage_phase is not None:
            # Conditions changed before a failed transition was completed.
            self._reset_mode_enforcement()

        needs_command = storage_command_required(
            planned_command_change=planned_command_change,
            actual_mode=actual_mode,
            expected_mode=expected_mode,
            keepalive_due=keepalive_due,
            confirmed_pending_transition=confirmed_pending_transition,
        )
        if not needs_command and not phase_changed:
            return

        if needs_command and (
            self._mode_enforcement_next_attempt is not None
            and now < self._mode_enforcement_next_attempt
        ):
            return

        restore_attempt = mode_mismatch and not planned_command_change
        if restore_attempt:
            self._mode_enforcement_failures += 1
            self._schedule_mode_enforcement_retry(now)
            self._record_mode_dropout(
                now,
                f"Mode {actual_mode} instead of {expected_mode} "
                "during storage operation",
            )

        if needs_command:
            # As with the normal persistent modes, only a later regular
            # ES.GetMode poll proves that the device retained this command.
            self._mode_confirmation_required_after = datetime.now()
            try:
                await self._async_apply_storage_phase(next_phase)
            except Exception as err:
                if not restore_attempt:
                    self._mode_enforcement_failures += 1
                    self._schedule_mode_enforcement_retry(now)
                _LOGGER.warning(
                    "Storage phase %s could not be confirmed (attempt %d): %s",
                    next_phase,
                    self._mode_enforcement_failures,
                    err,
                )
                self.async_update_listeners()
                return

        if phase_changed:
            assert soc_value is not None
            if next_phase == "solar_check":
                self._solar_check_started = now
            elif previous_phase == "solar_check":
                self._solar_check_started = None
            if next_phase not in ("solar_check", "solar_charging"):
                self._solar_discharge_started = None
            if solar_cycle_aborted:
                self._solar_check_cooldown_until = now + timedelta(
                    seconds=SOLAR_CHECK_COOLDOWN_SECONDS
                )
            _LOGGER.info(
                "Storage mode changed phase from %s to %s at %.1f%% SOC",
                previous_phase,
                next_phase,
                soc_value,
            )
        self._storage_phase = next_phase
        self._pending_storage_phase = None
        if self.automatic_storage_enabled and phase_changed:
            self._schedule_automatic_storage_save()
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
        # Editing a schedule must not silently replace the active controller.
        # This also preserves an automatic or manual storage phase.
        await self._async_restore_active_operating_mode()
        await self.async_request_refresh()

    async def _async_restore_active_operating_mode(self) -> None:
        """Reapply the controller that currently owns the device mode."""
        if self.automatic_storage_enabled and not self.storage_mode_enabled:
            await self.set_mode(MODE_AUTO)
            return
        if self.storage_mode_enabled:
            now = datetime.now()
            self._storage_command_due = now
            soc = self.data.get("bat_soc") if self.data else None
            await self._async_update_storage_mode(soc, now)
            return
        if self.desired_operating_mode == MODE_STORAGE:
            await self.async_enable_storage_mode()
            return
        await self.async_apply_desired_operating_mode()

    async def async_set_led_state(self, enabled: bool) -> None:
        """Set the panel LED and synchronize its optimistic HA state."""
        result = await self.client.set_led_ctrl(enabled)
        if result.get("set_result") is False:
            raise ValueError(
                f"Device rejected LED {'on' if enabled else 'off'} command"
            )
        self.led_state = enabled
        self.async_update_listeners()

    async def clear_all_manual_schedules(self) -> dict[str, Any]:
        """Clear all manual schedules.
        
        Returns:
            Dictionary with operation results
        """
        results = await self.client.clear_all_manual_schedules()
        await self._async_restore_active_operating_mode()
        await self.async_request_refresh()
        return results
