# Modifier Layers Guide

## Overview

Modifier layers are a revolutionary feature in Lighting Manager v5.0 that apply relative adjustments to lighting instead of absolute values. This solves the configuration duplication problem and enables dynamic, context-aware lighting control.

## The Problem They Solve

### Traditional Approach (Absolute Layers)
```yaml
# You need separate configurations for EVERY zone
- zone: living_room
  cloudy_brightness: 200
  cloudy_color: 3000K
  
- zone: kitchen
  cloudy_brightness: 180
  cloudy_color: 3200K
  
- zone: bedroom
  cloudy_brightness: 150
  cloudy_color: 2800K
# ... repeat for all zones
```

### Modifier Approach
```yaml
# ONE modifier works across ALL zones
- layer_type: modifier
  brightness_pct_delta: +20  # Boost by 20%
  color_temp_kelvin_delta: -300  # Warmer by 300K
# Applied to any zone, respects base values
```

## Types of Modifiers

### 1. Percentage Delta (`brightness_pct_delta`)
Adds or subtracts a percentage of current brightness:
- Range: -100 to +100
- Example: `+20` increases brightness by 20%
- Formula: `new = current * (1 + delta/100)`

### 2. Absolute Delta (`color_temp_kelvin_delta`)
Adds or subtracts a fixed amount:
- Range: -5000 to +5000 Kelvin
- Example: `-300` makes light 300K warmer
- Formula: `new = current + delta`

### 3. Multiplier Factor (`brightness_factor`)
Multiplies current value:
- Range: 0.0 to 2.0
- Example: `0.5` halves brightness
- Formula: `new = current * factor`

## How Modifiers Stack

Multiple modifiers combine in priority order:

```
Base Layer (Priority 50): brightness=100
├── Weather Modifier (Priority 70): +20% brightness
├── Motion Modifier (Priority 75): +15% brightness
└── Manual Override (Priority 80): -10% brightness

Final Result: 100 * 1.20 * 1.15 * 0.90 = 124
```

## Common Use Cases

### Weather-Based Adjustments
```yaml
service: lighting_manager.set_layer
data:
  zone_id: "{{ zone }}"
  layer_id: weather_boost
  layer_type: modifier
  priority: 70
  brightness_pct_delta: 20    # Brighter when cloudy
  color_temp_kelvin_delta: -200  # Warmer for comfort
  timeout_minutes: 60  # Re-evaluate hourly
```

### Time-Based Circadian Rhythm
```yaml
# Morning boost
brightness_pct_delta: 10
color_temp_kelvin_delta: 300  # Cooler to wake up

# Evening wind-down
brightness_pct_delta: -30
color_temp_kelvin_delta: -500  # Warmer to relax
```

### Activity Modes
```yaml
# Cooking mode
brightness_pct_delta: 25  # More light for tasks
color_temp_kelvin_delta: 200  # Cooler for clarity

# Movie mode
brightness_pct_delta: -60  # Dim for viewing
color_temp_kelvin_delta: -400  # Warm ambiance
```

### Motion Detection
```yaml
# Temporary boost when motion detected
brightness_pct_delta: 15
timeout_minutes: 5  # Auto-expires
```

## Auto-Expiration

Modifiers can automatically expire using `timeout_minutes`:

```yaml
service: lighting_manager.set_layer
data:
  zone_id: kitchen
  layer_id: cooking_boost
  layer_type: modifier
  brightness_pct_delta: 30
  timeout_minutes: 30  # Expires after 30 minutes
```

The coordinator automatically cleans up expired layers.

## Priority Ranges

Zones can limit modifier priorities to prevent interference:

```yaml
# Zone configuration
modifier_priority_min: 40
modifier_priority_max: 80

# This modifier would be ignored:
priority: 85  # Outside allowed range
```

## Best Practices

### 1. Use Appropriate Priorities
- 40-60: Background adjustments (circadian, weather)
- 60-75: Active responses (motion, activity)
- 75-85: User overrides (manual boost)

### 2. Set Reasonable Timeouts
- Weather: 30-60 minutes
- Motion: 3-10 minutes
- Activity: No timeout (persistent)
- Manual: 15-120 minutes

### 3. Avoid Extreme Values
- Brightness delta: ±50% maximum
- Color temp delta: ±1000K maximum
- Multiple small modifiers > one large modifier

### 4. Test Combinations
Modifiers stack, so test with multiple active:
- Weather + Motion + Activity
- Circadian + Manual Override
- All modifiers at min/max values

## Implementation Example

### Complete Weather Response System
```yaml
automation:
  - alias: "Smart Weather Response"
    trigger:
      - platform: state
        entity_id: weather.home
    
    action:
      - variables:
          conditions:
            sunny: {brightness: 0, warmth: 0}
            cloudy: {brightness: 15, warmth: -200}
            rainy: {brightness: 20, warmth: -300}
            stormy: {brightness: 30, warmth: -100}
      
      - repeat:
          for_each: "{{ states.sensor.lighting_manager_zones.attributes.zone_ids }}"
          sequence:
            - service: lighting_manager.set_layer
              data:
                zone_id: "{{ repeat.item }}"
                layer_id: weather
                layer_type: modifier
                priority: 65
                brightness_pct_delta: "{{ conditions[states('weather.home')].brightness }}"
                color_temp_kelvin_delta: "{{ conditions[states('weather.home')].warmth }}"
                timeout_minutes: 45
```

## Debugging Modifiers

### Check Applied Modifiers
Look at sensor attributes:
```yaml
sensor.living_room_status
  applied_modifiers:
    - weather_boost: +20% brightness
    - circadian: -300K color temp
    - motion: +10% brightness
```

### View Calculation Path
```yaml
sensor.living_room_status
  calculation_path:
    - step: "base_layer_selected"
      layer: "adaptive"
      brightness: 100
    - step: "modifier_applied"
      modifier: "weather_boost"
      brightness_before: 100
      brightness_after: 120
```

### Force Recalculation
```yaml
service: lighting_manager.recalculate_zone
data:
  zone_id: living_room
```

## Advanced Techniques

### Conditional Modifiers
```yaml
# Only apply if someone is home
condition:
  - condition: state
    entity_id: sensor.home_presence
    state: somebody
```

### Gradual Transitions
```yaml
# Slow fade for natural feel
transition: 60  # 1-minute transition
```

### Zone-Specific Modifiers
```yaml
# Only apply to certain zones
{% if 'bedroom' not in zone_id %}
  brightness_pct_delta: 20
{% endif %}
```

### Modifier Chaining
```yaml
# Create complementary modifiers
- Weather Base (priority 60): General adjustment
- Weather Extreme (priority 70): Additional boost for severe weather
- Weather Safety (priority 80): Maximum brightness for storms
```

## Migration from Absolute Patterns

### Before (Absolute)
```yaml
# 10 zones × 5 weather states = 50 configurations
living_room_sunny: {brightness: 180, color: 4000}
living_room_cloudy: {brightness: 220, color: 3500}
living_room_rainy: {brightness: 240, color: 3000}
kitchen_sunny: {brightness: 160, color: 4200}
kitchen_cloudy: {brightness: 200, color: 3700}
# ... 45 more configurations
```

### After (Modifiers)
```yaml
# 1 modifier for all zones and states
weather_modifier:
  sunny: {delta: 0}
  cloudy: {delta: +20}
  rainy: {delta: +30}
# Each zone keeps its base characteristics
```

## Troubleshooting

### Modifier Not Applied
- Check priority is within zone's allowed range
- Verify base layer is active (modifiers need something to modify)
- Confirm modifier layer is turned on
- Check for expiration

### Unexpected Results
- Multiple modifiers may be stacking
- Check calculation order (priority)
- Verify percentage vs absolute deltas
- Look for forced layers overriding

### Performance Issues
- Limit active modifiers to ~10 per zone
- Use longer transitions for smooth changes
- Increase debounce time if needed
- Check for automation loops