"""Fault monitor, Restart needed and Tuning state logic, without a running Home Assistant."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import types

import pytest

from custom_components.apollo_iii import general_errors as GE
from custom_components.apollo_iii import restart_needed as RN
from custom_components.apollo_iii import sensor as SN

from .conftest import load


class Coord:
    def __init__(self, data=None):
        self.data = data
        self.last_update_success = True
        self.hass = None

    def async_add_listener(self, update):
        return lambda: None

    async def async_request_refresh(self):
        return None


class Clock:
    def __init__(self):
        self.mono = 1000.0
        self.utc = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)

    def advance(self, seconds):
        self.mono += seconds
        self.utc += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(GE.time, "monotonic", lambda: c.mono)
    monkeypatch.setattr(GE.dt_util, "utcnow", lambda: c.utc)
    monkeypatch.setattr(SN.dt_util, "utcnow", lambda: c.utc)
    return c


def miner_data(clock, uptime=1_000_000, ghs=8000.0, error_rate=0.7, error_now=None, reconnects=0,
               online=True, stale=False):
    raw = load("miner")
    stats = raw["Miner"]["stats"]["result"]["stats"]
    s = stats[0]
    s["date"] = clock.utc.isoformat()
    s["master"]["upTime"] = uptime
    s["master"]["intervals"]["int_30"]["bySol"] = ghs
    s["master"]["intervals"]["int_300"]["bySol"] = ghs
    s["master"]["intervals"]["int_300"]["errorRate"] = error_rate
    s["master"]["intervals"]["int_30"]["errorRate"] = error_rate if error_now is None else error_now
    s["slots"]["int_0"]["ghs"] = ghs
    s["pool"]["intervals"]["int_0"]["reconnections"] = reconnects
    return {"online": {"status": "online" if online else "offline"}, "stats": stats, "stale": stale}


def settings_data(requested="online", requested_at="2026-11-05T23:13:47Z", **saved):
    base = {"minerMode": "super_eco", "minerHashrate": 14, "fanTemp": None, "fanPwm": None}
    base.update(saved)
    return {"settings": base, "services": [{"serviceName": "miner", "status": "online",
                                            "requestedStatus": requested, "requestedAt": requested_at}]}


@pytest.fixture
def monitor(clock):
    m = GE.GeneralErrorState(Coord({"entries": [], "dvfs": {"target_ths": 8.0}}),
                             Coord(miner_data(clock)), Coord(settings_data()),
                             types.SimpleNamespace(last_write=None))
    m.ready = True
    m.update()
    return m


def run(monitor, clock, data, seconds, step=15):
    for _ in range(int(seconds / step)):
        clock.advance(step)
        monitor.miner.data = data(clock) if callable(data) else data
        monitor.update()


def test_healthy_miner_has_no_fault(monitor, clock) -> None:
    run(monitor, clock, miner_data, 600)
    assert monitor.count == 0 and not monitor.active


def test_pool_reconnect_counts_once(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, reconnects=1), 60)
    assert monitor.count == 1
    assert monitor.last_text == "Pool reconnected (1 this miner run)"


@pytest.mark.parametrize(
    ("kwargs", "rule", "hold"),
    [
        ({"error_rate": 9.0}, "high_error_rate", 60),
        ({"ghs": 0}, "no_hashrate", 30),
        ({"ghs": 3000.0}, "low_hashrate", 300),
    ],
)
def test_condition_counts_after_hold_and_clears(monitor, clock, kwargs, rule, hold) -> None:
    run(monitor, clock, lambda c: miner_data(c, **kwargs), hold - 15)
    assert monitor.count == 0
    run(monitor, clock, lambda c: miner_data(c, **kwargs), 45)
    assert monitor.active_conditions == [rule]
    assert monitor.count == 1 and monitor.active
    run(monitor, clock, lambda c: miner_data(c, **kwargs), 300)
    assert monitor.count == 1  # once per episode
    run(monitor, clock, miner_data, 15)
    assert monitor.active_conditions == [] and not monitor.active


def test_startup_errors_are_not_a_fault(monitor, clock) -> None:
    """Live case: a mode change from HA restarted the miner; at 4 minutes of
    uptime the 5-minute error rate read 11.9 % while the 30 s rate was 0.2 %."""
    monitor.api.last_write = clock.mono  # mode change + restart sent from HA
    start = clock.mono
    run(monitor, clock, lambda c: miner_data(c, uptime=c.mono - start, error_rate=11.9,
                                             error_now=15.0), 240)
    run(monitor, clock, lambda c: miner_data(c, uptime=c.mono - start, error_rate=11.9,
                                             error_now=0.2), 300)
    assert monitor.count == 0 and not monitor.active


def test_high_errors_after_startup_still_count(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, uptime=1_000_000 + c.mono, error_rate=9.0,
                                             error_now=9.0), 120)
    assert monitor.active_conditions == ["high_error_rate"] and monitor.count == 1


def test_error_spike_already_over_is_not_a_fault(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, uptime=1_000_000 + c.mono, error_rate=9.0,
                                             error_now=0.5), 300)
    assert monitor.count == 0 and not monitor.active


def test_frozen_stats(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, stale=True), 90)
    assert monitor.active_conditions == ["stats_stale"]


def test_unexpected_restart_counts_requested_does_not(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, uptime=100), 15)
    assert monitor.last_text == "Miner restarted unexpectedly" and monitor.count == 1
    run(monitor, clock, miner_data, 15)
    monitor.api.last_write = clock.mono
    run(monitor, clock, lambda c: miner_data(c, uptime=100), 15)
    assert monitor.count == 1


def test_deliberately_stopped_is_not_a_fault(monitor, clock) -> None:
    monitor.settings.data = settings_data(requested="offline")
    run(monitor, clock, lambda c: miner_data(c, online=False), 600)
    assert monitor.count == 0 and not monitor.active


def test_not_running(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, online=False), 150)
    assert monitor.active_conditions == ["not_running"]


def test_warmup_survives_clock_jump_after_reboot(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, uptime=60, ghs=0), 15)
    # NTP jumps the controller clock: upTime suddenly reads weeks.
    run(monitor, clock, lambda c: miner_data(c, uptime=2_500_000, ghs=0), 180)
    assert "no_hashrate" not in monitor.active_conditions
    run(monitor, clock, lambda c: miner_data(c, uptime=2_500_000, ghs=0), 180)
    assert "no_hashrate" in monitor.active_conditions


def test_active_condition_not_recounted_after_ha_restart(monitor, clock) -> None:
    run(monitor, clock, lambda c: miner_data(c, online=False), 150)
    attrs = {"incident_keys": list(monitor.keys), "active_conditions": monitor.active_conditions}
    fresh = GE.GeneralErrorState(monitor.logs, monitor.miner, monitor.settings, monitor.api)
    fresh.restore(attrs, monitor.count)
    fresh.ready = True
    run(fresh, clock, lambda c: miner_data(c, online=False), 300)
    assert fresh.count == monitor.count


# ---- Restart needed ---------------------------------------------------------

def tracker_for(clock, uptime=1000, **saved):
    miner = Coord(miner_data(clock, uptime=uptime))
    settings = Coord(settings_data(**saved))
    t = RN.RestartTracker(miner, settings)
    t.start()
    return t, miner, settings


def test_restart_needed_follows_saved_settings(clock) -> None:
    t, miner, settings = tracker_for(clock)
    assert not t.needed
    settings.data = settings_data(minerHashrate=16)  # ignored outside custom mode
    assert not t.needed
    settings.data = settings_data(minerMode="turbo")
    assert t.needed and t.changes == ["Power mode: super_eco → turbo"]
    miner.data = miner_data(clock, uptime=20)
    t._miner_update()
    assert not t.needed  # waiting for a settings read after the restart
    t._settings_update()
    assert not t.needed and t.applied["power_mode"] == "turbo"


def test_restart_needed_restores_same_run(clock) -> None:
    t, miner, settings = tracker_for(clock)
    settings.data = settings_data(fanPwm=60)
    attrs = {"running_settings": t.applied, "run_start": t.run_start.isoformat()}
    t2 = RN.RestartTracker(Coord(miner_data(clock, uptime=1015)), settings)
    t2.restore(attrs)
    t2.start()
    assert t2.baseline == "restored"
    assert t2.changes == ["Fan control: automatic → fixed PWM 60%"]


def test_effective_settings() -> None:
    assert RN.effective({"minerMode": "custom", "minerHashrate": None}) == {"power_mode": "eco", "fan": "automatic"}
    assert RN.effective({"minerMode": "custom", "minerHashrate": 99, "fanTemp": 55}) == {
        "power_mode": "custom 20 TH/s", "fan": "temperature target 55 °C"}
    assert RN.effective({"minerMode": "eco", "fanPwm": 0, "fanTemp": 0})["fan"] == "automatic"


# ---- Tuning state -----------------------------------------------------------

def test_tuning_state(clock) -> None:
    logs = Coord({"dvfs": {"tune": "TUNE_STEPPING_UP", "voltage": 5.195}, "dvfs_stale": False})
    miner = Coord(miner_data(clock))
    t = SN.TuningActivity(types.SimpleNamespace(entry_id="x", data={"host": "h"}), logs, miner)

    def step(minutes):
        clock.advance(minutes * 60)
        t._observe()
        return t.native_value

    assert step(0) is None
    assert step(11) == "holding"
    miner.data = miner_data(clock)
    miner.data["stats"][0]["master"]["osc"] = 415
    assert step(1) == "adjusting"
    assert step(11) == "holding"
    logs.data = {"dvfs": {"voltage": 5.195, "last_action": "x lower down voltage"}, "dvfs_stale": False}
    assert step(1) == "adjusting"
