"""Zone State Machine - Manages high-level zone states and transitions."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_ZONE_STATE_CHANGED,
    EVENT_ZONE_STATE_TRANSITION_FAILED,
)

_LOGGER = logging.getLogger(__name__)


class ZoneState(Enum):
    """Zone state enumeration."""
    OFF = "off"
    AUTO = "auto"
    MANUAL_OVERRIDE = "manual_override"
    LOCKED = "locked"
    ERROR = "error"


class ZoneStateMachine:
    """Manages zone state transitions."""
    
    # Allowed state transitions
    TRANSITIONS = {
        ZoneState.OFF: [ZoneState.AUTO, ZoneState.MANUAL_OVERRIDE, ZoneState.ERROR],
        ZoneState.AUTO: [ZoneState.OFF, ZoneState.MANUAL_OVERRIDE, ZoneState.LOCKED, ZoneState.ERROR],
        ZoneState.MANUAL_OVERRIDE: [ZoneState.OFF, ZoneState.AUTO, ZoneState.LOCKED, ZoneState.ERROR],
        ZoneState.LOCKED: [ZoneState.AUTO, ZoneState.OFF, ZoneState.ERROR],
        ZoneState.ERROR: [ZoneState.OFF],
    }
    
    def __init__(self, hass: HomeAssistant, zone_id: str) -> None:
        """Initialize state machine.
        
        Args:
            hass: Home Assistant instance
            zone_id: Zone identifier
        """
        self.hass = hass
        self.zone_id = zone_id
        self.state = ZoneState.OFF
        self._listeners: List[Callable[[ZoneState, ZoneState], None]] = []
        self._transition_history: List[tuple] = []
        self._last_transition_time = dt_util.now()
        _LOGGER.info("ZoneStateMachine initialized for zone %s in state %s", zone_id, self.state)
    
    def can_transition(self, to_state: ZoneState) -> bool:
        """Check if transition is allowed.
        
        Args:
            to_state: Target state
            
        Returns:
            True if transition is allowed
        """
        allowed = self.TRANSITIONS.get(self.state, [])
        return to_state in allowed
    
    def transition_to(self, new_state: ZoneState, reason: Optional[str] = None) -> bool:
        """Transition to a new state if allowed.
        
        Args:
            new_state: Target state
            reason: Optional reason for transition
            
        Returns:
            True if transition succeeded
        """
        if not self.can_transition(new_state):
            _LOGGER.warning(
                "Invalid state transition for zone %s: %s -> %s (reason: %s)",
                self.zone_id, self.state, new_state, reason or "none"
            )
            
            # Fire failed transition event
            self.hass.bus.async_fire(
                EVENT_ZONE_STATE_TRANSITION_FAILED,
                {
                    "zone_id": self.zone_id,
                    "from_state": self.state.value,
                    "to_state": new_state.value,
                    "reason": reason or "none",
                    "timestamp": dt_util.now().isoformat(),
                }
            )
            return False
        
        # Perform transition
        old_state = self.state
        self.state = new_state
        now = dt_util.now()
        
        # Record in history
        self._transition_history.append((old_state, new_state, now, reason))
        if len(self._transition_history) > 100:  # Keep last 100 transitions
            self._transition_history.pop(0)
        
        self._last_transition_time = now
        
        # Log transition
        _LOGGER.info(
            "Zone %s state transition: %s -> %s (reason: %s)",
            self.zone_id, old_state.value, new_state.value, reason or "none"
        )
        
        # Fire state change event
        self.hass.bus.async_fire(
            EVENT_ZONE_STATE_CHANGED,
            {
                "zone_id": self.zone_id,
                "old_state": old_state.value,
                "new_state": new_state.value,
                "reason": reason or "none",
                "timestamp": now.isoformat(),
            }
        )
        
        # Notify listeners
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception as err:
                _LOGGER.error(
                    "Error notifying state change listener: %s",
                    err, exc_info=True
                )
        
        return True
    
    def add_listener(self, listener: Callable[[ZoneState, ZoneState], None]) -> None:
        """Add a state change listener.
        
        Args:
            listener: Callback(old_state, new_state)
        """
        self._listeners.append(listener)
        _LOGGER.debug("Added state listener for zone %s, total: %d", self.zone_id, len(self._listeners))
    
    def remove_listener(self, listener: Callable[[ZoneState, ZoneState], None]) -> None:
        """Remove a state change listener.
        
        Args:
            listener: Callback to remove
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
            _LOGGER.debug("Removed state listener for zone %s, remaining: %d", self.zone_id, len(self._listeners))
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state information.
        
        Returns:
            Dictionary with state details
        """
        return {
            "current_state": self.state.value,
            "last_transition": self._last_transition_time.isoformat(),
            "allowed_transitions": [s.value for s in self.TRANSITIONS.get(self.state, [])],
            "history_count": len(self._transition_history),
        }
    
    def get_transition_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transition history.
        
        Args:
            limit: Maximum number of entries
            
        Returns:
            List of transition records
        """
        history = []
        for old, new, time, reason in self._transition_history[-limit:]:
            history.append({
                "from": old.value,
                "to": new.value,
                "time": time.isoformat(),
                "reason": reason or "none",
            })
        return history
    
    def reset(self) -> None:
        """Reset state machine to OFF state."""
        _LOGGER.info("Resetting zone %s state machine", self.zone_id)
        self.state = ZoneState.OFF
        self._transition_history.clear()
        self._last_transition_time = dt_util.now()