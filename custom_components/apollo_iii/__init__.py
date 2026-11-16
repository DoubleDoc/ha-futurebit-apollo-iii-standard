"""Apollo III Home Assistant integration."""
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApolloAPI, ApolloAPIError
from .registry_cleanup import async_cleanup
from .const import DOMAIN, MINER_INTERVAL, MCU_INTERVAL, SETTINGS_INTERVAL, LOG_INTERVAL

PLATFORMS = ["sensor", "binary_sensor", "select", "number", "button", "switch"]
_LOGGER = logging.getLogger(__name__)

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
            from homeassistant.util import dt as dt_util
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
        "miner": ApolloCoordinator(hass, api, "miner", MINER_INTERVAL, api.get_miner),
        "mcu": ApolloCoordinator(hass, api, "mcu", MCU_INTERVAL, api.get_mcu),
        "settings": ApolloCoordinator(hass, api, "settings", SETTINGS_INTERVAL, api.get_settings),
        "logs": ApolloCoordinator(hass, api, "logs", LOG_INTERVAL, api.get_miner_logs),
    }
    # MCU/settings work even with the mining hardware offline.
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api, **coordinators}
    from .general_errors import GeneralErrorState
    hass.data[DOMAIN][entry.entry_id]["general_error_monitor"] = GeneralErrorState(coordinators["logs"], coordinators["miner"])
    await async_cleanup(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
