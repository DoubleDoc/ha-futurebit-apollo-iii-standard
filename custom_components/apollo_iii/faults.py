"""Read-only log-based fault observations for the single-board Apollo III."""
import re
from datetime import datetime
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import ApolloEntity

SESSION = re.compile(r"^=== Session ([^\s=]+) ===$", re.M)
FAULT = re.compile(r"no ASIC is detected for brd\s+(\d+)", re.I)
STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):")
class FaultState:
    """One shared state object; the count sensor restores its durable checkpoint."""
    def __init__(self, entry, logs, miner):
        self.logs = logs
        self.miner = miner
        self.count = 0
        self.restarts = 0
        self.last_fault = None
        self.last_fault_time = None
        self.last_session = None
        self.last_event = None
        self.counted_sessions = set()
        self.last_log_session = None
        self.active = False
        self.ready = False
        self.entities = []
        logs.async_add_listener(self.update)
        miner.async_add_listener(self.update)

    def update(self):
        if not self.ready:
            return
        content = (self.logs.data or {}).get("content", "")
        if not isinstance(content, str):
            return
        session = None
        latest_session = None
        faults = []
        for line in content.splitlines():
            match = SESSION.search(line)
            if match:
                session = match.group(1)
                latest_session = session
                continue
            error = FAULT.search(line)
            if error and session is not None:
                stamp = STAMP.match(line)
                faults.append((session, stamp.group(1) if stamp else None, error.group(1)))
        # Count each distinct failed session only once, even if the API
        # repeats hundreds of messages or returns overlapping log windows.
        for session_id, stamp, board in faults:
            if session_id not in self.counted_sessions:
                self.counted_sessions.add(session_id)
                self.count += 1
                self.last_fault = f"No ASIC detected on board {board}"
                if stamp:
                    self.last_fault_time = stamp.replace(" ", "T")
                self.active = True
        if latest_session and latest_session != self.last_session:
            if self.last_session is not None:
                self.restarts += 1
            self.last_session = latest_session
        # Recovery requires actual positive hashrate; "online" and a
        # nonempty statistics response are not evidence of ASIC recovery.
        miner_data = self.miner.data or {}
        online = (miner_data.get("online") or {}).get("status") == "online"
        stats = miner_data.get("stats") or []
        try:
            ghs = float(((stats[0] if isinstance(stats, list) and stats else stats) or {})
                        .get("slots", {}).get("int_0", {}).get("ghs") or 0)
        except (ValueError, TypeError, AttributeError):
            ghs = 0
        if online and ghs > 0:
            self.active = False
        for entity in self.entities:
            if entity.hass is not None:
                entity.async_write_ha_state()

class FaultEntity(ApolloEntity):
    def __init__(self, entry, monitor, key, name):
        super().__init__(entry, monitor.logs, key, name)
        self.monitor = monitor
        monitor.entities.append(self)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

class FaultCountSensor(FaultEntity, SensorEntity, RestoreEntity):
    """Durable count and cursor checkpoint for all log-derived sensors."""
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "asic_failed_sessions", "ASIC initialization failures")

    async def async_added_to_hass(self):
        old = await self.async_get_last_state()
        if old:
            try:
                self.monitor.count = max(0, int(float(old.state)))
            except (TypeError, ValueError):
                pass
            attrs = old.attributes
            self.monitor.counted_sessions = set(attrs.get("counted_sessions") or [])
            self.monitor.active = bool(attrs.get("fault_latched", False))
            self.monitor.last_session = attrs.get("last_session")
            self.monitor.last_fault = attrs.get("last_fault")
            self.monitor.last_fault_time = attrs.get("last_fault_time")
            try:
                self.monitor.restarts = max(0, int(attrs.get("restart_count", 0)))
            except (TypeError, ValueError):
                pass
        await super().async_added_to_hass()
        self.monitor.ready = True
        self.monitor.update()

    @property
    def native_value(self):
        return self.monitor.count

    @property
    def extra_state_attributes(self):
        return {
            "counted_sessions": sorted(self.monitor.counted_sessions),
            "fault_latched": self.monitor.active,
            "last_session": self.monitor.last_session,
            "last_fault": self.monitor.last_fault,
            "last_fault_time": self.monitor.last_fault_time,
            "restart_count": self.monitor.restarts,
            "scope": "Distinct failed miner sessions observed; not lifetime hardware failures",
        }

class FaultBinarySensor(FaultEntity, BinarySensorEntity, RestoreEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "asic_detection_fault", "ASIC detection fault")
        self._attr_device_class = "problem"
    @property
    def is_on(self):
        return self.monitor.active

class FaultTextSensor(FaultEntity, SensorEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "last_asic_fault", "Last ASIC detection fault")
    @property
    def native_value(self):
        return self.monitor.last_fault

class FaultTimeSensor(FaultEntity, SensorEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "last_asic_fault_time", "Last ASIC detection fault time")
    @property
    def native_value(self):
        if not self.monitor.last_fault_time:
            return None
        # Miner log timestamps are local device timestamps (no UTC offset).
        # Return as a string sensor instead of pretending they are UTC.
        return self.monitor.last_fault_time

class FaultRestartSensor(FaultEntity, SensorEntity):
    def __init__(self, entry, monitor):
        super().__init__(entry, monitor, "miner_sessions_observed", "Miner session changes observed")
    @property
    def native_value(self):
        return self.monitor.restarts
