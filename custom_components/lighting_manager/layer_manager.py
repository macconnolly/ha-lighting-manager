"""Layer Manager - Handles CRUD operations and persistence for layers."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CREATED_AT,
    ATTR_IS_ON,
    ATTR_LAST_MODIFIED,
    ATTR_LAYER_NAME,
    ATTR_SOURCE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class LayerManager:
    """Manages layer CRUD operations and persistence."""
    
    def __init__(self, hass: HomeAssistant, zone_id: str) -> None:
        """Initialize layer manager.
        
        Args:
            hass: Home Assistant instance
            zone_id: Unique identifier for the zone
        """
        self.hass = hass
        self.zone_id = zone_id
        self.layers: Dict[str, Dict[str, Any]] = {}
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{zone_id}",
        )
        self._listeners: List[Callable[[], None]] = []
        self._save_pending = False
        _LOGGER.info("LayerManager initialized for zone %s", zone_id)
    
    async def load(self) -> None:
        """Load layers from storage.
        
        Filters out temporary layers (source == 'manual_override').
        Falls back to empty dict on error.
        """
        try:
            _LOGGER.debug("Loading layers for zone %s", self.zone_id)
            stored = await self._store.async_load()
            
            if stored and isinstance(stored, dict):
                # Only load configuration layers, not temporary ones
                self.layers = {
                    lid: layer 
                    for lid, layer in stored.get("layers", {}).items()
                    if layer.get(ATTR_SOURCE) != "manual_override"
                }
                _LOGGER.info(
                    "Loaded %d configuration layers for zone %s",
                    len(self.layers), self.zone_id
                )
            else:
                self.layers = {}
                _LOGGER.info("No stored layers found for zone %s", self.zone_id)
                
        except Exception as err:
            _LOGGER.error(
                "Failed to load layers for zone %s: %s",
                self.zone_id, err, exc_info=True
            )
            self.layers = {}
    
    async def save(self) -> None:
        """Save configuration layers to storage.
        
        Only saves layers where source != 'manual_override'.
        """
        try:
            # Filter to configuration layers only
            config_layers = {
                lid: layer 
                for lid, layer in self.layers.items()
                if layer.get(ATTR_SOURCE) != "manual_override"
            }
            
            save_data = {
                "version": STORAGE_VERSION,
                "layers": config_layers,
                "zone_id": self.zone_id,
                "saved_at": dt_util.now().isoformat(),
            }
            
            await self._store.async_save(save_data)
            self._save_pending = False
            _LOGGER.debug(
                "Saved %d configuration layers for zone %s",
                len(config_layers), self.zone_id
            )
            
        except Exception as err:
            _LOGGER.error(
                "Failed to save layers for zone %s: %s",
                self.zone_id, err, exc_info=True
            )
    
    def set_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> tuple[bool, str]:
        """Set (create or update) a layer - idempotent operation.
        
        This is THE SINGLE ENTRY POINT for all layer modifications.
        
        Args:
            layer_id: Unique identifier for the layer
            layer_data: Complete layer attributes
            
        Returns:
            Tuple of (success, action) where action is 'created' or 'updated'
        """
        if layer_id in self.layers:
            # Update existing layer
            success = self._update_layer(layer_id, layer_data)
            return (success, "updated" if success else "failed")
        else:
            # Create new layer
            self._create_layer(layer_id, layer_data)
            return (True, "created")
    
    def _create_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> None:
        """Internal method to create a new layer.
        
        Args:
            layer_id: Unique identifier for the layer
            layer_data: Layer attributes
        """
        # Add timestamps
        now = dt_util.now()
        layer_data[ATTR_CREATED_AT] = now.isoformat()
        layer_data[ATTR_LAST_MODIFIED] = now.isoformat()
        
        # Store layer
        self.layers[layer_id] = layer_data
        self._save_pending = True
        
        # Notify listeners
        self._notify_listeners()
        
        _LOGGER.info(
            "Created layer %s in zone %s with %d attributes",
            layer_id, self.zone_id, len(layer_data)
        )
    
    def create_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> None:
        """Legacy method - use set_layer instead.
        
        Kept for backward compatibility with change_detector.
        """
        if layer_id in self.layers:
            _LOGGER.warning(
                "Layer %s already exists in zone %s, skipping creation",
                layer_id, self.zone_id
            )
            return
        self._create_layer(layer_id, layer_data)
    
    def _update_layer(self, layer_id: str, updates: Dict[str, Any]) -> bool:
        """Internal method to update an existing layer.
        
        Args:
            layer_id: Layer to update
            updates: Attributes to update
            
        Returns:
            True if updated, False if layer not found
        """
        if layer_id not in self.layers:
            _LOGGER.warning(
                "Cannot update non-existent layer %s in zone %s",
                layer_id, self.zone_id
            )
            return False
        
        # Update timestamp
        updates[ATTR_LAST_MODIFIED] = dt_util.now().isoformat()
        
        # Apply updates
        self.layers[layer_id].update(updates)
        self._save_pending = True
        
        # Notify listeners
        self._notify_listeners()
        
        _LOGGER.debug(
            "Updated layer %s in zone %s with %d changes",
            layer_id, self.zone_id, len(updates)
        )
        return True
    
    def update_layer(self, layer_id: str, updates: Dict[str, Any]) -> bool:
        """Legacy method - use set_layer instead.
        
        Kept for backward compatibility.
        """
        return self._update_layer(layer_id, updates)
    
    def delete_layer(self, layer_id: str) -> bool:
        """Delete a layer.
        
        Args:
            layer_id: Layer to delete
            
        Returns:
            True if deleted, False if not found
        """
        if layer_id not in self.layers:
            _LOGGER.warning(
                "Cannot delete non-existent layer %s from zone %s",
                layer_id, self.zone_id
            )
            return False
        
        # Delete layer
        del self.layers[layer_id]
        self._save_pending = True
        
        # Notify listeners
        self._notify_listeners()
        
        _LOGGER.info("Deleted layer %s from zone %s", layer_id, self.zone_id)
        return True
    
    def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Get a layer by ID.
        
        Args:
            layer_id: Layer to retrieve
            
        Returns:
            Layer data or None if not found
        """
        return self.layers.get(layer_id)
    
    def get_active_layers(self) -> List[Dict[str, Any]]:
        """Get all active layers.
        
        Returns:
            List of layers where is_on=True, with layer_id included
        """
        return [
            {**layer, "layer_id": lid}
            for lid, layer in self.layers.items()
            if layer.get(ATTR_IS_ON, False)
        ]
    
    def get_all_layers(self) -> Dict[str, Dict[str, Any]]:
        """Get all layers.
        
        Returns:
            Dictionary of all layers
        """
        return self.layers.copy()
    
    def add_listener(self, listener: Callable[[], None]) -> None:
        """Add a change listener.
        
        Args:
            listener: Callback to invoke on changes
        """
        self._listeners.append(listener)
        _LOGGER.debug("Added listener, total: %d", len(self._listeners))
    
    def remove_listener(self, listener: Callable[[], None]) -> None:
        """Remove a change listener.
        
        Args:
            listener: Callback to remove
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
            _LOGGER.debug("Removed listener, remaining: %d", len(self._listeners))
    
    def _notify_listeners(self) -> None:
        """Notify all listeners of changes."""
        for listener in self._listeners:
            try:
                listener()
            except Exception as err:
                _LOGGER.error("Error notifying listener: %s", err, exc_info=True)
    
    def has_pending_save(self) -> bool:
        """Check if there are unsaved changes.
        
        Returns:
            True if save is pending
        """
        return self._save_pending