"""The Lighting Manager integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_TRANSITION,
    DATA_ADD_ENTITIES,
    DATA_COORDINATOR,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    PLATFORMS,
    SW_VERSION,
)
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)


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
    
    # Do initial data fetch
    await coordinator.async_config_entry_first_refresh()
    
    # Register services (only once for the domain)
    if len(hass.data[DOMAIN]) == 1:
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
        await coordinator.async_will_remove_from_hass()
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove domain data if no more entries
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading zone %s due to options change", entry.data["zone_name"])
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Lighting Manager."""
    
    @callback
    async def handle_create_layer(call: ServiceCall) -> None:
        """Handle create_layer service call."""
        # Get the target entity from the service call
        entity_ids = call.data.get(ATTR_ENTITY_ID, [])
        if not entity_ids:
            _LOGGER.error("No target entity specified for create_layer")
            return
        
        # Extract zone from the entity_id (switch.zone_id_*_layer)
        for entity_id in entity_ids:
            if not entity_id.startswith("switch."):
                continue
            
            # Find the config entry for this entity
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if entry_id == "services":  # Skip service registration marker
                    continue
                
                coordinator: ZoneCoordinator = entry_data.get(DATA_COORDINATOR)
                if not coordinator:
                    continue
                
                # Check if this entity belongs to this zone
                if entity_id.startswith(f"switch.{coordinator.zone_id}_"):
                    # Create the layer
                    layer_name = call.data["layer_name"]
                    priority = call.data.get("priority", 50)
                    
                    # Build attributes
                    attributes = {}
                    if "brightness" in call.data:
                        attributes[ATTR_BRIGHTNESS] = call.data["brightness"]
                    if "color_temp" in call.data:
                        attributes[ATTR_COLOR_TEMP] = call.data["color_temp"]
                    if "transition" in call.data:
                        attributes[ATTR_TRANSITION] = call.data["transition"]
                    
                    # Create layer in coordinator
                    layer_id = coordinator.create_layer(layer_name, priority, **attributes)
                    
                    # Create switch entity for the new layer
                    add_entities = entry_data.get(DATA_ADD_ENTITIES)
                    if add_entities:
                        from .switch import LayerSwitch
                        
                        new_switch = LayerSwitch(
                            coordinator=coordinator,
                            zone_id=coordinator.zone_id,
                            zone_name=coordinator.zone_name,
                            layer_id=layer_id,
                        )
                        add_entities([new_switch])
                        _LOGGER.info("Created layer %s in zone %s", layer_name, coordinator.zone_id)
                    break
    
    # Register the service
    hass.services.async_register(
        DOMAIN,
        "create_layer",
        handle_create_layer,
        schema=vol.Schema({
            vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
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
            vol.Optional("transition", default=2.0): vol.Coerce(float),
        }),
    )
    
    _LOGGER.info("Registered Lighting Manager services")