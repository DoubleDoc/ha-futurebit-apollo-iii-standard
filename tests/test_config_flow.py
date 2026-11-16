"""Config flow: user, DHCP, reconfigure, reauth."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.apollo_iii.const import DOMAIN

from .conftest import HOST, MAC, PASSWORD, PORT

USER_INPUT = {"host": HOST, "port": PORT, "password": PASSWORD}


async def test_user_flow_creates_entry(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Apollo III Standard ({HOST})"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == MAC


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"password": "wrong"}, "invalid_auth"),
        ({"unreachable": True}, "cannot_connect"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, fake_miner, mock_setup_entry, change, error
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    if change.get("unreachable"):
        fake_miner.unreachable = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "password": change.get("password", PASSWORD)})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    fake_miner.unreachable = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unknown_error(hass: HomeAssistant, fake_miner, mock_setup_entry, monkeypatch) -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("custom_components.apollo_iii.config_flow.validate", boom)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(hass: HomeAssistant, fake_miner, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


DHCP = DhcpServiceInfo(ip=HOST, hostname="futurebit-apollo-3", macaddress=MAC.replace(":", ""))


async def test_dhcp_discovery_new_miner(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dhcp_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"port": PORT, "password": PASSWORD})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == HOST
    assert result["result"].unique_id == MAC


async def test_dhcp_updates_host_of_known_miner(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, title="Apollo III Standard (192.0.2.1)",
                            data={"host": "192.0.2.1", "port": PORT, "password": PASSWORD})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == HOST


async def test_reconfigure_changes_host_keeps_password(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, title="Apollo III Standard (192.0.2.99)",
                            data={"host": "192.0.2.99", "port": PORT, "password": PASSWORD})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "port": PORT})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {"host": HOST, "port": PORT, "password": PASSWORD}


async def test_reconfigure_rejects_other_miner(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="aa:bb:cc:dd:ee:99", title="x",
                            data={"host": HOST, "port": PORT, "password": PASSWORD})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "port": PORT})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reconfigure_adopts_mac_for_legacy_entry(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"{HOST}:{PORT}", title="x",
                            data={"host": HOST, "port": PORT, "password": PASSWORD})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "port": PORT})
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == MAC


async def test_reauth(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, title="x",
                            data={"host": HOST, "port": PORT, "password": "old-password"})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "still-wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": PASSWORD})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == PASSWORD


async def test_dhcp_confirm_error(hass: HomeAssistant, fake_miner, mock_setup_entry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"port": PORT, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_error(hass: HomeAssistant, fake_miner, mock_setup_entry, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    fake_miner.unreachable = True
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "port": PORT})
    assert result["errors"] == {"base": "cannot_connect"}
