"""Config flow for Lighting Manager - Golden Path implementation."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ADAPTIVE_BRIGHTNESS_MAX,
    CONF_ADAPTIVE_BRIGHTNESS_MIN,
    CONF_ADAPTIVE_COLOR_TEMP_MAX,
    CONF_ADAPTIVE_COLOR_TEMP_MIN,
    CONF_ADAPTIVE_ELEVATION_MAX,
    CONF_ADAPTIVE_ELEVATION_MIN,
    CONF_ADAPTIVE_ENABLED,
    DEFAULT_BRIGHTNESS_MAX,
    DEFAULT_BRIGHTNESS_MIN,
    DEFAULT_COLOR_TEMP_MAX,
    DEFAULT_COLOR_TEMP_MIN,
    DEFAULT_TRANSITION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_zone_name(hass: HomeAssistant, zone_name: str) -> bool:
    """Validate that zone name is unique."""
    zone_id = slugify(zone_name)
    
    # Check existing config entries
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("zone_id") == zone_id:
            return False
    
    return True


class LightingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lighting Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            zone_name = user_input["zone_name"]
            zone_id = slugify(zone_name)
            
            # Validate unique zone name
            if not await validate_zone_name(self.hass, zone_name):
                errors["base"] = "duplicate_zone"
            
            # Validate at least one light selected
            light_entities = user_input.get("light_entities", [])
            if not light_entities:
                errors["base"] = "no_lights"
            
            if not errors:
                # Create config entry with proper data/options split
                return self.async_create_entry(
                    title=zone_name,
                    data={
                        "zone_id": zone_id,  # Immutable, structural
                        "zone_name": zone_name,  # Immutable, display name
                        "area_id": None,  # Optional area association (Phase 5)
                    },
                    options={
                        "light_entities": light_entities,  # User-configurable
                        "default_transition": DEFAULT_TRANSITION,
                        CONF_ADAPTIVE_ENABLED: False,
                        CONF_ADAPTIVE_BRIGHTNESS_MIN: 10,
                        CONF_ADAPTIVE_BRIGHTNESS_MAX: 255,
                        CONF_ADAPTIVE_COLOR_TEMP_MIN: 153,  # Mireds (warm)
                        CONF_ADAPTIVE_COLOR_TEMP_MAX: 500,  # Mireds (cool)
                        CONF_ADAPTIVE_ELEVATION_MIN: -6,
                        CONF_ADAPTIVE_ELEVATION_MAX: 15,
                    },
                )

        # Show form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("zone_name"): str,
                    vol.Required("light_entities"): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=LIGHT_DOMAIN,
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Lighting Manager.
    
    GOLDEN PATH: Properly reconstruct brightness/color ranges as arrays.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Store adaptive settings as individual values
            options_data = {
                "light_entities": user_input["light_entities"],
                "default_transition": user_input["default_transition"],
                CONF_ADAPTIVE_ENABLED: user_input[CONF_ADAPTIVE_ENABLED],
                CONF_ADAPTIVE_BRIGHTNESS_MIN: user_input[CONF_ADAPTIVE_BRIGHTNESS_MIN],
                CONF_ADAPTIVE_BRIGHTNESS_MAX: user_input[CONF_ADAPTIVE_BRIGHTNESS_MAX],
                CONF_ADAPTIVE_COLOR_TEMP_MIN: user_input[CONF_ADAPTIVE_COLOR_TEMP_MIN],
                CONF_ADAPTIVE_COLOR_TEMP_MAX: user_input[CONF_ADAPTIVE_COLOR_TEMP_MAX],
                CONF_ADAPTIVE_ELEVATION_MIN: user_input[CONF_ADAPTIVE_ELEVATION_MIN],
                CONF_ADAPTIVE_ELEVATION_MAX: user_input[CONF_ADAPTIVE_ELEVATION_MAX],
            }
            _LOGGER.info("Saving options for zone %s: light_entities=%s", 
                        self.config_entry.data.get("zone_name"), 
                        user_input["light_entities"])
            return self.async_create_entry(title="", data=options_data)

        options = self.config_entry.options
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "light_entities",
                        default=options.get("light_entities", []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=LIGHT_DOMAIN,
                            multiple=True,
                        )
                    ),
                    vol.Optional(
                        "default_transition",
                        default=options.get("default_transition", DEFAULT_TRANSITION),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=300.0)),
                    vol.Optional(
                        CONF_ADAPTIVE_ENABLED,
                        default=options.get(CONF_ADAPTIVE_ENABLED, False),
                    ): bool,
                    vol.Optional(
                        CONF_ADAPTIVE_BRIGHTNESS_MIN,
                        default=options.get(CONF_ADAPTIVE_BRIGHTNESS_MIN, 10),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                    vol.Optional(
                        CONF_ADAPTIVE_BRIGHTNESS_MAX,
                        default=options.get(CONF_ADAPTIVE_BRIGHTNESS_MAX, 255),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                    vol.Optional(
                        CONF_ADAPTIVE_COLOR_TEMP_MIN,
                        default=options.get(CONF_ADAPTIVE_COLOR_TEMP_MIN, 153),
                    ): vol.All(vol.Coerce(int), vol.Range(min=153, max=500)),
                    vol.Optional(
                        CONF_ADAPTIVE_COLOR_TEMP_MAX,
                        default=options.get(CONF_ADAPTIVE_COLOR_TEMP_MAX, 500),
                    ): vol.All(vol.Coerce(int), vol.Range(min=153, max=500)),
                    vol.Optional(
                        CONF_ADAPTIVE_ELEVATION_MIN,
                        default=options.get(CONF_ADAPTIVE_ELEVATION_MIN, -6),
                    ): vol.All(vol.Coerce(int), vol.Range(min=-90, max=90)),
                    vol.Optional(
                        CONF_ADAPTIVE_ELEVATION_MAX,
                        default=options.get(CONF_ADAPTIVE_ELEVATION_MAX, 15),
                    ): vol.All(vol.Coerce(int), vol.Range(min=-90, max=90)),
                }
            ),
        )