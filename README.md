# FutureBit Apollo III Standard for Home Assistant

A Home Assistant custom integration for the **FutureBit Apollo III Standard**, the miner-only Apollo III model (no Bitcoin node). It reads the miner's local API and gives you its hashrate, power, temperatures, pool shares and health in Home Assistant, plus controls for mining, power mode and fans.

Unofficial and not affiliated with FutureBit.

> Tested on an Apollo III Standard running **Web OS v2.1.3** (FutureBit's Apollo software), with Home Assistant 2026.10. Other Web OS versions may report data differently; if something looks wrong, please open an issue and include your Web OS version.

## Features

- **Live mining data** every 15 seconds: hashrate (30 s and 1 h average), the hashrate target the miner is tuning to, power, current, board voltage, efficiency, chip speed and frequency, temperatures, fan speed and PWM, pool shares.
- **Health monitoring:** a `Miner fault` sensor and an incident counter that catch a stopped miner, frozen stats, zero or low hashrate, a high chip error rate, an unpowered hashboard, pool reconnections and unexpected restarts. A miner you stop on purpose is never a fault.
- **Controls:** start, stop and restart mining; choose the power mode (Super ECO, ECO, Balanced, Turbo, Custom); set the custom hashrate; choose the fan mode and its target.
- **Restart needed indicator:** the miner loads its settings only when it starts, so this shows when saved settings are not running yet.
- **Energy estimate** of the hashboard's consumption, for the Energy dashboard.
- **Discovery, reconfigure and re-authentication** built into the setup flow.

## Requirements

- A FutureBit Apollo III **Standard** on your network, with its Apollo web dashboard set up (you need the dashboard password). Tested with Web OS v2.1.3.
- Home Assistant 2026.3 or newer.

## Installation

### HACS (recommended)
1. In HACS, open the menu (three dots) > **Custom repositories**.
2. Add `https://github.com/DoubleDoc/ha-futurebit-apollo-iii-standard` with type **Integration**.
3. Search for **FutureBit Apollo III Standard**, install it, and restart Home Assistant.

### Manual
1. Copy the `custom_components/apollo_iii` folder from this repository into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

**Discovery:** Home Assistant usually finds the miner on your network by its hostname (`futurebit-apollo-*`) and offers it under **Settings > Devices & services**. Click **Add** and enter the dashboard password.

**Manually:** go to **Settings > Devices & services > Add integration**, search for **FutureBit Apollo III Standard**, and enter:

| Field | What to enter |
|---|---|
| Host | The miner's IP address or hostname, for example `192.168.1.50`. |
| API port | `5000`, unless you changed it. |
| Dashboard password | The password for the Apollo web dashboard. There is no username. |

**Later changes:**
- **New IP, port or password:** open the integration's menu (three dots) > **Reconfigure**. Leave the password blank to keep it.
- **Password changed on the miner:** Home Assistant shows a re-authentication prompt. Enter the new password.
- **Miner moved to a new IP:** on a wired connection, discovery updates it automatically. On Wi-Fi, Home Assistant shows the miner as discovered; enter the password and the existing entry is updated. Each miner is identified by its controller's wired MAC address, so it is never added twice.
- **More than one miner:** add each one the same way. Rename the new device (for example "Garage Apollo") so its entity names are easy to tell apart.

## Entities

### Controls
| Entity | Notes |
|---|---|
| Mining enabled (switch) | Starts or stops mining. Takes effect immediately. |
| Start / Stop / Restart miner (buttons) | Restart also applies saved settings. |
| Performance mode (select) | Super ECO, ECO, Balanced, Turbo, Custom. |
| Fan mode (select) | Automatic, Temperature target, or Fixed PWM. |
| Custom mode target hashrate (number) | 5–20 TH/s. Used only in Custom mode. |
| Fan temperature target / Fan PWM target (numbers) | 40–80 °C / 10–100 %. Setting a PWM switches the fan to Fixed PWM. |

> **Settings take effect at the next miner restart.** The miner reads its settings only when it starts, and this integration never restarts it on its own. After changing the performance mode, custom hashrate or fan settings, `Restart needed` turns on; press **Restart miner** when you are ready. Its `pending_changes` attribute lists what will change.

### Sensors
| Group | Entities |
|---|---|
| Performance | Hashrate, Hashrate (1 h average), Hashrate target, Hashrate target setting, Chip speed, Chip frequency, Mining efficiency, Mining efficiency (1 h average) |
| Power | Hashboard power, Hashboard current, Board voltage, Hashboard energy (estimated) |
| Thermal | Hashboard temperature, Miner average temperature, Controller temperature, Miner fan speed, Fan PWM, Fan control setting |
| Pool | Pool accepted shares, Pool rejected shares |
| Health | Miner online, Miner fault, Restart needed, Miner error count, Miner last error, Miner last error time, Miner last error category, Chip error rate (5 min), Miner service status, CPU usage |

**Diagnostic:** Tuning state (Adjusting / Holding), chip errors since miner start, maximum temperature, active hashboards, SPI errors, solutions, pool host, sent shares, miner uptime, controller boot time, operating system, CPU threads, load average, memory and disk usage.

## How the health monitoring works

`Miner fault` is on while a problem lasts. `Miner error count` counts each problem once, and `Miner last error` says what it was. The checks, with how long each must last before it counts:

| Problem | Counts after |
|---|---|
| Miner not running although mining is enabled | 2 minutes |
| Miner stats stopped updating (frozen miner) | 1 minute |
| No hashrate (after 5 minutes of uptime) | 30 seconds |
| 5-minute hashrate below half of the target (after 15 minutes of uptime) | 5 minutes |
| Chip error rate above 5 % | 1 minute |
| Hashboard not powered | 1 minute |
| Pool reconnection | immediately |
| Miner restarted without anyone asking | immediately |

Error messages that appear in the miner's log are also counted. A deliberately stopped miner, and restarts within 15 minutes of a start, stop, restart or setting change, are not faults.

## Known limitations

- **Preset hashrate targets** (Super ECO, ECO and so on) are not published by FutureBit. `Hashrate target` shows the target the miner itself reports while running.
- **Miner uptime can read too long.** The controller has no real-time clock, so after a reboot its clock jumps forward when it syncs, and the miner's uptime includes that jump. The Apollo dashboard shows the same value.
- **Apollo III Full Package** (with the Bitcoin node) and the older USB Apollo I/II are not supported.
- **Pool configuration** (URL, worker, password) can't be viewed or changed here and isn't tracked by `Restart needed`. `Pool host` shows only the pool currently in use.

## Troubleshooting

- **"Could not reach the Apollo API":** check the host and port, that the miner is on, and that Home Assistant can reach it (firewalls, VLANs).
- **"The miner rejected the password":** use the password you log in to the Apollo web dashboard with.
- **Entities unavailable:** the miner's stats have not updated for a minute, or Home Assistant cannot reach it. `Miner online` has `stats_stale` and `service_status` attributes to tell which.
- **Reporting a problem:** open an issue and attach the diagnostics file (device page > three dots > **Download diagnostics**). Passwords, MAC and IP addresses and the pool username are removed from it.
- **Debug logs:** go to **Settings > Devices & services > FutureBit Apollo III Standard**, open the menu (three dots) and choose **Enable debug logging**. Reproduce the problem, then choose **Disable debug logging**; Home Assistant downloads the log file. No restart is needed.
  To keep debug logging on across restarts instead, add this to `configuration.yaml` and restart. If you already have a `logger:` section, add only the `custom_components.apollo_iii` line under its `logs:`.
  ```yaml
  logger:
    logs:
      custom_components.apollo_iii: debug
  ```
  This changes only this integration's log level. Remove the line and restart when you are done.

## Authorship

This integration was built with **Claude**, Anthropic's AI model, working in Claude Code. Claude did the heavy lifting: since this repository was created at version 0.3.9, Claude wrote essentially all of the code, the tests, the CI setup and the documentation. That included auditing every sensor against the miner's API and FutureBit's open-source backend and dashboard code, finding and fixing the bugs that turned up, and rebuilding the fault monitor, setup flow and controls.

[DoubleDoc](https://github.com/DoubleDoc) directed the project: deciding what to build and how it should behave, reviewing the results, testing on a real Apollo III Standard, and making the release decisions. Versions before 0.3.9 predate this repository.

## More

- [CHANGELOG.md](CHANGELOG.md): version history.
- [DEVELOPMENT.md](DEVELOPMENT.md): how the integration works, and how to develop and test it.
- License: [MIT](LICENSE).
