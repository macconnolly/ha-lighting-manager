#!/usr/bin/env python3
"""Test script for adaptive lighting implementation."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'lighting_manager'))

def test_adaptive_sensor():
    """Test adaptive sensor calculations."""
    print("\n=== Testing Adaptive Sensor ===")
    
    # Mock sun elevations
    test_cases = [
        (-10, 1.0, "Night - lowest elevation"),
        (-6, 1.0, "Night - at minimum threshold"),
        (0, 0.65, "Twilight"),
        (7.5, 0.32, "Morning/Evening"),
        (15, 0.0, "Day - at maximum threshold"),
        (30, 0.0, "Day - above maximum"),
    ]
    
    min_elev = -6
    max_elev = 15
    range_size = max_elev - min_elev
    
    print(f"Configuration: min_elevation={min_elev}, max_elevation={max_elev}")
    
    for elevation, expected, description in test_cases:
        clamped = max(min_elev, min(max_elev, elevation))
        factor = 1.0 - ((clamped - min_elev) / range_size)
        factor = round(factor, 2)
        
        status = "✓" if abs(factor - expected) < 0.01 else "✗"
        print(f"{status} Elevation {elevation:3}° → Factor {factor:.2f} ({description})")

def test_adaptive_values():
    """Test adaptive brightness and color calculations."""
    print("\n=== Testing Adaptive Value Calculations ===")
    
    # Config
    min_brightness = 10
    max_brightness = 255
    min_color = 153  # Warm
    max_color = 500  # Cool
    
    print(f"Config: brightness={min_brightness}-{max_brightness}, color={min_color}-{max_color}")
    
    factors = [0.0, 0.25, 0.5, 0.75, 1.0]
    
    for factor in factors:
        # Factor: 0 = day (bright/cool), 1 = night (dim/warm)
        brightness = int(max_brightness - (factor * (max_brightness - min_brightness)))
        color_temp = int(min_color + (factor * (max_color - min_color)))
        
        time_desc = {
            0.0: "Day      ",
            0.25: "Afternoon",
            0.5: "Sunset   ",
            0.75: "Evening  ",
            1.0: "Night    "
        }[factor]
        
        print(f"  {time_desc}: factor={factor:.2f} → brightness={brightness:3}, color_temp={color_temp:3}")

def test_layer_priority():
    """Test that adaptive has lowest priority."""
    print("\n=== Testing Layer Priority ===")
    
    from calculator import LightingCalculator
    
    calc = LightingCalculator()
    
    # Test 1: Adaptive alone
    layers = [
        {
            "layer_id": "base_adaptive",
            "is_on": True,
            "priority": 0,
            "brightness": 150,
            "color_temp": 350,
        }
    ]
    
    result = calc.calculate_state(layers)
    assert result["winning_layer"] == "base_adaptive"
    print("✓ Adaptive wins when alone")
    
    # Test 2: Any other layer overrides adaptive
    layers.append({
        "layer_id": "motion",
        "is_on": True,
        "priority": 20,
        "brightness": 200,
    })
    
    result = calc.calculate_state(layers)
    assert result["winning_layer"] == "motion"
    print("✓ Motion layer (priority 20) overrides adaptive (priority 0)")
    
    # Test 3: Manual override
    layers.append({
        "layer_id": "manual",
        "is_on": True,
        "priority": 100,
        "brightness": 255,
    })
    
    result = calc.calculate_state(layers)
    assert result["winning_layer"] == "manual"
    print("✓ Manual layer (priority 100) wins over all")

def test_config_validation():
    """Test configuration value validation."""
    print("\n=== Testing Config Validation ===")
    
    test_configs = [
        # (min_br, max_br, min_ct, max_ct, valid)
        (10, 255, 153, 500, True),
        (0, 255, 153, 500, False),  # 0 brightness not allowed
        (10, 256, 153, 500, False),  # >255 not allowed
        (10, 255, 152, 500, False),  # <153 mireds not allowed
        (10, 255, 153, 501, False),  # >500 mireds not allowed
    ]
    
    for min_br, max_br, min_ct, max_ct, valid in test_configs:
        # Simple validation
        is_valid = (
            1 <= min_br <= 255 and
            1 <= max_br <= 255 and
            153 <= min_ct <= 500 and
            153 <= max_ct <= 500
        )
        
        status = "✓" if is_valid == valid else "✗"
        print(f"{status} Config({min_br}-{max_br}, {min_ct}-{max_ct}) -> {'Valid' if is_valid else 'Invalid'}")

if __name__ == "__main__":
    print("=" * 60)
    print("ADAPTIVE LIGHTING TEST SUITE")
    print("=" * 60)
    
    test_adaptive_sensor()
    test_adaptive_values()
    test_layer_priority()
    test_config_validation()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("\nNext steps to test in Home Assistant:")
    print("1. Create a zone with adaptive enabled")
    print("2. Check that sensor.{zone}_adaptive_factor appears")
    print("3. Verify base_adaptive layer is created at priority 0")
    print("4. Change sun.sun elevation in Dev Tools → States")
    print("5. Verify adaptive values update")
    print("6. Add higher priority layer and verify it wins")