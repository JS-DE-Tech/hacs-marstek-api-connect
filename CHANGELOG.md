# Changelog

## [2.6.0] - 2026-07-21

### Added
- Persistent Operating Mode setpoint with automatic restoration when physical `ES.GetMode` feedback differs.
- Five restore attempts at 30-second intervals and `Fehler Betriebsmodus` in the Status sensor after repeated failure.
- User-facing Standby mode implemented as a neutral 0 W Passive command.
- Persistent Manual power slider from -2400 W to +2400 W in 100 W steps.
- Three-sample Standby confirmation using a ±30 W Grid Power tolerance.

### Changed
- Remove Passive from the user-facing Operating Mode selector and expose Standby and Manual power instead.
- Use a firmware-compatible 300-second Passive countdown and renew it after 240 seconds.
- Preserve the Manual power slider value when switching to Standby.
- Keep physical Manual mode available for schedule services while the selector's Manual option controls direct power through Passive mode.

## [2.5.2] - 2026-07-21

### Fixed
- Add the `measurement` state class to Grid Power so it can be selected by Home Assistant statistics and battery power-flow configuration.
- Add the `measurement` state class to Battery State of Charge so it is accepted as the Energy Dashboard battery state-of-charge sensor.

## [2.5.1] - 2026-07-21

### Fixed
- Normalize IPv4 display values by removing leading zeroes from device IP, WiFi IP, gateway, subnet mask, and DNS addresses.

## [2.5.0] - 2026-07-21

### Added
- Battery voltage, current, error code, available capacity, normalized battery power, charge power, and discharge power sensors.
- WiFi signal, SSID, IP, gateway, subnet, and DNS diagnostic sensors.
- Device model, firmware, Bluetooth MAC, WiFi MAC, and device IP diagnostic sensors.
- CT parse-state sensor and Bluetooth connectivity binary sensor.

### Changed
- Poll static device, WiFi, Bluetooth, and detailed battery information once per hour.
- Normalize battery voltage and current from centi-units and fall back to Venus E 3.0 grid power when battery power is omitted.

## [2.4.0] - 2026-07-21

### Added
- Persistent `Automatic storage / winter operation` switch.
- Enter Storage after five valid consecutive calendar days whose maximum SOC stayed below 50 percent.
- Return to Auto after two valid consecutive Storage days reaching at least 99 percent SOC.
- Separate `Status-Lagerung` sensor for observation counters, storage phases, and detected full-charge days.
- Persist counters, current day maximum, and controller state across integration restarts.

### Changed
- Manual operating-mode selection disables automatic winter operation to prevent competing controls.
- Days with less than 20 hours of observations or non-consecutive dates do not count toward either threshold.
- Document the automatic-storage state machine, thresholds, persistence, entity states, polling intervals, and renamed integration domain in the README.

## [2.3.6] - 2026-07-21

### Changed
- Configure live energy/power and operating-mode/CT polling intervals separately in the integration options.
- Default live interval remains 10 seconds; mode/CT defaults to 60 seconds.
- Stop creating the three manual refresh button entities; automatic polling replaces them.

## [2.3.5] - 2026-07-21

### Changed
- Turn on the device LED only once after the first successful integration setup.
- Preserve the user's last LED choice on later Home Assistant restarts and integration reloads.

## [2.3.4] - 2026-07-21

### Changed
- Always turn on the device LED when the integration starts or reloads and reflect the confirmed state in the LED switch.
- Shorten the neutral operation status from `Standby - keine Ladung, keine Entladung` to `Standby`.

## [2.3.3] - 2026-07-21

### Changed
- Always disable the virtual storage mode and request `Auto` mode whenever the integration starts or reloads.
- Keep setup available and log a warning if the device does not confirm Auto mode during startup.

## [2.3.2] - 2026-07-21

### Fixed
- Derive charge/discharge status from `ongrid_power` when Venus E 3.0 firmware omits `bat_power`.
- Account for the Venus E 3.0 sign convention where negative on-grid power means charging and positive means discharging.

## [2.3.1] - 2026-07-21

### Added
- Status sensor updated every 10 seconds with `Standby - keine Ladung, keine Entladung`, `Laden`, `Entladen`, `Lagerung - Laden`, `Lagerung - Halten`, or `Lagerung - Entladen`.
- Use `bat_power` with a 10 W deadband for the normal charging state and the storage controller phase for storage states.

## [2.3.0] - 2026-07-21

### Added
- Options page for selecting which operating modes are displayed by the mode selector.
- Storage/winter mode with 45/50/55 percent hysteresis: charge at 500 W from 45 percent, hold at 50 percent, and use Auto above 55 percent until SOC returns to 50 percent.
- Restore an active storage mode after Home Assistant or the integration restarts.

## [2.2.3] - 2026-07-21

### Changed
- Poll `ES.GetStatus`, including grid power, every 10 seconds by default.
- Keep `ES.GetMode` and `EM.GetStatus` limited to once per minute and battery details to the existing slow interval.
- Configure the fast polling interval in seconds (10-300) through the integration options.

## [2.2.2] - 2026-07-21

### Fixed
- Prefer the `ct_state` reported by `EM.GetStatus` over the stale value from `ES.GetMode` when the energy meter is available.
- Validate the result of LED control commands.

### Changed
- Display LED control as a regular switch instead of an assumed-state two-button control.
- Restore the last LED state known to Home Assistant after an integration restart. The Marstek Open API does not provide a command for reading the physical LED state.

## [2.2.1] - 2026-07-21

### Fixed
- Prevented the operating-mode selector from immediately reverting to a stale value after a mode change.
- Validate `set_result` and confirm the selected mode with `ES.GetMode` after a short device processing delay.
- Report rejected mode changes to Home Assistant instead of silently accepting them.

### Changed
- Renamed the integration domain to `hacs_marstek_api_connect`.
- Added German setup, options, entity, and service translations.

All notable changes to the Marstek Venus E Home Assistant Integration will be documented in this file.

## [2.2.0] - 2026-04-12

### Added
- **LED Control**: Added a new `switch` entity to control the device panel LED (`Led.Ctrl`).
- **Assumed State**: Implemented assumed state for the LED switch since the API does not provide feedback on the current state.

### Removed
- **DOD Control**: Removed the `number` platform and `set_dod` service. API analysis confirmed that DOD is write-only and cannot be read, making it unreliable for a Home Assistant UI element.

### Changed
- **Improved Logging**: Service calls and switch actions now include the device IP address in the logs for better traceability.
- **Translations**: Updated English and French translation files for the new switch and cleaned up removed services.
- **Manifest Update**: Added `switch` to the supported platforms list.

## [2.1.0] - 2026-04-11

### Fixed
- **Power Limit Correction**: Updated battery charging/discharging power limit from 800W to 2500W to match device capabilities
- **Service Validation**: Updated all service schemas in `services.yaml` to allow power values up to 2500W
- **Documentation Update**: Corrected README.md and test files to reflect the proper 100-2500W power range

### Technical Details
- Updated `services.yaml` power selectors: `max: 2500` for all manual schedule slots
- Corrected documentation in README.md examples and constraints
- Updated test files to reflect proper power range validation
- Updated copilot instructions for accurate API documentation

## [2.0.0] - 2026-04-11

### Added
- **Differentiated Update Intervals**: Implemented separate scan intervals for different data sources:
  - **ES (Energy System)**: Updated every 30 seconds for real-time energy monitoring (ES.GetStatus, ES.GetMode, EM.GetStatus)
  - **Bat (Battery)**: Updated every 10 minutes to reduce device battery drain while keeping status available

- **Battery Sensors Available**: Re-enabled battery-related sensors with optimized update frequency:
  - `sensor.marstek_venus_e_battery_temperature` - Updates every 10 minutes
  - `sensor.marstek_venus_e_battery_rated_capacity` - Updates every 10 minutes
  - `binary_sensor.marstek_venus_e_battery_charging` - Updates every 10 minutes
  - `binary_sensor.marstek_venus_e_battery_discharging` - Updates every 10 minutes

### Fixed
- **Phase Power Data (Phase A/B/C) - Critical Fix**: 
  - Fixed incorrect zero values being reported for phase power sensors
  - Implemented intelligent data source merging between ES.GetMode and EM.GetStatus
  - EM.GetStatus now takes precedence for CT power fields when ES.GetMode returns zeros
  - `sensor.marstek_venus_e_phase_b_power` now correctly reports actual power values (e.g., 463W instead of 0W)

- **Power Limit Correction**: Updated battery charging/discharging power limit from 800W to 2500W to match device capabilities
- **Service Validation**: Updated all service schemas in `services.yaml` to allow power values up to 2500W
- **Documentation Update**: Corrected README.md and test files to reflect the proper 100-2500W power range

### Technical Details
- Updated `services.yaml` power selectors: `max: 2500` for all manual schedule slots
- Corrected documentation in README.md examples and constraints
- Updated test files to reflect proper power range validation
- Updated copilot instructions for accurate API documentation

## [1.1.0] - 2026-01-15

### Added
- **API Rev 2.0 Support**: Updated integration to support all commands from Marstek Device Open API Rev 2.0 (2026-01-06)
- **ES.GetMode Data**: Now retrieves and displays all operating mode data including:
  - Current operating mode (Auto, AI, Manual, Passive, UPS)
  - Grid-tied power and off-grid power
  - Battery state of charge
  - CT (Current Transformer) status (0: Not connected, 1: Connected)
  - CT Phase A, B, C power readings [W]
  - Total CT power [W]
  - Cumulative input energy [Wh] (*0.1 scaling applied)
  - Cumulative output energy [Wh] (*0.1 scaling applied)

- **EM.GetStatus Support**: Added energy meter status queries for additional CT meter data (when available)

- **New Sensors**:
  - CT Input Energy (from ES.GetMode) - cumulative input energy measurement
  - CT Output Energy (from ES.GetMode) - cumulative output energy measurement

- **New Services**:
  - `marstek_venus_e.set_dod`: Configure battery depth of discharge (30-88%)
  - `marstek_venus_e.set_ble_adv`: Enable/disable Bluetooth advertising
  - `marstek_venus_e.set_led_ctrl`: Control the device LED (on/off)

- **Enhanced Data Retrieval**:
  - Coordinator now retrieves both ES.GetMode and EM.GetStatus in parallel with main status
  - Automatic energy value scaling (*0.1) for API compliance
  - Added fallback mechanism for optional EM.GetStatus when unavailable

### Changed
- **API Timeout**: Increased from 20s to 30s to comply with API specification requirements
- **UDP Request Spacing**: Added constant for 30-second minimum time between requests per API guidelines
- **Error Handling**: Improved error logging with distinction between fatal and non-fatal failures
- **Data Update Strategy**: Mode and meter data are now collected on every coordinator update cycle

### Fixed
- **Full ES.GetMode Data Now Available**: Previously, ES.GetMode data was being fetched but not all fields were properly utilized
- **Energy Value Scaling**: Cumulative energy values from ES.GetMode are now correctly scaled by 0.1 as per API documentation
- **Mode Data Persistence**: Mode data is now properly merged and persisted through coordinator updates

### Technical Details
- Updated DEFAULT_TIMEOUT from 20.0s to 30.0s
- Added MIN_TIME_BETWEEN_REQUESTS constant (30.0s)
- Enhanced coordinator's _async_update_data() to handle multiple optional data sources
- New const.py entries for DOD configuration (DOD_MIN, DOD_MAX, DOD_DEFAULT)
- Added proper docstrings for all new API methods

### Developer Notes
- All UDP requests now include proper debug logging of payloads and responses
- Error messages distinguish between timeout errors (debug level) and other errors (error level)
- DoD values validate range 30-88 before sending to device
- Ble.Adv uses inverted logic: enable=0 (enable), enable=1 (disable) per API spec
- Led.Ctrl: state=1 (on), state=0 (off)

## [1.0.0] - 2025-11-20

### Initial Release
- Full integration with Marstek Venus E battery storage system
- Real-time battery, solar PV, and grid monitoring
- Operating mode control (Auto, AI, Manual, Passive)
- Manual schedule configuration for charging/discharging
- Energy dashboard integration
- Multi-language support (English, French)
- UDP JSON-RPC communication with device
- Automatic device discovery
- Support for current transformer (CT) meter sensors

### Features
- Comprehensive sensor suite (battery status, PV power, grid power, energy totals)
- Binary sensors for charging/discharging status and CT meter connection
- Operating mode selection entity
- Multiple configuration options
- Service-based control for mode changes and schedule management
