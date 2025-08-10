# Adaptive Lighting Implementation Plan

## Architectural Decision: Adaptive as Managed Base Layer

After analyzing the original package and our architecture, the cleanest approach is:

**Adaptive creates/updates a `base_adaptive` layer automatically**
- Priority 0 (lowest, provides baseline)
- Managed by the system, not user-controlled
- Updates periodically based on sun position
- Always active when adaptive is enabled

## Implementation Steps

### Step 1: Create Adaptive Factor Sensor
**File:** `custom_components/lighting_manager/adaptive_sensor.py`

```python
class AdaptiveLightFactorSensor(SensorEntity):
    """Sensor that tracks sun elevation and calculates adaptive factor."""
    
    def __init__(self, zone_id: str):
        self._zone_id = zone_id
        self._factor = 0.0
        
    @property
    def unique_id(self):
        return f"{self._zone_id}_adaptive_factor"
    
    @property
    def name(self):
        return f"{self._zone_id.title()} Adaptive Factor"
        
    @property
    def native_value(self):
        return self._factor  # 0.0 to 1.0
        
    async def async_added_to_hass(self):
        """Subscribe to sun.sun changes."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                "sun.sun",
                self._on_sun_change
            )
        )
        
    async def _on_sun_change(self, event):
        """Recalculate factor when sun moves."""
        sun_state = self.hass.states.get("sun.sun")
        if sun_state:
            elevation = sun_state.attributes.get("elevation", 0)
            # Lower elevation = higher factor (more warm/dim)
            self._factor = 1.0 - (max(0, min(elevation, 15)) / 15)
            self.async_write_ha_state()
```

### Step 2: Add Adaptive Manager to Coordinator
**File:** `custom_components/lighting_manager/coordinator.py`

```python
class ZoneCoordinator(DataUpdateCoordinator):
    
    def __init__(self, ...):
        # ... existing init ...
        self._adaptive_enabled = config_entry.options.get("adaptive_enabled", False)
        self._adaptive_sensor = None
        
    async def async_setup(self):
        """Set up coordinator and adaptive sensor."""
        await super().async_setup()
        
        if self._adaptive_enabled:
            # Create adaptive sensor
            self._adaptive_sensor = AdaptiveLightFactorSensor(self.zone_id)
            await self._adaptive_sensor.async_setup()
            
            # Create base_adaptive layer if not exists
            if "base_adaptive" not in self.layers:
                self.layers["base_adaptive"] = {
                    "layer_name": "Adaptive Baseline",
                    "is_on": True,
                    "priority": 0,  # Lowest priority
                    "brightness": 150,
                    "color_temp": 350,
                    "locked": True,  # System-managed
                }
            
            # Track adaptive factor changes
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    f"sensor.{self.zone_id}_adaptive_factor",
                    self._on_adaptive_change
                )
            )
    
    async def _on_adaptive_change(self, event):
        """Update base_adaptive layer when factor changes."""
        factor = float(event.data["new_state"].state)
        
        # Get zone-specific ranges from config
        min_brightness = self._config_entry.options.get("adaptive_brightness_min", 10)
        max_brightness = self._config_entry.options.get("adaptive_brightness_max", 255)
        min_color_temp = self._config_entry.options.get("adaptive_color_temp_min", 153)
        max_color_temp = self._config_entry.options.get("adaptive_color_temp_max", 500)
        
        # Calculate actual values
        brightness = int(((max_brightness - min_brightness) * (1 - factor)) + min_brightness)
        color_temp = int(((max_color_temp - min_color_temp) * factor) + min_color_temp)
        
        # Update base_adaptive layer
        self.layers["base_adaptive"].update({
            "brightness": brightness,
            "color_temp": color_temp,
            "last_update": dt_util.now().isoformat(),
        })
        
        # Trigger recalculation
        await self._trigger_update()
```

### Step 3: Add Offset Support to Layers
**File:** `custom_components/lighting_manager/const.py`

```python
# Add new attributes
ATTR_BRIGHTNESS_OFFSET = "brightness_offset"
ATTR_COLOR_TEMP_OFFSET = "color_temp_offset"
ATTR_OFFSET_MODE = "offset_mode"  # "absolute" or "percentage"
```

### Step 4: Update Calculator for Offsets
**File:** `custom_components/lighting_manager/calculator.py`

```python
def calculate_state(self, layers: list[dict], adaptive_baseline: dict = None):
    """Calculate with offset support."""
    
    # ... existing priority logic ...
    
    # After determining winning layer
    final_state = self._build_final_state(winning_layer, adaptive_baseline)
    
def _build_final_state(self, layer: dict, adaptive_baseline: dict = None):
    """Build state with offset support."""
    
    state = {"power": "on"}
    
    # Handle brightness
    if "brightness_offset" in layer and adaptive_baseline:
        base_brightness = adaptive_baseline.get("brightness", 150)
        offset = layer["brightness_offset"]
        
        if isinstance(offset, str) and offset.endswith("%"):
            # Percentage offset: "-50%" means 50% of baseline
            percent = float(offset.rstrip("%")) / 100
            state["brightness"] = int(base_brightness * (1 + percent))
        else:
            # Absolute offset: +50 or -50
            state["brightness"] = base_brightness + int(offset)
            
        state["brightness"] = max(0, min(255, state["brightness"]))
        
    elif "brightness" in layer:
        # Absolute value (existing behavior)
        state["brightness"] = layer["brightness"]
    
    # Handle color_temp similarly
    if "color_temp_offset" in layer and adaptive_baseline:
        base_color_temp = adaptive_baseline.get("color_temp", 350)
        offset = layer["color_temp_offset"]
        
        if isinstance(offset, str) and offset.endswith("%"):
            percent = float(offset.rstrip("%")) / 100
            state["color_temp"] = int(base_color_temp * (1 + percent))
        else:
            state["color_temp"] = base_color_temp + int(offset)
            
        state["color_temp"] = max(153, min(500, state["color_temp"]))
        
    elif "color_temp" in layer:
        state["color_temp"] = layer["color_temp"]
    
    return state
```

### Step 5: Update Config Flow for Zone-Specific Ranges
**File:** `custom_components/lighting_manager/config_flow.py`

```python
# Add to options schema
vol.Optional("adaptive_enabled", default=False): bool,
vol.Optional("adaptive_brightness_min", default=10): vol.All(
    vol.Coerce(int), vol.Range(min=0, max=255)
),
vol.Optional("adaptive_brightness_max", default=255): vol.All(
    vol.Coerce(int), vol.Range(min=0, max=255)
),
vol.Optional("adaptive_color_temp_min", default=153): vol.All(
    vol.Coerce(int), vol.Range(min=153, max=500)
),
vol.Optional("adaptive_color_temp_max", default=500): vol.All(
    vol.Coerce(int), vol.Range(min=153, max=500)
),
```

### Step 6: Create Service for Layer Templates
**File:** `custom_components/lighting_manager/services.py`

```python
async def apply_layer_template(call: ServiceCall):
    """Apply a layer template to multiple zones."""
    
    template = call.data["template"]
    zones = call.data["zones"]
    
    for zone_id in zones:
        coordinator = hass.data[DOMAIN].get(zone_id)
        if coordinator:
            # Create layer with zone-specific name
            layer_id = call.data.get("layer_id", "template")
            coordinator.layers[layer_id] = {
                **template,
                "layer_id": layer_id,
                "applied_from_template": True,
            }
            
            # If template has offsets, they'll work with zone's adaptive
            await coordinator._trigger_update()
```

## Testing Plan

1. **Test Adaptive Sensor**
   - Mock sun.sun state changes
   - Verify factor calculation (0-1 range)
   - Check sensor attributes

2. **Test Base Layer Updates**
   - Verify base_adaptive created on setup
   - Check updates when factor changes
   - Ensure zone-specific ranges applied

3. **Test Offset Calculations**
   - Test percentage offsets ("-50%")
   - Test absolute offsets (+50, -50)
   - Verify bounds checking (0-255, 153-500)

4. **Test Layer Templates**
   - Apply template to multiple zones
   - Verify offsets work with different baselines
   - Check zone independence

## Migration Notes

For existing users:
1. Adaptive is opt-in via config
2. Existing layers unchanged
3. New offset fields are optional
4. base_adaptive layer auto-created if enabled

## Success Criteria

✅ Sun position drives adaptive baseline
✅ Each zone has personalized ranges  
✅ Layers can use offsets or absolute values
✅ Templates work across zones
✅ Architecture remains pure (no condition evaluation)