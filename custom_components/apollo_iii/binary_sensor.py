"""Apollo III online state."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN
from .entity import ApolloEntity

class MinerOnline(ApolloEntity, BinarySensorEntity):
    def __init__(self, entry, coordinator):
        super().__init__(entry, coordinator, "online", "Miner online")

    @property
    def is_on(self):
        return ((self.coordinator.data or {}).get("online") or {}).get("status") == "online"

async def async_setup_entry(hass, entry, async_add_entities):
    # Shared monitor instance is registered during sensor setup, which may run concurrently.
    # The monitor is initialized once in __init__.py before platform forwarding.
    data = hass.data[DOMAIN][entry.entry_id]
    from .general_errors import MinerFault
    async_add_entities([MinerOnline(entry, data["miner"]), MinerFault(entry, data["general_error_monitor"])])
