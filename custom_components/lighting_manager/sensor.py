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

from .const import DOMAIN, DATA_COORDINATOR, CONF_ADAPTIVE_ENABLED
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
            "sw_version": "2.0.0",
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
        """Return sanitized diagnostic attributes.
        
        CRITICAL: Summarize data, don't dump raw dictionaries.
        No user input, no secrets, no large objects.
        """
        if not self.coordinator.data:
            return {}
        
        attrs = {}
        
        # List active layers (names only, not full data)
        active_layers = self.coordinator.data.get("active_layers", [])
        if active_layers:
            attrs["active_layers"] = [
                self.coordinator.layers.get(lid, {}).get("layer_name", lid)
                for lid in active_layers
            ]
            attrs["active_layer_count"] = len(active_layers)
        
        # Add conflict info if present
        conflicts = self.coordinator.data.get("conflicts", [])
        if conflicts:
            # A conflict item is a dictionary, e.g. {'type': 'priority_tie', 'layers': ['id1', 'id2']}
            # We need to extract the list of layer IDs from it.
            # Assuming one conflict for simplicity, but can be extended for multiple.
            conflict_item = conflicts[0]
            conflicting_lids = conflict_item.get("layers", [])

            attrs["conflicting_layers"] = [
                self.coordinator.layers.get(lid, {}).get("layer_name", lid)
                for lid in conflicting_lids
            ]
            attrs["conflict_priority"] = conflict_item.get("priority", 0)
        
        # Add timing info (for performance monitoring)
        if "last_calculation" in self.coordinator.data:
            attrs["last_calculation"] = self.coordinator.data["last_calculation"]
        if "calculation_time_ms" in self.coordinator.data:
            attrs["calculation_time_ms"] = round(
                self.coordinator.data["calculation_time_ms"], 2
            )
        
        # Add cache info (for optimization monitoring)
        if "cache_hit" in self.coordinator.data:
            attrs["cache_hit"] = self.coordinator.data["cache_hit"]
        
        # Add trigger source (what caused last calculation)
        if "trigger" in self.coordinator.data:
            trigger = self.coordinator.data["trigger"]
            # Sanitize trigger - only include type, not full path
            if isinstance(trigger, str):
                attrs["trigger"] = trigger.split(".")[-1] if "." in trigger else trigger
        
        # Add unavailable lights if any
        unavailable = self.coordinator.data.get("lights_unavailable", [])
        if unavailable:
            attrs["lights_unavailable_count"] = len(unavailable)
            # Only include first 3 light names to prevent attribute bloat
            attrs["lights_unavailable_sample"] = unavailable[:3]
        
        # Add error message if in error state
        if self.coordinator.data.get("error"):
            error = str(self.coordinator.data["error"])
            # Truncate error message to prevent attribute bloat
            attrs["error_message"] = error[:200] if len(error) > 200 else error
        
        # Add winning reason with more detail
        winning_layer = self.coordinator.data.get("winning_layer")
        if winning_layer and winning_layer in self.coordinator.layers:
            layer = self.coordinator.layers[winning_layer]
            layer_name = layer.get("layer_name", winning_layer)
            priority = layer.get("priority", 0)
            
            # Explain why this layer won
            if conflicts:
                attrs["winning_reason"] = f"{layer_name} wins tie at priority {priority}"
            elif len(active_layers) > 1:
                # Find second highest priority
                other_priorities = [
                    self.coordinator.layers.get(lid, {}).get("priority", 0)
                    for lid in active_layers
                    if lid != winning_layer
                ]
                if other_priorities:
                    next_priority = max(other_priorities)
                    attrs["winning_reason"] = f"{layer_name} (priority {priority}) beats next highest ({next_priority})"
                else:
                    attrs["winning_reason"] = f"{layer_name} wins with priority {priority}"
            else:
                attrs["winning_reason"] = f"Only {layer_name} is active"
        
        # Add zone configuration summary
        attrs["total_layers"] = len(self.coordinator.layers)
        attrs["total_lights"] = len(self.coordinator.light_entities)
        
        return attrs


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
    
    This replaces the original 7-sensor approach which would have
    created 140 sensors for 20 zones, causing UI chaos and database issues.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    zone_name = entry.data["zone_name"]
    
    _LOGGER.info("Setting up observability sensors for zone %s", zone_name)
    
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