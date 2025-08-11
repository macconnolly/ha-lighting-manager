"""Zone coordinator for Lighting Manager - Complete rewrite with proper architecture.

This coordinator properly separates concerns and detects manual control.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT_DELTA,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_KELVIN_DELTA,
    ATTR_EXPIRES_AT,
    ATTR_IS_ON,
    ATTR_LAYER_NAME,
    ATTR_LAYER_TYPE,
    ATTR_PRIORITY,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    CONF_ADAPTIVE_ENABLED,
    DATA_COORDINATOR,
    DOMAIN,
    LAYER_TYPE_ABSOLUTE,
    LAYER_TYPE_MODIFIER,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class ZoneState(Enum):
    """Zone state machine states."""
    OFF = "off"
    AUTO = "auto"
    MANUAL_OVERRIDE = "manual_override"
    LOCKED = "locked"
    ERROR = "error"


class LayerManager:
    """Manages layer CRUD operations and persistence."""
    
    def __init__(self, hass: HomeAssistant, zone_id: str):
        """Initialize layer manager."""
        self.hass = hass
        self.zone_id = zone_id
        self.layers: Dict[str, Dict[str, Any]] = {}
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{zone_id}",
        )
        self._listeners: List[callback] = []
    
    async def load(self) -> None:
        """Load layers from storage."""
        try:
            stored = await self._store.async_load()
            if stored and isinstance(stored, dict):
                # Only load configuration layers, not temporary ones
                self.layers = {
                    lid: layer for lid, layer in stored.get("layers", {}).items()
                    if layer.get(ATTR_SOURCE) != "manual_override"
                }
                _LOGGER.info("Loaded %d layers for zone %s", len(self.layers), self.zone_id)
        except Exception as err:
            _LOGGER.error("Failed to load layers for zone %s: %s", self.zone_id, err)
            self.layers = {}
    
    async def save(self) -> None:
        """Save configuration layers only."""
        config_layers = {
            lid: layer for lid, layer in self.layers.items()
            if layer.get(ATTR_SOURCE) != "manual_override"
        }
        await self._store.async_save({
            "version": STORAGE_VERSION,
            "layers": config_layers,
            "zone_id": self.zone_id,
            "saved_at": dt_util.now().isoformat(),
        })
    
    def create_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> None:
        """Create a new layer."""
        self.layers[layer_id] = layer_data
        self._notify_listeners()
    
    def update_layer(self, layer_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing layer."""
        if layer_id not in self.layers:
            return False
        self.layers[layer_id].update(updates)
        self._notify_listeners()
        return True
    
    def delete_layer(self, layer_id: str) -> bool:
        """Delete a layer."""
        if layer_id not in self.layers:
            return False
        del self.layers[layer_id]
        self._notify_listeners()
        return True
    
    def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Get a layer by ID."""
        return self.layers.get(layer_id)
    
    def get_active_layers(self) -> List[Dict[str, Any]]:
        """Get all active layers."""
        return [
            {**layer, "layer_id": lid}
            for lid, layer in self.layers.items()
            if layer.get(ATTR_IS_ON, False)
        ]
    
    def add_listener(self, listener: callback) -> None:
        """Add a change listener."""
        self._listeners.append(listener)
    
    def _notify_listeners(self) -> None:
        """Notify all listeners of changes."""
        for listener in self._listeners:
            listener()


class StateCalculator:
    """Pure calculation of desired state from layers."""
    
    def calculate_state(
        self,
        layers: List[Dict[str, Any]],
        adaptive_values: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calculate the desired state from active layers."""
        active_layers = [l for l in layers if l.get(ATTR_IS_ON, False)]
        
        if not active_layers:
            return {
                "power": "off",
                "winning_layer": None,
                "calculation_path": ["No active layers"],
            }
        
        # Sort by priority (higher wins)
        active_layers.sort(key=lambda x: x.get(ATTR_PRIORITY, 50), reverse=True)
        
        # Get base state from highest priority absolute layer
        absolute_layers = [
            l for l in active_layers 
            if l.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE) == LAYER_TYPE_ABSOLUTE
        ]
        
        if not absolute_layers:
            # No absolute layer, use adaptive values if available
            if adaptive_values:
                base_state = {
                    "power": "on",
                    "brightness": adaptive_values.get("brightness", 128),
                    "color_temp": adaptive_values.get("color_temp", 370),
                }
                winning_layer = "adaptive_default"
            else:
                return {
                    "power": "off",
                    "winning_layer": None,
                    "calculation_path": ["No absolute layers and no adaptive values"],
                }
        else:
            winner = absolute_layers[0]
            base_state = {
                "power": "on",
                "brightness": winner.get(ATTR_BRIGHTNESS, 255),
                "color_temp": winner.get(ATTR_COLOR_TEMP, 370),
                "transition": winner.get(ATTR_TRANSITION, 2.0),
            }
            winning_layer = winner.get("layer_id", "unknown")
        
        # Apply modifiers
        modifiers = [
            l for l in active_layers
            if l.get(ATTR_LAYER_TYPE) == LAYER_TYPE_MODIFIER
        ]
        
        for modifier in modifiers:
            # Apply brightness delta
            if ATTR_BRIGHTNESS_PCT_DELTA in modifier:
                delta = modifier[ATTR_BRIGHTNESS_PCT_DELTA]
                current_pct = (base_state["brightness"] / 255) * 100
                new_pct = max(0, min(100, current_pct + delta))
                base_state["brightness"] = int((new_pct / 100) * 255)
            
            # Apply color temp delta
            if ATTR_COLOR_TEMP_KELVIN_DELTA in modifier:
                delta_k = modifier[ATTR_COLOR_TEMP_KELVIN_DELTA]
                current_k = 1000000 / base_state["color_temp"]
                new_k = max(2000, min(6500, current_k + delta_k))
                base_state["color_temp"] = int(1000000 / new_k)
        
        return {
            **base_state,
            "winning_layer": winning_layer,
            "calculation_path": [f"Winner: {winning_layer}", f"Modifiers: {len(modifiers)}"],
            "applied_modifiers": [m.get("layer_id") for m in modifiers],
        }


class LightController:
    """Controls physical lights and tracks commanded state."""
    
    def __init__(self, hass: HomeAssistant, zone_id: str, light_entities: List[str]):
        """Initialize light controller."""
        self.hass = hass
        self.zone_id = zone_id
        self.light_entities = light_entities
        self.last_commanded_state: Dict[str, Any] = {}
        self.last_command_time: Optional[datetime] = None
    
    async def apply_state(self, desired_state: Dict[str, Any]) -> bool:
        """Apply desired state to lights."""
        if not self.light_entities:
            return False
        
        try:
            if desired_state.get("power") == "off":
                await self.hass.services.async_call(
                    "light",
                    "turn_off",
                    {
                        ATTR_ENTITY_ID: self.light_entities,
                        "transition": desired_state.get("transition", 2.0),
                    },
                    blocking=False,
                )
                self.last_commanded_state = {"power": "off"}
            else:
                service_data = {
                    ATTR_ENTITY_ID: self.light_entities,
                    "brightness": desired_state.get("brightness", 255),
                    "transition": desired_state.get("transition", 2.0),
                }
                
                # Only add color_temp if lights support it
                if "color_temp" in desired_state:
                    service_data["color_temp"] = desired_state["color_temp"]
                
                await self.hass.services.async_call(
                    "light",
                    "turn_on",
                    service_data,
                    blocking=False,
                )
                self.last_commanded_state = desired_state.copy()
            
            self.last_command_time = dt_util.now()
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to apply state to lights in zone %s: %s", self.zone_id, err)
            return False
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current actual state of lights."""
        if not self.light_entities:
            return {"power": "off"}
        
        states = []
        for entity_id in self.light_entities:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                states.append(state)
        
        if not states:
            return {"power": "unknown"}
        
        # If any light is on, consider zone on
        on_lights = [s for s in states if s.state == STATE_ON]
        if not on_lights:
            return {"power": "off"}
        
        # Average the attributes of on lights
        total_brightness = 0
        total_color_temp = 0
        color_temp_count = 0
        
        for state in on_lights:
            attrs = state.attributes
            total_brightness += attrs.get("brightness", 255)
            if "color_temp" in attrs:
                total_color_temp += attrs["color_temp"]
                color_temp_count += 1
        
        result = {
            "power": "on",
            "brightness": int(total_brightness / len(on_lights)),
        }
        
        if color_temp_count > 0:
            result["color_temp"] = int(total_color_temp / color_temp_count)
        
        return result
    
    def was_recently_commanded(self, threshold_seconds: int = 5) -> bool:
        """Check if lights were recently commanded by us."""
        if not self.last_command_time:
            return False
        
        elapsed = (dt_util.now() - self.last_command_time).total_seconds()
        return elapsed < threshold_seconds


class ChangeDetector:
    """Detects manual control and creates override layers."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        zone_id: str,
        layer_manager: LayerManager,
        light_controller: LightController
    ):
        """Initialize change detector."""
        self.hass = hass
        self.zone_id = zone_id
        self.layer_manager = layer_manager
        self.light_controller = light_controller
        self.manual_override_active = False
        self.last_override_id: Optional[str] = None
    
    def check_for_manual_change(self) -> bool:
        """Check if lights were manually changed."""
        # Don't check if we recently sent a command
        if self.light_controller.was_recently_commanded():
            return False
        
        current_state = self.light_controller.get_current_state()
        commanded_state = self.light_controller.last_commanded_state
        
        # No commanded state yet, not a manual change
        if not commanded_state:
            return False
        
        # Compare states
        if current_state.get("power") != commanded_state.get("power"):
            _LOGGER.info("Manual power change detected in zone %s", self.zone_id)
            return True
        
        if current_state.get("power") == "on" and commanded_state.get("power") == "on":
            # Check brightness difference (allow 5% tolerance)
            current_brightness = current_state.get("brightness", 255)
            commanded_brightness = commanded_state.get("brightness", 255)
            if abs(current_brightness - commanded_brightness) > 13:  # ~5% of 255
                _LOGGER.info(
                    "Manual brightness change detected in zone %s: %d -> %d",
                    self.zone_id, commanded_brightness, current_brightness
                )
                return True
            
            # Check color temp difference (allow 10 mired tolerance)
            if "color_temp" in current_state and "color_temp" in commanded_state:
                current_ct = current_state["color_temp"]
                commanded_ct = commanded_state["color_temp"]
                if abs(current_ct - commanded_ct) > 10:
                    _LOGGER.info(
                        "Manual color change detected in zone %s: %d -> %d",
                        self.zone_id, commanded_ct, current_ct
                    )
                    return True
        
        return False
    
    def create_manual_override(self) -> str:
        """Create a manual override layer based on current light state."""
        # Remove old override if exists
        if self.last_override_id and self.last_override_id in self.layer_manager.layers:
            self.layer_manager.delete_layer(self.last_override_id)
        
        current_state = self.light_controller.get_current_state()
        now = dt_util.now()
        override_id = f"manual_override_{now.timestamp():.0f}"
        
        # Create high-priority override layer
        override_layer = {
            ATTR_LAYER_NAME: "Manual Override",
            ATTR_IS_ON: current_state.get("power") == "on",
            ATTR_PRIORITY: 95,  # High priority
            ATTR_SOURCE: "manual_override",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_TRANSITION: 0.5,  # Quick transition for manual
            ATTR_EXPIRES_AT: now + timedelta(hours=2),  # 2 hour timeout
            "created_at": now,
        }
        
        if current_state.get("power") == "on":
            override_layer[ATTR_BRIGHTNESS] = current_state.get("brightness", 255)
            if "color_temp" in current_state:
                override_layer[ATTR_COLOR_TEMP] = current_state["color_temp"]
        
        self.layer_manager.create_layer(override_id, override_layer)
        self.last_override_id = override_id
        self.manual_override_active = True
        
        _LOGGER.info(
            "Created manual override %s for zone %s with state: %s",
            override_id, self.zone_id, current_state
        )
        
        return override_id
    
    def clear_manual_override(self) -> None:
        """Clear the manual override."""
        if self.last_override_id and self.last_override_id in self.layer_manager.layers:
            self.layer_manager.delete_layer(self.last_override_id)
            self.last_override_id = None
            self.manual_override_active = False
            _LOGGER.info("Cleared manual override for zone %s", self.zone_id)


class AdaptiveProvider:
    """Provides adaptive lighting values based on sun position."""
    
    def __init__(self, hass: HomeAssistant, options: Dict[str, Any]):
        """Initialize adaptive provider."""
        self.hass = hass
        self.options = options
        self.enabled = options.get(CONF_ADAPTIVE_ENABLED, False)
    
    def get_adaptive_values(self) -> Dict[str, Any]:
        """Get current adaptive brightness and color temperature."""
        if not self.enabled:
            return {}
        
        # Get sun elevation
        sun_state = self.hass.states.get("sun.sun")
        if not sun_state:
            return {}
        
        sun_elevation = sun_state.attributes.get("elevation", -6)
        
        # Get configuration
        min_brightness_pct = self.options.get("min_brightness_pct", 15)
        max_brightness_pct = self.options.get("max_brightness_pct", 100)
        min_kelvin = self.options.get("min_kelvin", 2200)
        max_kelvin = self.options.get("max_kelvin", 4000)
        elevation_min = self.options.get("adaptive_elevation_min", -6)
        elevation_max = self.options.get("adaptive_elevation_max", 10)
        
        # Calculate based on sun elevation
        if sun_elevation <= elevation_min:
            brightness_pct = min_brightness_pct
            kelvin = min_kelvin
        elif sun_elevation >= elevation_max:
            brightness_pct = max_brightness_pct
            kelvin = max_kelvin
        else:
            # Linear interpolation
            ratio = (sun_elevation - elevation_min) / (elevation_max - elevation_min)
            brightness_pct = min_brightness_pct + (max_brightness_pct - min_brightness_pct) * ratio
            kelvin = min_kelvin + (max_kelvin - min_kelvin) * ratio
        
        return {
            "brightness": int(brightness_pct * 255 / 100),
            "color_temp": int(1000000 / kelvin),
            "brightness_pct": brightness_pct,
            "kelvin": int(kelvin),
            "sun_elevation": sun_elevation,
        }


class ZoneStateMachine:
    """Manages zone state transitions."""
    
    def __init__(self):
        """Initialize state machine."""
        self.state = ZoneState.OFF
        self._listeners: List[callback] = []
    
    def can_transition(self, to_state: ZoneState) -> bool:
        """Check if transition is allowed."""
        # Define allowed transitions
        allowed = {
            ZoneState.OFF: [ZoneState.AUTO, ZoneState.MANUAL_OVERRIDE],
            ZoneState.AUTO: [ZoneState.OFF, ZoneState.MANUAL_OVERRIDE, ZoneState.LOCKED],
            ZoneState.MANUAL_OVERRIDE: [ZoneState.OFF, ZoneState.AUTO],
            ZoneState.LOCKED: [ZoneState.AUTO],
            ZoneState.ERROR: [ZoneState.OFF],
        }
        
        return to_state in allowed.get(self.state, [])
    
    def transition_to(self, new_state: ZoneState) -> bool:
        """Transition to a new state if allowed."""
        if not self.can_transition(new_state):
            _LOGGER.warning("Invalid state transition: %s -> %s", self.state, new_state)
            return False
        
        old_state = self.state
        self.state = new_state
        _LOGGER.info("Zone state transition: %s -> %s", old_state, new_state)
        
        for listener in self._listeners:
            listener(old_state, new_state)
        
        return True
    
    def add_listener(self, listener: callback) -> None:
        """Add a state change listener."""
        self._listeners.append(listener)


class ZoneCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator for a lighting zone - orchestrates all components."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the zone coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data['zone_id']}",
            config_entry=entry,
        )
        
        self.config_entry = entry
        self.zone_id = entry.data["zone_id"]
        self.zone_name = entry.data["zone_name"]
        self.light_entities = entry.options.get("light_entities", [])
        
        # Initialize components
        self.layer_manager = LayerManager(hass, self.zone_id)
        self.calculator = StateCalculator()
        self.light_controller = LightController(hass, self.zone_id, self.light_entities)
        self.adaptive_provider = AdaptiveProvider(hass, entry.options)
        self.state_machine = ZoneStateMachine()
        
        # Initialize change detector after other components
        self.change_detector = ChangeDetector(
            hass, self.zone_id, self.layer_manager, self.light_controller
        )
        
        # Track listeners
        self._cleanup_listeners: List[callback] = []
        self._manual_check_listener = None
        self._sun_listener = None
        
        # Debounce timer
        self._debounce_timer = None
        
        # Public properties for sensors/switches
        self.layers = self.layer_manager.layers  # Direct reference
        self.new_layer_callback = None
        
        # Initial data structure
        self.data = {
            "layers": {},
            "zone_state": ZoneState.OFF.value,
            "manual_override_active": False,
            "adaptive_values": {},
            "winning_layer": None,
            "final_state": {"power": "off"},
        }
    
    async def async_load(self) -> None:
        """Load stored configuration and set up monitoring."""
        # Load stored layers
        await self.layer_manager.load()
        
        # Create default manual layer if not exists
        if "manual" not in self.layer_manager.layers:
            self.layer_manager.create_layer("manual", {
                ATTR_LAYER_NAME: "Manual Control",
                ATTR_IS_ON: False,
                ATTR_PRIORITY: 90,
                ATTR_BRIGHTNESS: 255,
                ATTR_COLOR_TEMP: 370,
                ATTR_TRANSITION: 2.0,
                ATTR_SOURCE: "configuration",
                ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            })
        
        # Set up change listeners
        self.layer_manager.add_listener(self._on_layers_changed)
        self.state_machine.add_listener(self._on_state_changed)
        
        # Start manual control detection (check every 5 seconds)
        self._manual_check_listener = async_track_time_interval(
            self.hass,
            self._check_manual_control,
            timedelta(seconds=5)
        )
        
        # Track sun changes if adaptive enabled
        if self.adaptive_provider.enabled:
            self._sun_listener = async_track_state_change_event(
                self.hass, "sun.sun", self._on_sun_changed
            )
        
        # Set initial state
        self.state_machine.transition_to(ZoneState.AUTO)
        
        # Don't apply any state on startup - just observe current state
        current_state = self.light_controller.get_current_state()
        self.light_controller.last_commanded_state = current_state
        
        _LOGGER.info(
            "Coordinator loaded for zone %s with %d layers, current light state: %s",
            self.zone_id, len(self.layer_manager.layers), current_state
        )
    
    @callback
    def _on_layers_changed(self) -> None:
        """Handle layer changes."""
        self._schedule_update()
    
    @callback
    def _on_state_changed(self, old_state: ZoneState, new_state: ZoneState) -> None:
        """Handle zone state changes."""
        _LOGGER.info("Zone %s state changed: %s -> %s", self.zone_id, old_state, new_state)
        self._schedule_update()
    
    @callback
    def _on_sun_changed(self, event) -> None:
        """Handle sun position changes."""
        self._schedule_update()
    
    @callback
    async def _check_manual_control(self, now) -> None:
        """Periodically check for manual control."""
        if self.state_machine.state == ZoneState.LOCKED:
            return
        
        if self.change_detector.check_for_manual_change():
            # Manual control detected
            override_id = self.change_detector.create_manual_override()
            self.state_machine.transition_to(ZoneState.MANUAL_OVERRIDE)
            
            # Save state but don't save the override layer
            await self.layer_manager.save()
            
            # Trigger update
            self._schedule_update()
    
    def _schedule_update(self) -> None:
        """Schedule an update with debouncing."""
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        self._debounce_timer = self.hass.loop.call_later(
            0.1,  # 100ms debounce
            lambda: self.hass.async_create_task(self.async_refresh())
        )
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Calculate and apply the desired state."""
        # Get adaptive values
        adaptive_values = self.adaptive_provider.get_adaptive_values()
        
        # Get active layers
        active_layers = self.layer_manager.get_active_layers()
        
        # Calculate desired state
        calc_result = self.calculator.calculate_state(active_layers, adaptive_values)
        
        # Apply state based on zone state
        if self.state_machine.state in [ZoneState.AUTO, ZoneState.MANUAL_OVERRIDE]:
            await self.light_controller.apply_state(calc_result)
        
        # Update data
        self.data = {
            "layers": self.layer_manager.layers.copy(),
            "zone_state": self.state_machine.state.value,
            "manual_override_active": self.change_detector.manual_override_active,
            "adaptive_values": adaptive_values,
            "winning_layer": calc_result.get("winning_layer"),
            "final_state": calc_result,
            "active_layers": [l["layer_id"] for l in active_layers],
        }
        
        return self.data
    
    async def create_layer(self, layer_name: str, **attributes) -> str:
        """Create a new layer."""
        layer_id = layer_name.lower().replace(" ", "_")
        
        # Ensure unique ID
        if layer_id in self.layer_manager.layers:
            suffix = 1
            while f"{layer_id}_{suffix}" in self.layer_manager.layers:
                suffix += 1
            layer_id = f"{layer_id}_{suffix}"
        
        layer_data = {
            ATTR_LAYER_NAME: layer_name,
            ATTR_IS_ON: False,
            **attributes,
        }
        
        self.layer_manager.create_layer(layer_id, layer_data)
        await self.layer_manager.save()
        
        # Notify switch platform
        if self.new_layer_callback:
            await self.new_layer_callback(layer_id, layer_name)
        
        return layer_id
    
    async def update_layer(self, layer_id: str, **updates) -> bool:
        """Update a layer."""
        success = self.layer_manager.update_layer(layer_id, updates)
        if success:
            await self.layer_manager.save()
        return success
    
    async def delete_layer(self, layer_id: str) -> bool:
        """Delete a layer."""
        success = self.layer_manager.delete_layer(layer_id)
        if success:
            await self.layer_manager.save()
        return success
    
    def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Get a layer by ID."""
        return self.layer_manager.get_layer(layer_id)
    
    def schedule_recalculation(self) -> None:
        """Schedule a recalculation (for compatibility)."""
        self._schedule_update()
    
    async def save_layers(self) -> None:
        """Save layers (for compatibility)."""
        await self.layer_manager.save()
    
    def schedule_save(self) -> None:
        """Schedule a save (for compatibility)."""
        self.hass.async_create_task(self.layer_manager.save())
    
    async def async_shutdown(self) -> None:
        """Clean up when coordinator is being removed."""
        # Cancel listeners
        if self._manual_check_listener:
            self._manual_check_listener()
        if self._sun_listener:
            self._sun_listener()
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        # Final save
        await self.layer_manager.save()