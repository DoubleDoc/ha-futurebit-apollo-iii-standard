# Development

Notes for working on the integration. For using it, see [README.md](README.md).

## Repository layout

| Path | Purpose |
|---|---|
| `custom_components/apollo_iii/` | The integration (domain `apollo_iii`). This folder is what users install. |
| `custom_components/apollo_iii/translations/en.json` | UI strings. Custom integrations load these, not `strings.json`; keep the two identical. |
| `custom_components/apollo_iii/brand/` | Local brand images (Home Assistant 2026.3+). |
| `hacs.json` | HACS metadata. |
| `deploy.sh` | Copies the integration into a local Home Assistant config for testing. |

## How it works

### Data sources
The miner runs FutureBit's Apollo WebOS 2 backend ([apolloapi-v2](https://github.com/jstefanop/apolloapi-v2), `staging` branch for Apollo III; the UI is [apolloui-v2](https://github.com/jstefanop/apolloui-v2)). The integration talks to its GraphQL API at `http://<host>:5000/api/graphql`.

| Coordinator | Interval | Query | Auth |
|---|---|---|---|
| `miner` | 15 s | `Miner.online`, `Miner.stats` | none |
| `mcu` | 30 s | `Mcu.stats` (controller) | token |
| `settings` | 60 s | `Settings.read`, `Services.stats` | token |
| `logs` | 30 s | `Logs.read` (MINER) | token |

Login is `Auth.login(password)`, which returns a JWT. A wrong password is a GraphQL error with code `UNAUTHENTICATED` (`ApolloAuthError`), which starts Home Assistant's reauth flow. GraphQL introspection is disabled on the miner; use the typeDefs in apolloapi-v2.

### Miner quirks the code depends on
- **The MINER log is a screen snapshot,** not a file: `screen -X hardcopy` of the miner's terminal, about 25 lines, hard-wrapped at 80 columns. `logparse.py` joins wrapped lines. It scrolls in seconds, so the fault monitor uses the stats, not the log, as its main signal.
- **DVFS log lines** (every ~3 s) are the only source of the active hashrate target, board voltage setpoint, fan PWM and tuner phase. The phase label stays at `TUNE_STEPPING_UP` indefinitely in Super ECO, so `Tuning state` reports observed changes instead.
- **Slot-level `errors` / `errorRate` are always 0** on the Apollo III. Chip errors are in `master.intervals.int_*`.
- **Current hashrate** = `master.intervals.int_30.bySol` (equal to `slots.int_0.ghs`); 1 h average = `int_3600.bySol`. `int_0` is the whole miner run.
- **Settings apply only at miner start.** `Settings.update` rewrites the config file; the miner reads it once. `configurator.js` uses `minerHashrate` only in `custom` mode, spells Super ECO `supereco` on the command line, treats 0 or null fan values as unset, and lets a fixed PWM override the temperature target. `restart_needed.py` mirrors that logic.
- **No RTC on the controller:** after a reboot, NTP jumps the clock forward and `master.upTime` includes the jump.
- **Stats staleness:** `stats.date` updates about every 10 s; the dashboard treats more than 1 minute as inactive.
- **Hostname** is `futurebit-apollo-3` on every unit, so entries are keyed by the controller MAC (`Mcu.stats.network[eth0].mac`).

### Modules
| File | Role |
|---|---|
| `__init__.py` | Setup, coordinators, staleness tracking, unique-ID migration, title sync. |
| `api.py` | GraphQL client and queries. |
| `config_flow.py` | User, DHCP, reconfigure and reauth steps. |
| `logparse.py` | Screen-snapshot parsing and DVFS values. |
| `general_errors.py` | Fault monitor: stats conditions, events, log matching, incident counter. |
| `restart_needed.py` | Tracks the settings the running miner loaded. |
| `sensor.py`, `binary_sensor.py`, `select.py`, `number.py`, `switch.py`, `button.py` | Entity platforms. |
| `registry_cleanup.py` | Removes entities retired in early versions. |

## Local development

`deploy.sh` copies `custom_components/apollo_iii` into a Home Assistant config folder, backing up the existing copy first. It does not restart Home Assistant; Python changes load only after a restart.

```sh
./deploy.sh                                            # defaults below
HA_CONFIG=/path/to/config BACKUP_DIR=/path/to/backups ./deploy.sh
```

| Variable | Default |
|---|---|
| `HA_CONFIG` | `/config` |
| `BACKUP_DIR` | `$HOME/apollo-iii-backups` |

Then check the configuration and restart Home Assistant (`ha core check` and `ha core restart` on Home Assistant OS).

## Testing

There is no automated test suite yet. Changes so far were checked by:
- running the API client and coordinator fetchers against a live miner, with Home Assistant modules stubbed;
- simulating fault, restart-needed and tuning scenarios against the same code;
- checking the live entities and the config flow (through Home Assistant's REST flow API) after deploying.

## Releasing

1. Update `version` in `custom_components/apollo_iii/manifest.json` and add an entry to `CHANGELOG.md`.
2. Commit, then tag and publish a GitHub release named `vX.Y.Z`. HACS installs from releases.
