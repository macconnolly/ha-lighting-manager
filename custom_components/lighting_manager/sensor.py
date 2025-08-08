"""Sensor platform for Lighting Manager - Phase 4 placeholder."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lighting Manager sensor platform."""
    # Phase 4: Will implement observability sensors here
    # For now, just log that we're ready
    _LOGGER.debug("Sensor platform ready for zone %s (Phase 4 pending)",
                  config_entry.data["zone_name"])