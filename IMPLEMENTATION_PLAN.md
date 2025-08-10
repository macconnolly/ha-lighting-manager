# Lighting Manager - Implementation Plan v4.0: The Unified Architecture

## 1. Vision & Guiding Principles

This document is the definitive engineering blueprint for modernizing the `lighting_manager` custom component. It is designed to be a complete guide for a developer of average proficiency to create a best-in-class Home Assistant integration that is architecturally pure, observable, and maintainable, fulfilling all specifications in `REQUIREMENTS.md`.

The core architectural transformation is the elevation of **layers from an internal data structure to first-class Home Assistant entities.** This single change is the foundation upon which all other principles rest:

- **Architectural Purity:** All state that influences lighting decisions must be stored in `layer` entities. There will be **no hidden state**.
- **Total Observability:** Any user or developer can understand the system's behavior at a glance by inspecting the `layer` and `sensor` entities in the UI.
- **Reactive & Event-Driven:** The system will react to changes in `layer` entities, not poll for them. The `ZoneCoordinator` is the heart of this reactive engine.
- **Single Source of Truth:** The state and attributes of the `layer` entities are the *only* source of truth for the calculation engine.
- **Calculate → Store → Apply:** We will rigorously follow this pattern to ensure stability and prevent race conditions.

## 2. Target File Structure

```
custom_components/lighting_manager/
├── __init__.py            # Setup, service registration and teardown
├── manifest.json
├── config_flow.py         # UI-based configuration (with YAML import support)
├── coordinator.py         # ZoneCoordinator (calculation + schedule)
├── manager.py             # LightingManager (pure calculation logic)
├── layer.py               # Layer entity platform (RestoreEntity)
├── adaptive.py            # Adaptive brightness/colour-temperature helpers
├── sensor.py              # Observability sensors
├── services.yaml          # Full service definitions and schemas
├── const.py               # Constants and keys
└── translations/
    └── en.json            # i18n strings
```

## 3. Phased Implementation Plan

### Phase 1 – Foundations (Layers, Config Flow & Basic Control)
1. **Manifest & Constants**
   - Update `manifest.json` to version 4.0.0 with `config_flow: true`, `integration_type: service`, and `iot_class: local_push`.
   - In `const.py` define the domain string (`lighting_manager`), default layer names/priorities, service names, and any shared data keys.
2. **Config Flow**
   - `config_flow.py` collects a zone name and one or more light entities. Optional YAML import for migration.
   - Store zone ID, light list, and default adaptive parameters in config entries. Provide an options flow for editing.
3. **Layer Entities**
   - `layer.py` defines `LayerEntity` inheriting from `RestoreEntity`.
   - `async_setup_entry` creates five default layers (`base_adaptive`, `environmental`, `activity`, `mode`, `manual`) per zone using pattern `layer.{zone}_{layer_id}`.
   - Methods for activation, deactivation, and attribute updates.
4. **Service Registration**
   - Register `activate_layer`, `update_layer`, and `deactivate_layer` services in `__init__.py` and define selectors in `services.yaml`.
5. **ZoneCoordinator (Initial)**
   - `coordinator.py` inherits from `DataUpdateCoordinator`.
   - Watches only its zone's layer entities. Debounce state changes (~100 ms) and perform an initial refresh at startup.
6. **LightingManager (Initial)**
   - Implement `calculate_zone_state(active_layers)` as a pure function resolving priorities, force, and lock flags.
   - Returns ordered active layers, winning layer ID, and final state dict.
7. **Apply Step**
   - After calculation, apply the final state to all zone lights via `light.turn_on` using only provided attributes.

### Phase 2 – Adaptive Behaviour and State Storage
- Adaptive factor computation and brightness sensor mapping in `adaptive.py`.
- Track adaptive entities per zone and overlay adaptive values when calculating final states.
- Implement `add_adaptive` and `remove_adaptive` services.

### Phase 3 – Advanced Services and Scene/State Insertion
- `insert_scene` and `insert_state` services with layer storage and adaptive attribute parsing.
- `remove_layer`, `refresh`, and `refresh_all` utilities.
- Conflict detection and priority management enhancements.

### Phase 4 – Observability & Events
- Comprehensive sensor suite for active layers, winning layer, calculation input/output, conflicts, and performance.
- Event emission for layer activation/deactivation, calculation completion, conflict detection, and state application.
- Device registry integration to group zone entities.

### Phase 5 – Configuration & Documentation Alignment
- Determine YAML support or update README for config entries only.
- Maintain up-to-date documentation and translations.

### Phase 6 – Testing & Performance
- Unit tests for calculation logic and adaptive helpers.
- Integration tests for services and event firing.
- Benchmarking to meet performance requirements.

