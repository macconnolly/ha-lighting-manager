# Architecture Update: Switches as Layers

## Major Architecture Change

Based on modern Home Assistant development practices (2024/2025), we're updating the architecture:

### ❌ OLD: Custom `layer.` entity platform
```python
layer.living_room_movie  # NOT SUPPORTED IN HA
```

### ✅ NEW: Switch platform for layers
```python
switch.living_room_movie_layer
  state: on/off  # Layer active/inactive
  attributes:
    zone: "living_room"
    priority: 50
    brightness: 30
    color_temp: 500
    rgb_color: [255, 200, 100]
    transition: 2.0
    force: false
    locked: false
    source: "scene.movie_time"
    last_updated: "2024-01-15T20:30:00Z"
    # Any other arbitrary attributes via extra_attributes
```

## Why Switches?

1. **Semantic Clarity**: Layers are things you "switch on/off" to control lighting
2. **User Expectation**: Users understand switches as controls
3. **Standard Platform**: Fully supported by Home Assistant
4. **Rich Attributes**: Can expose all lighting configuration as attributes
5. **UI Integration**: Works naturally with Lovelace switch cards
6. **Automation-Friendly**: Easy to use in automations and scripts

## Updated Entity Structure

### Per Zone:
```yaml
# Switches (Layer Control)
switch.living_room_adaptive_layer    # Built-in adaptive layer
switch.living_room_movie_layer       # User-created layer
switch.living_room_dinner_layer      # User-created layer
switch.living_room_manual_layer      # User-created layer

# Sensors (Observability)
sensor.living_room_winning_layer     # Which layer is currently winning
sensor.living_room_calculated_state  # Final calculated light state
sensor.living_room_active_layers     # List of active layers
sensor.living_room_calculation_path  # How we got to this state
sensor.living_room_conflicts         # Any priority conflicts
sensor.living_room_performance       # Calculation performance metrics

# Device Registry
device: "Living Room Lighting"       # Groups all above entities
```

## Key Implementation Changes

### 1. Switch Platform (`switch.py`)
```python
class LayerSwitch(SwitchEntity, RestoreEntity, CoordinatorEntity):
    """Represents a lighting layer as a switch."""
    
    @property
    def is_on(self) -> bool:
        """Return true if layer is active."""
        return self._attr_is_on
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return all layer configuration as attributes."""
        return {
            "zone": self._zone_id,
            "priority": self._priority,
            "brightness": self._brightness,
            "color_temp": self._color_temp,
            "rgb_color": self._rgb_color,
            "transition": self._transition,
            "force": self._force,
            "locked": self._locked,
            "source": self._source,
            "last_updated": self._last_updated,
            **self._extra_attributes  # User-defined attributes
        }
    
    async def async_turn_on(self, **kwargs) -> None:
        """Activate the layer with optional attribute updates."""
        # Update attributes from kwargs if provided
        # Mark layer as active
        # Trigger coordinator recalculation
    
    async def async_turn_off(self, **kwargs) -> None:
        """Deactivate the layer."""
        # Mark layer as inactive
        # Trigger coordinator recalculation
```

### 2. Service Updates

Services now target switch entities:

```yaml
# Activate a layer
service: switch.turn_on
target:
  entity_id: switch.living_room_movie_layer
data:
  # Can optionally update attributes during activation
  brightness: 30
  color_temp: 500

# Deactivate a layer
service: switch.turn_off
target:
  entity_id: switch.living_room_movie_layer

# Update layer attributes without changing active state
service: lighting_manager.update_layer
target:
  entity_id: switch.living_room_movie_layer
data:
  priority: 60
  brightness: 40
  
# Create a new layer
service: lighting_manager.create_layer
data:
  zone_id: "living_room"
  layer_name: "party"
  priority: 45
  # Creates: switch.living_room_party_layer
```

### 3. Modern HA Patterns Applied

#### From Gemini's Research:

1. **DataUpdateCoordinator with `_async_setup`**
   - Use new `_async_setup` method for one-time initialization
   - Centralized data fetching in coordinator
   - CoordinatorEntity base for sensors

2. **Event-Driven Architecture**
   - Listen for `state_changed` events on switches
   - No polling, pure reactive model
   - Custom events for observability

3. **Proper Async Patterns**
   - `async`/`await` throughout
   - `@callback` for synchronous event handlers
   - No blocking operations

4. **Device Registry Integration**
   - Zone as device container
   - Proper entity categories:
     - Switches: `EntityCategory.CONFIG`
     - Diagnostic sensors: `EntityCategory.DIAGNOSTIC`

5. **Statistics Support**
   - `state_class = StateClass.MEASUREMENT` for sensors
   - Long-term history automatically handled

6. **WebSocket API**
   - Real-time updates for UI
   - No custom implementation needed

## Benefits of This Architecture

1. **100% Home Assistant Native**: No custom platforms or hacks
2. **UI-Friendly**: Switches work perfectly in Lovelace
3. **Discoverable**: Shows up naturally in entity lists
4. **Maintainable**: Uses only standard, documented APIs
5. **Future-Proof**: Aligned with HA's architectural direction
6. **Testable**: Standard entities are easier to test

## Migration Path

Since this is a clean install (no existing users), we can implement this architecture directly without migration concerns.

## Separation of Concerns Maintained

Despite the platform change, our core principles remain:

1. **Switches = Pure Data**: Just containers for lighting state
2. **Coordinator = Orchestration**: Manages calculation timing
3. **Calculator = Pure Logic**: Determines winning layer
4. **Controller = Application**: Applies state to lights
5. **Sensors = Observation**: Read-only views of state

The switch platform change is purely about using HA's standard entity types - it doesn't change our fundamental architecture of separated concerns.