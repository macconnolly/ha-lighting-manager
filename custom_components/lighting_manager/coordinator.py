"""Zone coordinator for Lighting Manager - Golden Path implementation.

CRITICAL: This coordinator is the single source of truth for all layer state.
The 'data' property returns the layers dictionary directly, not a copy.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_CONDITIONS,
    ATTR_CREATED_AT,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAST_MODIFIED,
    ATTR_LAYER_NAME,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    DEBOUNCE_SECONDS,
    DEFAULT_PRIORITY,
    DEFAULT_TRANSITION,
    DOMAIN,
    EVENT_CALCULATION_COMPLETE,
    EVENT_CONFLICT_DETECTED,
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
        )
        
        self.config_entry = entry
        self.zone_id = entry.data["zone_id"]
        self.zone_name = entry.data["zone_name"]
        self.light_entities = entry.options.get("light_entities", [])
        
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
        
        # Calculator and light controller (Phase 2)
        self._calculator = LightingCalculator()
        self._light_controller = LightController(hass, zone_id, self.light_entities)
        
        # Cached calculation result
        self._last_calculation: dict[str, Any] | None = None
        
        _LOGGER.info("Coordinator initialized for zone %s", self.zone_id)

    @property
    def data(self) -> dict[str, Any]:
        """CRITICAL: Always return current state - single source of truth.
        
        This is the GOLDEN PATH implementation - data is a property that
        returns the layers dictionary directly, not through _async_update_data.
        """
        # Include last calculation result if available
        calc_data = self._last_calculation or {
            "winning_layer": None,
            "final_state": {"power": "off"},
            "conflicts": [],
            "calculation_path": [],
        }
        
        return {
            "layers": self.layers,  # Direct reference, not copy!
            "active_layers": [
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
        }
        
        # Add any extra attributes not in standard set
        for key, value in attributes.items():
            if key not in self.layers[layer_id]:
                self.layers[layer_id][key] = value
        
        # Save and trigger recalculation
        self.schedule_save()
        self.schedule_recalculation()  # Phase 2: Triggers calculation + light update
        
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
        # Get active layers
        active_layers = [
            {**layer, "layer_id": lid}
            for lid, layer in self.layers.items()
            if layer.get(ATTR_IS_ON, False)
        ]
        
        # Calculate winning state
        if active_layers:
            calc_result = self._calculator.calculate_state(active_layers)
        else:
            calc_result = {
                "winning_layer": None,
                "final_state": {"power": "off"},
                "conflicts": [],
                "calculation_path": [],
                "total_active_layers": 0,
            }
        
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
                    (l for l in active_layers if l["layer_id"] == winning_layer),
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
                        for l in active_layers
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
        
        # Apply to lights
        await self._light_controller.apply_state(calc_result["final_state"])
        
        # Fire calculation complete event
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
        
        # Return the data (though we use the property now)
        return self.data
    
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
    
    async def async_shutdown(self) -> None:
        """Clean up when coordinator is being removed."""
        # Cancel timers
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._save_timer:
            self._save_timer.cancel()
        
        # Final save
        await self.save_layers()