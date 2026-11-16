"""Shared Apollo III entity."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class ApolloEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, coordinator, key, name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="FutureBit Apollo III",
            manufacturer="FutureBit",
            model="Apollo III",
            configuration_url=f"http://{entry.data['host']}/",
        )
