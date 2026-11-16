"""Diagnostics download for the Apollo III Standard (Settings > device > Download diagnostics)."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import ApolloConfigEntry

# Credentials, hardware identifiers and the pool username (often a payout address).
TO_REDACT = {"password", "unique_id", "mac", "hwAddr", "userName", "address", "host"}
POOL_USER = re.compile(r"(-user2?|-pswd2?)\s+\S+")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ApolloConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data
    logs = dict(data.logs.data or {})
    # The screen snapshot can contain the miner command line, including the
    # pool user and password; keep only parsed values and redacted text.
    content = logs.pop("content", None)
    logs.pop("entries", None)
    if isinstance(content, str):
        logs["content"] = POOL_USER.sub(r"\1 **REDACTED**", content)
    monitor = data.monitor
    tracker = data.restart_tracker
    return {
        "entry": async_redact_data(
            # The default title contains the host.
            {"title": entry.title.replace(entry.data.get("host") or "\0", "**REDACTED**"),
             "data": dict(entry.data), "unique_id": entry.unique_id,
             "version": entry.version}, TO_REDACT),
        "coordinators": {
            name: {
                "last_update_success": coordinator.last_update_success,
                "data": async_redact_data(coordinator.data, TO_REDACT),
            }
            for name, coordinator in (("miner", data.miner), ("mcu", data.mcu),
                                      ("settings", data.settings))
        } | {"logs": {"last_update_success": data.logs.last_update_success,
                      "data": async_redact_data(logs, TO_REDACT)}},
        "fault_monitor": {
            "count": monitor.count, "latched": monitor.latched,
            "active_conditions": monitor.active_conditions,
            "last_error": monitor.last_text, "last_error_time": monitor.last_time,
            "last_error_category": monitor.last_category,
        },
        "restart_tracker": {
            "needed": tracker.needed, "pending": tracker.pending, "baseline": tracker.baseline,
            "running_settings": tracker.applied, "saved_settings": tracker._saved(),
        },
    }
