"""FutureBit Apollo III Standard (miner-only model) Home Assistant integration."""
from datetime import datetime, timedelta
import logging
import re
import time
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApolloAPI, ApolloAPIError, ApolloAuthError
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
    def __init__(self, hass, entry, api, name, interval, fetch):
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"Apollo III {name}",
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
        except ApolloAuthError as err:
            # Password changed on the miner: HA starts the reauth flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApolloAPIError as err:
            self._consecutive_failures += 1
            if self.name == "Apollo III mcu" and self.data is not None and self._consecutive_failures == 1:
                _LOGGER.warning("Transient MCU polling failure; retaining last sample: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err

def _migrate_unique_id(hass, entry, mcu):
    """Entries created before v0.5.0 are keyed by host:port; key them by the
    controller MAC (as the config flow now does) so an IP change, or DHCP
    discovery, maps to the same entry. Retried at each setup until it works."""
    from .config_flow import is_mac
    if is_mac(entry.unique_id) or not mcu:
        return
    mac = ApolloAPI.device_mac(mcu)
    if not mac:
        return
    unique_id = format_mac(mac)
    if any(e.unique_id == unique_id for e in hass.config_entries.async_entries(DOMAIN)):
        return
    hass.config_entries.async_update_entry(entry, unique_id=unique_id)
    _LOGGER.info("Apollo III config entry now identified by MAC %s", unique_id)


def _sync_title(hass, entry):
    """Keep the default "Apollo III Standard (<host>)" title in step with the
    host after Reconfigure or a DHCP address update, and update the pre-0.5.1
    "Apollo III (<host>)" default. A title the user renamed is left alone."""
    match = re.fullmatch(r"Apollo III(?: Standard)? \((.+)\)", entry.title or "")
    wanted = f"Apollo III Standard ({entry.data['host']})"
    if match and entry.title != wanted:
        hass.config_entries.async_update_entry(entry, title=wanted)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    api = ApolloAPI(
        async_get_clientsession(hass),
        entry.data["host"], entry.data["port"], entry.data["password"]
    )
    coordinators = {
        "miner": ApolloCoordinator(hass, entry, api, "miner", MINER_INTERVAL, miner_fetcher(api)),
        "mcu": ApolloCoordinator(hass, entry, api, "mcu", MCU_INTERVAL, api.get_mcu),
        "settings": ApolloCoordinator(hass, entry, api, "settings", SETTINGS_INTERVAL, api.get_settings),
        "logs": ApolloCoordinator(hass, entry, api, "logs", LOG_INTERVAL, log_fetcher(api)),
    }
    # A rejected password fails setup and starts reauth. An unreachable miner
    # does not: entities are created and stay unavailable until it answers.
    try:
        await api.login()
    except ApolloAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ApolloAPIError:
        pass
    # MCU/settings work even with the mining hardware offline.
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    _migrate_unique_id(hass, entry, coordinators["mcu"].data)
    _sync_title(hass, entry)
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
