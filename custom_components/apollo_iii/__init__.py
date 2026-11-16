"""Apollo III Home Assistant integration."""
from datetime import datetime, timedelta
import logging
import time
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApolloAPI, ApolloAPIError
from .registry_cleanup import async_cleanup
from .const import (DOMAIN, MINER_INTERVAL, MCU_INTERVAL, SETTINGS_INTERVAL, LOG_INTERVAL,
                    STATS_STALE_AFTER, STATS_MAX_CLOCK_SKEW, LOG_STALE_AFTER)
from .logparse import entries, parse_dvfs

PLATFORMS = ["sensor", "binary_sensor", "select", "number", "button", "switch"]
_LOGGER = logging.getLogger(__name__)

class ChangeTracker:
    """Track how long a value has gone unchanged, on HA's monotonic clock."""
    def __init__(self):
        self.value = None
        self.changed = None

    def age(self, value):
        now = time.monotonic()
        if self.changed is None or value != self.value:
            self.value, self.changed = value, now
        return now - self.changed


def _clock_skew(stamp):
    """Seconds between an ISO timestamp with offset and HA's clock, or None."""
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return None
    return abs((dt_util.utcnow() - when).total_seconds())


def miner_fetcher(api):
    """get_miner plus staleness: the stats file can stop updating while the
    miner service still reports online, which would freeze every value."""
    tracker = ChangeTracker()

    async def fetch():
        data = await api.get_miner()
        stats = data.get("stats") or []
        first = stats[0] if stats and isinstance(stats[0], dict) else {}
        date = first.get("date")
        age = tracker.age(date)
        skew = _clock_skew(date)
        data["stats_unchanged_s"] = round(age)
        data["stale"] = (not date or age > STATS_STALE_AFTER
                         or skew is None or skew > STATS_MAX_CLOCK_SKEW)
        return data

    return fetch


def log_fetcher(api):
    """Miner log snapshot plus parsed DVFS values and their staleness."""
    tracker = ChangeTracker()

    async def fetch():
        data = dict(await api.get_miner_logs())
        items = entries(data.get("content"))
        dvfs = parse_dvfs(items)
        data["entries"] = items
        data["dvfs"] = dvfs
        data["dvfs_stale"] = (not dvfs.get("stamp")
                              or tracker.age(dvfs.get("stamp")) > LOG_STALE_AFTER)
        return data

    return fetch


class ApolloCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api, name, interval, fetch):
        super().__init__(
            hass, _LOGGER, name=f"Apollo III {name}",
            update_interval=timedelta(seconds=interval)
        )
        self.api = api
        self.fetch = fetch
        self._consecutive_failures = 0
        self.last_success = None

    async def _async_update_data(self):
        try:
            result = await self.fetch()
            self._consecutive_failures = 0
            self.last_success = dt_util.utcnow()
            return result
        except ApolloAPIError as err:
            self._consecutive_failures += 1
            if self.name == "Apollo III mcu" and self.data is not None and self._consecutive_failures == 1:
                _LOGGER.warning("Transient MCU polling failure; retaining last sample: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    api = ApolloAPI(
        async_get_clientsession(hass),
        entry.data["host"], entry.data["port"], entry.data["password"]
    )
    coordinators = {
        "miner": ApolloCoordinator(hass, api, "miner", MINER_INTERVAL, miner_fetcher(api)),
        "mcu": ApolloCoordinator(hass, api, "mcu", MCU_INTERVAL, api.get_mcu),
        "settings": ApolloCoordinator(hass, api, "settings", SETTINGS_INTERVAL, api.get_settings),
        "logs": ApolloCoordinator(hass, api, "logs", LOG_INTERVAL, log_fetcher(api)),
    }
    # MCU/settings work even with the mining hardware offline.
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api, **coordinators}
    from .general_errors import GeneralErrorState
    hass.data[DOMAIN][entry.entry_id]["general_error_monitor"] = GeneralErrorState(
        coordinators["logs"], coordinators["miner"], coordinators["settings"], api)
    from .restart_needed import RestartTracker
    hass.data[DOMAIN][entry.entry_id]["restart_tracker"] = RestartTracker(
        coordinators["miner"], coordinators["settings"])
    await async_cleanup(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
