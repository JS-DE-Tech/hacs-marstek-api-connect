"""Constants for the Marstek Venus E integration."""
from typing import Final

DOMAIN: Final = "hacs_marstek_api_connect"

# Device Configuration
DEFAULT_PORT: Final = 30000
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds (fast ES.GetStatus polling)
DEFAULT_TIMEOUT: Final = 30.0  # seconds - UDP request timeout (API requires 30s)

# Passive-mode renewal for persistent Standby/Manual and storage phases.
# The countdown must comfortably exceed the renewal interval so a missed
# fast-poll cycle can never let the Passive configuration expire.
PASSIVE_CD_TIME_SECONDS: Final = 600
PASSIVE_KEEPALIVE_SECONDS: Final = 300
MODE_ENFORCEMENT_RETRY_SECONDS: Final = 30
# Retry a failed setpoint every 30 minutes after the regular attempts fail.
MODE_ENFORCEMENT_RECOVERY_SECONDS: Final = 1800

# Modes
MODE_AUTO: Final = "Auto"
MODE_AI: Final = "AI"
MODE_MANUAL: Final = "Manual"
MODE_PASSIVE: Final = "Passive"
MODE_SCHEDULE: Final = "Schedule"
MODE_STORAGE: Final = "Storage"
MODE_STANDBY: Final = "Standby"

SELECTABLE_MODES: Final = [
    MODE_AUTO,
    MODE_AI,
    MODE_STANDBY,
    MODE_MANUAL,
    MODE_SCHEDULE,
    MODE_STORAGE,
]

# Storage/winter mode thresholds
STORAGE_CHARGE_START_SOC: Final = 45
STORAGE_TARGET_SOC: Final = 50
STORAGE_AUTO_START_SOC: Final = 55
STORAGE_CHARGE_POWER: Final = -500  # Negative values charge the battery

# Automatic storage solar control defaults
DEFAULT_SOLAR_SURPLUS_ON_W: Final = 1400
DEFAULT_SOLAR_SURPLUS_OFF_W: Final = 1000
DEFAULT_SOLAR_SURPLUS_ON_MINUTES: Final = 2
DEFAULT_SOLAR_SURPLUS_OFF_MINUTES: Final = 5
SOLAR_CHECK_MAX_SECONDS: Final = 300
SOLAR_CHECK_COOLDOWN_SECONDS: Final = 600
SOLAR_CHARGE_CONFIRMATION_SECONDS: Final = 120
BATTERY_POWER_AVERAGE_SECONDS: Final = 120
BATTERY_POWER_THRESHOLD_W: Final = 100
SOLAR_DISCHARGE_ABORT_SECONDS: Final = 60
SOLAR_DISCHARGE_THRESHOLD_W: Final = 100

# Configurable local-time window for the automatic 500 W storage recharge.
DEFAULT_STORAGE_RECHARGE_START: Final = "22:00:00"
DEFAULT_STORAGE_RECHARGE_END: Final = "05:00:00"

# Solar-charging hysteresis. The phase is entered once the battery power
# average rises above BATTERY_POWER_THRESHOLD_W and is only left once charging
# has actually stopped. Using the entry threshold for both directions would
# leave no dead band and let an average hovering at 100 W flip the phase
# repeatedly.
SOLAR_CHARGING_EXIT_W: Final = 0

# Automatic winter controller day counters
STORAGE_OBSERVATION_DAYS: Final = 5
STORAGE_EXIT_FULL_CHARGE_DAYS: Final = 2
STORAGE_VALID_DAY_HOURS: Final = 20
STORAGE_FULL_CHARGE_ARM_SOC: Final = 95
STORAGE_FULL_CHARGE_SOC: Final = 99

# Internal storage phase to translated sensor state
STORAGE_PHASE_STATES: Final = {
    "charging": "storage_charging",
    "recharging": "storage_recharging",
    "holding": "storage_holding",
    "solar_check": "storage_solar_check",
    "solar_charging": "storage_solar_charging",
    "auto": "storage_discharging",
}

OPERATION_STATUS_STATES: Final = [
    "charging",
    "discharging",
    "standby",
    "mode_error",
    *STORAGE_PHASE_STATES.values(),
]

STORAGE_STATUS_STATES: Final = [
    "disabled",
    "observing",
    "full_charge_detected",
    *STORAGE_PHASE_STATES.values(),
]

# Sensors Configuration
# Sensors from ES.GetStatus (automatic updates)
SENSORS_BATTERY: Final = {
    "battery_state_of_charge": {
        "unit": "%",
        # Home Assistant selects the battery icon from the device class.
        "device_class": "battery",
        "state_class": "measurement",
        "attr": "bat_soc",
        "source": "auto",  # From ES.GetStatus
    },
    "battery_capacity": {
        "unit": "Wh",
        "icon": "mdi:battery-heart",
        "device_class": "energy",
        "attr": "bat_cap",
        "source": "auto",  # From ES.GetStatus
    },
}

# Sensors from the slower Bat.GetStatus poll.
SENSORS_BATTERY_MANUAL: Final = {
    "battery_temperature": {
        "unit": "°C",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "attr": "bat_temp",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_rated_capacity": {
        "unit": "Wh",
        "icon": "mdi:battery-heart",
        "device_class": "energy",
        "attr": "rated_capacity",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_voltage": {
        "unit": "V",
        "icon": "mdi:sine-wave",
        "device_class": "voltage",
        "state_class": "measurement",
        "attr": "bat_voltage",
        "source": "battery",
    },
    "battery_current": {
        "unit": "A",
        "icon": "mdi:current-dc",
        "device_class": "current",
        "state_class": "measurement",
        "attr": "bat_current",
        "source": "battery",
    },
    "battery_error_code": {
        "icon": "mdi:alert-circle-outline",
        "device_class": None,
        "attr": "error_code",
        "source": "battery",
    },
}

SENSORS_BATTERY_DERIVED: Final = {
    "solar_power": {
        "unit": "W",
        "icon": "mdi:solar-power",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_power": {
        "unit": "W",
        "icon": "mdi:battery-charging-medium",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_charge_power": {
        "unit": "W",
        "icon": "mdi:battery-arrow-up",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_discharge_power": {
        "unit": "W",
        "icon": "mdi:battery-arrow-down",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_available_capacity": {
        "unit": "Wh",
        "icon": "mdi:battery-plus",
        "device_class": "energy_storage",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
}

# Binary sensors from the slower Bat.GetStatus poll.
SENSORS_BATTERY_BINARY: Final = {
    "battery_charging": {
        "icon": "mdi:battery-charging",
        "device_class": "battery_charging",
        "attr": "charg_flag",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_discharging": {
        "icon": "mdi:battery-minus",
        "device_class": None,
        "attr": "dischrg_flag",
        "source": "battery",  # From Bat.GetStatus
    },
}

SENSORS_PV: Final = {
    "pv_power": {
        "unit": "W",
        "icon": "mdi:solar-power",
        "device_class": "power",
        "attr": "pv_power",  # Direct field from ES.GetStatus
    },
}

SENSORS_GRID: Final = {
    "grid_power": {
        "unit": "W",
        "icon": "mdi:transmission-tower",
        "device_class": "power",
        "state_class": "measurement",
        "attr": "ongrid_power",  # Direct field from ES.GetStatus
    },
    "offgrid_power": {
        "unit": "W",
        "icon": "mdi:power-off",
        "device_class": "power",
        "attr": "offgrid_power",  # Direct field from ES.GetStatus
    },
}

SENSORS_ENERGY: Final = {
    "total_pv_energy": {
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:solar-power-box",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_pv_energy",  # Direct field from ES.GetStatus
    },
    "total_grid_export_energy": {
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:transmission-tower-export",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_grid_output_energy",  # Direct field from ES.GetStatus
    },
    "total_grid_import_energy": {
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:transmission-tower-import",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_grid_input_energy",  # Direct field from ES.GetStatus
    },
    "total_load_energy": {
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:home-lightning-bolt",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_load_energy",  # Direct field from ES.GetStatus
    },
}

# CT meter sensors from the slower ES.GetMode poll.
SENSORS_CT: Final = {
    "phase_a_power": {
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "a_power",
        "source": "mode",  # From ES.GetMode
    },
    "phase_b_power": {
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "b_power",
        "source": "mode",  # From ES.GetMode
    },
    "phase_c_power": {
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "c_power",
        "source": "mode",  # From ES.GetMode
    },
    "ct_input_energy": {
        "unit": "Wh",
        "icon": "mdi:lightning-bolt-circle",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "input_energy",
        "source": "mode",  # From ES.GetMode - multiply by 0.1
    },
    "ct_output_energy": {
        "unit": "Wh",
        "icon": "mdi:lightning-bolt-circle",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "output_energy",
        "source": "mode",  # From ES.GetMode - multiply by 0.1
    },
    "total_ct_power": {
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "total_power",
        "source": "mode",  # From ES.GetMode
    },
    "ct_parse_state": {
        "icon": "mdi:meter-electric-outline",
        "device_class": None,
        "attr": "parse_state",
        "source": "mode",
    },
}

SENSORS_WIFI: Final = {
    "wifi_signal_strength": {
        "unit": "dBm",
        "icon": "mdi:wifi",
        "device_class": "signal_strength",
        "state_class": "measurement",
        "attr": "rssi",
        "source": "wifi",
    },
    "wifi_ssid": {
        "icon": "mdi:wifi-settings",
        "device_class": None,
        "attr": "ssid",
        "source": "wifi",
    },
    "wifi_ip_address": {
        "icon": "mdi:ip-network",
        "device_class": None,
        "attr": "sta_ip",
        "source": "wifi",
    },
    "wifi_gateway": {
        "icon": "mdi:router-network",
        "device_class": None,
        "attr": "sta_gate",
        "source": "wifi",
    },
    "wifi_subnet_mask": {
        "icon": "mdi:ip-network-outline",
        "device_class": None,
        "attr": "sta_mask",
        "source": "wifi",
    },
    "wifi_dns_server": {
        "icon": "mdi:dns",
        "device_class": None,
        "attr": "sta_dns",
        "source": "wifi",
    },
}

SENSORS_DEVICE: Final = {
    "device_model": {
        "icon": "mdi:battery-unknown",
        "device_class": None,
        "attr": "device",
        "source": "device",
    },
    "firmware_version": {
        "icon": "mdi:chip",
        "device_class": None,
        "attr": "ver",
        "source": "device",
    },
    "bluetooth_mac_address": {
        "icon": "mdi:bluetooth",
        "device_class": None,
        "attr": "ble_mac",
        "source": "device",
    },
    "wifi_mac_address": {
        "icon": "mdi:wifi-cog",
        "device_class": None,
        "attr": "wifi_mac",
        "source": "device",
    },
    "device_ip_address": {
        "icon": "mdi:ip",
        "device_class": None,
        "attr": "ip",
        "source": "device",
    },
}

# CT meter binary sensor from ES.GetMode
SENSORS_CT_BINARY: Final = {
    "ct_meter_connected": {
        "icon": "mdi:meter-electric",
        "device_class": "connectivity",
        "attr": "ct_state",
        "source": "mode",  # From ES.GetMode
    },
}

# Operating mode sensor from ES.GetMode
SENSORS_SYSTEM: Final = {
    "operating_mode": {
        "icon": "mdi:cog",
        "device_class": None,
        "attr": "mode",
        "source": "auto",  # Mode is added to main data by coordinator
    },
    "operation_status": {
        "icon": "mdi:battery-sync",
        "device_class": "enum",
        "options": OPERATION_STATUS_STATES,
        "translation_key": "operation_status",
        "attr": None,
        "source": "derived",
    },
    "storage_status": {
        "icon": "mdi:snowflake-alert",
        "device_class": "enum",
        "options": STORAGE_STATUS_STATES,
        "translation_key": "storage_status",
        "attr": None,
        "source": "derived",
    },
    "storage_observation_progress": {
        "icon": "mdi:calendar-clock",
        "device_class": None,
        "attr": None,
        "source": "derived",
    },
    "self_test": {
        "icon": "mdi:clipboard-pulse",
        "device_class": "enum",
        "options": ["ok", "warning", "error"],
        "translation_key": "self_test",
        "attr": None,
        "source": "derived",
    },
}

# Combine all sensors
ALL_SENSORS: Final = {
    **SENSORS_BATTERY,
    **SENSORS_BATTERY_MANUAL,
    **SENSORS_BATTERY_DERIVED,
    **SENSORS_PV,
    **SENSORS_GRID,
    **SENSORS_ENERGY,
    **SENSORS_CT,
    **SENSORS_WIFI,
    **SENSORS_DEVICE,
    **SENSORS_SYSTEM,
}

# Binary Sensors
# From manual API calls (Bat.GetStatus and ES.GetMode)
BINARY_SENSORS: Final = {
    **SENSORS_BATTERY_BINARY,
    **SENSORS_CT_BINARY,
    "bluetooth_connected": {
        "icon": "mdi:bluetooth-connect",
        "device_class": "connectivity",
        "attr": "state",
        "source": "ble",
    },
    "solar_surplus": {
        "icon": "mdi:solar-power-variant",
        "device_class": None,
        "translation_key": "solar_surplus",
        "attr": None,
        "source": "derived",
    },
    "integration_problem": {
        "icon": "mdi:alert-circle",
        "device_class": "problem",
        "translation_key": "integration_problem",
        "attr": None,
        "source": "derived",
    },
}

# Configuration Keys
CONF_IP_ADDRESS: Final = "ip_address"
CONF_PORT: Final = "port"
CONF_BLE_MAC: Final = "ble_mac"
CONF_FAST_SCAN_INTERVAL: Final = "fast_scan_interval"
CONF_MODE_SCAN_INTERVAL: Final = "mode_scan_interval"
CONF_ENABLED_MODES: Final = "enabled_modes"
CONF_SOLAR_POWER_ENTITY: Final = "solar_power_entity"
CONF_SOLAR_SURPLUS_ON_W: Final = "solar_surplus_on_w"
CONF_SOLAR_SURPLUS_OFF_W: Final = "solar_surplus_off_w"
CONF_SOLAR_SURPLUS_ON_MINUTES: Final = "solar_surplus_on_minutes"
CONF_SOLAR_SURPLUS_OFF_MINUTES: Final = "solar_surplus_off_minutes"
CONF_STORAGE_RECHARGE_START: Final = "storage_recharge_start"
CONF_STORAGE_RECHARGE_END: Final = "storage_recharge_end"
CONF_STORAGE_OBSERVATION_DAYS: Final = "storage_observation_days"
