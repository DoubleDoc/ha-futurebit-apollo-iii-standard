"""General-purpose miner fault monitor (read-only).

Two sources feed one incident counter:

1. Counter and state checks on the miner stats (every miner poll). These are
   the primary signal, because the MINER "log" is only a ~25-line screen
   snapshot that scrolls in seconds (see logparse.py). Conditions (stats stale,
   no hashrate, low hashrate, high chip error rate, board not powered, miner not
   running) count once per episode and keep the fault on while they last.
   Events (pool reconnection, unexpected miner restart) count once each.
2. Error messages that happen to be on screen when the log is polled. Known
   fatal errors count once per session; other messages once per distinct
   message per session. Repeating lines do not inflate totals.

Any incident also latches the fault until positive hashrate on fresh stats
confirms recovery. A miner deliberately stopped, or restarted/reconfigured
within FAULT_INTENTIONAL_WINDOW, is not a fault.
"""
from collections import deque
from datetime import datetime, timedelta
import re
import time
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from .entity import ApolloEntity, miner_stats
from .const import (FAULT_ERROR_RATE, FAULT_LOW_HASHRATE, FAULT_STARTUP_GRACE,
                    FAULT_LOW_HASHRATE_GRACE, FAULT_INTENTIONAL_WINDOW)

ASIC = re.compile(r"no ASIC is detected for brd\s+\d+", re.I)
# These are candidate patterns, not claims that all Apollo III versions emit them.
RULES = (
    ("asic", ASIC, True),
    ("thermal", re.compile(r"(?:over.?temp|overheat|thermal (?:shutdown|fault)|temperature (?:sensor )?(?:fault|error))", re.I), False),
    ("power", re.compile(r"(?:PSU|power supply|voltage|over.?current).*?(?:fault|fail(?:ed|ure)?|error|shutdown)|(?:fault|fail(?:ed|ure)?|error).*?(?:PSU|power supply)", re.I), False),
    ("pool", re.compile(r"(?:stratum|pool).*?(?:error|fail(?:ed|ure)?|disconnect|timeout|refused)|(?:error|fail(?:ed|ure)?|timeout).*?(?:stratum|pool)", re.I), False),
    ("process", re.compile(r"(?:miner|process).*?(?:crash|fatal|panic|terminated unexpectedly)|(?:fatal|panic).*?(?:miner|process)", re.I), True),
)
GENERIC = re.compile(r"\b(?:fatal|panic|exception|error|failed|failure)\b", re.I)
EXCLUDE = re.compile(r"(?:\b0\s+errors?\b|\berror\s*(?:rate|count|code)\s*[:=]\s*0\b|\bno\s+errors?\b)", re.I)
MAX_KEYS = 80

# rule: (category, fatal, seconds the condition must hold before it counts, text)
CONDITIONS = {
    "not_running": ("process", True, 120, "Miner not running"),
    "stats_stale": ("process", True, 60, "Miner stats stopped updating"),
    "no_hashrate": ("hardware", False, 30, "No hashrate"),
    "low_hashrate": ("performance", False, 300, "Hashrate below half of target"),
    "high_error_rate": ("hardware", False, 60, "High chip error rate"),
    "board_unpowered": ("asic", True, 60, "Hashboard not powered"),
}
# Conditions expected for a while after a requested restart or setting change.
TRANSITIONAL = {"not_running", "stats_stale"}


def classify(message):
    if EXCLUDE.search(message):
        return None
    for category, pattern, fatal in RULES:
        if pattern.search(message):
            return category, fatal
    if GENERIC.search(message):
        return "unclassified", False
    return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(stamp):
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else None


def _hashrate_ghs(stats):
    intervals = (stats.get("master") or {}).get("intervals") or {}
    value = _num((intervals.get("int_30") or {}).get("bySol"))
    if value is None:
        value = _num(((stats.get("slots") or {}).get("int_0") or {}).get("ghs"))
    return value


class GeneralErrorState:
    def __init__(self, logs, miner, settings, api):
        self.logs, self.miner, self.settings, self.api = logs, miner, settings, api
        self.count = 0
        self.failed_sessions = 0
        self.last_text = None
        self.last_time = None
        self.last_category = None
        self.latched = False
        self.ready = False
        self.keys = deque(maxlen=MAX_KEYS)
        self.seen = set()
        self.failed_ids = deque(maxlen=MAX_KEYS)
        self.failed_seen = set()
        self.entities = []
        # Condition rule -> monotonic time it was first seen true.
        self.cond_since = {}
        # Conditions already counted in their current episode (restored).
        self.cond_counted = set()
        # Previous miner sample, for event detection.
        self.run = None
        self.prev_uptime = None
        self.prev_reconnects = None
        # Monotonic time HA saw the miner restart (uptime went backwards).
        self.restart_seen = None
        logs.async_add_listener(self.update)
        miner.async_add_listener(self.update)

    # ---- persistence -------------------------------------------------------
    def restore(self, attrs, value):
        try: self.count = max(0, int(float(value)))
        except (TypeError, ValueError): pass
        self.keys = deque((str(x) for x in attrs.get("incident_keys", [])[-MAX_KEYS:]), maxlen=MAX_KEYS)
        self.seen = set(self.keys)
        self.failed_ids = deque((str(x) for x in attrs.get("failed_session_ids", [])[-MAX_KEYS:]), maxlen=MAX_KEYS)
        self.failed_seen = set(self.failed_ids)
        try: self.failed_sessions = max(0, int(attrs.get("failed_sessions", 0)))
        except (TypeError, ValueError): pass
        self.last_text = attrs.get("last_error")
        self.last_time = attrs.get("last_error_time")
        self.last_category = attrs.get("last_error_category")
        self.latched = attrs.get("fault_latched") is True
        # An episode still active across an HA restart is not counted again.
        self.cond_counted = {str(x) for x in attrs.get("active_conditions", []) if x in CONDITIONS}

    # ---- bookkeeping -------------------------------------------------------
    def _remember(self, key):
        if key in self.seen: return False
        if len(self.keys) == MAX_KEYS: self.seen.discard(self.keys[0])
        self.keys.append(key)
        self.seen.add(key)
        return True

    def _failed(self, session):
        if session in self.failed_seen: return
        if len(self.failed_ids) == MAX_KEYS: self.failed_seen.discard(self.failed_ids[0])
        self.failed_ids.append(session)
        self.failed_seen.add(session)
        self.failed_sessions += 1

    def _incident(self, key, session, category, fatal, text, timestamp):
        if not self._remember(key): return
        self.count += 1
        self.last_text = text[:255]
        self.last_time = timestamp
        self.last_category = category
        self.latched = True
        if fatal: self._failed(session)

    @staticmethod
    def _now_text():
        return dt_util.now().strftime("%Y-%m-%dT%H:%M:%S")

    def _service(self):
        services = (self.settings.data or {}).get("services") or []
        return next((s for s in services if s.get("serviceName") == "miner"), {})

    def _intentional(self):
        """True shortly after a start/stop/restart or setting change."""
        last = self.api.last_write
        if last is not None and time.monotonic() - last < FAULT_INTENTIONAL_WINDOW:
            return True
        requested = _parse_utc(self._service().get("requestedAt"))
        return (requested is not None
                and dt_util.utcnow() - requested < timedelta(seconds=FAULT_INTENTIONAL_WINDOW))

    # ---- log snapshot ------------------------------------------------------
    def _check_log(self):
        for session, stamp, message in (self.logs.data or {}).get("entries") or []:
            classification = classify(message)
            if classification is None: continue
            category, fatal = classification
            # Collapse ASIC repeats per session, and identical other messages
            # regardless of their changing timestamps.
            normalized = "asic" if category == "asic" else re.sub(r"\s+", " ", message.strip().lower())[:240]
            self._incident(f"{session}|{category}|{normalized}", session, category, fatal,
                           message.strip(), stamp.replace(" ", "T"))

    # ---- miner stats -------------------------------------------------------
    def _check_stats(self):
        if not self.miner.last_update_success:
            # HA cannot reach the miner API at all; that is shown by the
            # entities going unavailable, not counted as a miner fault.
            # Condition state is left as it was.
            return
        data = self.miner.data or {}
        online = (data.get("online") or {}).get("status") == "online"
        stats = miner_stats(data)
        service = self._service()
        conditions = set()

        if service.get("requestedStatus") == "online" and not online:
            conditions.add("not_running")
        if online and data.get("stale"):
            conditions.add("stats_stale")

        if stats:
            master = stats.get("master") or {}
            intervals = master.get("intervals") or {}
            slot = (stats.get("slots") or {}).get("int_0") or {}
            uptime = _num(master.get("upTime")) or 0
            now_text = self._now_text()

            # Run identity: miner start time, from its own clock.
            date = _parse_utc(stats.get("date"))
            run = (date - timedelta(seconds=uptime)).strftime("%Y%m%dT%H%M") if date else "unknown"

            # Event: miner restarted (uptime went backwards) without a request.
            if self.prev_uptime is not None and uptime + 30 < self.prev_uptime:
                if not self._intentional():
                    self._incident(f"{run}|process|restart", run, "process", True,
                                   "Miner restarted unexpectedly", now_text)
                self.prev_reconnects = None
                self.restart_seen = time.monotonic()
            self.prev_uptime = uptime
            self.run = run
            # The controller has no RTC: after a reboot its clock jumps forward
            # when NTP syncs, and the miner's upTime includes the jump. Count
            # the warm-up from when HA saw the restart as well.
            if self.restart_seen is not None:
                uptime = min(uptime, time.monotonic() - self.restart_seen)

            # Event: pool reconnection (the counter is per miner run).
            pool = ((stats.get("pool") or {}).get("intervals") or {}).get("int_0") or {}
            reconnects = _num(pool.get("reconnections"))
            if reconnects is not None:
                if self.prev_reconnects is not None and reconnects > self.prev_reconnects:
                    self._incident(f"{run}|pool|reconnect {int(reconnects)}", run, "pool", False,
                                   f"Pool reconnected ({int(reconnects)} this miner run)", now_text)
                self.prev_reconnects = reconnects

            hashrate = _hashrate_ghs(stats)
            if uptime > FAULT_STARTUP_GRACE and (hashrate or 0) <= 0:
                conditions.add("no_hashrate")

            target = ((self.logs.data or {}).get("dvfs") or {}).get("target_ths")
            avg5 = _num((intervals.get("int_300") or {}).get("bySol"))
            if (uptime > FAULT_LOW_HASHRATE_GRACE and target and avg5 is not None
                    and avg5 < FAULT_LOW_HASHRATE * target * 1000):
                conditions.add("low_hashrate")

            error_rate = _num((intervals.get("int_300") or {}).get("errorRate"))
            if error_rate is not None and error_rate > FAULT_ERROR_RATE:
                conditions.add("high_error_rate")

            pwr_on, pwr_target = _num(slot.get("pwrOn")), _num(slot.get("pwrOnTarget"))
            if pwr_on is not None and pwr_target is not None and pwr_on < pwr_target:
                conditions.add("board_unpowered")

        if service.get("requestedStatus") == "offline":
            # Deliberately stopped: not a fault.
            conditions.clear()
        elif self._intentional():
            conditions -= TRANSITIONAL

        self._track_conditions(conditions)

    def _track_conditions(self, conditions):
        now = time.monotonic()
        for rule in list(self.cond_since):
            if rule not in conditions:
                del self.cond_since[rule]
        self.cond_counted &= conditions
        for rule in conditions:
            since = self.cond_since.setdefault(rule, now)
            category, fatal, hold, text = CONDITIONS[rule]
            if rule in self.cond_counted or now - since < hold:
                continue
            self.cond_counted.add(rule)
            minute = dt_util.now().strftime("%Y%m%dT%H%M")
            session = self.run or "unknown"
            self._incident(f"{session}|{category}|{rule}@{minute}", session, category, fatal,
                           text, self._now_text())

    @property
    def active_conditions(self):
        """Conditions that have held long enough to count."""
        return sorted(self.cond_counted)

    @property
    def active(self):
        return self.latched or bool(self.cond_counted)

    def update(self):
        if not self.ready: return
        self._check_log()
        self._check_stats()
        stats = miner_stats(self.miner.data)
        if stats and (_hashrate_ghs(stats) or 0) > 0:
            self.latched = False
        for entity in self.entities:
            if entity.hass is not None: entity.async_write_ha_state()


class GeneralEntity(ApolloEntity):
    def __init__(self, entry, monitor, key, name):
        super().__init__(entry, monitor.logs, key, name)
        self.monitor = monitor
        monitor.entities.append(self)
        # Expose generalized fault entities in the device Sensors section.
        self._attr_entity_category = None

    @property
    def available(self):
        # Fed by several coordinators; one failed log read must not make the
        # counter or fault unavailable.
        return True


class MinerErrorCount(GeneralEntity, SensorEntity, RestoreEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "miner_error_incidents", "Miner error count")

    async def async_added_to_hass(self):
        old = await self.async_get_last_state()
        if old: self.monitor.restore(old.attributes, old.state)
        await super().async_added_to_hass()
        self.monitor.ready = True
        self.monitor.update()

    @property
    def native_value(self): return self.monitor.count

    @property
    def extra_state_attributes(self):
        m = self.monitor
        return {"incident_keys": list(m.keys), "failed_session_ids": list(m.failed_ids),
                "failed_sessions": m.failed_sessions, "last_error": m.last_text,
                "last_error_time": m.last_time, "last_error_category": m.last_category,
                "fault_latched": m.latched, "active_conditions": m.active_conditions,
                "scope": "Miner stats checks every poll, plus errors visible in the "
                         "miner log snapshot; 80-key deduplication window"}


class MinerLastError(GeneralEntity, SensorEntity):
    def __init__(self, entry, monitor): super().__init__(entry, monitor, "miner_last_error", "Miner last error")
    @property
    def native_value(self): return self.monitor.last_text


class MinerLastErrorTime(GeneralEntity, SensorEntity):
    def __init__(self, entry, monitor): super().__init__(entry, monitor, "miner_last_error_time", "Miner last error time")
    @property
    def native_value(self): return self.monitor.last_time


class MinerLastErrorCategory(GeneralEntity, SensorEntity):
    def __init__(self, entry, monitor): super().__init__(entry, monitor, "miner_last_error_category", "Miner last error category")
    @property
    def native_value(self): return self.monitor.last_category


class MinerFault(GeneralEntity, BinarySensorEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "miner_fault", "Miner fault")
        self._attr_device_class = "problem"

    @property
    def is_on(self): return self.monitor.active

    @property
    def extra_state_attributes(self):
        return {"active_conditions": self.monitor.active_conditions,
                "latched_incident": self.monitor.latched}
