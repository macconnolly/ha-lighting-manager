# 🚨 CRITICAL HANDOFF CONTEXT - LIGHTING MANAGER v5 🚨

## ⚡ IMMEDIATE NEXT TASK: Complete Revision of /packages/ Directory

The `/packages/` directory contains 12 YAML files that are **COMPLETELY OUTDATED** and violate our new architecture:
- They use the OLD service calls (layer_name without layer_id)
- They create layers incorrectly
- They don't follow the single entry point pattern
- They conflict with our production-grade refactoring

### Files Requiring Complete Rewrite:
```
packages/
├── lighting_modifier_activities.yaml    # Activity-based modifiers
├── lighting_modifier_circadian.yaml     # Circadian rhythm modifiers
├── lighting_modifier_climate.yaml       # Climate-based adjustments
├── lighting_modifier_manual_override.yaml # Manual override handling
├── lighting_modifier_motion.yaml        # Motion detection layers
├── lighting_modifier_presence.yaml      # Presence-based control
├── lighting_modifier_weather.yaml       # Weather modifiers
├── lighting_startup_delay.yaml          # Startup delay logic
├── lighting_zones_auto_create.yaml      # Auto zone creation
├── lighting_zones_auto_setup.yaml       # Auto setup logic
├── lighting_zones_config.yaml           # Zone configuration
└── lighting_zones_setup.yaml            # Zone setup helpers
```

## 🏗️ CURRENT ARCHITECTURE STATUS (GRADE: A-)

### Sacred Principles (NON-NEGOTIABLE):
1. **Single Entry Point**: ALL layer modifications MUST use `layer_manager.set_layer(layer_id, data)`
2. **Event-Driven**: Service handlers call set_layer() → LayerManager notifies → Coordinator saves/recalculates
3. **Separation of Concerns**: Each component has EXACTLY ONE responsibility
4. **No Startup Calculation**: System reads current light state as baseline
5. **Stateless Entities**: All entities read from coordinator.data

### Component Responsibilities:
| Component | Single Responsibility | What it MUST NOT do |
|-----------|----------------------|---------------------|
| **LayerManager** | CRUD operations & persistence | Calculate state, control lights |
| **StateCalculator** | Pure functional calculation | Import HomeAssistant, have side effects |
| **LightController** | Hardware control with circuit breaker | Store layer data, calculate state |
| **ChangeDetector** | Manual override detection (5 sec) | Modify layers directly |
| **AdaptiveProvider** | Reference values only | Create layers, modify state |
| **ZoneStateMachine** | Zone state transitions | Control lights, modify layers |
| **ZoneCoordinator** | Pure orchestration ONLY | Contain ANY business logic |

## 📝 CRITICAL SERVICE CHANGES (BREAKING)

### OLD (WRONG) Service Call Format:
```yaml
service: lighting_manager.set_layer
data:
  zone_id: living_room
  layer_name: "Weather Boost"  # This was primary identifier
  layer_type: modifier
  priority: 70
```

### NEW (CORRECT) Service Call Format:
```yaml
service: lighting_manager.set_layer
data:
  zone_id: living_room
  layer_id: weather_boost  # REQUIRED - primary identifier
  layer_name: "Weather Boost"  # OPTIONAL - display name only
  layer_type: modifier
  priority: 70
```

## 🔄 DATA FLOW ARCHITECTURE

```
User Action → Service Call → set_layer(layer_id, data)
                                       ↓
                            LayerManager.set_layer()
                                       ↓
                            Returns (success, action)
                                       ↓
                            Notify listeners via _notify_listeners()
                                       ↓
                    Coordinator._on_layers_changed() triggered
                                       ↓
                    Saves if pending + Schedules recalculation
                                       ↓
                    100ms debounced _async_update_data()
                                       ↓
                    Orchestrates all components in sequence
                                       ↓
                    All entities read from coordinator.data
```

## ✅ WHAT'S BEEN COMPLETED

### Core Refactoring (100% Complete):
1. ✅ All 6 new component files created
2. ✅ Coordinator rewritten as pure orchestrator
3. ✅ LayerManager.set_layer() as single entry point
4. ✅ All service handlers use set_layer()
5. ✅ Switch entities are stateless views
6. ✅ ChangeDetector uses set_layer()
7. ✅ Default layer creation on first setup
8. ✅ Diagnostic sensor with size limits
9. ✅ Event-driven save/recalc in coordinator
10. ✅ Race condition fixed in manual detection

### Files Modified:
- `coordinator.py`: Pure orchestrator, default layers, event-driven saves
- `layer_manager.py`: Single entry point set_layer() method
- `services.py`: ALL handlers use set_layer() (9 fixes)
- `switch.py`: async_turn_on/off use set_layer()
- `change_detector.py`: create_manual_override uses set_layer()
- `sensor.py`: Size-limited diagnostic attributes
- `__init__.py`: No startup calculation
- `services.yaml`: layer_id REQUIRED, update_layer deprecated

## 🚫 COMMON MISTAKES TO AVOID

### ❌ DO NOT:
```python
# WRONG - Direct update
coordinator.layer_manager.update_layer(layer_id, data)

# WRONG - Direct create
coordinator.layer_manager.create_layer(layer_id, data)

# WRONG - Manual save
await coordinator.layer_manager.save()

# WRONG - Manual recalculation
coordinator.schedule_recalculation()
```

### ✅ ALWAYS DO:
```python
# CORRECT - Single entry point
success, action = coordinator.layer_manager.set_layer(layer_id, data)

# Let the coordinator's listener handle save/recalc automatically
```

## 📦 PACKAGE FILES UPDATE REQUIREMENTS

Each package file needs:

### 1. Update ALL Service Calls:
```yaml
# OLD (WRONG)
- service: lighting_manager.set_layer
  data:
    zone_id: "{{ zone }}"
    layer_name: "Motion Detected"
    
# NEW (CORRECT)
- service: lighting_manager.set_layer
  data:
    zone_id: "{{ zone }}"
    layer_id: motion_detected  # REQUIRED
    layer_name: "Motion Detected"  # Optional
```

### 2. Use Proper Layer IDs:
- Layer IDs should be snake_case: `weather_boost`, `motion_detected`, `presence_home`
- Layer names are display only: "Weather Boost", "Motion Detected", "Presence Home"

### 3. Modifier Layers Pattern:
```yaml
layer_type: modifier  # or multiplier
priority: 60-80  # Modifiers typically mid-range
brightness_pct_delta: 20  # For brightness adjustment
color_temp_kelvin_delta: -500  # For color adjustment
```

### 4. Absolute Layers Pattern:
```yaml
layer_type: absolute  # Default if not specified
priority: 0-100  # Higher wins
brightness: 255  # 0-255
color_temp: 370  # Mireds
```

## 🎯 SPECIFIC PACKAGE FIXES NEEDED

### lighting_zones_auto_create.yaml:
- Remove any startup calculation triggers
- Use set_layer with layer_id for default layers
- Don't create adaptive as a layer (it's reference only)

### lighting_modifier_*.yaml files:
- ALL must use layer_id as primary identifier
- Use proper modifier attributes (brightness_pct_delta, not brightness)
- Ensure idempotent behavior (create if not exists, update if exists)

### lighting_startup_delay.yaml:
- Should be DELETED - we don't apply state on startup anymore
- System reads current light state as baseline

### lighting_zones_config.yaml:
- Update to use new service format
- Ensure default layers match coordinator.async_load() pattern

## 🔍 TESTING REQUIREMENTS

After updating packages, verify:
1. `set_layer` service creates new layers with layer_id
2. `set_layer` service updates existing layers (idempotent)
3. Manual light changes create override within 5 seconds
4. Circuit breaker opens after 3 failures
5. All internal state visible in diagnostic sensor
6. No layers activate on startup
7. Manual override expires after 2 hours

## ⚠️ GEMINI REVIEW FEEDBACK (A- Grade)

### Strengths Identified:
- Single entry point perfectly implemented
- Event-driven architecture exemplary
- Separation of concerns sacred and maintained
- Performance optimizations well done

### Minor Issues (Already Fixed):
- ✅ Race condition in manual detection (FIXED)
- ⚠️ Zone lookup could be O(1) instead of O(n) (minor optimization)

## 🚀 NEXT AGENT INSTRUCTIONS

1. **READ THIS ENTIRE DOCUMENT FIRST**
2. **Review each package file** for outdated service calls
3. **Update ALL service calls** to use layer_id (REQUIRED)
4. **Test each package** after updating
5. **Delete lighting_startup_delay.yaml** entirely
6. **Document changes** in each file's header

### Command to Start:
```bash
ls -la packages/
grep -r "layer_name" packages/  # Find all old service calls
```

## 📚 KEY REFERENCE FILES

| File | Purpose | Critical Info |
|------|---------|---------------|
| `/CLAUDE.md` | Architecture rules | NON-NEGOTIABLE principles |
| `/PLAN.md` | Implementation spec | Lines 1847-1923 (set_layer) |
| `layer_manager.py:112-131` | set_layer() method | Single entry point |
| `coordinator.py:183-197` | _on_layers_changed | Event-driven saves |
| `services.yaml:15-21` | Service definition | layer_id REQUIRED |

## 🎖️ SUCCESS CRITERIA

The package update is complete when:
- ZERO instances of update_layer() or create_layer() remain
- ALL service calls use layer_id as required field
- NO startup calculations or applies
- Modifiers use correct attributes (*_delta, not absolute values)
- Each file has a header comment with update date and compliance note

---
**Generated**: 2025-01-11
**Branch**: v5
**Architecture Grade**: A-
**Next Task**: Complete package directory revision
**Estimated Time**: 2-3 hours

Remember: The architecture is COMPLETE. We're updating YAML configs only, not changing code architecture.