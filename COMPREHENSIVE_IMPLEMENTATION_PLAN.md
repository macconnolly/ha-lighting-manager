# Comprehensive Implementation Plan: Lighting Manager v4.0

## Core Architectural Principle
Transform layers from hidden dictionary entries to **first-class Home Assistant switch entities** that users can see, control, and automate against. Each layer becomes a visible, manageable switch entity with "on/off" states and rich attributes.

**Critical Design Pattern**: The ZoneCoordinator is the single source of truth for all layer state. Switch entities are stateless views that display coordinator data and send commands to the coordinator. This follows the standard Home Assistant DataUpdateCoordinator pattern.

## Complete Task Breakdown

### PHASE 1: Foundation - Entity Platform & Data Models
**Goal**: Establish the layer entity platform and core data structures

#### Task 1.1: Project Structure Setup
- [ ] Create `custom_components/lighting_manager/` directory structure
- [ ] Create `__init__.py` with domain registration
- [ ] Create `manifest.json` with config_flow enabled
- [ ] Create `const.py` with all constants
- [ ] Create `translations/en.json` for UI strings
- [ ] Define domain constant: `DOMAIN = "lighting_manager"`
- [ ] Define platform list: `PLATFORMS = ["switch", "sensor"]`

#### Task 1.2: Switch Platform for Layers (`switch.py`)
- [ ] Create switch platform implementation 
- [ ] Implement `async_setup_entry()` function
  - [ ] Get coordinator reference from hass.data
  - [ ] Create switch entities for existing layers in coordinator
  - [ ] Store add_entities callback for dynamic layer creation
- [ ] Define `LayerSwitch` class extending `CoordinatorEntity, SwitchEntity` (NOT RestoreEntity)
- [ ] Implement entity ID slugification:
  - [ ] Import `from homeassistant.util import slugify`
  - [ ] Generate entity_id: `f"switch.{slugify(zone_id)}_{slugify(layer_name)}_layer"`
  - [ ] Ensure all user-provided names are slugified
- [ ] Implement entity properties (ALL read from coordinator.data):
  - [ ] `entity_id` following pattern: `switch.{zone_id}_{layer_name}_layer` (slugified)
  - [ ] `unique_id` for entity registry
  - [ ] `device_info` for grouping under zone device
  - [ ] `entity_category` as `CONFIG` for UI organization
- [ ] Implement stateless property getters from coordinator:
  - [ ] `is_on` property: Read from `coordinator.data["layers"][layer_id]["is_on"]`
  - [ ] `available` property: Based on coordinator availability
  - [ ] `extra_state_attributes`: Read ALL attributes from coordinator data
    - [ ] zone_id, layer_name, priority, brightness, color_temp, etc.
    - [ ] All values come from coordinator, switch stores NOTHING
  - [ ] CRITICAL: coordinator.data must be a property that returns {"layers": self.layers}
- [ ] Implement switch methods that call coordinator:
  - [ ] `async_turn_on()`: Call `coordinator.update_layer(layer_id, is_on=True, **kwargs)`
  - [ ] `async_turn_off()`: Call `coordinator.update_layer(layer_id, is_on=False)`
  - [ ] No local state changes, only coordinator calls
- [ ] Implement coordinator update handling:
  - [ ] Override `_handle_coordinator_update()` from CoordinatorEntity
  - [ ] Simply call `self.async_write_ha_state()` to update UI
- [ ] NO state storage in switch entity:
  - [ ] No `_attr_is_on` or similar attributes
  - [ ] No `_priority`, `_brightness`, etc.
  - [ ] Switch is purely a view of coordinator data

#### Task 1.3: Config Flow (`config_flow.py`)
- [ ] Create `LightingManagerConfigFlow` class
- [ ] Implement `async_step_user()` for UI entry
- [ ] Create simple zone configuration form:
  - [ ] Zone name input (string)
  - [ ] Light entity selector (multi-select)
- [ ] Generate unique zone_id from slugified name
- [ ] Validate no duplicate zones
- [ ] Create ConfigEntry with proper data/options split:
  - [ ] `config_entry.data` (structural, immutable):
    - [ ] `zone_id`: Unique zone identifier (slugified)
    - [ ] `zone_name`: Display name for zone
    - [ ] `area_id`: Optional area association
  - [ ] `config_entry.options` (user-configurable):
    - [ ] `light_entities`: List of light entity IDs
    - [ ] `default_transition`: Default transition time
    - [ ] `adaptive_enabled`: Boolean for built-in adaptive
    - [ ] `adaptive_brightness_range`: [min, max]
    - [ ] `adaptive_color_temp_range`: [min, max]

#### Task 1.4: Options Flow (`config_flow.py`)
- [ ] Implement `async_get_options_flow()`
- [ ] Create `OptionsFlowHandler` class
- [ ] Allow editing ONLY options (not data):
  - [ ] Light entities list
  - [ ] Default transition time
  - [ ] Adaptive enable/disable
  - [ ] Adaptive brightness range (CRITICAL: properly reconstruct from min/max inputs)
  - [ ] Adaptive color temp range (CRITICAL: properly reconstruct from min/max inputs)
- [ ] Note: zone_id and zone_name are immutable (in data)
- [ ] FIX: When saving options, reconstruct ranges as arrays:
  ```python
  # In async_step_init when user_input is not None:
  options_data = {
      "light_entities": user_input["light_entities"],
      "default_transition": user_input["default_transition"],
      "adaptive_enabled": user_input["adaptive_enabled"],
      "adaptive_brightness_range": [
          user_input["adaptive_brightness_min"],
          user_input["adaptive_brightness_max"]
      ],
      "adaptive_color_temp_range": [
          user_input["adaptive_color_temp_min"],
          user_input["adaptive_color_temp_max"]
      ]
  }
  return self.async_create_entry(title="", data=options_data)
  ```

### PHASE 1.5: Core Fixes and Validation
**Goal**: Ensure foundation is rock-solid before adding complexity

#### Task 1.5.1: Fix Coordinator Data Model
- [ ] Implement `data` as a property, not from `_async_update_data()`:
  ```python
  @property
  def data(self):
      """Always return current state - single source of truth."""
      return {"layers": self.layers, ...}
  ```
- [ ] Remove @callback from async methods
- [ ] Ensure all state-modifying methods are async
- [ ] Add proper error handling to all methods

#### Task 1.5.2: Add Input Validation
- [ ] Create validation helper functions:
  ```python
  def validate_brightness(value: Any) -> int:
      """Validate and clamp brightness 0-255."""
      try:
          val = int(value)
          return max(0, min(255, val))
      except (TypeError, ValueError):
          raise ValueError(f"Invalid brightness: {value}")
  ```
- [ ] Validate ALL user inputs before storage
- [ ] Use `dt_util.now()` for timezone-aware timestamps

#### Task 1.5.3: Fix Storage Implementation
- [ ] Add validation on load:
  ```python
  stored = await self._store.async_load()
  if stored and self._validate_storage(stored):
      self.layers = stored["layers"]
  else:
      self.layers = {}
  ```
- [ ] Handle corrupted data gracefully
- [ ] Add version migration support

#### Task 1.5.4: Fix Service Implementation
- [ ] Rewrite using proper entity targeting
- [ ] Register at domain level, not per zone
- [ ] Add comprehensive input validation
- [ ] Use entity registry properly

### PHASE 2: Orchestration Engine
**Goal**: Build the reactive calculation and application engine

#### Task 2.1: Zone Coordinator (`coordinator.py`)
- [ ] Create `ZoneCoordinator` extending `DataUpdateCoordinator`
- [ ] Initialize with zone_id and light entities
- [ ] Implement centralized layer state management:
  - [ ] Store all layer states in `self.layers = {}` dictionary
  - [ ] Each layer is a dict with: is_on, priority, brightness, color_temp, etc.
  - [ ] Coordinator is single source of truth for ALL layer data
- [ ] Implement Store for persistence:
  - [ ] Create `Store` instance in `__init__`
  - [ ] Load layers from `.storage/lighting_manager_{zone_id}.json` on startup
  - [ ] Save layers on every state change (debounced)
  - [ ] Handle migration from old format if needed
- [ ] Implement layer management methods (NO @callback decorator - these modify state!):
  - [ ] `async create_layer(layer_name, priority, **attributes)`: Add new layer to dict
  - [ ] `async update_layer(layer_id, **updates)`: Update layer attributes
  - [ ] `async delete_layer(layer_id)`: Remove layer from dict
  - [ ] `get_layer(layer_id)`: Return layer data (read-only, can be sync)
  - [ ] All methods trigger refresh after changes
  - [ ] CRITICAL: Methods that modify state must be async, NOT @callback
- [ ] Set up debounced refresh:
  - [ ] Implement proper 100ms debouncing with timer
  - [ ] Collect all pending updates during debounce window
  - [ ] Single recalculation after debounce expires
- [ ] Implement coordinator.data property (NOT _async_update_data for now):
  - [ ] Simple property that returns current state:
    ```python
    @property
    def data(self):
        """Single source of truth - always returns current layers."""
        return {
            "layers": self.layers,  # Direct reference to layer dict
            "active_layers": [l for l in self.layers.values() if l.get("is_on")],
            "winning_layer": None,  # Phase 2 will calculate
            "final_state": {},  # Phase 2 will calculate
        }
    ```
  - [ ] Phase 2 will add _async_update_data() for calculations
- [ ] Handle coordinator lifecycle:
  - [ ] Load from Store on initialization
  - [ ] Save to Store on shutdown
  - [ ] Clean up timers on removal
- [ ] Implement state restoration for lights:
  - [ ] Track light availability state
  - [ ] Queue commands for unavailable lights
  - [ ] Apply queued commands when lights return

#### Task 2.2: Calculation Engine (`calculator.py`)
- [ ] Create `LightingCalculator` class
- [ ] Implement `calculate_state()` pure function:
  - [ ] Input: List of active layers
  - [ ] Sort by priority (highest first)
  - [ ] Check force flags (override priority)
  - [ ] Check locked flags (cannot change)
  - [ ] Determine winning layer
  - [ ] Build final light state
  - [ ] Return calculation result
- [ ] Implement calculation caching (REQ-P009):
  - [ ] Cache key from layer states
  - [ ] TTL-based cache expiry
  - [ ] Cache invalidation on change
- [ ] Add @callback decorators (REQ-P007):
  - [ ] For synchronous operations
  - [ ] Avoid unnecessary async overhead
- [ ] Implement conflict detection:
  - [ ] Detect priority ties
  - [ ] Detect multiple force flags
  - [ ] Detect all layers locked
  - [ ] Log conflicts with resolution (REQ-O012)
  - [ ] Return conflict list
- [ ] Create calculation result structure:
  ```python
  {
    "winning_layer": "switch.zone_layername_layer",
    "final_state": {
      "power": "on/off",
      "brightness": 0-255,
      "color_temp": mireds,
      "rgb_color": (r,g,b),
      "transition": seconds
    },
    "conflicts": ["priority_tie_at_20"],
    "calculation_path": ["layer1", "layer2"],
    "calculation_time_ms": 12
  }
  ```

#### Task 2.3: Light Control (`light_control.py`)
- [ ] Create `LightController` class
- [ ] Implement `apply_state()` method:
  - [ ] Receive final state from coordinator
  - [ ] Build service call data
  - [ ] Handle different light capabilities
  - [ ] Apply atomically to all lights
- [ ] Handle special cases:
  - [ ] Lights without color temp support
  - [ ] Lights without brightness control
  - [ ] RGB-only lights
  - [ ] Unavailable lights
- [ ] Implement transition handling:
  - [ ] Respect layer transition times
  - [ ] Handle instant changes
  - [ ] Queue transitions

#### Task 2.4: Integration (`__init__.py`)
- [ ] Update `async_setup_entry()`:
  - [ ] Create zone device in registry
  - [ ] Initialize ZoneCoordinator
  - [ ] Forward to platform setup
  - [ ] Register coordinator listener
- [ ] Implement listener callback:
  - [ ] Get data from coordinator
  - [ ] Apply to lights via controller
  - [ ] Fire completion events
- [ ] Handle zone lifecycle:
  - [ ] Creation from config flow
  - [ ] Removal/unload
  - [ ] Reload on options change

### PHASE 3: Layer Management Services
**Goal**: Create intuitive API for layer control

#### Task 3.0: Service Implementation Pattern (CRITICAL)
- [ ] Use Home Assistant's proper service patterns:
  ```python
  from homeassistant.helpers import entity_registry as er
  from homeassistant.helpers.service import async_extract_referenced_entity_ids
  
  async def handle_create_layer(call: ServiceCall) -> None:
      """Proper service implementation."""
      # Extract entities properly
      referenced = async_extract_referenced_entity_ids(hass, call)
      entity_ids = referenced.referenced | referenced.indirectly_referenced
      
      # Use entity registry to find our entities
      entity_reg = er.async_get(hass)
      for entity_id in entity_ids:
          entry = entity_reg.async_get(entity_id)
          if entry and entry.platform == DOMAIN:
              # Get coordinator from entry's config_entry_id
              coordinator = hass.data[DOMAIN][entry.config_entry_id][DATA_COORDINATOR]
              # Now work with coordinator
  ```
- [ ] NEVER manually parse entity IDs or search through hass.data
- [ ] Register services once at domain level, not per zone

#### Task 3.1: Layer Creation Service
- [ ] Service: `create_layer`
- [ ] Parameters:
  - [ ] zone_id: Target zone (via entity targeting)
  - [ ] layer_name: Unique name (will be slugified)
  - [ ] priority: Initial priority (validate 0-100)
  - [ ] brightness: Optional (validate 0-255)
  - [ ] color_temp: Optional (validate 153-500 mireds)
- [ ] Implementation:
  - [ ] Use proper entity targeting (see Task 3.0)
  - [ ] Validate ALL input parameters
  - [ ] Call `await coordinator.create_layer(layer_name, priority, **kwargs)`
  - [ ] Coordinator adds layer to its internal dictionary
  - [ ] Coordinator saves to Store
  - [ ] Get add_entities callback from hass.data
  - [ ] Create new LayerSwitch entity pointing to this layer
  - [ ] Switch entity is just a view of coordinator data

#### Task 3.2: Layer Control Services
- [ ] Service: `activate_layer`
  - [ ] Target: switch entity
  - [ ] Parameters: brightness, color_temp, rgb_color, transition, source
  - [ ] Call switch's `async_turn_on()` or `async_activate()`
- [ ] Service: `deactivate_layer`
  - [ ] Target: switch entity
  - [ ] Call switch's `async_turn_off()` or `async_deactivate()`
- [ ] Service: `update_layer`
  - [ ] Target: switch entity
  - [ ] Parameters: Any layer attributes
  - [ ] Update without changing on/off state

#### Task 3.3: Layer State Services
- [ ] Service: `set_layer_priority`
  - [ ] Target: switch entity
  - [ ] Parameter: priority (0-100)
- [ ] Service: `lock_layer`
  - [ ] Target: switch entity
  - [ ] Prevent modifications
- [ ] Service: `unlock_layer`
  - [ ] Target: switch entity
- [ ] Service: `force_layer`
  - [ ] Target: switch entity
  - [ ] Override priority system

#### Task 3.4: Zone Services
- [ ] Service: `recalculate_zone`
  - [ ] Parameter: zone_id
  - [ ] Force immediate recalculation
- [ ] Service: `clear_zone`
  - [ ] Parameter: zone_id
  - [ ] Deactivate all layers
- [ ] Service: `clear_layer`
  - [ ] Parameters: zone_id, layer_name
  - [ ] Remove specified layer from ALL entities at once
  - [ ] System-wide layer cleanup
- [ ] Service: `apply_preset`
  - [ ] Parameters: zone_id, preset_data
  - [ ] Configure multiple layers atomically
- [ ] Service: `insert_scene`
  - [ ] Parameters: zone_id, scene_entity_id, layer_name, priority
  - [ ] Extract scene state and apply as layer
  - [ ] Map HA scene attributes to layer attributes
  - [ ] Support scene transitions and source tracking

#### Task 3.5: Service Definitions (`services.yaml`)
- [ ] Define all services with descriptions
- [ ] Add parameter schemas
- [ ] Include examples
- [ ] Define selectors for UI

### PHASE 4: Observability & Debugging
**Goal**: Complete transparency of system state

#### Task 4.1: Sensor Platform (`sensor.py`)
- [ ] Implement `async_setup_entry()`
- [ ] Create sensor base class extending `CoordinatorEntity`
- [ ] Implement zone sensors:
  - [ ] Winning Layer Sensor
  - [ ] Active Layers Sensor
  - [ ] Calculation Path Sensor
  - [ ] Conflict Status Sensor
  - [ ] Final State Sensor
  - [ ] Performance Metrics Sensor
  - [ ] Last Calculation Time Sensor
  - [ ] AdaptiveLightFactorSensor (critical for sun-based adaptation)
    - [ ] Calculate sun elevation factor
    - [ ] Return 0.0 (night) to 1.0 (day) range
    - [ ] Update every 5 minutes or on sun events
    - [ ] Include sun azimuth and time-of-day data
- [ ] Link sensors to coordinator:
  - [ ] Subscribe to coordinator updates
  - [ ] Update state from coordinator data
  - [ ] Show "unknown" when no data
  - [ ] Set `entity_category` as `DIAGNOSTIC` for UI organization

#### Task 4.2: Event System
- [ ] Define event types in `const.py`
- [ ] Fire events from coordinator:
  - [ ] `lighting_manager.layer_activated`
  - [ ] `lighting_manager.layer_deactivated`
  - [ ] `lighting_manager.calculation_complete`
  - [ ] `lighting_manager.conflict_detected`
  - [ ] `lighting_manager.state_applied`
- [ ] Include relevant data in payloads:
  - [ ] Zone and layer identifiers
  - [ ] State changes
  - [ ] Timing information
  - [ ] Conflict details

#### Task 4.3: Device Registry Integration
- [ ] Create zone device on setup:
  - [ ] Manufacturer: "Lighting Manager"
  - [ ] Model: "Adaptive Zone"
  - [ ] SW Version: "4.0.0"
- [ ] Associate all entities:
  - [ ] Switch entities (layers)
  - [ ] Sensor entities
  - [ ] Group under zone device
- [ ] Update device on changes:
  - [ ] Configuration updates
  - [ ] Entity additions/removals

#### Task 4.4: Diagnostics (`diagnostics.py`)
- [ ] Implement `async_get_config_entry_diagnostics()`
- [ ] Include diagnostic data:
  - [ ] Zone configuration
  - [ ] Switch entity states (layers)
  - [ ] Calculation history
  - [ ] Performance metrics
  - [ ] Error logs
- [ ] Redact sensitive information

### PHASE 5: Area and Scene Integration
**Goal**: Integrate with Home Assistant areas and scenes

#### Task 5.1: Area Integration (`area_manager.py`)
- [ ] Create `AreaManager` class
- [ ] Implement area-zone linking:
  - [ ] Store area_id in zone config
  - [ ] Subscribe to area registry changes
  - [ ] Auto-update light list when area changes
- [ ] Implement light discovery:
  - [ ] Find all lights in area
  - [ ] Filter by domain and capabilities
  - [ ] Present to user for confirmation
- [ ] Area-wide operations:
  - [ ] Apply preset to all zones in area
  - [ ] Sync settings across area zones
  - [ ] Area-based automation triggers

#### Task 5.2: Scene Integration (`scene_handler.py`)
- [ ] Create `SceneHandler` class
- [ ] Implement scene → layer activation:
  - [ ] Register scene.turn_on listener
  - [ ] Check if scene contains managed lights
  - [ ] Create/activate corresponding switch entity (layer)
  - [ ] Map scene attributes to layer attributes
- [ ] Implement layer → scene creation:
  - [ ] Service to save current layers as scene
  - [ ] Include all active switch entity states (layers)
  - [ ] Store layer metadata in scene
- [ ] Scene transition support:
  - [ ] Extract transition from scene data
  - [ ] Apply to layer activation
  - [ ] Respect scene priorities

### PHASE 6: Built-in Adaptive Lighting System
**Goal**: Implement circadian and sensor-based adaptation as core system feature

#### Task 6.1: Built-in Adaptive Engine (`adaptive.py`)
- [ ] Create `AdaptiveEngine` as core system component (not external)
- [ ] Implement sun-based calculations:
  - [ ] Track sun elevation using HA sun integration
  - [ ] Calculate color temperature curve (2000K-6500K default)
  - [ ] Calculate brightness curve (10%-100% default)
  - [ ] Use AdaptiveLightFactorSensor as primary data source
- [ ] Implement time-based profiles (REQ-I003):
  - [ ] Define profile structure
  - [ ] Time-of-day curves
  - [ ] Weekday/weekend variations
  - [ ] Override sun-based when active
- [ ] Built-in sensor integration:
  - [ ] Subscribe to sensor changes
  - [ ] Scale values to ranges
  - [ ] Apply to calculations
  - [ ] Default to sun-based when no sensors configured
- [ ] Handle adaptive properties:
  - [ ] Per-zone settings stored in zone config
  - [ ] Per-layer overrides via layer attributes
  - [ ] Global defaults in integration config
- [ ] Automatic adaptive layer creation:
  - [ ] Create "adaptive" layer on zone setup if enabled
  - [ ] Priority 10 (low but not zero)
  - [ ] Auto-update based on sun/time/sensor changes

#### Task 6.2: Built-in Adaptive Layer Support
- [ ] Add adaptive attributes to LayerSwitch (via extra_attributes):
  - [ ] `adaptive_brightness`: Boolean
  - [ ] `adaptive_color_temp`: Boolean
  - [ ] `brightness_range`: (min, max)
  - [ ] `color_temp_range`: (min, max)
  - [ ] `adaptive_mode`: "sun", "time", "sensor", or "disabled"
- [ ] Implement built-in adaptive value calculation:
  - [ ] Check if layer has adaptive enabled
  - [ ] Get current adaptive values from AdaptiveLightFactorSensor
  - [ ] Apply scaling to brightness/color_temp ranges
  - [ ] Update layer state automatically
  - [ ] Trigger zone recalculation
- [ ] Automatic adaptive layer management:
  - [ ] Create on zone setup if adaptive enabled
  - [ ] Update every 5 minutes or on sensor changes
  - [ ] Remove when adaptive disabled for zone

#### Task 6.3: Built-in Adaptive Configuration
- [ ] Add to config flow (zone setup):
  - [ ] Enable/disable built-in adaptive
  - [ ] Default brightness ranges (10-100%)
  - [ ] Default color temp ranges (2000-6500K)
  - [ ] Optional input sensor selection
  - [ ] Adaptive mode selection (sun/time/sensor)
- [ ] Store in config entry:
  - [ ] Per-zone adaptive settings
  - [ ] Default values for new layers
  - [ ] Sensor entity IDs
- [ ] Allow runtime updates:
  - [ ] Via options flow (zone reconfiguration)
  - [ ] Via services (adaptive_layer_update)
  - [ ] Automatic sensor change detection

### PHASE 6: Migration & Compatibility
**Goal**: Smooth transition from existing system

#### Task 6.1: YAML Config Import
- [ ] Detect existing `configuration.yaml` entries
- [ ] Parse entity configurations
- [ ] Create config entries automatically
- [ ] Preserve all settings:
  - [ ] Adaptive ranges
  - [ ] Entity mappings
  - [ ] Input sensors

#### Task 6.2: State Migration
- [ ] Read existing `DATA_STATES` if present
- [ ] Convert to switch entities:
  - [ ] Create switch entity for each existing layer_id
  - [ ] Set priority from stored value
  - [ ] Apply stored state attributes
  - [ ] Convert "active"/"inactive" to "on"/"off"
- [ ] Maintain layer activation status

#### Task 6.3: Service Translation
- [ ] Create compatibility shim for old services:
  - [ ] Map `insert_state` to layer activation
  - [ ] Map `remove_layer` to layer deactivation
  - [ ] Map `insert_scene` to preset application
- [ ] Log deprecation warnings
- [ ] Guide users to new services

### PHASE 7: Testing & Validation
**Goal**: Ensure reliability and performance

#### Task 7.1: Unit Tests
- [ ] Test calculator logic:
  - [ ] Priority resolution
  - [ ] Force flag handling
  - [ ] Lock state handling
  - [ ] Conflict detection
- [ ] Test switch entity (layers):
  - [ ] On/off state changes
  - [ ] Attribute updates
  - [ ] Persistence
- [ ] Test coordinator:
  - [ ] Event handling
  - [ ] Debouncing
  - [ ] Data updates

#### Task 7.2: Integration Tests
- [ ] Test full flow:
  - [ ] Layer change → calculation → application
  - [ ] Service calls → state changes
  - [ ] Event firing → automation triggers
- [ ] Test edge cases:
  - [ ] Unavailable lights
  - [ ] Rapid state changes
  - [ ] Conflicting updates

#### Task 7.3: Performance Tests
- [ ] Measure calculation speed:
  - [ ] 10 layers: < 50ms
  - [ ] 20 layers: < 100ms
- [ ] Test scalability:
  - [ ] 20 zones
  - [ ] 20 layers per zone
  - [ ] 50 lights per zone
- [ ] Monitor memory usage:
  - [ ] Entity overhead
  - [ ] Calculation caching
  - [ ] Event handling

#### Task 7.4: User Acceptance Testing
- [ ] Deploy to test instance
- [ ] Create sample zones and layers
- [ ] Test common scenarios:
  - [ ] Manual override
  - [ ] Scene activation
  - [ ] Adaptive transitions
  - [ ] Conflict resolution
- [ ] Verify UI functionality:
  - [ ] Config flow
  - [ ] Entity cards
  - [ ] Service calls
  - [ ] Sensor visibility

### PHASE 8: Documentation & Polish
**Goal**: Production-ready component

#### Task 8.1: User Documentation
- [ ] Write README.md:
  - [ ] Installation instructions
  - [ ] Configuration guide
  - [ ] Service documentation
  - [ ] Example automations
- [ ] Create wiki pages:
  - [ ] Architecture overview
  - [ ] Layer concepts
  - [ ] Troubleshooting guide

#### Task 8.2: Code Documentation
- [ ] Add docstrings to all classes
- [ ] Document all public methods
- [ ] Include type hints
- [ ] Add inline comments for complex logic

#### Task 8.3: Error Handling
- [ ] Add try/catch blocks
- [ ] Implement graceful degradation
- [ ] Log appropriate messages
- [ ] User-friendly error reporting

#### Task 8.4: Final Polish
- [ ] Code formatting (black/isort)
- [ ] Linting (pylint/flake8)
- [ ] Remove debug code
- [ ] Optimize performance
- [ ] Version tagging

## Implementation Order

Given your test instance availability, I recommend this order:

1. **Start with Phase 1 & 2 together** - Get basic layer entities and calculation working
2. **Add Phase 3** - Services to control layers
3. **Add Phase 4** - Observability for debugging
4. **Add Phase 5** - Adaptive lighting
5. **Skip Phase 6** - No migration needed for fresh install
6. **Continuous Phase 7** - Test as we build
7. **Final Phase 8** - Documentation

## Key Design Decisions

1. **No Prescriptive Layers**: Users create whatever layers they need
2. **Coordinator as Single Source of Truth**: All layer state lives in the coordinator, switches are just views
3. **Pure Calculation**: Calculator has no side effects, completely testable
4. **Event-Driven**: Changes trigger recalculation automatically
5. **Total Visibility**: Every decision is observable via switch entities and sensors
6. **Atomic Operations**: All lights in a zone update together
7. **Store-Based Persistence**: Coordinator state saved to `.storage` for recovery

## Success Metrics

- Layer state changes apply within 200ms
- No hidden state anywhere in the system
- Every lighting decision traceable to specific layers
- Zero race conditions
- Clean separation of concerns

## Critical Implementation Requirements

### Threading Model Rules (MUST FOLLOW)
1. **@callback decorator**: Only for SYNCHRONOUS methods that don't modify state
2. **async methods**: Required for ANY method that modifies state or does I/O
3. **DataUpdateCoordinator**: The `data` property should be simple, `_async_update_data()` does calculations

### Data Flow Requirements
1. **Single source of truth**: `coordinator.layers` is THE state, `coordinator.data` is a property that returns it
2. **No dual state**: Never have separate write location and read location
3. **Validation**: ALL user input must be validated before storage

### Service Implementation Rules
1. **Use entity registry**: Never manually parse entity IDs
2. **Use proper helpers**: `async_extract_referenced_entity_ids()` for entity targeting
3. **Domain-level registration**: Services registered once, not per zone

### Required Validations
- **Brightness**: 0-255 integer
- **Color temp**: 153-500 mireds (or 2000-6500 Kelvin converted)
- **RGB color**: Tuple of 3 integers 0-255
- **Priority**: 0-100 integer
- **Transition**: 0.0-300.0 float (seconds)
- **Layer names**: Slugified for entity ID compatibility
- **Datetime**: Always use timezone-aware (`dt_util.now()` not `datetime.now()`)

### Storage Requirements
1. **Validate on load**: Check data structure and types
2. **Handle corruption**: Graceful fallback to empty state
3. **Atomic saves**: Use Store's built-in safety

### Platform Requirements
1. **sensor.py**: Must exist even if empty (declared in PLATFORMS)
2. **services.yaml**: Must define all services with proper schemas
3. **translations**: Must include all user-facing strings

## Lessons Learned from Initial Implementation

### Critical Architecture Violations to Avoid

1. **❌ NEVER extend RestoreEntity for switches**
   - Switches must extend only `CoordinatorEntity, SwitchEntity`
   - All state restoration happens through the coordinator's Store

2. **❌ NEVER store state in switch entities**
   - No `_attr_is_on`, `_priority`, `_brightness` etc. in switches
   - ALL state lives in `coordinator.layers` dictionary

3. **❌ NEVER modify state directly in switches**
   - `async_turn_on()` must call `coordinator.update_layer()`
   - Switches are read-only views, write-only commands

4. **✅ ALWAYS read from coordinator.data in switches**
   ```python
   @property
   def is_on(self) -> bool:
       layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
       return layer_data.get("is_on", False)
   ```

5. **✅ ALWAYS implement Store in coordinator from the start**
   - Load layers in `async_load()` during setup
   - Save on every change with debouncing
   - This is the ONLY place state is persisted

6. **✅ ALWAYS properly reconstruct options in options flow**
   - Brightness and color temp ranges must be reconstructed as arrays
   - Don't pass individual min/max values directly

### Implementation Order Corrections

- Start coordinator implementation BEFORE switches
- Implement Store persistence immediately, not later
- Test coordinator state management before adding UI elements