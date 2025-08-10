# Phase 4 Implementation Plan - Observability Sensors
## Based on Critical Gemini Review Findings

### Executive Summary
The original Phase 4 requirements specify 7 sensors per zone (140 sensors for 20 zones), which would create:
- **UI chaos** with entity overload
- **Database destruction** from verbose, frequently-updating sensors
- **Performance collapse** from update storms
- **User confusion** from data without insights

### The "Missing Sidewalk" Solution
Users don't need 7 sensors showing raw data. They need **2 sensors** that answer their questions:
1. **What's controlling my lights?** (Active Layer Sensor)
2. **Is everything working correctly?** (Zone Status Sensor)

## Revised Implementation Strategy

### Core Architecture Decisions

1. **Sensor Pattern**: All sensors MUST be `CoordinatorEntity` subclasses
   - Ensures single source of truth
   - Prevents update storms
   - Maintains data consistency
   
2. **Update Flow**: Strictly one-way
   ```
   Inputs → Coordinator → Sensors (read-only views)
   ```
   - Sensors NEVER trigger recalculations
   - Sensors NEVER modify coordinator state
   
3. **Entity Categories**:
   - Active Layer Sensor: Normal entity (user-facing)
   - Zone Status Sensor: Diagnostic entity (hidden by default)

### Sensor Specifications

#### 1. Active Layer Sensor (`sensor.{zone}_active_layer`)
**Purpose**: Primary user-facing sensor for automations and UI

**State**: String - name of winning layer
- Example: `"movie_scene"`, `"adaptive"`, `"manual"`
- Simple, automation-friendly

**Attributes** (minimal, safe):
```python
{
    "priority": 75,
    "brightness": 128,
    "color_temp": 350,
    "rgb_color": [255, 180, 120],  # if applicable
    "source": "automation.sunset",
    "reason": "Movie scene (priority 75) overrides adaptive (priority 50)"
}
```

**Update Frequency**: Only when winning layer changes
**Recorder**: Full history retained

#### 2. Zone Status Sensor (`sensor.{zone}_status`)
**Purpose**: Diagnostic sensor for debugging and monitoring

**State**: Enum string
- `"ok"` - Everything normal
- `"conflict"` - Multiple layers at same priority
- `"calculating"` - Currently processing
- `"error"` - Calculation failed
- `"unavailable"` - No coordinator data

**Attributes** (verbose but sanitized):
```python
{
    "active_layers": ["adaptive", "manual", "movie_scene"],
    "conflicting_layers": ["manual", "activity"],  # if conflict
    "last_calculation": "2024-01-15T10:30:45",
    "calculation_time_ms": 23,
    "cache_hit": True,
    "trigger": "layer_updated",
    "light_unavailable": ["light.ceiling"],  # if any
    "error_message": None,  # if error state
    "winning_reason": "Movie scene wins with priority 75"
}
```

**Entity Category**: `EntityCategory.DIAGNOSTIC`
**Update Frequency**: Every calculation
**Recorder**: Excluded from history by default

### Implementation Classes

```python
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DATA_COORDINATOR
from .coordinator import ZoneCoordinator


class LightingManagerSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for all Lighting Manager sensors."""
    
    def __init__(
        self,
        coordinator: ZoneCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.zone_id}_{description.key}"
        self._attr_device_info = coordinator.device_info
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ActiveLayerSensor(LightingManagerSensorBase):
    """Sensor showing the currently active layer."""
    
    @property
    def native_value(self) -> str | None:
        """Return the active layer name."""
        if not self.coordinator.data:
            return None
        
        winning_layer = self.coordinator.data.get("winning_layer")
        if not winning_layer:
            return "none"
        
        # Return human-friendly name
        layer_data = self.coordinator.layers.get(winning_layer, {})
        return layer_data.get("layer_name", winning_layer)
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return minimal, safe attributes."""
        if not self.coordinator.data:
            return {}
        
        attrs = {}
        winning_layer = self.coordinator.data.get("winning_layer")
        
        if winning_layer and winning_layer in self.coordinator.layers:
            layer = self.coordinator.layers[winning_layer]
            attrs["priority"] = layer.get("priority", 0)
            
            # Add light state if available
            if "brightness" in layer:
                attrs["brightness"] = layer["brightness"]
            if "color_temp" in layer:
                attrs["color_temp"] = layer["color_temp"]
            if "rgb_color" in layer:
                attrs["rgb_color"] = layer["rgb_color"]
            
            # Add source if tracked
            if "source" in layer:
                attrs["source"] = layer["source"]
            
            # Add human-readable reason
            active_count = len(self.coordinator.data.get("active_layers", []))
            if active_count > 1:
                attrs["reason"] = f"{layer.get('layer_name', winning_layer)} wins with priority {layer.get('priority', 0)}"
            else:
                attrs["reason"] = f"Only {layer.get('layer_name', winning_layer)} is active"
        
        return attrs


class ZoneStatusSensor(LightingManagerSensorBase):
    """Diagnostic sensor for zone health and debugging."""
    
    def __init__(
        self,
        coordinator: ZoneCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize diagnostic sensor."""
        super().__init__(coordinator, description)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
    
    @property
    def native_value(self) -> str:
        """Return zone status."""
        if not self.coordinator.data:
            return "unavailable"
        
        # Check for conflicts
        conflicts = self.coordinator.data.get("conflicts", [])
        if conflicts:
            return "conflict"
        
        # Check for errors
        if self.coordinator.data.get("error"):
            return "error"
        
        # Check if calculating
        if self.coordinator.data.get("calculating"):
            return "calculating"
        
        return "ok"
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return sanitized diagnostic attributes."""
        if not self.coordinator.data:
            return {}
        
        attrs = {}
        
        # List active layers (names only, not full data)
        active_layers = self.coordinator.data.get("active_layers", [])
        attrs["active_layers"] = [
            self.coordinator.layers.get(lid, {}).get("layer_name", lid)
            for lid in active_layers
        ]
        
        # Add conflict info if present
        conflicts = self.coordinator.data.get("conflicts", [])
        if conflicts:
            attrs["conflicting_layers"] = [
                self.coordinator.layers.get(lid, {}).get("layer_name", lid)
                for lid in conflicts
            ]
        
        # Add timing info
        if "last_calculation" in self.coordinator.data:
            attrs["last_calculation"] = self.coordinator.data["last_calculation"]
        if "calculation_time_ms" in self.coordinator.data:
            attrs["calculation_time_ms"] = self.coordinator.data["calculation_time_ms"]
        
        # Add cache info
        if "cache_hit" in self.coordinator.data:
            attrs["cache_hit"] = self.coordinator.data["cache_hit"]
        
        # Add trigger source
        if "trigger" in self.coordinator.data:
            attrs["trigger"] = self.coordinator.data["trigger"]
        
        # Add unavailable lights if any
        unavailable = self.coordinator.data.get("lights_unavailable", [])
        if unavailable:
            attrs["lights_unavailable"] = unavailable
        
        # Add error message if in error state
        if self.coordinator.data.get("error"):
            attrs["error_message"] = str(self.coordinator.data["error"])
        
        # Add winning reason
        winning_layer = self.coordinator.data.get("winning_layer")
        if winning_layer:
            layer = self.coordinator.layers.get(winning_layer, {})
            attrs["winning_reason"] = f"{layer.get('layer_name', winning_layer)} wins with priority {layer.get('priority', 0)}"
        
        return attrs
```

### Setup Function

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    
    sensors = [
        ActiveLayerSensor(
            coordinator,
            SensorEntityDescription(
                key="active_layer",
                name=f"{entry.data['zone_name']} Active Layer",
                icon="mdi:layers",
            ),
        ),
        ZoneStatusSensor(
            coordinator,
            SensorEntityDescription(
                key="status",
                name=f"{entry.data['zone_name']} Status",
                icon="mdi:information-outline",
            ),
        ),
    ]
    
    async_add_entities(sensors)
```

### Critical Implementation Rules

1. **NEVER store full calculation data in attributes**
   - Summarize, don't dump
   - Names, not dictionaries
   - Reasons, not raw data

2. **ALWAYS check for None/missing data**
   ```python
   if not self.coordinator.data:
       return None
   ```

3. **ALWAYS use defensive attribute access**
   ```python
   value = data.get("key", default_value)
   ```

4. **NEVER let sensors trigger recalculations**
   - Read-only views only
   - No calls to coordinator.async_refresh()

5. **ALWAYS sanitize user data**
   - No raw user input in attributes
   - No template evaluation results
   - No API keys or secrets

### Testing Requirements

1. **Startup Sequence**
   - Sensors handle coordinator.data = None gracefully
   - No exceptions during initial setup
   - Correct unavailable state until first calculation

2. **Scale Testing**
   - 20 zones × 2 sensors = 40 entities (not 140!)
   - Database size remains stable
   - UI remains responsive

3. **Error Scenarios**
   - Calculation failures don't crash sensors
   - Missing attributes handled gracefully
   - Network/entity unavailable states handled

4. **User Experience**
   - Active layer sensor useful for automations
   - Status sensor hidden by default
   - Clear, actionable information

### Migration from 7-Sensor Approach

**DO NOT IMPLEMENT** the original 7 sensors:
- ~~REQ-S001: Winning layer~~ → Covered by Active Layer Sensor
- ~~REQ-S002: Calculation path~~ → Too verbose, not needed
- ~~REQ-S003: Timestamp~~ → In Status Sensor attributes
- ~~REQ-S004: Conflict status~~ → In Status Sensor state
- ~~REQ-S005: Calculation input~~ → Too large, security risk
- ~~REQ-S006: Calculation output~~ → In Active Layer attributes
- ~~REQ-S007: Performance metrics~~ → In Status Sensor attributes

### Success Metrics

1. **Performance**: Sensor updates < 10ms
2. **Database**: < 1KB per sensor per hour
3. **UI**: Users can find what they need in < 3 clicks
4. **Debugging**: Problems identifiable from Status sensor
5. **Automation**: Active Layer sensor triggers work reliably

## Next Steps

1. Implement base sensor class with error handling
2. Create Active Layer and Zone Status sensors
3. Update coordinator.data to include required fields
4. Add diagnostic category and icons
5. Test at scale with 20 zones
6. Document recorder exclusion for users
7. Create Lovelace card example for visualization

## Key Insight

The "missing sidewalk" was that users need **answers**, not data. By consolidating 7 verbose sensors into 2 purposeful ones, we deliver a better user experience while protecting system performance.