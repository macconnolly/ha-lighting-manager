# Recorder Configuration for Lighting Manager

## Overview
The Lighting Manager creates 2 sensors per zone:
1. **Active Layer Sensor** (`sensor.{zone}_active_layer`) - Tracks which layer is controlling lights
2. **Zone Status Sensor** (`sensor.{zone}_status`) - Diagnostic information for debugging

## Automatic Configuration
The Zone Status sensor is automatically marked as `diagnostic` which:
- Hides it from the main UI by default
- Excludes it from most dashboards
- Prevents it from cluttering entity lists

## Recommended Recorder Configuration
While the diagnostic sensor is hidden from UI, it still records history by default. For optimal database performance, we recommend excluding verbose attributes from the recorder.

### Option 1: Exclude All Diagnostic Attributes (Recommended)
Add this to your `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_status  # Excludes all zone status sensors
```

### Option 2: Exclude Specific Attributes
If you want to keep some history but exclude verbose attributes:

```yaml
recorder:
  exclude:
    entities:
      - sensor.living_room_status
      - sensor.bedroom_status
      - sensor.kitchen_status
    # Or use patterns
    entity_globs:
      - sensor.*_status
```

### Option 3: Keep Limited History
Keep only recent history for diagnostic sensors:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_status
  include:
    entities:
      # Selectively include specific zones if needed
      - sensor.living_room_status
  # Set shorter retention for diagnostic data
  purge_keep_days: 7  # Default for all entities
  
# Then use a separate database view or query for diagnostics
```

## What Gets Recorded

### Active Layer Sensor (KEEP in recorder)
- **State**: Layer name (e.g., "movie_scene", "adaptive")
- **Attributes**: Minimal, automation-friendly
  - `priority`: Current layer priority
  - `brightness`: Light brightness setting
  - `color_temp`: Color temperature
  - `source`: What triggered this layer
  - `reason`: Why this layer won

This sensor changes infrequently and has small attributes - perfect for history tracking.

### Zone Status Sensor (EXCLUDE from recorder)
- **State**: Status enum ("ok", "conflict", "error")
- **Attributes**: Verbose diagnostic data
  - `active_layers`: List of all active layers
  - `conflicting_layers`: Layers in conflict
  - `calculation_time_ms`: Performance metrics
  - `lights_unavailable`: Problem lights
  - `winning_reason`: Detailed explanation
  - And more...

This sensor updates frequently with large attributes - excluding it prevents database bloat.

## Database Impact

### Without Exclusion
- 20 zones × 2 sensors × 24 hours × 60 updates/hour = 57,600 records/day
- With verbose attributes: ~10KB per record = 576MB/day

### With Exclusion
- 20 zones × 1 sensor × 24 hours × 10 updates/hour = 4,800 records/day
- With minimal attributes: ~1KB per record = 4.8MB/day

**120x reduction in database size!**

## Verification

After configuring, verify the exclusion is working:

1. Check recorder info:
   ```yaml
   # In Developer Tools > Services
   service: recorder.get_statistics
   data:
     statistic_ids:
       - sensor.living_room_status
   ```

2. Monitor database size:
   ```bash
   # Check your home-assistant_v2.db size
   ls -lh /config/home-assistant_v2.db
   ```

3. Use SQL query (if using default SQLite):
   ```sql
   SELECT 
     COUNT(*) as record_count,
     entity_id 
   FROM states 
   WHERE entity_id LIKE '%_status'
   GROUP BY entity_id;
   ```

## Troubleshooting

### Still Seeing Database Growth?
1. Restart Home Assistant after changing recorder config
2. Manually purge old data: `recorder.purge` service
3. Check for automation recording these sensors

### Need Diagnostic History?
Use the Event system instead:
- Listen to `lighting_manager.calculation_complete` events
- Store diagnostics in a separate database or log file
- Use external tools for long-term analysis

## Best Practices

1. **Always exclude diagnostic sensors** from recorder
2. **Keep Active Layer sensor** in recorder for automations
3. **Use events** for detailed debugging instead of sensor history
4. **Monitor database size** monthly
5. **Set appropriate purge_keep_days** for your use case

## Example Full Configuration

```yaml
# configuration.yaml
recorder:
  purge_keep_days: 30
  commit_interval: 30
  exclude:
    # Exclude all diagnostic sensors
    entity_globs:
      - sensor.*_status
    # Also exclude verbose events if not needed
    event_types:
      - lighting_manager.calculation_complete
      - lighting_manager.conflict_detected
  include:
    # Explicitly include active layer sensors
    entity_globs:
      - sensor.*_active_layer
```

This configuration ensures optimal performance while maintaining useful history for automations.