"""Performance mode and fan mode selectors.

These only save settings. The miner loads them at its next start; the
`Restart needed` binary sensor shows when saved settings are not yet running.
"""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .const import MODES
from .entity import ApolloEntity, is_set
from .api import ApolloAPIError

class ModeSelect(ApolloEntity, SelectEntity):
    _attr_options = MODES

    def __init__(self, entry, coordinator, api):
        super().__init__(entry, coordinator, "mode_select")
        self.api = api

    @property
    def current_option(self):
        return ((self.coordinator.data or {}).get("settings") or {}).get("minerMode")

    async def async_select_option(self, option):
        if option not in MODES:
            raise HomeAssistantError("Invalid mode")
        try:
            await self.api.update_settings({"minerMode": option})
            await self.coordinator.async_refresh()  # not debounced: show the change now
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err
        # Deliberately does not restart or start a stopped miner; see Restart needed.

FAN_AUTO, FAN_TEMP, FAN_PWM = "auto", "temperature", "fixed_pwm"
# Values the Apollo UI uses when a fan mode is first switched on.
DEFAULT_FAN_TEMP, DEFAULT_FAN_PWM = 50, 50


class FanModeSelect(ApolloEntity, SelectEntity):
    """Apollo III fan control: automatic, PID temperature target, or fixed PWM.

    The backend expresses "not set" as null, and a fixed PWM overrides the
    temperature target (configurator.js), which a number entity cannot show.
    """
    _attr_options = [FAN_AUTO, FAN_TEMP, FAN_PWM]

    def __init__(self, entry, coordinator, api):
        super().__init__(entry, coordinator, "fan_mode_select")
        self.api = api

    @property
    def _settings(self):
        return (self.coordinator.data or {}).get("settings") or {}

    @property
    def current_option(self):
        settings = self._settings
        if not settings:
            return None
        if is_set(settings.get("fanPwm")):
            return FAN_PWM
        if is_set(settings.get("fanTemp")):
            return FAN_TEMP
        return FAN_AUTO

    async def async_select_option(self, option):
        settings = self._settings
        if option == FAN_AUTO:
            changes = {"fanTemp": None, "fanPwm": None}
        elif option == FAN_TEMP:
            temp = settings.get("fanTemp")
            changes = {"fanPwm": None,
                       "fanTemp": int(float(temp)) if is_set(temp) else DEFAULT_FAN_TEMP}
        elif option == FAN_PWM:
            pwm = settings.get("fanPwm")
            changes = {"fanPwm": int(float(pwm)) if is_set(pwm) else DEFAULT_FAN_PWM}
        else:
            raise HomeAssistantError("Invalid fan mode")
        try:
            await self.api.update_settings(changes)
            await self.coordinator.async_refresh()  # not debounced: show the change now
        except ApolloAPIError as err:
            raise HomeAssistantError(str(err)) from err


async def async_setup_entry(hass, entry, async_add_entities):
    d=entry.runtime_data
    async_add_entities([ModeSelect(entry, d.settings, d.api),
                        FanModeSelect(entry, d.settings, d.api)])
