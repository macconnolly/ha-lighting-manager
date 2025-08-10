"""Constants for Lighting Manager integration."""
from typing import Final

# Domain
DOMAIN: Final = "lighting_manager"

# Platforms (sensor included even if placeholder for Phase 4)
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
ATTR_CREATED_AT: Final = "created_at"
ATTR_LAST_MODIFIED: Final = "last_modified"
ATTR_IS_ON: Final = "is_on"

# Adaptive Lighting
ATTR_ADAPTIVE_FACTOR: Final = "adaptive_factor"
ATTR_ADAPTIVE_SOURCE: Final = "adaptive_source"
CONF_ADAPTIVE_ENABLED: Final = "adaptive_enabled"
CONF_ADAPTIVE_BRIGHTNESS_MIN: Final = "adaptive_brightness_min"
CONF_ADAPTIVE_BRIGHTNESS_MAX: Final = "adaptive_brightness_max"
CONF_ADAPTIVE_COLOR_TEMP_MIN: Final = "adaptive_color_temp_min"
CONF_ADAPTIVE_COLOR_TEMP_MAX: Final = "adaptive_color_temp_max"
CONF_ADAPTIVE_ELEVATION_MIN: Final = "adaptive_elevation_min"
CONF_ADAPTIVE_ELEVATION_MAX: Final = "adaptive_elevation_max"
CONF_ADAPTIVE_BRIGHTNESS_ENTITY: Final = "adaptive_brightness_entity"

# Special Layer IDs
LAYER_BASE_ADAPTIVE: Final = "base_adaptive"

# Events
EVENT_LAYER_ACTIVATED: Final = f"{DOMAIN}.layer_activated"
EVENT_LAYER_DEACTIVATED: Final = f"{DOMAIN}.layer_deactivated"
EVENT_LAYER_CREATED: Final = f"{DOMAIN}.layer_created"
EVENT_LAYER_REMOVED: Final = f"{DOMAIN}.layer_removed"
EVENT_LAYER_LOCKED: Final = f"{DOMAIN}.layer_locked"
EVENT_LAYER_UNLOCKED: Final = f"{DOMAIN}.layer_unlocked"
EVENT_LAYER_FORCED: Final = f"{DOMAIN}.layer_forced"
EVENT_CALCULATION_COMPLETE: Final = f"{DOMAIN}.calculation_complete"
EVENT_CONFLICT_DETECTED: Final = f"{DOMAIN}.conflict_detected"
EVENT_STATE_APPLIED: Final = f"{DOMAIN}.state_applied"
EVENT_PRESET_APPLIED: Final = f"{DOMAIN}.preset_applied"
EVENT_ZONE_RESET: Final = f"{DOMAIN}.zone_reset"

# Device Info
MANUFACTURER: Final = "Lighting Manager"
MODEL: Final = "Adaptive Zone"
SW_VERSION: Final = "4.0.0"

# Data Keys
DATA_COORDINATOR: Final = "coordinator"
DATA_ADD_ENTITIES: Final = "add_entities"
DATA_LIGHT_CONTROLLER: Final = "light_controller"
SERVICES_REGISTERED: Final = "services_registered"

# Service Names
SERVICE_ACTIVATE_LAYER: Final = "activate_layer"
SERVICE_DEACTIVATE_LAYER: Final = "deactivate_layer"
SERVICE_UPDATE_LAYER: Final = "update_layer"
SERVICE_SET_LAYER_PRIORITY: Final = "set_layer_priority"
SERVICE_LOCK_LAYER: Final = "lock_layer"
SERVICE_UNLOCK_LAYER: Final = "unlock_layer"
SERVICE_FORCE_LAYER: Final = "force_layer"
SERVICE_UNFORCE_LAYER: Final = "unforce_layer"
SERVICE_RECALCULATE_ZONE: Final = "recalculate_zone"
SERVICE_RESET_ZONE: Final = "reset_zone"
SERVICE_APPLY_PRESET: Final = "apply_preset"
DATA_CALCULATOR: Final = "calculator"