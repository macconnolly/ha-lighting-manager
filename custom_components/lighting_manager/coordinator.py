"""Zone Coordinator - Pure orchestrator following sacred separation of concerns."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

# Import all components
from .adaptive_provider import AdaptiveProvider
from .change_detector import ChangeDetector
from .layer_manager import LayerManager
from .light_controller import LightController
from .state_calculator import StateCalculator
from .zone_state_machine import ZoneState, ZoneStateMachine

from .const import (
    DOMAIN,
    EVENT_CALCULATION_COMPLETE,
    EVENT_CALCULATION_FAILED,
)

_LOGGER = logging.getLogger(__name__)


class ZoneCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Zone Coordinator - Pure orchestrator.
    
    CRITICAL: This coordinator contains NO business logic.
    It ONLY orchestrates between components.
    """
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator as pure orchestrator.
        
        Args:
            hass: Home Assistant instance
            entry: Config entry
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data['zone_id']}",
            config_entry=entry,
        )
        
        # Basic configuration
        self.config_entry = entry
        self.zone_id = entry.data["zone_id"]
        self.zone_name = entry.data["zone_name"]
        self.light_entities = entry.options.get("light_entities", [])
        
        # Initialize all components (separation of concerns)
        self.layer_manager = LayerManager(hass, self.zone_id)
        self.state_calculator = StateCalculator()
        self.light_controller = LightController(hass, self.zone_id, self.light_entities)
        self.adaptive_provider = AdaptiveProvider(hass, entry.options)
        self.state_machine = ZoneStateMachine(hass, self.zone_id)
        
        # Initialize change detector after other components
        self.change_detector = ChangeDetector(
            hass,
            self.zone_id,
            self.layer_manager,
            self.light_controller
        )
        
        # Event listeners
        self._cleanup_tasks: List[Callable] = []
        self._manual_check_task = None
        self._sun_listener = None
        self._debounce_timer = None
        
        # Fail-safe state
        self._last_known_good_state: Optional[Dict[str, Any]] = None
        
        # Compatibility properties
        self.layers = self.layer_manager.layers  # Direct reference for switch platform
        self.new_layer_callback = None  # For dynamic switch creation
        
        # Initial data structure
        self.data = self._create_empty_data()
        
        _LOGGER.info(
            "ZoneCoordinator initialized for zone %s with %d lights",
            self.zone_id, len(self.light_entities)
        )
    
    async def async_load(self) -> None:
        """Initialize all components and set up monitoring."""
        _LOGGER.info("Loading coordinator for zone %s", self.zone_id)
        
        # Load layers from storage
        await self.layer_manager.load()
        
        # Set up component listeners
        self.layer_manager.add_listener(self._on_layers_changed)
        self.state_machine.add_listener(self._on_state_changed)
        
        # Start manual control detection (every 5 seconds)
        self._manual_check_task = async_track_time_interval(
            self.hass,
            self._check_manual_control,
            timedelta(seconds=5)
        )
        self._cleanup_tasks.append(self._manual_check_task)
        
        # Track sun changes if adaptive enabled
        if self.adaptive_provider.enabled:
            self._sun_listener = async_track_state_change_event(
                self.hass,
                "sun.sun",
                self._on_sun_changed
            )
            self._cleanup_tasks.append(self._sun_listener)
        
        # Set initial zone state
        self.state_machine.transition_to(ZoneState.AUTO, "initialization")
        
        # Read current light state as baseline (don't apply anything)
        current_state = self.light_controller.get_current_state()
        self.light_controller.last_commanded_state = current_state
        self._last_known_good_state = current_state
        
        _LOGGER.info(
            "Coordinator loaded for zone %s: %d layers, current lights: %s",
            self.zone_id, len(self.layer_manager.layers), current_state
        )
    
    # Event Handlers (pure routing, no logic)
    
    @callback
    def _on_layers_changed(self) -> None:
        """Handle layer changes - route to update."""
        _LOGGER.debug("Layers changed in zone %s", self.zone_id)
        self._schedule_update("layer_change")
    
    @callback
    def _on_state_changed(self, old_state: ZoneState, new_state: ZoneState) -> None:
        """Handle zone state changes - route to update."""
        _LOGGER.debug(
            "Zone %s state changed: %s -> %s",
            self.zone_id, old_state.value, new_state.value
        )
        self._schedule_update("state_change")
    
    @callback
    def _on_sun_changed(self, event) -> None:
        """Handle sun position changes - route to update."""
        _LOGGER.debug("Sun changed for zone %s", self.zone_id)
        self._schedule_update("sun_change")
    
    @callback
    async def _check_manual_control(self, now) -> None:
        """Periodic check for manual control."""
        # Skip if zone is locked
        if self.state_machine.state == ZoneState.LOCKED:
            return
        
        # Check for manual changes
        if self.change_detector.check_for_manual_change():
            _LOGGER.info("Manual control detected in zone %s", self.zone_id)
            
            # Create override layer
            override_id = self.change_detector.create_manual_override(timeout_hours=2.0)
            
            # Transition to manual override state
            self.state_machine.transition_to(
                ZoneState.MANUAL_OVERRIDE,
                f"manual control detected, created {override_id}"
            )
            
            # Save layers (but not the temporary override)
            await self.layer_manager.save()
            
            # Trigger update
            self._schedule_update("manual_override")
    
    def _schedule_update(self, trigger: str = "unknown") -> None:
        """Schedule an update with debouncing.
        
        Args:
            trigger: What triggered this update
        """
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        self._debounce_timer = self.hass.loop.call_later(
            0.1,  # 100ms debounce
            lambda: self.hass.async_create_task(self._do_update(trigger))
        )
    
    async def _do_update(self, trigger: str) -> None:
        """Perform the actual update."""
        self.data["trigger"] = trigger
        await self.async_refresh()
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Main orchestration loop - coordinate between components.
        
        This is the ONLY place where components interact.
        """
        try:
            _LOGGER.debug("Update cycle for zone %s (trigger: %s)", self.zone_id, self.data.get("trigger"))
            
            # Step 1: Get adaptive values
            adaptive_values = self.adaptive_provider.get_adaptive_values()
            
            # Step 2: Get active layers
            active_layers = self.layer_manager.get_active_layers()
            
            # Step 3: Calculate desired state
            calc_result = self.state_calculator.calculate_state(
                active_layers,
                adaptive_values
            )
            
            # Step 4: Apply state if appropriate
            if self.state_machine.state in [ZoneState.AUTO, ZoneState.MANUAL_OVERRIDE]:
                success = await self.light_controller.apply_state(calc_result)
                if success:
                    self._last_known_good_state = calc_result
            else:
                _LOGGER.debug(
                    "Not applying state in zone %s (state: %s)",
                    self.zone_id, self.state_machine.state.value
                )
            
            # Step 5: Check for expired overrides
            if self.change_detector.is_override_expired():
                _LOGGER.info("Manual override expired in zone %s", self.zone_id)
                self.change_detector.clear_manual_override()
                self.state_machine.transition_to(ZoneState.AUTO, "override expired")
            
            # Step 6: Fire success event
            self.hass.bus.async_fire(
                EVENT_CALCULATION_COMPLETE,
                {
                    "zone_id": self.zone_id,
                    "trigger": self.data.get("trigger", "unknown"),
                    "winning_layer": calc_result.get("winning_layer"),
                    "final_state": calc_result,
                    "zone_state": self.state_machine.state.value,
                }
            )
            
            # Step 7: Update data for entities
            self.data = {
                "layers": self.layer_manager.get_all_layers(),
                "active_layers": [l["layer_id"] for l in active_layers],
                "zone_state": self.state_machine.state.value,
                "zone_state_info": self.state_machine.get_state_info(),
                "manual_override_active": self.change_detector.manual_override_active,
                "adaptive_values": adaptive_values,
                "winning_layer": calc_result.get("winning_layer"),
                "final_state": calc_result,
                "applied_modifiers": calc_result.get("applied_modifiers", []),
                "conflicts": calc_result.get("conflicts", []),
                "calculation_path": calc_result.get("calculation_path", []),
                "last_commanded_state": self.light_controller.last_commanded_state,
                "current_actual_state": self.light_controller.get_current_state(),
                "circuit_breaker_status": self.light_controller.get_circuit_status(),
                "last_updated": dt_util.now().isoformat(),
                "trigger": self.data.get("trigger", "unknown"),
                "error": None,
            }
            
            return self.data
            
        except Exception as err:
            _LOGGER.error(
                "Error in update cycle for zone %s: %s",
                self.zone_id, err, exc_info=True
            )
            
            # Fire failure event
            self.hass.bus.async_fire(
                EVENT_CALCULATION_FAILED,
                {
                    "zone_id": self.zone_id,
                    "error": str(err),
                    "trigger": self.data.get("trigger", "unknown"),
                }
            )
            
            # Use fail-safe state
            if self._last_known_good_state:
                _LOGGER.info("Using last known good state for zone %s", self.zone_id)
                self.data["final_state"] = self._last_known_good_state
            
            self.data["error"] = str(err)
            return self.data
    
    # Compatibility methods for existing code
    
    async def create_layer(self, layer_name: str, **attributes) -> str:
        """Create a new layer (compatibility method)."""
        layer_id = layer_name.lower().replace(" ", "_")
        
        # Ensure unique ID
        suffix = 1
        test_id = layer_id
        while test_id in self.layer_manager.layers:
            test_id = f"{layer_id}_{suffix}"
            suffix += 1
        layer_id = test_id
        
        # Create layer
        layer_data = {
            "layer_name": layer_name,
            "is_on": False,
            **attributes,
        }
        
        self.layer_manager.create_layer(layer_id, layer_data)
        
        # Save if not temporary
        if attributes.get("source") != "manual_override":
            await self.layer_manager.save()
        
        # Notify switch platform
        if self.new_layer_callback:
            await self.new_layer_callback(layer_id, layer_name)
        
        return layer_id
    
    async def update_layer(self, layer_id: str, **updates) -> bool:
        """Update a layer (compatibility method)."""
        success = self.layer_manager.update_layer(layer_id, updates)
        
        if success and self.layer_manager.has_pending_save():
            await self.layer_manager.save()
        
        return success
    
    async def delete_layer(self, layer_id: str) -> bool:
        """Delete a layer (compatibility method)."""
        success = self.layer_manager.delete_layer(layer_id)
        
        if success:
            await self.layer_manager.save()
        
        return success
    
    def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Get a layer (compatibility method)."""
        return self.layer_manager.get_layer(layer_id)
    
    def schedule_recalculation(self) -> None:
        """Schedule recalculation (compatibility method)."""
        self._schedule_update("manual_trigger")
    
    async def save_layers(self) -> None:
        """Save layers (compatibility method)."""
        await self.layer_manager.save()
    
    def schedule_save(self) -> None:
        """Schedule save (compatibility method)."""
        self.hass.async_create_task(self.layer_manager.save())
    
    async def async_shutdown(self) -> None:
        """Clean up when coordinator is removed."""
        _LOGGER.info("Shutting down coordinator for zone %s", self.zone_id)
        
        # Cancel all listeners
        for cleanup_task in self._cleanup_tasks:
            if cleanup_task:
                cleanup_task()
        
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        # Final save
        await self.layer_manager.save()
        
        _LOGGER.info("Coordinator shutdown complete for zone %s", self.zone_id)
    
    def _create_empty_data(self) -> Dict[str, Any]:
        """Create empty data structure."""
        return {
            "layers": {},
            "active_layers": [],
            "zone_state": ZoneState.OFF.value,
            "zone_state_info": {},
            "manual_override_active": False,
            "adaptive_values": {},
            "winning_layer": None,
            "final_state": {"power": "off"},
            "applied_modifiers": [],
            "conflicts": [],
            "calculation_path": [],
            "last_commanded_state": {},
            "current_actual_state": {},
            "circuit_breaker_status": {"state": "closed"},
            "last_updated": None,
            "trigger": None,
            "error": None,
        }