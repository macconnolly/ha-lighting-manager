"""Zone coordinator for Lighting Manager - single source of truth for all layer state."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
    DATA_ADD_ENTITIES,
    DEBOUNCE_SECONDS,
    DEFAULT_PRIORITY,
    DEFAULT_TRANSITION,
    DOMAIN,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class ZoneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for a lighting zone - single source of truth for all layer state.
    
    This coordinator holds ALL layer state. Switch entities are just views that:
    1. Read their state from coordinator.data["layers"][layer_id]
    2. Call coordinator methods to request state changes
    3. Never store any state locally
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the zone coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data['zone_id']}",
            update_interval=None,  # Event-driven updates only, no polling
        )
        
        self.config_entry = entry
        self.zone_id = entry.data["zone_id"]
        self.zone_name = entry.data["zone_name"]
        
        # CRITICAL: All layer state lives here - switches are just views of this
        self.layers: dict[str, dict[str, Any]] = {}
        
        # Store for persistence
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{self.zone_id}",
        )
        
        # Debounce management
        self._debounce_timer: asyncio.TimerHandle | None = None
        self._save_timer: asyncio.TimerHandle | None = None
        
        # Last valid state for fallback
        self._last_valid_state: dict[str, Any] = {}
        
        _LOGGER.info("Coordinator initialized for zone %s", self.zone_id)

    async def async_load(self) -> None:
        """Load stored layer data from disk."""
        try:
            stored = await self._store.async_load()
            if stored and "layers" in stored:
                self.layers = stored["layers"]
                _LOGGER.info("Loaded %d layers for zone %s", len(self.layers), self.zone_id)
            else:
                self.layers = {}
                _LOGGER.info("No stored layers for zone %s, starting fresh", self.zone_id)
        except Exception as err:
            _LOGGER.error("Failed to load layers for zone %s: %s", self.zone_id, err)
            self.layers = {}
    
    @callback
    def async_schedule_save(self) -> None:
        """Schedule a save to disk with debouncing."""
        if self._save_timer:
            self._save_timer.cancel()
        
        self._save_timer = self.hass.loop.call_later(
            1.0,  # Save after 1 second of no changes
            lambda: self.hass.async_create_task(self._async_save())
        )
    
    async def _async_save(self) -> None:
        """Save layer data to disk."""
        try:
            await self._store.async_save({"layers": self.layers})
            _LOGGER.debug("Saved %d layers for zone %s", len(self.layers), self.zone_id)
        except Exception as err:
            _LOGGER.error("Failed to save layers for zone %s: %s", self.zone_id, err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Calculate the current state for this zone.
        
        This is called after debouncing to recalculate which layer wins
        and what the final light state should be.
        """
        try:
            # Get active layers (those that are "on")
            active_layers = [
                {**layer, "layer_id": lid}
                for lid, layer in self.layers.items()
                if layer.get(ATTR_IS_ON, False)
            ]
            
            # Sort by priority for simple winner selection (Phase 2 will use calculator)
            if active_layers:
                active_layers.sort(key=lambda x: x.get(ATTR_PRIORITY, 0), reverse=True)
                winning_layer = active_layers[0]["layer_id"]
            else:
                winning_layer = None
            
            # Build result structure
            result = {
                "layers": self.layers,  # ALL layer states for switches to read
                "active_layers": active_layers,
                "winning_layer": winning_layer,
                "final_state": {},  # Phase 2 will calculate this
                "conflicts": [],
                "calculation_path": [l["layer_id"] for l in active_layers],
                "calculation_time_ms": 0,
            }
            
            # Store as last valid state
            self._last_valid_state = result
            return result
            
        except Exception as err:
            _LOGGER.error("Calculation failed for zone %s: %s", self.zone_id, err)
            if self._last_valid_state:
                return self._last_valid_state
            raise UpdateFailed(f"Calculation failed: {err}") from err
    
    @callback
    def create_layer(self, layer_name: str, priority: int = DEFAULT_PRIORITY, **attributes) -> str:
        """Create a new layer and return its ID.
        
        This is called by services to dynamically create layers.
        """
        layer_id = slugify(layer_name)
        
        if layer_id in self.layers:
            _LOGGER.warning("Layer %s already exists in zone %s", layer_id, self.zone_id)
            return layer_id
        
        # Create the layer with all attributes
        self.layers[layer_id] = {
            ATTR_LAYER_NAME: layer_name,
            ATTR_IS_ON: False,
            ATTR_PRIORITY: priority,
            ATTR_BRIGHTNESS: attributes.get(ATTR_BRIGHTNESS),
            ATTR_COLOR_TEMP: attributes.get(ATTR_COLOR_TEMP),
            ATTR_RGB_COLOR: attributes.get(ATTR_RGB_COLOR),
            ATTR_TRANSITION: attributes.get(ATTR_TRANSITION, DEFAULT_TRANSITION),
            ATTR_FORCE: attributes.get(ATTR_FORCE, False),
            ATTR_LOCKED: attributes.get(ATTR_LOCKED, False),
            ATTR_CONDITIONS: attributes.get(ATTR_CONDITIONS, {}),
            ATTR_SOURCE: attributes.get(ATTR_SOURCE, "manual"),
            ATTR_LAST_UPDATED: datetime.now().isoformat(),
        }
        
        # Add any extra attributes not in the standard set
        for key, value in attributes.items():
            if key not in self.layers[layer_id]:
                self.layers[layer_id][key] = value
        
        # Schedule save and refresh
        self.async_schedule_save()
        self.async_schedule_refresh()
        
        _LOGGER.info("Created layer %s in zone %s with priority %d", 
                     layer_id, self.zone_id, priority)
        return layer_id
    
    @callback
    def update_layer(self, layer_id: str, **updates) -> bool:
        """Update layer attributes.
        
        This is the ONLY way switches should modify state.
        Returns True if successful, False if layer not found or locked.
        """
        if layer_id not in self.layers:
            _LOGGER.error("Layer %s not found in zone %s", layer_id, self.zone_id)
            return False
        
        # Check if layer is locked (unless force update)
        if self.layers[layer_id].get(ATTR_LOCKED, False) and not updates.get("_force_update"):
            _LOGGER.warning("Cannot update locked layer %s", layer_id)
            return False
        
        # Remove internal flags
        updates.pop("_force_update", None)
        
        # Update the layer
        self.layers[layer_id].update(updates)
        self.layers[layer_id][ATTR_LAST_UPDATED] = datetime.now().isoformat()
        
        # Schedule save and refresh
        self.async_schedule_save()
        self.async_schedule_refresh()
        
        _LOGGER.debug("Updated layer %s in zone %s: %s", layer_id, self.zone_id, updates)
        return True
    
    @callback
    def delete_layer(self, layer_id: str) -> bool:
        """Remove a layer.
        
        Returns True if successful, False if layer not found.
        """
        if layer_id not in self.layers:
            _LOGGER.warning("Cannot delete non-existent layer %s", layer_id)
            return False
        
        del self.layers[layer_id]
        
        # Schedule save and refresh
        self.async_schedule_save()
        self.async_schedule_refresh()
        
        _LOGGER.info("Deleted layer %s from zone %s", layer_id, self.zone_id)
        return True
    
    def get_layer(self, layer_id: str) -> dict[str, Any] | None:
        """Get layer data by ID."""
        return self.layers.get(layer_id)
    
    @callback
    def async_schedule_refresh(self) -> None:
        """Schedule a refresh with debouncing.
        
        This implements the 100ms debounce window to batch rapid changes.
        """
        if self._debounce_timer:
            self._debounce_timer.cancel()
        
        self._debounce_timer = self.hass.loop.call_later(
            DEBOUNCE_SECONDS,  # 100ms debounce
            lambda: self.hass.async_create_task(self.async_request_refresh())
        )
    
    async def async_will_remove_from_hass(self) -> None:
        """Clean up when coordinator is removed."""
        # Cancel timers
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._save_timer:
            self._save_timer.cancel()
        
        # Final save
        await self._async_save()