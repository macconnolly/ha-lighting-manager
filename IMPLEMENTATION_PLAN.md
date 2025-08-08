## 1. Vision & Guiding Principles

This document is the definitive engineering blueprint for modernizing the `lighting_manager` custom component. It is designed to be a complete guide for a developer of average proficiency to create a best-in-class Home Assistant integration that is architecturally pure, observable, and maintainable, fulfilling all specifications in `REQUIREMENTS.md`.

The core architectural transformation is the elevation of **layers from an internal data structure to first-class Home Assistant entities.** This single change is the foundation upon which all other principles rest:

-   **Architectural Purity:** All state that influences lighting decisions must be stored in `layer` entities. There will be **no hidden state**.
-   **Total Observability:** Any user or developer can understand the system's behavior at a glance by inspecting the `layer` and `sensor` entities in the UI.
-   **Reactive & Event-Driven:** The system will react to changes in `layer` entities, not poll for them. The `ZoneCoordinator` is the heart of this reactive engine.
-   **Single Source of Truth:** The state and attributes of the `layer` entities are the *only* source of truth for the calculation engine.
-   **Calculate → Store → Apply:** We will rigorously follow this pattern to ensure stability and prevent race conditions.

## 2. Target File Structure

The final component will be organized as follows:

```
custom_components/lighting_manager/
├── __init__.py             # Handles entry setup, service registration, and the LightingManager class.
├── manifest.json           # Component manifest, declaring the domain, version, and config flow.
├── config_flow.py          # Manages UI-based Zone creation and configuration.
├── coordinator.py          # Defines the ZoneCoordinator, the core orchestration engine.
├── const.py                # Stores all shared constants (DOMAIN, service names, etc.).
├── layer.py                # Defines the custom `layer` entity platform and the LayerEntity class.
├── sensor.py               # Defines the observability sensor platform.
├── services.yaml           # Defines the public API for interacting with layers and zones.
└── translations/
    └── en.json             # UI strings for the config flow.
```

## 3. Phased Implementation Plan

This plan is broken into discrete, sequential phases. Each task builds upon the last.

---

### **Phase 1: The Bedrock - The `layer` Entity & Zone Onboarding**

**Goal:** Establish the most fundamental component: the `layer` entity. At the end of this phase, a user can add a "Lighting Manager" integration from the UI, create a Zone, and see the corresponding `layer` entities appear in Home Assistant.

#### **Task 1.1: Project Scaffolding**
-   **File:** `manifest.json`
    -   **Action:** Ensure the file contains: `{"domain": "lighting_manager", "name": "Lighting Manager", "config_flow": true, "version": "4.0.0", "iot_class": "local_push"}`. This declares the component and enables UI configuration.
-   **File:** `const.py`
    -   **Action:** Create this file. Define all required constants, including `DOMAIN = "lighting_manager"`, platform names (`PLATFORMS = ["layer", "sensor"]`), service names (`SERVICE_ACTIVATE_LAYER = "activate_layer"`), and the default layer names and priorities as specified in **REQ-L006**.

#### **Task 1.2: Zone Onboarding (Config Flow)**
-   **File:** `config_flow.py`
    -   **Action:** Implement the `AdaptiveLightingConfigFlow` class.
    -   **Action:** Define `async_step_user`. This method will show a form asking for a `zone_name` (string) and `light_entities` (a `light` entity selector). This fulfills **REQ-C001** and **REQ-C002**.
    -   **Action:** Upon submission, create the `ConfigEntry` with the `zone_name` and `light_entities` stored in its data.

#### **Task 1.3: The `layer` Entity Platform**
-   **File:** `layer.py`
    -   **Action:** Create this file to define the new `layer` platform.
    -   **Action:** Implement `async_setup_entry`. This function will be called when a `ConfigEntry` is created. It will read the `zone_name` from the entry data.
    -   **Action:** Inside `async_setup_entry`, create and add the five standard `LayerEntity` objects for that zone, fulfilling **REQ-L006**. The entity IDs must follow the `layer.{zone_id}_{layer_id}` pattern (**REQ-L004**).
-   **File:** `layer.py`
    -   **Action:** Define the `LayerEntity` class.
    -   **Action:** It **must** inherit from `homeassistant.helpers.entity.RestoreEntity` to persist its state across restarts (**REQ-L007**).
    -   **Action:** The entity's `state` property will return a boolean representing if it is `active`.
    -   **Action:** The entity's `extra_state_attributes` property will return a dictionary containing all other mutable properties from **REQ-L005**: `priority`, `brightness`, `color_temp`, `rgb_color`, `transition`, `force`, `locked`, `source`, and `last_updated`.

---

### **Phase 2: The Engine - Calculation & Control**

**Goal:** Make the system functional. Changes to `layer` entities will now be observed, calculated, and applied to the target lights.

#### **Task 2.1: The Orchestration Engine (Coordinator)**
-   **File:** `coordinator.py`
    -   **Action:** Create the `ZoneCoordinator` class, inheriting from `DataUpdateCoordinator`.
    -   **Action:** The coordinator's `__init__` will receive the `zone_id` and a reference to the `LightingManager` instance. It will immediately find all `layer` entities associated with its zone and store their entity IDs.
    -   **Action:** The coordinator will register itself as a listener for state changes on **only its own `layer` entities**. This is the event-driven trigger (**REQ-O003**). Any change will call `async_request_refresh`.
    -   **Action:** Implement the `_async_update_data` method. This is the **Calculate** step. It will call a method on the `LightingManager` instance (`lighting_manager.calculate_zone_state()`) which contains the existing, proven priority logic. This method will return the final, calculated state for the lights.
    -   **Action:** The data returned by `_async_update_data` is the **Store** step. It will contain the final light state and all debug information required for the sensors (**REQ-S001**-**S007**).

#### **Task 2.2: Refactoring the `LightingManager` Core Logic**
-   **File:** `__init__.py`
    -   **Action:** The `LightingManager` class is refactored. **Crucially, remove the `self.states` dictionary.** The class no longer holds internal state.
    -   **Action:** Create a new method `calculate_zone_state`. This method will contain the core logic from the old `render_entity` function.
    -   **Action:** This method will **not** read from `self.states`. Instead, it will get the current states of the relevant `layer` entities directly from `hass.states.get(layer_entity_id)`. It will then perform the priority resolution (**REQ-O006**), force flag check (**REQ-O007**), and locked check (**REQ-O008**) to determine the winning layer and return the result.

#### **Task 2.3: State Application**
-   **File:** `__init__.py`
    -   **Action:** In `async_setup_entry`, after creating the coordinator, register a listener using `coordinator.async_add_listener`.
    -   **Action:** The callback function for this listener is the **Apply** step. It will be extremely simple:
        1.  Get the final state from `coordinator.data`.
        2.  Call the `light.turn_on` service for the zone's lights with the data from the coordinator. This fulfills **REQ-O014**.

---

### **Phase 3: The API - Services & Events**

**Goal:** Expose a clean, intuitive API for users and automations to control the system.

#### **Task 3.1: Modernizing Services**
-   **File:** `services.yaml`
    -   **Action:** Define all services specified in `REQUIREMENTS.md`, Section 4. The `target` for layer-specific services should be an `entity` of the `lighting_manager` domain (which will resolve to our `layer` entities).
-   **File:** `__init__.py`
    -   **Action:** Register the service handlers. The handlers will be dramatically simplified.
    -   **Action:** The `activate_layer` service handler (**REQ-A001**) will now:
        1.  Get the target `layer` entity from the service call.
        2.  Update its state to `active`.
        3.  Update its attributes (`brightness`, `source`, etc.) with the data from the service call.
    -   **Action:** The `deactivate_layer` service handler (**REQ-A002**) will simply set the target `layer` entity's state to `inactive`.
    -   **Architectural Note:** Because the `ZoneCoordinator` is listening to these entities, these service calls automatically trigger the entire Calculate->Store->Apply cycle.

#### **Task 3.2: The Event Bus**
-   **File:** `coordinator.py`
    -   **Action:** In the `_async_update_data` method, after a successful calculation, fire the events required by **REQ-S008** through **REQ-S012**. The event payload will be populated with data from the calculation result (e.g., `winning_layer`, `final_state`, `conflicts`).

---

### **Phase 4: Total System Observability**

**Goal:** Make the system completely transparent and easy to debug from the UI.

#### **Task 4.1: The Sensor Platform**
-   **File:** `sensor.py`
    -   **Action:** Implement `async_setup_entry`. It will create a suite of sensors for the zone.
    -   **Action:** All sensor classes will inherit from `CoordinatorEntity`.
    -   **Action:** Each sensor will be linked to the `ZoneCoordinator` instance for its zone.
    -   **Action:** The `state` of each sensor will be a simple property that reads a specific key from the coordinator's data. For example, the "Winning Layer" sensor's state will be `self.coordinator.data['winning_layer']`. This makes the sensors incredibly efficient and always in sync. This fulfills all sensor requirements (**REQ-S001**-**S007**).

#### **Task 4.2: Device Registry Integration**
-   **Files:** `layer.py`, `sensor.py`
    -   **Action:** In the `async_setup_entry` for both platforms, when creating a Zone, first create a `Device` entry in the Home Assistant Device Registry.
    -   **Action:** Ensure every `LayerEntity` and `SensorEntity` created for that zone has its `device_info` property pointing to this parent Zone device. This will group all related entities neatly in the UI, fulfilling **REQ-C004** and **REQ-C005**.
