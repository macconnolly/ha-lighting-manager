# Adaptive Lighting Discovery Report

## Original Package Architecture

After analyzing the original `ha-lighting-manager` package, here's how adaptive lighting ACTUALLY works:

### Key Components

1. **AdaptiveLightFactorSensor** (`sensor.py`)
   - Creates `sensor.adaptive_lighting_factor` entity
   - Tracks `sun.sun` elevation
   - Calculates factor 0.0-1.0 (lower sun = higher factor)
   - Formula: `1.0 - (elevation / max_elevation)`

2. **Configuration** (`__init__.py`)
   - Global adaptive config with min/max color temp and brightness
   - Per-entity overrides for individual lights
   - Optional `brightness_entity_id` for non-sun-based brightness

3. **Services**
   - `add_adaptive`: Enable adaptive for specific lights
   - `remove_adaptive`: Disable adaptive for lights

### Critical Architectural Difference

**Original Package:**
- Adaptive is SEPARATE from layers
- Direct light control via `async_reproduce_state`
- Bypasses the layer system entirely
- Applied as a continuous background process

**Our Current Implementation:**
- NO adaptive implementation exists
- Config UI collects settings but never uses them
- References to "base_adaptive" layer but never creates it
- Would need to integrate WITH layer system

## How Original Adaptive Works

```python
# 1. Sensor calculates factor based on sun
sensor.adaptive_lighting_factor = 0.8  # (sun is low)

# 2. Service applies to light directly
async def update_adaptive(entities):
    factor = hass.states.get("sensor.adaptive_lighting_factor").state
    
    # Calculate actual values
    color_temp = ((max_ct - min_ct) * factor) + min_ct
    brightness = ((max_br - min_br) * factor) + min_br
    
    # Apply directly to light
    await async_reproduce_state(light_entity, {
        "color_temp": color_temp,
        "brightness": brightness
    })
```

## Our Architecture Challenge

We need adaptive to work WITH our layer system, not bypass it:

### Option 1: Adaptive as Base Layer
```python
# Auto-create/update base_adaptive layer
layers["base_adaptive"] = {
    "priority": 0,
    "brightness": adaptive_brightness,  # Calculated from sun
    "color_temp": adaptive_color_temp,
    "is_on": True  # Always on as baseline
}
```

### Option 2: Adaptive as Calculator Input
```python
# Pass adaptive values to calculator
result = calculator.calculate_state(
    layers=active_layers,
    adaptive_baseline={
        "brightness": 150,
        "color_temp": 350
    }
)

# Calculator applies offsets
if layer.get("brightness_offset"):
    brightness = adaptive_baseline["brightness"] + offset
```

## What's Missing in Current Implementation

1. **No Sensor Entity**
   - Need to create `AdaptiveLightFactorSensor`
   - Track sun elevation
   - Calculate 0-1 factor

2. **No Adaptive Calculation**
   - Config stores min/max but never uses them
   - No code to calculate brightness/color from factor
   - No periodic updates

3. **No Layer Integration**
   - base_adaptive layer never created
   - No mechanism to update it periodically
   - No offset support in layers

## Implementation Requirements

### Phase 1: Basic Adaptive
1. Create `AdaptiveLightFactorSensor` 
2. Calculate brightness/color from sun position
3. Create/update base_adaptive layer automatically
4. Ensure it has priority 0 (lowest)

### Phase 2: Offset Support
1. Add `brightness_offset` field to layers
2. Add `color_temp_offset` field to layers
3. Modify calculator to handle offsets
4. Support percentage offsets ("-50%")

### Phase 3: Zone-Specific Ranges
1. Store per-zone min/max in config
2. Scale adaptive factor to zone ranges
3. Each zone gets personalized adaptive baseline

## Key Insight

The original package treats adaptive as a PARALLEL system to layers. We need to make it work WITHIN our layer system while maintaining architectural purity. The base_adaptive layer should be automatically managed, not user-controlled.