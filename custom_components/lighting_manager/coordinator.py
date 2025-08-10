"""Zone coordinator for Lighting Manager - Golden Path implementation.

CRITICAL: This coordinator is the single source of truth for all layer state.
The 'data' property returns a deep copy of layers to prevent external mutation.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_FACTOR,
    ATTR_BRIGHTNESS_PCT_DELTA,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_FACTOR,
    ATTR_COLOR_TEMP_KELVIN_DELTA,
    ATTR_CONDITIONS,
    ATTR_CREATED_AT,
    ATTR_EXPIRES_AT,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAST_MODIFIED,
    ATTR_LAYER_NAME,
    ATTR_LAYER_TYPE,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    CONF_ADAPTIVE_BRIGHTNESS_MAX,
    CONF_ADAPTIVE_BRIGHTNESS_MIN,
    CONF_ADAPTIVE_COLOR_TEMP_MAX,
    CONF_ADAPTIVE_COLOR_TEMP_MIN,
    CONF_ADAPTIVE_ENABLED,
    DEBOUNCE_SECONDS,
    DEFAULT_PRIORITY,
    DEFAULT_TRANSITION,
    DOMAIN,
    EVENT_CALCULATION_COMPLETE,
    EVENT_CONFLICT_DETECTED,
    LAYER_BASE_ADAPTIVE,
    LAYER_TYPE_ABSOLUTE,
    LAYER_TYPE_MODIFIER,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)
from .calculator import LightingCalculator
from .light_control import LightController
from .validation import (
    get_timezone_aware_now,
    validate_brightness,
    validate_color_temp,
    validate_layer_data,
    validate_layer_name,
    validate_priority,
    validate_rgb_color,
    validate_transition,
)

_LOGGER = logging.getLogger(__name__)


class ZoneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for a lighting zone - single source of truth for all layer state.
    
    GOLDEN PATH IMPLEMENTATION:
    - The 'data' property returns current state directly
    - All layer state lives in self.layers dictionary
    - Switches read from coordinator.data, never store state
    - All state modifications are async methods (no @callback)
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the zone coordinator."""
        # Don't set update_interval - we're event-driven
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
        
        _LOGGER.info("Coordinator init for zone %s with lights: %s", 
                    self.zone_name, self.light_entities)
        
        # CRITICAL: All layer state lives here - switches are just views
        self.layers: dict[str, dict[str, Any]] = {}
        
        # Store for persistence
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{self.zone_id}",
        )
        
        # Debounce timer
        self._debounce_timer: asyncio.TimerHandle | None = None
        self._save_timer: asyncio.TimerHandle | None = None
        
        # Calculator and light controller
        self._calculator = LightingCalculator()
        self._light_controller = LightController(hass, self.zone_id, self.light_entities)
        
        # Cached calculation result
        self._last_calculation: dict[str, Any] | None = None
        self._last_final_state: dict[str, Any] | None = None  # Track last applied state
        
        # Adaptive lighting tracking
        self._adaptive_enabled = False
        self._adaptive_factor = 0.5
        self._adaptive_listener = None
        
        # Callback for dynamically adding switch entities
        self.new_layer_callback = None
        
        # Layer expiration cleanup task
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval = 60  # Check every minute for expired layers
        
        # Zone configuration (e.g., k_control_enabled)
        self.zone_config = {
            "k_control_enabled": entry.options.get("k_control_enabled", True),
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
        }
        
        # Initialize data with proper structure to avoid race conditions
        self.data = {
            "layers": {},
            "active_layers": [],
            "active_layers_full": [],
            "zone_id": self.zone_id,
            "last_updated": None,
            "winning_layer": None,
            "final_state": {"power": "off"},
            "conflicts": [],
            "calculation_path": [],
            "calculating": False,
            "applied_modifiers": [],
        }
        
        _LOGGER.info("Coordinator initialized for zone %s", self.zone_id)

    def _get_current_data(self) -> dict[str, Any]:
        """Get current state data.
        
        This is the GOLDEN PATH implementation - returns the layers 
        dictionary directly, not through _async_update_data.
        """
        # Include last calculation result if available
        calc_data = self._last_calculation or {
            "winning_layer": None,
            "final_state": {"power": "off"},
            "conflicts": [],
            "calculation_path": [],
        }
        
        # Get list of active layer IDs for sensors
        active_layer_ids = [
            lid for lid, layer in self.layers.items()
            if layer.get(ATTR_IS_ON, False)
        ]
        
        # Build a read-only view of layers for consumers
        # This is much faster than deepcopy and still prevents mutation
        layers_view = {
            lid: {**layer}  # Shallow copy of each layer
            for lid, layer in self.layers.items()
        }
        
        return {
            "layers": layers_view,  # Read-only view, much faster than deepcopy
            "active_layers": active_layer_ids,  # Just IDs for sensors
            "active_layers_full": [  # Full data for existing consumers
                {**layer, "layer_id": lid}
                for lid, layer in self.layers.items()
                if layer.get(ATTR_IS_ON, False)
            ],
            "zone_id": self.zone_id,
            "last_updated": get_timezone_aware_now(),
            # Phase 2: Include calculation results
            "winning_layer": calc_data.get("winning_layer"),
            "final_state": calc_data.get("final_state", {}),
            "conflicts": calc_data.get("conflicts", []),
            "calculation_path": calc_data.get("calculation_path", []),
            "applied_modifiers": calc_data.get("applied_modifiers", []),
            # Phase 4: Additional fields for sensors
            "last_calculation": calc_data.get("timestamp"),
            "calculation_time_ms": calc_data.get("calculation_time_ms"),
            "cache_hit": calc_data.get("cache_hit", False),
            "trigger": calc_data.get("trigger"),
            "lights_unavailable": calc_data.get("lights_unavailable", []),
            "error": calc_data.get("error"),
            "calculating": False,  # Set to True during calculation
        }

    async def async_load(self) -> None:
        """Load stored layer data from disk."""
        try:
            stored = await self._store.async_load()
            if stored and self._validate_storage(stored):
                self.layers = stored.get("layers", {})
                _LOGGER.info("Loaded %d layers for zone %s", len(self.layers), self.zone_id)
            else:
                self.layers = {}
                _LOGGER.info("No valid stored layers for zone %s", self.zone_id)
        except Exception as err:
            _LOGGER.error("Failed to load layers for zone %s: %s", self.zone_id, err)
            self.layers = {}
        
        # Create default layer if no layers exist
        if not self.layers:
            await self.create_layer(
                layer_name="Manual",
                priority=50,
                brightness=255,
                color_temp=370,
                transition=2.0
            )
            _LOGGER.info("Created default 'Manual' layer for zone %s", self.zone_id)
        
        # Set up adaptive lighting if enabled
        await self._setup_adaptive()
        
        # Start background task for layer cleanup
        self._start_cleanup_task()

    def _validate_storage(self, data: Any) -> bool:
        """Validate loaded data structure."""
        if not isinstance(data, dict):
            return False
        if "layers" not in data:
            return False
        if not isinstance(data["layers"], dict):
            return False
        
        # Validate each layer
        for layer_id, layer_data in data["layers"].items():
            if not validate_layer_data(layer_data):
                _LOGGER.warning("Invalid layer data for %s, skipping", layer_id)
                return False
        
        return True

    async def save_layers(self) -> None:
        """Save current state with validation."""
        save_data = {
            "version": STORAGE_VERSION,
            "layers": self.layers,
            "zone_id": self.zone_id,
            "saved_at": get_timezone_aware_now().isoformat(),
        }
        await self._store.async_save(save_data)
        _LOGGER.debug("Saved %d layers for zone %s", len(self.layers), self.zone_id)

    def schedule_save(self) -> None:
        """Schedule a save with debouncing."""
        if self._save_timer:
            self._save_timer.cancel()
        
        self._save_timer = self.hass.loop.call_later(
            1.0,  # Save after 1 second of no changes
            lambda: self.hass.async_create_task(self.save_layers())
        )

    async def create_layer(
        self,
        layer_name: str,
        priority: int = DEFAULT_PRIORITY,
        **attributes: Any
    ) -> str:
        """Create a new layer - MUST be async, not @callback.
        
        This modifies state, so it cannot be a @callback method.
        """
        # Validate layer name
        layer_id = validate_layer_name(layer_name)
        
        if layer_id in self.layers:
            _LOGGER.warning("Layer %s already exists in zone %s", layer_id, self.zone_id)
            return layer_id
        
        # Create layer with validated attributes
        now = get_timezone_aware_now()
        self.layers[layer_id] = {
            ATTR_LAYER_NAME: layer_name,  # Original name for display
            ATTR_IS_ON: False,
            ATTR_PRIORITY: validate_priority(priority),
            ATTR_BRIGHTNESS: validate_brightness(attributes.get(ATTR_BRIGHTNESS)),
            ATTR_COLOR_TEMP: validate_color_temp(attributes.get(ATTR_COLOR_TEMP)),
            ATTR_RGB_COLOR: validate_rgb_color(attributes.get(ATTR_RGB_COLOR)),
            ATTR_TRANSITION: validate_transition(
                attributes.get(ATTR_TRANSITION, DEFAULT_TRANSITION)
            ),
            ATTR_FORCE: bool(attributes.get(ATTR_FORCE, False)),
            ATTR_LOCKED: bool(attributes.get(ATTR_LOCKED, False)),
            ATTR_CONDITIONS: attributes.get(ATTR_CONDITIONS, {}),
            ATTR_SOURCE: attributes.get(ATTR_SOURCE, "manual"),
            ATTR_CREATED_AT: now,
            ATTR_LAST_MODIFIED: now,
            ATTR_LAYER_TYPE: attributes.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE),
        }
        
        # Handle expiration if timeout_minutes provided
        if "timeout_minutes" in attributes:
            timeout_minutes = attributes["timeout_minutes"]
            expires_at = now + timedelta(minutes=timeout_minutes)
            self.layers[layer_id][ATTR_EXPIRES_AT] = expires_at
        elif ATTR_EXPIRES_AT in attributes:
            self.layers[layer_id][ATTR_EXPIRES_AT] = attributes[ATTR_EXPIRES_AT]
        
        # Add modifier-specific attributes
        modifier_attrs = [
            ATTR_BRIGHTNESS_PCT_DELTA,
            ATTR_COLOR_TEMP_KELVIN_DELTA,
            ATTR_BRIGHTNESS_FACTOR,
            ATTR_COLOR_TEMP_FACTOR,
        ]
        for attr in modifier_attrs:
            if attr in attributes:
                self.layers[layer_id][attr] = attributes[attr]
        
        # Add any extra attributes not in standard set
        for key, value in attributes.items():
            if key not in self.layers[layer_id] and key != "timeout_minutes":
                self.layers[layer_id][key] = value
        
        # Save and trigger recalculation
        self.schedule_save()
        self.schedule_recalculation()  # Phase 2: Triggers calculation + light update
        
        # Notify switch platform to create entity for new layer
        if self.new_layer_callback and layer_id != LAYER_BASE_ADAPTIVE:
            await self.new_layer_callback(layer_id, layer_name)
        
        _LOGGER.info("Created layer %s in zone %s with priority %d",
                    layer_id, self.zone_id, priority)
        return layer_id

    async def update_layer(self, layer_id: str, **updates: Any) -> bool:
        """Update layer - MUST be async, not @callback.
        
        This is the ONLY way switches should modify state.
        """
        if layer_id not in self.layers:
            _LOGGER.error("Layer %s not found in zone %s", layer_id, self.zone_id)
            return False
        
        # Check if layer is locked (unless force update)
        if self.layers[layer_id].get(ATTR_LOCKED, False) and not updates.pop("_force_update", False):
            _LOGGER.warning("Cannot update locked layer %s", layer_id)
            return False
        
        # Validate all updates
        if ATTR_BRIGHTNESS in updates:
            updates[ATTR_BRIGHTNESS] = validate_brightness(updates[ATTR_BRIGHTNESS])
        if ATTR_COLOR_TEMP in updates:
            updates[ATTR_COLOR_TEMP] = validate_color_temp(updates[ATTR_COLOR_TEMP])
        if ATTR_RGB_COLOR in updates:
            updates[ATTR_RGB_COLOR] = validate_rgb_color(updates[ATTR_RGB_COLOR])
        if ATTR_PRIORITY in updates:
            updates[ATTR_PRIORITY] = validate_priority(updates[ATTR_PRIORITY])
        if ATTR_TRANSITION in updates:
            updates[ATTR_TRANSITION] = validate_transition(updates[ATTR_TRANSITION])
        
        # Update timestamp
        updates[ATTR_LAST_MODIFIED] = get_timezone_aware_now()
        
        # Apply updates
        self.layers[layer_id].update(updates)
        
        # Save and trigger recalculation
        self.schedule_save()
        self.schedule_recalculation()  # Phase 2: Triggers calculation + light update
        
        _LOGGER.debug("Updated layer %s in zone %s", layer_id, self.zone_id)
        return True

    async def delete_layer(self, layer_id: str) -> bool:
        """Remove a layer - MUST be async."""
        if layer_id not in self.layers:
            _LOGGER.warning("Cannot delete non-existent layer %s", layer_id)
            return False
        
        del self.layers[layer_id]
        
        # Save and trigger recalculation
        self.schedule_save()
        self.schedule_recalculation()  # Phase 2: Triggers calculation + light update
        
        _LOGGER.info("Deleted layer %s from zone %s", layer_id, self.zone_id)
        return True

    def get_layer(self, layer_id: str) -> dict[str, Any] | None:
        """Get layer data by ID - read-only, can be sync."""
        return self.layers.get(layer_id)

    async def _async_update_data(self) -> dict[str, Any]:
        """Calculate new state and apply to lights.
        
        This is called after debouncing to:
        1. Calculate which layer wins
        2. Apply the result to lights
        3. Return the updated data
        """
        try:
            # Track calculation timing for Phase 4 sensors
            start_time = dt_util.now()
            
            # Get all layers for calculation
            # The calculator will only consider layers where is_on=True
            all_layers = [
                {**layer, "layer_id": lid}
                for lid, layer in self.layers.items()
            ]
            
            # Calculate winning state with zone config for modifier support
            if all_layers:
                calc_result = self._calculator.calculate_state(all_layers, self.zone_config)
            else:
                calc_result = {
                    "winning_layer": None,
                    "final_state": {"power": "off"},
                    "conflicts": [],
                    "calculation_path": [],
                    "total_active_layers": 0,
                    "applied_modifiers": [],
                }
            
            # Add timing and metadata for Phase 4 sensors
            calc_time_ms = (dt_util.now() - start_time).total_seconds() * 1000
            calc_result["timestamp"] = start_time.isoformat()
            calc_result["calculation_time_ms"] = calc_time_ms
            calc_result["trigger"] = "layer_update"  # Will be overridden by specific triggers
            calc_result["cache_hit"] = False  # Would be set by calculator if caching implemented
            
            # Store calculation result
            self._last_calculation = calc_result
            
            # Fire conflict event if conflicts detected
            conflicts = calc_result.get("conflicts", [])
            if conflicts:
                # Determine resolution reason
                winning_layer = calc_result.get("winning_layer")
                resolution_reason = "no_winner"
                
                if winning_layer:
                    # Find the winning layer data
                    winning_data = next(
                        (l for l in all_layers if l["layer_id"] == winning_layer),
                        None
                    )
                    if winning_data:
                        if winning_data.get(ATTR_FORCE):
                            resolution_reason = "force_flag_override"
                        elif winning_data.get(ATTR_LOCKED):
                            resolution_reason = "locked_layer"
                        else:
                            resolution_reason = f"highest_priority_{winning_data.get(ATTR_PRIORITY, 0)}"
                
                # Determine conflict severity
                severity = "info"
                if "multiple_force_flags" in conflicts:
                    severity = "warning"
                elif "all_layers_locked" in conflicts:
                    severity = "error"
                
                self.hass.bus.async_fire(
                    EVENT_CONFLICT_DETECTED,
                    {
                        "zone_id": self.zone_id,
                        "conflicts": conflicts,
                        "severity": severity,
                        "resolution": winning_layer,
                        "resolution_reason": resolution_reason,
                        "affected_layers": [
                            {
                                "layer_id": l["layer_id"],
                                "priority": l.get(ATTR_PRIORITY, 0),
                                "force": l.get(ATTR_FORCE, False),
                                "locked": l.get(ATTR_LOCKED, False),
                            }
                            for l in all_layers
                            if l.get(ATTR_IS_ON, False)  # Only include active layers in conflict report
                        ],
                        "timestamp": dt_util.now().isoformat(),
                    }
                )
                
                _LOGGER.info(
                    "Conflict detected in zone %s: %s, resolved with %s (%s)",
                    self.zone_id,
                    conflicts,
                    winning_layer,
                    resolution_reason
                )
            
            # Check if state actually changed
            state_changed = (self._last_final_state != calc_result["final_state"])
            
            # Only apply to lights if state changed
            if state_changed:
                application_result = await self._light_controller.apply_state(calc_result["final_state"])
            else:
                application_result = True  # Skip redundant update
                _LOGGER.debug("Skipping light update for zone %s - state unchanged", self.zone_id)
            
            # Track unavailable lights from the light controller
            if hasattr(self._light_controller, '_unavailable_lights'):
                calc_result["lights_unavailable"] = list(self._light_controller._unavailable_lights)
            else:
                calc_result["lights_unavailable"] = []
            
            # Only fire event if state actually changed
            if state_changed:
                self._last_final_state = calc_result["final_state"].copy()
                self.hass.bus.async_fire(
                    EVENT_CALCULATION_COMPLETE,
                    {
                        "zone_id": self.zone_id,
                        "winning_layer": calc_result.get("winning_layer"),
                        "final_state": calc_result.get("final_state"),
                        "conflicts": calc_result.get("conflicts"),
                        "calculation_time_ms": calc_result.get("calculation_time_ms", 0),
                    }
                )
            
            _LOGGER.debug(
                "Calculation complete for zone %s: winner=%s, time=%.2fms",
                self.zone_id,
                calc_result.get("winning_layer"),
                calc_result.get("calculation_time_ms", 0)
            )
            
            # Update and return the data
            self.data = self._get_current_data()
            return self.data
        except Exception as err:
            _LOGGER.error("Error in update cycle for zone %s: %s", self.zone_id, err, exc_info=True)
            # Return last known good state
            if self.data:
                return self.data
            # Or minimal safe state
            return {
                "layers": copy.deepcopy(self.layers),
                "error": str(err),
                "zone_id": self.zone_id,
                "last_updated": get_timezone_aware_now(),
            }
    
    def schedule_recalculation(self) -> None:
        """Schedule a recalculation with debouncing.
        
        This replaces the simple async_update_listeners() call
        to add debouncing and calculation.
        """
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        self._debounce_timer = self.hass.loop.call_later(
            DEBOUNCE_SECONDS,  # 100ms debounce
            lambda: self.hass.async_create_task(self.async_refresh())
        )
    
    async def async_refresh(self) -> None:
        """Refresh data with calculation."""
        await self._async_update_data()
        self.async_update_listeners()
    
    async def _setup_adaptive(self) -> None:
        """Set up adaptive lighting integration."""
        # Check if adaptive is enabled
        self._adaptive_enabled = self.config_entry.options.get(
            CONF_ADAPTIVE_ENABLED, False
        )
        
        if not self._adaptive_enabled:
            # Remove base_adaptive layer if it exists
            if LAYER_BASE_ADAPTIVE in self.layers:
                self.layers[LAYER_BASE_ADAPTIVE][ATTR_IS_ON] = False
                await self.save_layers()
            return
        
        _LOGGER.info("Setting up adaptive lighting for zone %s", self.zone_id)
        
        # Track adaptive factor sensor
        sensor_id = f"sensor.{self.zone_id}_adaptive_factor"
        
        # Don't wait for sensor - it will be created by the sensor platform
        # We'll start tracking it when it becomes available
        
        @callback
        def on_adaptive_change(event):
            """Handle adaptive factor changes."""
            new_state = event.data.get("new_state")
            if new_state and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._adaptive_factor = float(new_state.state)
                    _LOGGER.debug("Adaptive factor changed to %s for zone %s", 
                                 self._adaptive_factor, self.zone_id)
                    self.hass.async_create_task(self._update_adaptive_layer())
                except ValueError:
                    _LOGGER.warning("Invalid adaptive factor value: %s", new_state.state)
        
        # Remove old listener if exists
        if self._adaptive_listener:
            self._adaptive_listener()
        
        self._adaptive_listener = async_track_state_change_event(
            self.hass, sensor_id, on_adaptive_change
        )
        
        # Get initial factor if sensor exists
        sensor_state = self.hass.states.get(sensor_id)
        if sensor_state and sensor_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._adaptive_factor = float(sensor_state.state)
            except ValueError:
                pass
        
        # Initialize adaptive layer
        await self._update_adaptive_layer()
    
    async def _update_adaptive_layer(self) -> None:
        """Update the base_adaptive layer with current values."""
        if not self._adaptive_enabled:
            return
        
        # Get config values
        options = self.config_entry.options
        min_brightness = options.get(CONF_ADAPTIVE_BRIGHTNESS_MIN, 10)
        max_brightness = options.get(CONF_ADAPTIVE_BRIGHTNESS_MAX, 255)
        min_color = options.get(CONF_ADAPTIVE_COLOR_TEMP_MIN, 153)
        max_color = options.get(CONF_ADAPTIVE_COLOR_TEMP_MAX, 500)
        
        # Calculate actual values based on factor
        # Factor: 0 = day (bright/cool), 1 = night (dim/warm)
        brightness = int(
            max_brightness - (self._adaptive_factor * (max_brightness - min_brightness))
        )
        color_temp = int(
            min_color + (self._adaptive_factor * (max_color - min_color))
        )
        
        _LOGGER.debug(
            "Updating adaptive layer for %s: factor=%s, brightness=%s, color_temp=%s",
            self.zone_id, self._adaptive_factor, brightness, color_temp
        )
        
        # Update or create base_adaptive layer
        now = get_timezone_aware_now()
        
        if LAYER_BASE_ADAPTIVE not in self.layers:
            self.layers[LAYER_BASE_ADAPTIVE] = {
                ATTR_LAYER_NAME: "Adaptive Baseline",
                ATTR_IS_ON: True,
                ATTR_PRIORITY: 0,  # Lowest priority
                ATTR_BRIGHTNESS: brightness,
                ATTR_COLOR_TEMP: color_temp,
                ATTR_TRANSITION: DEFAULT_TRANSITION,
                ATTR_LOCKED: True,  # System-managed
                ATTR_SOURCE: "system",
                ATTR_CREATED_AT: now,
                ATTR_LAST_MODIFIED: now,
                "adaptive_factor": self._adaptive_factor,
            }
            _LOGGER.info("Created base_adaptive layer for zone %s", self.zone_id)
        else:
            self.layers[LAYER_BASE_ADAPTIVE].update({
                ATTR_IS_ON: True,
                ATTR_BRIGHTNESS: brightness,
                ATTR_COLOR_TEMP: color_temp,
                ATTR_LAST_MODIFIED: now,
                "adaptive_factor": self._adaptive_factor,
            })
        
        # Save and trigger update
        await self.save_layers()
        self.schedule_recalculation()
    
    async def async_shutdown(self) -> None:
        """Clean up when coordinator is being removed."""
        # Remove adaptive listener
        if self._adaptive_listener:
            self._adaptive_listener()
            self._adaptive_listener = None
        
        # Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        
        # Cancel timers safely
        if self._debounce_timer and not self._debounce_timer.cancelled():
            self._debounce_timer.cancel()
            self._debounce_timer = None
        if self._save_timer and not self._save_timer.cancelled():
            self._save_timer.cancel()
            self._save_timer = None
        
        # Final save
        try:
            await self.save_layers()
        except Exception as e:
            _LOGGER.error("Error during final save for zone %s: %s", self.zone_id, e)
    
    def _start_cleanup_task(self) -> None:
        """Start the background task for cleaning expired layers."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        async def cleanup_loop():
            """Background task that periodically checks for expired layers."""
            while True:
                try:
                    await asyncio.sleep(self._cleanup_interval)
                    await self._cleanup_expired_layers()
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    _LOGGER.error("Error in cleanup task for zone %s: %s", self.zone_id, err)
        
        self._cleanup_task = self.hass.async_create_task(cleanup_loop())
        _LOGGER.debug("Started cleanup task for zone %s", self.zone_id)
    
    async def _cleanup_expired_layers(self) -> None:
        """Remove any layers that have expired."""
        now = get_timezone_aware_now()
        expired_layers = []
        
        for layer_id, layer_data in self.layers.items():
            if ATTR_EXPIRES_AT in layer_data:
                expires_at = layer_data[ATTR_EXPIRES_AT]
                # Handle both datetime objects and ISO strings
                if isinstance(expires_at, str):
                    expires_at = dt_util.parse_datetime(expires_at)
                
                if expires_at and now >= expires_at:
                    expired_layers.append(layer_id)
                    _LOGGER.info(
                        "Layer %s in zone %s has expired (expired at %s)",
                        layer_id, self.zone_id, expires_at
                    )
        
        # Remove expired layers
        if expired_layers:
            for layer_id in expired_layers:
                # Skip adaptive layer - it should never expire
                if layer_id == LAYER_BASE_ADAPTIVE:
                    continue
                    
                del self.layers[layer_id]
                _LOGGER.info("Removed expired layer %s from zone %s", layer_id, self.zone_id)
            
            # Save and recalculate if we removed anything
            self.schedule_save()
            self.schedule_recalculation()
    
    def get_layer_time_remaining(self, layer_id: str) -> timedelta | None:
        """Get the time remaining before a layer expires."""
        layer = self.layers.get(layer_id)
        if not layer or ATTR_EXPIRES_AT not in layer:
            return None
        
        expires_at = layer[ATTR_EXPIRES_AT]
        if isinstance(expires_at, str):
            expires_at = dt_util.parse_datetime(expires_at)
        
        if not expires_at:
            return None
        
        now = get_timezone_aware_now()
        if now >= expires_at:
            return timedelta(0)  # Already expired
        
        return expires_at - now