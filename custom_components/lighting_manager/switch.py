"""Switch platform for Lighting Manager layers - stateless views of coordinator data."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_CONDITIONS,
    ATTR_FORCE,
    ATTR_IS_ON,
    ATTR_LAST_UPDATED,
    ATTR_LAYER_NAME,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    ATTR_ZONE_ID,
    DATA_ADD_ENTITIES,
    DATA_COORDINATOR,
    DOMAIN,
    EVENT_LAYER_ACTIVATED,
    EVENT_LAYER_DEACTIVATED,
    EVENT_LAYER_REMOVED,
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
        switch = LayerSwitch(
            coordinator=coordinator,
            zone_id=zone_id,
            zone_name=zone_name,
            layer_id=layer_id,
        )
        switches.append(switch)
    
    if switches:
        async_add_entities(switches)
        _LOGGER.info("Created %d layer switches for zone %s", len(switches), zone_id)
    else:
        _LOGGER.info("No existing layers for zone %s", zone_id)


class LayerSwitch(CoordinatorEntity[ZoneCoordinator], SwitchEntity):
    """Representation of a lighting layer as a switch.
    
    CRITICAL: This is a STATELESS view of coordinator data.
    - ALL state is read from coordinator.data["layers"][layer_id]
    - ALL changes go through coordinator.update_layer()
    - This entity stores NOTHING locally
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: ZoneCoordinator,
        zone_id: str,
        zone_name: str,
        layer_id: str,
    ) -> None:
        """Initialize the layer switch as a view of coordinator data."""
        super().__init__(coordinator)
        
        # Store only the IDs needed to look up data from coordinator
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._layer_id = layer_id
        
        # Entity setup
        self._attr_unique_id = f"{zone_id}_{layer_id}_layer"
        
        _LOGGER.debug("Initialized layer switch %s for zone %s", layer_id, zone_id)

    @property
    def entity_id(self) -> str:
        """Return the entity ID."""
        # Use slugified IDs for entity_id
        return f"switch.{slugify(self._zone_id)}_{slugify(self._layer_id)}_layer"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        # Get display name from coordinator data
        layer_data = self._get_layer_data()
        layer_name = layer_data.get(ATTR_LAYER_NAME, self._layer_id)
        return f"{layer_name} Layer"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping under zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._zone_id)},
            name=self._zone_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=SW_VERSION,
        )

    @property
    def is_on(self) -> bool:
        """Return true if layer is active.
        
        CRITICAL: Read from coordinator data, not local state!
        """
        layer_data = self._get_layer_data()
        return layer_data.get(ATTR_IS_ON, False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if coordinator has data and our layer exists
        if not self.coordinator.data:
            return False
        layers = self.coordinator.data.get("layers", {})
        return self._layer_id in layers

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all layer configuration as attributes.
        
        CRITICAL: All attributes come from coordinator data!
        """
        layer_data = self._get_layer_data()
        
        # Return all layer attributes for full observability
        return {
            ATTR_ZONE_ID: self._zone_id,
            ATTR_LAYER_NAME: layer_data.get(ATTR_LAYER_NAME, self._layer_id),
            ATTR_PRIORITY: layer_data.get(ATTR_PRIORITY),
            ATTR_BRIGHTNESS: layer_data.get(ATTR_BRIGHTNESS),
            ATTR_COLOR_TEMP: layer_data.get(ATTR_COLOR_TEMP),
            ATTR_RGB_COLOR: layer_data.get(ATTR_RGB_COLOR),
            ATTR_TRANSITION: layer_data.get(ATTR_TRANSITION),
            ATTR_FORCE: layer_data.get(ATTR_FORCE),
            ATTR_LOCKED: layer_data.get(ATTR_LOCKED),
            ATTR_CONDITIONS: layer_data.get(ATTR_CONDITIONS),
            ATTR_SOURCE: layer_data.get(ATTR_SOURCE),
            ATTR_LAST_UPDATED: layer_data.get(ATTR_LAST_UPDATED),
            # Include any extra attributes from the layer
            **{k: v for k, v in layer_data.items() 
               if k not in [ATTR_IS_ON, ATTR_LAYER_NAME, ATTR_PRIORITY, 
                           ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR,
                           ATTR_TRANSITION, ATTR_FORCE, ATTR_LOCKED,
                           ATTR_CONDITIONS, ATTR_SOURCE, ATTR_LAST_UPDATED]},
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the layer (activate it).
        
        CRITICAL: Only calls coordinator.update_layer(), never modifies local state!
        """
        # Check if layer is locked
        layer_data = self._get_layer_data()
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot activate locked layer %s", self.entity_id)
            return
        
        # Build update dict with is_on=True and any provided attributes
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
        if ATTR_SOURCE in kwargs:
            updates[ATTR_SOURCE] = kwargs[ATTR_SOURCE]
        
        # Call coordinator to update layer state
        if self.coordinator.update_layer(self._layer_id, **updates):
            # Fire event for layer activation
            self.hass.bus.async_fire(
                EVENT_LAYER_ACTIVATED,
                {
                    "zone_id": self._zone_id,
                    "layer_id": self._layer_id,
                    "entity_id": self.entity_id,
                },
            )
            _LOGGER.debug("Activated layer %s", self.entity_id)
        else:
            _LOGGER.error("Failed to activate layer %s", self.entity_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the layer (deactivate it).
        
        CRITICAL: Only calls coordinator.update_layer(), never modifies local state!
        """
        # Check if layer is locked
        layer_data = self._get_layer_data()
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot deactivate locked layer %s", self.entity_id)
            return
        
        # Call coordinator to update layer state
        if self.coordinator.update_layer(self._layer_id, **{ATTR_IS_ON: False}):
            # Fire event for layer deactivation
            self.hass.bus.async_fire(
                EVENT_LAYER_DEACTIVATED,
                {
                    "zone_id": self._zone_id,
                    "layer_id": self._layer_id,
                    "entity_id": self.entity_id,
                },
            )
            _LOGGER.debug("Deactivated layer %s", self.entity_id)
        else:
            _LOGGER.error("Failed to deactivate layer %s", self.entity_id)

    async def async_update_priority(self, priority: int) -> None:
        """Update the layer priority.
        
        Service method to change priority.
        """
        layer_data = self._get_layer_data()
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot update locked layer %s", self.entity_id)
            return
        
        self.coordinator.update_layer(self._layer_id, **{ATTR_PRIORITY: priority})

    async def async_lock(self) -> None:
        """Lock the layer to prevent modifications."""
        self.coordinator.update_layer(self._layer_id, **{ATTR_LOCKED: True, "_force_update": True})

    async def async_unlock(self) -> None:
        """Unlock the layer to allow modifications."""
        self.coordinator.update_layer(self._layer_id, **{ATTR_LOCKED: False, "_force_update": True})

    async def async_force(self, force: bool = True) -> None:
        """Set or unset the force flag."""
        layer_data = self._get_layer_data()
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot force locked layer %s", self.entity_id)
            return
        
        self.coordinator.update_layer(self._layer_id, **{ATTR_FORCE: force})

    async def async_update_attributes(self, **kwargs: Any) -> None:
        """Update layer attributes without changing active state.
        
        Service method for updating layer configuration.
        """
        layer_data = self._get_layer_data()
        if layer_data.get(ATTR_LOCKED, False):
            _LOGGER.warning("Cannot update locked layer %s", self.entity_id)
            return
        
        # Don't allow changing is_on through this method
        kwargs.pop(ATTR_IS_ON, None)
        
        if kwargs:
            self.coordinator.update_layer(self._layer_id, **kwargs)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.
        
        This is called automatically when coordinator data changes.
        We just need to update our state in the UI.
        """
        self.async_write_ha_state()

    def _get_layer_data(self) -> dict[str, Any]:
        """Get this layer's data from the coordinator.
        
        Helper method to safely get layer data.
        """
        if not self.coordinator.data:
            return {}
        
        layers = self.coordinator.data.get("layers", {})
        return layers.get(self._layer_id, {})

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is being removed."""
        # Fire event for layer removal
        self.hass.bus.async_fire(
            EVENT_LAYER_REMOVED,
            {
                "zone_id": self._zone_id,
                "layer_id": self._layer_id,
                "entity_id": self.entity_id,
            },
        )
        
        await super().async_will_remove_from_hass()