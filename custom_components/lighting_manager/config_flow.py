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
        """Manage the options - show menu for basic or advanced."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["basic", "advanced", "modifier"]
        )
    
    async def async_step_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle basic options."""
        if user_input is not None:
            # Update only the basic options
            self.config_entry.options.update(user_input)
            return self.async_create_entry(title="", data=self.config_entry.options)
        
        options = self.config_entry.options
        
        return self.async_show_form(
            step_id="basic",
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
                }
            ),
        )
    
    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adaptive lighting options."""
        if user_input is not None:
            # Update adaptive settings
            self.config_entry.options.update(user_input)
            return self.async_create_entry(title="", data=self.config_entry.options)

        options = self.config_entry.options
        
        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
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
    
    async def async_step_modifier(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle modifier layer settings."""
        if user_input is not None:
            # Validate priority range
            min_priority = user_input.get("modifier_priority_min", 0)
            max_priority = user_input.get("modifier_priority_max", 100)
            
            if min_priority >= max_priority:
                return self.async_show_form(
                    step_id="modifier",
                    data_schema=self._get_modifier_schema(),
                    errors={"base": "invalid_priority_range"},
                    description_placeholders={
                        "error": f"Minimum priority ({min_priority}) must be less than maximum ({max_priority})"
                    }
                )
            
            # Check for existing modifiers outside the new range
            coordinator = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            ).get("coordinator")
            
            if coordinator and hasattr(coordinator, "layers"):
                out_of_range_modifiers = []
                for layer_id, layer_data in coordinator.layers.items():
                    if (layer_data.get("layer_type") in ["modifier", "multiplier"] and 
                        (layer_data.get("priority", 50) < min_priority or 
                         layer_data.get("priority", 50) > max_priority)):
                        out_of_range_modifiers.append(layer_data.get("layer_name", layer_id))
                
                if out_of_range_modifiers:
                    # Warn user about out-of-range modifiers
                    return self.async_show_form(
                        step_id="modifier_confirm",
                        data_schema=vol.Schema({
                            vol.Required("confirm", default=False): bool,
                        }),
                        description_placeholders={
                            "warning": f"The following modifiers will be ignored with the new priority range [{min_priority}, {max_priority}]: {', '.join(out_of_range_modifiers)}"
                        }
                    )
            
            # Update modifier settings
            self.config_entry.options.update(user_input)
            return self.async_create_entry(title="", data=self.config_entry.options)
        
        return self.async_show_form(
            step_id="modifier",
            data_schema=self._get_modifier_schema(),
        )
    
    def _get_modifier_schema(self) -> vol.Schema:
        """Get the schema for modifier settings."""
        options = self.config_entry.options
        return vol.Schema(
            {
                vol.Optional(
                    "k_control_enabled",
                    default=options.get("k_control_enabled", True),
                ): bool,
                vol.Optional(
                    "modifier_priority_min",
                    default=options.get("modifier_priority_min", 0),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=99)),
                vol.Optional(
                    "modifier_priority_max",
                    default=options.get("modifier_priority_max", 100),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    "default_modifier_timeout",
                    default=options.get("default_modifier_timeout", 0),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=10080)),
            }
        )
    
    async def async_step_modifier_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm modifier settings despite warnings."""
        if user_input is not None:
            if user_input.get("confirm"):
                # User confirmed, save the settings
                return self.async_create_entry(title="", data=self.config_entry.options)
            else:
                # User cancelled, go back to modifier step
                return await self.async_step_modifier()
        
        # This shouldn't happen, but handle it gracefully
        return await self.async_step_modifier()