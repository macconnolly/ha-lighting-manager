# Zone Setup Instructions for Lighting Manager

## Step 1: Create Zones via UI

You need to create 5 zones through the Home Assistant UI:

1. Go to **Settings → Devices & Services → Add Integration → Lighting Manager**
2. Create each zone with these exact names:
   - **Main Living** → Creates zone_id: `main_living`
   - **Kitchen Island** → Creates zone_id: `kitchen_island` (already exists)
   - **Bedroom Primary** → Creates zone_id: `bedroom_primary`
   - **Accent Spots** → Creates zone_id: `accent_spots`
   - **Recessed Ceiling** → Creates zone_id: `recessed_ceiling`

3. For each zone, select the appropriate lights:
   - **main_living**: 
     - light.living_room_couch_lamp
     - light.living_room_floor_lamp
     - light.office_desk_lamp
     - light.entryway_lamp
     - light.living_room_corner_accent
     - light.cradenza_accent
   
   - **kitchen_island**: 
     - light.kitchen_island_pendants
   
   - **bedroom_primary**: 
     - light.master_bedroom_table_lamps
     - light.master_bedroom_corner_accent
   
   - **accent_spots**: 
     - light.dining_room_spot_lights
     - light.living_room_spot_lights (if exists)
   
   - **recessed_ceiling**: 
     - light.kitchen_main_lights
     - light.living_room_hallway_lights

## Step 2: Verify Zone Creation

Check that all zones are created:
```yaml
# Developer Tools → States
# Look for: sensor.lighting_manager_zones
# Should show zone_ids: ["main_living", "kitchen_island", "bedroom_primary", "accent_spots", "recessed_ceiling"]
```

## Step 3: Use the Zone Configuration Service

Once zones exist, run this service call to configure them:

```yaml
service: script.configure_all_zones
data: {}
```

## Why Manual UI Creation?

The Lighting Manager integration uses Home Assistant's config flow system, which requires zones to be created through the UI. This ensures:
- Proper entity registration
- Correct device tracking
- Valid configuration storage
- Integration with Home Assistant's entity registry

Zones cannot be created programmatically through service calls - they must be added via the UI config flow.