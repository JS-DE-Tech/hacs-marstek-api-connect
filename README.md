# Marstek Venus E for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-marstek-api-connect/main/docs/images/marstek-venus-e.png"
       alt="Marstek Venus E battery storage system"
       width="420">
</p>

Home Assistant integration for Marstek Venus E battery storage systems using the local UDP JSON-RPC API.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
[![Validate](https://github.com/JS-DE-Tech/hacs-marstek-api-connect/actions/workflows/validate.yml/badge.svg)](https://github.com/JS-DE-Tech/hacs-marstek-api-connect/actions/workflows/validate.yml)
[![Protocol](https://img.shields.io/badge/Protocol-Local%20UDP-success)](#api-reference)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](https://github.com/JS-DE-Tech/hacs-marstek-api-connect/blob/main/LICENSE)
[![Support via PayPal](https://img.shields.io/badge/Support%20via-PayPal-0070BA?logo=paypal&logoColor=white)](https://paypal.me/JensSaffrich)

Local Home Assistant HACS custom integration for the **Marstek Venus E**, including
the Venus E 3.0. It communicates directly with the battery over the LAN without a
cloud connection and provides local monitoring, operating-mode control, manual
schedules and automatic storage/winter operation. The official Marstek app can
continue to be used in parallel.

## Features

- Local UDP communication without a cloud dependency
- Automatic discovery with manual IP configuration as a fallback
- Battery, power, energy and three-phase CT monitoring
- User-facing operating modes: Auto, AI, Standby, Manual power, Schedule and Storage/Winter
- Configurable list of modes shown in the operating-mode selector
- Ten configurable manual schedule slots
- Automatic storage/winter controller with configurable solar-output detection
- Separate live-data and mode/CT polling intervals
- LED control as a regular Home Assistant switch
- Complete German and English translations
- Native Home Assistant services for automations

Default polling intervals:

- Energy and live power data: **10 seconds**
- Operating mode and CT data: **60 seconds**

Both intervals can be changed in the integration options.

## Persistent operating-mode control

The **Operating Mode** selector is a persistent setpoint. The separate operating-
mode sensor remains the physical feedback reported by `ES.GetMode`.

- **Standby** sends a neutral 0 W Passive command.
- **Manual** sends the value stored by the **Manual power** slider.
- **Schedule** activates the physical Marstek Manual mode and therefore the
  configured schedule slots.
- The slider ranges from -2400 W to +2400 W in 100 W steps.
- Negative values charge; positive values discharge.
- Selecting Standby does not change the stored slider value.
- Changing the slider while Manual is active applies the new value immediately.

The Venus E 3.0 requires a finite Passive countdown. Standby and Manual therefore
use a 600-second command that the integration renews after 300 seconds. The
renewal runs on the fast update cycle, so the countdown can never expire between
the slower supervision checks.

If physical feedback differs from the persistent setpoint, the integration checks
it every two minutes and tries to restore it. A write is not considered stable
until a later regular `ES.GetMode` poll still reports the requested mode. Standby
additionally requires three consecutive fast Grid Power samples within ±30 W.
Recurring dropbacks therefore continue the same restore counter. After five
failed correction cycles, the regular Status sensor reports the `mode_error`
state and the integration keeps retrying every 30 minutes until the device
confirms the setpoint again. Selecting a mode also resets the error and retry
counter immediately.

Storage and automatic winter operation manage their own internal mode changes and
temporarily take priority over the normal setpoint. Their physical commands use
the same supervision rule: an immediate response is not considered stable until
a later regular `ES.GetMode` poll confirms it. Repeated storage-mode dropbacks
therefore also lead to `mode_error` after five correction attempts.

## Manual Storage mode

Selecting **Storage** directly uses a self-contained 45/50/55% hysteresis:

- At or below 45%, charging at 500 W starts and remains active until 50%.
- At or above 55%, Auto starts and remains active until the battery returns to
  50%.
- When neither active transition applies, a renewed 0 W Passive command holds
  the battery.

The active phase is retained inside the hysteresis, preventing repeated mode
changes around a threshold.

## Automatic storage / winter operation

Enable the **Automatic storage / winter operation** switch to manage seasonal
storage without fixed calendar dates.

1. While the battery is in Auto mode, the integration records the highest state
   of charge reached each calendar day.
2. Storage mode starts after the configured number of consecutive valid days
   whose maximum state of charge remained below 50% (default: five days).
3. A day is valid when at least 20 hours elapsed between its first and last
   observation. Missing or non-consecutive days reset the current sequence.
4. During the day, a battery below 50% remains at a renewed 0 W Passive target
   while the controller waits for usable solar output. Grid-assisted charging
   is restricted to the configurable **Storage recharge period** (default:
   22:00–05:00 local time), in which recharging starts at or below 45% and continues at 500 W until 50%.
   Both recharge thresholds are configurable; start must be lower than stop.
   Recharging stops at the end of the window even if the stop SOC is not reached.
   These settings apply to automatic recharge; the automatic winter reserve follows the stop threshold.
5. A configured Home Assistant solar-power entity is evaluated with
   time-weighted moving averages. The default hysteresis detects surplus at a
   two-minute average of at least 1400 W and clears it at a five-minute average
   below 1000 W.
6. Detected surplus starts a five-minute Auto-mode solar test even when SOC is
   below 50%. A two-minute average Battery Power above +100 W confirms charging.
7. Solar testing or charging ends if solar output clears, charging stops, or the
   battery continuously discharges by more than 100 W for 60 seconds. A stopped
   solar cycle has a ten-minute cooldown before another test may start.
8. After a solar cycle, every SOC above 50%—up to and including 100%—remains
   in Auto and may use stored energy down to 50%; at 50% it returns to 0 W
   Passive holding.
9. A full-charge day requires confirmed solar charging from 95% or below to at
   least 99%. After two consecutive valid full-charge days, the controller
   returns to Auto observation and restarts the five-day counter.

Controller state and daily counters are stored by Home Assistant and survive
integration reloads and restarts. Selecting an operating mode manually disables
automatic storage to prevent competing commands.

Configure the solar source under **Configure → Configure solar output**. The
source must be a Home Assistant power sensor using W or kW. If it is missing,
unknown, unavailable, or has an unsupported unit, surplus is false and no new
solar test starts. The solar entities remain informational outside automatic
winter operation.

Configure the nightly fallback under **Configure → Configure storage recharge
period**. Start and end are interpreted in Home Assistant's local time and may
span midnight. The same form configures the number of observation days before
Storage starts. When both times are equal, the form rejects the configuration.

The **Storage status** sensor reports one of these states, which Home Assistant
shows in the user's language:

- `disabled`
- `observing`
- `storage_charging`
- `storage_recharging`
- `storage_holding`
- `storage_solar_check`
- `storage_solar_charging`
- `storage_discharging`
- `full_charge_detected`

The separate **Observation progress** sensor shows the current observation
counter, for example `0/5` through `5/5` with the default setting. The detailed
counters also remain
available as attributes of **Storage status**: `low_soc_days`,
`low_soc_days_required`, `full_soc_days`, `full_soc_days_required` and the
internal `storage_phase`.

The regular **Status** sensor reports `standby`, `charging`, `discharging`,
`mode_error`, or the current `storage_*` phase.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Open the menu in the upper-right corner and select **Custom repositories**.
3. Add `https://github.com/JS-DE-Tech/hacs-marstek-api-connect` as an
   **Integration** repository.
4. Find **Marstek Venus E** in HACS and select **Download**.
5. Restart Home Assistant.

### Manual installation

1. Copy `custom_components/hacs_marstek_api_connect` into the
   `custom_components` directory of your Home Assistant configuration.
2. Restart Home Assistant.

## Configuration

1. Open **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **Marstek Venus E**.
4. Select a discovered device or enter its IP address manually.
5. Keep UDP port `30000` unless the device uses a different port.
6. Enter the Bluetooth MAC address only when required by your setup.

The integration requests Auto mode after the first setup and switches on the
device LED once. Later integration reloads preserve the last LED selection.

### Integration options

Open **Settings → Devices & services → Marstek Venus E → Configure** to:

- configure manual schedule slots;
- select the modes shown by the operating-mode entity;
- change live energy/power and operating-mode/CT polling intervals.
- select a solar-power entity and configure surplus thresholds and averaging
  periods.

The option to reset existing schedules disables all ten manual schedule slots on
the device. Use it only when Home Assistant should take over schedule management.

## Entities

The exact entity IDs depend on the device name and any existing Home Assistant
registry entries. The entity registry is authoritative.

### Sensors

| Category | Available values |
| --- | --- |
| Battery | State of charge, capacity, rated and available capacity, temperature, voltage, current, power, charge/discharge power, error code and charging/discharging state |
| Power | PV power, configured solar power, grid power, off-grid power and total CT power |
| Three-phase CT | Phase A, B and C power, CT input/output energy, parser state and connection state |
| Energy totals | PV energy, grid import/export energy and load energy |
| Network and device | WiFi signal and network details, device model, firmware, MAC addresses, device IP and Bluetooth connection |
| System | Operating mode, Status, Storage status, Self-test and Solar Output state |

### Status sensors

**Status** and **Storage status** are enum sensors. Their states are
language-independent keys that Home Assistant translates for display, and the
winter-controller day counters are attributes instead of text. See
[Automatic storage / winter operation](#automatic-storage--winter-operation)
for the full list of states.

### Self-test

The **Self-test** sensor reports `OK`, `Warning` or `Error` (translated by Home
Assistant) and runs internal
checks on every update cycle:

- device connectivity (age of the last successful answer)
- operating-mode supervision (setpoint restored, restore attempts, error state)
- Passive renewal age for persistent Standby/Manual
- operating-mode deviations detected during the last 24 hours
- validity of the configured solar sensor
- gaps in the winter-controller day tracking

The result of each check is available as a sensor attribute. Mode-dropout
incidents are deduplicated and retained for 24 hours across restarts. The **Problem**
binary sensor (device class `problem`) turns on while the self-test reports
`error`, so it can drive notification automations directly. Both entities stay
available while the device is unreachable in order to report exactly that.

### Controls

- **Operating Mode** selector, including the separate physical **Schedule** mode
- **Manual power** slider (-2400 W to +2400 W)
- **LED Control** switch
- **Automatic storage / winter operation** switch
- **Clear all manual schedules** button

The former manual refresh buttons are no longer created because the integration
updates data automatically.

## Services

All services use the `hacs_marstek_api_connect` domain.

### Set operating mode

```yaml
action: hacs_marstek_api_connect.set_mode
data:
  mode: Auto
```

The service accepts the same persistent setpoints as the Operating Mode
selector: `Auto`, `AI`, `Standby`, `Manual`, `Schedule` and `Storage`. In the
user-facing selector, **Standby** and **Manual power** are both implemented through
the physical Passive mode. **Schedule** maps to the physical Manual API mode.
Storage is a virtual mode controlled by the integration. Calling this service
also disables automatic winter operation, just like selecting a mode in the UI.

Every service call explicitly selects its Marstek configuration entry:

```yaml
action: hacs_marstek_api_connect.set_mode
data:
  config_entry_id: 01ABCDEF0123456789ABCDEF01
  mode: Auto
```

The `config_entry_id` field is required on every integration service, so an
automation remains deterministic when further batteries are added later.

### Configure a manual schedule

```yaml
action: hacs_marstek_api_connect.set_manual_schedule
data:
  time_num: 0
  start_time: "01:00"
  end_time: "06:00"
  week_set: 127
  mode: charging
  power: 500
  enable: true
```

Constraints:

- `time_num`: slot 0–9
- `end_time`: must be later than `start_time`
- `mode`: `charging` or `discharging` (the former title-case values remain
  accepted for compatibility)
- `power`: magnitude from 100 to 2500 W
- `week_set`: day bitmask from 1 to 127

Editing or clearing schedules does not change the persistent Operating Mode
setpoint. Select **Schedule** explicitly when the stored schedules should run.

Day bitmask values:

| Day | Value |
| --- | ---: |
| Monday | 1 |
| Tuesday | 2 |
| Wednesday | 4 |
| Thursday | 8 |
| Friday | 16 |
| Saturday | 32 |
| Sunday | 64 |
| Weekdays | 31 |
| Weekend | 96 |
| Every day | 127 |

### Clear manual schedules

```yaml
action: hacs_marstek_api_connect.clear_all_schedules
```

This disables all ten schedule slots.

The former `set_passive_mode` and `change_operating_mode` services were removed.
Use the persistent Operating Mode selector or `set_mode`, the **Manual power**
slider, and `set_manual_schedule` instead.

## Automation example

The following example returns the device to Auto mode every morning:

```yaml
alias: Marstek - Auto mode in the morning
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: hacs_marstek_api_connect.set_mode
    data:
      mode: Auto
mode: single
```

## Troubleshooting

### Integration does not appear

- Restart Home Assistant after installation.
- Verify that
  `custom_components/hacs_marstek_api_connect/manifest.json` exists.
- Check **Settings → System → Logs** for setup errors.

### Device cannot be reached

- Confirm the device IP address.
- Ensure Home Assistant and the battery are on the same local network.
- Allow UDP port `30000` between Home Assistant and the device.
- Use manual IP configuration if UDP broadcast discovery is unavailable.
- Ensure that the device is powered on and connected to Wi-Fi.

### CT meter appears disconnected

The integration prefers the current CT state reported by `EM.GetStatus`. Confirm
that the CT meter is paired and that the device firmware exposes this endpoint.

### Debug logging

Add the following to `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.hacs_marstek_api_connect: debug
```

## API reference

The integration uses the Marstek Device Local API over UDP JSON-RPC. The supplied
reference is available at
[docs/MarstekDeviceOpenApi 2.0.pdf](docs/MarstekDeviceOpenApi%202.0.pdf).

## Support

- [GitHub Issues](https://github.com/JS-DE-Tech/hacs-marstek-api-connect/issues)
- [Home Assistant Community](https://community.home-assistant.io/)
- [Support development via PayPal](https://paypal.me/JensSaffrich)

## Contributing

Contributions are welcome. Keep changes focused and update the documentation when
behavior changes. Integration source files are located in
`custom_components/hacs_marstek_api_connect`.

Run the Home Assistant-independent regression suite before submitting changes:

```bash
python -m unittest discover -s tests -v
```

GitHub Actions additionally runs the official HACS and Home Assistant hassfest
validators on every push and pull request and once a week.

## License

Licensed under the [MIT License](LICENSE).

Copyright © 2026 Jens Saffrich (JS TechSector).

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by
Marstek. Use it at your own risk.

### Starting solar control from CT grid export

In the solar-control options, choose **Grid export (CT)** as the start source.
The defaults are **100 W minimum export** and a **2-minute start averaging time**.
A complete time-weighted CT average of **-100 W or lower** starts the existing
solar-check phase from Storage holding; periods of grid import count against export.
Only fresh meter readings while the battery is idle (within 10 W) are collected.
Invalid readings and polling gaps restart the observation window. The solar-power
sensor and solar thresholds are not needed for CT start mode. Existing installations
continue using solar-power mode until the source is changed.

Once started, CT approaching zero does not end the cycle: existing battery-power
confirmation, discharge protection, recharge-window priority and retry cooldown
remain in effect. The CT option changes the start trigger, not the device's Auto
mode behavior. Confirm behavior with the actual meter and battery after installation.


CT-triggered solar checks confirm charging after at least two minutes with a
battery-power average above **10 W** (the idle tolerance). The **100 W export**
setting controls the initial CT trigger, not this confirmation. The solar-power
source retains its existing above-100-W battery confirmation. In CT mode, actual
charging while already in Auto also counts for solar full-charge day tracking.

The recharge-window end is enforced even when the SOC field is missing or invalid
in an otherwise successful status response. Commands still require a working
connection to the device; tests simulate communication failures without hardware.
