# Metaball System - Complete Documentation

## System Overview

Interactive metaball visualization system using TouchDesigner + Paper.js, controlled by Kinect Azure depth detection or MediaPipe hand tracking, with MIDI output to Ableton Live.

---

## Architecture

```
┌─────────────────┐
│  Kinect Azure   │ (Depth/IR Camera)
└────────┬────────┘
         │
    ┌────▼─────┐
    │ TD Input │
    └────┬─────┘
         │
    ┌────▼──────────────────────┐
    │  Detection Pipeline       │
    ├───────────────────────────┤
    │ 1. bump_detection.py      │ → Finds bump positions
    │ 2. bump_validation.py     │ → Filters false positives
    │ 3. bump_stop.py           │ → Controls cache freeze
    └────┬──────────────────────┘
         │
    ┌────▼──────────────────────┐
    │  Control Layer            │
    ├───────────────────────────┤
    │ hero_control.py           │ → Hero ball control
    │ proximity_calculator.py   │ → Distance/bridge calc
    │ bridge_midi_controller.py │ → MIDI output
    └────┬──────────────────────┘
         │
    ┌────▼──────────────────────┐
    │  Visualization            │
    ├───────────────────────────┤
    │ metaball.html (Paper.js)  │ → 5 fixed + 1 hero ball
    │ webrender1 (TD Web TOP)   │ → Renders HTML
    └───────────────────────────┘
         │
    ┌────▼──────────────────────┐
    │  MIDI Output              │
    └───────────────────────────┘
         │
    ┌────▼──────────────────────┐
    │  Ableton Live             │
    └───────────────────────────┘
```

---

## File Structure

```
Metaball/
├── SYSTEM_DOCUMENTATION.md          # This file
│
├── Detection Pipeline (3 files)
│   ├── bump_detection.py            # Script CHOP - Detects bump positions
│   ├── bump_validation.py           # Execute DAT - Validates bumps
│   └── bump_stop.py                 # Execute DAT - Cache freeze controller
│
├── Control Layer (4 files)
│   ├── hero_control.py              # CHOP Execute - Hero ball control
│   ├── proximity_calculator.py      # Execute DAT - Distance calculations
│   ├── bridge_midi_controller.py    # Execute DAT - MIDI output
│   └── balls_position_updater.py    # CHOP Execute - Dynamic ball positioning
│
├── Utilities (1 file)
│   └── kinect_pressure_depth.py     # Script CHOP - Total depth area
│
├── Visualization (2 files)
│   ├── metaball.html                # Paper.js metaball renderer
│   └── balls_positions.csv          # Ball position data
│
└── TouchDesigner Project
    └── [your .toe file]
```

---

## Detection Pipeline

### 1. bump_detection.py (Script CHOP)

**Purpose:** Core detection engine that finds bump positions from Kinect depth data.

**Inputs:**
- `null_Kinect` TOP - Kinect depth texture
- `null_dust` TOP - Dust particle detection
- `cache_null` TOP - Reference frame

**Outputs:** (CHOP channels)
- `b1:x`, `b1:y`, `b1:age`, `b1:stability` - Bump 1 (normalized 0-1)
- `b2:x`, `b2:y`, `b2:age`, `b2:stability` - Bump 2
- `b3:x`, `b3:y`, `b3:age`, `b3:stability` - Bump 3
- `b4:x`, `b4:y`, `b4:age`, `b4:stability` - Bump 4
- `d1:x`, `d1:y` - Dust 1
- `d2:x`, `d2:y` - Dust 2
- `d3:x`, `d3:y` - Dust 3
- `d4:x`, `d4:y` - Dust 4

**Key Parameters:**
```python
MAX_PEAKS = 4               # Max bumps to detect
MAX_DUST = 4                # Max dust particles
STRONG_THRESHOLD = 0.85     # Strong bump sensitivity
SUBTLE_THRESHOLD = 0.70     # Subtle bump sensitivity
BUMP_STABLE_TIME = 1.0      # Seconds before bump is "stable"
distance_mini = 0.12        # Fusion threshold (merge close bumps)
```

**Algorithm:**
1. **Two-pass detection:**
   - Pass 1: Strong bumps (threshold 0.85)
   - Pass 2: Subtle bumps (threshold 0.70) in unexplored areas
2. **Temporal tracking:** Assigns IDs, tracks age/stability across frames
3. **Dust detection:** Reads from `null_dust`, max 4 particles
4. **Temporal priority:**
   - Stable bumps (>1s) override dust
   - New bumps (<1s) rejected if overlapping dust
5. **Bump fusion:** Merges bumps closer than `distance_mini`

**Output Format:** Normalized coordinates (0.0 = left/top, 1.0 = right/bottom)

---

### 2. bump_validation.py (Execute DAT)

**Purpose:** Filters false positives from bump detection using kinematic + dust overlap validation.

**Inputs:**
- `info_bumpblob` DAT - Bump blob tracking info
- `info_dustblob` DAT - Dust blob tracking info

**Outputs:** (Constant CHOPs)
- `constant_validation_b1` - Validated bump 1 (x, y, age, stability)
- `constant_validation_b2` - Validated bump 2
- `constant_validation_b3` - Validated bump 3
- `constant_validation_b4` - Validated bump 4

**Validation Pipeline:**
```
Raw Bump → Kinematic Filter → Dust Overlap Filter → Age Gate → Debounce → Validated Bump
```

**Stage 1: Kinematic Filter**
```python
MIN_SIZE = 10.0         # Minimum blob size (pixels)
MAX_VELOCITY = 800.0    # Max speed (pixels/frame)
MAX_ACCEL = 600.0       # Max acceleration
MAX_JUMP = 300.0        # Max position jump
```
Rejects bumps that move too fast, too small, or teleport.

**Stage 2: Dust Overlap Filter**
```python
STRONG_IOU = 0.30       # Intersection over union threshold
CONFIRM_FRAMES = 2      # Frames to confirm dust overlap
```
Rejects bumps overlapping dust for 2+ consecutive frames.

**Stage 3: Age Gate + Debounce**
```python
MIN_BUMP_AGE = 8        # Minimum frames before publishable
PUBLISH_OK_FRAMES = 2   # Stability frames required
```
Only publishes bumps that survive 8 frames + 2 frames stable.

**Output Format:**
- Valid bump: `(x, y, age, stability)` in normalized coordinates
- Empty slot: `(-1, -1, 0, 0)`

---

### 3. bump_stop.py (Execute DAT)

**Purpose:** Controls cache freeze/unfreeze for both bump and dust caches based on detection state.

**Inputs:**
- `info_bumpblob` DAT - Bump presence
- `info_dustblob` DAT - Dust presence
- `bump_stop` CHOP - Bump gate (1=freeze on bump)
- `dust_stop` CHOP - Dust gate (1=freeze on dust-only)
- `double_stop` CHOP - Double gate (1=freeze on both)

**Outputs:**
- `cache_capture_bump` TOP `active` parameter (0=freeze, 1=unfreeze)
- `cache_capture_dust` TOP `active` parameter (0=freeze, 1=unfreeze)

**Priority Logic:**
```python
if double_gate and has_bump and has_dust:
    freeze()    # Both present
elif bump_gate and has_bump:
    freeze()    # Bump mode
elif dust_gate and has_dust and not has_bump:
    freeze()    # Dust-only mode
else:
    unfreeze()  # Normal operation
```

**Gate Modes:**
- **bump_stop**: Freeze when bump detected (most common)
- **dust_stop**: Freeze when dust detected but no bump
- **double_stop**: Freeze only when both bump AND dust present

---

## Control Layer

### 4. hero_control.py (CHOP Execute DAT)

**Purpose:** Controls hero ball position and visibility based on detection method (Bump vs MediaPipe).

**Inputs:**
- `hero_control` CHOP - Hero position data (x, y from bump or MediaPipe)
- `detection_methode['method']` - Detection mode (0=bump, 1=MediaPipe)
- `h1:hand_active` channel - MediaPipe hand active state

**Outputs:**
- JavaScript calls to `webrender1`: `window.setHeroPosition(x, y)`, `window.hideHero()`
- `constant_debug_method_tracking` - Debug value

**Logic:**
```python
method = detection_methode['method'].eval()  # 0=bump, 1=MediaPipe
hand_active = hero_control['h1:hand_active'].eval()  # MediaPipe only

# If MediaPipe AND main hand inactive → hide hero
if method == 1 and not hand_active:
    web.executeJavaScript("if(window.hideHero) window.hideHero();")
    return

# If at edges (0 or 1080) → disable connections
if x in (0, 1080) or y in (0, 1080):
    CONNECT_DISTANCE = 0  # No bridges at edges

# Otherwise → update hero position
web.executeJavaScript(f"if(window.setHeroPosition) window.setHeroPosition({x}, {y});")
```

**Detection Methods:**
- **Bump (0):** Uses validated bump position from `bump_validation.py`
- **MediaPipe (1):** Uses hand tracking, **hides hero instantly when hand inactive** (no bridge retraction animation)

**Current Behavior (v1.0):**
- ⚠️ When hand disappears in MediaPipe mode → Hero **disappears instantly**
- ⚠️ Bridges **disappear instantly** (no smooth retraction)
- ✅ When hand returns → Hero reappears and follows hand normally

**Known Limitation:**
Bridge retraction animation not implemented. Attempts to add smooth retraction (ghost mode) were unsuccessful due to TouchDesigner callback limitations (`whileOn()` not called every frame consistently).

---

### 5. proximity_calculator.py (Execute DAT)

**Purpose:** Calculates distances from hero to each of the 5 fixed balls, detects bridge activation.

**Inputs:**
- `hero_control` CHOP - Hero position (x, y)
- `balls_positions_table` DAT - Fixed ball positions

**Outputs:** `proximity_dat` DAT Table
```
ball_id | distance | bridge_active | ball_x | ball_y | angle
0       | 245.67   | 1             | 540.00 | 135.00 | 45.3
1       | 520.00   | 0             | 925.00 | 415.00 | 0.0
2       | 180.23   | 1             | 778.00 | 868.00 | 135.7
3       | 410.00   | 0             | 302.00 | 868.00 | 0.0
4       | 290.45   | 1             | 155.00 | 415.00 | 210.2
```

**Parameters:**
```python
CONNECT_DISTANCE = 480  # Max distance for bridge (pixels)
```

**Calculation:**
```python
dx = ball_x - hero_x
dy = ball_y - hero_y
distance = sqrt(dx² + dy²)

if distance <= CONNECT_DISTANCE:
    bridge_active = 1
    angle = atan2(dy, dx) in degrees (0-360)
else:
    bridge_active = 0
    angle = 0
```

**Bridge Logic:**
- `distance <= 480px` → Bridge active, output actual distance + angle
- `distance > 480px` → Bridge inactive, output 0

---

### 6. bridge_midi_controller.py (Execute DAT)

**Purpose:** Converts bridge states to MIDI notes/CC for Ableton Live control.

**Inputs:**
- `proximity_dat` DAT - Bridge states from proximity calculator

**Outputs:**
- MIDI notes (0-127) to Ableton via TouchDesigner MIDI Out
- MIDI CC messages for continuous parameters

**Mapping:**
```python
# Bridge activation → Note On
ball_0_active → MIDI Note 60 (C4)
ball_1_active → MIDI Note 62 (D4)
ball_2_active → MIDI Note 64 (E4)
ball_3_active → MIDI Note 65 (F4)
ball_4_active → MIDI Note 67 (G4)

# Distance → CC (0-127)
ball_0_distance → CC 1 (Modulation)
ball_1_distance → CC 2
# etc.
```

**Behavior:**
- **Bridge activates:** Send Note On + start sending CC with distance
- **Bridge deactivates:** Send Note Off + stop CC
- **Distance changes:** Update CC value (0-127 mapped from 0-480px)

---

### 7. balls_position_updater.py (CHOP Execute DAT)

**Purpose:** Dynamically updates fixed ball positions in HTML from TouchDesigner.

**Inputs:**
- `balls_positions_table` DAT - Ball positions
- CHOP trigger pulse (when table changes)

**Outputs:**
- JavaScript call to `webrender1`: `window.setAllBallPositions([[x1,y1], [x2,y2], ...])`

**Usage:** Enables runtime control of the 5 fixed ball positions without editing HTML.

**Format:**
```
ball_id | x   | y
0       | 540 | 135
1       | 925 | 415
2       | 778 | 868
3       | 302 | 868
4       | 155 | 415
```

---

## Utilities

### 8. kinect_pressure_depth.py (Script CHOP)

**Purpose:** Simple global presence detector - calculates total occupied area.

**Inputs:**
- `null_Kinect` TOP - Kinect depth texture

**Outputs:**
- `area` channel - Percentage of surface occupied (0.0-1.0)

**Algorithm:**
```python
THRESH = 0.5        # Depth threshold
MASK_WHT = 0.999    # White pixel filter

active_pixels = (depth > THRESH) & (depth < MASK_WHT)
area = count(active_pixels) / total_pixels
```

**Use Case:** Detect overall presence/activity level on the surface.

---

## Visualization

### 9. metaball.html (Paper.js)

**Purpose:** Main visual output - organic blob rendering with bridges.

**Components:**
- **5 Fixed Balls:** Static positions in circular formation (center 540,540, radius 405px)
- **1 Hero Ball:** Controlled by user input (bump or hand)
- **Bridges:** Distance-based connections between hero and fixed balls

**Ball Positions:**
```javascript
[540, 135]   // Ball 0 - North (-90°)
[925, 415]   // Ball 1 - North-East (-18°)
[778, 868]   // Ball 2 - South-East (54°)
[302, 868]   // Ball 3 - South-West (126°)
[155, 415]   // Ball 4 - North-West (198°)
```

**Size Animation:**
```javascript
MIN_SIZE = 38  // Minimum ball radius
MAX_SIZE = 74  // Maximum ball radius

// Size based on inverse distance (closer = bigger)
size = MIN_SIZE + (MAX_SIZE - MIN_SIZE) * (1 - distance/CONNECT_DISTANCE)
```

**JavaScript API:**
```javascript
window.setHeroPosition(x, y)           // Update hero position
window.hideHero()                       // Hide hero ball
window.showHero()                       // Show hero ball
window.setAllBallPositions([[x,y],...]) // Update all fixed balls
```

**Rendering:**
- Paper.js metaball algorithm (iso-surface)
- 60 FPS animation loop
- Distance-based size interpolation
- Smooth bridge appearance/disappearance

---

## Data Flow Summary

```
┌─────────────┐
│ Kinect Azure│
└──────┬──────┘
       │ depth/IR frames
       ▼
┌──────────────────┐
│ bump_detection.py│ (finds 4 bumps + 4 dust)
└──────┬───────────┘
       │ raw positions
       ▼
┌────────────────────┐
│ bump_validation.py │ (filters false positives)
└──────┬─────────────┘
       │ validated bumps
       ▼
┌──────────────────┐
│ hero_control.py  │ (selects best bump → hero)
└──────┬───────────┘
       │ hero position
       ├─────────────────┐
       ▼                 ▼
┌──────────────────┐  ┌────────────┐
│proximity_calc.py │  │metaball.   │
│                  │  │html        │
│(distance/bridge) │  │(visual)    │
└──────┬───────────┘  └────────────┘
       │ bridge states
       ▼
┌──────────────────────┐
│bridge_midi_controller│ (MIDI to Ableton)
└──────────────────────┘
```

---

## Key Thresholds and Parameters

### Detection Sensitivity
```python
STRONG_THRESHOLD = 0.85     # Strong bump (bump_detection.py)
SUBTLE_THRESHOLD = 0.70     # Subtle bump (bump_detection.py)
distance_mini = 0.12        # Bump fusion threshold (bump_detection.py)
```

### Validation Filters
```python
MIN_BUMP_AGE = 8            # Frames before valid (bump_validation.py)
CONFIRM_FRAMES = 2          # Dust overlap confirmation (bump_validation.py)
STRONG_IOU = 0.30           # Dust overlap threshold (bump_validation.py)
```

### Bridge Detection
```python
CONNECT_DISTANCE = 480      # Max bridge distance in pixels (proximity_calculator.py)
```

### Visual
```javascript
MIN_SIZE = 38               // Min ball radius (metaball.html)
MAX_SIZE = 74               // Max ball radius (metaball.html)
```

---

## Troubleshooting

### No bumps detected
1. Check `null_Kinect` TOP has valid depth data
2. Lower `STRONG_THRESHOLD` in `bump_detection.py`
3. Check `cache_null` reference frame is set

### Too many false positives
1. Increase `MIN_BUMP_AGE` in `bump_validation.py`
2. Enable dust filtering via `bump_stop.py` gates
3. Adjust `STRONG_IOU` dust overlap threshold

### Hero disappears randomly
1. Check `hero_control.py` edge detection (x/y = 0 or 1080)
2. Verify MediaPipe `hand_active` state if using hand tracking
3. Check validated bump age meets `MIN_BUMP_AGE`

### Bridges not activating
1. Verify `CONNECT_DISTANCE` in `proximity_calculator.py` (480px)
2. Check hero position is within 480px of fixed balls
3. Verify `proximity_dat` shows `bridge_active = 1`

### MIDI not working
1. Check TouchDesigner MIDI Out device is configured
2. Verify `bridge_midi_controller.py` is receiving `proximity_dat`
3. Test MIDI connection with external MIDI monitor

---

## Future Improvements

### Bump Detection
- [ ] Adaptive thresholds based on ambient lighting
- [ ] Multi-scale detection (different bump sizes)
- [ ] Confidence scoring for bumps

### Validation
- [ ] Machine learning false positive classifier
- [ ] Pressure-based validation (harder press = more valid)
- [ ] Historical pattern analysis

### Hero Control
- [ ] Smooth interpolation between bumps when switching
- [ ] Predictive positioning (anticipate hand movement)
- [ ] Multi-hero support (multiple users)

### Visualization
- [ ] Dynamic ball count (add/remove balls runtime)
- [ ] Color coding based on bridge strength
- [ ] Particle effects on bridge activation

### MIDI
- [ ] Customizable note mappings
- [ ] Velocity based on bump pressure
- [ ] Multi-channel MIDI for complex routing

---

## Version History

**v1.0** (2025-01-25)
- Initial system with bump detection + validation
- 5 fixed balls + 1 hero ball
- MIDI output to Ableton
- MediaPipe hand tracking support
- **Known issue:** Hero and bridges disappear instantly when hand inactive (no smooth retraction)
- **Attempted fix:** Ghost mode animation - failed due to TD callback limitations
- **Backups:** `hero_control_GHOST_BROKEN.py`, `metaball_BROKEN.html` for future reference

---

## Credits

- **TouchDesigner** - Derivative
- **Paper.js** - Jürg Lehni & Jonathan Puckey
- **Kinect Azure SDK** - Microsoft
- **MediaPipe** - Google

---

*Last Updated: 2025-01-25*
