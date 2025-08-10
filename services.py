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
    ATTR_COLOR_TEMP,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAYER_NAME,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    DATA_COORDINATOR,
    DOMAIN,
    EVENT_LAYER_ACTIVATED,
    EVENT_LAYER_DEACTIVATED,
    EVENT_LAYER_FORCED,
    EVENT_LAYER_LOCKED,
    EVENT_LAYER_UNLOCKED,
    EVENT_PRESET_APPLIED,
    EVENT_ZONE_RESET,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_APPLY_PRESET,
    SERVICE_DEACTIVATE_LAYER,
    SERVICE_FORCE_LAYER,
    SERVICE_LOCK_LAYER,
    SERVICE_RECALCULATE_ZONE,
    SERVICE_RESET_ZONE,
    SERVICE_SET_LAYER_PRIORITY,
    SERVICE_UNFORCE_LAYER,
    SERVICE_UNLOCK_LAYER,
    SERVICE_UPDATE_LAYER,
    SERVICES_REGISTERED,
)
from .validation import (
    validate_brightness,
    validate_color_temp,
    validate_priority,
    validate_rgb_color,
    validate_transition,
)

_LOGGER = logging.getLogger(__name__)

# Service Schemas
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

SERVICE_LOCK_UNLOCK_SCHEMA = vol.Schema({})

SERVICE_FORCE_SCHEMA = vol.Schema({
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


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Phase 3 services."""
    
    # Check if already registered
    if SERVICES_REGISTERED in hass.data.get(DOMAIN, {}):
        return
    
    # Register all services
    services = [
        # Layer Control Services
        (SERVICE_ACTIVATE_LAYER, handle_activate_layer, SERVICE_ACTIVATE_LAYER_SCHEMA),
        (SERVICE_DEACTIVATE_LAYER, handle_deactivate_layer, SERVICE_DEACTIVATE_LAYER_SCHEMA),
        (SERVICE_UPDATE_LAYER, handle_update_layer, SERVICE_UPDATE_LAYER_SCHEMA),
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
    
    # Mark as registered
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][SERVICES_REGISTERED] = True


async def _get_switch_entities(hass: HomeAssistant, call: ServiceCall) -> list:
    """Extract and validate switch entities from service call."""
    # Extract referenced entities
    referenced = async_extract_referenced_entity_ids(hass, call)
    entity_ids = referenced.referenced | referenced.indirectly_referenced
    
    if not entity_ids:
        raise ServiceValidationError("No target entities specified")
    
    # Get entity registry
    entity_reg = er.async_get(hass)
    switches = []
    
    for entity_id in entity_ids:
        # Get entity from registry
        entry = entity_reg.async_get(entity_id)
        if not entry or entry.platform != DOMAIN:
            _LOGGER.warning("Entity %s is not a lighting_manager switch", entity_id)
            continue
        
        # Get the actual switch entity
        state = hass.states.get(entity_id)
        if not state:
            _LOGGER.warning("Entity %s not found in states", entity_id)
            continue
        
        # Check if this is a layer switch by checking the registry entry
        # and state attributes
        if (entry.platform == DOMAIN and 
            state.attributes.get("layer_id") and 
            state.attributes.get("zone_id")):
            # Create a simple object that has the needed attributes
            class SwitchProxy:
                def __init__(self, entity_id, state, entry):
                    self.entity_id = entity_id
                    self.layer_id = state.attributes.get("layer_id")
                    # Get coordinator from domain data
                    config_entry_id = entry.config_entry_id
                    if config_entry_id in hass.data[DOMAIN]:
                        self.coordinator = hass.data[DOMAIN][config_entry_id].get(DATA_COORDINATOR)
            
            proxy = SwitchProxy(entity_id, state, entry)
            if proxy.coordinator:
                switches.append(proxy)
            else:
                _LOGGER.warning("No coordinator found for entity %s", entity_id)
        else:
            _LOGGER.warning("Entity %s is not a valid layer switch", entity_id)
    
    if not switches:
        raise ServiceValidationError("No valid layer switches found in targets")
    
    return switches


async def _get_zone_coordinator(hass: HomeAssistant, zone_id: str):
    """Get coordinator for a specific zone."""
    # Find the config entry for this zone
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if entry_id == SERVICES_REGISTERED:
            continue
        
        coordinator = entry_data.get(DATA_COORDINATOR)
        if coordinator and coordinator.zone_id == zone_id:
            return coordinator
    
    raise ServiceValidationError(f"Zone '{zone_id}' not found")


# Service Handlers

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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **activation_data
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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **deactivation_data
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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **update_data
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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_PRIORITY: priority}
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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_LOCKED: True}
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
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_LOCKED: False}
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
    """Force layers to override priority system."""
    try:
        switches = await _get_switch_entities(hass, call)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    force_value = call.data.get("force", True)
    results = []
    for switch in switches:
        try:
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_FORCE: force_value}
            )
            if success and force_value:
                hass.bus.async_fire(
                    EVENT_LAYER_FORCED,
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
                "forced": force_value,
            })
        except Exception as e:
            _LOGGER.error("Failed to force layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(iserr=False, data={"results": results})


async def handle_unforce_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Remove force flag from layers."""
    call.data["force"] = False
    return await handle_force_layer(hass, call)


async def handle_recalculate_zone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Force immediate recalculation for a zone."""
    zone_id = call.data["zone_id"]
    
    try:
        coordinator = await _get_zone_coordinator(hass, zone_id)
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


async def handle_reset_zone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Reset zone by deactivating all layers except base."""
    zone_id = call.data["zone_id"]
    
    try:
        coordinator = await _get_zone_coordinator(hass, zone_id)
    except ServiceValidationError as e:
        return ServiceResponse(iserr=True, data={"error": str(e)})
    
    try:
        # Deactivate all layers except base_adaptive
        from .const import LAYER_BASE_ADAPTIVE
        
        for layer_id in list(coordinator.layers.keys()):
            if layer_id != LAYER_BASE_ADAPTIVE:
                await coordinator.update_layer(layer_id, **{ATTR_IS_ON: False})
        
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
        coordinator = await _get_zone_coordinator(hass, zone_id)
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
        if "manual" not in coordinator.layers:
            await coordinator.create_layer("Manual", priority=50, **preset_data)
        else:
            await coordinator.update_layer("manual", **preset_data)
        
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