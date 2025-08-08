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

# Service schemas
SERVICE_CREATE_LAYER_SCHEMA = vol.Schema({
    vol.Required("layer_name"): cv.string,
    vol.Optional("priority", default=50): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
    vol.Optional("brightness"): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional("color_temp"): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional("transition", default=2.0): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=300.0)
    ),
})


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
        await async_setup_services(hass)
    
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
            hass.services.async_remove(DOMAIN, "create_layer")
            hass.data.pop(DOMAIN)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading zone %s due to options change", entry.data["zone_name"])
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Lighting Manager.
    
    GOLDEN PATH: Uses proper entity targeting with entity registry.
    """
    
    async def handle_create_layer(call: ServiceCall) -> None:
        """GOLDEN PATH: Proper service implementation using entity registry."""
        # Extract entities properly
        referenced = async_extract_referenced_entity_ids(hass, call)
        entity_ids = referenced.referenced | referenced.indirectly_referenced
        
        if not entity_ids:
            _LOGGER.error("No target entities specified for create_layer")
            return
        
        # Use entity registry to find our switch entities
        entity_reg = er.async_get(hass)
        coordinators_to_update = set()
        
        for entity_id in entity_ids:
            entry = entity_reg.async_get(entity_id)
            
            # Check if this is one of our layer switches
            if entry and entry.platform == DOMAIN and "layer" in entity_id:
                # Get coordinator from the config entry
                config_entry_id = entry.config_entry_id
                if config_entry_id not in hass.data[DOMAIN]:
                    continue
                    
                coordinator = hass.data[DOMAIN][config_entry_id].get(DATA_COORDINATOR)
                if not coordinator:
                    continue
                
                # Validate ALL inputs before calling coordinator
                try:
                    layer_name = validate_layer_name(call.data["layer_name"])
                    priority = validate_priority(call.data.get("priority", 50))
                    
                    # Build attributes dict with validated values
                    attributes = {}
                    if "brightness" in call.data:
                        attributes[ATTR_BRIGHTNESS] = validate_brightness(call.data["brightness"])
                    if "color_temp" in call.data:
                        attributes[ATTR_COLOR_TEMP] = validate_color_temp(call.data["color_temp"])
                    if "transition" in call.data:
                        attributes[ATTR_TRANSITION] = validate_transition(call.data["transition"])
                    
                    # Create layer in coordinator
                    layer_id = await coordinator.create_layer(
                        layer_name=call.data["layer_name"],  # Original name for display
                        priority=priority,
                        **attributes
                    )
                    
                    # Create switch entity for the new layer
                    add_entities = hass.data[DOMAIN][config_entry_id].get(DATA_ADD_ENTITIES)
                    if add_entities and layer_id:
                        from .switch import LayerSwitch
                        
                        new_switch = LayerSwitch(
                            coordinator=coordinator,
                            layer_id=layer_id,
                            layer_name=call.data["layer_name"],
                        )
                        add_entities([new_switch])
                        
                        # Fire event
                        hass.bus.async_fire(
                            EVENT_LAYER_CREATED,
                            {
                                "zone_id": coordinator.zone_id,
                                "layer_id": layer_id,
                                "layer_name": call.data["layer_name"],
                            },
                        )
                        
                        _LOGGER.info("Created layer %s in zone %s",
                                    layer_name, coordinator.zone_id)
                    
                    coordinators_to_update.add(coordinator)
                    
                except ValueError as e:
                    _LOGGER.error("Invalid input for create_layer: %s", e)
                    continue
                
                # Only process first matching entity
                break
    
    # Register service at domain level
    hass.services.async_register(
        DOMAIN,
        "create_layer",
        handle_create_layer,
        schema=SERVICE_CREATE_LAYER_SCHEMA,
    )
    
    _LOGGER.info("Registered Lighting Manager services")