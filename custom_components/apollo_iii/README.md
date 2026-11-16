# FutureBit Apollo III v0.3.3

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
