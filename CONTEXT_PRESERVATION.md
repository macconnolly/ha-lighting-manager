# CRITICAL CONTEXT PRESERVATION - Lighting Manager v4.0
## Read This After Compaction to Restore Full Understanding

### 🎯 Core Architecture - The Sacred Separation

```
Switches (Views) → Coordinator (State) → Calculator (Logic) → Controller (Application)
```

**CRITICAL RULE**: Switches are STATELESS VIEWS. Coordinator holds ALL state. Calculator is PURE FUNCTIONAL.

### 🔴 Architectural Decision: Pure External Activation

**We removed ALL condition evaluation from the package!**
- Deleted `condition_evaluator.py` entirely
- Removed entity tracking from coordinator
- Calculator only checks `is_on` flag
- **Why**: Package is a state management engine, NOT an automation engine
- External automations handle ALL activation logic

### 📁 Current Implementation Status

**Completed Phases (1-4):**
- ✅ Core architecture with coordinator pattern
- ✅ Pure functional calculator
- ✅ 12 services implemented
- ✅ 2 sensors per zone (not 7!)
- ✅ Store persistence
- ✅ Event system

**Key Files:**
- `coordinator.py` (467 lines) - Single source of truth
- `calculator.py` (303 lines) - Pure priority logic
- `switch.py` (266 lines) - Stateless layer views
- `light_control.py` (308 lines) - Apply to lights
- `services.py` + `services_phase3.py` - All 12 services
- `sensor.py` (335 lines) - 2 observability sensors

### 🚨 CRITICAL DISCOVERY: No Adaptive Implementation Exists!

**What We Found:**
- ❌ NO adaptive lighting calculation exists
- ❌ NO sun integration implemented  
- ❌ NO time-based profiles
- ❌ NO offset support in layers
- ✅ Config stores min/max values but NEVER USES THEM
- ✅ References to "base_adaptive" layer but NEVER CREATES IT

**This is a FUNDAMENTAL GAP - not a minor feature!**

**What SHOULD Exist:**
```python
# Zone-specific adaptive calculation (MISSING)
zone: "bedroom"
  brightness_min: 10
  brightness_max: 150
  → Adaptive should calculate: 80 (based on sun/time)

# Layer offset support (MISSING)
"movie_mode":
  brightness_offset: -80%  # Currently impossible - only absolute values work
  
# Result (CANNOT CURRENTLY ACHIEVE)
bedroom + movie = 16 (80 × 0.2)
```

**Current Reality:**
- Layers can only store absolute values (brightness: 100)
- No way to express relative offsets (brightness_offset: -50%)
- No adaptive baseline to offset from
- Config UI collects adaptive settings that go nowhere

### 💡 Key Insights from Discussion

1. **Layers are just state declarations** - they don't activate themselves
2. **External automations control is_on** - package never decides activation
3. **Conditions can be stored but not evaluated** - data only
4. **Layers should be applicable to multiple zones** - avoid redundancy
5. **Adaptive is zone-specific baseline** - other layers offset from it

### 🔧 What MUST Be Built (Not Just Polish!)

1. **Adaptive Lighting System (COMPLETELY MISSING)**
   - [ ] Create adaptive calculator module
   - [ ] Integrate with sun.sun entity
   - [ ] Calculate brightness/color based on time
   - [ ] Scale to zone-specific min/max ranges
   - [ ] Create base_adaptive layer automatically
   - [ ] Update adaptive values periodically
   
2. **Offset Support in Layers (FUNDAMENTAL CHANGE)**
   - [ ] Add brightness_offset field to layers
   - [ ] Add color_temp_offset field to layers  
   - [ ] Modify calculator to handle both absolute and relative
   - [ ] Calculator needs adaptive baseline as input
   - [ ] Support percentage offsets: "-50%"
   - [ ] Support absolute offsets: "+200"

3. **Cross-Zone Layer Application (ARCHITECTURAL ENHANCEMENT)**
   - [ ] Layer templates or shared definitions
   - [ ] Service to apply template to multiple zones
   - [ ] Per-zone overrides while using template

### 📊 Architecture Rules (NEVER VIOLATE)

1. **coordinator.data is @property** returning current state
2. **NO @callback on async state-modifying methods**
3. **Entity Registry for services**: Use `async_extract_referenced_entity_ids()`
4. **dt_util.now()** for timezone awareness, never datetime.now()
5. **Switches read from coordinator.data**, never store state

### 🎓 The User's Vision

The user wants a system where:
- Adaptive lighting provides zone-specific baseline
- Layers can modify that baseline with offsets
- Same layer definition works across zones
- Physical switches integrate naturally
- External automations handle all conditions

### ⚠️ Common Pitfalls to Avoid

1. **Don't add automation logic** - We tried adding conditions, removed it all
2. **Don't make layers smart** - They're just state declarations
3. **Don't track external entities** - That's automation engine's job
4. **Don't evaluate conditions** - Store them as data only
5. **Don't create cross-zone dependencies** - Zones are independent

### 🔄 Next Steps Priority

1. **Investigate current adaptive implementation** - Is it even there?
2. **Add offset support to layers** - brightness_offset, color_temp_offset
3. **Implement zone-specific adaptive ranges** - Per-zone min/max
4. **Create layer template system** - Apply same layer to multiple zones

### 🎯 Success Criteria

The system succeeds when:
- User can define "movie mode" once, apply everywhere
- Each zone respects its own brightness/color personality
- Adaptive provides intelligent baseline per zone
- Layers modify baseline with simple offsets
- External automations control everything

### 💭 Final Context

We discovered a fundamental gap: the current implementation doesn't support relative offsets or zone-specific adaptive ranges. This is a CORE requirement that needs implementation, not a nice-to-have. The user's mental model is:

**Adaptive Baseline (per-zone) + Layer Offset (universal) = Final State**

This is simpler and more powerful than absolute values only.