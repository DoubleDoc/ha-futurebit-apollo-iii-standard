"""Apollo III config flow."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import ApolloAPI, ApolloAPIError
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT

class ApolloFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                api = ApolloAPI(
                    async_get_clientsession(self.hass),
                    user_input["host"], user_input["port"], user_input["password"]
                )
                await api.login()
                await self.async_set_unique_id(f"{user_input['host']}:{user_input['port']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Apollo III ({user_input['host']})", data=user_input)
            except ApolloAPIError:
                errors["base"] = "cannot_connect"
        schema = vol.Schema({
            vol.Required("host", default=DEFAULT_HOST): str,
            vol.Required("port", default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required("password"): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
