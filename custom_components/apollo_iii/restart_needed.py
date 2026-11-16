"""Detect saved miner settings that the running miner has not loaded yet.

The miner reads its configuration once, at startup. Saving a setting (from HA
or the Apollo UI) only rewrites the config file, so the running miner keeps
its old settings until it restarts. HA deliberately does not restart it; this
indicator shows when a restart is needed to apply what is saved.

The tracker remembers the effective settings at the start of the current miner
run and compares them with the saved settings. "Effective" means what
apolloapi-v2's configurator.js puts on the command line, so changes the miner
would ignore (for example the custom hashrate while in a preset mode) do not
count. Pool and other Apollo UI-only settings are not tracked.
"""
from datetime import datetime, timedelta
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from .entity import ApolloEntity, miner_stats, is_set

# A restored run within this many seconds of the current one is the same run.
RUN_MATCH_TOLERANCE = 120

LABELS = {"power_mode": "Power mode", "fan": "Fan control"}


def _clamp(value, low, high):
    return max(low, min(high, int(float(value))))


def effective(settings):
    """The tuning the backend would put on the miner command line."""
    if not settings:
        return None
    mode = settings.get("minerMode")
    hashrate = settings.get("minerHashrate")
    if mode == "custom":
        power = f"custom {_clamp(hashrate, 5, 20)} TH/s" if is_set(hashrate) else "eco"
    else:
        power = mode
    pwm, temp = settings.get("fanPwm"), settings.get("fanTemp")
    if is_set(pwm):
        fan = f"fixed PWM {_clamp(pwm, 10, 100)}%"
    elif is_set(temp):
        fan = f"temperature target {_clamp(temp, 40, 80)} °C"
    else:
        fan = "automatic"
    return {"power_mode": power, "fan": fan}


def _run_start(stats):
    """Miner run start time from its own clock, or None."""
    try:
        date = datetime.fromisoformat(stats.get("date"))
        uptime = float((stats.get("master") or {}).get("upTime"))
    except (TypeError, ValueError):
        return None
    return date - timedelta(seconds=uptime) if date.tzinfo else None


class RestartTracker:
    def __init__(self, miner, settings):
        self.miner, self.settings = miner, settings
        self.applied = None        # effective settings the running miner loaded
        self.baseline = None       # how `applied` was determined
        self.run_start = None
        self.prev_uptime = None
        self.pending = False       # snapshot due at the next settings refresh
        self.ready = False
        self._restored = None
        self.entity = None
        miner.async_add_listener(self._miner_update)
        settings.async_add_listener(self._settings_update)

    def _saved(self):
        return effective((self.settings.data or {}).get("settings"))

    def restore(self, attrs):
        applied = attrs.get("running_settings")
        try:
            run = datetime.fromisoformat(attrs.get("run_start"))
        except (TypeError, ValueError):
            run = None
        if isinstance(applied, dict):
            self._restored = (dict(applied), run)

    def start(self):
        self.ready = True
        self._miner_update()

    def _snapshot(self, baseline):
        saved = self._saved()
        if saved is None:
            self.pending, self.baseline = True, baseline
            return
        self.applied, self.baseline, self.pending = saved, baseline, False

    def _miner_update(self):
        if not self.ready:
            return
        stats = miner_stats(self.miner.data)
        if stats:
            uptime = float((stats.get("master") or {}).get("upTime") or 0)
            start = _run_start(stats)
            if self.applied is None and not self.pending:
                # First fresh sample since HA started.
                restored = self._restored
                same_run = (restored and restored[1] and start
                            and abs((restored[1] - start).total_seconds()) <= RUN_MATCH_TOLERANCE)
                if same_run:
                    self.applied, self.run_start = restored[0], restored[1]
                    self.baseline = "restored"
                else:
                    # Unknown what this run loaded; assume the saved settings.
                    self.run_start = start
                    self._snapshot("assumed: miner run started while HA was not watching")
            elif self.prev_uptime is not None and uptime + 30 < self.prev_uptime:
                # The miner restarted and loaded whatever is saved now. Take the
                # snapshot from a settings read made after the restart, in case
                # the settings were changed just before it.
                self.run_start = start
                self.pending, self.baseline = True, "observed miner restart"
                hass = getattr(self.settings, "hass", None)
                if hass is not None:
                    hass.async_create_task(self.settings.async_request_refresh())
            self.prev_uptime = uptime
        self._notify()

    def _settings_update(self):
        if self.ready and self.pending:
            self._snapshot(self.baseline)
        self._notify()

    def _notify(self):
        if self.entity is not None and self.entity.hass is not None:
            self.entity.async_write_ha_state()

    @property
    def needed(self):
        saved = self._saved()
        return bool(not self.pending and self.applied and saved and self.applied != saved)

    @property
    def changes(self):
        if not self.needed:
            return []
        saved = self._saved() or {}
        applied = self.applied or {}
        return [f"{LABELS.get(k, k)}: {applied.get(k)} → {saved.get(k)}"
                for k in saved if applied and applied.get(k) != saved.get(k)]


class RestartNeeded(ApolloEntity, BinarySensorEntity, RestoreEntity):
    _attr_icon = "mdi:restart-alert"

    def __init__(self, entry, tracker):
        super().__init__(entry, tracker.settings, "restart_needed", "Restart needed")
        self.tracker = tracker
        tracker.entity = self

    async def async_added_to_hass(self):
        old = await self.async_get_last_state()
        if old:
            self.tracker.restore(old.attributes)
        await super().async_added_to_hass()
        self.tracker.start()

    @property
    def is_on(self):
        return self.tracker.needed

    @property
    def extra_state_attributes(self):
        t = self.tracker
        return {
            "pending_changes": t.changes,
            "running_settings": t.applied,
            "saved_settings": t._saved(),
            "run_start": t.run_start.isoformat() if t.run_start else None,
            "baseline": t.baseline,
            "note": "Press Restart miner to apply saved settings",
        }
