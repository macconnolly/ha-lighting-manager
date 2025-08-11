"""Change Detector - Detects manual control and creates override layers."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .layer_manager import LayerManager
    from .light_controller import LightController

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EXPIRES_AT,
    ATTR_IS_ON,
    ATTR_LAYER_NAME,
    ATTR_LAYER_TYPE,
    ATTR_PRIORITY,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    EVENT_MANUAL_CONTROL_DETECTED,
    EVENT_MANUAL_OVERRIDE_CREATED,
    EVENT_MANUAL_OVERRIDE_CLEARED,
    LAYER_TYPE_ABSOLUTE,
)

_LOGGER = logging.getLogger(__name__)


class ChangeDetector:
    """Detects manual control and creates override layers."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        zone_id: str,
        layer_manager: LayerManager,
        light_controller: LightController
    ) -> None:
        """Initialize change detector.
        
        Args:
            hass: Home Assistant instance
            zone_id: Zone identifier
            layer_manager: Reference to layer manager
            light_controller: Reference to light controller
        """
        self.hass = hass
        self.zone_id = zone_id
        self.layer_manager = layer_manager
        self.light_controller = light_controller
        self.manual_override_active = False
        self.last_override_id: Optional[str] = None
        self.brightness_tolerance = 13  # ~5% of 255
        self.color_temp_tolerance = 10  # mireds
        _LOGGER.info("ChangeDetector initialized for zone %s", zone_id)
    
    def check_for_manual_change(self) -> bool:
        """Check if lights were manually changed.
        
        Returns:
            True if manual change detected, False otherwise
        """
        # Don't check if we recently sent a command (within 5 seconds)
        if self.light_controller.was_recently_commanded(threshold_seconds=5):
            _LOGGER.debug("Skipping check - recent command sent")
            return False
        
        # Get current and commanded states
        current_state = self.light_controller.get_current_state()
        commanded_state = self.light_controller.last_commanded_state
        
        # No commanded state yet means no baseline
        if not commanded_state:
            _LOGGER.debug("No commanded state yet, cannot detect changes")
            return False
        
        # Check power state change
        if current_state.get("power") != commanded_state.get("power"):
            _LOGGER.info(
                "Manual power change detected in zone %s: %s -> %s",
                self.zone_id,
                commanded_state.get("power"),
                current_state.get("power")
            )
            self._fire_manual_control_event("power", commanded_state, current_state)
            return True
        
        # If both are on, check attributes
        if current_state.get("power") == "on" and commanded_state.get("power") == "on":
            # Check brightness change
            current_brightness = current_state.get("brightness", 255)
            commanded_brightness = commanded_state.get("brightness", 255)
            brightness_diff = abs(current_brightness - commanded_brightness)
            
            if brightness_diff > self.brightness_tolerance:
                _LOGGER.info(
                    "Manual brightness change detected in zone %s: %d -> %d (diff: %d)",
                    self.zone_id,
                    commanded_brightness,
                    current_brightness,
                    brightness_diff
                )
                self._fire_manual_control_event("brightness", commanded_state, current_state)
                return True
            
            # Check color temperature change
            if "color_temp" in current_state and "color_temp" in commanded_state:
                current_ct = current_state["color_temp"]
                commanded_ct = commanded_state["color_temp"]
                ct_diff = abs(current_ct - commanded_ct)
                
                if ct_diff > self.color_temp_tolerance:
                    _LOGGER.info(
                        "Manual color temp change detected in zone %s: %d -> %d (diff: %d)",
                        self.zone_id,
                        commanded_ct,
                        current_ct,
                        ct_diff
                    )
                    self._fire_manual_control_event("color_temp", commanded_state, current_state)
                    return True
        
        return False
    
    def create_manual_override(self, timeout_hours: float = 2.0) -> str:
        """Create a manual override layer based on current light state.
        
        Args:
            timeout_hours: Hours until override expires
            
        Returns:
            Layer ID of created override
        """
        # Remove old override if exists
        if self.last_override_id:
            self._clear_existing_override()
        
        # Get current light state
        current_state = self.light_controller.get_current_state()
        now = dt_util.now()
        
        # Generate unique override ID
        override_id = f"manual_override_{int(now.timestamp())}"
        
        # Create override layer
        override_layer = {
            ATTR_LAYER_NAME: "Manual Override",
            ATTR_IS_ON: current_state.get("power") == "on",
            ATTR_PRIORITY: 95,  # High priority
            ATTR_SOURCE: "manual_override",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_TRANSITION: 0.5,  # Quick transition
            ATTR_EXPIRES_AT: (now + timedelta(hours=timeout_hours)).isoformat(),
        }
        
        # Add light attributes if on
        if current_state.get("power") == "on":
            override_layer[ATTR_BRIGHTNESS] = current_state.get("brightness", 255)
            if "color_temp" in current_state:
                override_layer[ATTR_COLOR_TEMP] = current_state["color_temp"]
        
        # Use single entry point pattern
        success, action = self.layer_manager.set_layer(override_id, override_layer)
        
        if not success:
            _LOGGER.error("Failed to create manual override layer for zone %s", self.zone_id)
            return None
        
        # Update tracking
        self.last_override_id = override_id
        self.manual_override_active = True
        
        # Fire event
        self.hass.bus.async_fire(
            EVENT_MANUAL_OVERRIDE_CREATED,
            {
                "zone_id": self.zone_id,
                "override_id": override_id,
                "current_state": current_state,
                "timeout_hours": timeout_hours,
                "expires_at": override_layer[ATTR_EXPIRES_AT],
            }
        )
        
        _LOGGER.info(
            "Created manual override %s for zone %s (expires in %.1f hours)",
            override_id, self.zone_id, timeout_hours
        )
        
        return override_id
    
    def clear_manual_override(self) -> None:
        """Clear the manual override layer."""
        if not self.last_override_id:
            _LOGGER.debug("No manual override to clear")
            return
        
        self._clear_existing_override()
        
        # Fire event
        self.hass.bus.async_fire(
            EVENT_MANUAL_OVERRIDE_CLEARED,
            {
                "zone_id": self.zone_id,
                "override_id": self.last_override_id,
            }
        )
        
        _LOGGER.info("Cleared manual override for zone %s", self.zone_id)
    
    def _clear_existing_override(self) -> None:
        """Internal method to clear existing override."""
        if self.last_override_id and self.last_override_id in self.layer_manager.layers:
            self.layer_manager.delete_layer(self.last_override_id)
            self.last_override_id = None
            self.manual_override_active = False
    
    def _fire_manual_control_event(
        self,
        change_type: str,
        commanded_state: Dict[str, Any],
        current_state: Dict[str, Any]
    ) -> None:
        """Fire event for manual control detection.
        
        Args:
            change_type: Type of change (power, brightness, color_temp)
            commanded_state: What we commanded
            current_state: What we observed
        """
        self.hass.bus.async_fire(
            EVENT_MANUAL_CONTROL_DETECTED,
            {
                "zone_id": self.zone_id,
                "change_type": change_type,
                "commanded_state": commanded_state,
                "current_state": current_state,
                "timestamp": dt_util.now().isoformat(),
            }
        )
    
    def is_override_expired(self) -> bool:
        """Check if current override has expired.
        
        Returns:
            True if override exists and is expired
        """
        if not self.last_override_id:
            return False
        
        layer = self.layer_manager.get_layer(self.last_override_id)
        if not layer:
            return False
        
        expires_at_str = layer.get(ATTR_EXPIRES_AT)
        if not expires_at_str:
            return False
        
        expires_at = dt_util.parse_datetime(expires_at_str)
        if not expires_at:
            return False
        
        return dt_util.now() >= expires_at