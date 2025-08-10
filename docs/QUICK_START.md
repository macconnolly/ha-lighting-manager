# Lighting Manager Quick Start Guide

## Installation

### Via HACS
1. Open HACS → Integrations
2. Click menu → Custom repositories
3. Add this repository URL
4. Category: Integration
5. Install "Lighting Manager"
6. Restart Home Assistant

### Manual
1. Copy `custom_components/lighting_manager` to your `custom_components/` folder
2. Restart Home Assistant

## Setting Up Your First Zone

### Step 1: Add Integration
1. Settings → Devices & Services → Add Integration
2. Search for "Lighting Manager"
3. Click to add

### Step 2: Create Zone
Enter:
- **Zone Name**: e.g., "living_room" (will be slugified)
- **Lights**: Select lights for this zone
- **Area**: Optional, link to HA area

### Step 3: Configure (Optional)
Click Configure on the zone to set:
- Brightness ranges (min/max)
- Color temperature ranges
- Modifier priority limits
- Default timeouts

## Basic Usage

### Manual Control
```yaml
# Turn on manual layer
service: switch.turn_on
entity_id: switch.living_room_manual_layer

# Adjust brightness
service: lighting_manager.update_layer
target:
  entity_id: switch.living_room_manual_layer
data:
  brightness: 200
  color_temp: 370
```

### Create a Scene Layer
```yaml
service: lighting_manager.set_layer
data:
  zone_id: living_room
  layer_id: movie
  layer_name: "Movie Time"
  priority: 60
  brightness: 30
  color_temp: 500
  transition: 5
```

### Apply a Modifier
```yaml
# Boost brightness by 20%
service: lighting_manager.set_layer
data:
  zone_id: living_room
  layer_id: boost
  layer_type: modifier
  priority: 70
  brightness_pct_delta: 20
  timeout_minutes: 30  # Auto-expires
```

## Pre-Built Automations

### 1. Weather Response
Include in `configuration.yaml`:
```yaml
homeassistant:
  packages:
    weather: !include packages/lighting_modifier_weather.yaml
```

Features:
- Automatic brightness boost when cloudy
- Storm safety lighting
- Smooth transitions

### 2. Circadian Rhythm
```yaml
homeassistant:
  packages:
    circadian: !include packages/lighting_modifier_circadian.yaml
```

Features:
- Natural color temperature shifts
- Brightness following sun position
- Bedtime wind-down

### 3. Motion Response
```yaml
homeassistant:
  packages:
    motion: !include packages/lighting_modifier_motion.yaml
```

Features:
- Temporary brightness boost
- Path lighting at night
- Occupancy-based dimming

## Your Zone Configuration

Use the provided setup file:
```yaml
homeassistant:
  packages:
    zones: !include examples/zones/setup_zones.yaml
```

This configures your 5 zones:
- `main_living`: 30-100% brightness, 2200-3700K
- `kitchen_island`: 15-100% brightness, 2700-3700K
- `bedroom_primary`: 15-80% brightness, 1800-3700K
- `accent_spots`: 5-60% brightness, 2200-3200K
- `recessed_ceiling`: 2-35% brightness, 1800-5000K

## Understanding Layers

### Layer Types

**Absolute Layers**: Set specific values
```yaml
brightness: 200  # Specific brightness
color_temp: 370  # Specific color
```

**Modifier Layers**: Apply relative changes
```yaml
brightness_pct_delta: +20  # Increase by 20%
color_temp_kelvin_delta: -300  # Warmer by 300K
```

### Priority System
- 0-29: Background/Ambient
- 30-49: Adaptive/Automatic
- 50-69: Manual Control
- 70-89: Overrides/Boosts
- 90-100: Emergency/Safety

Higher priority wins!

## Monitoring

### Key Sensors
- `sensor.{zone}_status`: Overall zone status
- `sensor.{zone}_active_layer`: Current winning layer
- `sensor.{zone}_status`: Zone health and debug details
- `sensor.lighting_manager_zones`: List of all zones

### Dashboard Card Example
```yaml
type: entities
title: Living Room Lighting
entities:
  - entity: sensor.living_room_active_layer
    name: Active Layer
  - entity: switch.living_room_manual_layer
    name: Manual Control
  - entity: switch.living_room_adaptive_layer
    name: Adaptive
  - type: divider
  - entity: sensor.living_room_status
    name: Status
```

## Common Automations

### Turn on at Sunset
```yaml
automation:
  - alias: "Lights on at sunset"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: switch.turn_on
        entity_id: switch.living_room_adaptive_layer
```

### Motion Activated Boost
```yaml
automation:
  - alias: "Motion boost"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_motion
        to: "on"
    action:
      - service: lighting_manager.set_layer
        data:
          zone_id: living_room
          layer_id: motion
          layer_type: modifier
          priority: 75
          brightness_pct_delta: 20
          timeout_minutes: 5
```

### Activity Modes
```yaml
script:
  movie_mode:
    sequence:
      - service: lighting_manager.set_layer
        data:
          zone_id: living_room
          layer_id: activity
          layer_type: modifier
          priority: 65
          brightness_pct_delta: -60
          color_temp_kelvin_delta: -500
```

## Tips & Tricks

### 1. Start Simple
- Begin with manual and adaptive layers
- Add modifiers as needed
- Test each addition

### 2. Use Modifiers for Flexibility
Instead of creating multiple absolute configurations, use modifiers:
- Weather boost: +20% when cloudy
- Evening dim: -30% after sunset
- Activity adjust: varies by activity

### 3. Set Appropriate Timeouts
- Motion: 3-10 minutes
- Weather: 30-60 minutes
- Manual override: 15-120 minutes
- Persistent modes: no timeout

### 4. Monitor Performance
Check calculation times in sensor attributes:
```yaml
sensor.living_room_status
  attributes:
    calculation_time_ms: 12
```

### 5. Debug Issues
Enable debug logging:
```yaml
logger:
  logs:
    custom_components.lighting_manager: debug
```

## Getting Help

1. Check sensor states for current configuration
2. Use Developer Tools → Services to test
3. Review logs for errors
4. Check status sensor for details

## Next Steps

1. **Customize Zones**: Adjust brightness/color ranges
2. **Add Automations**: Create your own modifiers
3. **Build Dashboard**: Create custom UI cards
4. **Share**: Contribute your automations back!