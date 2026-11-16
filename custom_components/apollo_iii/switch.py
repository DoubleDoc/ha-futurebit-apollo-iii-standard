"""Apollo III requested mining state."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import ApolloEntity
from .api import ApolloAPIError

class MiningSwitch(ApolloEntity, SwitchEntity):
    def __init__(self, entry, coordinator, api):
        super().__init__(entry, coordinator, "mining_switch", "Mining enabled")
        self.api = api

    @property
    def is_on(self):
        services = (self.coordinator.data or {}).get("services") or []
        service = next((x for x in services if x.get("serviceName")=="miner"), {})
        requested = service.get("requestedStatus")
        if requested in ("online","offline"):
            return requested == "online"
        return service.get("status") == "online"

    async def _command(self, action):
        try:
            await self.api.miner_command(action)
            await self.coordinator.async_request_refresh()
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs):
        await self._command("start")

    async def async_turn_off(self, **kwargs):
        await self._command("stop")

async def async_setup_entry(hass, entry, async_add_entities):
    d=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MiningSwitch(entry,d["settings"],d["api"])])
