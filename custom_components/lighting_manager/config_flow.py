"""Config flow for Lighting Manager."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

from .const import DOMAIN, CONF_ENTITIES, CONF_ADAPTIVE

DEFAULT_ADAPTIVE = {
    "min_elevation": 0,
    "max_elevation": 15,
    "color_temp_min": 153,
    "color_temp_max": 333,
}


class LightingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lighting Manager."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            data = {
                CONF_ENTITIES: {
                    eid: {} for eid in user_input["light_entities"]
                },
                CONF_ADAPTIVE: DEFAULT_ADAPTIVE,
            }
            return self.async_create_entry(
                title=user_input["zone_name"], data=data
            )

        schema = vol.Schema(
            {
                vol.Required("zone_name"): str,
                vol.Required("light_entities"): selector(
                    {"entity": {"domain": "light", "multiple": True}}
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
