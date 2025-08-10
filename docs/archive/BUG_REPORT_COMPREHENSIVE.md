# Comprehensive Bug Report - Lighting Manager Integration

## Critical Issues (Must Fix)

### 1. 🔴 **Config Flow Initialization Bug**
**File:** `config_flow.py`, line 128
**Issue:** `OptionsFlowHandler.__init__` doesn't pass `config_entry` to parent
```python
# WRONG:
super().__init__()
# CORRECT:
super().__init__(config_entry)
```
**Impact:** Options flow may not initialize properly

### 2. 🔴 **Duplicate Adaptive Sensor Creation**
**File:** `adaptive_sensor.py`
**Issue:** Contains its own `async_setup_entry` function while `sensor.py` also creates it
**Fix:** Remove the entire `async_setup_entry` function from `adaptive_sensor.py`
**Impact:** Creates duplicate sensor entities

### 3. 🔴 **Mutable State Reference in Coordinator**
**File:** `coordinator.py`, line ~139
**Issue:** `data` property returns direct reference to `self.layers`, not a copy
```python
"layers": self.layers,  # Direct reference, not copy!
```
**Impact:** External code can mutate internal state, bypassing validation
**Fix:** Return deep copy: `"layers": copy.deepcopy(self.layers)`

### 4. 🔴 **Race Condition in Adaptive Setup**
**File:** `coordinator.py`, line ~491
**Issue:** Uses fixed `await asyncio.sleep(2)` to wait for sensor
```python
# Wait a bit for sensor to be created
await asyncio.sleep(2)
```
**Impact:** Sensor may not be ready, or unnecessary delay
**Fix:** Use event listening or polling with timeout

## High Priority Issues

### 5. 🟠 **Missing Top-Level Error Handler**
**File:** `coordinator.py`, `_async_update_data` method
**Issue:** No try-except around main calculation/application logic
**Impact:** Unhandled exception would crash update loop
**Fix:** Add try-except around entire method body

### 6. 🟠 **StopIteration Risk in Conflict Handler**
**File:** `coordinator.py`, line ~381
**Issue:** `next()` without default when finding winning layer data
```python
winning_data = next(
    (l for l in all_layers if l.get("layer_id") == winning_layer),
    None  # ADD THIS DEFAULT
)
```

### 7. 🟠 **Type Safety in Calculator Sorting**
**File:** `calculator.py`, sorting logic
**Issue:** Non-numeric priority values would cause TypeError
**Impact:** Crash during calculation if priority is string
**Fix:** Validate priority type or add try-except

### 8. 🟠 **Missing Brightness Bounds Check**
**File:** `light_control.py`
**Issue:** No validation that brightness is 0-255
**Fix:** Add clamping:
```python
brightness = max(0, min(255, final_state[ATTR_BRIGHTNESS]))
```

## Medium Priority Issues

### 9. 🟡 **Color Temperature Handling**
**File:** `light_control.py`
**Issue:** Out-of-range color temps cause attribute to be skipped
**Better:** Clamp to light's supported range instead of skipping

### 10. 🟡 **Race Condition in Service Handlers**
**File:** `services.py`
**Issue:** Concurrent service calls to same zone could conflict
**Fix:** Add per-zone locking mechanism

### 11. 🟡 **Entity Removal Race Condition**
**File:** `services.py`, `_get_switch_entities`
**Issue:** Entity could be removed between registry and state checks
**Fix:** Tighten validation sequence

### 12. 🟡 **Timer Usage Pattern**
**File:** `coordinator.py`
**Issue:** Uses `hass.loop.call_later` (outdated pattern)
**Better:** Use `hass.helpers.event.async_call_later`

## Low Priority / Best Practices

### 13. 🟢 **Service Handler Re-entrancy**
**File:** `services.py`, `handle_unforce_layer`
**Issue:** Modifies `call.data` and calls another handler
**Better:** Extract common logic to shared function

### 14. 🟢 **Missing Available Check**
**File:** `switch.py`, `is_on` property
**Issue:** Returns state even when entity unavailable
**Better:** Check `self.available` first

### 15. 🟢 **Coordinator Retrieval Error Handling**
**File:** `services.py`, `_get_zone_coordinator`
**Issue:** No internal error handling
**Better:** Add try-except for robustness

## Quick Fixes Script

```python
# Apply these fixes to resolve critical issues:

# 1. config_flow.py - Line 128
# Change: super().__init__()
# To: super().__init__(config_entry)

# 2. adaptive_sensor.py - Remove lines 292-308 (entire async_setup_entry function)

# 3. coordinator.py - Line 139
# Add import at top: import copy
# Change: "layers": self.layers,
# To: "layers": copy.deepcopy(self.layers),

# 4. coordinator.py - Replace sleep with proper waiting:
# Instead of: await asyncio.sleep(2)
# Use entity registry listener or polling loop with timeout
```

## Testing After Fixes

1. **Test adaptive sensor:** Enable adaptive, verify only ONE sensor created
2. **Test config flow:** Modify zone options, verify they save correctly  
3. **Test concurrent updates:** Rapidly change multiple layers
4. **Test with invalid data:** Send non-numeric priority via service call
5. **Test light bounds:** Send brightness >255 or <0
6. **Test unavailable lights:** Disconnect a light, verify graceful handling

## Recommendation Priority

Fix issues 1-4 immediately as they cause functional problems.
Issues 5-8 should be addressed soon for stability.
Issues 9-15 can be addressed during refactoring.