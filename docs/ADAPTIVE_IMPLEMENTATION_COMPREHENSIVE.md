# Comprehensive Adaptive Lighting Implementation Plan

## Overview
Integrate adaptive lighting INTO our layer system (not parallel to it) while maintaining architectural purity and avoiding breaking changes.

## Core Design Decisions

### 1. Adaptive as System-Managed Layer
- **Decision**: Create a `base_adaptive` layer automatically at priority 0
- **Rationale**: Keeps everything within our layer system
- **Impact**: No changes to calculator or controller logic needed

### 2. Offset Support Strategy
- **Decision**: Phase 2 feature - NOT required for basic adaptive
- **Rationale**: Can add value later without breaking existing functionality
- **Alternative**: Layers can still use absolute values overlaying adaptive

### 3. Zone-Specific Configuration
- **Decision**: Store adaptive settings in config_entry.options
- **Rationale**: Allows per-zone customization
- **Storage**: Reuse existing config flow infrastructure

## Dependency Analysis

### What Already Works (Don't Break!)
1. ✅ Layer priority system
2. ✅ Calculator logic (pure functional)
3. ✅ Switch entities
4. ✅ Service calls
5. ✅ Storage persistence
6. ✅ Event system
7. ✅ Sensors (2 per zone)

### New Components Needed
1. 🔴 AdaptiveLightFactorSensor entity
2. 🔴 Adaptive tracking in coordinator
3. 🔴 Config options for adaptive
4. 🔴 Auto-management of base_adaptive layer

### Files to Modify (Carefully!)
1. `__init__.py` - Register adaptive sensor platform
2. `coordinator.py` - Add adaptive tracking
3. `config_flow.py` - Add adaptive options
4. `translations/en.json` - Add UI strings
5. `const.py` - Add adaptive constants

### Files NOT to Modify (Working Fine!)
1. ❌ `calculator.py` - Keep pure functional
2. ❌ `switch.py` - No changes needed
3. ❌ `light_control.py` - No changes needed
4. ❌ `services.py` - No changes needed (initially)
5. ❌ `sensor.py` - Existing sensors unchanged

## Implementation Steps (In Order!)

### Phase 1: Basic Adaptive (MVP)

#### Step 1.1: Add Constants
**File**: `const.py`
```python
# Adaptive lighting
ATTR_ADAPTIVE_FACTOR = "adaptive_factor"
ATTR_ADAPTIVE_SOURCE = "adaptive_source"
CONF_ADAPTIVE_ENABLED = "adaptive_enabled"
CONF_ADAPTIVE_BRIGHTNESS_MIN = "adaptive_brightness_min"
CONF_ADAPTIVE_BRIGHTNESS_MAX = "adaptive_brightness_max"
CONF_ADAPTIVE_COLOR_TEMP_MIN = "adaptive_color_temp_min"
CONF_ADAPTIVE_COLOR_TEMP_MAX = "adaptive_color_temp_max"
CONF_ADAPTIVE_ELEVATION_MIN = "adaptive_elevation_min"
CONF_ADAPTIVE_ELEVATION_MAX = "adaptive_elevation_max"
CONF_ADAPTIVE_BRIGHTNESS_ENTITY = "adaptive_brightness_entity"

# Layer IDs
LAYER_BASE_ADAPTIVE = "base_adaptive"
```

#### Step 1.2: Update Config Flow
**File**: `config_flow.py`
```python
# Add to OPTIONS_SCHEMA (don't break existing!)
vol.Optional(CONF_ADAPTIVE_ENABLED, default=False): bool,
vol.Optional(CONF_ADAPTIVE_BRIGHTNESS_MIN, default=10): vol.All(
    vol.Coerce(int), vol.Range(min=1, max=255)
),
vol.Optional(CONF_ADAPTIVE_BRIGHTNESS_MAX, default=255): vol.All(
    vol.Coerce(int), vol.Range(min=1, max=255)
),
vol.Optional(CONF_ADAPTIVE_COLOR_TEMP_MIN, default=153): vol.All(
    vol.Coerce(int), vol.Range(min=153, max=500)
),
vol.Optional(CONF_ADAPTIVE_COLOR_TEMP_MAX, default=500): vol.All(
    vol.Coerce(int), vol.Range(min=153, max=500)
),
vol.Optional(CONF_ADAPTIVE_ELEVATION_MIN, default=-6): vol.All(
    vol.Coerce(int), vol.Range(min=-90, max=90)
),
vol.Optional(CONF_ADAPTIVE_ELEVATION_MAX, default=15): vol.All(
    vol.Coerce(int), vol.Range(min=-90, max=90)
),
```

#### Step 1.3: Add Translations
**File**: `translations/en.json`
```json
"options": {
  "step": {
    "init": {
      "data": {
        "adaptive_enabled": "Enable adaptive lighting",
        "adaptive_brightness_min": "Minimum brightness (night)",
        "adaptive_brightness_max": "Maximum brightness (day)",
        "adaptive_color_temp_min": "Minimum color temperature (warm)",
        "adaptive_color_temp_max": "Maximum color temperature (cool)",
        "adaptive_elevation_min": "Sun elevation for night mode",
        "adaptive_elevation_max": "Sun elevation for day mode"
      }
    }
  }
}
```

#### Step 1.4: Create Adaptive Sensor
**File**: `adaptive_sensor.py` (NEW)
- Already created above ✅
- Tracks sun.sun or custom entity
- Calculates 0-1 factor
- Updates on state changes

#### Step 1.5: Register Sensor Platform
**File**: `__init__.py`
```python
# In async_setup_entry, add:
await hass.config_entries.async_forward_entry_setups(
    config_entry, 
    ["switch", "sensor", "adaptive_sensor"]  # Add adaptive_sensor
)
```

#### Step 1.6: Update Coordinator
**File**: `coordinator.py`
```python
class ZoneCoordinator:
    def __init__(self, ...):
        # ... existing ...
        self._adaptive_enabled = False
        self._adaptive_factor = 0.5
        self._adaptive_listener = None
        
    async def async_setup(self):
        """Set up coordinator."""
        await super().async_setup()
        
        # Check if adaptive is enabled
        self._adaptive_enabled = self._config_entry.options.get(
            CONF_ADAPTIVE_ENABLED, False
        )
        
        if self._adaptive_enabled:
            await self._setup_adaptive()
    
    async def _setup_adaptive(self):
        """Set up adaptive lighting integration."""
        # Wait for sensor to be created
        await asyncio.sleep(1)  # Give sensor time to register
        
        # Track adaptive factor sensor
        sensor_id = f"sensor.{self.zone_id}_adaptive_factor"
        
        @callback
        def on_adaptive_change(event):
            """Handle adaptive factor changes."""
            new_state = event.data.get("new_state")
            if new_state and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._adaptive_factor = float(new_state.state)
                    self.hass.async_create_task(self._update_adaptive_layer())
                except ValueError:
                    pass
        
        self._adaptive_listener = async_track_state_change_event(
            self.hass, sensor_id, on_adaptive_change
        )
        self.async_on_remove(self._adaptive_listener)
        
        # Initialize adaptive layer
        await self._update_adaptive_layer()
    
    async def _update_adaptive_layer(self):
        """Update the base_adaptive layer with current values."""
        if not self._adaptive_enabled:
            return
            
        # Get config values
        options = self._config_entry.options
        min_brightness = options.get(CONF_ADAPTIVE_BRIGHTNESS_MIN, 10)
        max_brightness = options.get(CONF_ADAPTIVE_BRIGHTNESS_MAX, 255)
        min_color = options.get(CONF_ADAPTIVE_COLOR_TEMP_MIN, 153)
        max_color = options.get(CONF_ADAPTIVE_COLOR_TEMP_MAX, 500)
        
        # Calculate actual values based on factor
        # Factor: 0 = day (bright/cool), 1 = night (dim/warm)
        brightness = int(
            max_brightness - (self._adaptive_factor * (max_brightness - min_brightness))
        )
        color_temp = int(
            min_color + (self._adaptive_factor * (max_color - min_color))
        )
        
        # Update or create base_adaptive layer
        now = get_timezone_aware_now()
        
        if LAYER_BASE_ADAPTIVE not in self.layers:
            self.layers[LAYER_BASE_ADAPTIVE] = {
                ATTR_LAYER_NAME: "Adaptive Baseline",
                ATTR_IS_ON: True,
                ATTR_PRIORITY: 0,  # Lowest priority
                ATTR_BRIGHTNESS: brightness,
                ATTR_COLOR_TEMP: color_temp,
                ATTR_TRANSITION: DEFAULT_TRANSITION,
                ATTR_LOCKED: True,  # System-managed
                ATTR_SOURCE: "system",
                ATTR_CREATED_AT: now,
                ATTR_LAST_MODIFIED: now,
                "adaptive_factor": self._adaptive_factor,
            }
        else:
            self.layers[LAYER_BASE_ADAPTIVE].update({
                ATTR_BRIGHTNESS: brightness,
                ATTR_COLOR_TEMP: color_temp,
                ATTR_LAST_MODIFIED: now,
                "adaptive_factor": self._adaptive_factor,
            })
        
        # Save and trigger update
        await self._save_layers()
        await self._trigger_update()
```

## Testing Plan

### Unit Tests
1. Test AdaptiveLightFactorSensor calculations
2. Test coordinator adaptive layer updates
3. Test config flow with new options

### Integration Tests
1. Enable adaptive in config
2. Verify sensor creation
3. Mock sun.sun changes
4. Verify base_adaptive layer updates
5. Verify priority system still works
6. Test with adaptive disabled

### Manual Testing Checklist
- [ ] Create new zone without adaptive
- [ ] Create new zone with adaptive
- [ ] Verify sensor appears in UI
- [ ] Change sun elevation (dev tools)
- [ ] Verify base_adaptive updates
- [ ] Verify lights respond
- [ ] Add higher priority layer
- [ ] Verify priority override works
- [ ] Disable adaptive in options
- [ ] Verify sensor removed
- [ ] Verify base_adaptive deactivated

## Rollback Plan

If issues arise:
1. Set `adaptive_enabled: false` in options
2. Remove `adaptive_sensor.py` file
3. Revert `__init__.py` platform registration
4. Coordinator will ignore adaptive code path

## Phase 2: Offset Support (Future)

### Why Defer?
- Not required for MVP
- Needs calculator changes (risk)
- Can overlay absolute values for now
- User can achieve same effect with automations

### When to Implement?
- After Phase 1 is stable
- After user feedback
- When we understand use cases better

### Design Preview
```python
# In layers
"movie_mode": {
    "brightness_offset": "-50%",  # 50% dimmer than adaptive
    "color_temp_offset": "+100",  # 100 mireds warmer
}

# Calculator changes needed
def _build_final_state(self, layer, adaptive_baseline):
    # Handle offsets...
```

## Success Criteria

### Phase 1 Complete When:
- [x] Adaptive sensor created and working
- [ ] Base_adaptive layer auto-managed
- [ ] Responds to sun changes
- [ ] Zone-specific ranges work
- [ ] Can be enabled/disabled
- [ ] Doesn't break existing functionality
- [ ] All tests pass

### User Experience:
- [ ] Enable adaptive in zone config
- [ ] See sensor in UI
- [ ] Lights follow sun automatically
- [ ] Can override with manual layer
- [ ] Can disable if not wanted

## Risk Mitigation

### High Risk Areas
1. **Coordinator changes** - Test thoroughly
2. **Storage compatibility** - Ensure backward compatible
3. **Sensor registration** - Handle missing sun.sun

### Low Risk Areas
1. **New sensor file** - Isolated component
2. **Config options** - Already have pattern
3. **Translations** - Just strings

### Safeguards
1. Adaptive is opt-in (disabled by default)
2. Sensor is separate platform
3. base_adaptive at priority 0 (easily overridden)
4. No changes to core calculator logic

## Questions to Resolve

1. **Q**: Should base_adaptive be visible in UI?
   **A**: Yes, but locked (read-only)

2. **Q**: What if sun.sun doesn't exist?
   **A**: Fallback to 0.5 factor, log warning

3. **Q**: Should we fire events for adaptive changes?
   **A**: Yes, use existing EVENT_LAYER_UPDATED

4. **Q**: How often to update adaptive?
   **A**: On every sun change (already debounced by HA)

## Next Steps

1. ✅ Review this plan
2. ⬜ Get approval
3. ⬜ Implement Phase 1 in order
4. ⬜ Test thoroughly
5. ⬜ Document for users
6. ⬜ Consider Phase 2 later