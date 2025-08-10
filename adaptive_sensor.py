"""Adaptive lighting factor sensor for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AdaptiveLightFactorSensor(SensorEntity):
    """Sensor that calculates adaptive lighting factor based on sun elevation."""
    
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None
    _attr_icon = "mdi:theme-light-dark"
    
    def __init__(self, zone_id: str, zone_name: str, config_entry: ConfigEntry) -> None:
        """Initialize the adaptive factor sensor."""
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._config_entry = config_entry
        self._factor = 0.5  # Default to middle
        
        # Get elevation ranges from config (with defaults)
        self._min_elevation = config_entry.options.get("adaptive_elevation_min", -6)
        self._max_elevation = config_entry.options.get("adaptive_elevation_max", 15)
        
        # Optional alternative sensor for brightness
        self._brightness_entity = config_entry.options.get("adaptive_brightness_entity")
        self._brightness_min = config_entry.options.get("adaptive_brightness_entity_min", 0)
        self._brightness_max = config_entry.options.get("adaptive_brightness_entity_max", 255)
    
    @property
    def unique_id(self) -> str:
        """Return unique ID for the sensor."""
        return f"{self._zone_id}_adaptive_factor"
    
    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return f"{self._zone_name} Adaptive Factor"
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for grouping under zone device."""
        return {
            "identifiers": {(DOMAIN, self._zone_id)},
            "name": self._zone_name,
            "manufacturer": "Lighting Manager",
            "model": "Zone Controller",
            "sw_version": "2.0.0",
        }
    
    @property
    def native_value(self) -> float:
        """Return the adaptive factor (0.0 to 1.0)."""
        return round(self._factor, 3)
    
    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return additional sensor attributes."""
        return {
            "zone_id": self._zone_id,
            "min_elevation": self._min_elevation,
            "max_elevation": self._max_elevation,
            "brightness_entity": self._brightness_entity,
            "source": "sun" if not self._brightness_entity else self._brightness_entity,
        }
    
    async def async_added_to_hass(self) -> None:
        """Set up sensor when added to hass."""
        # Calculate initial value
        self._calculate_factor()
        
        if self._brightness_entity:
            # Track alternative brightness sensor
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._brightness_entity,
                    self._on_brightness_entity_change
                )
            )
        else:
            # Track sun elevation
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    "sun.sun",
                    self._on_sun_change
                )
            )
    
    @callback
    def _on_sun_change(self, event) -> None:
        """Handle sun state changes."""
        self._calculate_factor()
        self.async_write_ha_state()
    
    @callback
    def _on_brightness_entity_change(self, event) -> None:
        """Handle alternative brightness entity changes."""
        self._calculate_factor()
        self.async_write_ha_state()
    
    def _calculate_factor(self) -> None:
        """Calculate adaptive factor from sun or brightness entity."""
        if self._brightness_entity:
            # Use alternative brightness entity
            state = self.hass.states.get(self._brightness_entity)
            if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return
            
            try:
                value = float(state.state)
                # Normalize to 0-1 (inverted - lower value = higher factor)
                normalized = (value - self._brightness_min) / (self._brightness_max - self._brightness_min)
                self._factor = 1.0 - max(0.0, min(1.0, normalized))
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Could not parse brightness entity %s value: %s",
                    self._brightness_entity,
                    state.state
                )
        else:
            # Use sun elevation
            sun_state = self.hass.states.get("sun.sun")
            if not sun_state:
                return
            
            elevation = sun_state.attributes.get("elevation")
            if elevation is None:
                return
            
            # Clamp elevation to configured range
            clamped = max(self._min_elevation, min(self._max_elevation, elevation))
            
            # Calculate factor (lower elevation = higher factor = warmer/dimmer)
            # At min_elevation (e.g., -6°): factor = 1.0 (warmest/dimmest)
            # At max_elevation (e.g., 15°): factor = 0.0 (coolest/brightest)
            range_size = self._max_elevation - self._min_elevation
            if range_size > 0:
                self._factor = 1.0 - ((clamped - self._min_elevation) / range_size)
            else:
                self._factor = 0.5