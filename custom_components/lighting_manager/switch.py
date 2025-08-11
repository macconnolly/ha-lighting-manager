"""Switch platform for Lighting Manager - Golden Path stateless implementation.

CRITICAL: Switches are STATELESS VIEWS of coordinator data.
They store NOTHING locally and read everything from coordinator.data.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_FACTOR,
    ATTR_BRIGHTNESS_PCT_DELTA,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_FACTOR,
    ATTR_COLOR_TEMP_KELVIN_DELTA,
    ATTR_CONDITIONS,
    ATTR_CREATED_AT,
    ATTR_EXPIRES_AT,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAST_MODIFIED,
    ATTR_LAYER_NAME,
    ATTR_LAYER_TYPE,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    DATA_ADD_ENTITIES,
    DATA_COORDINATOR,
    DOMAIN,
    EVENT_LAYER_ACTIVATED,
    EVENT_LAYER_DEACTIVATED,
    EVENT_LAYER_REMOVED,
    LAYER_TYPE_ABSOLUTE,
    LAYER_TYPE_MODIFIER,
    LAYER_TYPE_MULTIPLIER,
    MANUFACTURER,
    MODEL,
    SW_VERSION,
)
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lighting Manager switch platform."""
    # Get the coordinator for this zone
    coordinator: ZoneCoordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    zone_id = config_entry.data["zone_id"]
    zone_name = config_entry.data["zone_name"]
    
    # Store add_entities callback for dynamic layer creation via services
    hass.data[DOMAIN][config_entry.entry_id][DATA_ADD_ENTITIES] = async_add_entities
    
    # Create switch entities for any existing layers in coordinator
    switches = []
    for layer_id in coordinator.layers:
        layer_data = coordinator.layers[layer_id]
        switch = LayerSwitch(
            coordinator=coordinator,
            layer_id=layer_id,
            layer_name=layer_data.get(ATTR_LAYER_NAME, layer_id),
        )
        switches.append(switch)
    
    if switches:
        async_add_entities(switches)
        _LOGGER.info("Created %d layer switches for zone %s", len(switches), zone_id)
    else:
        _LOGGER.info("No existing layers for zone %s - waiting for layer creation", zone_id)
    
    # Set up listener for new layers
    async def handle_new_layer(layer_id: str, layer_name: str) -> None:
        """Handle creation of new layer by adding switch entity."""
        _LOGGER.info("Creating switch for new layer %s in zone %s", layer_id, zone_id)
        switch = LayerSwitch(
            coordinator=coordinator,
            layer_id=layer_id,
            layer_name=layer_name,
        )
        async_add_entities([switch])
    
    # Store callback for coordinator to use
    coordinator.new_layer_callback = handle_new_layer


class LayerSwitch(CoordinatorEntity[ZoneCoordinator], SwitchEntity):
    """Representation of a lighting layer as a switch.
    
    GOLDEN PATH: This is a STATELESS view of coordinator data.
    - ALL state is read from coordinator.data["layers"][layer_id]
    - ALL changes go through coordinator.update_layer()
    - This entity stores NOTHING locally (no _is_on, _priority, etc.)
    """

    _attr_has_entity_name = True
    # Don't use entity_category so switches appear in main UI

    def __init__(
        self,
        coordinator: ZoneCoordinator,
        layer_id: str,
        layer_name: str,
    ) -> None:
        """Initialize the layer switch as a stateless view.
        
        Store ONLY the minimum needed to identify which layer we represent.
        """
        super().__init__(coordinator)
        
        # Store only IDs - everything else comes from coordinator.data
        self.layer_id = layer_id
        self.layer_name = layer_name  # For display only
        
        # Set unique ID for entity registry
        self._attr_unique_id = f"{slugify(coordinator.zone_id)}_{slugify(layer_id)}_layer"
        
        _LOGGER.debug("Initialized layer switch %s for zone %s", 
                     layer_id, coordinator.zone_id)

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self.layer_name} Layer"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping under zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.zone_id)},
            name=self.coordinator.zone_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=SW_VERSION,
        )

    @property
    def is_on(self) -> bool:
        """Read ONLY from coordinator.data.
        
        GOLDEN PATH: This is the critical property - must read from
        coordinator.data, never store state locally.
        """
        layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
        return layer_data.get(ATTR_IS_ON, False)

    @property
    def available(self) -> bool:
        """Available when coordinator has our layer."""
        return self.layer_id in self.coordinator.data.get("layers", {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose ALL layer state as attributes.
        
        GOLDEN PATH: All attributes come from coordinator.data.
        """
        layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
        
        # Return all layer attributes for complete observability
        attrs = {
            "zone_id": self.coordinator.zone_id,
            "layer_id": self.layer_id,
        }
        
        # Define all possible attributes to expose
        # This makes it easy to add/remove attributes in the future
        attribute_keys = [
            ATTR_LAYER_NAME,
            ATTR_PRIORITY,
            ATTR_LAYER_TYPE,  # Add layer type (absolute/modifier)
            # Absolute layer attributes
            ATTR_BRIGHTNESS,
            ATTR_COLOR_TEMP,
            ATTR_RGB_COLOR,
            # Modifier layer attributes
            ATTR_BRIGHTNESS_PCT_DELTA,
            ATTR_COLOR_TEMP_KELVIN_DELTA,
            ATTR_BRIGHTNESS_FACTOR,
            ATTR_COLOR_TEMP_FACTOR,
            # Common attributes
            ATTR_TRANSITION,
            ATTR_FORCE,
            ATTR_LOCKED,
            ATTR_CONDITIONS,
            ATTR_SOURCE,
            ATTR_CREATED_AT,
            ATTR_LAST_MODIFIED,
            ATTR_EXPIRES_AT,  # Add expiration timestamp
        ]
        
        for key in attribute_keys:
            if key in layer_data:
                value = layer_data[key]
                # Convert datetime objects to ISO format for HA frontend
                if key in [ATTR_CREATED_AT, ATTR_LAST_MODIFIED, ATTR_EXPIRES_AT]:
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                attrs[key] = value
        
        # Add any extra non-standard attributes from the layer
        # (excluding is_on which is represented by the switch state)
        for key, value in layer_data.items():
            if key not in attrs and key != ATTR_IS_ON and key not in attribute_keys:
                # Handle datetime conversion for any additional datetime fields
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                attrs[key] = value
        
        # Add computed attributes for better UX
        if ATTR_EXPIRES_AT in attrs:
            # Add a human-readable time remaining
            # (HA frontend will handle relative time display automatically)
            pass  # Let HA handle the display format
        
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the layer - calls coordinator only.
        
        GOLDEN PATH: Only calls coordinator.update_layer(), 
        never modifies local state.
        """
        # Check if layer is locked
        layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot activate locked layer %s", self.entity_id)
            return
        
        # Build update dict
        updates = {ATTR_IS_ON: True}
        
        # Add any provided attributes
        if ATTR_BRIGHTNESS in kwargs:
            updates[ATTR_BRIGHTNESS] = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP in kwargs:
            updates[ATTR_COLOR_TEMP] = kwargs[ATTR_COLOR_TEMP]
        if ATTR_RGB_COLOR in kwargs:
            updates[ATTR_RGB_COLOR] = kwargs[ATTR_RGB_COLOR]
        if ATTR_TRANSITION in kwargs:
            updates[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]
        
        # Call layer_manager to update
        if self.coordinator.layer_manager.update_layer(self.layer_id, updates):
            # Save if needed
            if self.coordinator.layer_manager.has_pending_save():
                await self.coordinator.layer_manager.save()
            
            # Trigger coordinator update
            self.coordinator.schedule_recalculation()
            
            # Fire event
            self.hass.bus.async_fire(
                EVENT_LAYER_ACTIVATED,
                {
                    "zone_id": self.coordinator.zone_id,
                    "layer_id": self.layer_id,
                    "entity_id": self.entity_id,
                },
            )
            _LOGGER.debug("Activated layer %s", self.entity_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the layer - calls coordinator only.
        
        GOLDEN PATH: Only calls coordinator.update_layer(), 
        never modifies local state.
        """
        # Check if layer is locked
        layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot deactivate locked layer %s", self.entity_id)
            return
        
        # Call layer_manager to update
        if self.coordinator.layer_manager.update_layer(self.layer_id, {ATTR_IS_ON: False}):
            # Save if needed
            if self.coordinator.layer_manager.has_pending_save():
                await self.coordinator.layer_manager.save()
            
            # Trigger coordinator update
            self.coordinator.schedule_recalculation()
            
            # Fire event
            self.hass.bus.async_fire(
                EVENT_LAYER_DEACTIVATED,
                {
                    "zone_id": self.coordinator.zone_id,
                    "layer_id": self.layer_id,
                    "entity_id": self.entity_id,
                },
            )
            _LOGGER.debug("Deactivated layer %s", self.entity_id)

    @property
    def icon(self) -> str | None:
        """Return icon based on layer state and type.
        
        Visual indicators:
        - Absolute layers: mdi:layers
        - Modifier layers: mdi:layers-plus
        - Multiplier layers: mdi:layers-triple
        - Locked state: Adds lock overlay
        - Off state: Uses outline version
        """
        layer_data = self.coordinator.data.get("layers", {}).get(self.layer_id, {})
        layer_type = layer_data.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE)
        is_locked = layer_data.get(ATTR_LOCKED, False)
        is_forced = layer_data.get(ATTR_FORCE, False)
        
        # Determine base icon based on layer type
        if layer_type == LAYER_TYPE_MODIFIER:
            base_icon = "layers-plus"
        elif layer_type == LAYER_TYPE_MULTIPLIER:
            base_icon = "layers-triple"
        else:  # LAYER_TYPE_ABSOLUTE or unknown
            base_icon = "layers"
        
        # Build the full icon name
        if self.is_on:
            if is_forced:
                # Force flag gets special attention
                return f"mdi:{base_icon}"
            elif is_locked:
                # Locked layers show lock
                return f"mdi:lock"
            else:
                # Normal on state
                return f"mdi:{base_icon}"
        else:
            # Off state uses outline version
            if layer_type == LAYER_TYPE_MODIFIER:
                return "mdi:layers-outline"
            elif layer_type == LAYER_TYPE_MULTIPLIER:
                return "mdi:layers-triple-outline"
            else:
                return "mdi:layers-off-outline"

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is being removed."""
        # Fire event
        self.hass.bus.async_fire(
            EVENT_LAYER_REMOVED,
            {
                "zone_id": self.coordinator.zone_id,
                "layer_id": self.layer_id,
                "entity_id": self.entity_id,
            },
        )
        await super().async_will_remove_from_hass()