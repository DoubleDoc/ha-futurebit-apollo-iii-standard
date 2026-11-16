"""Setup, entities, migration, reauth, unload and diagnostics."""
from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.apollo_iii.const import DOMAIN

from .conftest import HOST, MAC, PASSWORD, PORT


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_entities(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    stats = fake_miner.stats

    hashrate = hass.states.get("sensor.futurebit_apollo_iii_hashrate")
    assert hashrate is not None
    assert hashrate.attributes["friendly_name"] == "FutureBit Apollo III Hashrate"
    assert float(hashrate.state) == round(stats["slots"]["int_0"]["ghs"] * 0.001, 4)

    error_rate = hass.states.get("sensor.futurebit_apollo_iii_chip_error_rate_5_min")
    assert float(error_rate.state) == stats["master"]["intervals"]["int_300"]["errorRate"]

    assert hass.states.get("binary_sensor.futurebit_apollo_iii_miner_online").state == "on"
    assert hass.states.get("binary_sensor.futurebit_apollo_iii_miner_fault").state == "off"
    assert hass.states.get("binary_sensor.futurebit_apollo_iii_restart_needed").state == "off"
    assert hass.states.get("select.futurebit_apollo_iii_performance_mode").state == fake_miner.saved["minerMode"]
    assert hass.states.get("select.futurebit_apollo_iii_fan_mode").state == "auto"
    assert hass.states.get("sensor.futurebit_apollo_iii_hashrate_target").state == "8.0"
    assert hass.states.get("sensor.futurebit_apollo_iii_board_voltage").state == "5.195"
    assert hass.states.get("switch.futurebit_apollo_iii_mining_enabled").state == "on"

    entities = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert len(entities) > 60
    unavailable = [e.entity_id for e in entities
                   if (s := hass.states.get(e.entity_id)) and s.state == "unavailable"]
    assert unavailable == []


async def test_stale_stats_make_miner_sensors_unavailable(hass: HomeAssistant, fake_miner, config_entry) -> None:
    fake_miner.stats["date"] = "2020-01-01T00:00:00+00:00"
    original = fake_miner.answer

    def frozen(query, variables):
        result = original(query, variables)
        if "Miner" in query and "stats" in query:
            result["data"]["Miner"]["stats"]["result"]["stats"][0]["date"] = "2020-01-01T00:00:00+00:00"
        return result

    fake_miner.answer = frozen
    await setup(hass, config_entry)
    assert hass.states.get("sensor.futurebit_apollo_iii_hashrate").state == "unavailable"
    online = hass.states.get("binary_sensor.futurebit_apollo_iii_miner_online")
    assert online.state == "off"
    assert online.attributes["stats_stale"] is True


async def test_wrong_password_starts_reauth(hass: HomeAssistant, fake_miner, config_entry) -> None:
    fake_miner.password = "changed-on-the-miner"
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unreachable_miner_still_sets_up(hass: HomeAssistant, fake_miner, config_entry) -> None:
    fake_miner.unreachable = True
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.futurebit_apollo_iii_hashrate").state == "unavailable"


async def test_legacy_entry_migrates_unique_id_and_title(hass: HomeAssistant, fake_miner) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"{HOST}:{PORT}", title="Apollo III (192.0.2.1)",
                            data={"host": HOST, "port": PORT, "password": PASSWORD})
    await setup(hass, entry)
    assert entry.unique_id == MAC
    assert entry.title == f"Apollo III Standard ({HOST})"


async def test_custom_title_is_kept(hass: HomeAssistant, fake_miner) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, title="Garage Apollo",
                            data={"host": HOST, "port": PORT, "password": PASSWORD})
    await setup(hass, entry)
    assert entry.title == "Garage Apollo"


async def test_unload(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_secrets(hass: HomeAssistant, hass_client, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    text = str(diag)
    assert PASSWORD not in text
    assert MAC not in text
    assert "bc1q" not in text
    assert diag["entry"]["data"]["password"] == "**REDACTED**"
    assert diag["coordinators"]["miner"]["last_update_success"] is True
    assert diag["fault_monitor"]["active_conditions"] == []
