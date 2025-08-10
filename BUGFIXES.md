# Bug Fixes Applied

## Issues Fixed

### 1. ✅ AttributeError: property 'data' has no setter
**Error**: `AttributeError: property 'data' of 'ZoneCoordinator' object has no setter`
**Fix**: 
- Changed `data` from a read-only `@property` to a regular attribute
- Created `_get_current_data()` method to generate the data
- Updated `_async_update_data()` to set `self.data` properly

### 2. ✅ Deprecated ATTR_COLOR_TEMP
**Warning**: `The deprecated constant ATTR_COLOR_TEMP was used from lighting_manager`
**Fix**:
- Removed import of `ATTR_COLOR_TEMP` from `homeassistant.components.light`
- Using our own `ATTR_COLOR_TEMP` constant from `const.py`

### 3. ✅ Config Entry Warning
**Warning**: `Detected that custom integration 'lighting_manager' sets option flow config_entry explicitly`
**Fix**:
- Removed explicit `self.config_entry = config_entry` assignment
- Added `super().__init__()` call to let parent handle it

### 4. ✅ ContextVar Warning
**Warning**: `Detected that custom integration 'lighting_manager' relies on ContextVar`
**Fix**:
- Added `config_entry=entry` parameter to `super().__init__()` in coordinator

## Files Modified

1. `coordinator.py`:
   - Changed data property to regular attribute
   - Added `_get_current_data()` method
   - Added `config_entry` parameter to parent init

2. `light_control.py`:
   - Removed ATTR_COLOR_TEMP import from HA
   - Added import from our const.py

3. `config_flow.py`:
   - Removed explicit config_entry assignment
   - Added super().__init__() call

## Testing Required

After uploading these fixes:
1. Restart Home Assistant
2. Check logs for any remaining errors
3. Create a test zone
4. Verify all entities are created
5. Test creating and activating layers