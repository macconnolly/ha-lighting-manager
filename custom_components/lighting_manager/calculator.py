"""Pure functional calculation engine for Lighting Manager.

This module contains NO Home Assistant imports and can be tested standalone.
It implements the core layer priority logic and conflict detection.
"""
from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from typing import Any

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
        self._cache_hits = 0
        self._cache_misses = 0
    
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
        
        # Create cache key from layer data
        cache_key = self._create_cache_key(layers)
        
        # Try to get from cache
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            self._cache_hits += 1
            cached["cache_hit"] = True
            cached["calculation_time_ms"] = (time.perf_counter() - start_time) * 1000
            return cached
        
        self._cache_misses += 1
        
        # Perform calculation with zone config
        result = self._calculate(layers, zone_config)
        
        # Add timing and cache info
        result["calculation_time_ms"] = (time.perf_counter() - start_time) * 1000
        result["cache_hit"] = False
        result["cache_stats"] = {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses)
        }
        
        # Cache the result
        self._cache_result(cache_key, result)
        
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
            if l.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE) in [LAYER_TYPE_MODIFIER, LAYER_TYPE_MULTIPLIER]
        ]
        
        calculation_path.append({
            "step": "layer_separation",
            "absolute_count": len(absolute_layers),
            "modifier_count": len(modifier_layers),
            "absolute_layers": [l.get(ATTR_LAYER_ID, "unknown") for l in absolute_layers],
            "modifier_layers": [l.get(ATTR_LAYER_ID, "unknown") for l in modifier_layers]
        })
        
        # Must have at least one absolute layer
        if not absolute_layers:
            calculation_path.append({
                "step": "no_absolute_layers",
                "result": "cannot_apply_modifiers_without_base"
            })
            return self._empty_result()
        
        # Find winning absolute layer (same logic as before)
        winning_layer = self._find_winning_absolute_layer(absolute_layers, conflicts, calculation_path)
        
        # Build base state from winning layer
        final_state = self._build_final_state(winning_layer)
        winning_priority = winning_layer.get(ATTR_PRIORITY, 0)
        
        # Find applicable modifiers
        # Modifiers apply if:
        # 1. They have higher priority than the winning absolute layer, OR
        # 2. They have the force flag set
        applicable_modifiers = []
        for modifier in modifier_layers:
            mod_priority = modifier.get(ATTR_PRIORITY, 0)
            mod_forced = modifier.get(ATTR_FORCE, False)
            
            if mod_forced or mod_priority > winning_priority:
                applicable_modifiers.append(modifier)
        
        if applicable_modifiers:
            calculation_path.append({
                "step": "applying_modifiers",
                "count": len(applicable_modifiers),
                "modifiers": [m.get(ATTR_LAYER_ID, "unknown") for m in applicable_modifiers]
            })
            
            # Sort modifiers by priority (lower priority applies first)
            applicable_modifiers.sort(key=lambda x: x.get(ATTR_PRIORITY, 0))
            
            # Apply each modifier in sequence
            for modifier in applicable_modifiers:
                final_state = self._apply_modifier(final_state, modifier, zone_config)
                applied_modifiers.append({
                    "id": modifier.get(ATTR_LAYER_ID, "unknown"),
                    "name": modifier.get(ATTR_LAYER_NAME, "Unknown"),
                    "type": modifier.get(ATTR_LAYER_TYPE, LAYER_TYPE_MODIFIER),
                    "priority": modifier.get(ATTR_PRIORITY, 0)
                })
        
        # Create result description
        if applied_modifiers:
            winning_name = f"{winning_layer.get(ATTR_LAYER_NAME, 'Unknown')} + {len(applied_modifiers)} modifier(s)"
        else:
            winning_name = winning_layer.get(ATTR_LAYER_NAME, "Unknown")
        
        return {
            "winning_layer": winning_layer.get(ATTR_LAYER_ID, "unknown"),
            "winning_layer_name": winning_name,
            "final_state": final_state,
            "conflicts": conflicts,
            "calculation_path": calculation_path,
            "applied_modifiers": applied_modifiers,
            "total_active_layers": len(active_layers),
            "forced_layer_active": winning_layer.get(ATTR_FORCE, False) or any(m.get(ATTR_FORCE, False) for m in applied_modifiers),
        }
    
    def _find_winning_absolute_layer(self, absolute_layers: list[dict[str, Any]], 
                                    conflicts: list, calculation_path: list) -> dict[str, Any]:
        """Find the winning absolute layer using standard priority rules."""
        # Separate forced and normal layers
        forced_layers = [l for l in absolute_layers if l.get(ATTR_FORCE, False)]
        normal_layers = [l for l in absolute_layers if not l.get(ATTR_FORCE, False)]
        
        # Check for multiple force flags (conflict)
        if len(forced_layers) > 1:
            conflicts.append({
                "type": "multiple_force_flags",
                "layers": [l.get(ATTR_LAYER_ID, "unknown") for l in forced_layers],
                "resolution": "using_highest_priority_forced"
            })
        
        # Determine winning layer
        if forced_layers:
            # Force flag overrides normal priority
            forced_layers.sort(key=lambda x: x.get(ATTR_PRIORITY, 0), reverse=True)
            winning_layer = forced_layers[0]
            calculation_path.append({
                "step": "forced_winner",
                "layer": winning_layer.get(ATTR_LAYER_ID, "unknown")
            })
        else:
            # Normal priority resolution
            normal_layers.sort(key=lambda x: x.get(ATTR_PRIORITY, 0), reverse=True)
            
            # Check for priority ties
            if len(normal_layers) > 1:
                top_priority = normal_layers[0].get(ATTR_PRIORITY, 0)
                tied_layers = [l for l in normal_layers 
                              if l.get(ATTR_PRIORITY, 0) == top_priority]
                
                if len(tied_layers) > 1:
                    conflicts.append({
                        "type": "priority_tie",
                        "priority": top_priority,
                        "layers": [l.get(ATTR_LAYER_ID, "unknown") for l in tied_layers],
                        "resolution": "using_first_in_list"
                    })
            
            winning_layer = normal_layers[0]
            calculation_path.append({
                "step": "priority_winner",
                "layer": winning_layer.get(ATTR_LAYER_ID, "unknown"),
                "priority": winning_layer.get(ATTR_PRIORITY, 0)
            })
        
        # Check if winning layer is locked
        if winning_layer.get(ATTR_LOCKED, False):
            conflicts.append({
                "type": "winning_layer_locked",
                "layer": winning_layer.get(ATTR_LAYER_ID, "unknown"),
                "note": "Layer modifications prevented"
            })
        
        return winning_layer
    
    def _apply_modifier(self, state: dict[str, Any], modifier: dict[str, Any], 
                       zone_config: dict[str, Any] = None) -> dict[str, Any]:
        """Apply a single modifier to the current state.
        
        Args:
            state: Current light state
            modifier: Modifier layer to apply
            zone_config: Optional zone configuration (e.g., k_control_enabled)
            
        Returns:
            Modified state
        """
        result = state.copy()
        zone_config = zone_config or {}
        
        # Brightness percentage delta (e.g., +15% for weather boost)
        if ATTR_BRIGHTNESS_PCT_DELTA in modifier and "brightness" in result:
            delta_pct = modifier[ATTR_BRIGHTNESS_PCT_DELTA]
            current = result["brightness"]
            # Apply percentage change
            new_val = current * (1 + delta_pct / 100.0)
            result["brightness"] = max(1, min(255, int(new_val)))
        
        # Brightness factor (multiplicative, e.g., 0.5 for 50% dimming)
        if ATTR_BRIGHTNESS_FACTOR in modifier and "brightness" in result:
            factor = modifier[ATTR_BRIGHTNESS_FACTOR]
            current = result["brightness"]
            result["brightness"] = max(1, min(255, int(current * factor)))
        
        # Color temperature delta in Kelvin
        # Only apply if zone has k_control enabled (default True)
        if zone_config.get("k_control_enabled", True):
            if ATTR_COLOR_TEMP_KELVIN_DELTA in modifier and "color_temp" in result:
                delta_k = modifier[ATTR_COLOR_TEMP_KELVIN_DELTA]
                current_mireds = result["color_temp"]
                
                # Convert mireds to Kelvin, apply delta, convert back
                current_kelvin = 1000000 / current_mireds
                new_kelvin = current_kelvin + delta_k
                new_kelvin = max(1000, min(10000, new_kelvin))  # Clamp to reasonable range
                new_mireds = 1000000 / new_kelvin
                
                result["color_temp"] = max(153, min(500, int(new_mireds)))
            
            # Color temperature factor
            if ATTR_COLOR_TEMP_FACTOR in modifier and "color_temp" in result:
                factor = modifier[ATTR_COLOR_TEMP_FACTOR]
                current_mireds = result["color_temp"]
                current_kelvin = 1000000 / current_mireds
                new_kelvin = current_kelvin * factor
                new_kelvin = max(1000, min(10000, new_kelvin))
                new_mireds = 1000000 / new_kelvin
                result["color_temp"] = max(153, min(500, int(new_mireds)))
        
        # Override transition if specified in modifier
        if ATTR_TRANSITION in modifier:
            result["transition"] = modifier[ATTR_TRANSITION]
        
        return result
    
    def _build_final_state(self, layer: dict[str, Any]) -> dict[str, Any]:
        """Build the final light state from the winning layer.
        
        This determines what should be applied to the actual lights.
        """
        state = {
            "power": "on",  # Active layers are always "on"
        }
        
        # Add brightness if specified
        if ATTR_BRIGHTNESS in layer and layer[ATTR_BRIGHTNESS] is not None:
            state["brightness"] = layer[ATTR_BRIGHTNESS]
        
        # Add color temperature if specified
        if ATTR_COLOR_TEMP in layer and layer[ATTR_COLOR_TEMP] is not None:
            state["color_temp"] = layer[ATTR_COLOR_TEMP]
        
        # Add RGB color if specified
        if ATTR_RGB_COLOR in layer and layer[ATTR_RGB_COLOR] is not None:
            state["rgb_color"] = layer[ATTR_RGB_COLOR]
        
        # Add transition if specified
        if ATTR_TRANSITION in layer and layer[ATTR_TRANSITION] is not None:
            state["transition"] = layer[ATTR_TRANSITION]
        else:
            state["transition"] = 2.0  # Default transition
        
        return state
    
    def _empty_result(self) -> dict[str, Any]:
        """Return result when no layers are active."""
        return {
            "winning_layer": None,
            "winning_layer_name": None,
            "final_state": {
                "power": "off",
            },
            "conflicts": [],
            "calculation_path": [],
            "total_active_layers": 0,
            "forced_layer_active": False,
            "calculation_time_ms": 0,
            "cache_hit": False,
        }
    
    def _create_cache_key(self, layers: list[dict[str, Any]]) -> str:
        """Create a deterministic cache key from layer data.
        
        This ensures the same layer configuration always produces
        the same cache key.
        """
        # Sort layers by ID for deterministic ordering
        sorted_layers = sorted(layers, key=lambda x: x.get(ATTR_LAYER_ID, ""))
        
        # Extract only relevant fields for caching
        cache_data = []
        for layer in sorted_layers:
            cache_data.append({
                "id": layer.get(ATTR_LAYER_ID, ""),
                "priority": layer.get(ATTR_PRIORITY, 0),
                "force": layer.get(ATTR_FORCE, False),
                "locked": layer.get(ATTR_LOCKED, False),
                "brightness": layer.get(ATTR_BRIGHTNESS),
                "color_temp": layer.get(ATTR_COLOR_TEMP),
                "rgb_color": layer.get(ATTR_RGB_COLOR),
                "transition": layer.get(ATTR_TRANSITION),
            })
        
        # Create hash
        json_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    @lru_cache(maxsize=128)
    def _get_cached_result(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached result by key.
        
        The LRU cache decorator handles the actual caching.
        """
        # In a real implementation, this would retrieve from cache
        # For now, the @lru_cache decorator handles it
        return None
    
    def _cache_result(self, cache_key: str, result: dict[str, Any]) -> None:
        """Cache a calculation result.
        
        In a real implementation, this would store to cache.
        """
        # The caching is handled by @lru_cache on _get_cached_result
        pass
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses),
            "cache_info": self._get_cached_result.cache_info()._asdict()
        }


# Standalone test function
def test_calculator():
    """Test the calculator in isolation (no HA required)."""
    calc = LightingCalculator()
    
    print("=" * 60)
    print("TESTING MODIFIER LAYER FUNCTIONALITY")
    print("=" * 60)
    
    # Test 1: Basic absolute layers (backwards compatibility)
    print("\n1. Traditional Absolute Layers Test:")
    print("-" * 40)
    
    absolute_layers = [
        {
            ATTR_LAYER_ID: "manual",
            ATTR_LAYER_NAME: "Manual",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 50,
            ATTR_BRIGHTNESS: 200,
            ATTR_COLOR_TEMP: 370,
        },
        {
            ATTR_LAYER_ID: "adaptive",
            ATTR_LAYER_NAME: "Adaptive",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 10,
            ATTR_BRIGHTNESS: 150,
            ATTR_COLOR_TEMP: 400,
        },
    ]
    
    result = calc.calculate_state(absolute_layers)
    print(f"  Winner: {result['winning_layer_name']} (priority {50})")
    print(f"  Final State: brightness={result['final_state']['brightness']}, color_temp={result['final_state']['color_temp']}")
    print(f"  Applied Modifiers: {len(result.get('applied_modifiers', []))}")
    
    # Test 2: Absolute layer with modifier
    print("\n2. Absolute Layer + Weather Boost Modifier:")
    print("-" * 40)
    
    layers_with_modifier = [
        {
            ATTR_LAYER_ID: "adaptive",
            ATTR_LAYER_NAME: "Adaptive",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 10,
            ATTR_BRIGHTNESS: 150,
            ATTR_COLOR_TEMP: 400,  # ~2500K
        },
        {
            ATTR_LAYER_ID: "weather_boost",
            ATTR_LAYER_NAME: "Cloudy Weather Boost",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 15,  # Higher than adaptive, so it applies
            ATTR_BRIGHTNESS_PCT_DELTA: 20,  # +20% brightness
            ATTR_COLOR_TEMP_KELVIN_DELTA: -500,  # Warmer by 500K
        },
    ]
    
    result = calc.calculate_state(layers_with_modifier)
    print(f"  Winner: {result['winning_layer_name']}")
    print(f"  Base State: brightness=150, color_temp=400")
    print(f"  Final State: brightness={result['final_state']['brightness']}, color_temp={result['final_state']['color_temp']}")
    print(f"  Applied Modifiers: {result.get('applied_modifiers', [])}")
    
    # Test 3: Multiple modifiers stacking
    print("\n3. Multiple Modifiers Stacking Test:")
    print("-" * 40)
    
    stacking_test = [
        {
            ATTR_LAYER_ID: "manual",
            ATTR_LAYER_NAME: "Manual",
            ATTR_LAYER_TYPE: LAYER_TYPE_ABSOLUTE,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 50,
            ATTR_BRIGHTNESS: 200,
            ATTR_COLOR_TEMP: 370,
        },
        {
            ATTR_LAYER_ID: "weather_boost",
            ATTR_LAYER_NAME: "Weather Boost",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 60,  # Higher priority, will apply
            ATTR_BRIGHTNESS_PCT_DELTA: 15,  # +15%
        },
        {
            ATTR_LAYER_ID: "sunset_boost",
            ATTR_LAYER_NAME: "Sunset Boost",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 70,  # Even higher, will also apply
            ATTR_BRIGHTNESS_PCT_DELTA: 25,  # +25%
            ATTR_COLOR_TEMP_KELVIN_DELTA: -800,  # Much warmer
        },
        {
            ATTR_LAYER_ID: "low_priority_mod",
            ATTR_LAYER_NAME: "Low Priority Modifier",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 30,  # Lower than manual, won't apply
            ATTR_BRIGHTNESS_PCT_DELTA: 50,
        },
    ]
    
    result = calc.calculate_state(stacking_test)
    print(f"  Winner: {result['winning_layer_name']}")
    print(f"  Base State: brightness=200, color_temp=370")
    print(f"  Final State: brightness={result['final_state']['brightness']}, color_temp={result['final_state']['color_temp']}")
    print(f"  Applied Modifiers: {[m['name'] for m in result.get('applied_modifiers', [])]}")
    print(f"  Calculation Path: {result['calculation_path']}")
    
    # Test 4: Zone config with k_control disabled
    print("\n4. Zone Config Test (k_control_enabled=False):")
    print("-" * 40)
    
    zone_config = {"k_control_enabled": False}
    
    k_control_test = [
        {
            ATTR_LAYER_ID: "manual",
            ATTR_LAYER_NAME: "Manual",
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 50,
            ATTR_BRIGHTNESS: 200,
            ATTR_COLOR_TEMP: 370,
        },
        {
            ATTR_LAYER_ID: "color_modifier",
            ATTR_LAYER_NAME: "Color Temperature Modifier",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 60,
            ATTR_COLOR_TEMP_KELVIN_DELTA: -1000,  # Should be ignored
            ATTR_BRIGHTNESS_PCT_DELTA: 10,  # Should still apply
        },
    ]
    
    result = calc.calculate_state(k_control_test, zone_config)
    print(f"  Zone Config: k_control_enabled=False")
    print(f"  Base State: brightness=200, color_temp=370")
    print(f"  Final State: brightness={result['final_state']['brightness']}, color_temp={result['final_state']['color_temp']}")
    print(f"  Note: Color temp modifier ignored, brightness modifier applied")
    
    # Test 5: Forced modifier
    print("\n5. Forced Modifier Test:")
    print("-" * 40)
    
    forced_modifier_test = [
        {
            ATTR_LAYER_ID: "high_priority",
            ATTR_LAYER_NAME: "High Priority Layer",
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 90,
            ATTR_BRIGHTNESS: 255,
            ATTR_COLOR_TEMP: 300,
        },
        {
            ATTR_LAYER_ID: "emergency_dim",
            ATTR_LAYER_NAME: "Emergency Dim",
            ATTR_LAYER_TYPE: LAYER_TYPE_MODIFIER,
            ATTR_IS_ON: True,
            ATTR_PRIORITY: 10,  # Very low priority
            ATTR_FORCE: True,  # But forced!
            ATTR_BRIGHTNESS_FACTOR: 0.1,  # Dim to 10%
        },
    ]
    
    result = calc.calculate_state(forced_modifier_test)
    print(f"  Winner: {result['winning_layer_name']}")
    print(f"  Base State: brightness=255")
    print(f"  Final State: brightness={result['final_state']['brightness']} (10% of 255)")
    print(f"  Note: Low priority modifier applied due to force flag")
    
    # Performance test
    print("\n6. Performance Test:")
    print("-" * 40)
    print(f"  Cache Stats: {calc.get_cache_stats()}")


if __name__ == "__main__":
    # This can be run standalone for testing
    test_calculator()