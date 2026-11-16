"""Apollo III online state."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN
from .entity import ApolloEntity, miner_stats

class MinerOnline(ApolloEntity, BinarySensorEntity):
    def __init__(self, entry, coordinator):
        super().__init__(entry, coordinator, "online", "Miner online")

    @property
    def is_on(self):
        # Online means the miner service is up AND its stats are still updating.
        return miner_stats(self.coordinator.data) is not None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {"service_status": (data.get("online") or {}).get("status"),
                "stats_stale": data.get("stale"),
                "stats_unchanged_s": data.get("stats_unchanged_s")}

async def async_setup_entry(hass, entry, async_add_entities):
    # Shared monitor instance is registered during sensor setup, which may run concurrently.
    # The monitor is initialized once in __init__.py before platform forwarding.
    data = hass.data[DOMAIN][entry.entry_id]
    from .general_errors import MinerFault
    from .restart_needed import RestartNeeded
    async_add_entities([MinerOnline(entry, data["miner"]), MinerFault(entry, data["general_error_monitor"]),
                        RestartNeeded(entry, data["restart_tracker"])])
