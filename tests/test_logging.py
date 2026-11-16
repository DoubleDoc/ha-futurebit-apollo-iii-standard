"""Debug logging: useful messages, and never a secret."""
from __future__ import annotations

import logging

import pytest

from homeassistant.core import HomeAssistant

from .conftest import MAC, PASSWORD
from .test_controls import call
from .test_init import setup
from .test_monitors import clock, miner_data, monitor, run  # noqa: F401  (fixtures)

LOGGER = "custom_components.apollo_iii"
SECRETS = (PASSWORD, MAC, "bc1qexample", "Bearer", "token")


def assert_no_secrets(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"{secret!r} leaked into the log"


@pytest.fixture
def debug_log(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    return caplog


async def test_setup_and_polling_are_logged(hass: HomeAssistant, fake_miner, config_entry, debug_log) -> None:
    await setup(hass, config_entry)
    text = debug_log.text
    for expected in ("Logging in to http://", "Logged in", "Auth.login took",
                     "Miner poll: service online", "Log snapshot:", "DVFS fresh (target 8.0 TH/s",
                     "Running settings recorded"):
        assert expected in text, expected
    assert_no_secrets(text)


async def test_controls_are_logged(hass: HomeAssistant, fake_miner, config_entry, debug_log) -> None:
    await setup(hass, config_entry)
    await call(hass, "select", "select_option", "select.futurebit_apollo_iii_performance_mode", option="turbo")
    await call(hass, "button", "press", "button.futurebit_apollo_iii_restart_miner")
    text = debug_log.text
    assert "Saving settings {'minerMode': 'turbo'}" in text
    assert "Restart needed: Power mode: super_eco → turbo" in text
    assert "Sending miner command: restart" in text
    assert "Settings.update took" in text and "Miner.restart took" in text
    for routine in ("Settings.read took", "Miner.stats took", "Mcu.stats took", "Logs.read took"):
        assert routine not in text  # routine polls are not timed twice
    assert_no_secrets(text)


async def test_wrong_password_is_logged_without_the_password(
    hass: HomeAssistant, fake_miner, config_entry, debug_log
) -> None:
    fake_miner.password = "something-else"
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert "Auth.login returned GraphQL errors: Invalid password" in debug_log.text
    assert_no_secrets(debug_log.text)


async def test_unreachable_miner_is_logged(hass: HomeAssistant, fake_miner, config_entry, debug_log) -> None:
    fake_miner.unreachable = True
    await setup(hass, config_entry)
    assert "failed (unreachable); retrying once" in debug_log.text
    assert "Miner not reachable at setup" in debug_log.text


def test_fault_monitor_decisions_are_logged(monitor, clock, debug_log) -> None:  # noqa: F811
    run(monitor, clock, lambda c: miner_data(c, error_rate=9.0), 90)
    run(monitor, clock, miner_data, 15)
    run(monitor, clock, lambda c: miner_data(c, uptime=100), 15)
    text = debug_log.text
    assert "Condition high_error_rate started; counts if it lasts 60 s" in text
    assert "Incident #1 counted (hardware): High chip error rate" in text
    assert "Condition high_error_rate cleared after" in text
    assert "Miner restart seen: uptime 1000000 s -> 100 s (not requested)" in text
