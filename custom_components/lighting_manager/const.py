"""Constants for Lighting Manager integration."""
from typing import Final

# Domain
DOMAIN: Final = "lighting_manager"

# Platforms
PLATFORMS: Final = ["switch", "sensor"]

# Storage
STORAGE_VERSION: Final = 1
STORAGE_KEY_PREFIX: Final = "lighting_manager_"

# Defaults
DEFAULT_PRIORITY: Final = 50
DEFAULT_TRANSITION: Final = 2.0
DEFAULT_BRIGHTNESS_MIN: Final = 10
DEFAULT_BRIGHTNESS_MAX: Final = 100
DEFAULT_COLOR_TEMP_MIN: Final = 2000  # Kelvin (warm)
DEFAULT_COLOR_TEMP_MAX: Final = 6500  # Kelvin (cool)

# Debouncing
DEBOUNCE_SECONDS: Final = 0.1  # 100ms

# Layer Attributes
ATTR_ZONE_ID: Final = "zone_id"
ATTR_LAYER_NAME: Final = "layer_name"
ATTR_LAYER_ID: Final = "layer_id"
ATTR_PRIORITY: Final = "priority"
ATTR_BRIGHTNESS: Final = "brightness"
ATTR_COLOR_TEMP: Final = "color_temp"
ATTR_RGB_COLOR: Final = "rgb_color"
ATTR_TRANSITION: Final = "transition"
ATTR_FORCE: Final = "force"
ATTR_LOCKED: Final = "locked"
ATTR_CONDITIONS: Final = "conditions"
ATTR_SOURCE: Final = "source"
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_EXTRA_ATTRIBUTES: Final = "extra_attributes"
ATTR_IS_ON: Final = "is_on"

# Events
EVENT_LAYER_ACTIVATED: Final = f"{DOMAIN}.layer_activated"
EVENT_LAYER_DEACTIVATED: Final = f"{DOMAIN}.layer_deactivated"
EVENT_LAYER_REMOVED: Final = f"{DOMAIN}.layer_removed"
EVENT_CALCULATION_COMPLETE: Final = f"{DOMAIN}.calculation_complete"
EVENT_CONFLICT_DETECTED: Final = f"{DOMAIN}.conflict_detected"
EVENT_STATE_APPLIED: Final = f"{DOMAIN}.state_applied"

# Device Info
MANUFACTURER: Final = "Lighting Manager"
MODEL: Final = "Adaptive Zone"
SW_VERSION: Final = "4.0.0"

# Data Keys
DATA_COORDINATOR: Final = "coordinator"
DATA_ADD_ENTITIES: Final = "add_entities"
DATA_LIGHT_CONTROLLER: Final = "light_controller"
DATA_CALCULATOR: Final = "calculator"