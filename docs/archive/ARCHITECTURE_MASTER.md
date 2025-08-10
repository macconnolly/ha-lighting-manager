# Lighting Manager - Master Architecture Documentation

## 🎯 Core Architectural Principles

### The Five Sacred Pillars

1. **Centralized State Management**: One orchestration engine per zone (single source of truth)
2. **Explicit State Storage**: All state visible as entities in UI (debug with eyes, not logs)
3. **Calculate → Store → Apply**: Pure functional pipeline with no side effects
4. **Zone Independence**: Each zone is an isolated island with no shared state
5. **Event-Driven Reactivity**: Only react to state changes, never poll

### The Sacred Separation

```
External Systems → Switches (Views) → Coordinator (State+Orchestration) → Calculator (Logic) → Controller (Application)
      ↓               ↓                      ↓                             ↓                      ↓
   Automation      UI Display        Single Source of Truth         Pure Functions         Service Calls
   Scene Logic     User Input         All Layer State Here         No Side Effects       Light Commands
   Manual Control  Attributes Only    Event Management             No HA Dependencies     Physical Output
```

**Critical Rule**: Switches are STATELESS VIEWS. The Coordinator holds ALL state.

## 🏗️ Architecture Decision Records (ADRs)

### ADR-001: Switch Platform for Layers
**Date**: 2025-01-08  
**Status**: Accepted and Implemented

**Decision**: Use `switch.*` entities instead of custom `layer.*` platform

**Rationale**: 
- Home Assistant doesn't support custom entity platforms in 2024/2025
- Switches provide on/off state with rich attributes
- Native UI support and automation integration
- Users understand switches as controls for layers

**Implementation**:
```python
# Entity ID Pattern
switch.{zone_id}_{layer_name}_layer

# Example
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
```

### ADR-002: Pure Functional Calculator
**Decision**: Calculator must be a pure function with no Home Assistant imports

**Rationale**:
- Enables unit testing without HA infrastructure
- Guarantees no side effects
- Makes logic portable and reusable

**Test**: `python3 calculator.py` must run standalone

### ADR-003: 100ms Debounce Window
**Decision**: Coordinator debounces all changes for 100ms before calculation

**Rationale**:
- Prevents calculation storms during rapid changes
- Batches related updates together
- Fast enough for human perception (sub-200ms total latency)

### ADR-004: Coordinator-Centric State Management
**Decision**: ZoneCoordinator holds ALL layer state; switches are stateless views

**Rationale**: 
- Single source of truth eliminates sync issues
- Follows Home Assistant's DataUpdateCoordinator pattern
- Enables atomic updates and prevents race conditions
- Simplifies debugging (all state in one place)

**Implementation**: Switches read from `coordinator.data["layers"][layer_id]` and call `coordinator.update_layer()`

### ADR-005: Pure External Activation Model
**Date**: 2025-01-08  
**Status**: Accepted and Implemented

**Decision**: The package does NOT evaluate any conditions - external systems handle ALL activation logic

**Rationale**:
- Separation of concerns: Package manages competing states, not activation logic
- Architectural purity: Layers are pure state declarations
- Flexibility: ANY external system can activate layers
- Home Assistant Philosophy: Don't duplicate HA's automation engine

**What We DON'T Do**:
- ❌ Evaluate conditions inside the package
- ❌ Decide when to activate layers
- ❌ React directly to sensors
- ❌ Implement automation logic

**What We DO Excellently**:
- ✅ Store layer state declarations
- ✅ Determine priority-based winners
- ✅ Apply states atomically to lights
- ✅ Provide clean API for external control

### ADR-006: Config Entry Integration Pattern
**Decision**: Use Config Entry (not YAML) for modern HA integration

**Rationale**:
- Modern HA best practice (2024/2025)
- UI-based configuration
- Multiple instances support (one per zone)
- Options flow for reconfiguration
- Professional user experience

## 🏛️ Component Architecture

### System Overview
```
┌─────────────────────────────────────────────────────────────────┐
│                    LIGHTING MANAGER ZONE                        │
├─────────────────────────────────────────────────────────────────┤
│  EXTERNAL TRIGGERS                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Automations │  │   Scenes    │  │   Manual    │             │
│  │   Motion    │  │  Circadian  │  │   Control   │             │
│  └─────┬───────┘  └─────┬───────┘  └─────┬───────┘             │
│        │                │                │                     │
│        └────────────────┼────────────────┘                     │
│                         ▼                                       │
│  DATA LAYER (Views)                                             │
│  ┌─────────────────────────────────────────────────────────────┤
│  │ ●switch.zone_adaptive_layer  ●switch.zone_movie_layer      │
│  │ ●switch.zone_manual_layer    ●switch.zone_dinner_layer     │
│  │                                                             │
│  │ - Pure data containers with attributes                      │
│  │ - Stateless views of coordinator state                      │
│  │ - No logic, just on/off + attributes                       │
│  └─────────────────┬───────────────────────────────────────────┤
│                    │ State Changes (Events)                    │
│                    ▼                                           │
│  ORCHESTRATION LAYER                                            │
│  ┌─────────────────────────────────────────────────────────────┤
│  │                 ZoneCoordinator                             │
│  │                                                             │
│  │ - Single source of truth for all layer state               │
│  │ - Event-driven updates (no polling)                        │
│  │ - 100ms debounce window                                     │
│  │ - Manages calculation timing                                │
│  │ - Persistence and state restoration                         │
│  └─────────────────┬───────────────────────────────────────────┤
│                    │ Trigger Calculation                       │
│                    ▼                                           │
│  CALCULATION LAYER                                              │
│  ┌─────────────────────────────────────────────────────────────┤
│  │                LightingCalculator                           │
│  │                                                             │
│  │ - Pure functional logic (no HA imports)                    │
│  │ - Priority-based winner determination                       │
│  │ - Handles force flags and locks                             │
│  │ - No side effects or state mutation                         │
│  │ - Fully testable in isolation                               │
│  └─────────────────┬───────────────────────────────────────────┤
│                    │ Return Winning State                      │
│                    ▼                                           │
│  APPLICATION LAYER                                              │
│  ┌─────────────────────────────────────────────────────────────┤
│  │                 LightController                             │
│  │                                                             │
│  │ - Apply calculated state to physical lights                 │
│  │ - Handle light capabilities and constraints                 │
│  │ - Service call management                                   │
│  │ - No calculation logic                                      │
│  └─────────────────┬───────────────────────────────────────────┤
│                    │ Apply to Hardware                         │
│                    ▼                                           │
│  OBSERVATION LAYER                                              │
│  ┌─────────────────────────────────────────────────────────────┤
│  │ ●sensor.zone_winning_layer    ●sensor.zone_conflicts       │
│  │ ●sensor.zone_calculated_state ●sensor.zone_performance     │
│  │ ●sensor.zone_active_layers    ●sensor.zone_health          │
│  │                                                             │
│  │ - Read-only views of internal state                         │
│  │ - Full observability for debugging                          │
│  │ - Performance and health monitoring                         │
│  └─────────────────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Patterns

#### 1. Layer Activation Flow
```
External Automation: "Motion detected, activate motion layer"
                ↓
Sets: switch.living_room_motion_layer = ON
                ↓
Coordinator: "State changed event received"
                ↓
Debounce Timer: "Wait 100ms for more changes"
                ↓
Calculator: "Of all ON layers, motion (priority 20) wins over manual (priority 10)"
                ↓
Controller: "Apply brightness=200, color_temp=4000 to all zone lights"
                ↓
Sensors: "Update winning_layer=motion, calculated_state={...}"
                ↓
Events: "Fire lighting_manager.calculation_complete"
```

#### 2. Priority Conflict Resolution
```
Current State: Manual layer (priority 10) active, brightness=100
                ↓
Movie Scene: Activates movie layer (priority 50), brightness=30
                ↓
Calculator Input: [
  {entity_id: "switch.zone_manual_layer", priority: 10, is_on: true, brightness: 100},
  {entity_id: "switch.zone_movie_layer", priority: 50, is_on: true, brightness: 30}
]
                ↓
Priority Logic: max(10, 50) = 50 → movie layer wins
                ↓
Result: {winning_layer: "movie", brightness: 30, color_temp: 3000}
                ↓
Applied: Lights dim to 30, warm to 3000K
```

#### 3. Force Flag Override
```
Current Winner: Movie layer (priority 50)
                ↓
Emergency Override: Manual layer forced (priority 10, force=true)
                ↓
Calculator Logic: Force flag overrides priority comparison
                ↓
Result: Manual layer wins despite lower priority
                ↓
Applied: Immediate override to manual settings
```

### State Management Strategy

#### Coordinator Data Structure
```python
coordinator.data = {
    "layers": {
        "manual": {
            "entity_id": "switch.zone_manual_layer",
            "is_on": False,
            "priority": 10,
            "brightness": 255,
            "color_temp": 4000,
            "rgb_color": None,
            "transition": 1.0,
            "force": False,
            "locked": False,
            "source": None,
            "last_updated": "2024-01-15T20:30:00Z",
            "extra_attributes": {}
        },
        "adaptive": {
            "entity_id": "switch.zone_adaptive_layer",
            "is_on": True,
            "priority": 5,
            "brightness": 180,
            "color_temp": 3200,
            # ... etc
        }
    },
    "zone_config": {
        "light_entities": ["light.ceiling", "light.lamp"],
        "adaptive_enabled": True,
        "default_transition": 2.0
    },
    "calculated_state": {
        "winning_layer": "adaptive",
        "brightness": 180,
        "color_temp": 3200,
        "last_calculation": "2024-01-15T20:30:05Z",
        "calculation_time_ms": 12
    },
    "performance": {
        "cache_hits": 145,
        "cache_misses": 23,
        "avg_calculation_time": 8.5,
        "total_calculations": 168
    }
}
```

#### State Visibility Rules
1. **All state must be visible in UI** - No hidden internal dictionaries
2. **Attributes expose everything** - Every switch shows all its configuration
3. **Sensors show read-only views** - Coordinator state visible through sensors
4. **Events provide audit trail** - All state changes fire events

## 🎛️ Event System Design

### Event Architecture
```python
# Core Events
"lighting_manager.calculation_complete" - After each calculation
"lighting_manager.layer_activated" - When layer turns on
"lighting_manager.layer_deactivated" - When layer turns off
"lighting_manager.layer_updated" - When layer attributes change
"lighting_manager.lights_applied" - After lights updated
"lighting_manager.error_occurred" - On any error

# Event Data Structure
{
    "zone_id": "living_room",
    "timestamp": "2024-01-15T20:30:05.123Z",
    "trigger": "switch.living_room_motion_layer",
    "event_type": "calculation_complete",
    "data": {
        "input_layers": 3,
        "active_layers": 2,
        "winning_layer": "motion",
        "conflicts": [],
        "calculation_time_ms": 12,
        "cache_hit": True,
        "applied_state": {
            "brightness": 200,
            "color_temp": 4000
        }
    }
}
```

### Event-Driven Patterns

#### 1. State Change Listeners
```python
class ZoneCoordinator:
    async def async_added_to_hass(self):
        """Set up event listeners."""
        # Listen to all switch state changes in this zone
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                list(self.switch_entity_ids),
                self._on_layer_state_change
            )
        )
        
        # Listen to light state changes for feedback
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self.zone_config["light_entities"],
                self._on_light_state_change
            )
        )
```

#### 2. Debounce Implementation
```python
class ZoneCoordinator:
    def __init__(self):
        self._pending_updates = set()
        self._debounce_timer = None
    
    async def _on_layer_state_change(self, event):
        """Collect changes during debounce window."""
        entity_id = event.data.get("entity_id")
        self._pending_updates.add(entity_id)
        
        # Cancel existing timer
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        # Start new timer
        self._debounce_timer = self.hass.helpers.event.async_call_later(
            0.1,  # 100ms debounce
            self._process_batched_updates
        )
    
    async def _process_batched_updates(self):
        """Process all collected changes atomically."""
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        
        # Single calculation for all changes
        await self.schedule_recalculation(f"batch_update_{len(updates)}")
```

## 🛡️ Error Handling Patterns

### Defensive Programming Strategy

#### 1. Graceful Degradation
```python
class ZoneCoordinator:
    async def _async_update_data(self):
        """Calculate with fallback to last known good state."""
        try:
            return await self._calculate_state()
        except CalculationError as e:
            _LOGGER.error(f"Calculation failed: {e}")
            return self._last_valid_state or self._safe_defaults()
        except Exception as e:
            _LOGGER.critical(f"Unexpected error in zone {self.zone_id}: {e}")
            return self._emergency_safe_state()
```

#### 2. Circuit Breaker Pattern
```python
class LightController:
    def __init__(self):
        self._failure_count = 0
        self._circuit_open = False
        self._last_failure = None
    
    async def apply_state(self, state: dict):
        """Apply state with circuit breaker protection."""
        if self._circuit_open and not self._should_retry():
            _LOGGER.warning(f"Circuit breaker open, skipping light update")
            return
        
        try:
            await self._apply_state_to_lights(state)
            self._reset_circuit_breaker()
        except Exception as e:
            await self._handle_failure(e)
    
    async def _handle_failure(self, error):
        """Handle failure and possibly open circuit breaker."""
        self._failure_count += 1
        self._last_failure = datetime.now()
        
        if self._failure_count >= 3:
            self._circuit_open = True
            _LOGGER.error(f"Circuit breaker opened after {self._failure_count} failures")
            
            # Fire event for monitoring
            self.hass.bus.async_fire(
                "lighting_manager.error_occurred",
                {
                    "zone_id": self.zone_id,
                    "error_type": "circuit_breaker_open",
                    "failure_count": self._failure_count
                }
            )
```

#### 3. Input Validation
```python
class LayerSwitch:
    async def async_turn_on(self, **kwargs):
        """Turn on layer with attribute validation."""
        updates = {}
        
        # Validate brightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 255:
                _LOGGER.warning(f"Invalid brightness {brightness}, clamping to 0-255")
                brightness = max(0, min(255, float(brightness)))
            updates[ATTR_BRIGHTNESS] = brightness
        
        # Validate color temperature
        if ATTR_COLOR_TEMP in kwargs:
            color_temp = kwargs[ATTR_COLOR_TEMP]
            if not isinstance(color_temp, (int, float)) or not 153 <= color_temp <= 500:
                _LOGGER.warning(f"Invalid color_temp {color_temp}, using default")
                updates[ATTR_COLOR_TEMP] = 250  # Default warm white
            else:
                updates[ATTR_COLOR_TEMP] = color_temp
        
        # Apply validated updates
        await self.coordinator.update_layer(self._layer_id, updates)
```

### Anti-Patterns to Avoid

Based on comprehensive bug analysis, these patterns MUST be avoided:

#### ❌ State Mutation Anti-Patterns
```python
# WRONG - Direct state mutation
coordinator.layers[layer_id]["brightness"] = 100

# WRONG - Returning mutable references
@property
def data(self):
    return {"layers": self.layers}  # Direct reference!

# RIGHT - Immutable updates through API
await coordinator.update_layer(layer_id, {"brightness": 100})

# RIGHT - Return copies
@property
def data(self):
    return {"layers": copy.deepcopy(self.layers)}
```

#### ❌ Logic Placement Anti-Patterns
```python
# WRONG - Calculator importing HA
from homeassistant.helpers.service import async_call_service

# WRONG - Switch containing calculation logic
class LayerSwitch:
    def get_winning_layer(self):
        # Priority comparison logic here

# WRONG - Coordinator doing brightness math
class ZoneCoordinator:
    def calculate_brightness(self, layers):
        # Mathematical calculation here
```

#### ❌ Async/Sync Mixing Anti-Patterns
```python
# WRONG - Sync in async context
async def process_layers(self):
    time.sleep(0.1)  # Blocks event loop

# WRONG - Async in sync context  
def calculate_state(self):
    await some_async_call()  # Can't await in sync

# RIGHT - Proper async patterns
async def process_layers(self):
    await asyncio.sleep(0.1)
```

## 🚀 Performance Optimizations Applied

### Calculation Caching
```python
from functools import lru_cache
from hashlib import md5

class LightingCalculator:
    def __init__(self):
        self._cache_hits = 0
        self._cache_misses = 0
    
    @lru_cache(maxsize=128)
    def _calculate_state_cached(self, layers_hash: str) -> dict:
        """Cached calculation based on input hash."""
        self._cache_misses += 1
        layers = json.loads(layers_hash)
        return self._calculate_state_internal(layers)
    
    def calculate_state(self, layers: list) -> dict:
        """Public interface with caching."""
        # Create deterministic hash of input
        layers_json = json.dumps(layers, sort_keys=True)
        layers_hash = md5(layers_json.encode()).hexdigest()
        
        result = self._calculate_state_cached(layers_hash)
        self._cache_hits += 1
        
        return {
            **result,
            "cache_hit": True,
            "cache_stats": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": self._cache_hits / (self._cache_hits + self._cache_misses)
            }
        }
```

### Non-Blocking Light Updates
```python
class LightController:
    async def apply_state(self, state: dict):
        """Apply state to lights non-blocking."""
        # Prepare all service calls
        service_calls = []
        for entity_id in self.light_entities:
            service_calls.append(
                self.hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": entity_id,
                        **self._prepare_light_data(state)
                    },
                    blocking=False  # Non-blocking
                )
            )
        
        # Execute all calls concurrently
        await asyncio.gather(*service_calls, return_exceptions=True)
```

### Smart Event Firing
```python
class ZoneCoordinator:
    async def _apply_calculated_state(self, result: dict):
        """Apply state and fire events only on change."""
        previous_winner = self.data.get("calculated_state", {}).get("winning_layer")
        new_winner = result.get("winning_layer")
        
        # Always update internal state
        self.data["calculated_state"] = result
        
        # Only fire events on actual changes
        if new_winner != previous_winner:
            self.hass.bus.async_fire(
                "lighting_manager.winner_changed",
                {
                    "zone_id": self.zone_id,
                    "previous_winner": previous_winner,
                    "new_winner": new_winner,
                    "timestamp": datetime.now().isoformat()
                }
            )
```

## 📊 Performance Targets & Monitoring

### Latency Budget (200ms total)
- Event detection: < 10ms
- Debounce wait: 100ms (fixed)
- Calculation: < 50ms
- Service call: < 40ms

### Scalability Targets
- 20 zones × 20 layers = 400 switch entities
- Memory per zone: < 10MB
- CPU per calculation: < 5%
- Cache hit rate: > 60%

### Health Monitoring
```python
class LightingManagerHealth(SensorEntity):
    """System health monitoring sensor."""
    
    @property
    def state(self):
        """Return overall system health."""
        if self._error_rate > 0.05:
            return "degraded"
        if self._latency_p95 > 150:
            return "slow"
        return "healthy"
    
    @property
    def extra_state_attributes(self):
        """Detailed health metrics."""
        return {
            "zones_active": len(self._active_zones),
            "calculations_per_min": self._calc_rate,
            "cache_hit_rate": self._cache_hit_rate,
            "error_rate": self._error_rate,
            "latency_p50_ms": self._latency_p50,
            "latency_p95_ms": self._latency_p95,
            "circuit_breakers_open": self._circuit_breakers_open,
            "memory_usage_mb": self._memory_usage,
            "uptime_hours": self._uptime_hours
        }
```

## 🔧 Implementation Patterns

### Entity ID Generation
```python
from homeassistant.util import slugify

def generate_layer_entity_id(zone_name: str, layer_name: str) -> str:
    """Generate consistent entity ID for layer switch."""
    zone_slug = slugify(zone_name)
    layer_slug = slugify(layer_name)
    return f"switch.{zone_slug}_{layer_slug}_layer"

# Examples:
# "Living Room" + "Movie Time" → "switch.living_room_movie_time_layer"
# "Master Bedroom" + "Reading Light" → "switch.master_bedroom_reading_light_layer"
```

### Config Entry Data Split
```python
# Immutable structural data (config_entry.data)
IMMUTABLE_DATA = {
    "zone_id": "living_room",      # Never changes after creation
    "zone_name": "Living Room",    # Display name
    "area_id": "bedroom_area"      # HA area association
}

# User-modifiable settings (config_entry.options)
MUTABLE_OPTIONS = {
    "light_entities": ["light.ceiling", "light.lamp"],
    "default_transition": 2.0,
    "adaptive_enabled": True,
    "default_brightness": 200,
    "performance_mode": "balanced"
}
```

### Service Implementation Pattern
```python
async def handle_create_layer(call: ServiceCall):
    """Create new layer through service call."""
    # 1. Validate inputs
    zone_id = call.data.get("zone_id")
    layer_name = call.data.get("layer_name")
    
    if not zone_id or not layer_name:
        raise ServiceValidationError("zone_id and layer_name required")
    
    # 2. Get zone coordinator
    coordinator = await _get_zone_coordinator(call.hass, zone_id)
    if not coordinator:
        raise ServiceValidationError(f"Zone {zone_id} not found")
    
    # 3. Create layer through coordinator API
    layer_config = {
        "priority": call.data.get("priority", 50),
        "brightness": call.data.get("brightness", 255),
        "color_temp": call.data.get("color_temp"),
        "rgb_color": call.data.get("rgb_color"),
        "transition": call.data.get("transition", 1.0)
    }
    
    try:
        entity_id = await coordinator.create_layer(layer_name, layer_config)
        
        # 4. Fire success event
        call.hass.bus.async_fire(
            "lighting_manager.layer_created",
            {
                "zone_id": zone_id,
                "layer_name": layer_name,
                "entity_id": entity_id,
                "config": layer_config
            }
        )
        
    except Exception as e:
        _LOGGER.error(f"Failed to create layer {layer_name} in {zone_id}: {e}")
        raise HomeAssistantError(f"Layer creation failed: {e}")
```

## 🧪 Testing Strategy

### Unit Testing Patterns
```python
# Calculator Testing (Pure Functions)
def test_calculator_priority_logic():
    """Test calculator without any HA dependencies."""
    calc = LightingCalculator()
    
    layers = [
        {"entity_id": "test.layer_1", "priority": 10, "brightness": 100, "is_on": True},
        {"entity_id": "test.layer_2", "priority": 20, "brightness": 200, "is_on": True}
    ]
    
    result = calc.calculate_state(layers)
    
    assert result["winning_layer"] == "test.layer_2"
    assert result["brightness"] == 200
    assert result["conflicts"] == []

# Integration Testing
async def test_full_layer_activation_flow(hass):
    """Test complete flow from switch activation to light change."""
    # 1. Set up zone
    coordinator = await create_test_zone(hass, "test_zone")
    
    # 2. Create layer
    layer_id = await coordinator.create_layer("test_layer", {"priority": 50})
    
    # 3. Activate layer
    await hass.services.async_call("switch", "turn_on", {"entity_id": layer_id})
    await hass.async_block_till_done()
    
    # 4. Verify light state changed
    light_state = hass.states.get("light.test_light")
    assert light_state.state == "on"
```

### Performance Testing
```python
def test_calculation_performance():
    """Verify calculation performance meets targets."""
    calc = LightingCalculator()
    
    # Generate 20 layers (max expected)
    layers = [
        {
            "entity_id": f"test.layer_{i}",
            "priority": random.randint(1, 100),
            "brightness": random.randint(1, 255),
            "is_on": random.choice([True, False])
        }
        for i in range(20)
    ]
    
    # Measure calculation time
    start = time.perf_counter()
    result = calc.calculate_state(layers)
    duration_ms = (time.perf_counter() - start) * 1000
    
    # Must complete within 50ms target
    assert duration_ms < 50
    assert "winning_layer" in result
```

## ✅ Definition of Done

A component is complete when:

1. **Single Responsibility**: It does exactly ONE thing well
2. **Observable State**: All internal state is visible in the UI
3. **Testable**: It can be tested in isolation without complex mocking
4. **Event-Driven**: It reacts to events, never polls for changes
5. **Graceful Failure**: It fails gracefully with appropriate fallbacks
6. **Appropriate Logging**: It logs errors and important state changes
7. **Documented**: Its purpose and interactions are clearly documented

## 🎓 Implementation Rules (Non-Negotiable)

1. **Always slugify** user input for entity IDs
2. **Always expose** internal state as attributes  
3. **Always cache** expensive calculations
4. **Always debounce** rapid state changes
5. **Always fail gracefully** with fallback behavior
6. **Always use events**, never poll for changes
7. **Always separate** data, orchestration, calculation, and application logic
8. **Never mutate** state objects directly
9. **Never import** Home Assistant modules in calculator.py
10. **Never share** state between zones

## 🚨 Critical Fixes Applied

Based on comprehensive architectural audit, these critical issues have been resolved:

### Runtime Stability Fixes
- ✅ Missing `_trigger_update()` method causing AttributeError
- ✅ Race condition in data property initialization
- ✅ Timer cleanup race conditions during shutdown
- ✅ Fixed adaptive sensor timing issues

### Entity System Fixes
- ✅ Removed hardcoded entity_id property conflicting with HA registry
- ✅ Removed CONFIG entity category hiding switches from UI
- ✅ Added device info to all sensors for proper grouping
- ✅ Created default "Manual" layer on zone creation

### State Management Fixes
- ✅ Fixed mutable state reference returning direct coordinator.layers
- ✅ Added proper deep copy for state isolation
- ✅ Implemented performance optimizations (non-blocking calls, smart event firing)

### Config Flow Fixes
- ✅ Fixed OptionsFlowHandler init not passing config_entry to parent
- ✅ Removed duplicate adaptive sensor creation
- ✅ Implemented proper modern Config Entry pattern

## 🔮 Future Architectural Considerations

### Extensibility Points
- **Plugin System**: Custom calculator implementations
- **ML Integration**: Pattern learning for adaptive behaviors
- **Scene Learning**: Auto-create layers from user behavior
- **Conflict Resolution**: Pluggable strategies beyond simple priority

### Performance Optimizations
- **Compiled Calculations**: Numba/Cython for calculator hot paths
- **State Diffing**: Only send changed attributes to lights
- **Predictive Caching**: Pre-calculate likely next states
- **WebSocket Streaming**: Real-time updates to custom frontend

### Advanced Features
- **Cross-Zone Coordination**: Opt-in shared state for complex scenarios
- **Temporal Logic**: Time-based priority adjustments
- **Environmental Adaptation**: Integration with weather, occupancy sensors
- **Energy Optimization**: Power-aware brightness and scheduling

---

**Remember**: Clean architecture is not negotiable. When in doubt, favor separation of concerns over performance. The system's long-term maintainability depends on strict adherence to these architectural principles.

Every component should pass the "elevator pitch test": If you can't explain what it does and why in 30 seconds, it's doing too much.