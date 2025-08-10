# Architecture Decision Records (ADRs)

## ADR-005: Pure External Activation Model
**Date**: 2025-01-08
**Status**: Accepted and Implemented

### Context
We initially attempted to add condition evaluation inside the package, allowing layers to have "smart" activation based on sensor states, time, etc. This would have made layers automatically activate when conditions were met.

### Decision
We decided to follow the **Pure External Approach** where:
- The package does NOT evaluate any conditions
- External automations handle ALL activation logic
- Layers only declare desired state ("if I win, set brightness to X")
- The package only determines which active layer wins based on priority

### Rationale
1. **Separation of Concerns**: The package should do ONE thing well - manage competing light states
2. **Architectural Purity**: Layers are pure state declarations, not automation entities
3. **Flexibility**: ANY external system can activate layers (automations, physical switches, voice, scenes)
4. **Simplicity**: No condition evaluation means less code, fewer bugs, easier testing
5. **Home Assistant Philosophy**: HA already has a powerful automation engine - don't duplicate it

### Consequences
**Positive:**
- Clean, maintainable architecture
- Calculator remains pure functional (no HA dependencies)
- Package is simpler and more focused
- Works with any automation system

**Negative:**
- Users must write external automations for conditional activation
- No "smart layers" out of the box

### Implementation
- Removed `condition_evaluator.py` entirely
- Removed condition tracking from coordinator
- Calculator only checks `is_on` flag
- Conditions can still be stored as data but are not evaluated

## ADR-001: Switch Platform for Layers (Updated)
**Original Decision**: Use switch entities to represent layers
**Remains Valid**: Switches are perfect for external control - automations can turn them on/off

## ADR-002: Pure Functional Calculator (Reinforced)
**Original Decision**: Calculator must be pure function
**Strengthened**: Calculator has NO Home Assistant imports, NO condition logic, just pure priority math

## ADR-003: 100ms Debounce Window (Unchanged)
**Original Decision**: Debounce for 100ms before calculation
**Remains Valid**: Still prevents calculation storms

## ADR-004: Coordinator-Centric State Management (Clarified)
**Original Decision**: Coordinator holds all state
**Clarified**: Coordinator stores state but does NOT evaluate conditions or make activation decisions

## Core Principles (Updated)

### What Each Component Does

1. **Switches (Views)**
   - Display layer configuration
   - Show on/off state (set by external systems)
   - Store settings like brightness, color, priority
   - NO logic, NO automation, NO decisions

2. **Coordinator (Orchestration)**
   - Single source of truth for layer state
   - Triggers calculations when state changes
   - Manages persistence
   - NO condition evaluation, NO activation logic

3. **Calculator (Logic)**
   - Pure priority comparison
   - Determines winning layer from active (is_on=True) layers
   - Handles force flags and locks
   - NO Home Assistant dependencies, NO condition checks

4. **Controller (Application)**
   - Applies winning state to physical lights
   - Handles light capabilities
   - NO decision making

### The Flow

```
External System Decision:
"It's dark and motion detected, activate motion layer"
                ↓
Sets: switch.living_room_motion_layer = ON
                ↓
Coordinator: "State changed, trigger calculation"
                ↓
Calculator: "Of all ON layers, motion (priority 20) wins"
                ↓
Controller: "Apply brightness=200 to lights"
```

### What We DON'T Do
- ❌ Evaluate conditions inside the package
- ❌ Decide when to activate layers
- ❌ React directly to sensors
- ❌ Implement automation logic
- ❌ Create "smart" self-activating layers

### What We DO Excellently
- ✅ Store layer state declarations
- ✅ Determine priority-based winners
- ✅ Apply states atomically to lights
- ✅ Provide a clean API for external control
- ✅ Maintain architectural purity