"""Pure functional calculation engine for Lighting Manager.

This module contains NO Home Assistant imports and can be tested standalone.
It implements the core layer priority logic and conflict detection.
"""
from __future__ import annotations

import time
from typing import Any

# Import temperature constants
try:
    from .const import KELVIN_MIN, KELVIN_MAX
except ImportError:
    # Fallback for standalone testing
    KELVIN_MIN = 1500
    KELVIN_MAX = 10000

# Pure constants - no HA imports
ATTR_IS_ON = "is_on"
ATTR_PRIORITY = "priority"
ATTR_BRIGHTNESS = "brightness"
ATTR_COLOR_TEMP = "color_temp"
ATTR_RGB_COLOR = "rgb_color"
ATTR_TRANSITION = "transition"
ATTR_FORCE = "force"
ATTR_LOCKED = "locked"
ATTR_LAYER_NAME = "layer_name"
ATTR_LAYER_ID = "layer_id"
ATTR_LAYER_TYPE = "layer_type"

# Modifier-specific attributes
ATTR_BRIGHTNESS_PCT_DELTA = "brightness_pct_delta"
ATTR_COLOR_TEMP_KELVIN_DELTA = "color_temp_kelvin_delta"
ATTR_BRIGHTNESS_FACTOR = "brightness_factor"
ATTR_COLOR_TEMP_FACTOR = "color_temp_factor"
ATTR_EXPIRES_AT = "expires_at"

# Layer types
LAYER_TYPE_ABSOLUTE = "absolute"
LAYER_TYPE_MODIFIER = "modifier"
LAYER_TYPE_MULTIPLIER = "multiplier"


class LightingCalculator:
    """Pure functional calculator for layer priority resolution.
    
    This class has no side effects and can be tested in isolation.
    All methods are deterministic given the same inputs.
    """
    
    def __init__(self):
        """Initialize the calculator."""
        pass
    
    def calculate_state(self, layers: list[dict[str, Any]], zone_config: dict[str, Any] = None) -> dict[str, Any]:
        """Calculate final state from active layers.
        
        This is the main entry point for calculations.
        
        Args:
            layers: List of active layer dictionaries
            zone_config: Optional zone configuration (e.g., k_control_enabled)
            
        Returns:
            Dictionary with winning layer, final state, conflicts, etc.
        """
        start_time = time.perf_counter()
        
        if not layers:
            return self._empty_result()
        
        # Perform calculation with zone config
        result = self._calculate(layers, zone_config)
        
        # Add timing info
        result["calculation_time_ms"] = (time.perf_counter() - start_time) * 1000
        
        return result
    
    def _calculate(self, layers: list[dict[str, Any]], zone_config: dict[str, Any] = None) -> dict[str, Any]:
        """Perform the actual calculation logic with modifier support.
        
        Enhanced calculation:
        - Separates absolute and modifier layers
        - Finds winning absolute layer
        - Applies applicable modifiers
        - Returns combined result
        """
        conflicts = []
        calculation_path = []
        applied_modifiers = []
        
        # Filter to only active layers (is_on=True)
        active_layers = [
            l for l in layers 
            if l.get(ATTR_IS_ON, False)
        ]
        
        if not active_layers:
            calculation_path.append({
                "step": "no_active_layers",
                "result": "all_off"
            })
            return self._empty_result()
        
        # Separate layers by type
        absolute_layers = [
            l for l in active_layers 
            if l.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE) == LAYER_TYPE_ABSOLUTE
        ]
        
        modifier_layers = [
            l for l in active_layers 
            if l.get(ATTR_LAYER_TYPE) in [LAYER_TYPE_MODIFIER, LAYER_TYPE_MULTIPLIER]
        ]
        
        calculation_path.append({
            "step": "layer_separation",
            "absolute_count": len(absolute_layers),
            "modifier_count": len(modifier_layers)
        })
        
        # Find winning absolute layer (if any)
        winning_layer = None
        winning_state = {}
        
        if absolute_layers:
            # Check for force override layers
            forced_layers = [l for l in absolute_layers if l.get(ATTR_FORCE, False)]
            
            if forced_layers:
                # Force layers override everything
                calculation_path.append({
                    "step": "force_override",
                    "forced_count": len(forced_layers)
                })
                candidates = forced_layers
            else:
                candidates = absolute_layers
            
            # Find highest priority
            max_priority = max(l.get(ATTR_PRIORITY, 0) for l in candidates)
            top_priority_layers = [
                l for l in candidates 
                if l.get(ATTR_PRIORITY, 0) == max_priority
            ]
            
            # Detect conflicts
            if len(top_priority_layers) > 1:
                conflict_ids = [l.get(ATTR_LAYER_ID, "unknown") for l in top_priority_layers]
                conflicts.append({
                    "type": "priority_tie",
                    "priority": max_priority,
                    "layers": conflict_ids
                })
                calculation_path.append({
                    "step": "conflict_detected",
                    "priority": max_priority,
                    "conflicting_layers": conflict_ids
                })
            
            # Winner is first in the list (or only one)
            winning_layer = top_priority_layers[0]
            winning_state = self._extract_light_state(winning_layer)
            
            calculation_path.append({
                "step": "winner_selected",
                "winner": winning_layer.get(ATTR_LAYER_ID),
                "priority": winning_layer.get(ATTR_PRIORITY, 0),
                "initial_state": winning_state.copy()
            })
        
        # Apply modifiers to winning state (or start from defaults if no absolute winner)
        if modifier_layers:
            if not winning_state:
                # Start from sensible defaults if no absolute layer
                winning_state = {
                    ATTR_BRIGHTNESS: 128,  # 50% brightness
                    ATTR_COLOR_TEMP: 370,   # Neutral white
                }
                calculation_path.append({
                    "step": "default_base_state",
                    "reason": "no_absolute_layer",
                    "state": winning_state.copy()
                })
            
            # Sort modifiers by priority for consistent application order
            sorted_modifiers = sorted(
                modifier_layers,
                key=lambda x: x.get(ATTR_PRIORITY, 0)
            )
            
            for modifier in sorted_modifiers:
                # Check if modifier should apply
                modifier_priority = modifier.get(ATTR_PRIORITY, 0)
                
                # If zone_config has priority limits, check them
                if zone_config:
                    min_priority = zone_config.get("modifier_priority_min", 0)
                    max_priority = zone_config.get("modifier_priority_max", 100)
                    if modifier_priority < min_priority or modifier_priority > max_priority:
                        calculation_path.append({
                            "step": "modifier_skipped",
                            "modifier": modifier.get(ATTR_LAYER_ID),
                            "reason": "priority_out_of_range",
                            "priority": modifier_priority,
                            "allowed_range": [min_priority, max_priority]
                        })
                        continue
                
                # Apply modifier
                before_state = winning_state.copy()
                winning_state = self._apply_modifier(winning_state, modifier)
                
                applied_modifiers.append({
                    "name": modifier.get(ATTR_LAYER_NAME, modifier.get(ATTR_LAYER_ID, "unknown")),
                    "type": modifier.get(ATTR_LAYER_TYPE, LAYER_TYPE_MODIFIER),
                    "priority": modifier_priority,
                    "changes": self._diff_states(before_state, winning_state)
                })
                
                calculation_path.append({
                    "step": "modifier_applied",
                    "modifier": modifier.get(ATTR_LAYER_ID),
                    "type": modifier.get(ATTR_LAYER_TYPE),
                    "priority": modifier_priority,
                    "state_before": before_state,
                    "state_after": winning_state.copy()
                })
        
        # Apply zone constraints if configured
        if zone_config:
            constrained_state = self._apply_zone_constraints(winning_state, zone_config)
            if constrained_state != winning_state:
                calculation_path.append({
                    "step": "zone_constraints_applied",
                    "state_before": winning_state,
                    "state_after": constrained_state
                })
                winning_state = constrained_state
        
        # Build result
        result = {
            "winning_layer": winning_layer.get(ATTR_LAYER_ID) if winning_layer else None,
            "winning_priority": winning_layer.get(ATTR_PRIORITY, 0) if winning_layer else 0,
            "conflicts": conflicts,
            "active_layers": [l.get(ATTR_LAYER_ID, "unknown") for l in active_layers],
            "final_state": winning_state,
            "calculation_path": calculation_path,
            "applied_modifiers": applied_modifiers,
        }
        
        # Add light control attributes
        if winning_state:
            result.update({
                ATTR_BRIGHTNESS: winning_state.get(ATTR_BRIGHTNESS),
                ATTR_COLOR_TEMP: winning_state.get(ATTR_COLOR_TEMP),
                ATTR_RGB_COLOR: winning_state.get(ATTR_RGB_COLOR),
                ATTR_TRANSITION: winning_layer.get(ATTR_TRANSITION, 1.0) if winning_layer else 1.0,
            })
        
        return result
    
    def _apply_modifier(self, base_state: dict[str, Any], modifier: dict[str, Any]) -> dict[str, Any]:
        """Apply a modifier layer to a base state.
        
        Modifiers can apply:
        - Percentage changes (brightness_pct_delta)
        - Absolute changes (color_temp_kelvin_delta)
        - Multiplier factors (brightness_factor, color_temp_factor)
        """
        result = base_state.copy()
        
        # Apply brightness percentage delta
        if ATTR_BRIGHTNESS_PCT_DELTA in modifier and ATTR_BRIGHTNESS in result:
            delta = modifier[ATTR_BRIGHTNESS_PCT_DELTA]
            current = result[ATTR_BRIGHTNESS]
            # Calculate new value: current * (1 + delta/100)
            new_brightness = int(current * (1 + delta / 100))
            # Clamp to valid range
            result[ATTR_BRIGHTNESS] = max(1, min(255, new_brightness))
        
        # Apply brightness factor (multiplier)
        if ATTR_BRIGHTNESS_FACTOR in modifier and ATTR_BRIGHTNESS in result:
            factor = modifier[ATTR_BRIGHTNESS_FACTOR]
            result[ATTR_BRIGHTNESS] = max(1, min(255, int(result[ATTR_BRIGHTNESS] * factor)))
        
        # Apply color temperature kelvin delta
        if ATTR_COLOR_TEMP_KELVIN_DELTA in modifier and ATTR_COLOR_TEMP in result:
            delta_kelvin = modifier[ATTR_COLOR_TEMP_KELVIN_DELTA]
            current_mireds = result[ATTR_COLOR_TEMP]
            # Convert to Kelvin, apply delta, convert back to mireds
            current_kelvin = 1000000 / current_mireds if current_mireds > 0 else 4000
            new_kelvin = current_kelvin + delta_kelvin
            # Clamp to configured range
            new_kelvin = max(KELVIN_MIN, min(KELVIN_MAX, new_kelvin))
            result[ATTR_COLOR_TEMP] = int(1000000 / new_kelvin)
        
        # Apply color temperature factor
        if ATTR_COLOR_TEMP_FACTOR in modifier and ATTR_COLOR_TEMP in result:
            factor = modifier[ATTR_COLOR_TEMP_FACTOR]
            current_mireds = result[ATTR_COLOR_TEMP]
            current_kelvin = 1000000 / current_mireds if current_mireds > 0 else 4000
            new_kelvin = current_kelvin * factor
            new_kelvin = max(KELVIN_MIN, min(KELVIN_MAX, new_kelvin))
            result[ATTR_COLOR_TEMP] = int(1000000 / new_kelvin)
        
        # Copy over any direct color values from modifier
        if ATTR_RGB_COLOR in modifier:
            result[ATTR_RGB_COLOR] = modifier[ATTR_RGB_COLOR]
        
        return result
    
    def _apply_zone_constraints(self, state: dict[str, Any], zone_config: dict[str, Any]) -> dict[str, Any]:
        """Apply zone-specific constraints to the final state.
        
        This ensures the output respects zone limits for brightness and color temperature.
        """
        result = state.copy()
        
        # Apply brightness constraints
        if ATTR_BRIGHTNESS in result:
            min_b = zone_config.get("base_min_brightness", 1)
            max_b = zone_config.get("base_max_brightness", 255)
            result[ATTR_BRIGHTNESS] = max(min_b, min(max_b, result[ATTR_BRIGHTNESS]))
        
        # Apply color temperature constraints
        if ATTR_COLOR_TEMP in result:
            # Zone config is in Kelvin, need to convert
            min_k = zone_config.get("base_min_kelvin", 2000)
            max_k = zone_config.get("base_max_kelvin", 6500)
            
            # Convert current mireds to Kelvin
            current_mireds = result[ATTR_COLOR_TEMP]
            current_kelvin = 1000000 / current_mireds if current_mireds > 0 else 4000
            
            # Apply constraints
            constrained_kelvin = max(min_k, min(max_k, current_kelvin))
            
            # Convert back to mireds
            result[ATTR_COLOR_TEMP] = int(1000000 / constrained_kelvin)
        
        return result
    
    def _diff_states(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """Calculate the difference between two states."""
        changes = {}
        
        for key in [ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR]:
            if key in after:
                if key not in before or before[key] != after[key]:
                    changes[key] = {
                        "before": before.get(key),
                        "after": after[key]
                    }
        
        return changes
    
    def _extract_light_state(self, layer: dict[str, Any]) -> dict[str, Any]:
        """Extract light control attributes from a layer."""
        state = {}
        
        # Only extract actual light attributes
        for attr in [ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR]:
            if attr in layer:
                state[attr] = layer[attr]
        
        return state
    
    def _empty_result(self) -> dict[str, Any]:
        """Return an empty/default result when no layers are active."""
        return {
            "winning_layer": None,
            "winning_priority": 0,
            "conflicts": [],
            "active_layers": [],
            "final_state": {},
            "calculation_path": [{
                "step": "empty_result",
                "reason": "no_active_layers"
            }],
            "applied_modifiers": [],
        }


# Standalone test
if __name__ == "__main__":
    calc = LightingCalculator()
    
    # Test with absolute and modifier layers
    test_layers = [
        {
            ATTR_LAYER_ID: "manual",
            ATTR_LAYER_NAME: "Manual",
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 50,
            ATTR_BRIGHTNESS: 200,
            ATTR_COLOR_TEMP: 370,
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
        },
        {
            ATTR_LAYER_ID: "weather",
            ATTR_LAYER_NAME: "Weather Boost",
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 60,
            ATTR_BRIGHTNESS_PCT_DELTA: 20,
            ATTR_COLOR_TEMP_KELVIN_DELTA: -300,
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
        }
    ]
    
    zone_config = {
        "base_min_brightness": 10,
        "base_max_brightness": 255,
        "base_min_kelvin": 2000,
        "base_max_kelvin": 6500,
        "modifier_priority_min": 40,
        "modifier_priority_max": 80,
    }
    
    result = calc.calculate_state(test_layers, zone_config)
    
    print("Calculation Result:")
    print(f"  Winning Layer: {result['winning_layer']}")
    print(f"  Final Brightness: {result.get(ATTR_BRIGHTNESS)}")
    print(f"  Final Color Temp: {result.get(ATTR_COLOR_TEMP)}")
    print(f"  Applied Modifiers: {len(result['applied_modifiers'])}")
    print(f"  Calculation Time: {result['calculation_time_ms']:.2f}ms")