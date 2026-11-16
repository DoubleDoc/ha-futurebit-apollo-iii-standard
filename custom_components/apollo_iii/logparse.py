"""Parse the Apollo III miner log snapshot.

The backend's MINER log is a `screen` hardcopy of the miner's terminal, not a
log file: about 25 lines, with long lines hard-wrapped at 80 columns. A wrapped
continuation has no timestamp and must be joined to the line before it, with
no separator (numbers can be split across the wrap).
"""
import re

SESSION = re.compile(r"^=== Session ([^\s=]+) ===$")
STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):\s*(.*)$")

DVFS_STATE = re.compile(
    r"DVFS: state (\w+), tune (\w+), target ([\d.]+) TH/s(?:, voltage ([\d.]+)V)?")
DVFS_FAN = re.compile(r"DVFS: fan \d+ PWM (\d+)% speed (\d+) RPM")
DVFS_HIT = re.compile(r"DVFS: hitrate ([\d.]+)")
DVFS_POWER = re.compile(r"DVFS: avg_temp .*?power ([\d.]+)")


def entries(content):
    """Return [(session, 'YYYY-MM-DD HH:MM:SS', message)] with wraps joined."""
    out = []
    session = None
    if not isinstance(content, str):
        return out
    for line in content.splitlines():
        header = SESSION.match(line)
        if header:
            session = header.group(1)
            continue
        stamp = STAMP.match(line)
        if stamp:
            out.append([session, stamp.group(1), stamp.group(2)])
        elif out and out[-1][0] == session and line:
            # Continuation of a wrapped line. A fragment before the first
            # timestamp of a session belongs to a line that scrolled off.
            out[-1][2] += line
    return [tuple(e) for e in out if e[0] is not None]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_dvfs(items):
    """Latest DVFS values from parsed entries; missing keys mean not seen."""
    result = {}
    for _session, stamp, message in items:
        if not message.startswith("DVFS:"):
            continue
        result["stamp"] = stamp
        if m := DVFS_STATE.search(message):
            result["state"], result["tune"] = m.group(1), m.group(2)
            result["target_ths"] = _num(m.group(3))
            if m.group(4):
                result["voltage"] = _num(m.group(4))
        elif m := DVFS_FAN.search(message):
            result["fan_pwm"] = int(m.group(1))
        elif m := DVFS_HIT.search(message):
            result["hitrate"] = _num(m.group(1))
        elif m := DVFS_POWER.search(message):
            result["power"] = _num(m.group(1))
    return result
