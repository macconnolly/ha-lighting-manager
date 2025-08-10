# Implementation Guardrails & Checkpoints

## 🚨 RED FLAGS - Stop Immediately If You See:

### 1. Logic Creeping Into Wrong Layers
❌ **VIOLATION**: Switch entity calculating its own priority winner
❌ **VIOLATION**: Coordinator doing brightness math
❌ **VIOLATION**: Calculator calling Home Assistant services
✅ **CORRECT**: Each component only does its ONE job

### 2. Cross-Zone Communication
❌ **VIOLATION**: Zone A reading state from Zone B
❌ **VIOLATION**: Shared state variables between zones
❌ **VIOLATION**: Global coordinator managing multiple zones
✅ **CORRECT**: Each zone is an island

### 3. Hidden State
❌ **VIOLATION**: Storing data in class variables not exposed as attributes
❌ **VIOLATION**: Internal dictionaries tracking state
❌ **VIOLATION**: State that can't be seen in Developer Tools
✅ **CORRECT**: If it exists, it's visible in the UI

### 4. Polling Patterns
❌ **VIOLATION**: Periodic timers checking state
❌ **VIOLATION**: While loops waiting for conditions
❌ **VIOLATION**: Scheduled updates without state changes
✅ **CORRECT**: Everything is reactive to events

## 📋 Phase Completion Checklists

### Before Moving from Phase 1 → Phase 2:
- [ ] Can create a switch entity with: `switch.living_room_test_layer`
- [ ] Switch shows all attributes in Developer Tools
- [ ] Switch survives HA restart (RestoreEntity works)
- [ ] Config flow creates zone successfully
- [ ] Zone appears as device in Settings
- [ ] NO calculation logic exists yet

### Before Moving from Phase 2 → Phase 3:
- [ ] Calculator is a pure function (testable with just Python)
- [ ] Coordinator successfully detects switch changes
- [ ] 100ms debounce measurably working
- [ ] Lights actually change when switch toggled
- [ ] Can trace: Switch change → Coordinator → Calculator → Lights
- [ ] NO services exist yet (only native switch.turn_on/off)

### Before Moving from Phase 3 → Phase 4:
- [ ] All services work via Developer Tools
- [ ] Services properly target switch entities
- [ ] Create_layer generates correct entity IDs
- [ ] No service contains calculation logic
- [ ] Services only manipulate data, never calculate

## 🧪 Smoke Tests After Each Component

### After `switch.py`:
```python
# This should work in Python console:
switch = LayerSwitch(...)
assert switch.is_on in [True, False]
assert switch.extra_state_attributes["priority"] == 50
# No references to coordinator or calculator!
```

### After `calculator.py`:
```python
# This should work without ANY HA imports:
calc = LightingCalculator()
layers = [
    {"entity_id": "switch.test_1", "priority": 10, "brightness": 100},
    {"entity_id": "switch.test_2", "priority": 20, "brightness": 200}
]
result = calc.calculate_state(layers)
assert result["winning_layer"] == "switch.test_2"
# Pure Python, no HA dependencies!
```

### After `coordinator.py`:
```python
# Coordinator should have NO calculation logic:
coordinator = ZoneCoordinator(...)
# Search for these banned terms in coordinator.py:
assert "priority" not in coordinator_source  # Should not compare priorities
assert "force" not in coordinator_source     # Should not check force flags
assert "brightness" not in coordinator_source # Should not calculate brightness
```

## 🔍 Code Review Checklist

Before EVERY commit, ask:

1. **Single Responsibility**: Does this component do exactly ONE thing?
2. **Data Flow**: Can I trace data flow without any hidden steps?
3. **Dependencies**: Am I importing from the right modules only?
4. **State Visibility**: Is all state visible in the UI?
5. **Event-Driven**: Am I reacting to events, not polling?
6. **Pure Functions**: Are my calculations free of side effects?
7. **Proper Platform**: Am I using standard HA platforms correctly?

## 🏗️ Architecture Validation Commands

Run these regularly to verify architecture:

### Check Separation of Concerns:
```bash
# Calculator should not import from HA
grep -r "from homeassistant" calculator.py  # Should return nothing

# Switch should not import calculator
grep -r "calculator" switch.py  # Should return nothing

# Check for hidden state
grep -r "_state\|_cache\|_data" *.py | grep -v "extra_state_attributes"
```

### Check Event-Driven:
```bash
# Look for polling anti-patterns
grep -r "time.sleep\|while True\|async_timeout" *.py

# Verify event subscriptions
grep -r "async_track_state_change\|async_listen" coordinator.py
```

## 🚦 Go/No-Go Decision Points

### After Phase 1: Foundation
**GO if:**
- Switches appear in UI ✓
- Attributes visible ✓
- Survives restart ✓
- Clean separation ✓

**NO-GO if:**
- Any calculation logic exists
- Hidden state anywhere
- Cross-component dependencies

### After Phase 2: Orchestration
**GO if:**
- Lights respond to switches ✓
- Calculation is pure function ✓
- Debouncing works ✓
- No race conditions ✓

**NO-GO if:**
- Logic in wrong components
- State not visible
- Polling patterns exist

## 📊 Metrics to Track

### Performance Metrics:
- Switch toggle → Light change: Target < 200ms
- Calculator execution time: Target < 50ms for 20 layers
- Memory per zone: Target < 10MB

### Architecture Metrics:
- Lines of code in calculator.py with HA imports: Must be 0
- Number of state variables not in attributes: Must be 0
- Number of cross-zone references: Must be 0

## 🛑 STOP Conditions

**IMMEDIATELY STOP and reassess if:**

1. You find yourself adding a "quick fix" that violates separation
2. You need to add state that won't be visible in UI
3. You're adding polling because events aren't working
4. You're putting logic in switches to "simplify" things
5. You're sharing data between zones to "optimize"
6. Tests can't be written because of tight coupling
7. You can't explain the data flow in one sentence

## 🔄 Recovery Protocol

If architecture starts drifting:

1. **Stop all new feature work**
2. **Document the violation**
3. **Trace back to where drift started**
4. **Refactor to restore separation**
5. **Add test to prevent recurrence**
6. **Update guardrails with new check**

## 📝 Daily Implementation Checklist

Start each session:
- [ ] Review guardrails document
- [ ] Check current phase requirements
- [ ] Verify no red flags present

End each session:
- [ ] Run architecture validation commands
- [ ] Verify all smoke tests pass
- [ ] Check that no STOP conditions triggered
- [ ] Commit only if clean separation maintained

## 🎯 Success Criteria

You're on track if you can always answer YES to:
1. Can I unit test the calculator without HA?
2. Can I see all state in Developer Tools?
3. Can I trace events without hidden steps?
4. Can I explain each component's job in one sentence?
5. Does each zone work in complete isolation?

Remember: **It's better to stop and refactor early than to compound architectural debt!**