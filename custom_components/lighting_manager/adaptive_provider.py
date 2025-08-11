"""Adaptive Provider - Provides reference values based on sun position."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADAPTIVE_ENABLED,
    CONF_ADAPTIVE_BRIGHTNESS_MAX,
    CONF_ADAPTIVE_BRIGHTNESS_MIN,
    CONF_ADAPTIVE_COLOR_TEMP_MAX,
    CONF_ADAPTIVE_COLOR_TEMP_MIN,
    CONF_ADAPTIVE_ELEVATION_MAX,
    CONF_ADAPTIVE_ELEVATION_MIN,
)

_LOGGER = logging.getLogger(__name__)


class AdaptiveProvider:
    """Provides adaptive lighting values based on sun position.
    
    NOT A LAYER - provides reference values that layers can use.
    """
    
    def __init__(self, hass: HomeAssistant, options: Dict[str, Any]) -> None:
        """Initialize adaptive provider.
        
        Args:
            hass: Home Assistant instance
            options: Zone configuration options
        """
        self.hass = hass
        self.options = options
        self.enabled = options.get(CONF_ADAPTIVE_ENABLED, False)
        
        # Cache configuration values
        self.min_brightness_pct = options.get("min_brightness_pct", 15)
        self.max_brightness_pct = options.get("max_brightness_pct", 100)
        self.min_kelvin = options.get("min_kelvin", 2200)
        self.max_kelvin = options.get("max_kelvin", 4000)
        self.elevation_min = options.get(CONF_ADAPTIVE_ELEVATION_MIN, -6)
        self.elevation_max = options.get(CONF_ADAPTIVE_ELEVATION_MAX, 10)
        
        _LOGGER.info(
            "AdaptiveProvider initialized (enabled: %s, range: %d-%d%% brightness, %dK-%dK color)",
            self.enabled,
            self.min_brightness_pct,
            self.max_brightness_pct,
            self.min_kelvin,
            self.max_kelvin
        )
    
    def get_adaptive_values(self) -> Dict[str, Any]:
        """Get current adaptive brightness and color temperature.
        
        Returns:
            Dictionary containing:
                - brightness: 0-255 value
                - color_temp: mireds value
                - brightness_pct: percentage value
                - kelvin: color temperature in Kelvin
                - sun_elevation: current sun elevation
            Returns empty dict if disabled or sun unavailable.
        """
        if not self.enabled:
            _LOGGER.debug("Adaptive disabled, returning empty values")
            return {}
        
        # Get sun elevation
        sun_state = self.hass.states.get("sun.sun")
        if not sun_state or sun_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning("Sun entity unavailable, cannot calculate adaptive values")
            return {}
        
        sun_elevation = sun_state.attributes.get("elevation", -6)
        
        # Calculate values based on sun elevation
        if sun_elevation <= self.elevation_min:
            # Night time - use minimum values
            brightness_pct = self.min_brightness_pct
            kelvin = self.min_kelvin
            phase = "night"
        elif sun_elevation >= self.elevation_max:
            # Day time - use maximum values
            brightness_pct = self.max_brightness_pct
            kelvin = self.max_kelvin
            phase = "day"
        else:
            # Transition period - linear interpolation
            ratio = (sun_elevation - self.elevation_min) / (self.elevation_max - self.elevation_min)
            brightness_pct = self.min_brightness_pct + (self.max_brightness_pct - self.min_brightness_pct) * ratio
            kelvin = self.min_kelvin + (self.max_kelvin - self.min_kelvin) * ratio
            phase = "transition"
        
        # Convert to Home Assistant values
        brightness = int(brightness_pct * 255 / 100)
        color_temp = int(1000000 / kelvin)  # Convert Kelvin to mireds
        
        result = {
            "brightness": brightness,
            "color_temp": color_temp,
            "brightness_pct": round(brightness_pct, 1),
            "kelvin": int(kelvin),
            "sun_elevation": round(sun_elevation, 1),
            "phase": phase,
        }
        
        _LOGGER.debug(
            "Adaptive values: sun %.1f°, phase %s, brightness %d%% (%d/255), color %dK (%d mireds)",
            sun_elevation, phase, brightness_pct, brightness, kelvin, color_temp
        )
        
        return result
    
    def update_options(self, options: Dict[str, Any]) -> None:
        """Update configuration options.
        
        Args:
            options: New configuration options
        """
        self.options = options
        self.enabled = options.get(CONF_ADAPTIVE_ENABLED, False)
        
        # Update cached values
        self.min_brightness_pct = options.get("min_brightness_pct", 15)
        self.max_brightness_pct = options.get("max_brightness_pct", 100)
        self.min_kelvin = options.get("min_kelvin", 2200)
        self.max_kelvin = options.get("max_kelvin", 4000)
        self.elevation_min = options.get(CONF_ADAPTIVE_ELEVATION_MIN, -6)
        self.elevation_max = options.get(CONF_ADAPTIVE_ELEVATION_MAX, 10)
        
        _LOGGER.info("AdaptiveProvider options updated")