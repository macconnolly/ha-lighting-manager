"""Sensor platform for Lighting Manager - Phase 4 Observability.

This module implements the consolidated 2-sensor approach:
1. Active Layer Sensor - User-facing, shows what's controlling lights
2. Zone Status Sensor - Diagnostic, shows health and debugging info

Based on critical review findings to prevent:
- UI chaos from 140 sensors
- Database destruction from verbose updates
- Performance collapse from update storms
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DATA_COORDINATOR, 
    CONF_ADAPTIVE_ENABLED,
    ATTR_LAYER_TYPE,
    LAYER_TYPE_MODIFIER,
    LAYER_TYPE_MULTIPLIER,
    SW_VERSION,
)
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)


class LightingManagerSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for all Lighting Manager sensors.
    
    CRITICAL: All sensors MUST be CoordinatorEntity subclasses to:
    - Ensure single source of truth
    - Prevent update storms
    - Maintain data consistency
    """
    
    def __init__(
        self,
        coordinator: ZoneCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.zone_id}_{description.key}"
        self._attr_has_entity_name = True
        # Link to zone device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.zone_id)},
            "name": coordinator.zone_name,
            "manufacturer": "Lighting Manager",
            "model": "Zone Controller",
            "sw_version": SW_VERSION,
        }
    
    @property
    def available(self) -> bool:
        """Return if entity is available.
        
        CRITICAL: Must check coordinator.data is not None to prevent
        exceptions during startup or calculation failures.
        """
        return super().available and self.coordinator.data is not None
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.
        
        Read-only view - NEVER trigger recalculations from here.
        """
        self.async_write_ha_state()


class ActiveLayerSensor(LightingManagerSensorBase):
    """Sensor showing the currently active layer.
    
    Primary user-facing sensor for automations and UI.
    Shows WHAT is controlling the lights with minimal attributes.
    """
    
    def __init__(
        self,
        coordinator: ZoneCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize active layer sensor."""
        super().__init__(coordinator, description)
        self._attr_icon = "mdi:layers"
    
    @property
    def native_value(self) -> str | None:
        """Return the active layer name."""
        if not self.coordinator.data:
            return None
        
        # Get winning layer from coordinator data
        winning_layer = self.coordinator.data.get("winning_layer")
        if not winning_layer:
            return "none"
        
        # Return human-friendly name
        layer_data = self.coordinator.layers.get(winning_layer, {})
        return layer_data.get("layer_name", winning_layer)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return minimal, safe attributes for automation use.
        
        CRITICAL: Keep attributes small and JSON-serializable.
        No raw dictionaries, no user data, no secrets.
        """
        if not self.coordinator.data:
            return {}
        
        attrs = {}
        winning_layer = self.coordinator.data.get("winning_layer")
        
        if winning_layer and winning_layer in self.coordinator.layers:
            layer = self.coordinator.layers[winning_layer]
            
            # Basic layer info
            attrs["layer_id"] = winning_layer
            attrs["priority"] = layer.get("priority", 0)
            
            # Add light state if available
            if "brightness" in layer:
                attrs["brightness"] = layer["brightness"]
            if "color_temp" in layer:
                attrs["color_temp"] = layer["color_temp"]
            if "rgb_color" in layer:
                attrs["rgb_color"] = layer["rgb_color"]
            
            # Add source if tracked (sanitized)
            if "source" in layer:
                # Only include source name, not full path
                source = layer["source"]
                if isinstance(source, str):
                    attrs["source"] = source.split(".")[-1] if "." in source else source
            
            # Add human-readable reason for winning
            active_layers = self.coordinator.data.get("active_layers", [])
            if len(active_layers) > 1:
                attrs["reason"] = f"{layer.get('layer_name', winning_layer)} wins with priority {layer.get('priority', 0)}"
            elif len(active_layers) == 1:
                attrs["reason"] = f"Only {layer.get('layer_name', winning_layer)} is active"
            else:
                attrs["reason"] = "No active layers"
        
        return attrs


class ZoneStatusSensor(LightingManagerSensorBase):
    """Diagnostic sensor for zone health and debugging.
    
    Hidden by default via diagnostic category.
    Shows HOW the system is working with verbose (but safe) attributes.
    """
    
    def __init__(
        self,
        coordinator: ZoneCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize diagnostic sensor."""
        super().__init__(coordinator, description)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:information-outline"
    
    @property
    def native_value(self) -> str:
        """Return zone status as simple enum.
        
        States:
        - ok: Everything normal
        - conflict: Multiple layers at same priority
        - calculating: Currently processing
        - error: Calculation failed
        - unavailable: No coordinator data
        """
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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return comprehensive diagnostic attributes for debugging.
        
        Includes all internal state for full observability per architecture spec.
        """
        if not self.coordinator.data:
            return {}
        
        data = self.coordinator.data
        attrs = {}
        
        # Zone state machine information
        attrs["zone_state"] = data.get("zone_state")
        attrs["zone_state_info"] = data.get("zone_state_info", {})
        
        # Manual control detection
        attrs["manual_override_active"] = data.get("manual_override_active")
        
        # Light controller states
        attrs["last_commanded_state"] = data.get("last_commanded_state", {})
        attrs["current_actual_state"] = data.get("current_actual_state", {})
        
        # Circuit breaker status
        attrs["circuit_breaker_status"] = data.get("circuit_breaker_status", {})
        
        # Adaptive lighting values
        attrs["adaptive_values"] = data.get("adaptive_values", {})
        
        # Calculation details
        attrs["winning_layer"] = data.get("winning_layer")
        attrs["applied_modifiers"] = data.get("applied_modifiers", [])
        attrs["conflicts"] = data.get("conflicts", [])
        attrs["calculation_path"] = data.get("calculation_path", [])
        
        # Timing information
        attrs["last_updated"] = data.get("last_updated")
        attrs["trigger"] = data.get("trigger")
        
        # Error state if any
        attrs["error"] = data.get("error")
        
        # List active layers (names only for readability)
        active_layers = data.get("active_layers", [])
        if active_layers:
            attrs["active_layer_names"] = [
                self.coordinator.layers.get(lid, {}).get("layer_name", lid)
                for lid in active_layers
            ]
            attrs["active_layer_count"] = len(active_layers)
        
        # Add zone configuration summary
        attrs["total_layers"] = len(self.coordinator.layers)
        attrs["total_lights"] = len(self.coordinator.light_entities)
        
        return attrs


class GlobalZonesSensor(SensorEntity):
    """Global sensor listing all lighting zones.
    
    This sensor enables automations to iterate over all zones
    without hardcoding zone names. Critical for the "one automation
    for all zones" use case.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the global zones sensor."""
        self.hass = hass
        self._attr_unique_id = "lighting_manager_zones"
        self._attr_has_entity_name = False  # Use explicit name
        self._attr_name = "Lighting Manager Zones"
        self._attr_icon = "mdi:home-group"
        
        # Track all registered zones
        self._zones: dict[str, dict[str, Any]] = {}
        self._coordinators: dict[str, Any] = {}
        
        # Set device info to group under the integration
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "global")},
            "name": "Lighting Manager",
            "manufacturer": "Lighting Manager",
            "model": "Zone Controller",
            "sw_version": SW_VERSION,
        }
        
        _LOGGER.info("GlobalZonesSensor initialized")
    
    def register_zone(self, entry_id: str, zone_id: str, zone_name: str, 
                     coordinator: Any) -> None:
        """Register a zone with the global sensor."""
        self._zones[entry_id] = {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "adaptive_enabled": coordinator.config_entry.options.get(
                CONF_ADAPTIVE_ENABLED, False
            ),
        }
        self._coordinators[entry_id] = coordinator
        
        _LOGGER.debug("Registered zone %s with global sensor", zone_id)
        
        # Schedule update
        if self.hass and hasattr(self, "async_write_ha_state"):
            self.async_schedule_update_ha_state()
    
    def unregister_zone(self, entry_id: str) -> None:
        """Unregister a zone from the global sensor."""
        if entry_id in self._zones:
            zone_id = self._zones[entry_id]["zone_id"]
            del self._zones[entry_id]
            if entry_id in self._coordinators:
                del self._coordinators[entry_id]
            
            _LOGGER.debug("Unregistered zone %s from global sensor", zone_id)
            
            # Schedule update
            if self.hass and hasattr(self, "async_write_ha_state"):
                self.async_schedule_update_ha_state()
    
    @property
    def native_value(self) -> int:
        """Return the number of zones."""
        return len(self._zones)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone information for automations.
        
        Provides stable attributes for zone iteration:
        - zone_ids: List of all zone IDs
        - zone_names: Mapping of zone_id to display name
        - zones_with_adaptive: Zones with adaptive enabled
        - zone_count: Total number of zones
        
        Note: zones_with_active_modifiers moved to separate sensor
        to prevent excessive updates.
        """
        zone_ids = [z["zone_id"] for z in self._zones.values()]
        zone_names = {z["zone_id"]: z["zone_name"] for z in self._zones.values()}
        zones_with_adaptive = [
            z["zone_id"] for z in self._zones.values() 
            if z.get("adaptive_enabled", False)
        ]
        
        # Count zones with active modifiers (but don't list them to reduce updates)
        zones_with_modifiers_count = 0
        for entry_id, coordinator in self._coordinators.items():
            if hasattr(coordinator, "layers"):
                for layer_id, layer_data in coordinator.layers.items():
                    if (layer_data.get(ATTR_LAYER_TYPE) in [LAYER_TYPE_MODIFIER, LAYER_TYPE_MULTIPLIER] 
                        and layer_data.get("is_on", False)):
                        zones_with_modifiers_count += 1
                        break  # Only count zone once
        
        return {
            "zone_ids": zone_ids,
            "zone_names": zone_names,
            "zones_with_adaptive": zones_with_adaptive,
            "zone_count": len(self._zones),
            "zones_with_modifiers_count": zones_with_modifiers_count,
        }
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True  # Always available
    
    async def async_will_remove_from_hass(self) -> None:
        """Clean up when sensor is being removed."""
        # Clear references
        self._zones.clear()
        self._coordinators.clear()
        if "zones_sensor" in self.hass.data.get(DOMAIN, {}):
            del self.hass.data[DOMAIN]["zones_sensor"]
        await super().async_will_remove_from_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform.
    
    Creates sensors per zone:
    1. Active Layer - What's controlling the lights
    2. Zone Status - Is everything working correctly
    3. Adaptive Factor - Sun-based lighting factor (if enabled)
    
    Also creates global sensors (once):
    1. Zones List - All zones for automation iteration
    
    This replaces the original 7-sensor approach which would have
    created 140 sensors for 20 zones, causing UI chaos and database issues.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    zone_name = entry.data["zone_name"]
    zone_id = entry.data["zone_id"]
    
    _LOGGER.info("Setting up observability sensors for zone %s", zone_name)
    
    # Create global zones sensor (only once, with lock for thread safety)
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize lock if not present
    if "zones_sensor_lock" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["zones_sensor_lock"] = asyncio.Lock()
    
    # Create global sensor with lock to prevent race conditions
    lock = hass.data[DOMAIN]["zones_sensor_lock"]
    async with lock:
        if "zones_sensor" not in hass.data[DOMAIN]:
            _LOGGER.info("Creating global zones sensor")
            zones_sensor = GlobalZonesSensor(hass)
            hass.data[DOMAIN]["zones_sensor"] = zones_sensor
            async_add_entities([zones_sensor])
    
    # Register this zone with the global sensor
    if "zones_sensor" in hass.data[DOMAIN]:
        zones_sensor = hass.data[DOMAIN]["zones_sensor"]
        zones_sensor.register_zone(entry.entry_id, zone_id, zone_name, coordinator)
    
    sensors = [
        ActiveLayerSensor(
            coordinator,
            SensorEntityDescription(
                key="active_layer",
                name="Active Layer",
                translation_key="active_layer",
            ),
        ),
        ZoneStatusSensor(
            coordinator,
            SensorEntityDescription(
                key="status",
                name="Status",
                translation_key="status",
            ),
        ),
    ]
    
    # Add adaptive sensor if enabled
    if entry.options.get("adaptive_enabled", False):
        from .adaptive_sensor import AdaptiveLightFactorSensor
        zone_id = entry.data["zone_id"]
        sensors.append(
            AdaptiveLightFactorSensor(zone_id, zone_name, entry)
        )
    
    async_add_entities(sensors)
    
    _LOGGER.debug(
        "Created 2 observability sensors for zone %s (not 7!)",
        zone_name
    )