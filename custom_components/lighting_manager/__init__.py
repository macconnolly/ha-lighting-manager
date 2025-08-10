"""The Lighting Manager integration - Golden Path implementation."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_referenced_entity_ids

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_TRANSITION,
    DATA_ADD_ENTITIES,
    DATA_COORDINATOR,
    DOMAIN,
    EVENT_LAYER_CREATED,
    MANUFACTURER,
    MODEL,
    PLATFORMS,
    SW_VERSION,
)
from .coordinator import ZoneCoordinator
from .validation import (
    validate_brightness,
    validate_color_temp,
    validate_layer_name,
    validate_priority,
    validate_transition,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas moved to services.py for consolidation


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lighting Manager from a config entry."""
    _LOGGER.info("Setting up Lighting Manager for zone: %s", entry.data["zone_name"])
    
    # Initialize domain data if needed
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    # Initialize entry data
    hass.data[DOMAIN][entry.entry_id] = {}
    
    # Create and initialize the coordinator (single source of truth)
    coordinator = ZoneCoordinator(hass, entry)
    
    # Load existing layers from storage
    await coordinator.async_load()
    
    # Store coordinator reference
    hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR] = coordinator
    
    # Create zone device in registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data["zone_id"])},
        manufacturer=MANUFACTURER,
        model=MODEL,
        name=entry.data["zone_name"],
        sw_version=SW_VERSION,
    )
    
    # Set up platforms (switch for layers, sensor for observability)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    # Register services ONCE at domain level
    if len(hass.data[DOMAIN]) == 1:  # First zone being set up
        from .services import async_setup_services
        await async_setup_services(hass)
    
    # Phase 2: Trigger initial calculation if there are active layers
    if any(layer.get("is_on", False) for layer in coordinator.layers.values()):
        await coordinator.async_refresh()
        _LOGGER.info("Initial calculation performed for zone %s", entry.data["zone_name"])
    
    _LOGGER.info("Successfully set up zone: %s with %d existing layers",
                 entry.data["zone_name"], len(coordinator.layers))
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Lighting Manager zone: %s", entry.data["zone_name"])
    
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up coordinator
        coordinator: ZoneCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        await coordinator.async_shutdown()
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Unregister services if this was the last zone
        if not hass.data[DOMAIN]:
            from .services import unload_services
            unload_services(hass)
            hass.data.pop(DOMAIN)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading zone %s due to options change", entry.data["zone_name"])
    
    # Phase 2: Update light controller when options change
    coordinator: ZoneCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    new_lights = entry.options.get("light_entities", [])
    
    if coordinator._light_controller:
        coordinator._light_controller.update_light_entities(new_lights)
        coordinator.light_entities = new_lights
        _LOGGER.info("Updated light entities for zone %s without full reload", 
                    entry.data["zone_name"])
        
        # Trigger recalculation with new lights
        coordinator.schedule_recalculation()
    else:
        # Fall back to full reload if needed
        await async_unload_entry(hass, entry)
        await async_setup_entry(hass, entry)

