- You are an expert Home Assistant software architect. Your sole task is to refactor the "Lighting Manager" custom integration to be a
  production-grade, robust, and beautifully architected component, strictly adhering to the principles outlined below.

  These principles are non-negotiable.

  Core Architectural Mandates

   1. The Sacred Separation of Concerns: You must decompose the logic into the following single-responsibility classes. Do not add logic to a
      component that does not belong there.
       * `ZoneCoordinator`: Orchestrator only. It manages the other components and handles the main event loop. It contains no direct
         calculation, storage, or hardware control logic.
       * `LayerManager`: State storage only. Manages the CRUD (Create, Read, Update, Delete) operations and persistence of layers.
       * `StateCalculator`: Pure calculation only. It must be a pure function with no Home Assistant imports. Its only job is to take state
         and return a result.
       * `LightController`: Hardware control only. Its only job is to apply a calculated state to physical light entities.
       * `ChangeDetector`: Manual override detection only. It listens for out-of-band changes to lights.
       * `AdaptiveProvider`: Reference values only. It provides adaptive brightness/color values as a baseline; it must not create a layer.
       * `ZoneStateMachine`: Manages the zone's high-level state (AUTO, MANUAL_OVERRIDE, etc.).

   2. Idempotent and Atomic Services: All services that modify state must be idempotent.
       * There shall be a single `set_layer` service that handles both creation and updates (an "upsert" operation). The create_layer and
         update_layer services are to be deprecated and removed. The set_layer service is the single, atomic entry point for all declarative
         layer configuration.

   3. Total Observability: All state must be visible in the UI for debugging.
       * Internal states of components (e.g., the current ZoneState, the last-commanded state from the LightController) must be exposed as
         attributes on the diagnostic sensor.
       * Fire detailed events on the HA event bus for key actions (calculation_complete, manual_change_detected, state_transition_failed,
         etc.).

   4. Stateless Views: All Home Assistant entities (e.g., switch entities for layers) must be stateless views of the data held in the
      LayerManager and orchestrated by the ZoneCoordinator. They must not have their own state variables.

   5. Purely Event-Driven: The integration must never poll for state changes. Use async_track_state_change_event and other event-driven helpers
      for all reactivity. The only exception is a timed check for manual overrides if an event-based approach proves too complex.

   6. Resilience First: Implement defensive patterns.
       * The LightController should have a circuit breaker pattern to stop sending commands if lights become unresponsive.
       * The ZoneCoordinator's calculation loop must have a fail-safe and use the last known good state if a calculation fails.
 Before writing any code, present your step-by-step implementation plan for approval. Then, generate the code for one component at a time
  so we can review it.