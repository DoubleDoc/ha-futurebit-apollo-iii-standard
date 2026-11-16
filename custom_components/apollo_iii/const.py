DOMAIN = "apollo_iii"
DEFAULT_PORT = 5000
MINER_INTERVAL = 15
MCU_INTERVAL = 30
SETTINGS_INTERVAL = 60
MODES = ["super_eco", "eco", "balanced", "turbo", "custom"]
LOG_INTERVAL = 30

# Miner stats count as stale when their `date` has not changed for this long
# (the Apollo dashboard uses 1 minute), or is this far from HA's clock.
STATS_STALE_AFTER = 60
STATS_MAX_CLOCK_SKEW = 600
LOG_STALE_AFTER = 90

# Fault monitor thresholds.
FAULT_ERROR_RATE = 5.0          # % chip errors, 5 minute average
FAULT_LOW_HASHRATE = 0.5        # fraction of the DVFS target, 5 minute average
FAULT_STARTUP_GRACE = 300       # s of miner uptime before hashrate checks
FAULT_LOW_HASHRATE_GRACE = 900  # s of uptime before the low-hashrate check
FAULT_INTENTIONAL_WINDOW = 900  # s after a requested start/stop/setting change
