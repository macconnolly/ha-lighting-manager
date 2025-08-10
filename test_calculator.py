#!/usr/bin/env python3
"""Test the calculator to ensure it works after removing condition logic."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'lighting_manager'))

from calculator import LightingCalculator

def test_basic_priority():
    """Test basic priority resolution."""
    calc = LightingCalculator()
    
    layers = [
        {
            "layer_id": "manual",
            "is_on": True,
            "priority": 100,
            "brightness": 255,
            "color_temp": 200,
        },
        {
            "layer_id": "adaptive",
            "is_on": True,
            "priority": 0,
            "brightness": 150,
            "color_temp": 400,
        },
        {
            "layer_id": "motion",
            "is_on": False,  # OFF - should be ignored
            "priority": 50,
            "brightness": 200,
        }
    ]
    
    result = calc.calculate_state(layers)
    
    assert result["winning_layer"] == "manual", f"Expected manual, got {result['winning_layer']}"
    assert result["final_state"]["brightness"] == 255
    assert result["final_state"]["color_temp"] == 200
    print("✓ Basic priority test passed")

def test_no_active_layers():
    """Test when no layers are active."""
    calc = LightingCalculator()
    
    layers = [
        {
            "layer_id": "manual",
            "is_on": False,
            "priority": 100,
        },
        {
            "layer_id": "adaptive",
            "is_on": False,
            "priority": 0,
        }
    ]
    
    result = calc.calculate_state(layers)
    
    assert result["winning_layer"] is None
    assert result["final_state"]["power"] == "off"
    print("✓ No active layers test passed")

def test_force_flag():
    """Test force flag override."""
    calc = LightingCalculator()
    
    layers = [
        {
            "layer_id": "high_priority",
            "is_on": True,
            "priority": 100,
            "brightness": 255,
        },
        {
            "layer_id": "forced_low",
            "is_on": True,
            "priority": 10,
            "force": True,  # Force flag should make this win
            "brightness": 100,
        }
    ]
    
    result = calc.calculate_state(layers)
    
    assert result["winning_layer"] == "forced_low", f"Expected forced_low, got {result['winning_layer']}"
    assert result["final_state"]["brightness"] == 100
    print("✓ Force flag test passed")

def test_only_active_layers_considered():
    """Test that only is_on=True layers are considered."""
    calc = LightingCalculator()
    
    layers = [
        {
            "layer_id": "off_high_priority",
            "is_on": False,  # OFF - should be ignored even with high priority
            "priority": 100,
            "brightness": 255,
        },
        {
            "layer_id": "on_low_priority",
            "is_on": True,  # ON - should win despite low priority
            "priority": 10,
            "brightness": 100,
        }
    ]
    
    result = calc.calculate_state(layers)
    
    assert result["winning_layer"] == "on_low_priority"
    assert result["final_state"]["brightness"] == 100
    print("✓ Only active layers considered test passed")

if __name__ == "__main__":
    print("Testing Calculator (Pure External Approach)...")
    print("=" * 50)
    
    test_basic_priority()
    test_no_active_layers()
    test_force_flag()
    test_only_active_layers_considered()
    
    print("=" * 50)
    print("✅ All tests passed! Calculator works correctly.")
    print("\nThe package now follows the Pure External Approach:")
    print("- Only considers layers where is_on=True")
    print("- No condition evaluation in the package")
    print("- External automations handle all smart logic")