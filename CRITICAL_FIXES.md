# Critical Fixes Required - Apply Immediately

## Fix 1: Config Flow Options Handler
**File:** `custom_components/lighting_manager/config_flow.py`
**Line:** 128

```python
# CHANGE THIS:
def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    """Initialize options flow."""
    # Parent class handles config_entry assignment now
    super().__init__()

# TO THIS:
def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    """Initialize options flow."""
    super().__init__(config_entry)
```

## Fix 2: Remove Duplicate Sensor Setup
**File:** `custom_components/lighting_manager/adaptive_sensor.py`
**Action:** DELETE lines 21-36 (the entire `async_setup_entry` function)

```python
# DELETE THIS ENTIRE FUNCTION:
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up adaptive sensor for a zone."""
    zone_id = config_entry.data["zone_id"]
    zone_name = config_entry.data.get("zone_name", zone_id)
    
    # Only create sensor if adaptive is enabled
    if config_entry.options.get("adaptive_enabled", False):
        async_add_entities([AdaptiveLightFactorSensor(zone_id, zone_name, config_entry)])
```

## Fix 3: Prevent State Mutation
**File:** `custom_components/lighting_manager/coordinator.py`
**Line:** Add import at top:
```python
import copy
```

**Line:** ~139, change:
```python
# CHANGE THIS:
"layers": self.layers,  # Direct reference, not copy!

# TO THIS:
"layers": copy.deepcopy(self.layers),  # Safe copy
```

## Fix 4: Remove Race Condition
**File:** `custom_components/lighting_manager/coordinator.py`
**Line:** ~491

Replace the sleep with a retry mechanism:
```python
# REPLACE THIS:
await asyncio.sleep(2)

# WITH THIS:
# Try to get sensor with retries
for attempt in range(10):  # Try for up to 5 seconds
    sensor_state = self.hass.states.get(sensor_id)
    if sensor_state and sensor_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        break
    if attempt < 9:  # Don't sleep on last attempt
        await asyncio.sleep(0.5)
    else:
        _LOGGER.warning("Adaptive sensor %s not ready after 5 seconds", sensor_id)
```

## Fix 5: Add Error Handler
**File:** `custom_components/lighting_manager/coordinator.py`
**Function:** `_async_update_data`

Wrap the entire method body in try-except:
```python
async def _async_update_data(self) -> dict[str, Any]:
    """Calculate new state and apply to lights."""
    try:
        # ... existing code ...
    except Exception as err:
        _LOGGER.error("Error in update cycle for zone %s: %s", self.zone_id, err)
        # Return last known good state
        if self.data:
            return self.data
        # Or minimal safe state
        return {
            "layers": self.layers,
            "error": str(err),
            "zone_id": self.zone_id,
        }
```

## Quick Test After Fixes

1. Restart Home Assistant
2. Create a zone with adaptive enabled
3. Check logs for errors
4. Verify only ONE adaptive sensor created
5. Test changing layers rapidly
6. Test with a light disconnected

These fixes address the most critical issues that could cause crashes or incorrect behavior.