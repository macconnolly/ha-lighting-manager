"""Layer entity platform for Lighting Manager."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import voluptuous as vol
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import (
    DEFAULT_LAYERS,
    DOMAIN,
    DATA_LAYERS,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_DEACTIVATE_LAYER,
    SERVICE_UPDATE_LAYER,
)

ACTIVATE_LAYER_SCHEMA = vol.Schema(
    {
        vol.Optional("brightness"): vol.Coerce(int),
        vol.Optional("color_temp"): vol.Coerce(int),
        vol.Optional("rgb_color"): vol.Any(list, tuple),
        vol.Optional("transition"): vol.Coerce(float),
        vol.Optional("force", default=False): vol.Coerce(bool),
        vol.Optional("locked", default=False): vol.Coerce(bool),
        vol.Optional("conditions", default={}): dict,
        vol.Optional("source"): vol.Coerce(str),
    }
)

UPDATE_LAYER_SCHEMA = ACTIVATE_LAYER_SCHEMA


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities
) -> None:
    """Set up layer entities for a config entry."""
    zone_id = slugify(entry.title)
    entities = [
        LayerEntity(zone_id, layer_id, priority)
        for layer_id, priority in DEFAULT_LAYERS.items()
    ]
    async_add_entities(entities)

    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_LAYERS, {})[
        zone_id
    ] = [entity.entity_id for entity in entities]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_ACTIVATE_LAYER, ACTIVATE_LAYER_SCHEMA, "async_activate"
    )
    platform.async_register_entity_service(
        SERVICE_UPDATE_LAYER, UPDATE_LAYER_SCHEMA, "async_update_attributes"
    )
    platform.async_register_entity_service(
        SERVICE_DEACTIVATE_LAYER, {}, "async_deactivate"
    )


class LayerEntity(RestoreEntity):
    """Representation of a lighting layer."""

    def __init__(self, zone_id: str, layer_id: str, priority: int) -> None:
        self._zone_id = zone_id
        self._layer_id = layer_id
        self._priority = priority
        self._active = False
        self._brightness: int | None = None
        self._color_temp: int | None = None
        self._rgb_color: Any | None = None
        self._transition: float | None = None
        self._force = False
        self._locked = False
        self._conditions: Dict[str, Any] = {}
        self._last_updated: str | None = None
        self._source: str | None = None
        self.entity_id = f"layer.{zone_id}_{layer_id}"
        self._attr_name = f"{zone_id} {layer_id}"

    async def async_added_to_hass(self) -> None:
        if (last_state := await self.async_get_last_state()) is not None:
            self._active = last_state.state == STATE_ON
            attrs = last_state.attributes
            self._brightness = attrs.get("brightness")
            self._color_temp = attrs.get("color_temp")
            self._rgb_color = attrs.get("rgb_color")
            self._transition = attrs.get("transition")
            self._force = attrs.get("force", False)
            self._locked = attrs.get("locked", False)
            self._conditions = attrs.get("conditions", {})
            self._last_updated = attrs.get("last_updated")
            self._source = attrs.get("source")

    @property
    def state(self) -> str:
        return STATE_ON if self._active else STATE_OFF

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "zone_id": self._zone_id,
            "layer_id": self._layer_id,
            "priority": self._priority,
            "brightness": self._brightness,
            "color_temp": self._color_temp,
            "rgb_color": self._rgb_color,
            "transition": self._transition,
            "force": self._force,
            "locked": self._locked,
            "conditions": self._conditions,
            "last_updated": self._last_updated,
            "source": self._source,
        }

    async def async_activate(self, **kwargs: Any) -> None:
        if self._locked:
            return
        self._active = True
        await self.async_update_attributes(**kwargs)

    async def async_deactivate(self) -> None:
        if self._locked:
            return
        self._active = False
        self._last_updated = datetime.utcnow().isoformat()
        self.async_write_ha_state()

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information for the zone."""
        return {
            "identifiers": {(DOMAIN, self._zone_id)},
            "name": self._zone_id,
        }

    async def async_update_attributes(self, **kwargs: Any) -> None:
        if self._locked:
            return
        if "brightness" in kwargs:
            self._brightness = kwargs["brightness"]
        if "color_temp" in kwargs:
            self._color_temp = kwargs["color_temp"]
        if "rgb_color" in kwargs:
            self._rgb_color = kwargs["rgb_color"]
        if "transition" in kwargs:
            self._transition = kwargs["transition"]
        if "force" in kwargs:
            self._force = kwargs["force"]
        if "locked" in kwargs:
            self._locked = kwargs["locked"]
        if "conditions" in kwargs:
            self._conditions = kwargs["conditions"]
        if "source" in kwargs:
            self._source = kwargs["source"]
        self._last_updated = datetime.utcnow().isoformat()
        self.async_write_ha_state()
