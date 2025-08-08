# Home Assistant Lighting State Orchestration Architecture v2.0

## 🎯 Core Architectural Principles

### The Five Pillars
1. **Centralized State Management**: One orchestration engine per zone (single source of truth)
2. **Explicit State Storage**: All state visible as entities in UI (debug with eyes, not logs)
3. **Calculate → Store → Apply**: Pure functional pipeline with no side effects
4. **Zone Independence**: Each zone is an isolated island with no shared state
5. **Event-Driven Reactivity**: Only react to state changes, never poll

### The Sacred Separation
```
Switches (Data) → Coordinator (Orchestration) → Calculator (Logic) → Controller (Application)
     ↓                    ↓                          ↓                      ↓
   Pure State      Event Management            Pure Functions         Service Calls
```

## 🏗️ Architecture Decision Records (ADRs)

### ADR-001: Switch Platform for Layers
**Decision**: Use `switch.*` entities instead of custom platform
**Rationale**: Home Assistant doesn't support custom entity platforms; switches provide on/off state with rich attributes
**Test**: Switches appear in UI with all attributes visible

### ADR-002: Pure Functional Calculator
**Decision**: Calculator must be a pure function with no Home Assistant imports
**Rationale**: Enables unit testing without HA infrastructure, guarantees no side effects
**Test**: `python3 calculator.py` runs standalone

### ADR-003: 100ms Debounce Window
**Decision**: Coordinator debounces all changes for 100ms before calculation
**Rationale**: Prevents calculation storms during rapid changes while remaining responsive
**Measurement**: Log timestamp delta between trigger and application

## 🚦 Implementation Patterns

### Pattern: Entity ID Generation
```python
from homeassistant.util import slugify

# Always slugify user input for entity IDs
entity_id = f"switch.{slugify(zone_name)}_{slugify(layer_name)}_layer"
# "Living Room" + "Movie Time" → "switch.living_room_movie_time_layer"
```

### Pattern: Config Entry Data Split
```python
# Immutable structural data
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

### Pattern: Observable State
```python
class LayerSwitch:
    @property
    def extra_state_attributes(self):
        return {
            "priority": self._priority,
            "brightness": self._brightness,
            "color_temp": self._color_temp,
            "last_calculation": self._last_calc_time,
            "cache_hits": self._cache_hits
        }  # All internal state exposed as attributes
```

### Pattern: Event-Driven Updates
```python
async def async_added_to_hass(self):
    """Subscribe to state changes on setup."""
    self.async_on_remove(
        async_track_state_change_event(
            self.hass,
            self.entity_ids,
            self._on_state_change
        )
    )
```

## 🎨 Advanced Optimization Strategies

### Calculation Caching
```python
from functools import lru_cache
from hashlib import md5

class LightingCalculator:
    @lru_cache(maxsize=128)
    def calculate_state(self, layer_hash: str) -> dict:
        layers = self._deserialize(layer_hash)
        return self._calculate(layers)
    
    def process(self, layers: list) -> dict:
        # Create deterministic hash of input
        layer_hash = md5(
            json.dumps(layers, sort_keys=True).encode()
        ).hexdigest()
        return self.calculate_state(layer_hash)
```

### Batch Processing During Debounce
```python
class ZoneCoordinator:
    def __init__(self):
        self._pending_updates = set()
        self._debounce_timer = None
    
    async def _on_state_change(self, entity_id: str):
        """Collect changes during debounce window."""
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
        """Process all collected changes at once."""
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        
        result = await self._calculate_once(updates)
        await self._apply_result(result)
```

## 🔍 Debug & Observability

### Debug Sensor Implementation
```python
class CalculationDebugSensor(SensorEntity):
    """Expose internal calculation details."""
    
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

### Event Tracing
```python
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

## 🛡️ Resilience Patterns

### Graceful Degradation
```python
class ZoneCoordinator:
    async def _async_update_data(self):
        """Calculate with fallback to last known good state."""
        try:
            return await self._calculate_state()
        except CalculationError as e:
            _LOGGER.error(f"Calculation failed: {e}")
            return self._last_valid_state  # Use cached result
```

### Circuit Breaker
```python
class LightController:
    def __init__(self):
        self._failure_count = 0
        self._circuit_open = False
    
    async def apply_state(self, state: dict):
        if self._circuit_open and not self._should_retry():
            return  # Skip application
        
        try:
            await self._apply(state)
            self._failure_count = 0  # Reset on success
            self._circuit_open = False
        except Exception as e:
            self._failure_count += 1
            if self._failure_count > 3:
                self._circuit_open = True
                _LOGGER.error("Circuit breaker opened")
```

## 📊 Health Monitoring

### System Health Sensor
```python
class LightingManagerHealth(SensorEntity):
    """System health monitoring."""
    
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

## ✅ Definition of Done

A component is complete when:
1. It does ONE thing well
2. All state is visible in UI
3. It's testable in isolation
4. It reacts to events (no polling)
5. It fails gracefully
6. It logs appropriately
7. It's documented

## 🎓 Key Implementation Rules

1. **Always slugify** user input for entity IDs
2. **Always expose** internal state as attributes
3. **Always cache** expensive calculations
4. **Always debounce** rapid state changes
5. **Always fail gracefully** with fallback behavior
6. **Always use events**, never poll for changes
7. **Always separate** data, orchestration, and logic

Remember: **Clean architecture is not negotiable!**