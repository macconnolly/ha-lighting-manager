# Lighting Manager v5 - Setup Guide

## Quick Start

After installing the Lighting Manager integration, the system will automatically:
1. Create base adaptive and manual layers for each zone
2. Wait for system readiness (~40 seconds)
3. Apply a complete set of disabled modifier layers
4. Begin managing your lights based on adaptive calculations

## Required Configuration

### 1. Presence Detection (IMPORTANT)

The system automatically detects presence using:
- All `person.*` entities in your system
- All GPS-based `device_tracker.*` entities

**If you have no person entities configured:**
1. Go to Settings → People
2. Add each household member
3. Associate their device trackers

**Manual Override:**
If you don't use presence detection, toggle `input_boolean.presence_override` to control home/away status manually.

### 2. Weather Integration

**Requirement:** You must have a weather integration configured.

The system looks for `weather.home` by default. If your weather entity has a different name:
1. Install any weather integration (Met.no, OpenWeatherMap, etc.)
2. Ensure it creates a `weather.home` entity
3. Or modify the weather package to use your entity name

### 3. Welcome Home Zones

By default, the Welcome Home feature targets zones with these keywords:
- entry
- hall
- foyer
- porch

**To customize:**
1. Go to Settings → Helpers
2. Find "Welcome Home Zones"
3. Enter comma-separated zone IDs (e.g., "living_room,kitchen")

## Optional Configuration

### Activity Modes

Activities work out of the box. Simply select from the dropdown:
- Default (adaptive only)
- Movie (-60% brightness, warm)
- Reading (+20% brightness, cool)
- Work (+30% brightness, daylight)
- Gaming (-20% brightness, cool)
- Relaxing (-30% brightness, warm)
- Sleep (-70% brightness, very warm)
- Party (+40% brightness, neutral)
- Romantic (-50% brightness, candlelight)

### Weather Modifiers

Enable/disable with `input_boolean.weather_modifiers_enabled`

Automatic adjustments:
- Cloudy: +15% brightness
- Rainy: +25% brightness
- Snowy: +30% brightness
- Storm: +40% brightness (always active for safety)
- Fog: +20% brightness, warmer tone

### Presence Features

**Away Mode:** `input_boolean.presence_modifiers_enabled`
- Automatically dims lights to 30% when everyone leaves
- Restores normal lighting when someone returns

**Vacation Mode:** `input_boolean.vacation_mode`
- Simulates presence with random lighting changes
- Varies brightness between 60-90% of normal
- Changes every 45 minutes during evening hours

**Welcome Home:** `input_boolean.welcome_home_enabled`
- Brightens entry zones when arriving after dark
- +30% brightness for 5 minutes
- Configure zones via helper or use auto-detection

## Troubleshooting

### Lights Don't React to Presence

Check:
1. `binary_sensor.anyone_home` - Should show if anyone is detected
2. View its `tracked_entities` attribute to see what it's monitoring
3. Ensure you have person entities or GPS trackers configured
4. Use `input_boolean.presence_override` as manual fallback

### Weather Adjustments Not Working

Check:
1. `weather.home` entity exists and has valid state
2. `sensor.weather_lighting_impact` shows appropriate impact level
3. `input_boolean.weather_modifiers_enabled` is on

### Activities Not Changing Lights

Check:
1. `input_boolean.lighting_manager_ready` is on
2. Select different activity in `input_select.lighting_mode`
3. Verify zone has power and is responsive

### Manual Changes Being Overridden

This is normal! The system detects manual changes and creates a 2-hour override automatically. Your manual adjustments are respected.

## Advanced Customization

### Creating Custom Modifiers

Any automation can create modifiers using the service:

```yaml
service: lighting_manager.set_layer
data:
  zone_id: living_room
  layer_id: modifier_custom_party
  layer_name: "Custom: Party Time"
  layer_type: modifier
  priority: 65  # See priority guide below
  is_on: true
  brightness_pct_delta: 50  # +50% brightness
  color_temp_kelvin_delta: 200  # Cooler white
  transition: 2
```

### Priority Guide

- 90-99: Manual/Guest Overrides (highest)
- 80-89: Safety (storms, emergencies)
- 70-79: Critical Modes (sleep, away)
- 60-69: Focused Activities (movie, work)
- 50-59: General Modifiers (weather, presence)
- 40-49: Ambient Comfort (circadian, climate)

### Missing Features from v4

These features were removed for architectural purity but can be re-added:

**Motion-Based Lighting:**
Create your own automation using the pre-created layers:
- `modifier_motion_detected` - General motion boost
- `modifier_motion_pathway` - Dim pathway lighting

**Circadian Rhythms:**
The adaptive system handles sun position. For explicit time-based control:
- `modifier_circadian_morning` - Morning energy boost
- `modifier_circadian_evening` - Evening wind-down
- `modifier_circadian_bedtime` - Sleep preparation

**Climate Integration:**
Layers exist but need automations:
- `modifier_climate_heating` - Warmer when heating
- `modifier_climate_cooling` - Cooler when AC running

## System Architecture

The Lighting Manager uses a layered priority system:
1. **Base Layer:** Adaptive lighting based on sun position (always on)
2. **Modifier Layers:** Percentage adjustments (weather, activities, presence)
3. **Manual Overrides:** Direct control (highest priority, 2-hour timeout)

Each zone operates independently with its own set of layers.

## Need Help?

- Check the diagnostic sensor: `sensor.[zone]_zone_diagnostics`
- Review logs: Settings → System → Logs (filter by "lighting_manager")
- File issues: [GitHub Issues](https://github.com/your-repo/issues)