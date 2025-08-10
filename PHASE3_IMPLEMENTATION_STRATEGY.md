# Phase 3 Implementation Strategy - Production-Grade Services

## Architecture Decision

Based on gap analysis, we'll implement a **hybrid service pattern**:
1. **Entity-targeted services** for layer-specific operations
2. **Zone-targeted services** for zone-wide operations
3. **Atomic transaction support** for preset operations

## Implementation Blueprint

### Service Handler Pattern

```python
async def handle_service(call: ServiceCall) -> ServiceResponse:
    """Production-grade service handler pattern."""
    
    # 1. Extract and validate targets
    targets = await _extract_targets(hass, call)
    if not targets:
        raise ServiceValidationError("No valid targets found")
    
    # 2. Validate parameters
    try:
        validated_data = _validate_service_data(call.data)
    except ValueError as e:
        raise ServiceValidationError(f"Invalid parameters: {e}")
    
    # 3. Execute with transaction support
    results = []
    errors = []
    
    for target in targets:
        try:
            result = await _execute_service_action(target, validated_data)
            results.append(result)
        except Exception as e:
            errors.append({"target": target, "error": str(e)})
            _LOGGER.error("Service failed for %s: %s", target, e)
    
    # 4. Return comprehensive response
    return ServiceResponse(
        iserr=bool(errors),
        data={
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }
    )
```

### Transaction Support Pattern

```python
class TransactionContext:
    """Ensures atomic operations."""
    
    def __init__(self, coordinator: ZoneCoordinator):
        self.coordinator = coordinator
        self.backup = None
        self.changes = []
    
    async def __aenter__(self):
        self.backup = self.coordinator.layers.copy()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Rollback on error
            self.coordinator.layers = self.backup
            await self.coordinator.save_layers()
            _LOGGER.error("Transaction rolled back: %s", exc_val)
            return False
        # Commit successful
        return True
```

## Service Implementations

### 1. activate_layer Service

```python
async def handle_activate_layer(call: ServiceCall) -> ServiceResponse:
    """Activate layer with specified parameters.
    
    This is more explicit than switch.turn_on and allows
    setting all parameters in a single call.
    """
    # Extract switch entities
    switches = await _get_switch_entities(hass, call)
    
    # Prepare activation data
    activation_data = {
        ATTR_IS_ON: True,
        ATTR_SOURCE: call.data.get("source", "service.activate_layer"),
    }
    
    # Add optional parameters
    for attr in [ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR, ATTR_TRANSITION]:
        if attr in call.data:
            activation_data[attr] = validate_attribute(attr, call.data[attr])
    
    # Execute on all targets
    results = []
    for switch in switches:
        coordinator = switch.coordinator
        layer_id = switch.layer_id
        
        # Update via coordinator (single source of truth)
        success = await coordinator.update_layer(layer_id, **activation_data)
        
        if success:
            # Fire activation event
            hass.bus.async_fire(
                EVENT_LAYER_ACTIVATED,
                {
                    "zone_id": coordinator.zone_id,
                    "layer_id": layer_id,
                    "activation_data": activation_data,
                    "timestamp": dt_util.now().isoformat(),
                }
            )
        
        results.append({
            "entity_id": switch.entity_id,
            "success": success,
            "layer_id": layer_id,
        })
    
    return ServiceResponse(data={"results": results})
```

### 2. lock_layer Service

```python
async def handle_lock_layer(call: ServiceCall) -> ServiceResponse:
    """Lock a layer to prevent modifications.
    
    Critical: Must be atomic and logged for security.
    """
    switches = await _get_switch_entities(hass, call)
    results = []
    
    for switch in switches:
        coordinator = switch.coordinator
        layer_id = switch.layer_id
        
        # Get current state for audit
        current_layer = coordinator.get_layer(layer_id)
        if not current_layer:
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": "Layer not found",
            })
            continue
        
        # Check if already locked
        if current_layer.get(ATTR_LOCKED, False):
            results.append({
                "entity_id": switch.entity_id,
                "success": False,
                "error": "Already locked",
            })
            continue
        
        # Lock the layer
        success = await coordinator.update_layer(
            layer_id,
            **{ATTR_LOCKED: True}
        )
        
        if success:
            # Fire security event
            hass.bus.async_fire(
                EVENT_LAYER_LOCKED,
                {
                    "zone_id": coordinator.zone_id,
                    "layer_id": layer_id,
                    "locked_by": call.context.user_id,
                    "timestamp": dt_util.now().isoformat(),
                }
            )
            
            _LOGGER.info(
                "Layer %s in zone %s locked by %s",
                layer_id,
                coordinator.zone_id,
                call.context.user_id
            )
        
        results.append({
            "entity_id": switch.entity_id,
            "success": success,
            "layer_id": layer_id,
            "locked": success,
        })
    
    return ServiceResponse(data={"results": results})
```

### 3. apply_preset Service

```python
async def handle_apply_preset(call: ServiceCall) -> ServiceResponse:
    """Apply a preset configuration atomically.
    
    This is the most complex service requiring transaction support.
    """
    zone_id = call.data["zone_id"]
    preset_name = call.data["preset_name"]
    
    # Load preset definition
    preset = await _load_preset(hass, preset_name)
    if not preset:
        raise ServiceValidationError(f"Preset '{preset_name}' not found")
    
    # Get coordinator for zone
    coordinator = await _get_zone_coordinator(hass, zone_id)
    if not coordinator:
        raise ServiceValidationError(f"Zone '{zone_id}' not found")
    
    # Apply preset atomically
    async with TransactionContext(coordinator) as transaction:
        # First, deactivate all layers not in preset
        for layer_id in coordinator.layers:
            if layer_id not in preset.get("layers", {}):
                await coordinator.update_layer(layer_id, **{ATTR_IS_ON: False})
                transaction.changes.append(("deactivated", layer_id))
        
        # Then apply preset layer configurations
        for layer_id, layer_config in preset.get("layers", {}).items():
            # Ensure layer exists
            if layer_id not in coordinator.layers:
                # Create if needed
                await coordinator.create_layer(
                    layer_name=layer_config.get("name", layer_id),
                    priority=layer_config.get("priority", 50),
                )
                transaction.changes.append(("created", layer_id))
            
            # Update layer with preset values
            await coordinator.update_layer(layer_id, **layer_config)
            transaction.changes.append(("updated", layer_id))
        
        # Fire preset event
        hass.bus.async_fire(
            EVENT_PRESET_APPLIED,
            {
                "zone_id": zone_id,
                "preset_name": preset_name,
                "changes": transaction.changes,
                "timestamp": dt_util.now().isoformat(),
            }
        )
    
    return ServiceResponse(
        data={
            "zone_id": zone_id,
            "preset_name": preset_name,
            "changes_made": len(transaction.changes),
            "changes": transaction.changes,
        }
    )
```

## Service Registration

```python
async def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Phase 3 services."""
    
    services = [
        # Layer Control Services
        ("activate_layer", handle_activate_layer, SERVICE_ACTIVATE_LAYER_SCHEMA),
        ("deactivate_layer", handle_deactivate_layer, SERVICE_DEACTIVATE_LAYER_SCHEMA),
        ("update_layer", handle_update_layer, SERVICE_UPDATE_LAYER_SCHEMA),
        ("set_layer_priority", handle_set_layer_priority, SERVICE_SET_PRIORITY_SCHEMA),
        
        # Layer State Services
        ("lock_layer", handle_lock_layer, SERVICE_LOCK_LAYER_SCHEMA),
        ("unlock_layer", handle_unlock_layer, SERVICE_UNLOCK_LAYER_SCHEMA),
        ("force_layer", handle_force_layer, SERVICE_FORCE_LAYER_SCHEMA),
        
        # Zone Control Services
        ("recalculate_zone", handle_recalculate_zone, SERVICE_RECALCULATE_SCHEMA),
        ("reset_zone", handle_reset_zone, SERVICE_RESET_ZONE_SCHEMA),
        
        # Advanced Services
        ("apply_preset", handle_apply_preset, SERVICE_APPLY_PRESET_SCHEMA),
    ]
    
    for service_name, handler, schema in services:
        if hass.services.has_service(DOMAIN, service_name):
            continue
            
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
        
        _LOGGER.info("Registered service: %s.%s", DOMAIN, service_name)
```

## Validation Schemas

```python
# Service validation schemas
SERVICE_ACTIVATE_LAYER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_BRIGHTNESS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=255)
    ),
    vol.Optional(ATTR_COLOR_TEMP): vol.All(
        vol.Coerce(int), vol.Range(min=153, max=500)
    ),
    vol.Optional(ATTR_RGB_COLOR): vol.All(
        vol.ExactSequence([vol.Coerce(int)] * 3),
        vol.Length(min=3, max=3),
    ),
    vol.Optional(ATTR_TRANSITION): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
    vol.Optional("source"): cv.string,
})

SERVICE_APPLY_PRESET_SCHEMA = vol.Schema({
    vol.Required("zone_id"): cv.string,
    vol.Required("preset_name"): cv.string,
    vol.Optional("transition"): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=300)
    ),
})
```

## Error Handling Strategy

### Service Validation Errors
```python
class ServiceValidationError(HomeAssistantError):
    """Raised when service parameters are invalid."""
    
    def __init__(self, message: str, field: str = None):
        super().__init__(message)
        self.field = field
```

### Graceful Degradation
```python
async def handle_service_with_fallback(call: ServiceCall) -> ServiceResponse:
    """Handle service with graceful degradation."""
    try:
        return await handle_service(call)
    except ServiceValidationError as e:
        # User error - return helpful message
        return ServiceResponse(
            iserr=True,
            data={"error": str(e), "field": e.field}
        )
    except Exception as e:
        # System error - log and return generic message
        _LOGGER.exception("Service failed unexpectedly")
        return ServiceResponse(
            iserr=True,
            data={"error": "Service failed. Check logs for details."}
        )
```

## Testing Strategy

### Unit Tests
```python
async def test_activate_layer_service():
    """Test activate_layer service."""
    # Setup
    hass = Mock()
    call = ServiceCall(
        domain=DOMAIN,
        service="activate_layer",
        data={ATTR_BRIGHTNESS: 200},
        target={"entity_id": "switch.test_layer"},
    )
    
    # Execute
    response = await handle_activate_layer(call)
    
    # Assert
    assert response.data["results"][0]["success"] is True
    assert coordinator.layers["test"][ATTR_BRIGHTNESS] == 200
```

### Integration Tests
```python
async def test_preset_application():
    """Test atomic preset application."""
    # Apply preset
    await hass.services.async_call(
        DOMAIN,
        "apply_preset",
        {"zone_id": "living_room", "preset_name": "movie_night"},
        blocking=True,
    )
    
    # Verify all layers updated atomically
    coordinator = hass.data[DOMAIN]["living_room"][DATA_COORDINATOR]
    assert coordinator.layers["mode"][ATTR_IS_ON] is True
    assert coordinator.layers["manual"][ATTR_IS_ON] is False
```

## Performance Considerations

1. **Batch Operations**: Services that target multiple entities execute in parallel
2. **Debouncing**: Coordinator already debounces, services don't need to
3. **Caching**: Preset definitions cached for 5 minutes
4. **Event Throttling**: Duplicate events suppressed within 100ms window

## Success Metrics

1. **Response Time**: All services < 100ms for single entity
2. **Error Rate**: < 0.1% for valid inputs
3. **Transaction Success**: 100% atomicity for preset application
4. **Event Delivery**: 100% event firing for state changes