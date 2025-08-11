EXHAUSTIVE LIGHTING MANAGER REFACTORING SPECIFICATION

     Complete Implementation Instructions - No Implied Tasks

     ---
     PART 1: NEW FILE CREATION (6 FILES)

     FILE 1: /custom_components/lighting_manager/layer_manager.py

     Action: CREATE NEW FILE
     Complete Content:
     """Layer Manager - Handles CRUD operations and persistence for layers."""
     from __future__ import annotations

     import logging
     from datetime import datetime
     from typing import Any, Callable, Dict, List, Optional

     from homeassistant.core import HomeAssistant
     from homeassistant.helpers.storage import Store
     from homeassistant.util import dt as dt_util

     from .const import (
         ATTR_CREATED_AT,
         ATTR_IS_ON,
         ATTR_LAST_MODIFIED,
         ATTR_LAYER_NAME,
         ATTR_SOURCE,
         STORAGE_KEY_PREFIX,
         STORAGE_VERSION,
     )

     _LOGGER = logging.getLogger(__name__)


     class LayerManager:
         """Manages layer CRUD operations and persistence."""

         def __init__(self, hass: HomeAssistant, zone_id: str) -> None:
             """Initialize layer manager.

             Args:
                 hass: Home Assistant instance
                 zone_id: Unique identifier for the zone
             """
             self.hass = hass
             self.zone_id = zone_id
             self.layers: Dict[str, Dict[str, Any]] = {}
             self._store = Store(
                 hass,
                 STORAGE_VERSION,
                 f"{STORAGE_KEY_PREFIX}{zone_id}",
             )
             self._listeners: List[Callable[[], None]] = []
             self._save_pending = False
             _LOGGER.info("LayerManager initialized for zone %s", zone_id)

         async def load(self) -> None:
             """Load layers from storage.

             Filters out temporary layers (source == 'manual_override').
             Falls back to empty dict on error.
             """
             try:
                 _LOGGER.debug("Loading layers for zone %s", self.zone_id)
                 stored = await self._store.async_load()

                 if stored and isinstance(stored, dict):
                     # Only load configuration layers, not temporary ones
                     self.layers = {
                         lid: layer
                         for lid, layer in stored.get("layers", {}).items()
                         if layer.get(ATTR_SOURCE) != "manual_override"
                     }
                     _LOGGER.info(
                         "Loaded %d configuration layers for zone %s",
                         len(self.layers), self.zone_id
                     )
                 else:
                     self.layers = {}
                     _LOGGER.info("No stored layers found for zone %s", self.zone_id)

             except Exception as err:
                 _LOGGER.error(
                     "Failed to load layers for zone %s: %s",
                     self.zone_id, err, exc_info=True
                 )
                 self.layers = {}

         async def save(self) -> None:
             """Save configuration layers to storage.

             Only saves layers where source != 'manual_override'.
             """
             try:
                 # Filter to configuration layers only
                 config_layers = {
                     lid: layer
                     for lid, layer in self.layers.items()
                     if layer.get(ATTR_SOURCE) != "manual_override"
                 }

                 save_data = {
                     "version": STORAGE_VERSION,
                     "layers": config_layers,
                     "zone_id": self.zone_id,
                     "saved_at": dt_util.now().isoformat(),
                 }

                 await self._store.async_save(save_data)
                 self._save_pending = False
                 _LOGGER.debug(
                     "Saved %d configuration layers for zone %s",
                     len(config_layers), self.zone_id
                 )

             except Exception as err:
                 _LOGGER.error(
                     "Failed to save layers for zone %s: %s",
                     self.zone_id, err, exc_info=True
                 )

         def create_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> None:
             """Create a new layer.

             Args:
                 layer_id: Unique identifier for the layer
                 layer_data: Layer attributes
             """
             if layer_id in self.layers:
                 _LOGGER.warning(
                     "Layer %s already exists in zone %s, skipping creation",
                     layer_id, self.zone_id
                 )
                 return

             # Add timestamps
             now = dt_util.now()
             layer_data[ATTR_CREATED_AT] = now.isoformat()
             layer_data[ATTR_LAST_MODIFIED] = now.isoformat()

             # Store layer
             self.layers[layer_id] = layer_data
             self._save_pending = True

             # Notify listeners
             self._notify_listeners()

             _LOGGER.info(
                 "Created layer %s in zone %s with %d attributes",
                 layer_id, self.zone_id, len(layer_data)
             )

         def update_layer(self, layer_id: str, updates: Dict[str, Any]) -> bool:
             """Update an existing layer.

             Args:
                 layer_id: Layer to update
                 updates: Attributes to update

             Returns:
                 True if updated, False if layer not found
             """
             if layer_id not in self.layers:
                 _LOGGER.warning(
                     "Cannot update non-existent layer %s in zone %s",
                     layer_id, self.zone_id
                 )
                 return False

             # Update timestamp
             updates[ATTR_LAST_MODIFIED] = dt_util.now().isoformat()

             # Apply updates
             self.layers[layer_id].update(updates)
             self._save_pending = True

             # Notify listeners
             self._notify_listeners()

             _LOGGER.debug(
                 "Updated layer %s in zone %s with %d changes",
                 layer_id, self.zone_id, len(updates)
             )
             return True

         def delete_layer(self, layer_id: str) -> bool:
             """Delete a layer.

             Args:
                 layer_id: Layer to delete

             Returns:
                 True if deleted, False if not found
             """
             if layer_id not in self.layers:
                 _LOGGER.warning(
                     "Cannot delete non-existent layer %s from zone %s",
                     layer_id, self.zone_id
                 )
                 return False

             # Delete layer
             del self.layers[layer_id]
             self._save_pending = True

             # Notify listeners
             self._notify_listeners()

             _LOGGER.info("Deleted layer %s from zone %s", layer_id, self.zone_id)
             return True

         def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
             """Get a layer by ID.

             Args:
                 layer_id: Layer to retrieve

             Returns:
                 Layer data or None if not found
             """
             return self.layers.get(layer_id)

         def get_active_layers(self) -> List[Dict[str, Any]]:
             """Get all active layers.

             Returns:
                 List of layers where is_on=True, with layer_id included
             """
             return [
                 {**layer, "layer_id": lid}
                 for lid, layer in self.layers.items()
                 if layer.get(ATTR_IS_ON, False)
             ]

         def get_all_layers(self) -> Dict[str, Dict[str, Any]]:
             """Get all layers.

             Returns:
                 Dictionary of all layers
             """
             return self.layers.copy()

         def add_listener(self, listener: Callable[[], None]) -> None:
             """Add a change listener.

             Args:
                 listener: Callback to invoke on changes
             """
             self._listeners.append(listener)
             _LOGGER.debug("Added listener, total: %d", len(self._listeners))

         def remove_listener(self, listener: Callable[[], None]) -> None:
             """Remove a change listener.

             Args:
                 listener: Callback to remove
             """
             if listener in self._listeners:
                 self._listeners.remove(listener)
                 _LOGGER.debug("Removed listener, remaining: %d", len(self._listeners))

         def _notify_listeners(self) -> None:
             """Notify all listeners of changes."""
             for listener in self._listeners:
                 try:
                     listener()
                 except Exception as err:
                     _LOGGER.error("Error notifying listener: %s", err, exc_info=True)

         def has_pending_save(self) -> bool:
             """Check if there are unsaved changes.

             Returns:
                 True if save is pending
             """
             return self._save_pending

     FILE 2: /custom_components/lighting_manager/state_calculator.py

     Action: CREATE NEW FILE
     Complete Content:
     """State Calculator - Pure functional calculation with no Home Assistant dependencies."""
     from __future__ import annotations

     import logging
     from typing import Any, Dict, List, Optional

     # NO Home Assistant imports - this is a pure calculator

     _LOGGER = logging.getLogger(__name__)


     class StateCalculator:
         """Pure functional calculator for desired state.

         Takes layers and adaptive values, returns calculated state.
         NO SIDE EFFECTS, NO HOME ASSISTANT DEPENDENCIES.
         """

         def __init__(self) -> None:
             """Initialize calculator."""
             _LOGGER.debug("StateCalculator initialized")

         def calculate_state(
             self,
             layers: List[Dict[str, Any]],
             adaptive_values: Optional[Dict[str, Any]] = None
         ) -> Dict[str, Any]:
             """Calculate the desired state from active layers.

             Args:
                 layers: List of layer dictionaries with layer_id included
                 adaptive_values: Optional adaptive brightness/color values

             Returns:
                 Dictionary containing:
                     - power: "on" or "off"
                     - brightness: 0-255 (if on)
                     - color_temp: mireds (if on)
                     - transition: seconds
                     - winning_layer: layer_id of winner
                     - calculation_path: List of calculation steps
                     - applied_modifiers: List of modifier layer_ids
                     - conflicts: List of detected conflicts
             """
             _LOGGER.debug("Calculating state from %d layers", len(layers))

             # Filter to active layers only
             active_layers = [
                 layer for layer in layers
                 if layer.get("is_on", False)
             ]

             if not active_layers:
                 _LOGGER.debug("No active layers, returning off state")
                 return {
                     "power": "off",
                     "winning_layer": None,
                     "calculation_path": ["No active layers"],
                     "applied_modifiers": [],
                     "conflicts": [],
                 }

             # Separate absolute and modifier layers
             absolute_layers = [
                 layer for layer in active_layers
                 if layer.get("layer_type", "absolute") == "absolute"
             ]

             modifier_layers = [
                 layer for layer in active_layers
                 if layer.get("layer_type") in ["modifier", "multiplier"]
             ]

             # Find winning absolute layer
             if not absolute_layers:
                 # No absolute layer, use adaptive values if available
                 if adaptive_values:
                     _LOGGER.debug("No absolute layers, using adaptive values")
                     base_state = {
                         "power": "on",
                         "brightness": adaptive_values.get("brightness", 128),
                         "color_temp": adaptive_values.get("color_temp", 370),
                         "transition": 2.0,
                     }
                     winning_layer = "adaptive_default"
                     calculation_path = ["No absolute layers", "Using adaptive values"]
                 else:
                     _LOGGER.debug("No absolute layers and no adaptive values")
                     return {
                         "power": "off",
                         "winning_layer": None,
                         "calculation_path": ["No absolute layers", "No adaptive values"],
                         "applied_modifiers": [],
                         "conflicts": [],
                     }
             else:
                 # Sort by priority (higher wins)
                 absolute_layers.sort(
                     key=lambda x: x.get("priority", 50),
                     reverse=True
                 )

                 # Check for force flags
                 forced_layers = [
                     layer for layer in absolute_layers
                     if layer.get("force", False)
                 ]

                 if forced_layers:
                     # Multiple force flags is a conflict
                     if len(forced_layers) > 1:
                         _LOGGER.warning("Multiple force flags detected")
                         conflicts = ["multiple_force_flags"]
                     else:
                         conflicts = []
                     winner = forced_layers[0]
                 else:
                     winner = absolute_layers[0]
                     conflicts = []

                 winning_layer = winner.get("layer_id", "unknown")
                 base_state = {
                     "power": "on",
                     "brightness": winner.get("brightness", 255),
                     "color_temp": winner.get("color_temp", 370),
                     "transition": winner.get("transition", 2.0),
                 }

                 calculation_path = [
                     f"Winner: {winning_layer}",
                     f"Priority: {winner.get('priority', 50)}",
                 ]

                 _LOGGER.debug("Winning layer: %s", winning_layer)

             # Apply modifiers
             applied_modifiers = []
             for modifier in modifier_layers:
                 modifier_id = modifier.get("layer_id", "unknown")

                 # Apply brightness delta
                 if "brightness_pct_delta" in modifier:
                     delta = modifier["brightness_pct_delta"]
                     current_pct = (base_state["brightness"] / 255) * 100
                     new_pct = max(0, min(100, current_pct + delta))
                     base_state["brightness"] = int((new_pct / 100) * 255)
                     applied_modifiers.append(modifier_id)
                     _LOGGER.debug(
                         "Applied brightness delta %+.1f%% from %s",
                         delta, modifier_id
                     )

                 # Apply color temp delta (in Kelvin)
                 if "color_temp_kelvin_delta" in modifier:
                     delta_k = modifier["color_temp_kelvin_delta"]
                     current_k = 1000000 / base_state["color_temp"]
                     new_k = max(2000, min(6500, current_k + delta_k))
                     base_state["color_temp"] = int(1000000 / new_k)
                     applied_modifiers.append(modifier_id)
                     _LOGGER.debug(
                         "Applied color temp delta %+dK from %s",
                         delta_k, modifier_id
                     )

                 # Apply brightness factor (multiplier)
                 if "brightness_factor" in modifier:
                     factor = modifier["brightness_factor"]
                     base_state["brightness"] = int(
                         min(255, base_state["brightness"] * factor)
                     )
                     applied_modifiers.append(modifier_id)
                     _LOGGER.debug(
                         "Applied brightness factor %.2fx from %s",
                         factor, modifier_id
                     )

             if applied_modifiers:
                 calculation_path.append(f"Applied {len(applied_modifiers)} modifiers")

             # Add RGB color if present in winner
             if absolute_layers and "rgb_color" in absolute_layers[0]:
                 base_state["rgb_color"] = absolute_layers[0]["rgb_color"]

             return {
                 **base_state,
                 "winning_layer": winning_layer,
                 "calculation_path": calculation_path,
                 "applied_modifiers": applied_modifiers,
                 "conflicts": conflicts if 'conflicts' in locals() else [],
             }

     FILE 3: /custom_components/lighting_manager/change_detector.py

     Action: CREATE NEW FILEComplete Content:
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

             # Create the layer
             self.layer_manager.create_layer(override_id, override_layer)

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

     FILE 4: /custom_components/lighting_manager/adaptive_provider.py

     Action: CREATE NEW FILE
     Complete Content:
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

     FILE 5: /custom_components/lighting_manager/zone_state_machine.py

     Action: CREATE NEW FILE
     Complete Content:
     """Zone State Machine - Manages high-level zone states and transitions."""
     from __future__ import annotations

     import logging
     from enum import Enum
     from typing import Callable, List, Optional

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

     FILE 6: /custom_components/lighting_manager/light_controller.py

     Action: COMPLETE REWRITE
     Complete Content:
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

     ---
     PART 2: COORDINATOR REWRITE

     FILE 7: /custom_components/lighting_manager/coordinator.py

     Action: COMPLETE REWRITE
     Complete Content:
     """Zone Coordinator - Pure orchestrator following sacred separation of concerns."""
     from __future__ import annotations

     import asyncio
     import logging
     from datetime import timedelta
     from typing import Any, Callable, Dict, List, Optional

     from homeassistant.config_entries import ConfigEntry
     from homeassistant.core import HomeAssistant, callback
     from homeassistant.helpers.event import (
         async_track_state_change_event,
         async_track_time_interval,
     )
     from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
     from homeassistant.util import dt as dt_util

     # Import all components
     from .adaptive_provider import AdaptiveProvider
     from .change_detector import ChangeDetector
     from .layer_manager import LayerManager
     from .light_controller import LightController
     from .state_calculator import StateCalculator
     from .zone_state_machine import ZoneState, ZoneStateMachine

     from .const import (
         DOMAIN,
         EVENT_CALCULATION_COMPLETE,
         EVENT_CALCULATION_FAILED,
     )

     _LOGGER = logging.getLogger(__name__)


     class ZoneCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
         """Zone Coordinator - Pure orchestrator.

         CRITICAL: This coordinator contains NO business logic.
         It ONLY orchestrates between components.
         """

         def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
             """Initialize coordinator as pure orchestrator.

             Args:
                 hass: Home Assistant instance
                 entry: Config entry
             """
             super().__init__(
                 hass,
                 _LOGGER,
                 name=f"{DOMAIN}_{entry.data['zone_id']}",
                 config_entry=entry,
             )

             # Basic configuration
             self.config_entry = entry
             self.zone_id = entry.data["zone_id"]
             self.zone_name = entry.data["zone_name"]
             self.light_entities = entry.options.get("light_entities", [])

             # Initialize all components (separation of concerns)
             self.layer_manager = LayerManager(hass, self.zone_id)
             self.state_calculator = StateCalculator()
             self.light_controller = LightController(hass, self.zone_id, self.light_entities)
             self.adaptive_provider = AdaptiveProvider(hass, entry.options)
             self.state_machine = ZoneStateMachine(hass, self.zone_id)

             # Initialize change detector after other components
             self.change_detector = ChangeDetector(
                 hass,
                 self.zone_id,
                 self.layer_manager,
                 self.light_controller
             )

             # Event listeners
             self._cleanup_tasks: List[Callable] = []
             self._manual_check_task = None
             self._sun_listener = None
             self._debounce_timer = None

             # Fail-safe state
             self._last_known_good_state: Optional[Dict[str, Any]] = None

             # Compatibility properties
             self.layers = self.layer_manager.layers  # Direct reference for switch platform
             self.new_layer_callback = None  # For dynamic switch creation

             # Initial data structure
             self.data = self._create_empty_data()

             _LOGGER.info(
                 "ZoneCoordinator initialized for zone %s with %d lights",
                 self.zone_id, len(self.light_entities)
             )

         async def async_load(self) -> None:
             """Initialize all components and set up monitoring."""
             _LOGGER.info("Loading coordinator for zone %s", self.zone_id)

             # Load layers from storage
             await self.layer_manager.load()

             # Set up component listeners
             self.layer_manager.add_listener(self._on_layers_changed)
             self.state_machine.add_listener(self._on_state_changed)

             # Start manual control detection (every 5 seconds)
             self._manual_check_task = async_track_time_interval(
                 self.hass,
                 self._check_manual_control,
                 timedelta(seconds=5)
             )
             self._cleanup_tasks.append(self._manual_check_task)

             # Track sun changes if adaptive enabled
             if self.adaptive_provider.enabled:
                 self._sun_listener = async_track_state_change_event(
                     self.hass,
                     "sun.sun",
                     self._on_sun_changed
                 )
                 self._cleanup_tasks.append(self._sun_listener)

             # Set initial zone state
             self.state_machine.transition_to(ZoneState.AUTO, "initialization")

             # Read current light state as baseline (don't apply anything)
             current_state = self.light_controller.get_current_state()
             self.light_controller.last_commanded_state = current_state
             self._last_known_good_state = current_state

             _LOGGER.info(
                 "Coordinator loaded for zone %s: %d layers, current lights: %s",
                 self.zone_id, len(self.layer_manager.layers), current_state
             )

         # Event Handlers (pure routing, no logic)

         @callback
         def _on_layers_changed(self) -> None:
             """Handle layer changes - route to update."""
             _LOGGER.debug("Layers changed in zone %s", self.zone_id)
             self._schedule_update("layer_change")

         @callback
         def _on_state_changed(self, old_state: ZoneState, new_state: ZoneState) -> None:
             """Handle zone state changes - route to update."""
             _LOGGER.debug(
                 "Zone %s state changed: %s -> %s",
                 self.zone_id, old_state.value, new_state.value
             )
             self._schedule_update("state_change")

         @callback
         def _on_sun_changed(self, event) -> None:
             """Handle sun position changes - route to update."""
             _LOGGER.debug("Sun changed for zone %s", self.zone_id)
             self._schedule_update("sun_change")

         @callback
         async def _check_manual_control(self, now) -> None:
             """Periodic check for manual control."""
             # Skip if zone is locked
             if self.state_machine.state == ZoneState.LOCKED:
                 return

             # Check for manual changes
             if self.change_detector.check_for_manual_change():
                 _LOGGER.info("Manual control detected in zone %s", self.zone_id)

                 # Create override layer
                 override_id = self.change_detector.create_manual_override(timeout_hours=2.0)

                 # Transition to manual override state
                 self.state_machine.transition_to(
                     ZoneState.MANUAL_OVERRIDE,
                     f"manual control detected, created {override_id}"
                 )

                 # Save layers (but not the temporary override)
                 await self.layer_manager.save()

                 # Trigger update
                 self._schedule_update("manual_override")

         def _schedule_update(self, trigger: str = "unknown") -> None:
             """Schedule an update with debouncing.

             Args:
                 trigger: What triggered this update
             """
             if self._debounce_timer:
                 self._debounce_timer.cancel()

             self._debounce_timer = self.hass.loop.call_later(
                 0.1,  # 100ms debounce
                 lambda: self.hass.async_create_task(self._do_update(trigger))
             )

         async def _do_update(self, trigger: str) -> None:
             """Perform the actual update."""
             self.data["trigger"] = trigger
             await self.async_refresh()

         async def _async_update_data(self) -> Dict[str, Any]:
             """Main orchestration loop - coordinate between components.

             This is the ONLY place where components interact.
             """
             try:
                 _LOGGER.debug("Update cycle for zone %s (trigger: %s)", self.zone_id, self.data.get("trigger"))

                 # Step 1: Get adaptive values
                 adaptive_values = self.adaptive_provider.get_adaptive_values()

                 # Step 2: Get active layers
                 active_layers = self.layer_manager.get_active_layers()

                 # Step 3: Calculate desired state
                 calc_result = self.state_calculator.calculate_state(
                     active_layers,
                     adaptive_values
                 )

                 # Step 4: Apply state if appropriate
                 if self.state_machine.state in [ZoneState.AUTO, ZoneState.MANUAL_OVERRIDE]:
                     success = await self.light_controller.apply_state(calc_result)
                     if success:
                         self._last_known_good_state = calc_result
                 else:
                     _LOGGER.debug(
                         "Not applying state in zone %s (state: %s)",
                         self.zone_id, self.state_machine.state.value
                     )

                 # Step 5: Check for expired overrides
                 if self.change_detector.is_override_expired():
                     _LOGGER.info("Manual override expired in zone %s", self.zone_id)
                     self.change_detector.clear_manual_override()
                     self.state_machine.transition_to(ZoneState.AUTO, "override expired")

                 # Step 6: Fire success event
                 self.hass.bus.async_fire(
                     EVENT_CALCULATION_COMPLETE,
                     {
                         "zone_id": self.zone_id,
                         "trigger": self.data.get("trigger", "unknown"),
                         "winning_layer": calc_result.get("winning_layer"),
                         "final_state": calc_result,
                         "zone_state": self.state_machine.state.value,
                     }
                 )

                 # Step 7: Update data for entities
                 self.data = {
                     "layers": self.layer_manager.get_all_layers(),
                     "active_layers": [l["layer_id"] for l in active_layers],
                     "zone_state": self.state_machine.state.value,
                     "zone_state_info": self.state_machine.get_state_info(),
                     "manual_override_active": self.change_detector.manual_override_active,
                     "adaptive_values": adaptive_values,
                     "winning_layer": calc_result.get("winning_layer"),
                     "final_state": calc_result,
                     "applied_modifiers": calc_result.get("applied_modifiers", []),
                     "conflicts": calc_result.get("conflicts", []),
                     "calculation_path": calc_result.get("calculation_path", []),
                     "last_commanded_state": self.light_controller.last_commanded_state,
                     "current_actual_state": self.light_controller.get_current_state(),
                     "circuit_breaker_status": self.light_controller.get_circuit_status(),
                     "last_updated": dt_util.now().isoformat(),
                     "trigger": self.data.get("trigger", "unknown"),
                     "error": None,
                 }

                 return self.data

             except Exception as err:
                 _LOGGER.error(
                     "Error in update cycle for zone %s: %s",
                     self.zone_id, err, exc_info=True
                 )

                 # Fire failure event
                 self.hass.bus.async_fire(
                     EVENT_CALCULATION_FAILED,
                     {
                         "zone_id": self.zone_id,
                         "error": str(err),
                         "trigger": self.data.get("trigger", "unknown"),
                     }
                 )

                 # Use fail-safe state
                 if self._last_known_good_state:
                     _LOGGER.info("Using last known good state for zone %s", self.zone_id)
                     self.data["final_state"] = self._last_known_good_state

                 self.data["error"] = str(err)
                 return self.data

         # Compatibility methods for existing code

         async def create_layer(self, layer_name: str, **attributes) -> str:
             """Create a new layer (compatibility method)."""
             layer_id = layer_name.lower().replace(" ", "_")

             # Ensure unique ID
             suffix = 1
             test_id = layer_id
             while test_id in self.layer_manager.layers:
                 test_id = f"{layer_id}_{suffix}"
                 suffix += 1
             layer_id = test_id

             # Create layer
             layer_data = {
                 "layer_name": layer_name,
                 "is_on": False,
                 **attributes,
             }

             self.layer_manager.create_layer(layer_id, layer_data)

             # Save if not temporary
             if attributes.get("source") != "manual_override":
                 await self.layer_manager.save()

             # Notify switch platform
             if self.new_layer_callback:
                 await self.new_layer_callback(layer_id, layer_name)

             return layer_id

         async def update_layer(self, layer_id: str, **updates) -> bool:
             """Update a layer (compatibility method)."""
             success = self.layer_manager.update_layer(layer_id, updates)

             if success and self.layer_manager.has_pending_save():
                 await self.layer_manager.save()

             return success

         async def delete_layer(self, layer_id: str) -> bool:
             """Delete a layer (compatibility method)."""
             success = self.layer_manager.delete_layer(layer_id)

             if success:
                 await self.layer_manager.save()

             return success

         def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
             """Get a layer (compatibility method)."""
             return self.layer_manager.get_layer(layer_id)

         def schedule_recalculation(self) -> None:
             """Schedule recalculation (compatibility method)."""
             self._schedule_update("manual_trigger")

         async def save_layers(self) -> None:
             """Save layers (compatibility method)."""
             await self.layer_manager.save()

         def schedule_save(self) -> None:
             """Schedule save (compatibility method)."""
             self.hass.async_create_task(self.layer_manager.save())

         async def async_shutdown(self) -> None:
             """Clean up when coordinator is removed."""
             _LOGGER.info("Shutting down coordinator for zone %s", self.zone_id)

             # Cancel all listeners
             for cleanup_task in self._cleanup_tasks:
                 if cleanup_task:
                     cleanup_task()

             if self._debounce_timer:
                 self._debounce_timer.cancel()

             # Final save
             await self.layer_manager.save()

             _LOGGER.info("Coordinator shutdown complete for zone %s", self.zone_id)

         def _create_empty_data(self) -> Dict[str, Any]:
             """Create empty data structure."""
             return {
                 "layers": {},
                 "active_layers": [],
                 "zone_state": ZoneState.OFF.value,
                 "zone_state_info": {},
                 "manual_override_active": False,
                 "adaptive_values": {},
                 "winning_layer": None,
                 "final_state": {"power": "off"},
                 "applied_modifiers": [],
                 "conflicts": [],
                 "calculation_path": [],
                 "last_commanded_state": {},
                 "current_actual_state": {},
                 "circuit_breaker_status": {"state": "closed"},
                 "last_updated": None,
                 "trigger": None,
                 "error": None,
             }

     ---
     PART 3: SERVICE AND CONSTANT UPDATES

     FILE 8: /custom_components/lighting_manager/services.py

     Action: MODIFY
     Changes:

     1. Line 77-122: REPLACE the entire SERVICE_SET_LAYER_SCHEMA with:
     SERVICE_SET_LAYER_SCHEMA = vol.Schema({
         vol.Required("zone_id"): cv.string,
         vol.Required("layer_id"): cv.string,  # Now required for idempotent operation
         vol.Optional("layer_name"): cv.string,  # Optional display name
         vol.Optional(ATTR_LAYER_TYPE, default=LAYER_TYPE_ABSOLUTE): vol.In(
             ["absolute", "modifier", "multiplier"]
         ),
         vol.Optional(ATTR_IS_ON): cv.boolean,
         vol.Optional(ATTR_PRIORITY): vol.All(
             vol.Coerce(int), vol.Range(min=0, max=100)
         ),
         # ... rest of schema unchanged
     })

     2. Lines 450-578: REPLACE entire handle_set_layer function with:
     async def handle_set_layer(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
         """Set (create or update) a layer - idempotent operation.

         This is THE SINGLE ENTRY POINT for all layer configuration.
         """
         zone_id = call.data["zone_id"]
         layer_id = call.data["layer_id"]  # Required now

         try:
             coordinator = await _get_coordinator_from_call(hass, call)

             # Check if layer exists
             existing = coordinator.layer_manager.get_layer(layer_id)

             # Build complete layer data
             layer_data = {}

             # Copy all provided attributes
             for key, value in call.data.items():
                 if key not in ["zone_id", "layer_id"]:
                     layer_data[key] = value

             # Set defaults if not provided
             if "layer_name" not in layer_data:
                 layer_data["layer_name"] = layer_id.replace("_", " ").title()
             if "priority" not in layer_data:
                 layer_data["priority"] = 50
             if "is_on" not in layer_data:
                 layer_data["is_on"] = False
             if "source" not in layer_data:
                 layer_data["source"] = "service.set_layer"

             # Validate based on layer type
             layer_type = layer_data.get("layer_type", "absolute")
             if layer_type == "absolute":
                 # Ensure absolute layers have required attributes
                 if "brightness" not in layer_data:
                     layer_data["brightness"] = 255
                 if "color_temp" not in layer_data:
                     layer_data["color_temp"] = 370

             # Create or update
             if existing:
                 success = coordinator.layer_manager.update_layer(layer_id, layer_data)
                 action = "updated"
             else:
                 coordinator.layer_manager.create_layer(layer_id, layer_data)
                 success = True
                 action = "created"

             # Save if needed
             if coordinator.layer_manager.has_pending_save():
                 await coordinator.layer_manager.save()

             # Fire event
             hass.bus.async_fire(
                 f"lighting_manager_layer_{action}",
                 {
                     "zone_id": zone_id,
                     "layer_id": layer_id,
                     "action": action,
                     "layer_data": layer_data,
                 }
             )

             return {
                 "success": success,
                 "zone_id": zone_id,
                 "layer_id": layer_id,
                 "action": action,
             }

         except Exception as e:
             _LOGGER.error("Failed to set layer %s: %s", layer_id, e)
             raise ServiceValidationError(str(e))

     3. Lines 256-265: COMMENT OUT create_layer service registration:
     # DEPRECATED - use set_layer instead
     # ("create_layer", handle_create_layer, SERVICE_CREATE_LAYER_SCHEMA),

     4. Lines 266-268: COMMENT OUT update_layer service registration:
     # DEPRECATED - use set_layer instead
     # (SERVICE_UPDATE_LAYER, handle_update_layer, SERVICE_UPDATE_LAYER_SCHEMA),

     FILE 9: /custom_components/lighting_manager/const.py

     Action: MODIFY
     Add these constants at appropriate locations:

     1. After line 100 (Event constants section):
     # State machine events
     EVENT_ZONE_STATE_CHANGED = f"{DOMAIN}_zone_state_changed"
     EVENT_ZONE_STATE_TRANSITION_FAILED = f"{DOMAIN}_zone_state_transition_failed"

     # Manual control events
     EVENT_MANUAL_CONTROL_DETECTED = f"{DOMAIN}_manual_control_detected"
     EVENT_MANUAL_OVERRIDE_CREATED = f"{DOMAIN}_manual_override_created"
     EVENT_MANUAL_OVERRIDE_CLEARED = f"{DOMAIN}_manual_override_cleared"

     # Calculation events
     EVENT_CALCULATION_COMPLETE = f"{DOMAIN}_calculation_complete"
     EVENT_CALCULATION_FAILED = f"{DOMAIN}_calculation_failed"

     FILE 10: /custom_components/lighting_manager/__init__.py

     Action: MODIFY
     Changes:

     1. Line 29: CHANGE import to use new coordinator:
     from .coordinator import ZoneCoordinator

     2. Lines 54-58: No changes needed (coordinator handles initialization)
     3. Lines 87-90: REMOVE initial calculation:
     # Remove these lines - coordinator handles this
     # if any(layer.get("is_on", False) for layer in coordinator.layers.values()):
     #     await coordinator.async_refresh()

     FILE 11: /custom_components/lighting_manager/calculator.py

     Action: MODIFY (Already exists as state_calculator.py functionality)
     Note: The existing calculator.py can be kept for backward compatibility or removed if switching fully to state_calculator.py

     FILE 12: /custom_components/lighting_manager/switch.py

     Action: MODIFY
     Changes to ensure stateless operation:

     1. Lines 150-200: Verify LayerSwitch class has NO instance variables for state
     2. All @property methods: Must read from self.coordinator.layer_manager.get_layer(self.layer_id)
     3. Remove ANY caching or local state storage

     Example for is_on property:
     @property
     def is_on(self) -> bool:
         """Return true if layer is on."""
         layer = self.coordinator.layer_manager.get_layer(self.layer_id)
         return layer.get(ATTR_IS_ON, False) if layer else False

     FILE 13: /custom_components/lighting_manager/sensor.py

     Action: MODIFY
     Add observability attributes:

     1. In ZoneDiagnosticSensor class, add to extra_state_attributes:
     @property
     def extra_state_attributes(self) -> dict[str, Any]:
         """Return entity specific state attributes for debugging."""
         data = self.coordinator.data

         return {
             # Zone state machine
             "zone_state": data.get("zone_state"),
             "zone_state_info": data.get("zone_state_info", {}),

             # Manual control
             "manual_override_active": data.get("manual_override_active"),
             "last_commanded_state": data.get("last_commanded_state", {}),
             "current_actual_state": data.get("current_actual_state", {}),

             # Circuit breaker
             "circuit_breaker_status": data.get("circuit_breaker_status", {}),

             # Adaptive values
             "adaptive_values": data.get("adaptive_values", {}),

             # Calculation details
             "winning_layer": data.get("winning_layer"),
             "applied_modifiers": data.get("applied_modifiers", []),
             "conflicts": data.get("conflicts", []),
             "calculation_path": data.get("calculation_path", []),

             # Timing
             "last_updated": data.get("last_updated"),
             "trigger": data.get("trigger"),

             # Error state
             "error": data.get("error"),
         }

     FILE 14: /custom_components/lighting_manager/services.yaml

     Action: MODIFY
     Update set_layer service definition:

     set_layer:
       name: Set Layer
       description: Create or update a layer (idempotent operation)
       fields:
         zone_id:
           name: Zone ID
           description: The zone to modify
           required: true
           selector:
             text:
         layer_id:
           name: Layer ID
           description: Unique identifier for the layer
           required: true
           selector:
             text:
         layer_name:
           name: Layer Name
           description: Display name for the layer
           required: false
           selector:
             text:
         layer_type:
           name: Layer Type
           description: Type of layer (absolute, modifier, multiplier)
           required: false
           default: absolute
           selector:
             select:
               options:
                 - absolute
                 - modifier
                 - multiplier
         # ... rest of fields

     Comment out deprecated services:
     # DEPRECATED - use set_layer instead
     # create_layer:
     #   ...
     # update_layer:
     #   ...

     ---
     PART 4: TESTING CHECKLIST

     Manual Testing Steps:

     1. Create new zone - Verify no layers activate on startup
     2. Toggle physical switch - Verify manual override created within 5 seconds
     3. Check diagnostic sensor - Verify all new attributes visible
     4. Call set_layer service - Verify idempotent behavior
     5. Trigger 3 light failures - Verify circuit breaker opens
     6. Wait 2 hours - Verify manual override expires
     7. Change sun position - Verify adaptive values update

     Automated Test Files to Create:

     1. test_layer_manager.py - Unit tests for LayerManager
     2. test_state_calculator.py - Unit tests for StateCalculator
     3. test_change_detector.py - Unit tests for ChangeDetector
     4. test_zone_state_machine.py - Unit tests for ZoneStateMachine
     5. test_coordinator_integration.py - Integration tests

     ---
     IMPLEMENTATION ORDER

     1. Phase 1: Create all 6 new component files
     2. Phase 2: Rewrite coordinator.py and light_controller.py
     3. Phase 3: Update services.py for set_layer
     4. Phase 4: Update const.py with new constants
     5. Phase 5: Update init.py imports
     6. Phase 6: Update switch.py to be stateless
     7. Phase 7: Update sensor.py for observability
     8. Phase 8: Update services.yaml
     9. Phase 9: Test each component individually
     10. Phase 10: Integration testing

     VALIDATION CHECKLIST

     - Each component has single responsibility
     - No component imports another component (except coordinator)
     - All state in LayerManager
     - All calculation in StateCalculator
     - All hardware control in LightController
     - Coordinator only orchestrates
     - set_layer is idempotent
     - Manual control detected within 5 seconds
     - Circuit breaker stops after 3 failures
     - All internal state visible in diagnostic sensor
     - Events fired for all major actions
     - No polling except manual control check
     - Fail-safe uses last known good state