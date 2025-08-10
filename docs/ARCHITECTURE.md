# Lighting Manager Architecture

## Core Design Principles

### 1. Centralized State Management
Each zone maintains a single source of truth through the `ZoneCoordinator`. This eliminates race conditions and ensures consistent state across all components.

```
External Input → Coordinator → Calculator → Controller → Physical Lights
```

### 2. Pure Functional Calculations
The `LightingCalculator` is a pure function with no side effects:
- Input: Layer configurations
- Output: Winning state
- No Home Assistant dependencies
- Fully testable in isolation

### 3. Event-Driven Architecture
- React to state changes via events
- No polling mechanisms
- 100ms debounce window for efficiency
- Batch processing during debounce

### 4. Layer Priority System
```
Priority 0-100 (higher wins)
├── 90-100: Emergency/Safety
├── 70-89:  Forced Overrides
├── 50-69:  Manual Control
├── 30-49:  Adaptive/Automatic
└── 0-29:   Background/Ambient
```

## Component Architecture

### ZoneCoordinator (`coordinator.py`)
**Responsibility**: State orchestration and persistence

Key features:
- Maintains all layer state
- Handles layer lifecycle (create/update/delete)
- Manages expiration timers
- Triggers calculations
- Applies results to lights

### LightingCalculator (`calculator.py`)
**Responsibility**: Pure calculation logic

Key features:
- Priority resolution
- Modifier stacking
- Conflict detection
- State merging
- No side effects

### LayerSwitch (`switch.py`)
**Responsibility**: UI representation of layers

Key features:
- Stateless views of coordinator data
- User interaction handling
- State change notifications
- Rich attribute exposure

### ZoneSensor (`sensor.py`)
**Responsibility**: Observability and debugging

Key features:
- Active layer display
- Calculation metrics
- Applied modifiers list
- Performance tracking

### LightController (`controller.py`)
**Responsibility**: Hardware interaction

Key features:
- Light state application
- Transition management
- Error handling
- Retry logic

## Data Flow

### State Change Flow
1. User/automation triggers layer change
2. Switch entity notifies coordinator
3. Coordinator debounces (100ms)
4. Calculator determines winning state
5. Controller applies to lights
6. Sensors update for observability

### Modifier Application Flow
1. Absolute layers compete by priority
2. Winner determined
3. Modifiers sorted by priority
4. Each modifier applied sequentially
5. Final state calculated
6. Constraints applied (min/max)

## Key Patterns

### Debouncing Pattern
```python
async def _on_state_change(self):
    if self._debounce_timer:
        self._debounce_timer.cancel()
    
    self._debounce_timer = self.hass.loop.call_later(
        0.1,  # 100ms
        lambda: self.hass.async_create_task(self._calculate())
    )
```

### Priority Resolution Pattern
```python
def _get_winner(self, layers):
    active = [l for l in layers if l.get("is_on")]
    if not active:
        return None
    
    # Force overrides everything
    forced = [l for l in active if l.get("force")]
    if forced:
        return max(forced, key=lambda x: x.get("priority", 0))
    
    # Normal priority
    return max(active, key=lambda x: x.get("priority", 0))
```

### Modifier Stacking Pattern
```python
def _apply_modifiers(self, base_state, modifiers):
    result = base_state.copy()
    
    for modifier in sorted(modifiers, key=lambda x: x["priority"]):
        if "brightness_pct_delta" in modifier:
            result["brightness"] = self._apply_percentage_delta(
                result["brightness"],
                modifier["brightness_pct_delta"]
            )
    
    return result
```

## Performance Characteristics

### Latency Budget (200ms total)
- Event detection: < 10ms
- Debounce wait: 100ms (fixed)
- Calculation: < 50ms
- Light control: < 40ms

### Memory Usage
- Per zone: ~3MB base
- Per layer: ~10KB
- Calculation cache: 128 entries
- Event queue: 100 events

### Scalability
- Zones: Tested to 50
- Layers per zone: Tested to 30
- Lights per zone: Tested to 20
- Concurrent calculations: Unlimited (async)

## Error Handling

### Graceful Degradation
1. Calculation errors → Use last known good state
2. Light unavailable → Skip and continue
3. Service errors → Retry with backoff
4. Coordinator crash → Switches remain functional

### Recovery Mechanisms
- Automatic state validation on startup
- Persistent storage across restarts
- Self-healing after errors
- Manual recalculation service

## Security Considerations

### Layer Locking
Prevents unauthorized modifications:
```python
if layer.get("locked") and not force:
    raise ValueError("Layer is locked")
```

### Priority Boundaries
Zone-configurable min/max for modifiers:
```python
if modifier_priority < zone_min or modifier_priority > zone_max:
    # Modifier ignored, logged
    continue
```

### State Validation
All inputs validated before processing:
```python
def validate_layer_payload(payload):
    # Type checking
    # Range validation
    # Constraint enforcement
    return clean_payload
```