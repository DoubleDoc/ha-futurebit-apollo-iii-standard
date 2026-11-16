"""Apollo III config flow: manual setup, DHCP discovery, reconfigure, reauth.

The Apollo dashboard has a password but no username. A config entry is keyed
by the controller's MAC address, so an IP change is the same miner: DHCP
discovery updates the host of an existing entry automatically.
"""
import logging
import re
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector, NumberSelectorConfig, NumberSelectorMode,
    TextSelector, TextSelectorConfig, TextSelectorType,
)
from .api import ApolloAPI, ApolloAPIError, ApolloAuthError
from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
PORT = vol.All(
    NumberSelector(NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)),
    vol.Coerce(int),
)


async def validate(hass, host, port, password):
    """Log in and read the controller; return (unique_id, hostname)."""
    api = ApolloAPI(async_get_clientsession(hass), host, port, password)
    await api.login()
    mcu = await api.get_mcu()
    mac = ApolloAPI.device_mac(mcu)
    return (format_mac(mac) if mac else f"{host}:{port}"), mcu.get("hostname")


def is_mac(value):
    return bool(value) and bool(re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", value))


def _errors_for(err):
    if isinstance(err, ApolloAuthError):
        return {"base": "invalid_auth"}
    if isinstance(err, ApolloAPIError):
        return {"base": "cannot_connect"}
    _LOGGER.exception("Unexpected error validating Apollo III")
    return {"base": "unknown"}


class ApolloFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._host = None

    # ---- manual setup ------------------------------------------------------
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input["host"].strip()
            try:
                unique_id, _hostname = await validate(
                    self.hass, host, user_input["port"], user_input["password"])
            except Exception as err:  # noqa: BLE001 - mapped to form errors
                errors = _errors_for(err)
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Apollo III ({host})",
                    data={"host": host, "port": user_input["port"],
                          "password": user_input["password"]})
        defaults = user_input or {}
        schema = vol.Schema({
            vol.Required("host", default=defaults.get("host", "")): str,
            vol.Required("port", default=defaults.get("port", DEFAULT_PORT)): PORT,
            vol.Required("password"): PASSWORD,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ---- DHCP discovery ----------------------------------------------------
    async def async_step_dhcp(self, discovery_info):
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        # Same miner at a new address: update it and reload, no questions.
        self._abort_if_unique_id_configured(updates={"host": discovery_info.ip})
        self._host = discovery_info.ip
        self.context["title_placeholders"] = {"host": self._host}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                unique_id, _hostname = await validate(
                    self.hass, self._host, user_input["port"], user_input["password"])
            except Exception as err:  # noqa: BLE001
                errors = _errors_for(err)
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={"host": self._host})
                return self.async_create_entry(
                    title=f"Apollo III ({self._host})",
                    data={"host": self._host, "port": user_input["port"],
                          "password": user_input["password"]})
        schema = vol.Schema({
            vol.Required("port", default=DEFAULT_PORT): PORT,
            vol.Required("password"): PASSWORD,
        })
        return self.async_show_form(
            step_id="dhcp_confirm", data_schema=schema, errors=errors,
            description_placeholders={"host": self._host})

    async def _check_same_device(self, entry, unique_id):
        """Abort if the new address is a different miner. Entries created
        before v0.5.0 are keyed by host:port; adopt the MAC for those."""
        if is_mac(entry.unique_id):
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_mismatch(reason="wrong_device")
        elif is_mac(unique_id):
            self.hass.config_entries.async_update_entry(entry, unique_id=unique_id)

    # ---- change host / port / password ------------------------------------
    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            host = user_input["host"].strip()
            # A blank password keeps the current one.
            password = user_input.get("password") or entry.data["password"]
            try:
                unique_id, _hostname = await validate(self.hass, host, user_input["port"], password)
            except Exception as err:  # noqa: BLE001
                errors = _errors_for(err)
            else:
                await self._check_same_device(entry, unique_id)
                return self.async_update_reload_and_abort(
                    entry, data_updates={"host": host, "port": user_input["port"],
                                         "password": password})
        current = user_input or entry.data
        schema = vol.Schema({
            vol.Required("host", default=current.get("host", "")): str,
            vol.Required("port", default=current.get("port", DEFAULT_PORT)): PORT,
            vol.Optional("password"): PASSWORD,
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    # ---- password changed on the miner ------------------------------------
    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            try:
                unique_id, _hostname = await validate(
                    self.hass, entry.data["host"], entry.data["port"], user_input["password"])
            except Exception as err:  # noqa: BLE001
                errors = _errors_for(err)
            else:
                await self._check_same_device(entry, unique_id)
                return self.async_update_reload_and_abort(
                    entry, data_updates={"password": user_input["password"]})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required("password"): PASSWORD}),
            errors=errors, description_placeholders={"host": entry.data["host"]})
