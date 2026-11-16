"""FutureBit Apollo III Standard (miner-only model) integration."""
from __future__ import annotations

import logging
import re

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import ApolloAPI, ApolloAPIError, ApolloAuthError
from .const import DOMAIN, LOG_INTERVAL, MCU_INTERVAL, MINER_INTERVAL, SETTINGS_INTERVAL
from .coordinator import ApolloConfigEntry, ApolloCoordinator, ApolloData, log_fetcher, miner_fetcher
from .general_errors import GeneralErrorState
from .restart_needed import RestartTracker

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER,
             Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
_LOGGER = logging.getLogger(__name__)
MAC_RE = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


def is_mac(value) -> bool:
    return bool(value) and bool(MAC_RE.fullmatch(value))


def _migrate_unique_id(hass, entry, mcu):
    """Entries created before v0.5.0 are keyed by host:port; key them by the
    controller MAC (as the config flow now does) so an IP change, or DHCP
    discovery, maps to the same entry. Retried at each setup until it works."""
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


async def async_setup_entry(hass: HomeAssistant, entry: ApolloConfigEntry) -> bool:
    api = ApolloAPI(
        async_get_clientsession(hass),
        entry.data["host"], entry.data["port"], entry.data["password"]
    )
    miner = ApolloCoordinator(hass, entry, api, "miner", MINER_INTERVAL, miner_fetcher(api))
    mcu = ApolloCoordinator(hass, entry, api, "mcu", MCU_INTERVAL, api.get_mcu, retain_one_failure=True)
    settings = ApolloCoordinator(hass, entry, api, "settings", SETTINGS_INTERVAL, api.get_settings)
    logs = ApolloCoordinator(hass, entry, api, "logs", LOG_INTERVAL, log_fetcher(api))

    # A rejected password fails setup and starts reauth. An unreachable miner
    # does not: entities are created and stay unavailable until it answers.
    try:
        await api.login()
    except ApolloAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ApolloAPIError:
        pass
    for coordinator in (miner, mcu, settings, logs):
        await coordinator.async_refresh()

    _migrate_unique_id(hass, entry, mcu.data)
    _sync_title(hass, entry)
    entry.runtime_data = ApolloData(
        api=api, miner=miner, mcu=mcu, settings=settings, logs=logs,
        monitor=GeneralErrorState(logs, miner, settings, api),
        restart_tracker=RestartTracker(miner, settings),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApolloConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
