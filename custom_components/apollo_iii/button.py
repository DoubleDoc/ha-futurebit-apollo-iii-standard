"""Apollo III miner actions."""
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import ApolloEntity
from .api import ApolloAPIError

class MinerButton(ApolloEntity, ButtonEntity):
    def __init__(self, entry, coordinator, api, action):
        super().__init__(entry, coordinator, f"button_{action}")
        self.action, self.api = action, api

    async def async_press(self):
        try:
            await self.api.miner_command(self.action)
            await self.coordinator.async_refresh()  # not debounced: show the change now
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err

async def async_setup_entry(hass, entry, async_add_entities):
    d=entry.runtime_data
    async_add_entities([MinerButton(entry,d.settings,d.api,action)
                        for action in ("start","stop","restart")])
