"""Sensor platform for Lighting Manager."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import ATTR_ELEVATION
from homeassistant.core import HomeAssistant, Event, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ADAPTIVE,
    CONF_MIN_ELEVATION,
    CONF_MAX_ELEVATION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up sensors for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    zone_id = coordinator.zone_id
    sensors: list[SensorEntity] = [
        AdaptiveLightFactorSensor(hass, entry, zone_id),
        ActiveLayerSensor(coordinator),
        WinningLayerSensor(coordinator),
        CalculationInputSensor(coordinator),
        CalculationOutputSensor(coordinator),
        ConflictStatusSensor(coordinator),
        LastCalculationSensor(coordinator),
    ]
    async_add_entities(sensors)


class AdaptiveLightFactorSensor(SensorEntity):
    """Sensor reporting the adaptive lighting factor."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry, zone_id: str) -> None:
        self.hass = hass
        self._adaptive = entry.data.get(CONF_ADAPTIVE, {})
        self._current_factor = 0.0
        self._zone_id = zone_id
        self._attr_name = f"{zone_id} Adaptive Lighting Factor"
        self._attr_unique_id = f"{zone_id}_adaptive_factor"

    async def async_added_to_hass(self) -> None:
        self.recalculate(self.hass.states.get("sun.sun"))
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, ["sun.sun"], self.recalculate_from_event
            )
        )

    def recalculate(self, state: State) -> None:
        elevation = state.attributes[ATTR_ELEVATION]
        adaptive = self._adaptive
        self._current_factor = 1.0 - (
            float(
                min(
                    max(elevation, adaptive[CONF_MIN_ELEVATION]),
                    adaptive[CONF_MAX_ELEVATION],
                )
            )
            / float(adaptive[CONF_MAX_ELEVATION])
        )
        self.schedule_update_ha_state()

    def recalculate_from_event(self, event: Event) -> None:
        if (new_state := event.data.get("new_state")) is not None:
            self.recalculate(new_state)

    @property
    def native_value(self) -> float:
        return self._current_factor

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return self._adaptive

    @property
    def device_info(self) -> Mapping[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._zone_id)},
            "name": self._zone_id,
        }


class _ZoneSensor(CoordinatorEntity, SensorEntity):
    """Base class for zone-bound sensors."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._zone_id = coordinator.zone_id
        self._attr_should_poll = False

    @property
    def device_info(self) -> Mapping[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._zone_id)},
            "name": self._zone_id,
        }


class ActiveLayerSensor(_ZoneSensor):
    """Number and list of active layers."""

    _attr_name = "Active Layers"
    _attr_unique_id = None

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_active_layers"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("active_layers", []))

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return {
            "layers": [
                layer["layer_id"]
                for layer in self.coordinator.data.get("active_layers", [])
            ]
        }


class WinningLayerSensor(_ZoneSensor):
    """Sensor for the winning layer."""

    _attr_name = "Winning Layer"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_winning_layer"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("winning_layer")

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return self.coordinator.data.get("final_state", {})


class CalculationInputSensor(_ZoneSensor):
    """Sensor showing full calculation input."""

    _attr_name = "Calculation Input"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_calc_input"

    @property
    def native_value(self) -> str:
        return json.dumps(self.coordinator.data.get("active_layers", []))


class CalculationOutputSensor(_ZoneSensor):
    """Sensor showing final calculation output."""

    _attr_name = "Calculation Output"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_calc_output"

    @property
    def native_value(self) -> str:
        return json.dumps(self.coordinator.data.get("final_state", {}))


class ConflictStatusSensor(_ZoneSensor):
    """Sensor reporting conflict status."""

    _attr_name = "Conflict Status"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_conflicts"

    @property
    def native_value(self) -> str:
        conflicts = self.coordinator.data.get("conflicts", [])
        return "ok" if not conflicts else "conflict"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return {"conflicts": self.coordinator.data.get("conflicts", [])}


class LastCalculationSensor(_ZoneSensor):
    """Sensor for last calculation timestamp and duration."""

    _attr_name = "Last Calculation"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._zone_id}_last_calc"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("last_calculation")

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return {
            "calculation_time_ms": self.coordinator.data.get(
                "calculation_time_ms"
            )
        }
