"""Pure state helpers for the Marstek Venus E integration."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any


def normalize_ipv4(value: Any) -> Any:
    """Remove harmless leading zeroes from a valid IPv4 address."""
    if not isinstance(value, str):
        return value
    parts = value.strip().split(".")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        return value
    numbers = [int(part, 10) for part in parts]
    if any(number > 255 for number in numbers):
        return value
    return ".".join(str(number) for number in numbers)


def device_selection_options(
    discovered_devices: list[tuple[str, int, dict[str, Any]]],
    actions: list[tuple[str, str]],
) -> list[dict[str, str]]:
    """Build a homogeneous Home Assistant select-option list."""
    options: list[dict[str, str]] = []
    for fallback_ip, _port, payload in discovered_devices:
        device_info = payload.get("result", {})
        device_name = device_info.get("device") or "Marstek Venus E"
        device_ip = str(
            normalize_ipv4(device_info.get("ip") or fallback_ip)
        )
        source = payload.get("src")
        label = f"{device_ip} - {device_name}"
        if source:
            label += f" [{source}]"
        options.append({"value": device_ip, "label": label})

    options.extend(
        {"value": value, "label": label} for value, label in actions
    )
    return options


def time_weighted_average(
    samples: deque[tuple[datetime, float]],
    now: datetime,
    window: timedelta,
) -> float | None:
    """Return a time-weighted average once the full window is covered."""
    if not samples:
        return None
    start = now - window
    if samples[0][0] > start:
        return None

    points = list(samples)
    current_value = points[0][1]
    cursor = start
    total = 0.0
    for timestamp, value in points[1:]:
        if timestamp <= start:
            current_value = value
            continue
        if timestamp > now:
            break
        total += current_value * (timestamp - cursor).total_seconds()
        cursor = timestamp
        current_value = value
    total += current_value * (now - cursor).total_seconds()
    seconds = window.total_seconds()
    return total / seconds if seconds > 0 else None


def append_sample(
    samples: deque[tuple[datetime, float]],
    now: datetime,
    value: float,
    keep: timedelta,
) -> None:
    """Append a sample while retaining one value before the window."""
    samples.append((now, value))
    cutoff = now - keep
    while len(samples) >= 2 and samples[1][0] <= cutoff:
        samples.popleft()


def week_set_from_days(days: list[str]) -> int:
    """Return the Marstek weekday bitmask, defaulting to every day."""
    day_map = {
        "monday": 1,
        "tuesday": 2,
        "wednesday": 4,
        "thursday": 8,
        "friday": 16,
        "saturday": 32,
        "sunday": 64,
    }
    week_set = 0
    for day in days:
        week_set |= day_map.get(day, 0)
    return week_set if week_set > 0 else 127


def normalized_battery_power(data: dict[str, Any] | None) -> float | None:
    """Return battery power with positive values representing charging."""
    if not data:
        return None
    value = data.get("bat_power")
    invert = False
    if value is None:
        value = data.get("ongrid_power")
        invert = True
    try:
        power = float(value)
    except (TypeError, ValueError):
        return None
    return -power if invert else power


def operation_status_from_power(
    battery_power: float | None,
    *,
    mode_error: bool = False,
    storage_state: str | None = None,
) -> str | None:
    """Return the language-independent operating status state."""
    if mode_error:
        return "mode_error"
    if storage_state is not None:
        return storage_state
    if battery_power is None:
        return None
    if battery_power > 10:
        return "charging"
    if battery_power < -10:
        return "discharging"
    return "standby"


def available_battery_capacity(
    soc: Any, rated_capacity: Any
) -> float | None:
    """Return the unfilled battery capacity in Wh."""
    try:
        return round(
            (100 - float(soc)) * float(rated_capacity) / 100,
            1,
        )
    except (TypeError, ValueError):
        return None


def manual_storage_next_phase(
    current_phase: str | None,
    soc: float,
    charge_start_soc: float,
    target_soc: float,
    auto_start_soc: float,
) -> str:
    """Return the next phase for manually selected Storage mode."""
    if current_phase == "charging" and soc < target_soc:
        return "charging"
    if current_phase == "auto" and soc > target_soc:
        return "auto"
    if soc <= charge_start_soc:
        return "charging"
    if soc >= auto_start_soc:
        return "auto"
    return "holding"


def automatic_storage_next_phase(
    current_phase: str | None,
    soc: float,
    *,
    solar_surplus: bool,
    cooldown_active: bool,
    solar_check_elapsed_seconds: float,
    battery_average: float | None,
    charge_start_soc: float,
    target_soc: float,
    charge_threshold_w: float,
    charge_exit_w: float,
    charge_confirmation_seconds: float,
    solar_check_max_seconds: float,
) -> str:
    """Return the next phase for automatic winter operation."""
    if current_phase == "charging":
        return "charging" if soc < target_soc else "holding"
    if soc <= charge_start_soc:
        return "charging"

    if current_phase == "solar_check":
        if soc < target_soc:
            return "holding"
        if (
            solar_check_elapsed_seconds >= charge_confirmation_seconds
            and battery_average is not None
            and battery_average > charge_threshold_w
        ):
            return "solar_charging"
        if solar_check_elapsed_seconds >= solar_check_max_seconds:
            return "auto" if soc > target_soc else "holding"
        return "solar_check"

    if current_phase == "solar_charging":
        return solar_charging_next_phase(
            soc, battery_average, target_soc, charge_exit_w
        )

    if current_phase == "auto":
        if soc <= target_soc:
            return "holding"
        if (
            battery_average is not None
            and battery_average > charge_threshold_w
        ):
            return "solar_charging"
        return "auto"

    if current_phase == "holding" and solar_surplus and not cooldown_active:
        return "solar_check"
    return "holding"


def storage_phase_command(
    phase: str, charge_power: int
) -> tuple[str, int | None]:
    """Map a storage phase to its physical mode and optional Passive power."""
    if phase == "charging":
        return "Passive", charge_power
    if phase == "holding":
        return "Passive", 0
    if phase in ("solar_check", "solar_charging", "auto"):
        return "Auto", None
    raise ValueError(f"Unknown storage phase: {phase}")


def storage_phase_changes_command(
    current_phase: str | None,
    next_phase: str,
    charge_power: int,
) -> bool:
    """Return whether a phase transition needs a different device command."""
    current_command = (
        storage_phase_command(current_phase, charge_power)
        if current_phase is not None
        else None
    )
    return current_command != storage_phase_command(next_phase, charge_power)


def storage_command_required(
    *,
    planned_command_change: bool,
    actual_mode: str | None,
    expected_mode: str,
    keepalive_due: bool,
    confirmed_pending_transition: bool,
) -> bool:
    """Return whether storage supervision must send a physical command."""
    mode_mismatch = actual_mode not in (None, expected_mode)
    return (
        (planned_command_change and not confirmed_pending_transition)
        or mode_mismatch
        or keepalive_due
    )


def solar_charging_next_phase(
    soc: float,
    battery_average: float | None,
    target_soc: float,
    exit_power_w: float,
) -> str:
    """Return the next automatic-storage phase after confirmed solar charging.

    ``exit_power_w`` is deliberately lower than the threshold that enters the
    phase. The resulting dead band keeps a battery power average hovering at
    the entry threshold from flipping the phase back and forth.
    """
    if soc <= target_soc:
        return "holding"
    if battery_average is not None and battery_average <= exit_power_w:
        return "auto"
    return "solar_charging"


def is_new_dropout(active_reason: str | None) -> bool:
    """Return whether a deviation starts a new continuous dropout incident."""
    return active_reason is None


def expected_physical_mode(desired_mode: str) -> str:
    """Map a persistent UI mode to the mode reported by the device."""
    if desired_mode in ("Standby", "Manual"):
        return "Passive"
    if desired_mode == "Schedule":
        return "Manual"
    return desired_mode


def mode_feedback_confirmed(
    desired_mode: str,
    actual_mode: str | None,
    standby_zero_samples: int,
) -> bool:
    """Return whether independent feedback confirms the persistent setpoint."""
    if actual_mode != expected_physical_mode(desired_mode):
        return False
    return desired_mode != "Standby" or standby_zero_samples >= 3
