"""Apollo III custom tuning controls.

These only save settings; the miner loads them at its next start (see the
Restart needed binary sensor). Setting a fan PWM turns on fixed-PWM mode, which
overrides the temperature target; use the Fan mode select to go back.
"""
from homeassistant.components.number import NumberEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import ApolloEntity
from .api import ApolloAPIError

FIELDS = [
    ("minerHashrate", 5, 20, 1, "TH/s"),
    ("fanTemp", 40, 80, 1, "°C"),
    ("fanPwm", 10, 100, 1, "%"),
]

class SettingNumber(ApolloEntity, NumberEntity):
    def __init__(self, entry, coordinator, api, spec):
        field, minimum, maximum, step, unit = spec
        super().__init__(entry, coordinator, "set_"+field)
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
            await self.coordinator.async_refresh()  # not debounced: show the change now
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err

async def async_setup_entry(hass, entry, async_add_entities):
    d=entry.runtime_data
    async_add_entities([SettingNumber(entry,d.settings,d.api,s) for s in FIELDS])
