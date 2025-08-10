# Lighting Manager Implementation Plan - Final Architecture
## Updated: 2025-01-08

### Architectural Philosophy: Pure External Activation

The Lighting Manager is a **priority-based state management system**, not an automation engine. It determines which desired state "wins" when multiple layers are active, but does NOT decide when to activate layers.

## Core Components

### 1. Layers (State Declarations)
**What they are**: Pure data containers that declare a desired light state
**What they store**:
- `priority`: Number 0-100 (higher wins)
- `brightness`: Desired brightness (0-255)
- `color_temp`: Desired color temperature in mireds
- `rgb_color`: RGB values (future)
- `transition`: Transition time in seconds
- `force`: Override priority system
- `locked`: Prevent modifications
- `conditions`: Data only (NOT evaluated by package)

**What they DON'T do**:
- ❌ Evaluate their own conditions
- ❌ Activate themselves
- ❌ React to sensors
- ❌ Know why they're on/off

### 2. Switches (Entity Representation)
**What they are**: Home Assistant switch entities representing layers
**What they do**:
- Display layer configuration in UI
- Show on/off state (controlled externally)
- Expose attributes for debugging
- Accept on/off commands from any source

**Entity ID Pattern**: `switch.{zone_id}_{layer_id}_layer`
Example: `switch.living_room_movie_layer`

### 3. Zone Coordinator (Orchestration)
**Responsibility**: Single source of truth for a zone's state
**What it does**:
- Stores all layer configurations
- Triggers calculations when state changes
- Manages persistence (.storage)
- Provides data to all entities
- Implements 100ms debouncing

**What it DOESN'T do**:
- ❌ Evaluate conditions
- ❌ Track external entities
- ❌ Make activation decisions
- ❌ Implement automation logic

### 4. Calculator (Pure Logic)
**Responsibility**: Determine winning layer based on priority
**Algorithm**:
1. Filter to layers where `is_on=True`
2. Check for force flags (override priority)
3. Check for locks (protected layers)
4. Select highest priority
5. Handle conflicts (same priority)
6. Return winning state

**Key Properties**:
- Pure functional (no side effects)
- No Home Assistant imports
- Deterministic (same input = same output)
- Fully testable in isolation

### 5. Light Controller (Application)
**Responsibility**: Apply calculated state to physical lights
**What it does**:
- Receives winning state from calculator
- Applies to all zone lights
- Handles unavailable entities
- Respects light capabilities
- Manages transitions

## Data Flow

```
1. External Trigger
   ├── User presses wall switch
   ├── Automation detects motion
   ├── Scene activates
   ├── Voice command
   └── Time-based trigger

2. External Action
   └── Set switch.zone_layer = ON/OFF

3. Internal Flow
   Coordinator detects change
   └── Debounce 100ms
       └── Trigger calculation
           └── Calculator determines winner
               └── Controller applies to lights
```

## Service API

### Layer Management
- `create_layer`: Create new layer (stores in coordinator)
- `activate_layer`: Turn on with parameters
- `deactivate_layer`: Turn off
- `update_layer`: Modify attributes
- `set_layer_priority`: Change priority

### Layer State
- `lock_layer`: Prevent modifications
- `unlock_layer`: Allow modifications
- `force_layer`: Override priority
- `unforce_layer`: Remove override

### Zone Control  
- `recalculate_zone`: Force immediate calculation
- `reset_zone`: Deactivate all layers except base
- `apply_preset`: Apply predefined configuration

## Storage & Persistence

### Config Entry Data (Immutable)
```python
{
    "zone_id": "living_room",
    "zone_name": "Living Room",
    "area_id": "living_room_area"  # Optional
}
```

### Config Entry Options (User Modifiable)
```python
{
    "light_entities": ["light.ceiling", "light.lamp"],
    "default_transition": 2.0,
    "adaptive_enabled": true
}
```

### Layer Storage (.storage/lighting_manager_{zone_id}.json)
```json
{
    "layers": {
        "manual": {
            "layer_name": "Manual Control",
            "is_on": false,
            "priority": 100,
            "brightness": 255,
            "color_temp": 350,
            "transition": 2.0,
            "created_at": "2025-01-08T10:00:00Z",
            "last_modified": "2025-01-08T10:00:00Z"
        }
    }
}
```

## Standard Layers (Auto-created)

Each zone gets these layers by default:

1. **base_adaptive** (Priority 0)
   - Lowest priority baseline
   - For circadian/adaptive lighting

2. **environmental** (Priority 10)
   - Environmental responses
   - Weather, outdoor light level

3. **activity** (Priority 20)
   - Motion, presence detection
   - Activity-based lighting

4. **mode** (Priority 30)
   - Mode-based changes
   - Movie, reading, gaming modes

5. **manual** (Priority 100)
   - Highest priority
   - Direct user control

## Events (For External Integration)

The package fires these events for external systems:

- `lighting_manager.layer_activated`
- `lighting_manager.layer_deactivated`
- `lighting_manager.layer_created`
- `lighting_manager.layer_removed`
- `lighting_manager.calculation_complete`
- `lighting_manager.conflict_detected`
- `lighting_manager.state_applied`

## Observability (Sensors)

### Per Zone Sensors

1. **Active Layer Sensor** (`sensor.{zone}_active_layer`)
   - State: Name of winning layer
   - Attributes: Priority, brightness, color_temp, reason

2. **Zone Status Sensor** (`sensor.{zone}_status`)
   - State: ok/conflict/error
   - Attributes: Diagnostic information
   - Category: Diagnostic (hidden by default)

## What This Package Does NOT Do

1. **No Condition Evaluation**
   - Conditions can be stored as data
   - External automations evaluate them
   - Package never checks conditions

2. **No Entity Tracking**
   - Doesn't monitor sensors
   - Doesn't react to state changes
   - Only responds to layer on/off

3. **No Automation Logic**
   - Doesn't decide when to activate
   - Doesn't implement triggers
   - Doesn't schedule actions

4. **No Cross-Zone Coordination**
   - Each zone is independent
   - No shared layers between zones
   - No zone-to-zone communication

## Integration Patterns

### Example: Motion-Activated Lighting
```yaml
# External automation
automation:
  - alias: "Living Room Motion"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_motion
        to: 'on'
    action:
      - service: switch.turn_on
        entity_id: switch.living_room_activity_layer
```

### Example: Time-Based Modes
```yaml
automation:
  - alias: "Evening Mode"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: lighting_manager.activate_layer
        target:
          entity_id: switch.living_room_mode_layer
        data:
          brightness: 150
          color_temp: 400
```

### Example: Physical Switch
```yaml
automation:
  - alias: "Wall Switch Pressed"
    trigger:
      - platform: device
        device_id: wall_switch_1
        domain: zha
        type: remote_button_short_press
    action:
      - service: switch.turn_on
        entity_id: switch.living_room_manual_layer
```

## Performance Characteristics

- **Calculation Latency**: < 50ms for 20 layers
- **Debounce Window**: 100ms (prevents storms)
- **Memory per Zone**: < 10MB
- **CPU per Calculation**: < 5%
- **Startup Time**: < 2 seconds per zone

## Testing Strategy

### Unit Tests (Calculator)
- Pure functional tests
- No HA dependencies needed
- Test priority logic
- Test conflict resolution
- Test force/lock flags

### Integration Tests
- Config flow
- Service calls
- Entity creation
- State persistence

### Manual Testing
- Create zones via UI
- Activate/deactivate layers
- Verify light behavior
- Check sensor updates

## Future Considerations (NOT Implemented)

These are intentionally NOT in the package:
1. **RGB Color Support**: Partial implementation exists
2. **Effects/Animations**: Could be added as layer attributes
3. **Schedules**: Use HA automations instead
4. **Conditions**: Stored but not evaluated
5. **Cross-Zone Sync**: Use scenes/scripts instead

## Success Metrics

The implementation succeeds when:
1. **Architectural Purity**: Clean separation of concerns
2. **Predictability**: Same inputs = same outputs
3. **Performance**: Sub-100ms response time
4. **Reliability**: No crashes, graceful failures
5. **Simplicity**: Easy to understand and maintain

## Key Insight

This package is intentionally "dumb" about activation logic. It's a **state management engine**, not an automation engine. This makes it:
- More reliable (less complexity)
- More flexible (works with any automation)
- More maintainable (single responsibility)
- More testable (pure functions)

The power comes from combining this simple, robust state manager with Home Assistant's powerful automation engine.