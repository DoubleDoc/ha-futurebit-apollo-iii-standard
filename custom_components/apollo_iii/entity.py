"""Shared Apollo III entity."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class ApolloEntity(CoordinatorEntity):
    """Base entity. Names come from translations (entity.<platform>.<key>)."""
    _attr_has_entity_name = True

    def __init__(self, entry, coordinator, key):
        super().__init__(coordinator)
        # Unique IDs keep their original keys; translation keys must be lowercase.
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key.lower()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            # Device name stays short: it prefixes every entity name.
            name="FutureBit Apollo III",
            manufacturer="FutureBit",
            model="Apollo III Standard",
            configuration_url=f"http://{entry.data['host']}/",
        )


def miner_stats(data):
    """First board's stats when the miner is online and its stats are fresh."""
    data = data or {}
    if (data.get("online") or {}).get("status") != "online" or data.get("stale"):
        return None
    stats = data.get("stats") or []
    return stats[0] if stats and isinstance(stats[0], dict) else None


def is_set(value):
    """Match apolloapi-v2's isSet(): only a positive number counts."""
    try:
        return value is not None and value != "" and float(value) > 0
    except (TypeError, ValueError):
        return False
