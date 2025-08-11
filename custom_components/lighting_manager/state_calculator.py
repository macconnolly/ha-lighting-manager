"""State Calculator - Pure functional calculation with no Home Assistant dependencies."""
# TODO: Delete the old calculator.py file which this file replaces.
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