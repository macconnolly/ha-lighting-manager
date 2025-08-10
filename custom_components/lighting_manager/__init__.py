"""Lighting Manager integration setup."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .const import CONF_ENTITIES, DOMAIN, PLATFORMS
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration via YAML (deprecated)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lighting Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    lights = list(entry.data[CONF_ENTITIES].keys())
    coordinator = ZoneCoordinator(hass, entry.title, lights)
    await coordinator.async_config_entry_first_refresh()

    async def _apply_state() -> None:
        final_state = coordinator.data.get("final_state")
        if not final_state:
            return
        service_data: dict[str, Any] = {ATTR_ENTITY_ID: lights}
        service_data.update(final_state)
        await hass.services.async_call(
            "light", "turn_on", service_data, blocking=False
        )

    coordinator.async_add_listener(_apply_state)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator: ZoneCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_shutdown()
    return unload_ok
