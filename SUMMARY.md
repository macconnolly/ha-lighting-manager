# Lighting Manager Setup Summary

## Fixed Issues
1. **Config flow initialization** - Fixed OptionsFlow parent init
2. **Device page entities** - Added device_info to sensors
3. **Switch creation** - Added default "Manual" layer on zone creation
4. **Dynamic switch creation** - New layers now create switch entities automatically
5. **Performance optimizations** - Non-blocking light calls, smart event firing, shallow copies

## How to Use

### Creating a Zone
1. Go to Settings → Devices & Services → Add Integration
2. Search for "Lighting Manager"
3. Enter zone name and select lights
4. Zone will be created with a default "Manual" layer

### Viewing Zone Entities
1. Go to Settings → Devices & Services → Lighting Manager
2. Click on your zone device
3. You'll see:
   - `switch.<zone>_manual_layer` - Default layer switch
   - `sensor.<zone>_active_layer` - Shows which layer is active
   - More sensors for calculation state, conflicts, etc.

### Creating Additional Layers
Use Developer Tools → Services:
1. Service: `lighting_manager.create_layer` (if zone-based)
2. Or target the zone's switch and use layer services

### Controlling Lights
1. Turn on a layer switch to activate it
2. Higher priority layers override lower ones
3. Use services to update brightness, color, etc.

## Key Services
- `activate_layer` - Turn on a layer with settings
- `deactivate_layer` - Turn off a layer
- `update_layer` - Change layer settings
- `set_layer_priority` - Change which layer wins
- `lock_layer` / `unlock_layer` - Prevent changes
- `force_layer` - Override all priorities

## Testing
1. Create a zone
2. Check device page shows entities
3. Toggle the Manual layer switch
4. Watch lights respond
5. Create more layers via services
6. Test priority system