# Layer Conditions System Design

## Overview
Layer conditions determine when a layer should automatically activate or deactivate based on Home Assistant entity states. This transforms layers from manual switches into intelligent, context-aware automation layers.

## Condition Structure

### Simple State Condition
```python
{
    "entity_id": "binary_sensor.living_room_motion",
    "state": "on"
}
```

### Numeric Comparison
```python
{
    "entity_id": "sensor.outdoor_lux",
    "below": 100
}
```

### Complex Conditions
```python
{
    "conditions": [
        {
            "entity_id": "media_player.tv",
            "state": "playing"
        },
        {
            "entity_id": "sun.sun",
            "state": "below_horizon"
        }
    ],
    "condition_type": "and"  # all must match (default)
    # or "condition_type": "or"  # any can match
}
```

## Implementation Plan

### Phase 1: Condition Evaluation Engine
Create a new module `condition_evaluator.py` that:
1. Evaluates conditions against current HA state
2. Returns True/False for layer activation
3. Handles missing entities gracefully
4. Supports multiple condition types

### Phase 2: Coordinator Integration
Update `coordinator.py` to:
1. Track entities referenced in conditions
2. Subscribe to their state changes
3. Re-evaluate conditions when tracked entities change
4. Auto-activate/deactivate layers based on conditions

### Phase 3: Service Enhancement
Update services to:
1. Allow setting conditions via service calls
2. Validate condition structure
3. Report which conditions are met/unmet

## Condition Types

### State Conditions
```python
{
    "entity_id": "light.kitchen",
    "state": "on"  # Exact match
}
```

### Numeric Conditions
```python
{
    "entity_id": "sensor.temperature",
    "above": 20,
    "below": 25  # Range: 20 < value < 25
}
```

### Attribute Conditions
```python
{
    "entity_id": "climate.thermostat",
    "attribute": "temperature",
    "above": 22
}
```

### Time Conditions
```python
{
    "after": "sunset",  # or "07:00:00"
    "before": "sunrise"  # or "23:00:00"
}
```

### Template Conditions (Advanced)
```python
{
    "template": "{{ states('sensor.temperature')|float > 25 and is_state('input_boolean.vacation_mode', 'off') }}"
}
```

## Condition Evaluation Logic

```python
def evaluate_conditions(hass, conditions):
    """Evaluate if all conditions are met."""
    if not conditions:
        return True  # No conditions = always active
    
    condition_type = conditions.get("condition_type", "and")
    condition_list = conditions.get("conditions", [conditions])
    
    results = []
    for condition in condition_list:
        result = evaluate_single_condition(hass, condition)
        results.append(result)
    
    if condition_type == "and":
        return all(results)
    elif condition_type == "or":
        return any(results)
    else:
        return False
```

## Auto-Activation Behavior

### When Conditions Become True
1. Layer automatically sets `is_on: true`
2. Source is set to `"condition_met"`
3. EVENT_LAYER_ACTIVATED fires with reason

### When Conditions Become False
1. Layer automatically sets `is_on: false`
2. Source is set to `"condition_unmet"`
3. EVENT_LAYER_DEACTIVATED fires with reason

### Manual Override
- If user manually activates layer, conditions are ignored
- If user manually deactivates layer, it stays off until:
  - Manually reactivated
  - Conditions become false then true again (reset)

## Examples

### Motion-Activated Layer
```python
"activity_layer": {
    "priority": 20,
    "brightness": 200,
    "conditions": {
        "entity_id": "binary_sensor.motion",
        "state": "on"
    }
}
```

### Movie Mode Layer
```python
"movie_layer": {
    "priority": 60,
    "brightness": 30,
    "color_temp": 500,
    "conditions": {
        "conditions": [
            {
                "entity_id": "media_player.tv",
                "state": "playing"
            },
            {
                "entity_id": "sun.sun",
                "state": "below_horizon"
            }
        ],
        "condition_type": "and"
    }
}
```

### Environmental Response Layer
```python
"dim_layer": {
    "priority": 15,
    "brightness": 100,
    "conditions": {
        "entity_id": "sensor.outdoor_illuminance",
        "below": 100
    }
}
```

## Benefits

1. **True Automation**: Layers activate without user intervention
2. **Context Awareness**: Lighting responds to environment
3. **Reduced Complexity**: No need for separate automations
4. **Centralized Logic**: All lighting logic in one place
5. **Override Capability**: Manual control still possible

## Testing Requirements

1. Condition evaluation with missing entities
2. State change subscription performance
3. Circular dependency prevention
4. Condition validation on save
5. Manual override behavior