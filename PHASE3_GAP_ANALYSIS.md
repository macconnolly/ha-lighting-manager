# Phase 3 Gap Analysis - Service Implementation

## Executive Summary

Analyzing the requirements (REQ-A001 through REQ-A011) against the current implementation and plan to identify gaps before Phase 3 implementation.

## Current State vs Requirements

### ✅ Already Implemented
- **REQ-A010** (partial): `create_dynamic_layer` → Implemented as `create_layer` service
  - Current: Creates layers via service
  - Gap: Not truly "dynamic" (temporary) - layers persist

### ⚠️ Partially Addressed via Switch Entity
These services are partially fulfilled by the switch entity's turn_on/turn_off methods:
- **REQ-A001**: `activate_layer` → Switch.turn_on() exists but no dedicated service
- **REQ-A002**: `deactivate_layer` → Switch.turn_off() exists but no dedicated service

### ❌ Not Implemented (11 services)
1. **REQ-A003**: `update_layer` - Update attributes without changing state
2. **REQ-A004**: `set_layer_priority` - Change priority of existing layer
3. **REQ-A005**: `lock_layer` - Prevent modifications
4. **REQ-A006**: `unlock_layer` - Allow modifications
5. **REQ-A007**: `force_layer` - Override priority system
6. **REQ-A008**: `recalculate_zone` - Force immediate recalculation
7. **REQ-A009**: `reset_zone` - Deactivate all layers except base
8. **REQ-A011**: `apply_preset` - Configure multiple layers atomically

## Plan vs Requirements Gaps

### 1. Service Naming Inconsistencies
- **Requirements**: Uses underscores (e.g., `activate_layer`)
- **Plan**: Mixed naming (some with underscores, some without)
- **Action**: Standardize on underscore naming per HA conventions

### 2. Missing Service Pattern Details

#### Entity Targeting Pattern
The plan shows entity registry pattern but doesn't address:
- How to handle multiple zones in a single service call
- Error handling when entity doesn't exist
- Validation of entity domain/platform

#### Atomic Operations
- **REQ-A011** requires atomic preset application
- Plan doesn't specify transaction/rollback mechanism
- Need to ensure all-or-nothing behavior

### 3. State Management Gaps

#### Lock/Unlock Mechanism
- Calculator checks `locked` flag
- No coordinator method to set/unset lock
- Need thread-safe lock management

#### Force Flag Implementation
- Calculator supports `force` flag
- No service to set/unset force
- Need to prevent multiple force flags

### 4. Missing Architectural Patterns

#### Service Response Pattern
```python
# Not specified in plan:
return {
    "success": bool,
    "entity_id": str,
    "previous_state": dict,
    "new_state": dict,
    "errors": list
}
```

#### Validation Pipeline
```python
# Need comprehensive validation:
1. Service schema validation (voluptuous)
2. Entity existence validation
3. Permission validation (locked layers)
4. Business logic validation (conflicts)
5. Capability validation (light features)
```

### 5. Advanced Features Not Specified

#### Preset System
- Where are presets stored? (config entry options? separate file?)
- Preset schema definition
- Preset inheritance/composition
- Built-in vs user presets

#### Batch Operations
- Apply service to multiple zones
- Bulk layer updates
- Zone synchronization

## Critical Implementation Decisions Needed

### 1. Service Registration Architecture

**Option A: Single Registration Point**
```python
# In __init__.py async_setup_entry()
if len(hass.data[DOMAIN]) == 1:  # First zone
    register_all_services(hass)
```

**Option B: Lazy Registration**
```python
# Register on first use
@callback
def ensure_services_registered(hass):
    if SERVICES_REGISTERED not in hass.data[DOMAIN]:
        register_all_services(hass)
        hass.data[DOMAIN][SERVICES_REGISTERED] = True
```

### 2. Service Target Resolution

**Option A: Entity-Based** (current approach)
```yaml
service: lighting_manager.lock_layer
target:
  entity_id: switch.living_room_manual_layer
```

**Option B: Zone + Layer Specification**
```yaml
service: lighting_manager.lock_layer
data:
  zone_id: living_room
  layer_id: manual
```

**Option C: Hybrid Approach**
```yaml
# Support both patterns
service: lighting_manager.lock_layer
target:
  entity_id: switch.living_room_manual_layer
# OR
data:
  zone_id: living_room
  layer_id: manual
```

### 3. State Modification Pattern

**Option A: Direct Coordinator Manipulation**
```python
# Service calls coordinator directly
coordinator.update_layer(layer_id, locked=True)
```

**Option B: Through Switch Entity**
```python
# Service calls switch method
switch_entity.async_lock()
# Switch updates coordinator
```

**Option C: Event-Driven**
```python
# Service fires event
hass.bus.async_fire("lighting_manager.lock_requested", {...})
# Coordinator listens and responds
```

## Recommended Implementation Order

### Phase 3.1: Core Layer Services (Priority: HIGH)
1. `update_layer` - Foundation for all modifications
2. `set_layer_priority` - Essential for priority management
3. `activate_layer` - Explicit activation with parameters
4. `deactivate_layer` - Explicit deactivation

### Phase 3.2: State Control Services (Priority: HIGH)
1. `lock_layer` - Prevent accidental changes
2. `unlock_layer` - Re-enable modifications
3. `force_layer` - Emergency override capability

### Phase 3.3: Zone Management (Priority: MEDIUM)
1. `recalculate_zone` - Debugging/refresh capability
2. `reset_zone` - Return to baseline state

### Phase 3.4: Advanced Features (Priority: LOW)
1. `apply_preset` - Complex but valuable
2. Dynamic layer improvements - Temporary/expiring layers

## Quality Standards Checklist

### For Each Service Implementation:
- [ ] Schema validation with voluptuous
- [ ] Input validation via validation.py
- [ ] Entity registry integration
- [ ] Proper async/await patterns
- [ ] Error handling with helpful messages
- [ ] Event firing for observability
- [ ] Logging at appropriate levels
- [ ] Service response with success/failure
- [ ] Update services.yaml with full documentation
- [ ] Test coverage for service handler
- [ ] Integration test with real entities
- [ ] Performance impact assessment

## Risk Assessment

### High Risk Areas
1. **Atomic Operations**: Preset application must be all-or-nothing
2. **Race Conditions**: Multiple services modifying same layer
3. **Lock State Corruption**: Lock/unlock must be bulletproof
4. **Performance**: Services triggering calculation storms

### Mitigation Strategies
1. **Transaction Pattern**: Implement rollback capability
2. **Service Queue**: Serialize modifications per zone
3. **Lock Verification**: Double-check lock state before/after
4. **Debouncing**: Already implemented, verify it works

## Production Standards Requirements

### Code Quality
- Type hints on all functions
- Docstrings following Google style
- Error messages with actionable information
- Logging that enables debugging without spam

### Testing Requirements
- Unit tests for each service handler
- Integration tests for service chains
- Performance tests for bulk operations
- Failure mode testing (locked layers, missing entities)

### Documentation
- services.yaml with complete descriptions
- Examples for each service
- Migration guide from switch operations
- Troubleshooting guide for common issues

## Conclusion

The Phase 3 implementation requires 11 new services with complex state management and coordination. The architecture is solid, but careful attention to:
1. Atomic operations for presets
2. Lock/force state management
3. Service response patterns
4. Error handling and recovery

will be critical for maintaining the high quality standard established in Phases 1-2.