"""Controls send the right settings and commands, and Restart needed follows."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .test_init import setup


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_performance_mode_saves_and_flags_restart(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    await call(hass, "select", "select_option", "select.futurebit_apollo_iii_performance_mode", option="turbo")
    assert fake_miner.updates[-1] == {"minerMode": "turbo"}
    assert fake_miner.commands == []  # never restarts the miner itself
    restart = hass.states.get("binary_sensor.futurebit_apollo_iii_restart_needed")
    assert restart.state == "on"
    assert restart.attributes["pending_changes"] == ["Power mode: super_eco → turbo"]


async def test_custom_hashrate_in_preset_mode_needs_no_restart(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    await call(hass, "number", "set_value", "number.futurebit_apollo_iii_custom_mode_target_hashrate", value=16)
    assert fake_miner.updates[-1] == {"minerHashrate": 16}
    assert hass.states.get("binary_sensor.futurebit_apollo_iii_restart_needed").state == "off"


async def test_fan_mode(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    await call(hass, "select", "select_option", "select.futurebit_apollo_iii_fan_mode", option="fixed_pwm")
    assert fake_miner.updates[-1] == {"fanPwm": 50}
    assert hass.states.get("select.futurebit_apollo_iii_fan_mode").state == "fixed_pwm"
    await call(hass, "select", "select_option", "select.futurebit_apollo_iii_fan_mode", option="temperature")
    assert fake_miner.updates[-1] == {"fanPwm": None, "fanTemp": 50}
    await call(hass, "select", "select_option", "select.futurebit_apollo_iii_fan_mode", option="auto")
    assert fake_miner.updates[-1] == {"fanTemp": None, "fanPwm": None}
    assert hass.states.get("select.futurebit_apollo_iii_fan_mode").state == "auto"


async def test_switch_and_buttons(hass: HomeAssistant, fake_miner, config_entry) -> None:
    await setup(hass, config_entry)
    await call(hass, "switch", "turn_off", "switch.futurebit_apollo_iii_mining_enabled")
    await call(hass, "switch", "turn_on", "switch.futurebit_apollo_iii_mining_enabled")
    await call(hass, "button", "press", "button.futurebit_apollo_iii_restart_miner")
    assert fake_miner.commands == ["stop", "start", "restart"]
