"""Light Controller - Hardware abstraction with circuit breaker pattern."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from homeassistant.const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_ENTITY_ID,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Circuit broken, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class LightController:
    """Controls physical lights with circuit breaker pattern."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        zone_id: str,
        light_entities: List[str]
    ) -> None:
        """Initialize light controller.
        
        Args:
            hass: Home Assistant instance
            zone_id: Zone identifier
            light_entities: List of light entity IDs
        """
        self.hass = hass
        self.zone_id = zone_id
        self.light_entities = light_entities
        
        # State tracking
        self.last_commanded_state: Dict[str, Any] = {}
        self.last_command_time: Optional[datetime] = None
        
        # Circuit breaker
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 3
        self.success_threshold = 2
        self.timeout_seconds = 60
        self.last_failure_time: Optional[datetime] = None
        self.half_open_successes = 0
        
        _LOGGER.info(
            "LightController initialized for zone %s with %d lights",
            zone_id, len(light_entities)
        )
    
    async def apply_state(self, desired_state: Dict[str, Any]) -> bool:
        """Apply desired state to lights.
        
        Args:
            desired_state: State to apply (power, brightness, color_temp, etc.)
            
        Returns:
            True if successful, False if failed or circuit open
        """
        # Check circuit breaker
        if not self._can_execute():
            _LOGGER.warning(
                "Circuit breaker OPEN for zone %s, rejecting command",
                self.zone_id
            )
            return False
        
        if not self.light_entities:
            _LOGGER.warning("No light entities configured for zone %s", self.zone_id)
            return False
        
        try:
            # Apply state based on power
            if desired_state.get("power") == "off":
                # Turn lights off
                await self.hass.services.async_call(
                    "light",
                    SERVICE_TURN_OFF,
                    {
                        ATTR_ENTITY_ID: self.light_entities,
                        ATTR_TRANSITION: desired_state.get("transition", 2.0),
                    },
                    blocking=False,
                )
                self.last_commanded_state = {"power": "off"}
                _LOGGER.debug("Commanded lights OFF for zone %s", self.zone_id)
                
            else:
                # Turn lights on with attributes
                service_data = {
                    ATTR_ENTITY_ID: self.light_entities,
                    ATTR_BRIGHTNESS: desired_state.get("brightness", 255),
                    ATTR_TRANSITION: desired_state.get("transition", 2.0),
                }
                
                # Add optional attributes
                if "color_temp" in desired_state:
                    service_data[ATTR_COLOR_TEMP] = desired_state["color_temp"]
                if "rgb_color" in desired_state:
                    service_data[ATTR_RGB_COLOR] = desired_state["rgb_color"]
                
                await self.hass.services.async_call(
                    "light",
                    SERVICE_TURN_ON,
                    service_data,
                    blocking=False,
                )
                
                self.last_commanded_state = {
                    "power": "on",
                    **{k: v for k, v in desired_state.items() if k != "power"}
                }
                
                _LOGGER.debug(
                    "Commanded lights ON for zone %s: brightness=%s, color_temp=%s",
                    self.zone_id,
                    desired_state.get("brightness"),
                    desired_state.get("color_temp")
                )
            
            # Update tracking
            self.last_command_time = dt_util.now()
            
            # Record success for circuit breaker
            self._record_success()
            return True
            
        except Exception as err:
            _LOGGER.error(
                "Failed to apply state to lights in zone %s: %s",
                self.zone_id, err, exc_info=True
            )
            
            # Record failure for circuit breaker
            self._record_failure()
            return False
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current actual state of lights.
        
        Returns:
            Dictionary with power, brightness, color_temp
        """
        if not self.light_entities:
            return {"power": "off"}
        
        # Collect states
        states = []
        for entity_id in self.light_entities:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                states.append(state)
        
        if not states:
            _LOGGER.debug("No available lights in zone %s", self.zone_id)
            return {"power": "unknown"}
        
        # Check if any light is on
        on_lights = [s for s in states if s.state == STATE_ON]
        if not on_lights:
            return {"power": "off"}
        
        # Calculate average attributes from on lights
        total_brightness = 0
        total_color_temp = 0
        color_temp_count = 0
        
        for state in on_lights:
            attrs = state.attributes
            total_brightness += attrs.get(ATTR_BRIGHTNESS, 255)
            
            if ATTR_COLOR_TEMP in attrs:
                total_color_temp += attrs[ATTR_COLOR_TEMP]
                color_temp_count += 1
        
        result = {
            "power": "on",
            "brightness": int(total_brightness / len(on_lights)),
        }
        
        if color_temp_count > 0:
            result["color_temp"] = int(total_color_temp / color_temp_count)
        
        return result
    
    def was_recently_commanded(self, threshold_seconds: int = 5) -> bool:
        """Check if lights were recently commanded.
        
        Args:
            threshold_seconds: Time threshold
            
        Returns:
            True if commanded within threshold
        """
        if not self.last_command_time:
            return False
        
        elapsed = (dt_util.now() - self.last_command_time).total_seconds()
        return elapsed < threshold_seconds
    
    def update_light_entities(self, new_entities: List[str]) -> None:
        """Update the list of controlled light entities.
        
        Args:
            new_entities: New list of entity IDs
        """
        old_count = len(self.light_entities)
        self.light_entities = new_entities
        _LOGGER.info(
            "Updated light entities for zone %s: %d -> %d",
            self.zone_id, old_count, len(new_entities)
        )
    
    # Circuit Breaker Methods
    
    def _can_execute(self) -> bool:
        """Check if circuit breaker allows execution.
        
        Returns:
            True if command can be executed
        """
        if self.circuit_state == CircuitState.CLOSED:
            return True
        
        if self.circuit_state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = (dt_util.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.timeout_seconds:
                    # Try half-open state
                    self.circuit_state = CircuitState.HALF_OPEN
                    self.half_open_successes = 0
                    _LOGGER.info(
                        "Circuit breaker for zone %s entering HALF_OPEN state",
                        self.zone_id
                    )
                    return True
            return False
        
        # Half-open state - allow execution
        return True
    
    def _record_success(self) -> None:
        """Record successful execution."""
        if self.circuit_state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.success_threshold:
                # Circuit recovered
                self.circuit_state = CircuitState.CLOSED
                self.failure_count = 0
                _LOGGER.info(
                    "Circuit breaker for zone %s CLOSED (recovered)",
                    self.zone_id
                )
        elif self.circuit_state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def _record_failure(self) -> None:
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = dt_util.now()
        
        if self.circuit_state == CircuitState.HALF_OPEN:
            # Immediately open circuit on failure in half-open
            self.circuit_state = CircuitState.OPEN
            _LOGGER.warning(
                "Circuit breaker for zone %s OPEN (half-open test failed)",
                self.zone_id
            )
        elif self.circuit_state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                # Open circuit
                self.circuit_state = CircuitState.OPEN
                _LOGGER.warning(
                    "Circuit breaker for zone %s OPEN (failure threshold reached: %d)",
                    self.zone_id, self.failure_count
                )
    
    def get_circuit_status(self) -> Dict[str, Any]:
        """Get circuit breaker status.
        
        Returns:
            Status dictionary
        """
        return {
            "state": self.circuit_state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }
    
    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker."""
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_successes = 0
        _LOGGER.info("Circuit breaker for zone %s manually reset", self.zone_id)