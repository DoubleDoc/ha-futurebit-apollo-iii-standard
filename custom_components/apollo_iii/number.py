"""Apollo III custom tuning controls."""
from homeassistant.components.number import NumberEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import ApolloEntity
from .api import ApolloAPIError

FIELDS = [
    ("minerHashrate", "Target hashrate", 5, 20, 1, "TH/s"),
    ("fanTemp", "Fan temperature target", 40, 80, 1, "°C"),
    ("fanPwm", "Fan PWM target", 10, 100, 1, "%"),
]

class SettingNumber(ApolloEntity, NumberEntity):
    def __init__(self, entry, coordinator, api, spec):
        field, name, minimum, maximum, step, unit = spec
        super().__init__(entry, coordinator, "set_"+field, name)
        self.field, self.api = field, api
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return ((self.coordinator.data or {}).get("settings") or {}).get(self.field)

    async def async_set_native_value(self, value):
        try:
            await self.api.update_settings({self.field: int(value)})
            await self.coordinator.async_request_refresh()
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err

async def async_setup_entry(hass, entry, async_add_entities):
    d=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SettingNumber(entry,d["settings"],d["api"],s) for s in FIELDS])
