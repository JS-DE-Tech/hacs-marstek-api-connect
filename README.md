# Marstek Venus E for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-marstek-api-connect/main/docs/images/marstek-venus-e.png"
       alt="Marstek Venus E battery storage system"
       width="420">
</p>

Home Assistant integration for Marstek Venus E battery storage systems using the local UDP JSON-RPC API.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
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
- User-facing operating modes: Auto, AI, Standby, Manual power and Storage/Winter
- Configurable list of modes shown in the operating-mode selector
- Ten configurable manual schedule slots
- Automatic storage/winter controller with configurable solar-surplus detection
- Separate live-data and mode/CT polling intervals
- LED control as a regular Home Assistant switch
- German, English and French translations
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
- The slider ranges from -2400 W to +2400 W in 100 W steps.
- Negative values charge; positive values discharge.
- Selecting Standby does not change the stored slider value.
- Changing the slider while Manual is active applies the new value immediately.

The Venus E 3.0 requires a finite Passive countdown. Standby and Manual therefore
use a 300-second command that the integration renews after 240 seconds.

If physical feedback differs from the persistent setpoint, the integration checks
it every two minutes and tries to restore it up to five times. Standby additionally
requires three consecutive Grid Power samples within ±30 W. After five failed
attempts, the regular Status sensor reports `Fehler Betriebsmodus`. Selecting a
mode again resets the error and retry counter.

Storage and automatic winter operation manage their own internal mode changes and
temporarily take priority over this supervision.

## Automatic storage / winter operation

Enable the **Automatic storage / winter operation** switch to manage seasonal
storage without fixed calendar dates.

1. While the battery is in Auto mode, the integration records the highest state
   of charge reached each calendar day.
2. Storage mode starts after five consecutive valid days whose maximum state of
   charge remained below 50%.
3. A day is valid when at least 20 hours elapsed between its first and last
   observation. Missing or non-consecutive days reset the current sequence.
4. At or below 45%, Storage charges at 500 W up to 50%; at 50% it uses a
   renewed 0 W Passive command to hold the battery.
5. A configured Home Assistant solar-power entity is evaluated with
   time-weighted moving averages. The default hysteresis detects surplus at a
   two-minute average of at least 1400 W and clears it at a five-minute average
   below 1000 W.
6. Detected surplus starts a five-minute Auto-mode solar test. A two-minute
   average Battery Power above +100 W confirms charging. Below -100 W means
   discharging; values between those thresholds are neutral.
7. A failed solar test has a ten-minute cooldown. Auto may use stored energy down
   to 50%, after which the battery returns to 0 W Passive holding.
8. A full-charge day requires confirmed solar charging from 95% or below to at
   least 99%. After two consecutive valid full-charge days, the controller
   returns to Auto observation and restarts the five-day counter.

Controller state and daily counters are stored by Home Assistant and survive
integration reloads and restarts. Selecting an operating mode manually disables
automatic storage to prevent competing commands.

Configure the solar source under **Configure → Configure solar surplus**. The
source must be a Home Assistant power sensor using W or kW. If it is missing,
unknown, unavailable, or has an unsupported unit, surplus is false and no new
solar test starts. The solar entities remain informational outside automatic
winter operation.

The **Status-Lagerung** sensor can report:

- `Deaktiviert`
- `Automatik – Beobachtung (n/5 Tage)`
- `Lagerung – Laden`
- `Lagerung – Halten`
- `Lagerung – Solarprüfung`
- `Lagerung – Solarladen`
- `Lagerung – Entladen`
- `Lagerung – Vollladung erkannt (1/2 Tage)`

The regular **Status** sensor reports `Standby`, `Laden`, `Entladen`, or the
current Storage phase.

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
| System | Operating mode, Status, Status-Lagerung and solar-surplus state |

### Controls

- **Operating Mode** selector
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

Supported physical API modes are `Auto`, `AI`, `Manual` and `Passive`. In the
user-facing selector, **Standby** and **Manual power** are both implemented through
the physical Passive mode. The physical Manual API mode remains available to the
schedule services. Storage is a virtual mode controlled by the integration.

### Configure a manual schedule

```yaml
action: hacs_marstek_api_connect.set_manual_schedule
data:
  time_num: 0
  start_time: "01:00"
  end_time: "06:00"
  week_set: 127
  mode: Charging
  power: 500
  enable: true
```

Constraints:

- `time_num`: slot 0–9
- `end_time`: must be later than `start_time`
- `mode`: `Charging` or `Discharging`
- `power`: magnitude from 100 to 2500 W
- `week_set`: day bitmask from 1 to 127

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

### Set passive mode

Negative power charges the battery; positive power discharges it.

```yaml
action: hacs_marstek_api_connect.set_passive_mode
data:
  power: -500
  cd_time: 3600
```

Set `cd_time` to `0` for an indefinite command.

### Clear manual schedules

```yaml
action: hacs_marstek_api_connect.clear_all_schedules
```

This disables all ten schedule slots.

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

## License

Licensed under the [MIT License](LICENSE).

Copyright © 2026 Jens Saffrich (JS TechSector).

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by
Marstek. Use it at your own risk.
