# FutureBit Apollo III Standard: changelog

## v0.3.3

## Changes
- Device **Visit** URL now uses the Apollo web portal on standard HTTP port 80, independent of GraphQL port 5000.
- Retired `Miner reported status` sensor (`miner_status`) is removed from the integration-owned entity registry by exact unique ID and config entry; the active `Miner online` binary sensor remains.
- `Miner online` remains mapped to `Miner.online.result.online.status == "online"` (actual miner API state), not the enabled switch.
- `Miner service status` remains the observed service status.
- `Mining enabled` remains the requested service status, falling back to observed status.
- Existing entity IDs, validated telemetry, energy accumulator, and polling behavior are unchanged.

## FutureBit icon
Home Assistant normally loads integration logos from its external **brands** repository, not from a `custom_components` package. Therefore no unverified logo asset is bundled and this ZIP does **not** claim to change the integration icon. The official FutureBit logo must be published through Home Assistant's brands integration branding mechanism to appear automatically. No invented or third-party logo is used.

## Upgrade
Replace `/config/custom_components/apollo_iii/` with the `apollo_iii` directory from the archive, then restart Home Assistant. Keep the existing config entry.

This release has been statically checked, but has not been run in your Home Assistant installation.

## v0.3.4 branding
Home Assistant 2026.3+ supports local integration branding.
The supplied FutureBit image is installed under `brand/` as icon and logo PNGs.
The source image itself contains cropped lettering; no missing letters were invented.

## v0.3.5: Single-board ASIC startup fault monitoring
- Adds authenticated read-only `Logs.read` polling every 30 seconds (last 1000 MINER log lines).
- Detects `no ASIC is detected for brd 1` as a single-board ASIC detection fault.
- New diagnostics: ASIC detection fault, last ASIC detection fault, last fault time,
  ASIC detection failures observed, miner session changes observed.
- Cumulative observations and last fault are restored from the count sensor's HA state.
- Renames the existing mining statistics counter to `Miner statistics errors`.
- Counts are observations only: HA downtime or log rotation can hide errors.
- No mining control, energy integration, or telemetry mappings were changed.

Note: last-fault time is a text timestamp because miner log timestamps have no
explicit timezone. The active fault sensor clears when the current log session
does not contain the fault, or when mining telemetry confirms recovery.
\n## v0.3.6\nCounts at most one ASIC detection failure per distinct miner session. New unique ID `asic_failed_sessions` starts a new counter (old log-message count history remains separate). Latches fault until positive GH/s confirms recovery. Persists counted session IDs and latch in restored counter attributes.\n

### v0.3.9
Generalized miner fault monitoring only. Retires ASIC-specific entities, miner failed sessions, and miner session-change sensor. Existing generalized incident counter and error history are preserved. The Mining enabled switch can intentionally stop the miner; an intentional stop is not by itself a logged error. Fault remains latched until positive hashrate confirms recovery.

### v0.3.10
- `Hashrate target setting` now shows the target the miner actually runs with. The Apollo backend uses `minerHashrate` only in custom mode; in preset modes it was showing the unused stored value (for example 14 TH/s while in Super ECO). It now reads `Super ECO preset`, `ECO preset` and so on, or `Custom N TH/s`. Attributes `miner_mode` and `custom_hashrate_ths` keep the raw values.
- `Fan control setting` treats 0 as unset, matching the backend.
- The number entity is renamed `Custom mode target hashrate` (entity ID unchanged), because it has no effect in preset modes.

### v0.4.0
Audit against the miner's API and FutureBit's dashboard code (apolloapi-v2 / apolloui-v2).
- **Fault monitor rebuilt.** The miner's MINER log is a ~25-line `screen` snapshot that scrolls in about 9 seconds, so log matching alone missed most errors. The monitor now checks the miner stats every poll:
  - Conditions (count once per episode; the fault stays on while they last): miner not running when requested on (120 s), stats stopped updating (60 s), no hashrate after 5 min uptime (30 s), 5-min hashrate below half of the DVFS target after 15 min uptime (300 s), chip error rate over 5% (60 s), hashboard not powered (60 s).
  - Events: pool reconnection; miner restart not preceded by a start/stop/restart or setting change (from HA or the Apollo UI) in the last 15 min.
  - A deliberately stopped miner is never a fault. Log matching remains, now with wrapped lines joined.
  - `Miner fault` and `Miner error count` carry an `active_conditions` attribute.
- **Stale stats.** Miner sensors go unavailable, and `Miner online` turns off, when the stats' `date` hasn't changed for 60 s or is more than 10 min off HA's clock (the dashboard uses 1 min). The energy estimate skips stale samples.
- **Error sensors fixed.** The slot-level error fields are always 0 on the Apollo III. `Hashboard error rate` is now `Chip error rate (5 min)` from the master interval stats, and `Miner statistics errors` is now `Chip errors since miner start`. Entity IDs unchanged.
- **New sensors:** `Hashrate (1 h average)`; from the miner's DVFS log lines: `Hashrate target` (TH/s the active mode is tuning to), `Tuning state` (with DVFS state and hitrate attributes), `Board voltage`, `Fan PWM`.
- **Controls.** The miner loads its settings only at startup; saving (from HA or the Apollo UI) just rewrites its config. HA still doesn't restart the miner, but a new `Restart needed` binary sensor turns on when the saved settings differ from the ones the running miner loaded. It compares what the backend would put on the miner command line (power mode and fan control), so changes the miner would ignore don't count. Its `pending_changes` attribute lists the differences; press `Restart miner` to apply them. Pool settings aren't tracked.
- **New `Fan mode` select:** Automatic, Temperature target, or Fixed PWM. It is the only way back to automatic fan control from HA, and shows when a fixed PWM is overriding the temperature target.
- Removed unused `faults.py`.

### v0.4.1
- The miner's `upTime` can include the controller's clock jump at boot (no RTC; NTP sets the time after the miner starts), so `Miner uptime` can read longer than the controller has been up. The fault monitor's warm-up periods now also count from when HA saw the restart, so a reboot cannot skip them.

### v0.4.2
- `Board voltage` shows 3 decimals (as the miner reports it) and moves from Diagnostic to Sensors.
- `Fan PWM` moves from Diagnostic to Sensors (0.4.3).
- New `Mining efficiency (1 h average)`: current hashboard power over the 1 h average hashrate, as the Apollo dashboard calculates it (0.4.4).

### v0.4.5
- `Tuning state` now shows **Adjusting** or **Holding** instead of the miner's phase label, which stays at `TUNE_STEPPING_UP` indefinitely in Super ECO while nothing changes. Adjusting = board voltage setpoint or chip frequency (`osc`) changed, or the tuner logged an action, in the last 10 minutes. The raw phase, DVFS state, voltage, frequency, average chip voltage, hitrate, last tuner action and last adjustment time are attributes. Unknown for the first 10 minutes after first install.

### v0.4.6
- New `Chip speed` (GH/s per chip, 30 s; 21 chips x chip speed = hashrate) in Sensors, and `Chip frequency (osc)` (raw value, unit undocumented) in Diagnostic.
- `Chip frequency (osc)` moves to Sensors (0.4.7).

### v0.4.8
- Fix HA deprecation warning (breaks in 2027.2): sensors no longer use the `group` attribute name, which HA now reserves for entity groups.
- `Tuning state` restores its watch start (`watching_since`) across HA restarts, so it no longer reads unknown for 10 minutes after each restart.

### v0.5.0: setup and configuration
- Setup form with labels and help text (custom integrations need `translations/en.json`), a masked password field, and separate errors for a wrong password, an unreachable miner, and unexpected errors. No default IP.
- **Reconfigure** (change host, port or password) and **reauthentication** when the miner rejects the saved password (setup fails with a reauth prompt instead of polling with a bad password).
- **DHCP discovery** by hostname `futurebit-apollo*`; for a miner already set up, discovery updates its IP automatically.
- Config entries are identified by the controller's MAC address instead of host:port. Existing entries are migrated at startup.
- The default entry title `Apollo III (<host>)` follows the host after Reconfigure or a discovery IP update; a renamed title is kept.

### v0.5.1
- Named for the model it supports, the **Apollo III Standard** (miner only): integration name, device model ("Apollo III Standard"), setup forms, and the default entry title "Apollo III Standard (<host>)". The device name stays "FutureBit Apollo III" so entity names stay short. Existing entity IDs and the `apollo_iii` domain are unchanged.
- GitHub repository renamed to `ha-futurebit-apollo-iii-standard`.
