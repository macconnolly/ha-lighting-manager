"""Zone coordinator for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DATA_LAYERS, DOMAIN
from .manager import LightingManager

_LOGGER = logging.getLogger(__name__)


class ZoneCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinate layer calculations for a zone."""

    def __init__(
        self, hass: HomeAssistant, zone_id: str, lights: List[str]
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"Lighting Manager {zone_id}")
        self.zone_id = zone_id
        self.lights = lights
        self.manager = LightingManager()
        layers = hass.data.get(DOMAIN, {}).get(DATA_LAYERS, {})
        self.layer_entities: List[str] = layers.get(zone_id, [])
        self._debounce: Any = None
        self._unsub = async_track_state_change_event(
            hass, self.layer_entities, self._handle_layer_state
        )

    @callback
    def _handle_layer_state(self, event) -> None:
        if self._debounce:
            self._debounce()
        self._debounce = async_call_later(self.hass, 0.1, self._refresh)

    @callback
    def _refresh(self, _now) -> None:
        self._debounce = None
        self.async_request_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        start = dt_util.utcnow()
        active = []
        for entity_id in self.layer_entities:
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                active.append(
                    {
                        "layer_id": state.attributes["layer_id"],
                        "priority": state.attributes["priority"],
                        "force": state.attributes.get("force", False),
                        "locked": state.attributes.get("locked", False),
                        "attributes": state.attributes,
                    }
                )
        (
            ordered,
            winning,
            final_state,
            conflicts,
        ) = self.manager.calculate_zone_state(active)
        end = dt_util.utcnow()
        duration = (end - start).total_seconds() * 1000
        return {
            "active_layers": ordered,
            "winning_layer": winning,
            "final_state": final_state,
            "conflicts": conflicts,
            "last_calculation": end.isoformat(),
            "calculation_time_ms": duration,
        }

    def async_shutdown(self) -> None:
        if self._unsub:
            self._unsub()
        if self._debounce:
            self._debounce()
