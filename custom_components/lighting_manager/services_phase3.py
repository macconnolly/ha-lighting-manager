"""Additional Phase 3 service handlers for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import ServiceCall, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LOCKED,
    ATTR_TRANSITION,
    EVENT_LAYER_FORCED,
    EVENT_LAYER_LOCKED,
    EVENT_LAYER_UNLOCKED,
    EVENT_PRESET_APPLIED,
    EVENT_ZONE_RESET,
)

_LOGGER = logging.getLogger(__name__)


async def handle_lock_layer(hass, call: ServiceCall, switches) -> ServiceResponse:
    """Lock layers to prevent modifications."""
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            # Get current state for audit
            current_layer = switch.coordinator.get_layer(switch.layer_id)
            if not current_layer:
                results.append({
                    "entity_id": switch.entity_id,
                    "success": False,
                    "error": "Layer not found",
                })
                continue
            
            # Check if already locked
            if current_layer.get(ATTR_LOCKED, False):
                results.append({
                    "entity_id": switch.entity_id,
                    "success": False,
                    "error": "Already locked",
                    "was_locked": True,
                })
                continue
            
            # Lock the layer
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_LOCKED: True}
            )
            
            if success:
                # Fire security event
                hass.bus.async_fire(
                    EVENT_LAYER_LOCKED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "locked_by": call.context.user_id,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
                
                _LOGGER.info(
                    "Layer %s in zone %s locked by %s",
                    switch.layer_id,
                    switch.coordinator.zone_id,
                    call.context.user_id
                )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
                "locked": success,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to lock layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_unlock_layer(hass, call: ServiceCall, switches) -> ServiceResponse:
    """Unlock layers to allow modifications."""
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            # Get current state for audit
            current_layer = switch.coordinator.get_layer(switch.layer_id)
            if not current_layer:
                results.append({
                    "entity_id": switch.entity_id,
                    "success": False,
                    "error": "Layer not found",
                })
                continue
            
            # Check if already unlocked
            if not current_layer.get(ATTR_LOCKED, False):
                results.append({
                    "entity_id": switch.entity_id,
                    "success": False,
                    "error": "Not locked",
                    "was_locked": False,
                })
                continue
            
            # Unlock the layer
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_LOCKED: False}
            )
            
            if success:
                # Fire security event
                hass.bus.async_fire(
                    EVENT_LAYER_UNLOCKED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "unlocked_by": call.context.user_id,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
                
                _LOGGER.info(
                    "Layer %s in zone %s unlocked by %s",
                    switch.layer_id,
                    switch.coordinator.zone_id,
                    call.context.user_id
                )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
                "locked": not success,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to unlock layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_force_layer(hass, call: ServiceCall, switches) -> ServiceResponse:
    """Force layers to override priority system."""
    force = call.data.get("force", True)
    
    # Execute on all targets
    results = []
    for switch in switches:
        try:
            success = await switch.coordinator.update_layer(
                switch.layer_id,
                **{ATTR_FORCE: force}
            )
            
            if success:
                # Fire force event
                hass.bus.async_fire(
                    EVENT_LAYER_FORCED,
                    {
                        "zone_id": switch.coordinator.zone_id,
                        "layer_id": switch.layer_id,
                        "forced": force,
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
                
                _LOGGER.info(
                    "Layer %s in zone %s force flag set to %s",
                    switch.layer_id,
                    switch.coordinator.zone_id,
                    force
                )
            
            results.append({
                "entity_id": switch.entity_id,
                "success": success,
                "layer_id": switch.layer_id,
                "forced": force if success else None,
            })
            
        except Exception as e:
            _LOGGER.error("Failed to force layer %s: %s", switch.entity_id, e)
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": str(e),
            })
    
    return ServiceResponse(
        iserr=False,
        data={"results": results}
    )


async def handle_recalculate_zone(hass, zone_id: str, coordinator) -> ServiceResponse:
    """Force immediate recalculation for a zone."""
    try:
        # Force immediate refresh
        await coordinator.async_refresh()
        
        _LOGGER.info("Forced recalculation for zone %s", zone_id)
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "success": True,
                "winning_layer": coordinator._last_calculation.get("winning_layer") if coordinator._last_calculation else None,
                "active_layers": len([l for l in coordinator.layers.values() if l.get(ATTR_IS_ON, False)]),
            }
        )
        
    except Exception as e:
        _LOGGER.error("Failed to recalculate zone %s: %s", zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )


async def handle_reset_zone(hass, zone_id: str, coordinator) -> ServiceResponse:
    """Reset zone by deactivating all layers except base."""
    try:
        # Deactivate all layers except base_adaptive
        deactivated = []
        for layer_id, layer in coordinator.layers.items():
            if layer_id != "base_adaptive" and layer.get(ATTR_IS_ON, False):
                success = await coordinator.update_layer(
                    layer_id,
                    **{ATTR_IS_ON: False}
                )
                if success:
                    deactivated.append(layer_id)
        
        # Fire reset event
        hass.bus.async_fire(
            EVENT_ZONE_RESET,
            {
                "zone_id": zone_id,
                "deactivated_layers": deactivated,
                "timestamp": dt_util.now().isoformat(),
            }
        )
        
        _LOGGER.info("Reset zone %s, deactivated %d layers", zone_id, len(deactivated))
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "success": True,
                "deactivated_layers": deactivated,
                "deactivated_count": len(deactivated),
            }
        )
        
    except Exception as e:
        _LOGGER.error("Failed to reset zone %s: %s", zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )


async def handle_apply_preset(hass, zone_id: str, preset_name: str, coordinator, transition: float) -> ServiceResponse:
    """Apply a preset configuration atomically."""
    # Define built-in presets
    presets = {
        "bright": {
            "layers": {
                "manual": {
                    ATTR_IS_ON: True,
                    "brightness": 255,
                    "color_temp": 200,
                    "transition": transition,
                }
            }
        },
        "dim": {
            "layers": {
                "manual": {
                    ATTR_IS_ON: True,
                    "brightness": 50,
                    "color_temp": 400,
                    "transition": transition,
                }
            }
        },
        "movie": {
            "layers": {
                "mode": {
                    ATTR_IS_ON: True,
                    "brightness": 30,
                    "color_temp": 500,
                    "transition": transition,
                },
                "manual": {ATTR_IS_ON: False},
                "activity": {ATTR_IS_ON: False},
            }
        },
        "adaptive": {
            "layers": {
                "base_adaptive": {ATTR_IS_ON: True},
                "environmental": {ATTR_IS_ON: True},
                "activity": {ATTR_IS_ON: True},
                "mode": {ATTR_IS_ON: False},
                "manual": {ATTR_IS_ON: False},
            }
        },
        "off": {
            "layers": {
                layer_id: {ATTR_IS_ON: False}
                for layer_id in coordinator.layers.keys()
            }
        },
    }
    
    # Get preset definition
    preset = presets.get(preset_name)
    if not preset:
        return ServiceResponse(
            iserr=True,
            data={"error": f"Unknown preset '{preset_name}'. Available: {list(presets.keys())}"}
        )
    
    try:
        # Apply preset atomically
        changes = []
        
        # First, process layers mentioned in preset
        for layer_id, layer_config in preset.get("layers", {}).items():
            if layer_id in coordinator.layers:
                success = await coordinator.update_layer(
                    layer_id,
                    **layer_config
                )
                if success:
                    changes.append({
                        "layer_id": layer_id,
                        "action": "updated",
                        "state": layer_config.get(ATTR_IS_ON, False),
                    })
        
        # Fire preset event
        hass.bus.async_fire(
            EVENT_PRESET_APPLIED,
            {
                "zone_id": zone_id,
                "preset_name": preset_name,
                "changes": changes,
                "timestamp": dt_util.now().isoformat(),
            }
        )
        
        _LOGGER.info(
            "Applied preset '%s' to zone %s with %d changes",
            preset_name,
            zone_id,
            len(changes)
        )
        
        return ServiceResponse(
            iserr=False,
            data={
                "zone_id": zone_id,
                "preset_name": preset_name,
                "success": True,
                "changes_made": len(changes),
                "changes": changes,
            }
        )
        
    except Exception as e:
        _LOGGER.error("Failed to apply preset %s to zone %s: %s", preset_name, zone_id, e)
        return ServiceResponse(
            iserr=True,
            data={"error": str(e)}
        )