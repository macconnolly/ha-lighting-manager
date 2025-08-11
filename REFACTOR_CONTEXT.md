# CRITICAL REFACTORING CONTEXT - READ THIS FIRST

## Current Status: Phase 1 of Production-Grade Refactor (8/14 tasks complete)

### ✅ COMPLETED COMPONENTS (DO NOT MODIFY ARCHITECTURE)
1. **layer_manager.py** - CRUD operations and persistence (single responsibility)
2. **state_calculator.py** - Pure functional calculation (NO HA imports)
3. **change_detector.py** - Manual control detection (checks every 5 seconds)
4. **adaptive_provider.py** - Reference values only (NOT a layer)
5. **zone_state_machine.py** - Zone state management (OFF/AUTO/MANUAL_OVERRIDE/LOCKED)
6. **light_controller.py** - Hardware control with circuit breaker pattern
7. **coordinator.py** - Pure orchestrator (NO business logic, only routes between components)
8. **const.py** - Added new event constants

### ⚠️ REMAINING CRITICAL TASKS (IN ORDER)
1. **services.py** - Implement idempotent `set_layer` service (lines 77-122, 450-578)
2. **__init__.py** - Remove initial calculation (lines 87-90)
3. **switch.py** - Ensure ALL properties read from layer_manager (NO local state)
4. **sensor.py** - Add observability attributes to extra_state_attributes
5. **services.yaml** - Update set_layer definition, deprecate create/update_layer

## ARCHITECTURAL MANDATES (NON-NEGOTIABLE)

### 1. Sacred Separation of Concerns
Each component has SINGLE responsibility:
- **LayerManager**: State storage ONLY
- **StateCalculator**: Calculation ONLY (pure function)
- **LightController**: Hardware control ONLY
- **ChangeDetector**: Manual detection ONLY
- **AdaptiveProvider**: Reference values ONLY (NOT a layer)
- **ZoneStateMachine**: State transitions ONLY
- **ZoneCoordinator**: Orchestration ONLY (NO logic)

### 2. Component Independence
- NO component imports another (except coordinator)
- Components communicate ONLY through coordinator
- All state lives in LayerManager
- Switches are stateless views

### 3. Manual Control Detection
- Runs every 5 seconds via async_track_time_interval
- Compares last_commanded_state vs current_state
- Creates manual_override layer (priority 95, 2hr timeout)
- Transitions zone to MANUAL_OVERRIDE state

### 4. Circuit Breaker Pattern
- LightController tracks failures
- Opens after 3 failures
- Enters HALF_OPEN after 60 seconds
- Requires 2 successes to close

### 5. Idempotent Services
```python
# SINGLE entry point for layer operations
async def handle_set_layer(hass, call):
    layer_id = call.data["layer_id"]  # REQUIRED
    # Creates if not exists, updates if exists
    # NO separate create/update services
```

### 6. Observability Requirements
All internal state MUST be visible in diagnostic sensor:
- zone_state (AUTO/MANUAL_OVERRIDE/etc)
- manual_override_active
- last_commanded_state
- current_actual_state
- circuit_breaker_status
- adaptive_values

## IMPLEMENTATION PATTERNS

### Event Flow
1. Layer change → LayerManager notifies listeners
2. Coordinator receives notification → schedules update (100ms debounce)
3. Update cycle:
   - Get adaptive values
   - Get active layers
   - Calculate state (pure function)
   - Apply if zone in AUTO/MANUAL_OVERRIDE
   - Check for expired overrides
   - Fire events
   - Update data structure

### State Machine Transitions
```
OFF → AUTO, MANUAL_OVERRIDE
AUTO → OFF, MANUAL_OVERRIDE, LOCKED  
MANUAL_OVERRIDE → OFF, AUTO
LOCKED → AUTO, OFF
```

### Data Structure (coordinator.data)
```python
{
    "layers": {},  # All layers
    "active_layers": [],  # IDs of is_on=True
    "zone_state": "auto",  # State machine state
    "manual_override_active": False,
    "adaptive_values": {},  # From AdaptiveProvider
    "winning_layer": "layer_id",
    "final_state": {"power": "on", "brightness": 255},
    "last_commanded_state": {},  # What we sent
    "current_actual_state": {},  # What lights report
    "circuit_breaker_status": {"state": "closed"},
}
```

## TESTING CHECKLIST
1. [ ] Create zone - NO layers activate on startup
2. [ ] Toggle physical switch - Override created within 5 seconds
3. [ ] Check diagnostic sensor - All attributes visible
4. [ ] Call set_layer - Idempotent behavior
5. [ ] Trigger 3 failures - Circuit breaker opens
6. [ ] Wait 2 hours - Manual override expires
7. [ ] Change sun position - Adaptive values update

## COMMON PITFALLS TO AVOID
1. ❌ DO NOT add logic to coordinator
2. ❌ DO NOT make components depend on each other
3. ❌ DO NOT store state in switches
4. ❌ DO NOT use polling except manual check
5. ❌ DO NOT create adaptive as a layer
6. ❌ DO NOT apply state on startup

## GIT WORKFLOW
After EACH file change:
```bash
git add [file]
git commit -m "feat/fix: [component] - [specific change]"
# Note: Push requires auth setup
```

## NEXT IMMEDIATE TASK
Update services.py to implement idempotent set_layer service:
- Lines 77-122: Update SERVICE_SET_LAYER_SCHEMA
- Lines 450-578: Replace handle_set_layer function
- Lines 256-268: Comment out deprecated services

Remember: The architecture is now PRODUCTION-GRADE with proper separation of concerns, manual control detection, and resilience patterns.