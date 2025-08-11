# LIGHTING MANAGER REFACTORING - COMMIT CONTEXT

## 🎯 Current Architecture Status

### What We're Building
A production-grade Home Assistant Lighting Manager with **sacred separation of concerns** where each component has EXACTLY ONE responsibility. This is NON-NEGOTIABLE per `/CLAUDE.md`.

### Critical Architecture Decisions Made

#### 1. Single Entry Point Pattern (COMPLETED)
```python
# LayerManager has THE SINGLE ENTRY POINT for all layer modifications:
success, action = layer_manager.set_layer(layer_id, layer_data)
# Returns: (True, "created") or (True, "updated") or (False, "failed")
```
- ✅ LayerManager.set_layer() implemented (layer_manager.py:112-131)
- ❌ services.py needs fixing - currently broken at line 467-487
- ❌ handle_apply_preset needs fixing at line 1036

#### 2. Component Responsibilities (SACRED - DO NOT VIOLATE)

| Component | Single Responsibility | What it MUST NOT do |
|-----------|----------------------|---------------------|
| **LayerManager** | CRUD operations & persistence | Calculate state, control lights |
| **StateCalculator** | Pure functional calculation | Import HomeAssistant, have side effects |
| **LightController** | Hardware control with circuit breaker | Store layer data, calculate state |
| **ChangeDetector** | Manual override detection (5 sec) | Modify layers directly, control lights |
| **AdaptiveProvider** | Reference values only | Create layers, modify state |
| **ZoneStateMachine** | Zone state transitions | Control lights, modify layers |
| **ZoneCoordinator** | Pure orchestration ONLY | Contain ANY business logic |

#### 3. Stateless Entity Pattern (COMPLETED)
All switch entities read from `coordinator.data`:
```python
@property
def is_on(self) -> bool:
    layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
    return layer_data.get(ATTR_IS_ON, False)
```

## 🔴 CRITICAL BUGS TO FIX IMMEDIATELY

### Bug 1: services.py handle_set_layer (Lines 467-487)
**CURRENT (BROKEN):**
```python
# Line 467-479 - This is WRONG, reverts to old pattern
existing = coordinator.layer_manager.get_layer(layer_id)
if existing:
    success = coordinator.layer_manager.update_layer(layer_id, layer_data)
    action = "updated" if success else "failed"
else:
    coordinator.layer_manager.create_layer(layer_id, layer_data)
    success = True
    action = "created"
```

**MUST BE:**
```python
# Call THE SINGLE ENTRY POINT in LayerManager
success, action = coordinator.layer_manager.set_layer(layer_id, layer_data)
```

### Bug 2: services.py handle_apply_preset (Line 1036)
**CURRENT (BROKEN):**
```python
# Line 1036 - Missing return value capture
coordinator.layer_manager.set_layer("manual", layer_data)
```

**MUST BE:**
```python
success, action = coordinator.layer_manager.set_layer("manual", layer_data)

if success:
    # Save if needed
    if coordinator.layer_manager.has_pending_save():
        await coordinator.layer_manager.save()
    
    # Trigger recalculation
    coordinator.schedule_recalculation()
```

## 📋 Remaining Tasks (Priority Order)

### 1. ⚠️ Fix services.py (URGENT)
- [ ] Fix handle_set_layer to use set_layer() properly
- [ ] Fix handle_apply_preset to use set_layer() properly
- [ ] Ensure ALL service handlers that modify layers go through set_layer()

### 2. Update __init__.py (Task 13 from PLAN.md)
- [ ] Line 29: Already correct - uses `from .coordinator import ZoneCoordinator`
- [ ] Lines 87-90: REMOVE the startup calculation:
```python
# DELETE THESE LINES - coordinator handles this
if any(layer.get("is_on", False) for layer in coordinator.layers.values()):
    await coordinator.async_refresh()
```

### 3. Update sensor.py for observability (Task 14)
Add ALL internal state to diagnostic sensor's `extra_state_attributes`:
```python
@property
def extra_state_attributes(self) -> dict[str, Any]:
    data = self.coordinator.data
    return {
        "zone_state": data.get("zone_state"),
        "zone_state_info": data.get("zone_state_info", {}),
        "manual_override_active": data.get("manual_override_active"),
        "last_commanded_state": data.get("last_commanded_state", {}),
        "current_actual_state": data.get("current_actual_state", {}),
        "circuit_breaker_status": data.get("circuit_breaker_status", {}),
        "adaptive_values": data.get("adaptive_values", {}),
        "winning_layer": data.get("winning_layer"),
        "applied_modifiers": data.get("applied_modifiers", []),
        "conflicts": data.get("conflicts", []),
        "calculation_path": data.get("calculation_path", []),
        "last_updated": data.get("last_updated"),
        "trigger": data.get("trigger"),
        "error": data.get("error"),
    }
```

### 4. Update services.yaml (Task 15)
- [ ] Update set_layer definition to REQUIRE layer_id
- [ ] Comment out deprecated create_layer and update_layer services

## 🏗️ Architecture Patterns (MUST MAINTAIN)

### Component Communication Flow
```
Service Call → handle_set_layer() 
    ↓
LayerManager.set_layer() → returns (success, action)
    ↓
Save if pending → coordinator.schedule_recalculation()
    ↓
Coordinator._on_layers_changed() → _schedule_update() [100ms debounce]
    ↓
_async_update_data() orchestrates:
1. AdaptiveProvider.get_adaptive_values()
2. LayerManager.get_active_layers()
3. StateCalculator.calculate_state()
4. LightController.apply_state() [if AUTO/MANUAL_OVERRIDE]
5. ChangeDetector.check_expired_overrides()
6. Fire events
7. Update coordinator.data
    ↓
All entities read from coordinator.data [stateless views]
```

### Data Flow Rules
1. **Services** → Always use `layer_manager.set_layer()` for modifications
2. **LayerManager** → Notifies listeners on change → triggers coordinator update
3. **Coordinator** → ONLY orchestrates, contains NO business logic
4. **Entities** → NEVER store state, always read from `coordinator.data`

## ⚠️ Common Pitfalls (AVOID)

### ❌ DO NOT:
1. Call `coordinator.update_layer()` - it doesn't exist anymore
2. Call `layer_manager.create_layer()` or `update_layer()` directly from services
3. Add business logic to coordinator - it's ONLY an orchestrator
4. Store state in switch entities - they're views only
5. Create adaptive as a layer - it provides reference values only
6. Apply state on startup - read current state as baseline
7. Make components depend on each other (except coordinator)

### ✅ ALWAYS:
1. Use `layer_manager.set_layer()` for ALL layer modifications
2. Check return value: `success, action = layer_manager.set_layer(...)`
3. Save after modifications if `has_pending_save()`
4. Trigger recalculation after successful modifications
5. Read all entity state from `coordinator.data`
6. Fire events for major actions
7. Maintain circuit breaker pattern in LightController

## 📊 Progress Summary

### Completed (12/16 tasks - 75%)
✅ Created all 6 new component files
✅ Rewrote coordinator.py as pure orchestrator
✅ Implemented LayerManager with set_layer()
✅ Updated switch.py to be stateless
✅ Added all event constants to const.py
✅ Implemented circuit breaker in LightController
✅ Created manual override detection (5 sec interval)
✅ Removed coordinator.update_layer/create_layer methods

### Remaining (4/16 tasks - 25%)
❌ Fix services.py to use set_layer() properly
❌ Update __init__.py to remove startup calculation
❌ Update sensor.py for full observability
❌ Update services.yaml

## 🔍 Testing Checklist

After fixes, verify:
1. [ ] `set_layer` service creates new layers
2. [ ] `set_layer` service updates existing layers (idempotent)
3. [ ] Manual light changes create override within 5 seconds
4. [ ] Circuit breaker opens after 3 failures
5. [ ] All internal state visible in diagnostic sensor
6. [ ] No layers activate on startup
7. [ ] Manual override expires after 2 hours

## 📚 Key Files Reference

| File | Purpose | Critical Lines |
|------|---------|----------------|
| `/CLAUDE.md` | Architectural mandates | Lines 1-41 (NON-NEGOTIABLE) |
| `/PLAN.md` | Complete implementation spec | Lines 1847-1923 (set_layer) |
| `layer_manager.py` | Layer CRUD + set_layer() | Lines 112-131 (set_layer method) |
| `services.py` | Service handlers | Lines 467-487, 1036 (NEED FIXING) |
| `coordinator.py` | Pure orchestrator | Lines 1718-1783 (compatibility methods) |

## 🚀 Next Agent Instructions

1. **FIRST**: Fix the two critical bugs in services.py
2. **THEN**: Update __init__.py, sensor.py, services.yaml
3. **FINALLY**: Run the testing checklist
4. **IMPORTANT**: Do NOT modify the architecture or add new patterns

Remember: The architecture is SET. We're fixing implementation bugs, not redesigning.

---
Generated: 2025-01-11
Branch: v5
Commit after fixing: "fix: Correct services.py to use LayerManager.set_layer() single entry point"