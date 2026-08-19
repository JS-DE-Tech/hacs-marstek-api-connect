# Changelog

## [2.8.0] - 2026-08-19

### Breaking
- `Status` and `Storage status` are now enum sensors with translated states.
  Their raw states changed from German text (`Laden`, `Lagerung - Halten`,
  `Fehler Betriebsmodus`, ...) to language-independent keys (`charging`,
  `storage_holding`, `mode_error`, ...). Automations or dashboard cards that
  compare these sensors against the old German strings must be updated. Entity
  IDs are unchanged.
- The day counters that used to be part of the `Storage status` text are now
  attributes: `low_soc_days`, `low_soc_days_required`, `full_soc_days` and
  `full_soc_days_required`.
- The `Operating mode` select now exposes lowercase option keys (`auto`, `ai`,
  `standby`, `manual`, `schedule`, `storage`) so Home Assistant can translate
  their visible labels. Automations using `select.select_option` must use the
  lowercase option key. The `set_mode` service and device protocol values are
  unchanged.
- Remove the redundant `set_passive_mode` and `change_operating_mode` services.
  Use the persistent `set_mode` service, Manual power slider and
  `set_manual_schedule` service instead.

### Added
- Separate `Observation progress` sensor showing the current automatic-storage
  observation counter as `0/5` through `5/5`.
- GitHub Actions validation for the regression suite, Python compilation, HACS
  repository rules and Home Assistant hassfest, plus weekly Dependabot updates
  for versioned workflow actions.
- A separate persistent `Schedule` operating mode that maps to the physical
  Marstek Manual mode, while `Manual` remains the direct Passive power target.
- `Self-test` sensor (OK / Warning / Error) with per-check details as
  attributes: device connectivity, setpoint supervision, Passive renewal age,
  mode deviations of the last 24 hours, solar-sensor validity and winter
  day-tracking gaps.
- `Problem` binary sensor (device class `problem`) that turns on while a
  self-test reports `error`, ready for notification automations.
- Mode-deviation incidents are deduplicated per continuous incident and
  survive restarts for 24 hours.
- Unit tests for the solar-charging state machine, incident deduplication and
  translation completeness of every enum sensor state.
- Regression tests for power/status normalization, IPv4 cleanup,
  time-weighted solar averages, weekday masks, UDP request serialization and
  cleanup, device RPC payloads, schedule fallback, discovery targets,
  duplicate packets, metadata and complete translation placeholders.

### Fixed
- Distinguish the persistent `Target operating mode` select from the physical
  `Operating mode` feedback sensor.
- Show the same translated operating-mode labels in the select entity and the
  available-modes configuration form.
- Set dynamic translation keys before entity initialization and stop overriding
  translated entity names with an explicit null name. Sensors, binary sensors,
  Operating Mode and Clear Schedules now show their individual translated names
  instead of only the device name.
- Start discovery immediately instead of showing a non-functional Continue
  checkbox, and build the device selector from one consistent option format so
  Home Assistant no longer returns an unknown setup error after discovery.
- Pass current HACS and Home Assistant hassfest metadata and translation
  validation. Schedule-direction selectors now use lowercase IDs while the
  service schema keeps accepting the former title-case values for compatibility.
- Ignore duplicate or late UDP response datagrams after a request has already
  completed, preventing `InvalidStateError` on devices or networks that deliver
  the same packet more than once.
- Reject schedule slot numbers outside 0–9 instead of silently sending an
  unchanged schedule to the device.
- Keep restore incidents and their attempt counter active until a later regular
  `ES.GetMode` poll confirms that the device retained the requested mode.
  Standby confirmation now uses three consecutive fast ±30 W samples instead
  of samples taken only during the slower supervision cycle.
- Serialize UDP requests per device and close every datagram transport in a
  `finally` block, including the final timeout path.
- Remove the stale `set_dod` service declaration, obsolete manual-refresh
  button implementations and their unused coordinator helpers.
- Renew persistent Standby/Manual Passive commands on the fast update cycle
  (renewal after 300 seconds, countdown 600 seconds). The renewal was
  previously gated behind the two-minute supervision interval and the
  three-sample Standby confirmation, so the 300-second countdown always
  expired and the device cyclically fell out of Standby.
- Mode supervision and winter-storage control no longer stop permanently after
  five failed restore attempts; they keep retrying every 30 minutes and reset
  automatically once the device confirms the setpoint again.
- Reset the shared restore backoff on every controller transition (manual
  Storage on/off, automatic winter switch, observation/storage changes), so a
  pending retry delay from the previous controller cannot postpone the first
  storage action by up to 30 minutes.
- Restore the dead band between the solar-charging phase and Auto. The phase is
  entered above +100 W average battery power and left at 0 W or below, so an
  average hovering at the entry threshold no longer flips the phase and resends
  redundant Auto commands.
- Apply the persistent confirmation policy to Storage phases as well. Repeated
  device dropbacks now accumulate across accepted writes and clear only after a
  later regular `ES.GetMode` poll confirms the requested phase.
- Preserve retry state across a failed Storage phase transition and commit
  phase timers/cooldowns only after the required physical command succeeds.
- Validate restored winter-controller states, counters, SOC values and tracking
  timestamps before using persisted data.
- Continue supervising and renewing the active Storage command while SOC data
  is temporarily unavailable; only phase transitions wait for valid SOC.

### Changed
- Remove stale development instructions, unused imports, constants and legacy
  UDP-client aliases. Keep sensor display names in the translation files only,
  replace duplicated port literals with the shared default and normalize the
  Python formatting without changing entity IDs or runtime behavior.
- Complete and align all German and English setup, options, entity, selector,
  service and error translations. Remove the incomplete French translation so
  Home Assistant no longer mixes translated and English fallback labels.
- Define the complete manual and automatic Storage transition tables as pure,
  tested state functions. Logical solar transitions that share physical Auto no
  longer resend an identical command, while changes between -500 W charging,
  0 W holding and Auto still apply immediately.
- Route service mode changes through the same persistent setpoint logic as the
  Operating Mode selector. Schedule changes no longer leave the device in a
  different mode, and every service requires explicit `config_entry_id`
  targeting so automations remain deterministic with multiple devices.
- Keep the LED switch synchronized when the LED service is called and surface
  rejected service commands as Home Assistant errors instead of logging and
  silently succeeding.
- Rename the `Solar Surplus` binary sensor to `Solar Output` and translate it,
  the self-test and both status sensors into English and German. The
  existing entity identity is retained for dashboard and automation
  compatibility.
- Raise the failed mode-selection error as a translated exception instead of a
  hardcoded German message.
- Supervise the persistent Auto setpoint during the observation phase of the
  automatic winter controller as well, so external app changes are corrected.
- The Operating Mode selector dynamically includes Storage while the winter
  controller holds the battery, even when Storage is not part of the
  configured mode list.
- Persist distinct operating-mode dropout incidents for 24 hours across
  integration reloads and Home Assistant restarts.

## [2.7.0] - 2026-07-23

### Added
- Configurable Home Assistant solar-power source with separate turn-on and
  turn-off thresholds and time-weighted averaging periods.
- Solar Power sensor and Solar Surplus binary sensor.
- Automatic-winter phases for solar testing and confirmed solar charging.
- Ten-minute cooldown after an unsuccessful five-minute solar test.
- Winter-phase device-mode confirmation and automatic correction.

### Changed
- Use normalized Battery Power as the primary charge/discharge signal with a
  +/-100 W deadband.
- Renew 0 W and 500 W Passive storage commands with a firmware-compatible
  300-second countdown.
- Count a full-charge day only after a real solar-assisted charge from 95% or
  below to at least 99%.
- Restore the persisted automatic-winter phase safely after integration reloads.
- Check persistent normal operating modes every two minutes and require physical
  `ES.GetMode` confirmation after correction.

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
