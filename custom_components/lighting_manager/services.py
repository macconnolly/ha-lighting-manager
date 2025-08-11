"""Service implementations for Lighting Manager.

This module contains all service handlers for Phase 3 functionality.
Follows production-grade patterns with validation, error handling, and events.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_referenced_entity_ids
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_FACTOR,
    ATTR_BRIGHTNESS_PCT_DELTA,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_FACTOR,
    ATTR_COLOR_TEMP_KELVIN_DELTA,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAYER_NAME,
    ATTR_LAYER_TYPE,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    DATA_COORDINATOR,
    DEFAULT_PRIORITY,
    DOMAIN,
    EVENT_LAYER_ACTIVATED,
    EVENT_LAYER_CREATED,
    EVENT_LAYER_DEACTIVATED,
    EVENT_LAYER_FORCED,
    EVENT_LAYER_LOCKED,
    EVENT_LAYER_UNLOCKED,
    EVENT_PRESET_APPLIED,
    EVENT_ZONE_RESET,
    LAYER_TYPE_ABSOLUTE,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_APPLY_PRESET,
    SERVICE_DEACTIVATE_LAYER,
    SERVICE_FORCE_LAYER,
    SERVICE_LOCK_LAYER,
    SERVICE_RECALCULATE_ZONE,
    SERVICE_RESET_ZONE,
    SERVICE_SET_LAYER,
    SERVICE_SET_LAYER_PRIORITY,
    SERVICE_UNFORCE_LAYER,
    SERVICE_UNLOCK_LAYER,
    SERVICE_UPDATE_LAYER,
    SERVICES_REGISTERED,
)
from .validation import (
    validate_brightness,
    validate_color_temp,
    validate_layer_name,
    validate_layer_payload,
    validate_priority,
    validate_rgb_color,
    validate_transition,
)

_LOGGER = logging.getLogger(__name__)

# Service Schemas
SERVICE_SET_LAYER_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("layer_id"): cv.string,  # Now required for idempotent operation
    vol.Optional("layer_name"): cv.string,  # Optional display name
    vol.Optional(ATTR_LAYER_TYPE, default=LAYER_TYPE_ABSOLUTE): vol.In(
        ["absolute", "modifier", "multiplier"]
    ),
    vol.Optional(ATTR_IS_ON): cv.boolean,  # No default, handled in service
    vol.Optional(ATTR_PRIORITY): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
    # Absolute layer attributes
    vol.Optional(ATTR_BRIGHTNESS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional(ATTR_COLOR_TEMP): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional(ATTR_RGB_COLOR): vol.All(
        vol.ExactSequence([vol.Coerce(int)] * 3),
        vol.Length(min=3, max=3),
    ),
    # Modifier layer attributes
    vol.Optional(ATTR_BRIGHTNESS_PCT_DELTA): vol.All(
        vol.Coerce(float), vol.Range(min=-100, max=100)
    ),
    vol.Optional(ATTR_COLOR_TEMP_KELVIN_DELTA): vol.All(
        vol.Coerce(float), vol.Range(min=-5000, max=5000)
    ),
    vol.Optional(ATTR_BRIGHTNESS_FACTOR): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=2)
    ),
    vol.Optional(ATTR_COLOR_TEMP_FACTOR): vol.All(
        vol.Coerce(float), vol.Range(min=0.5, max=2)
    ),
    # Common attributes
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
    vol.Optional(ATTR_FORCE, default=False): cv.boolean,
    vol.Optional(ATTR_LOCKED, default=False): cv.boolean,
    vol.Optional("timeout_minutes"): vol.All(
        vol.Coerce(float), vol.Range(min=0.1, max=10080)
    ),
    vol.Optional(ATTR_SOURCE): cv.string,
})

SERVICE_ACTIVATE_LAYER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_BRIGHTNESS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional(ATTR_COLOR_TEMP): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional(ATTR_RGB_COLOR): vol.All(
        vol.ExactSequence([vol.Coerce(int)] * 3),
        vol.Length(min=3, max=3),
    ),
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
    vol.Optional(ATTR_SOURCE): cv.string,
})

SERVICE_DEACTIVATE_LAYER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_SOURCE): cv.string,
})

SERVICE_UPDATE_LAYER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_BRIGHTNESS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional(ATTR_COLOR_TEMP): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional(ATTR_RGB_COLOR): vol.All(
        vol.ExactSequence([vol.Coerce(int)] * 3),
        vol.Length(min=3, max=3),
    ),
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
})

SERVICE_SET_PRIORITY_SCHEMA = vol.Schema({
    vol.Required(ATTR_PRIORITY): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
})

SERVICE_LOCK_UNLOCK_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("layer_id"): cv.string,
})

SERVICE_FORCE_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("layer_id"): cv.string,
    vol.Optional("force", default=True): cv.boolean,
})

SERVICE_ZONE_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
})

SERVICE_PRESET_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("preset_name"): cv.string,
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
})

SERVICE_CREATE_LAYER_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("layer_name"): cv.string,
    vol.Optional("priority", default=50): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
    vol.Optional(ATTR_BRIGHTNESS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional(ATTR_COLOR_TEMP): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
})


async def handle_create_zone(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the create_zone service call to programmatically create a zone."""
    zone_name = call.data.get("zone_name")
    light_entities = call.data.get("light_entities", [])
    
    # Create zone_id from zone_name
    from homeassistant.util import slugify
    zone_id = slugify(zone_name)
    
    # Check if zone already exists
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("zone_id") == zone_id:
            _LOGGER.warning("Zone %s already exists", zone_id)
            return
    
    # Create config entry directly
    config_entry = hass.config_entries.async_create_entry(
        domain=DOMAIN,
        title=zone_name,
        data={
            "zone_id": zone_id,
            "zone_name": zone_name,
            "area_id": None,
        },
        options={
            "light_entities": light_entities,
            "adaptive_enabled": True,
            "adaptive_min_brightness": 30,
            "adaptive_max_brightness": 100,
            "adaptive_min_color_temp": 2200,
            "adaptive_max_color_temp": 4000,
        }
    )
    
    # Trigger setup
    await hass.config_entries.async_setup(config_entry.entry_id)
    
    _LOGGER.info("Created zone %s with %d lights", zone_name, len(light_entities))


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Phase 3 services."""
    
    # Check if already registered
    if SERVICES_REGISTERED in hass.data.get(DOMAIN, {}):
        return
    
    # Register all services
    services = [
        # Primary Layer Services
        (SERVICE_SET_LAYER, handle_set_layer, SERVICE_SET_LAYER_SCHEMA),
        # Zone Control Services  
        ("delete_zone", handle_delete_zone, vol.Schema({
            vol.Required("zone_id"): cv.string,
        })),
        # DEPRECATED - use set_layer instead
        # ("create_layer", handle_create_layer, SERVICE_CREATE_LAYER_SCHEMA),
        
        # Legacy Layer Control Services (kept for compatibility)
        (SERVICE_ACTIVATE_LAYER, handle_activate_layer, SERVICE_ACTIVATE_LAYER_SCHEMA),
        (SERVICE_DEACTIVATE_LAYER, handle_deactivate_layer, SERVICE_DEACTIVATE_LAYER_SCHEMA),
        # DEPRECATED - use set_layer instead
        # (SERVICE_UPDATE_LAYER, handle_update_layer, SERVICE_UPDATE_LAYER_SCHEMA),
        (SERVICE_SET_LAYER_PRIORITY, handle_set_layer_priority, SERVICE_SET_PRIORITY_SCHEMA),
        
        # Layer State Services
        (SERVICE_LOCK_LAYER, handle_lock_layer, SERVICE_LOCK_UNLOCK_SCHEMA),
        (SERVICE_UNLOCK_LAYER, handle_unlock_layer, SERVICE_LOCK_UNLOCK_SCHEMA),
        (SERVICE_FORCE_LAYER, handle_force_layer, SERVICE_FORCE_SCHEMA),
        (SERVICE_UNFORCE_LAYER, handle_unforce_layer, SERVICE_LOCK_UNLOCK_SCHEMA),
        
        # Zone Control Services
        (SERVICE_RECALCULATE_ZONE, handle_recalculate_zone, SERVICE_ZONE_SCHEMA),
        (SERVICE_RESET_ZONE, handle_reset_zone, SERVICE_ZONE_SCHEMA),
        
        # Advanced Services
        (SERVICE_APPLY_PRESET, handle_apply_preset, SERVICE_PRESET_SCHEMA),
    ]
    
    for service_name, handler, schema in services:
        # Create a closure that captures hass and handler correctly
        def create_handler(h, handler_func):
            async def service_handler(call: ServiceCall) -> ServiceResponse:
                return await handler_func(h, call)
            return service_handler
        
        hass.services.async_register(
            DOMAIN,
            service_name,
            create_handler(hass, handler),
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
        _LOGGER.info("Registered service: %s.%s", DOMAIN, service_name)
    
    # Register create_zone service for programmatic zone creation
    hass.services.async_register(
        DOMAIN, 
        "create_zone", 
        handle_create_zone,
        schema=vol.Schema({
            vol.Required("zone_name"): cv.string,
            vol.Optional("light_entities", default=[]): cv.ensure_list,
        })
    )
    _LOGGER.info("Registered service: %s.create_zone", DOMAIN)
    
    # Mark as registered
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][SERVICES_REGISTERED] = True


async def _get_coordinator_from_call(hass: HomeAssistant, call: ServiceCall) -> ZoneCoordinator:
    """Get the coordinator from a service call targeting a zone or entity.
    
    This elegant helper unifies coordinator retrieval for both zone-based
    and entity-based service calls, avoiding redundant logic.
    """
    # Direct zone_id takes precedence - most efficient path
    if zone_id := call.data.get("zone_id"):
        # Iterate through lighting manager entries
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if entry_id == SERVICES_REGISTERED:
                continue
            coordinator = entry_data.get(DATA_COORDINATOR)
            if coordinator and coordinator.zone_id == zone_id:
                return coordinator
        raise ServiceValidationError(f"Zone '{zone_id}' not found")
    
    # Handle entity-based calls
    referenced = async_extract_referenced_entity_ids(hass, call)
    entity_ids = referenced.referenced | referenced.indirectly_referenced
    
    if not entity_ids:
        raise ServiceValidationError("Must provide 'zone_id' or target a lighting_manager entity")
    
    # Get coordinator from the first valid entity
    entity_reg = er.async_get(hass)
    
    for entity_id in entity_ids:
        if not (entry := entity_reg.async_get(entity_id)):
            continue
        
        # Verify it's our platform and get coordinator directly
        if entry.platform == DOMAIN and entry.config_entry_id:
            if entry_data := hass.data.get(DOMAIN, {}).get(entry.config_entry_id):
                if coordinator := entry_data.get(DATA_COORDINATOR):
                    return coordinator
    
    raise ServiceValidationError("No valid lighting_manager entity found in targets")


async def _get_switch_entities(hass: HomeAssistant, call: ServiceCall) -> list:
    """Extract and validate switch entities from service call.
    
    Returns a list of switch proxy objects with entity_id, layer_id, and coordinator.
    """
    referenced = async_extract_referenced_entity_ids(hass, call)
    entity_ids = referenced.referenced | referenced.indirectly_referenced
    
    if not entity_ids:
        raise ServiceValidationError("No target entities specified")
    
    entity_reg = er.async_get(hass)
    switches = []
    
    # Simple switch proxy to hold needed attributes
    from dataclasses import dataclass
    
    @dataclass
    class SwitchProxy:
        entity_id: str
        layer_id: str
        coordinator: ZoneCoordinator
    
    for entity_id in entity_ids:
        # Skip if not in registry or not our platform
        if not (entry := entity_reg.async_get(entity_id)) or entry.platform != DOMAIN:
            _LOGGER.warning("Entity %s is not a lighting_manager switch", entity_id)
            continue
        
        # Get state to extract layer_id
        if not (state := hass.states.get(entity_id)):
            _LOGGER.warning("Entity %s not found in states", entity_id)
            continue
        
        # Validate it's a layer switch and extract coordinator
        if (layer_id := state.attributes.get("layer_id")) and entry.config_entry_id:
            if entry_data := hass.data.get(DOMAIN, {}).get(entry.config_entry_id):
                if coordinator := entry_data.get(DATA_COORDINATOR):
                    switches.append(SwitchProxy(entity_id, layer_id, coordinator))
                else:
                    _LOGGER.warning("No coordinator found for entity %s", entity_id)
    
    if not switches:
        raise ServiceValidationError("No valid layer switches found in targets")
    
    return switches


# Service Handlers

async def handle_create_layer(hass: HomeAssistant, call: ServiceCall) -> None:
    """Create a new layer in a zone.
    
    Simple zone-based implementation that takes:
    - zone_id: The zone to create the layer in
    - layer_name: Name for the new layer
    - priority: Layer priority (optional)
    - brightness/color_temp/transition: Initial settings (optional)
    """
    layer_name = call.data.get("layer_name")
    
    if not layer_name:
        raise ServiceValidationError("layer_name is required")
    
    # Use unified helper to get coordinator
    coordinator = await _get_coordinator_from_call(hass, call)
    
    # Build layer attributes
    attributes = {}
    if "brightness" in call.data:
        attributes[ATTR_BRIGHTNESS] = call.data["brightness"]
    if "color_temp" in call.data:
        attributes[ATTR_COLOR_TEMP] = call.data["color_temp"]
    if "transition" in call.data:
        attributes[ATTR_TRANSITION] = call.data["transition"]
    
    priority = call.data.get("priority", 50)
    
    # Create the layer
    try:
        layer_id = await coordinator.create_layer(
            layer_name=layer_name,
            priority=priority,
            **attributes
        )
        _LOGGER.info("Created layer %s in zone %s", layer_id, zone_id)
    except Exception as e:
        _LOGGER.error("Failed to create layer in zone %s: %s", zone_id, e)
        raise ServiceValidationError(f"Failed to create layer: {e}")


async def handle_set_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Set (create or update) a layer - idempotent operation.
    
    This is THE SINGLE ENTRY POINT for all layer configuration.
    """
    zone_id = call.data["zone_id"]
    layer_id = call.data["layer_id"]  # Required for idempotent operation
    
    try:
        # Get the coordinator for this zone
        coordinator = await _get_coordinator_from_call(hass, call)
        
        # Build complete layer data
        layer_data = {}
        
        # Copy all provided attributes except zone_id and layer_id
        for key, value in call.data.items():
            if key not in ["zone_id", "layer_id"]:
                layer_data[key] = value
        
        # Set defaults if not provided
        if "layer_name" not in layer_data:
            layer_data["layer_name"] = layer_id.replace("_", " ").title()
        if "layer_type" not in layer_data:
            layer_data["layer_type"] = LAYER_TYPE_ABSOLUTE
        if "priority" not in layer_data:
            layer_data["priority"] = DEFAULT_PRIORITY
        if "is_on" not in layer_data:
            layer_data["is_on"] = False
        if "source" not in layer_data:
            layer_data["source"] = "service.set_layer"
        
        # Validate and set defaults based on layer type
        layer_type = layer_data.get("layer_type", LAYER_TYPE_ABSOLUTE)
        if layer_type == LAYER_TYPE_ABSOLUTE:
            # Ensure absolute layers have required attributes
            if "brightness" not in layer_data:
                layer_data["brightness"] = 255
            if "color_temp" not in layer_data:
                layer_data["color_temp"] = 370
        
        # Validate specific attributes
        if "brightness" in layer_data:
            layer_data["brightness"] = validate_brightness(layer_data["brightness"])
        if "color_temp" in layer_data:
            layer_data["color_temp"] = validate_color_temp(layer_data["color_temp"])
        if "rgb_color" in layer_data:
            layer_data["rgb_color"] = validate_rgb_color(layer_data["rgb_color"])
        if "priority" in layer_data:
            layer_data["priority"] = validate_priority(layer_data["priority"])
        if "transition" in layer_data:
            layer_data["transition"] = validate_transition(layer_data["transition"])
        
        # Call the single entry point in LayerManager
        success, action = coordinator.layer_manager.set_layer(layer_id, layer_data)
        
        # Save if needed
        if coordinator.layer_manager.has_pending_save():
            await coordinator.layer_manager.save()
        
        # Fire event
        hass.bus.async_fire(
            f"{DOMAIN}_layer_{action}",
            {
                "zone_id": zone_id,
                "layer_id": layer_id,
                "action": action,
                "layer_data": layer_data,
                "timestamp": dt_util.now().isoformat(),
            }
        )
        
        return {
            "success": success,
            "zone_id": zone_id,
            "layer_id": layer_id,
            "action": action,
        }
        
    except ServiceValidationError:
        raise
    except Exception as e:
        _LOGGER.error("Failed to set layer %s in zone %s: %s", layer_id, zone_id, e)
        raise ServiceValidationError(f"Failed to set layer: {str(e)}")


async def handle_activate_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Activate layer with specified parameters."""
    
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )
    
    # Prepare activation data
    activation_data = {
        ATTR_IS_ON: True,
        ATTR_SOURCE: call.data.get(ATTR_SOURCE, "service.activate_layer"),
    }
    
    # Add optional parameters with validation
    if ATTR_BRIGHTNESS in call.data:
        activation_data[ATTR_BRIGHTNESS] = validate_brightness(call.data[ATTR_BRIGHTNESS])
    if ATTR_COLOR_TEMP in call.data:
        activation_data[ATTR_COLOR_TEMP] = validate_color_temp(call.data[ATTR_COLOR_TEMP])
    if ATTR_RGB_COLOR in call.data:
        activation_data[ATTR_RGB_COLOR] = validate_rgb_color(call.data[ATTR_RGB_COLOR])
    if ATTR_TRANSITION in call.data:
        activation_data[ATTR_TRANSITION] = validate_transition(call.data[ATTR_TRANSITION])
    
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                activation_data
            )
            
            if success:
                # Fire activation event
                hass.bus.async_fire(
                    EVENT_LAYER_ACTIVATED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "activation_data": activation_data,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to activate layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_deactivate_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Deactivate specified layers."""
    
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )
    
    # Prepare deactivation data
    deactivation_data = {
        ATTR_IS_ON: False,
        ATTR_SOURCE: call.data.get(ATTR_SOURCE, "service.deactivate_layer"),
    }
    
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                deactivation_data
            )
            
            if success:
                # Fire deactivation event
                hass.bus.async_fire(
                    EVENT_LAYER_DEACTIVATED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to deactivate layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_update_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Update layer attributes without changing on/off state."""
    
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )
    
    # Prepare update data (exclude is_on)
    update_data = {}
    
    # Add optional parameters with validation
    if ATTR_BRIGHTNESS in call.data:
        update_data[ATTR_BRIGHTNESS] = validate_brightness(call.data[ATTR_BRIGHTNESS])
    if ATTR_COLOR_TEMP in call.data:
        update_data[ATTR_COLOR_TEMP] = validate_color_temp(call.data[ATTR_COLOR_TEMP])
    if ATTR_RGB_COLOR in call.data:
        update_data[ATTR_RGB_COLOR] = validate_rgb_color(call.data[ATTR_RGB_COLOR])
    if ATTR_TRANSITION in call.data:
        update_data[ATTR_TRANSITION] = validate_transition(call.data[ATTR_TRANSITION])
    
    if not update_data:
        return ServiceResponse(
            iserr=True,
            data={"error": "No attributes to update"}
        )
    
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                update_data
            )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
                "updated": list(update_data.keys()),
            })
            
        except Exception as e:
            _LOGGER.error("Failed to update layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_set_layer_priority(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Set priority for specified layers."""
    
    try:
        switches = await _get_switch_entities(hass, call)
        priority = validate_priority(call.data[ATTR_PRIORITY])
    except (ServiceValidationError, ValueError) as e:
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )
    
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                {ATTR_PRIORITY: priority}
            )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
                "new_priority": priority,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to set priority for %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_lock_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Lock layers to prevent modifications."""
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                {ATTR_LOCKED: True}
            )
            if success:
                hass.bus.async_fire(
                    EVENT_LAYER_LOCKED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
            })
        except Exception as e:
            _LOGGER.error("Failed to lock layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(iserr=False, data={"results": results})


async def handle_unlock_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Unlock layers to allow modifications."""
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    results = []
    for switch in switches:
        try:
            success = switch.coordinator.layer_manager.update_layer(
                switch.layer_id,
                {ATTR_LOCKED: False}
            )
            if success:
                hass.bus.async_fire(
                    EVENT_LAYER_UNLOCKED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
            })
        except Exception as e:
            _LOGGER.error("Failed to unlock layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(iserr=False, data={"results": results})


async def handle_force_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Force layer to override priority system."""
    zone_id = call.data["zone_id"]
    layer_id = call.data["layer_id"]
    force_value = call.data.get("force", True)
    
    try:
        coordinator = await _get_coordinator_from_call(hass, call)
        success = coordinator.layer_manager.update_layer(
            layer_id,
            {ATTR_FORCE: force_value}
        )
        
        if success:
            hass.bus.async_fire(
                EVENT_LAYER_FORCED,
                {
                    "zone_id": zone_id,
                    "layer_id": layer_id,
                    "forced": force_value,
                    "timestamp": dt_util.now().isoformat(),
                }
            )
        
        return ServiceResponse(
            iserr=False,
            data={
                "success": success,
                "zone_id": zone_id,
                "layer_id": layer_id,
                "forced": force_value,
            }
        )
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    except Exception as e:
        _LOGGER.error("Failed to force layer %s in zone %s: %s", layer_id, zone_id, e)
        return ServiceResponse(iserr=True, data={"error": f"Failed to force layer: {str(e)}"})


async def handle_unforce_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Remove force flag from layer."""
    zone_id = call.data["zone_id"]
    layer_id = call.data["layer_id"]
    
    try:
        coordinator = await _get_coordinator_from_call(hass, call)
        success = coordinator.layer_manager.update_layer(
            layer_id,
            {ATTR_FORCE: False}
        )
        
        if success:
            hass.bus.async_fire(
                EVENT_LAYER_FORCED,
                {
                    "zone_id": zone_id,
                    "layer_id": layer_id,
                    "forced": False,
                    "timestamp": dt_util.now().isoformat(),
                }
            )
        
        return ServiceResponse(
            iserr=False,
            data={
                "success": success,
                "zone_id": zone_id,
                "layer_id": layer_id,
                "forced": False,
            }
        )
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    except Exception as e:
        _LOGGER.error("Failed to unforce layer %s in zone %s: %s", layer_id, zone_id, e)
        return ServiceResponse(iserr=True, data={"error": f"Failed to unforce layer: {str(e)}"})


async def handle_recalculate_zone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Force immediate recalculation for a zone."""
    zone_id = call.data["zone_id"]
    
    try:
        coordinator = await _get_coordinator_from_call(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    try:
        # Force immediate recalculation
        await coordinator.async_refresh()
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "success": True,
                "winning_layer": coordinator.data.get("winning_layer"),
                "final_state": coordinator.data.get("final_state"),
            }
        )
    except Exception as e:
        _LOGGER.error("Failed to recalculate zone %s: %s", zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )


async def handle_delete_zone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Delete a zone and clean up all related entities."""
    zone_id = call.data["zone_id"]
    
    # Find the config entry for this zone
    config_entry = None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("zone_id") == zone_id:
            config_entry = entry
            break
    
    if not config_entry:
        raise ServiceValidationError(f"Zone {zone_id} not found")
    
    try:
        # Remove the config entry (which will trigger async_unload_entry)
        await hass.config_entries.async_remove(config_entry.entry_id)
        
        # Clean up any leftover entities
        entity_registry = er.async_get(hass)
        entries_to_remove = []
        
        # Find all entities related to this zone
        for entity_id, entry in entity_registry.entities.items():
            if zone_id in entity_id:
                entries_to_remove.append(entity_id)
        
        # Remove found entities
        for entity_id in entries_to_remove:
            entity_registry.async_remove(entity_id)
            _LOGGER.info("Removed entity: %s", entity_id)
        
        return {
            "zone_id": zone_id,
            "success": True,
            "entities_removed": len(entries_to_remove),
            "message": f"Zone {zone_id} deleted successfully"
        }
    except Exception as e:
        _LOGGER.error("Failed to delete zone %s: %s", zone_id, e)
        raise HomeAssistantError(f"Failed to delete zone: {str(e)}")


async def handle_reset_zone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Reset zone by deactivating all layers except base."""
    zone_id = call.data["zone_id"]
    
    try:
        coordinator = await _get_coordinator_from_call(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    try:
        # Deactivate all layers except base_adaptive
        from .const import LAYER_BASE_ADAPTIVE
        
        for layer_id in list(coordinator.layers.keys()):
            if layer_id != LAYER_BASE_ADAPTIVE:
                coordinator.layer_manager.update_layer(layer_id, {ATTR_IS_ON: False})
        
        # Fire reset event
        hass.bus.async_fire(
            EVENT_ZONE_RESET,
            {
                "zone_id": zone_id,
                "timestamp": dt_util.now().isoformat(),
            }
        )
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "success": True,
                "layers_reset": len(coordinator.layers) - 1,
            }
        )
    except Exception as e:
        _LOGGER.error("Failed to reset zone %s: %s", zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )


async def handle_apply_preset(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Apply a preset configuration atomically."""
    zone_id = call.data["zone_id"]
    preset_name = call.data["preset_name"]
    transition = call.data.get(ATTR_TRANSITION, 2.0)
    
    try:
        coordinator = await _get_coordinator_from_call(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    # Define presets
    presets = {
        "bright": {"brightness": 255, "color_temp": 153, "is_on": True},
        "dim": {"brightness": 77, "color_temp": 370, "is_on": True},
        "movie": {"brightness": 30, "color_temp": 500, "is_on": True},
        "adaptive": {"is_on": False},  # Turn off manual, let adaptive take over
        "off": {"is_on": False},
    }
    
    if preset_name not in presets:
        return ServiceResponse(
            iserr=True,
            data={"error": f"Unknown preset: {preset_name}"}
        )
    
    try:
        preset_data = presets[preset_name]
        preset_data[ATTR_TRANSITION] = transition
        
        # Apply to manual layer or create if doesn't exist
        # Use set_layer for idempotent operation
        layer_data = {
            "layer_name": "Manual",
            "priority": 50,
            **preset_data
        }
        coordinator.layer_manager.set_layer("manual", layer_data)
        
        # Fire preset event
        hass.bus.async_fire(
            EVENT_PRESET_APPLIED,
            {
                "zone_id": zone_id,
                "preset_name": preset_name,
                "timestamp": dt_util.now().isoformat(),
            }
        )
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "preset_name": preset_name,
                "success": True,
            }
        )
    except Exception as e:
        _LOGGER.error("Failed to apply preset %s to zone %s: %s", preset_name, zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )


def unload_services(hass: HomeAssistant) -> None:
    """Unload all lighting manager services."""
    _LOGGER.info("Unloading lighting manager services")
    
    # List of all service names to unload
    services = [
        "set_layer",
        "update_layer",
        "delete_layer",
        "activate_layer",
        "deactivate_layer",
        "clear_zone",
        "recalculate_zone",
        "list_layers",
        "get_layer",
        "lock_layer",
        "unlock_layer",
        "force_layer",
        "apply_preset",
        "create_layer",
    ]
    
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
            _LOGGER.debug("Removed service: %s", service)
    
    _LOGGER.info("All lighting manager services unloaded")