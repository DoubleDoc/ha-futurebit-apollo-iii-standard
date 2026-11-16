"""Screen-snapshot parsing and DVFS values."""
from custom_components.apollo_iii.logparse import entries, parse_dvfs

from .conftest import load

SNAPSHOT = """=== Session 1478.miner ===
, voltage 5.195V
2026-11-15 21:33:28: DVFS: avg_volt 1:0.2404 2:0.0000 3:0.0000 min 1:0.2310 2:0.
0000 3:0.0000 max 1:0.2452 2:0.0000 3:0.0000
2026-11-15 21:33:28: DVFS: fan 1 PWM 13% speed 1460 RPM
2026-11-15 21:33:28: DVFS: hitrate 0.993, boardspeeds [8014], total 8.01
2026-11-15 21:33:31: DVFS: state NORMAL, tune TUNE_STEPPING_UP, target 8.00 TH/s
, voltage 5.195V
2026-11-15 21:33:31: DVFS: avg_temp 55.12, max_temp 57.00 (1/1), power 92.1
"""


def test_wrapped_lines_are_joined_and_orphans_dropped() -> None:
    items = entries(SNAPSHOT)
    assert items[0] == ("1478.miner", "2026-11-15 21:33:28",
                        "DVFS: avg_volt 1:0.2404 2:0.0000 3:0.0000 min 1:0.2310 2:0.0000 3:0.0000 "
                        "max 1:0.2452 2:0.0000 3:0.0000")
    assert items[3][2] == "DVFS: state NORMAL, tune TUNE_STEPPING_UP, target 8.00 TH/s, voltage 5.195V"
    assert len(items) == 5


def test_parse_dvfs() -> None:
    dvfs = parse_dvfs(entries(SNAPSHOT))
    assert dvfs == {"stamp": "2026-11-15 21:33:31", "chip_voltage": 0.2404, "fan_pwm": 13,
                    "hitrate": 0.993, "state": "NORMAL", "tune": "TUNE_STEPPING_UP",
                    "target_ths": 8.0, "voltage": 5.195, "power": 92.1}


def test_tuner_action_is_recorded() -> None:
    text = "=== Session 1.miner ===\n2026-11-16 03:30:00: DVFS: lower down voltage to 5.180board 1\n"
    assert parse_dvfs(entries(text))["last_action"].startswith("2026-11-16 03:30:00 lower down voltage")


def test_live_fixture_parses() -> None:
    dvfs = parse_dvfs(entries(load("logs")["Logs"]["read"]["result"]["content"]))
    assert dvfs["target_ths"] > 0
    assert dvfs["tune"].startswith("TUNE_")


def test_garbage_is_ignored() -> None:
    assert entries(None) == []
    assert parse_dvfs(entries("no session header\n2026-01-01 00:00:00: x")) == {}
