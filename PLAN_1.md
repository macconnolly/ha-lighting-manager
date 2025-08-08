# Lighting Manager Modernization Plan: From Legacy to Layer-First Architecture

## Executive Summary

This plan transforms the legacy `lighting_manager` custom component into a modern, architecturally pure Home Assistant integration. The core innovation is elevating layers from internal data structures to first-class Home Assistant entities, creating total observability and a reactive, event-driven system.

## 1. Current State Analysis

### Architectural Debt in Legacy System
1. **Hidden State**: Layers stored in `hass.data[DOMAIN][DATA_STATES]` dictionary
2. **Imperative Logic**: Direct state manipulation instead of reactive patterns
3. **No UI Configuration**: YAML-only configuration
4. **Limited Observability**: Layer states invisible to users
5. **Tight Coupling**: Business logic mixed with state management

### What Works Well
- Core layer/priority concept is sound
- Service architecture for layer manipulation
- Adaptive lighting integration concept

## 2. Target Architecture Vision

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Home Assistant Core                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐   │
│  │   Layer     │  │   Zone      │  │    Sensor         │   │
│  │  Entities   │  │  Devices    │  │   Entities        │   │
│  └──────┬──────┘  └──────┬──────┘  └────────┬──────────┘   │
│         │                 │                   │              │
│  ┌──────▼─────────────────▼──────────────────▼──────────┐   │
│  │           Zone Coordinator (Orchestrator)             │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │   │
│  │  │  Monitor   │  │ Calculate  │  │     Apply      │  │   │
│  │  │  Layers    │─▶│   State    │─▶│   to Lights    │  │   │
│  │  └────────────┘  └────────────┘  └────────────────┘  │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Patterns

1. **Layer Entities as State Containers**
   - Each layer is a full Home Assistant entity
   - State: active/inactive
   - Attributes: priority, brightness, color_temp, rgb_color, transition, etc.

2. **Zone-Based Organization**
   - Each zone (e.g., "living_room") gets a device entry
   - Layers and sensors grouped under zone device
   - One coordinator per zone

3. **Pure Functional Calculation**
   - Calculator receives layer states, outputs light state
   - No side effects, completely deterministic
   - Testable in isolation

## 3. Implementation Phases

### Phase 1: Foundation - The Layer Platform

#### File Structure
```
custom_components/lighting_manager/
├── __init__.py          # Main setup, coordinator registration
├── manifest.json        # Modern manifest with config_flow
├── config_flow.py       # UI-based zone creation
├── const.py            # All constants and schemas
├── layer.py            # Layer entity platform
├── sensor.py           # Debug/status sensors
├── coordinator.py      # Zone orchestration engine
├── calculator.py       # Pure calculation logic
├── services.yaml       # Service definitions
└── translations/
    └── en.json         # UI strings
```

#### Task 1.1: Create Layer Entity Platform

**File: `layer.py`**
```python
"""Layer entity platform for Lighting Manager."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_FORCE,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_SOURCE,
    DOMAIN,
    EVENT_LAYER_ACTIVATED,
    EVENT_LAYER_DEACTIVATED,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up layer entities for a zone."""
    zone_id = entry.data["zone_id"]
    
    # Create standard layers
    layers = [
        LayerEntity(zone_id, "base_adaptive", 0, "Base Adaptive"),
        LayerEntity(zone_id, "environmental", 10, "Environmental"),
        LayerEntity(zone_id, "activity", 20, "Activity"),
        LayerEntity(zone_id, "mode", 30, "Mode"),
        LayerEntity(zone_id, "manual", 100, "Manual Override"),
    ]
    
    async_add_entities(layers)

class LayerEntity(RestoreEntity, Entity):
    """Representation of a lighting layer."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(
        self,
        zone_id: str,
        layer_id: str,
        priority: int,
        name: str,
    ) -> None:
        """Initialize the layer."""
        self._zone_id = zone_id
        self._layer_id = layer_id
        self._priority = priority
        self._attr_name = name
        self._attr_unique_id = f"{zone_id}_{layer_id}"
        self.entity_id = f"layer.{zone_id}_{layer_id}"
        
        # Mutable state
        self._active = False
        self._brightness: Optional[int] = None
        self._color_temp: Optional[int] = None
        self._rgb_color: Optional[tuple] = None
        self._transition: Optional[float] = None
        self._force = False
        self._locked = False
        self._conditions: Dict[str, Any] = {}
        self._last_updated: Optional[datetime] = None
        self._source: Optional[str] = None
    
    @property
    def state(self) -> str:
        """Return the state of the layer."""
        return "active" if self._active else "inactive"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity state attributes."""
        return {
            "zone_id": self._zone_id,
            "layer_id": self._layer_id,
            "priority": self._priority,
            "brightness": self._brightness,
            "color_temp": self._color_temp,
            "rgb_color": self._rgb_color,
            "transition": self._transition,
            "force": self._force,
            "locked": self._locked,
            "conditions": self._conditions,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            "source": self._source,
        }
    
    async def async_activate(
        self,
        brightness: Optional[int] = None,
        color_temp: Optional[int] = None,
        rgb_color: Optional[tuple] = None,
        transition: Optional[float] = None,
        source: Optional[str] = None,
    ) -> None:
        """Activate the layer with given parameters."""
        if self._locked:
            _LOGGER.warning("Cannot activate locked layer %s", self.entity_id)
            return
            
        self._active = True
        self._brightness = brightness
        self._color_temp = color_temp
        self._rgb_color = rgb_color
        self._transition = transition
        self._source = source
        self._last_updated = dt_util.utcnow()
        
        self.async_write_ha_state()
        
        # Fire activation event
        self.hass.bus.async_fire(
            EVENT_LAYER_ACTIVATED,
            {
                "entity_id": self.entity_id,
                "zone_id": self._zone_id,
                "layer_id": self._layer_id,
                "priority": self._priority,
            },
        )
    
    async def async_deactivate(self) -> None:
        """Deactivate the layer."""
        if self._locked:
            _LOGGER.warning("Cannot deactivate locked layer %s", self.entity_id)
            return
            
        self._active = False
        self._last_updated = dt_util.utcnow()
        
        self.async_write_ha_state()
        
        # Fire deactivation event
        self.hass.bus.async_fire(
            EVENT_LAYER_DEACTIVATED,
            {
                "entity_id": self.entity_id,
                "zone_id": self._zone_id,
                "layer_id": self._layer_id,
            },
        )
```

### Phase 2: Orchestration Engine

#### Task 2.1: Create Zone Coordinator

**File: `coordinator.py`**
```python
"""Zone coordinator for orchestrating layer changes."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .calculator import LightingCalculator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ZoneCoordinator(DataUpdateCoordinator):
    """Coordinate layer states and light control for a zone."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        zone_id: str,
        light_entities: List[str],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{zone_id}",
            update_interval=None,  # We're event-driven, not polling
        )
        
        self.zone_id = zone_id
        self.light_entities = light_entities
        self.calculator = LightingCalculator()
        self._layer_entities: List[str] = []
        self._debounce_task: Optional[asyncio.Task] = None
        
    async def async_initialize(self) -> None:
        """Initialize the coordinator by finding layer entities."""
        # Find all layer entities for this zone
        self._layer_entities = [
            entity_id
            for entity_id in self.hass.states.async_entity_ids("layer")
            if entity_id.startswith(f"layer.{self.zone_id}_")
        ]
        
        # Subscribe to layer state changes
        if self._layer_entities:
            async_track_state_change_event(
                self.hass,
                self._layer_entities,
                self._handle_layer_change,
            )
    
    @callback
    def _handle_layer_change(self, event) -> None:
        """Handle layer state changes with debouncing."""
        # Cancel existing debounce
        if self._debounce_task:
            self._debounce_task.cancel()
            
        # Schedule new update with 100ms debounce
        self._debounce_task = self.hass.async_create_task(
            self._debounced_refresh()
        )
    
    async def _debounced_refresh(self) -> None:
        """Refresh after debounce period."""
        await asyncio.sleep(0.1)
        await self.async_request_refresh()
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Calculate and apply lighting state."""
        # CALCULATE: Get all layer states
        active_layers = []
        
        for entity_id in self._layer_entities:
            if state := self.hass.states.get(entity_id):
                if state.state == "active":
                    active_layers.append({
                        "entity_id": entity_id,
                        "priority": state.attributes.get("priority", 0),
                        "brightness": state.attributes.get("brightness"),
                        "color_temp": state.attributes.get("color_temp"),
                        "rgb_color": state.attributes.get("rgb_color"),
                        "transition": state.attributes.get("transition"),
                        "force": state.attributes.get("force", False),
                        "locked": state.attributes.get("locked", False),
                    })
        
        # Calculate final state
        result = self.calculator.calculate_state(
            active_layers,
            self.light_entities,
        )
        
        # STORE: The result is our coordinator data
        self.data = result
        
        # APPLY: Update the actual lights
        if result["final_state"]:
            await self._apply_to_lights(result["final_state"])
        
        # Fire calculation complete event
        self.hass.bus.async_fire(
            "lighting_manager.calculation_complete",
            {
                "zone_id": self.zone_id,
                "winning_layer": result.get("winning_layer"),
                "final_state": result.get("final_state"),
                "conflicts": result.get("conflicts", []),
            },
        )
        
        return result
    
    async def _apply_to_lights(self, state: Dict[str, Any]) -> None:
        """Apply calculated state to physical lights."""
        service_data = {
            "entity_id": self.light_entities,
        }
        
        if brightness := state.get("brightness"):
            service_data["brightness"] = brightness
        if color_temp := state.get("color_temp"):
            service_data["color_temp"] = color_temp
        if rgb_color := state.get("rgb_color"):
            service_data["rgb_color"] = rgb_color
        if transition := state.get("transition"):
            service_data["transition"] = transition
            
        if state.get("power") == "on":
            await self.hass.services.async_call(
                "light", "turn_on", service_data
            )
        else:
            await self.hass.services.async_call(
                "light", "turn_off", service_data
            )
```

#### Task 2.2: Create Pure Calculator

**File: `calculator.py`**
```python
"""Pure calculation functions for lighting state."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

class LightingCalculator:
    """Calculate lighting state from layers."""
    
    @staticmethod
    def calculate_state(
        active_layers: List[Dict[str, Any]],
        light_entities: List[str],
    ) -> Dict[str, Any]:
        """Calculate final lighting state from active layers."""
        if not active_layers:
            return {
                "winning_layer": None,
                "final_state": {"power": "off"},
                "conflicts": [],
                "calculation_path": [],
            }
        
        # Sort by priority (highest first), then by force flag
        sorted_layers = sorted(
            active_layers,
            key=lambda x: (x.get("force", False), x.get("priority", 0)),
            reverse=True,
        )
        
        # Find winning layer
        winning_layer = None
        for layer in sorted_layers:
            if not layer.get("locked", False):
                winning_layer = layer
                break
        
        if not winning_layer:
            return {
                "winning_layer": None,
                "final_state": {"power": "off"},
                "conflicts": ["all_layers_locked"],
                "calculation_path": [l["entity_id"] for l in sorted_layers],
            }
        
        # Build final state
        final_state = {
            "power": "on",
            "brightness": winning_layer.get("brightness"),
            "color_temp": winning_layer.get("color_temp"),
            "rgb_color": winning_layer.get("rgb_color"),
            "transition": winning_layer.get("transition", 1.0),
        }
        
        # Detect conflicts
        conflicts = LightingCalculator._detect_conflicts(sorted_layers)
        
        return {
            "winning_layer": winning_layer["entity_id"],
            "final_state": final_state,
            "conflicts": conflicts,
            "calculation_path": [l["entity_id"] for l in sorted_layers],
        }
    
    @staticmethod
    def _detect_conflicts(layers: List[Dict[str, Any]]) -> List[str]:
        """Detect priority conflicts between layers."""
        conflicts = []
        
        # Check for priority ties
        priority_groups = {}
        for layer in layers:
            priority = layer.get("priority", 0)
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(layer["entity_id"])
        
        for priority, group in priority_groups.items():
            if len(group) > 1:
                conflicts.append(f"priority_tie_at_{priority}")
        
        # Check for multiple force flags
        forced_layers = [l for l in layers if l.get("force", False)]
        if len(forced_layers) > 1:
            conflicts.append("multiple_force_flags")
        
        return conflicts
```

### Phase 3: Config Flow & Services

#### Task 3.1: Implement Config Flow

**File: `config_flow.py`**
```python
"""Config flow for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class LightingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lighting Manager."""
    
    VERSION = 1
    
    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate zone name is unique
            zone_id = user_input[CONF_NAME].lower().replace(" ", "_")
            
            # Check for duplicates
            for entry in self._async_current_entries():
                if entry.data.get("zone_id") == zone_id:
                    errors["base"] = "zone_exists"
                    break
            
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        "zone_id": zone_id,
                        "zone_name": user_input[CONF_NAME],
                        "light_entities": user_input["lights"],
                    },
                )
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME): str,
                vol.Required("lights"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="light",
                        multiple=True,
                    )
                ),
            }),
            errors=errors,
        )
```

#### Task 3.2: Modernize Services

**File: `services.yaml`**
```yaml
activate_layer:
  name: Activate Layer
  description: Activate a lighting layer with specified parameters
  target:
    entity:
      domain: layer
  fields:
    brightness:
      name: Brightness
      description: Brightness value (0-255)
      selector:
        number:
          min: 0
          max: 255
    color_temp:
      name: Color Temperature
      description: Color temperature in mireds
      selector:
        number:
          min: 153
          max: 500
    rgb_color:
      name: RGB Color
      description: RGB color value
      selector:
        color_rgb:
    transition:
      name: Transition
      description: Transition time in seconds
      selector:
        number:
          min: 0
          max: 300
          step: 0.1
    source:
      name: Source
      description: What triggered this activation
      selector:
        text:

deactivate_layer:
  name: Deactivate Layer
  description: Deactivate a lighting layer
  target:
    entity:
      domain: layer

set_layer_priority:
  name: Set Layer Priority
  description: Change the priority of a layer
  target:
    entity:
      domain: layer
  fields:
    priority:
      name: Priority
      description: New priority value (0-100)
      selector:
        number:
          min: 0
          max: 100

lock_layer:
  name: Lock Layer
  description: Lock a layer to prevent changes
  target:
    entity:
      domain: layer

unlock_layer:
  name: Unlock Layer
  description: Unlock a layer to allow changes
  target:
    entity:
      domain: layer
```

### Phase 4: Observability Sensors

#### Task 4.1: Create Debug Sensors

**File: `sensor.py`**
```python
"""Sensor platform for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for a zone."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    zone_id = entry.data["zone_id"]
    
    sensors = [
        WinningLayerSensor(coordinator, zone_id),
        CalculationPathSensor(coordinator, zone_id),
        ConflictSensor(coordinator, zone_id),
        FinalStateSensor(coordinator, zone_id),
    ]
    
    async_add_entities(sensors)

class WinningLayerSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the currently winning layer."""
    
    def __init__(self, coordinator: ZoneCoordinator, zone_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_name = f"{zone_id.replace('_', ' ').title()} Winning Layer"
        self._attr_unique_id = f"{zone_id}_winning_layer"
    
    @property
    def state(self) -> str:
        """Return the winning layer."""
        if self.coordinator.data:
            return self.coordinator.data.get("winning_layer", "none")
        return "unknown"
```

## 4. Migration Strategy

### Phase 1: Parallel Installation
1. Install new component alongside old one
2. Create migration wizard in config flow
3. Import YAML config automatically

### Phase 2: Layer Migration
```python
async def migrate_from_legacy(hass, legacy_states):
    """Migrate legacy states to layer entities."""
    for entity_id, layers in legacy_states.items():
        zone_id = extract_zone_from_entity(entity_id)
        
        for layer_id, layer_data in layers.items():
            # Find corresponding layer entity
            layer_entity = f"layer.{zone_id}_{layer_id}"
            
            # Activate with legacy data
            await hass.services.async_call(
                DOMAIN,
                "activate_layer",
                {
                    "entity_id": layer_entity,
                    "brightness": layer_data["state"].attributes.get("brightness"),
                    "color_temp": layer_data["state"].attributes.get("color_temp"),
                    "source": "migration",
                },
            )
```

## 5. Testing Strategy

### Unit Tests
- Calculator logic (pure functions)
- Layer entity state management
- Conflict detection

### Integration Tests
- Full Calculate → Store → Apply flow
- Service calls
- Event firing
- State restoration

### Performance Tests
- 20 zones × 20 layers = 400 entities
- Sub-200ms response time
- Memory profiling

## 6. Advanced Features Roadmap

### V2.0: Enhanced Conditions
```python
conditions = {
    "time": {"after": "sunset", "before": "23:00"},
    "presence": {"any": ["person.john", "person.jane"]},
    "state": {"alarm_control_panel.home": "armed_away"},
}
```

### V3.0: Layer Templates
- Save/restore layer configurations
- Share between zones
- Import/export

### V4.0: Adaptive Layer Intelligence
- Learn patterns from manual overrides
- Predictive activation
- Energy optimization

## 7. Implementation Timeline

**Week 1-2**: Foundation
- Layer entity platform
- Basic coordinator
- Config flow

**Week 3-4**: Core Functionality  
- Services implementation
- State calculation
- Light control

**Week 5-6**: Observability
- Debug sensors
- Event system
- UI polish

**Week 7-8**: Migration & Testing
- Legacy migration
- Test coverage
- Documentation

## Conclusion

This plan transforms the lighting_manager into a modern, observable, and architecturally pure Home Assistant integration. By making layers first-class entities, we achieve total transparency while maintaining the powerful layered control system. The reactive, event-driven architecture ensures instant response times and the pure functional calculator makes the system predictable and testable.