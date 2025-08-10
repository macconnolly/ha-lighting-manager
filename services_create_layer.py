"""Create layer service implementation."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_TRANSITION,
    DATA_COORDINATOR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def handle_create_layer(hass: HomeAssistant, call: ServiceCall) -> None:
    """Create a new layer in a zone.
    
    Simple zone-based implementation that takes:
    - zone_id: The zone to create the layer in
    - layer_name: Name for the new layer
    - priority: Layer priority (optional)
    - brightness/color_temp/transition: Initial settings (optional)
    """
    zone_id = call.data.get("zone_id")
    layer_name = call.data.get("layer_name")
    
    if not zone_id:
        raise ServiceValidationError("zone_id is required")
    if not layer_name:
        raise ServiceValidationError("layer_name is required")
    
    # Find the coordinator for this zone
    coordinator = None
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if entry_id == "services_registered":
            continue
        coord = entry_data.get(DATA_COORDINATOR)
        if coord and coord.zone_id == zone_id:
            coordinator = coord
            break
    
    if not coordinator:
        raise ServiceValidationError(f"Zone '{zone_id}' not found")
    
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