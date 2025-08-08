# Home Assistant Lighting State Orchestration Architecture v2.0

## 🎯 Core Architectural Principles

### The Five Pillars
1. **Centralized State Management**: One orchestration engine per zone (single source of truth)
2. **Explicit State Storage**: All state visible as entities in UI (debug with eyes, not logs)
3. **Calculate → Store → Apply**: Pure functional pipeline with no side effects
4. **Zone Independence**: Each zone is an isolated island with no shared state
5. **Event-Driven Reactivity**: No polling, only react to state changes

### The Sacred Separation
```
Switches (Data) → Coordinator (Orchestration) → Calculator (Logic) → Controller (Application)
     ↓                    ↓                          ↓                      ↓
   Pure State      Event Management            Pure Functions         Service Calls
```

## 🏗️ Architecture Decision Records (ADRs)

### ADR-001: Switch Platform for Layers
**Decision**: Use `switch.*` entities instead of custom `layer.*` platform
**Rationale**: 
- Home Assistant doesn't support custom entity platforms
- Switches provide on/off state with rich attributes
- Native UI support and service integration
**Consequences**: 
- ✅ Standard platform = better compatibility
- ✅ Users understand switches
- ⚠️ Semantic stretch (layers aren't physical switches)

### ADR-002: Pure Functional Calculator
**Decision**: Calculator must be a pure function with no Home Assistant imports
**Rationale**:
- Enables unit testing without HA infrastructure
- Guarantees no side effects
- Makes logic portable and reusable
**Test**: `python3 calculator.py` should run standalone

### ADR-003: 100ms Debounce Window
**Decision**: Coordinator debounces all changes for 100ms before calculation
**Rationale**:
- Prevents calculation storms during rapid changes
- Batches related updates together
- Fast enough for human perception
**Measurement**: Log timestamp delta between trigger and application

## 🚦 Implementation Patterns

### Pattern: Entity ID Generation
```python
from homeassistant.util import slugify

# ALWAYS slugify user input for entity IDs
entity_id = f"switch.{slugify(zone_name)}_{slugify(layer_name)}_layer"
# "Living Room" + "Movie Time" → "switch.living_room_movie_time_layer"
```

### Pattern: Config Entry Data Split
```python
# Immutable structural data (survives reinstall)
config_entry.data = {
    "zone_id": "living_room",  # Never changes
    "zone_name": "Living Room", # Display name
    "area_id": "bedroom_area"   # HA area link
}

# User-modifiable settings
config_entry.options = {
    "light_entities": ["light.ceiling", "light.lamp"],
    "default_transition": 2.0,
    "adaptive_enabled": True
}
```

### Pattern: State Visibility
```python
# WRONG - Hidden state
class LayerSwitch:
    def __init__(self):
        self._internal_cache = {}  # ❌ Not visible in UI
        
# RIGHT - Observable state
class LayerSwitch:
    @property
    def extra_state_attributes(self):
        return {
            "cache_size": len(self.cache),  # ✅ Visible in UI
            "last_update": self.last_update  # ✅ Observable
        }
```

### Pattern: Event-Driven Updates
```python
# WRONG - Polling
async def check_updates(self):
    while True:
        await asyncio.sleep(1)  # ❌ Polling anti-pattern
        if self.state_changed():
            self.update()

# RIGHT - Event-driven
async def async_added_to_hass(self):
    self.async_on_remove(
        async_track_state_change_event(  # ✅ React to events
            self.hass,
            self.entity_ids,
            self._on_state_change
        )
    )
```

## 🎨 Advanced Optimization Strategies

### Vector State Representation
Consider representing layer states as vectors for efficient calculation:
```python
# Traditional (object comparison)
layers = [
    {"entity_id": "switch.a", "priority": 10, "brightness": 100},
    {"entity_id": "switch.b", "priority": 20, "brightness": 200}
]

# Optimized (vector operations)
priority_vector = np.array([10, 20])
brightness_matrix = np.array([[100], [200]])
winner_index = np.argmax(priority_vector)
final_brightness = brightness_matrix[winner_index]
```

### Calculation Caching Strategy
```python
from functools import lru_cache
from hashlib import md5

class LightingCalculator:
    @lru_cache(maxsize=128)
    def calculate_state(self, layer_hash: str) -> dict:
        # Cached calculation based on input hash
        layers = self._deserialize(layer_hash)
        return self._calculate(layers)
    
    def process(self, layers: list) -> dict:
        # Create deterministic hash of input
        layer_hash = md5(
            json.dumps(layers, sort_keys=True).encode()
        ).hexdigest()
        return self.calculate_state(layer_hash)
```

### Trigger Optimization
```python
class ZoneCoordinator:
    def __init__(self):
        self._pending_updates = set()
        self._debounce_timer = None
    
    async def _on_state_change(self, entity_id: str):
        """Collect changes during debounce window"""
        self._pending_updates.add(entity_id)
        
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        self._debounce_timer = self.hass.loop.call_later(
            0.1,  # 100ms
            lambda: self.hass.async_create_task(
                self._process_batch()
            )
        )
    
    async def _process_batch(self):
        """Process all collected changes at once"""
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        
        # Single calculation for all changes
        result = await self._calculate_once(updates)
        await self._apply_result(result)
```

## 🔍 Debug & Observability Patterns

### Debug Sensor Pattern
```python
class CalculationDebugSensor(SensorEntity):
    """Expose internal calculation details"""
    
    @property
    def extra_state_attributes(self):
        return {
            "input_layers": self._last_input,
            "calculation_steps": self._step_trace,
            "timing_ms": self._calculation_time,
            "cache_hit": self._was_cached,
            "trigger_source": self._trigger_entity
        }
```

### Event Trace Pattern
```python
# Fire detailed events for debugging
self.hass.bus.async_fire(
    "lighting_manager.calculation_complete",
    {
        "zone_id": self.zone_id,
        "trigger": trigger_entity,
        "input_count": len(active_layers),
        "winner": winning_layer,
        "conflicts": conflicts,
        "duration_ms": calc_time
    }
)
```

## 🚀 Performance Targets

### Latency Budget (200ms total)
- Event detection: < 10ms
- Debounce wait: 100ms (fixed)
- Calculation: < 50ms
- Service call: < 40ms

### Scalability Targets
- 20 zones × 20 layers = 400 switch entities
- Memory per zone: < 10MB
- CPU per calculation: < 5%

## 🛡️ Defensive Programming

### Fail-Safe Patterns
```python
class ZoneCoordinator:
    async def _async_update_data(self):
        """Fail gracefully with partial data"""
        try:
            return await self._calculate_state()
        except CalculationError as e:
            # Log but don't crash
            _LOGGER.error(f"Calculation failed: {e}")
            # Return last known good state
            return self._last_valid_state
        except Exception as e:
            # Unknown error - safe mode
            _LOGGER.critical(f"Unexpected error: {e}")
            return {"error": True, "safe_mode": True}
```

### Circuit Breaker Pattern
```python
class LightController:
    def __init__(self):
        self._failure_count = 0
        self._circuit_open = False
    
    async def apply_state(self, state: dict):
        if self._circuit_open:
            if self._should_retry():
                self._circuit_open = False
            else:
                return  # Skip application
        
        try:
            await self._apply(state)
            self._failure_count = 0  # Reset on success
        except Exception as e:
            self._failure_count += 1
            if self._failure_count > 3:
                self._circuit_open = True
                _LOGGER.error("Circuit breaker opened")
```

## 📊 Metrics & Monitoring

### Key Performance Indicators
1. **Calculation Latency**: p50, p95, p99
2. **Cache Hit Rate**: Target > 60%
3. **Event Queue Depth**: Should stay < 10
4. **Memory Growth**: Should plateau after startup
5. **Error Rate**: Target < 0.1%

### Health Check Pattern
```python
class LightingManagerHealth(SensorEntity):
    """System health monitoring"""
    
    @property
    def state(self):
        if self._error_rate > 0.05:
            return "degraded"
        if self._latency_p95 > 150:
            return "slow"
        return "healthy"
    
    @property
    def extra_state_attributes(self):
        return {
            "zones_active": self._zone_count,
            "calculations_per_min": self._calc_rate,
            "cache_hit_rate": self._cache_hits,
            "error_rate": self._error_rate,
            "latency_p95_ms": self._latency_p95
        }
```

## 🎓 Learning from Failures

### Common Pitfalls to Avoid
1. **State Mutation**: Never modify state objects directly
2. **Async Confusion**: Don't mix sync and async carelessly
3. **Entity ID Assumptions**: Always slugify user input
4. **Race Conditions**: Trust the debouncer, don't optimize prematurely
5. **Memory Leaks**: Clean up event listeners properly

### Recovery Strategies
- **Stuck State**: Service to force recalculation
- **Bad Config**: Validation in options flow
- **Performance Issues**: Circuit breaker + safe mode
- **Integration Conflicts**: Namespace everything

## 🔮 Future Considerations

### Potential Optimizations
- **Compiled Calculations**: Use Numba/Cython for calculator
- **State Diffing**: Only send changed attributes to lights
- **Predictive Caching**: Pre-calculate likely next states
- **WebSocket Streaming**: Real-time updates to frontend

### Extension Points
- **Plugin System**: Allow custom calculators
- **ML Integration**: Learn patterns for better defaults
- **Scene Learning**: Auto-create layers from behavior
- **Conflict Resolution**: Pluggable strategies beyond priority

## ✅ Definition of Done

A component is complete when:
1. **It does ONE thing well**
2. **All state is visible in UI**
3. **It's testable in isolation**
4. **It reacts to events, never polls**
5. **It fails gracefully**
6. **It logs appropriately**
7. **It's documented**

Remember: **Clean architecture is not negotiable!**