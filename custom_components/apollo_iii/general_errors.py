"""General-purpose miner log incident monitor (read-only).

Known fatal errors count once per session. Other recognizable error messages
count once per distinct message per session; repeating lines do not inflate totals.
Unknown candidate errors are retained with their original text for review.
"""
import re
from collections import deque
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import ApolloEntity

SESSION = re.compile(r"^=== Session ([^\s=]+) ===$")
STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):\s*(.*)$")
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

def classify(message):
    if EXCLUDE.search(message):
        return None
    for category, pattern, fatal in RULES:
        if pattern.search(message):
            return category, fatal
    if GENERIC.search(message):
        return "unclassified", False
    return None

class GeneralErrorState:
    def __init__(self, logs, miner):
        self.logs, self.miner = logs, miner
        self.count = 0
        self.failed_sessions = 0
        self.last_text = None
        self.last_time = None
        self.last_category = None
        self.active = False
        self.ready = False
        self.keys = deque(maxlen=MAX_KEYS)
        self.seen = set()
        self.failed_ids = deque(maxlen=MAX_KEYS)
        self.failed_seen = set()
        self.entities = []
        logs.async_add_listener(self.update)
        miner.async_add_listener(self.update)

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
        self.active = attrs.get("fault_latched") is True

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

    def update(self):
        if not self.ready: return
        content = (self.logs.data or {}).get("content", "")
        if not isinstance(content, str): return
        session = None
        for line in content.splitlines():
            header = SESSION.match(line)
            if header:
                session = header.group(1)
                continue
            if session is None: continue
            stamp = STAMP.match(line)
            if not stamp: continue
            timestamp, message = stamp.groups()
            classification = classify(message)
            if classification is None: continue
            category, fatal = classification
            # Collapse ASIC repeats per session, and identical other messages
            # regardless of their changing timestamps.
            normalized = "asic" if category == "asic" else re.sub(r"\s+", " ", message.strip().lower())[:240]
            key = f"{session}|{category}|{normalized}"
            if not self._remember(key): continue
            self.count += 1
            self.last_text = message.strip()[:255]
            self.last_time = timestamp.replace(" ", "T")
            self.last_category = category
            self.active = True
            if fatal: self._failed(session)
        miner_data = self.miner.data or {}
        online = (miner_data.get("online") or {}).get("status") == "online"
        stats = miner_data.get("stats") or []
        try:
            slot = (stats[0] if isinstance(stats, list) and stats else stats) or {}
            ghs = float((slot.get("slots") or {}).get("int_0", {}).get("ghs") or 0)
        except (ValueError, TypeError, AttributeError): ghs = 0
        if online and ghs > 0: self.active = False
        for entity in self.entities:
            if entity.hass is not None: entity.async_write_ha_state()

class GeneralEntity(ApolloEntity):
    def __init__(self, entry, monitor, key, name):
        super().__init__(entry, monitor.logs, key, name)
        self.monitor = monitor
        monitor.entities.append(self)
        # Expose generalized fault entities in the device Sensors section.
        self._attr_entity_category = None

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
                "fault_latched": m.active,
                "scope": "Observed distinct miner-log incidents; 80-key deduplication window"}

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
