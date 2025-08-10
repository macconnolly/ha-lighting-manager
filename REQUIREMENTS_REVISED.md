# Lighting Manager Requirements Specification (REVISED)

## Core Philosophy Change

The original requirements document prescribed specific layers that "must" exist in every zone. This fundamentally misunderstands the elegance of the layer abstraction. 

**The system provides mechanism, not policy.**

## Revised Section 1.3: Layer Philosophy

### Original (Prescriptive - WRONG):
- **REQ-L006**: Every zone must have these standard layers created automatically:
  - `base_adaptive` (priority 0): Circadian rhythm baseline
  - `environmental` (priority 10): Weather/sensor adjustments
  - `activity` (priority 20): Motion/presence-based changes
  - `mode` (priority 30): Scene/mode overrides
  - `manual` (priority 100): User manual control

### Revised (Flexible - CORRECT):
- **REQ-L006-REVISED**: The system SHALL NOT prescribe any specific layers. Users create whatever layers they need for their use cases. Layers are simply:
  - A name (user-defined)
  - A priority (user-defined, 0-100 or higher)
  - A state (active/inactive)
  - Lighting attributes (brightness, color, etc.)

Examples of layers users MIGHT create (but are not required to):
- "morning_routine" (priority 25)
- "movie_time" (priority 50)
- "security_alert" (priority 90)
- "holiday_colors" (priority 15)
- "bedtime" (priority 40)
- "party_mode" (priority 60)
- Literally anything they want!

The system doesn't know or care what a layer represents. It just manages priorities.

## Key Principle Updates

### 1. Pure Abstraction
Layers are containers for lighting states with priorities. Period. The system makes no assumptions about:
- What layers should exist
- What they should be named
- What priorities make sense
- How many you should have
- What triggers them

### 2. User-Defined Taxonomy
Every household is different:
- A family might want "homework_time" and "dinner"
- A couple might want "romantic" and "cooking"
- A gamer might want "gaming_rgb" and "stream_lighting"
- An office might want "meeting" and "focus"

The system enables all of these equally without judgment or prescription.

### 3. Dynamic Layer Creation
- Layers can be created on-the-fly via services
- Layers can be temporary (auto-remove when deactivated)
- Layers can be created by automations
- Layers can be created by scenes
- Layers can be created by the UI

### 4. No "Standard" Layers
There are no standard layers. If a user wants to create a layer called "base_adaptive" at priority 0, they can. If they want to call it "circadian" at priority 42, they can. If they don't want adaptive lighting at all, that's fine too.

## Impact on Implementation

This changes our approach significantly:

1. **Config Flow**: 
   - Don't create any layers automatically
   - Just create the zone with its lights
   - Let users add layers as needed

2. **Services**:
   - Focus on `create_layer` service
   - Make layer creation easy and dynamic
   - Don't assume any layers exist

3. **Documentation**:
   - Provide examples, not prescriptions
   - Show different household scenarios
   - Emphasize flexibility

4. **Adaptive Lighting**:
   - It's just another possible layer
   - Not special or required
   - Users might call it anything

## Why This Matters

The original requirements would have destroyed the elegance of the system by making it opinionated. The beauty is in its simplicity:

**"Any lighting decision is just a layer with a priority. Highest priority wins."**

That's it. That's the whole system. Everything else is just implementation details to make this concept visible and manageable in Home Assistant.