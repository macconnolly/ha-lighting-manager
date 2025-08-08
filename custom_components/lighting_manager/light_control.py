"""Light control module for Lighting Manager.

This module handles applying calculated states to actual lights,
managing transitions, and handling light capability differences.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import EVENT_STATE_APPLIED

_LOGGER = logging.getLogger(__name__)


class LightController:
    """Controller for applying calculated states to lights.
    
    Handles the complexity of different light capabilities and
    ensures atomic updates across all lights in a zone.
    """
    
    def __init__(self, hass: HomeAssistant, zone_id: str, light_entities: list[str]):
        """Initialize the light controller.
        
        Args:
            hass: Home Assistant instance
            zone_id: The zone this controller manages
            light_entities: List of light entity IDs to control
        """
        self.hass = hass
        self.zone_id = zone_id
        self.light_entities = light_entities
        self._unavailable_queue: dict[str, dict[str, Any]] = {}
        
        _LOGGER.info("Light controller initialized for zone %s with %d lights",
                    zone_id, len(light_entities))
    
    async def apply_state(self, final_state: dict[str, Any]) -> bool:
        """Apply the calculated state to all lights.
        
        Args:
            final_state: The final state from calculator containing:
                - power: "on" or "off"
                - brightness: Optional 0-255
                - color_temp: Optional mireds
                - rgb_color: Optional (r, g, b)
                - transition: Optional seconds
                
        Returns:
            True if successfully applied to at least one light
        """
        if not self.light_entities:
            _LOGGER.warning("No lights configured for zone %s", self.zone_id)
            return False
        
        power = final_state.get("power", "off")
        
        if power == "off":
            return await self._turn_off_lights(final_state)
        else:
            return await self._turn_on_lights(final_state)
    
    async def _turn_on_lights(self, final_state: dict[str, Any]) -> bool:
        """Turn on lights with the specified attributes.
        
        This method handles different light capabilities and applies
        the state atomically to all lights.
        """
        # Build service data
        service_data = {
            ATTR_ENTITY_ID: [],
        }
        
        # Add optional attributes
        if ATTR_BRIGHTNESS in final_state:
            service_data[ATTR_BRIGHTNESS] = final_state[ATTR_BRIGHTNESS]
        
        if ATTR_COLOR_TEMP in final_state:
            service_data[ATTR_COLOR_TEMP] = final_state[ATTR_COLOR_TEMP]
        
        if ATTR_RGB_COLOR in final_state:
            service_data[ATTR_RGB_COLOR] = final_state[ATTR_RGB_COLOR]
        
        if ATTR_TRANSITION in final_state:
            service_data[ATTR_TRANSITION] = final_state[ATTR_TRANSITION]
        
        # Separate lights by availability and capability
        available_lights = []
        unavailable_lights = []
        
        for entity_id in self.light_entities:
            state = self.hass.states.get(entity_id)
            
            if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                unavailable_lights.append(entity_id)
                # Queue the command for when light becomes available
                self._unavailable_queue[entity_id] = final_state
            else:
                # Check light capabilities
                if self._light_supports_features(state, final_state):
                    available_lights.append(entity_id)
                else:
                    # Apply with reduced features
                    await self._apply_with_reduced_features(entity_id, final_state)
        
        # Apply to all capable lights at once (atomic)
        if available_lights:
            service_data[ATTR_ENTITY_ID] = available_lights
            
            try:
                await self.hass.services.async_call(
                    LIGHT_DOMAIN,
                    SERVICE_TURN_ON,
                    service_data,
                    blocking=True,
                )
                
                # Fire event
                self.hass.bus.async_fire(
                    EVENT_STATE_APPLIED,
                    {
                        "zone_id": self.zone_id,
                        "lights_updated": len(available_lights),
                        "lights_unavailable": len(unavailable_lights),
                        "final_state": final_state,
                    }
                )
                
                _LOGGER.debug("Applied state to %d lights in zone %s",
                            len(available_lights), self.zone_id)
                return True
                
            except Exception as e:
                _LOGGER.error("Failed to apply state to lights in zone %s: %s",
                            self.zone_id, e)
                return False
        
        if unavailable_lights:
            _LOGGER.warning("%d lights unavailable in zone %s, state queued",
                          len(unavailable_lights), self.zone_id)
        
        return False
    
    async def _turn_off_lights(self, final_state: dict[str, Any]) -> bool:
        """Turn off all lights in the zone."""
        service_data = {
            ATTR_ENTITY_ID: self.light_entities,
        }
        
        # Add transition if specified
        if ATTR_TRANSITION in final_state:
            service_data[ATTR_TRANSITION] = final_state[ATTR_TRANSITION]
        
        try:
            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_OFF,
                service_data,
                blocking=True,
            )
            
            # Clear queued commands
            self._unavailable_queue.clear()
            
            # Fire event
            self.hass.bus.async_fire(
                EVENT_STATE_APPLIED,
                {
                    "zone_id": self.zone_id,
                    "lights_updated": len(self.light_entities),
                    "final_state": final_state,
                }
            )
            
            _LOGGER.debug("Turned off %d lights in zone %s",
                        len(self.light_entities), self.zone_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to turn off lights in zone %s: %s",
                        self.zone_id, e)
            return False
    
    def _light_supports_features(self, state: State, final_state: dict[str, Any]) -> bool:
        """Check if a light supports the requested features.
        
        This checks the light's attributes to determine what it supports.
        """
        attributes = state.attributes
        
        # Check brightness support
        if ATTR_BRIGHTNESS in final_state:
            if not attributes.get("supported_features", 0) & 1:  # SUPPORT_BRIGHTNESS
                return False
        
        # Check color temp support
        if ATTR_COLOR_TEMP in final_state:
            if "min_mireds" not in attributes or "max_mireds" not in attributes:
                return False
            
            # Check if requested temp is in range
            min_mireds = attributes["min_mireds"]
            max_mireds = attributes["max_mireds"]
            requested = final_state[ATTR_COLOR_TEMP]
            
            if not (min_mireds <= requested <= max_mireds):
                _LOGGER.debug("Light %s doesn't support color temp %d (range %d-%d)",
                            state.entity_id, requested, min_mireds, max_mireds)
                return False
        
        # Check RGB support
        if ATTR_RGB_COLOR in final_state:
            if not attributes.get("supported_features", 0) & 16:  # SUPPORT_COLOR
                return False
        
        return True
    
    async def _apply_with_reduced_features(
        self, 
        entity_id: str, 
        final_state: dict[str, Any]
    ) -> None:
        """Apply state with reduced features for limited lights.
        
        This handles lights that don't support all requested features.
        """
        state = self.hass.states.get(entity_id)
        if not state:
            return
        
        # Build reduced service data
        service_data = {
            ATTR_ENTITY_ID: entity_id,
        }
        
        # Only add supported features
        if ATTR_BRIGHTNESS in final_state:
            if state.attributes.get("supported_features", 0) & 1:
                service_data[ATTR_BRIGHTNESS] = final_state[ATTR_BRIGHTNESS]
        
        if ATTR_TRANSITION in final_state:
            service_data[ATTR_TRANSITION] = final_state[ATTR_TRANSITION]
        
        # Skip color temp and RGB if not supported
        
        try:
            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_ON,
                service_data,
                blocking=False,
            )
            _LOGGER.debug("Applied reduced state to light %s", entity_id)
        except Exception as e:
            _LOGGER.error("Failed to apply reduced state to %s: %s", entity_id, e)
    
    async def apply_queued_states(self) -> None:
        """Apply any queued states to lights that have become available.
        
        This should be called periodically or when light availability changes.
        """
        if not self._unavailable_queue:
            return
        
        applied = []
        for entity_id, queued_state in list(self._unavailable_queue.items()):
            state = self.hass.states.get(entity_id)
            
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                # Light is now available, apply queued state
                if await self._apply_with_reduced_features(entity_id, queued_state):
                    applied.append(entity_id)
        
        # Remove successfully applied states from queue
        for entity_id in applied:
            del self._unavailable_queue[entity_id]
        
        if applied:
            _LOGGER.info("Applied queued states to %d lights in zone %s",
                        len(applied), self.zone_id)
    
    def update_light_entities(self, light_entities: list[str]) -> None:
        """Update the list of controlled light entities.
        
        Called when zone configuration changes.
        """
        self.light_entities = light_entities
        
        # Remove queued states for lights no longer in zone
        for entity_id in list(self._unavailable_queue.keys()):
            if entity_id not in light_entities:
                del self._unavailable_queue[entity_id]
        
        _LOGGER.info("Updated light entities for zone %s: %d lights",
                    self.zone_id, len(light_entities))