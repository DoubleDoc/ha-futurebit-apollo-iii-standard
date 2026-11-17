# Changelog

All notable changes to the FutureBit Apollo III Standard integration. Newest first.

## 1.0.9
- Documentation only; the integration's behavior is unchanged.
- README: installation steps for the Home Assistant 2026.11+ Marketplace and for HACS on 2026.3 to 2026.10, including the restart and the step to add the integration.

## 1.0.8
- Documentation only; the integration's behavior is unchanged.
- DEVELOPMENT.md: measured chip frequency, hashrate, power, efficiency, temperatures, tuning values and start-up times for all four power modes, with start-up timings and charts, linked from the README.

## 1.0.7
- Fault monitor: a miner restart or power-mode change no longer counts as `High chip error rate`. The chips throw many errors while the miner tunes after a start, which kept the 5-minute error rate above 5 % for several minutes. The check now waits 5 minutes after a start, like the hashrate checks, and counts only while the 30-second rate is also above 5 %.

## 1.0.6
- `Chip frequency (osc)` is now `Chip frequency`, in MHz. Comparing Super ECO (409) with Eco (614) on a real miner showed that the hashrate per chip scales exactly with this value, about 932 hashes per clock, so it is the chip clock in MHz. It is set by the power mode. The entity ID is unchanged.
- Home Assistant may show a one-time repair because the sensor's long-term statistics gain a unit; choose to keep or delete the old data.

## 1.0.5
- Setup: a second setup for a miner that already has one open now shows a message instead of the raw reason `already_in_progress`.
- `Hashboard energy estimated` is renamed `Hashboard energy (estimated)` (display name only; the entity ID is unchanged).
- README: the debug logging YAML no longer sets `default:`; Home Assistant changes the overall log level only when `default:` is written, so the old advice could override a user's existing default.
- README: discovery updates a moved miner's IP automatically only on a wired connection (on Wi-Fi it asks for the password first), and the pool limitation is worded accurately (`Pool host` shows the pool in use).
- DEVELOPMENT.md: tests need Python 3.14.2 or newer; hashrate field sources, the module list (`const.py`, `entity.py`) and CI triggers corrected.

## 1.0.4
- Debug logging: routine miner polls are no longer timed twice (the coordinator already logs their duration).

## 1.0.3
- **Debug logging** for troubleshooting (integration page > Enable debug logging): logins, token refresh, setting changes, commands and slow API calls with their duration, a one-line summary of every miner poll and log snapshot (DVFS target, voltage, phase, tuner actions), stats going stale and recovering, fault-monitor decisions (condition started, counted, cleared; why a restart did or did not count), Restart needed snapshots and pending changes, tuner adjustments, and settings and commands sent from Home Assistant.
- Passwords, tokens, MAC addresses and the pool username are never logged.
- The README's debug logging instructions are rewritten (the YAML example was corrected again after 1.0.4).
- README: tested with Apollo Web OS v2.1.3.

## 1.0.2
- Repository published. HACS validation now runs with no ignored checks (brand images are found in `custom_components/apollo_iii/brand/`).
- README: authorship statement.
- No changes to the integration's behavior.

## 1.0.1
- Diagnostics: the miner's IP address is also removed from the entry title.

## 1.0.0
First stable release.
- **Diagnostics download** (device page > Download diagnostics), with the password, MACs, IP addresses and pool username redacted.
- Entity names, select options and the tuning state come from translations; icons from `icons.json`. Visible names are unchanged.
- Controls refresh the miner state immediately after a change, instead of up to 10 seconds later.
- Zero hashrate no longer also counts as "low hashrate".
- Code follows current Home Assistant conventions (`runtime_data`, separate coordinator module); legacy entity cleanup from pre-0.4 versions removed.
- Automated tests (45, 92 % coverage), and CI for tests, hassfest and HACS validation.
- MIT license.

## 0.5.1
- Named for the model it supports, the **Apollo III Standard** (miner only): integration name, device model, setup forms, and the default entry title "Apollo III Standard (<host>)". The device name stays "FutureBit Apollo III" so entity names stay short. Entity IDs and the `apollo_iii` domain are unchanged.
- GitHub repository renamed to `ha-futurebit-apollo-iii-standard`.
- Documentation split into a user README, this changelog, and DEVELOPMENT.md.

## 0.5.0: setup and configuration
- Setup form with labels and help text, a masked password field, and separate errors for a wrong password, an unreachable miner, and unexpected errors. No default IP.
- **Reconfigure** to change host, port or password, and **re-authentication** when the miner rejects the saved password.
- **DHCP discovery** by hostname `futurebit-apollo*`. For a miner already set up, discovery updates its IP automatically on a wired connection; on Wi-Fi it asks for the password first.
- Config entries are identified by the controller's MAC address instead of host:port. Existing entries are migrated at startup.
- The default entry title follows the host after Reconfigure or a discovery IP update; a renamed title is kept.

## 0.4.8
- Fix a Home Assistant deprecation (breaks in 2027.2): sensors no longer use the `group` attribute name, which HA now reserves for entity groups.
- `Tuning state` restores its watch start across HA restarts, so it no longer reads unknown for 10 minutes after each restart.

## 0.4.6 – 0.4.7
- New `Chip speed` (GH/s per chip) and `Chip frequency (osc)` (raw value; unit undocumented) sensors.

## 0.4.5
- `Tuning state` shows **Adjusting** or **Holding** from observed changes, instead of the miner's phase label, which stays at `TUNE_STEPPING_UP` indefinitely in Super ECO. The raw phase and related values are attributes.

## 0.4.2 – 0.4.4
- `Board voltage` shows 3 decimals. `Board voltage` and `Fan PWM` move to Sensors.
- New `Mining efficiency (1 h average)`: current power over the 1 h average hashrate, as the Apollo dashboard calculates it.

## 0.4.1
- The miner's uptime can include the controller's clock jump after boot (no RTC). The fault monitor's warm-up periods now also count from when HA saw the restart.

## 0.4.0
- **Fault monitor rebuilt.** The miner's log is only a ~25-line screen snapshot, so log matching alone missed most errors. The monitor now checks the miner stats every poll: miner not running, stats stopped updating, no hashrate, low hashrate against the target, high chip error rate, hashboard not powered, pool reconnections and unexpected restarts. A deliberately stopped miner is never a fault.
- **Stale stats:** miner sensors go unavailable, and `Miner online` turns off, when the stats stop updating. The energy estimate skips stale samples.
- **Error sensors fixed:** the slot-level error fields are always 0 on the Apollo III. `Chip error rate (5 min)` and `Chip errors since miner start` now read the master interval stats.
- **New sensors:** `Hashrate (1 h average)`, `Hashrate target`, `Tuning state`, `Board voltage`, `Fan PWM`.
- **`Restart needed`** binary sensor: settings load only at miner start, so this shows when saved settings are not running yet.
- **`Fan mode`** select: Automatic, Temperature target, or Fixed PWM.

## 0.3.10
- `Hashrate target setting` shows the target the miner actually uses (for example `Super ECO preset`); the stored custom hashrate applies only in Custom mode. The number entity is renamed `Custom mode target hashrate`.
- `Fan control setting` treats 0 as unset.

## 0.3.3 – 0.3.9
- Device "Visit" link uses the Apollo web portal on port 80.
- Local brand images (Home Assistant 2026.3+).
- Log-based miner fault monitoring, generalized in 0.3.9.
- Retired early v0.1/v0.2 entities are removed from the entity registry.
