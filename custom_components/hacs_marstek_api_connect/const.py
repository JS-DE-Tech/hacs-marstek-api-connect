"""Constants for the Marstek Venus E integration."""
from typing import Final

DOMAIN: Final = "hacs_marstek_api_connect"

# Device Configuration
DEFAULT_PORT: Final = 30000
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds (fast ES.GetStatus polling)
DEFAULT_TIMEOUT: Final = 30.0  # seconds - UDP request timeout (API requires 30s)
MIN_TIME_BETWEEN_REQUESTS: Final = 30.0  # seconds - minimum time between UDP requests per API spec

# Modes
MODE_AUTO: Final = "Auto"
MODE_AI: Final = "AI"
MODE_MANUAL: Final = "Manual"
MODE_PASSIVE: Final = "Passive"
MODE_STORAGE: Final = "Storage"

VALID_MODES: Final = [MODE_AUTO, MODE_AI, MODE_MANUAL, MODE_PASSIVE]
SELECTABLE_MODES: Final = [*VALID_MODES, MODE_STORAGE]

# Storage/winter mode thresholds
STORAGE_CHARGE_START_SOC: Final = 45
STORAGE_TARGET_SOC: Final = 50
STORAGE_AUTO_START_SOC: Final = 55
STORAGE_CHARGE_POWER: Final = -500  # Negative values charge the battery

# API Methods
API_GET_REALTIME_DATA: Final = "get_realtime_data"
API_GET_BATTERY_INFO: Final = "get_battery_info"
API_SET_MODE: Final = "set_mode"
API_SET_MANUAL_SCHEDULE: Final = "set_manual_schedule"
API_SET_PASSIVE_MODE: Final = "set_passive_mode"
API_GET_SCHEDULE: Final = "get_schedule"

# Battery Attributes
ATTR_BATTERY_SOC: Final = "battery_soc"
ATTR_BATTERY_TEMPERATURE: Final = "battery_temperature"
ATTR_BATTERY_CAPACITY: Final = "battery_capacity"
ATTR_BATTERY_RATED_CAPACITY: Final = "battery_rated_capacity"
ATTR_BATTERY_POWER: Final = "battery_power"
ATTR_BATTERY_CHARGING: Final = "battery_charging"
ATTR_BATTERY_DISCHARGING: Final = "battery_discharging"

# PV Attributes
ATTR_PV_POWER: Final = "pv_power"
ATTR_PV_VOLTAGE: Final = "pv_voltage"
ATTR_PV_CURRENT: Final = "pv_current"

# Grid Attributes
ATTR_GRID_POWER: Final = "grid_power"
ATTR_OFFGRID_POWER: Final = "offgrid_power"

# Energy Attributes
ATTR_TOTAL_PV_ENERGY: Final = "total_pv_energy"
ATTR_TOTAL_GRID_EXPORT_ENERGY: Final = "total_grid_export_energy"
ATTR_TOTAL_GRID_IMPORT_ENERGY: Final = "total_grid_import_energy"
ATTR_TOTAL_LOAD_ENERGY: Final = "total_load_energy"

# CT Meter Attributes
ATTR_PHASE_A_POWER: Final = "phase_a_power"
ATTR_PHASE_B_POWER: Final = "phase_b_power"
ATTR_PHASE_C_POWER: Final = "phase_c_power"
ATTR_TOTAL_CT_POWER: Final = "total_ct_power"
ATTR_CT_METER_CONNECTED: Final = "ct_meter_connected"

# WiFi Attributes
ATTR_WIFI_SIGNAL_STRENGTH: Final = "wifi_signal_strength"
ATTR_WIFI_SSID: Final = "wifi_ssid"

# Operating Mode
ATTR_OPERATING_MODE: Final = "operating_mode"

# CT Energy Attributes (from ES.GetMode/EM.GetStatus)
ATTR_CT_INPUT_ENERGY: Final = "ct_input_energy"
ATTR_CT_OUTPUT_ENERGY: Final = "ct_output_energy"

# Sensors Configuration
# Sensors from ES.GetStatus (automatic updates)
SENSORS_BATTERY: Final = {
    "battery_state_of_charge": {
        "name": "Battery State of Charge",
        "unit": "%",
        #"icon": "mdi:battery-percent",
        "device_class": "battery",
        "state_class": "measurement",
        "attr": "bat_soc",
        "source": "auto",  # From ES.GetStatus
    },
    "battery_capacity": {
        "name": "Battery Capacity",
        "unit": "Wh",
        "icon": "mdi:battery-heart",
        "device_class": "energy",
        "attr": "bat_cap",
        "source": "auto",  # From ES.GetStatus
    },
}

# Sensors from Bat.GetStatus (manual refresh button)
SENSORS_BATTERY_MANUAL: Final = {
    "battery_temperature": {
        "name": "Battery Temperature",
        "unit": "°C",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "attr": "bat_temp",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_rated_capacity": {
        "name": "Battery Rated Capacity",
        "unit": "Wh",
        "icon": "mdi:battery-heart",
        "device_class": "energy",
        "attr": "rated_capacity",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_voltage": {
        "name": "Battery Voltage",
        "unit": "V",
        "icon": "mdi:sine-wave",
        "device_class": "voltage",
        "state_class": "measurement",
        "attr": "bat_voltage",
        "source": "battery",
    },
    "battery_current": {
        "name": "Battery Current",
        "unit": "A",
        "icon": "mdi:current-dc",
        "device_class": "current",
        "state_class": "measurement",
        "attr": "bat_current",
        "source": "battery",
    },
    "battery_error_code": {
        "name": "Battery Error Code",
        "icon": "mdi:alert-circle-outline",
        "device_class": None,
        "attr": "error_code",
        "source": "battery",
    },
}

SENSORS_BATTERY_DERIVED: Final = {
    "battery_power": {
        "name": "Battery Power",
        "unit": "W",
        "icon": "mdi:battery-charging-medium",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_charge_power": {
        "name": "Battery Charge Power",
        "unit": "W",
        "icon": "mdi:battery-arrow-up",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_discharge_power": {
        "name": "Battery Discharge Power",
        "unit": "W",
        "icon": "mdi:battery-arrow-down",
        "device_class": "power",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
    "battery_available_capacity": {
        "name": "Battery Available Capacity",
        "unit": "Wh",
        "icon": "mdi:battery-plus",
        "device_class": "energy_storage",
        "state_class": "measurement",
        "attr": None,
        "source": "derived",
    },
}

# Binary sensors from Bat.GetStatus (manual refresh button)
SENSORS_BATTERY_BINARY: Final = {
    "battery_charging": {
        "name": "Battery Charging",
        "icon": "mdi:battery-charging",
        "device_class": "battery_charging",
        "attr": "charg_flag",
        "source": "battery",  # From Bat.GetStatus
    },
    "battery_discharging": {
        "name": "Battery Discharging",
        "icon": "mdi:battery-minus",
        "device_class": None,
        "attr": "dischrg_flag",
        "source": "battery",  # From Bat.GetStatus
    },
}

SENSORS_PV: Final = {
    "pv_power": {
        "name": "PV Power",
        "unit": "W",
        "icon": "mdi:solar-power",
        "device_class": "power",
        "attr": "pv_power",  # Direct field from ES.GetStatus
    },
}

SENSORS_GRID: Final = {
    "grid_power": {
        "name": "Grid Power",
        "unit": "W",
        "icon": "mdi:transmission-tower",
        "device_class": "power",
        "state_class": "measurement",
        "attr": "ongrid_power",  # Direct field from ES.GetStatus
    },
    "offgrid_power": {
        "name": "Off-Grid Power",
        "unit": "W",
        "icon": "mdi:power-off",
        "device_class": "power",
        "attr": "offgrid_power",  # Direct field from ES.GetStatus
    },
}

SENSORS_ENERGY: Final = {
    "total_pv_energy": {
        "name": "Total PV Energy",
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:solar-power-box",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_pv_energy",  # Direct field from ES.GetStatus
    },
    "total_grid_export_energy": {
        "name": "Total Grid Export Energy",
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:transmission-tower-export",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_grid_output_energy",  # Direct field from ES.GetStatus
    },
    "total_grid_import_energy": {
        "name": "Total Grid Import Energy",
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:transmission-tower-import",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_grid_input_energy",  # Direct field from ES.GetStatus
    },
    "total_load_energy": {
        "name": "Total Load Energy",
        "unit": "Wh",  # Device returns Wh, not kWh
        "icon": "mdi:home-lightning-bolt",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "total_load_energy",  # Direct field from ES.GetStatus
    },
}

# CT meter sensors from ES.GetMode (manual refresh button)
SENSORS_CT: Final = {
    "phase_a_power": {
        "name": "Phase A Power",
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "a_power",
        "source": "mode",  # From ES.GetMode
    },
    "phase_b_power": {
        "name": "Phase B Power",
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "b_power",
        "source": "mode",  # From ES.GetMode
    },
    "phase_c_power": {
        "name": "Phase C Power",
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "c_power",
        "source": "mode",  # From ES.GetMode
    },
    "ct_input_energy": {
        "name": "CT Input Energy",
        "unit": "Wh",
        "icon": "mdi:lightning-bolt-circle",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "input_energy",
        "source": "mode",  # From ES.GetMode - multiply by 0.1
    },
    "ct_output_energy": {
        "name": "CT Output Energy",
        "unit": "Wh",
        "icon": "mdi:lightning-bolt-circle",
        "device_class": "energy",
        "state_class": "total_increasing",
        "attr": "output_energy",
        "source": "mode",  # From ES.GetMode - multiply by 0.1
    },
    "total_ct_power": {
        "name": "Total CT Power",
        "unit": "W",
        "icon": "mdi:lightning-bolt",
        "device_class": "power",
        "attr": "total_power",
        "source": "mode",  # From ES.GetMode
    },
    "ct_parse_state": {
        "name": "CT Parse State",
        "icon": "mdi:meter-electric-outline",
        "device_class": None,
        "attr": "parse_state",
        "source": "mode",
    },
}

SENSORS_WIFI: Final = {
    "wifi_signal_strength": {
        "name": "WiFi Signal Strength",
        "unit": "dBm",
        "icon": "mdi:wifi",
        "device_class": "signal_strength",
        "state_class": "measurement",
        "attr": "rssi",
        "source": "wifi",
    },
    "wifi_ssid": {
        "name": "WiFi SSID",
        "icon": "mdi:wifi-settings",
        "device_class": None,
        "attr": "ssid",
        "source": "wifi",
    },
    "wifi_ip_address": {
        "name": "WiFi IP Address",
        "icon": "mdi:ip-network",
        "device_class": None,
        "attr": "sta_ip",
        "source": "wifi",
    },
    "wifi_gateway": {
        "name": "WiFi Gateway",
        "icon": "mdi:router-network",
        "device_class": None,
        "attr": "sta_gate",
        "source": "wifi",
    },
    "wifi_subnet_mask": {
        "name": "WiFi Subnet Mask",
        "icon": "mdi:ip-network-outline",
        "device_class": None,
        "attr": "sta_mask",
        "source": "wifi",
    },
    "wifi_dns_server": {
        "name": "WiFi DNS Server",
        "icon": "mdi:dns",
        "device_class": None,
        "attr": "sta_dns",
        "source": "wifi",
    },
}

SENSORS_DEVICE: Final = {
    "device_model": {
        "name": "Device Model",
        "icon": "mdi:battery-unknown",
        "device_class": None,
        "attr": "device",
        "source": "device",
    },
    "firmware_version": {
        "name": "Firmware Version",
        "icon": "mdi:chip",
        "device_class": None,
        "attr": "ver",
        "source": "device",
    },
    "bluetooth_mac_address": {
        "name": "Bluetooth MAC Address",
        "icon": "mdi:bluetooth",
        "device_class": None,
        "attr": "ble_mac",
        "source": "device",
    },
    "wifi_mac_address": {
        "name": "WiFi MAC Address",
        "icon": "mdi:wifi-cog",
        "device_class": None,
        "attr": "wifi_mac",
        "source": "device",
    },
    "device_ip_address": {
        "name": "Device IP Address",
        "icon": "mdi:ip",
        "device_class": None,
        "attr": "ip",
        "source": "device",
    },
}

# CT meter binary sensor from ES.GetMode
SENSORS_CT_BINARY: Final = {
    "ct_meter_connected": {
        "name": "CT Meter Connected",
        "icon": "mdi:meter-electric",
        "device_class": "connectivity",
        "attr": "ct_state",
        "source": "mode",  # From ES.GetMode
    },
}

# Operating mode sensor from ES.GetMode
SENSORS_SYSTEM: Final = {
    "operating_mode": {
        "name": "Operating Mode",
        "icon": "mdi:cog",
        "device_class": None,
        "attr": "mode",
        "source": "auto",  # Mode is added to main data by coordinator
    },
    "operation_status": {
        "name": "Status",
        "icon": "mdi:battery-sync",
        "device_class": None,
        "attr": None,
        "source": "derived",
    },
    "storage_status": {
        "name": "Status-Lagerung",
        "icon": "mdi:snowflake-alert",
        "device_class": None,
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
        "name": "Bluetooth Connected",
        "icon": "mdi:bluetooth-connect",
        "device_class": "connectivity",
        "attr": "state",
        "source": "ble",
    },
}

# Week Set Bitmask
WEEK_SET_MONDAY: Final = 1
WEEK_SET_TUESDAY: Final = 2
WEEK_SET_WEDNESDAY: Final = 4
WEEK_SET_THURSDAY: Final = 8
WEEK_SET_FRIDAY: Final = 16
WEEK_SET_SATURDAY: Final = 32
WEEK_SET_SUNDAY: Final = 64
WEEK_SET_ALL_DAYS: Final = 127
WEEK_SET_WEEKDAYS: Final = 31
WEEK_SET_WEEKEND: Final = 96

# Configuration Keys
CONF_IP_ADDRESS: Final = "ip_address"
CONF_PORT: Final = "port"
CONF_BLE_MAC: Final = "ble_mac"
CONF_TIMEOUT: Final = "timeout"
CONF_FAST_SCAN_INTERVAL: Final = "fast_scan_interval"
CONF_MODE_SCAN_INTERVAL: Final = "mode_scan_interval"
CONF_ENABLED_MODES: Final = "enabled_modes"
