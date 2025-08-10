"""Validation functions for Lighting Manager - Golden Path implementation."""
from typing import Any

from homeassistant.util import slugify, dt as dt_util


def validate_layer_name(name: str) -> str:
    """Validate and slugify layer name."""
    if not isinstance(name, str) or len(name.strip()) == 0:
        raise ValueError("Layer name must be non-empty string")
    if len(name) > 50:
        raise ValueError("Layer name too long (max 50 chars)")
    slugified = slugify(name)
    if not slugified:
        raise ValueError(f"Layer name '{name}' results in empty slug")
    return slugified


def validate_brightness(value: Any) -> int | None:
    """Validate brightness 0-255."""
    if value is None:
        return None
    try:
        val = int(value)
        if val < 0 or val > 255:
            raise ValueError(f"Brightness must be 0-255, got {val}")
        return val
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid brightness: {value}") from e


def validate_color_temp(value: Any) -> int | None:
    """Validate color temperature 153-500 mireds."""
    if value is None:
        return None
    try:
        val = int(value)
        if val < 153 or val > 500:
            raise ValueError(f"Color temp must be 153-500 mireds, got {val}")
        return val
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid color_temp: {value}") from e


def validate_priority(value: Any) -> int:
    """Validate priority 0-100."""
    try:
        val = int(value)
        if val < 0 or val > 100:
            raise ValueError(f"Priority must be 0-100, got {val}")
        return val
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid priority: {value}") from e


def validate_transition(value: Any) -> float | None:
    """Validate transition time 0.0-300.0 seconds."""
    if value is None:
        return None
    try:
        val = float(value)
        if val < 0.0 or val > 300.0:
            raise ValueError(f"Transition must be 0-300 seconds, got {val}")
        return val
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid transition: {value}") from e


def validate_rgb_color(value: Any) -> tuple[int, int, int] | None:
    """Validate RGB color tuple."""
    if value is None:
        return None
    
    try:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("RGB color must be [r, g, b] tuple")
        
        r, g, b = value
        r = int(r)
        g = int(g)
        b = int(b)
        
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB values must be 0-255")
        
        return (r, g, b)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid RGB color: {value}") from e


def get_timezone_aware_now():
    """Get timezone-aware current time.
    
    CRITICAL: Always use this instead of datetime.now()
    """
    return dt_util.now()


def validate_layer_data(data: dict[str, Any]) -> bool:
    """Validate a complete layer data structure."""
    if not isinstance(data, dict):
        return False
    
    # Required fields
    if ATTR_IS_ON not in data:
        return False
    
    # Validate types if present
    try:
        if ATTR_PRIORITY in data:
            validate_priority(data[ATTR_PRIORITY])
        if ATTR_BRIGHTNESS in data:
            validate_brightness(data[ATTR_BRIGHTNESS])
        if ATTR_COLOR_TEMP in data:
            validate_color_temp(data[ATTR_COLOR_TEMP])
        if ATTR_RGB_COLOR in data:
            validate_rgb_color(data[ATTR_RGB_COLOR])
        if ATTR_TRANSITION in data:
            validate_transition(data[ATTR_TRANSITION])
        return True
    except ValueError:
        return False


def validate_layer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a layer payload for create/update operations.
    
    Enforces strict rules about what attributes are allowed based on layer_type.
    
    Args:
        payload: Dictionary containing layer attributes
        
    Returns:
        Validated and cleaned payload
        
    Raises:
        ValueError: If payload violates layer type rules
    """
    layer_type = payload.get(ATTR_LAYER_TYPE, LAYER_TYPE_ABSOLUTE)
    
    # Absolute attributes (only allowed in absolute layers)
    absolute_attrs = {
        ATTR_BRIGHTNESS,
        ATTR_COLOR_TEMP,
        ATTR_RGB_COLOR,
    }
    
    # Modifier attributes (only allowed in modifier/multiplier layers)
    modifier_attrs = {
        ATTR_BRIGHTNESS_PCT_DELTA,
        ATTR_COLOR_TEMP_KELVIN_DELTA,
        ATTR_BRIGHTNESS_FACTOR,
        ATTR_COLOR_TEMP_FACTOR,
    }
    
    if layer_type in [LAYER_TYPE_MODIFIER, LAYER_TYPE_MULTIPLIER]:
        # Check for forbidden absolute attributes
        forbidden = absolute_attrs.intersection(payload.keys())
        if forbidden:
            raise ValueError(
                f"Modifier layer cannot have absolute attributes: {', '.join(forbidden)}. "
                f"Use modifiers like brightness_pct_delta instead."
            )
    else:
        # Absolute layer - check for forbidden modifier attributes
        forbidden = modifier_attrs.intersection(payload.keys())
        if forbidden:
            raise ValueError(
                f"Absolute layer cannot have modifier attributes: {', '.join(forbidden)}. "
                f"Use absolute values like brightness instead."
            )
    
    # Validate modifier values if present
    if ATTR_BRIGHTNESS_PCT_DELTA in payload:
        delta = payload[ATTR_BRIGHTNESS_PCT_DELTA]
        if not isinstance(delta, (int, float)):
            raise ValueError(f"brightness_pct_delta must be a number, got {type(delta).__name__}")
        if not -100 <= delta <= 100:
            raise ValueError(f"brightness_pct_delta must be between -100 and 100, got {delta}")
    
    if ATTR_COLOR_TEMP_KELVIN_DELTA in payload:
        delta = payload[ATTR_COLOR_TEMP_KELVIN_DELTA]
        if not isinstance(delta, (int, float)):
            raise ValueError(f"color_temp_kelvin_delta must be a number, got {type(delta).__name__}")
        if not -5000 <= delta <= 5000:
            raise ValueError(f"color_temp_kelvin_delta must be between -5000 and 5000, got {delta}")
    
    if ATTR_BRIGHTNESS_FACTOR in payload:
        factor = payload[ATTR_BRIGHTNESS_FACTOR]
        if not isinstance(factor, (int, float)):
            raise ValueError(f"brightness_factor must be a number, got {type(factor).__name__}")
        if not 0 <= factor <= 2:
            raise ValueError(f"brightness_factor must be between 0 and 2, got {factor}")
    
    if ATTR_COLOR_TEMP_FACTOR in payload:
        factor = payload[ATTR_COLOR_TEMP_FACTOR]
        if not isinstance(factor, (int, float)):
            raise ValueError(f"color_temp_factor must be a number, got {type(factor).__name__}")
        if not 0.5 <= factor <= 2:
            raise ValueError(f"color_temp_factor must be between 0.5 and 2, got {factor}")
    
    # Validate timeout_minutes if present
    if "timeout_minutes" in payload:
        timeout = payload["timeout_minutes"]
        if not isinstance(timeout, (int, float)):
            raise ValueError(f"timeout_minutes must be a number, got {type(timeout).__name__}")
        if not 0.1 <= timeout <= 10080:  # Max 1 week
            raise ValueError(f"timeout_minutes must be between 0.1 and 10080 (1 week), got {timeout}")
    
    return payload


# Import these in const.py to avoid circular imports
from .const import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_FACTOR,
    ATTR_BRIGHTNESS_PCT_DELTA,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_FACTOR,
    ATTR_COLOR_TEMP_KELVIN_DELTA,
    ATTR_IS_ON,
    ATTR_LAYER_TYPE,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    LAYER_TYPE_ABSOLUTE,
    LAYER_TYPE_MODIFIER,
    LAYER_TYPE_MULTIPLIER,
)