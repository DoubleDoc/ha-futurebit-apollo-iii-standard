"""Performance mode selector."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, MODES
from .entity import ApolloEntity
from .api import ApolloAPIError

class ModeSelect(ApolloEntity, SelectEntity):
    _attr_options = MODES

    def __init__(self, entry, coordinator, api):
        super().__init__(entry, coordinator, "mode_select", "Performance mode")
        self.api = api

    @property
    def current_option(self):
        return ((self.coordinator.data or {}).get("settings") or {}).get("minerMode")

    async def async_select_option(self, option):
        if option not in MODES:
            raise HomeAssistantError("Invalid mode")
        try:
            await self.api.update_settings({"minerMode": option})
            await self.coordinator.async_request_refresh()
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err
        # Deliberately does not restart or start a stopped miner.

async def async_setup_entry(hass, entry, async_add_entities):
    d=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ModeSelect(entry, d["settings"], d["api"])])
