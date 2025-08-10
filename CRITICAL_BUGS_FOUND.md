# Critical Bugs Found - Must Fix Before Running

## 🔴 CRITICAL BUGS (Will cause immediate crashes)

### 1. **switch.py - Missing @property decorator**
**Line 114**: `entity_id` method missing @property decorator
```python
# WRONG (current):
def entity_id(self) -> str:

# CORRECT:
@property
def entity_id(self) -> str:
```

### 2. **switch.py - Missing slugify import**
**Top of file**: Need to import slugify
```python
# ADD:
from homeassistant.util import slugify
```
**Lines 108, 116**: Use slugify for entity IDs
```python
# Line 108 - CHANGE TO:
self._attr_unique_id = f"{slugify(coordinator.zone_id)}_{slugify(layer_id)}"

# Line 116 - CHANGE TO:
return f"switch.{slugify(self.coordinator.zone_id)}_{slugify(self.layer_id)}_layer"
```

### 3. **sensor.py - Missing device_info property**
**Line 51**: References non-existent `coordinator.device_info`
```python
# REMOVE THIS LINE:
self._attr_device_info = coordinator.device_info
```

### 4. **services.py - Incorrect entity access**
**Lines 200-201**: Wrong way to get switch entity
```python
# WRONG (current):
component = hass.data["switch"]
entity = component.get_entity(entity_id)

# CORRECT:
# Just use the state, we don't need the entity object
state = hass.states.get(entity_id)
if not state:
    continue
```

### 5. **light_control.py - Wrong return type**
**Line 275**: Method should return bool, not None
```python
# CHANGE:
async def _apply_with_reduced_features(self, entity_id: str, final_state: dict[str, Any]) -> None:

# TO:
async def _apply_with_reduced_features(self, entity_id: str, final_state: dict[str, Any]) -> bool:
```
**Line 312**: Add return statement
```python
# ADD at end of method:
return True  # Successfully applied
```

## 🟠 HIGH PRIORITY BUGS (Will cause errors in certain conditions)

### 6. **__init__.py - Protected member access**
**Line 143**: Accessing private _light_controller
```python
# Create public method in coordinator instead of accessing _light_controller
```

### 7. **services.py - Missing hass parameter**
**Line 502**: Missing hass parameter in call
```python
# WRONG:
return await handle_force_layer(call)

# CORRECT:
return await handle_force_layer(hass, call, switches)
```

### 8. **sensor.py - Wrong config key**
**Line 332**: Should use constant
```python
# CHANGE:
if entry.options.get("adaptive_enabled", False):

# TO:
if entry.options.get(CONF_ADAPTIVE_ENABLED, False):
```

## Quick Fix Script

```bash
# Fix 1: Add @property to switch.py
sed -i '114s/def entity_id/@property\n    def entity_id/' switch.py

# Fix 2: Add slugify import to switch.py
sed -i '10a from homeassistant.util import slugify' switch.py

# Fix 3: Remove device_info line from sensor.py
sed -i '51d' sensor.py

# Fix 5: Fix return type in light_control.py
sed -i '275s/-> None:/-> bool:/' light_control.py
sed -i '312a\        return True' light_control.py
```

## Files That Need Manual Fixes

1. **switch.py** - Lines 108, 116 (add slugify calls)
2. **services.py** - Lines 200-201 (fix entity access)
3. **services.py** - Line 502 (add hass parameter)
4. **sensor.py** - Line 332 (use constant)

## Testing After Fixes

1. Restart Home Assistant
2. Create a zone - verify switch entities have valid IDs
3. Enable adaptive - verify sensor creation works
4. Test service calls - verify they execute without errors
5. Turn lights on/off - verify light control works