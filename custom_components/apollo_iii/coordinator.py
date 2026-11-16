"""Data update coordinators for the Apollo III Standard."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApolloAPI, ApolloAPIError, ApolloAuthError
from .const import LOG_STALE_AFTER, STATS_MAX_CLOCK_SKEW, STATS_STALE_AFTER
from .logparse import entries, parse_dvfs

if TYPE_CHECKING:
    from .general_errors import GeneralErrorState
    from .restart_needed import RestartTracker

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
    """Polls one part of the miner API."""

    def __init__(self, hass, entry, api, name, interval, fetch, retain_one_failure=False):
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"Apollo III {name}",
            update_interval=timedelta(seconds=interval)
        )
        self.api = api
        self.fetch = fetch
        # Keep the last sample through one transient failure (controller stats).
        self.retain_one_failure = retain_one_failure
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
            if self.retain_one_failure and self.data is not None and self._consecutive_failures == 1:
                _LOGGER.warning("Transient MCU polling failure; retaining last sample: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err


@dataclass
class ApolloData:
    """Runtime data for one config entry (entry.runtime_data)."""
    api: ApolloAPI
    miner: ApolloCoordinator
    mcu: ApolloCoordinator
    settings: ApolloCoordinator
    logs: ApolloCoordinator
    monitor: GeneralErrorState
    restart_tracker: RestartTracker


type ApolloConfigEntry = ConfigEntry[ApolloData]
