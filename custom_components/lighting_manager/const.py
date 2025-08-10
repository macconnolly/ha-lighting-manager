"""Constants for Lighting Manager."""

DOMAIN = "lighting_manager"

CONF_ENTITIES = "entities"
CONF_ADAPTIVE = "adaptive"
CONF_MIN_ELEVATION = "min_elevation"
CONF_MAX_ELEVATION = "max_elevation"
CONF_MIN_COLOR_TEMP = "color_temp_min"
CONF_MAX_COLOR_TEMP = "color_temp_max"
CONF_MIN_BRIGHTNESS = "brightness_min"
CONF_MAX_BRIGHTNESS = "brightness_max"
CONF_ADAPTIVE_INPUT_ENTITIES = "adaptive_input_entities"
CONF_INPUT_BRIGHTNESS_ENTITY = "input_brightness_entity"
CONF_INPUT_BRIGHTNESS_MIN = "input_brightness_min"
CONF_INPUT_BRIGHTNESS_MAX = "input_brightness_max"

DATA_ENTITIES = "lm_entities"
DATA_STATES = "lm_states"
DATA_ADAPTIVE_ENTITIES = "adaptive_entities"
DATA_LAYERS = "layers"

PLATFORM_LAYER = "layer"
PLATFORM_SENSOR = "sensor"
PLATFORMS = [PLATFORM_LAYER, PLATFORM_SENSOR]

SERVICE_ACTIVATE_LAYER = "activate_layer"
SERVICE_UPDATE_LAYER = "update_layer"
SERVICE_DEACTIVATE_LAYER = "deactivate_layer"

DEFAULT_LAYERS: dict[str, int] = {
    "base_adaptive": 0,
    "environmental": 10,
    "activity": 20,
    "mode": 30,
    "manual": 100,
}
