"""
TouchDesigner Bump Detection Script CHOP
=========================================
Detects multiple pressure bump epicenters from Kinect Azure depth/IR data.
Based on working Script CHOP pattern - reads from null_Kinect TOP.

Network Setup:
1. Kinect Azure TOP -> Null TOP (null_Kinect)
2. Reference TOP (no pressure) -> Cache TOP (cache_null)
3. Slider CHOP (distance_mini) -> Script CHOP INPUT 0 [fusion threshold]
4. Script CHOP with this code

IMPORTANT: Wire distance_mini to Script CHOP input 0 to ensure real-time updates!
- distance_mini = fusion threshold (pixels):
  - Below this distance: bumps are MERGED into one
  - Above this distance: bumps stay SEPARATE
- Recommended range: 50-300 pixels

Outputs per bump (up to MAX_PEAKS):
  bump1_x, bump1_y, bump1_intensity
  bump2_x, bump2_y, bump2_intensity
  ...
  bump_count (total detected)
  debug_diff_max (max intensity above baseline)
  debug_ref_init (baseline value from cache_null)
  debug_min_distance (current min_distance value)
"""

import numpy as np

# Configuration
TOP_PATH = 'null_Kinect'        # Source TOP path
REF_PATH = 'cache_null'         # Reference TOP path for baseline
DUST_TOP_PATH = 'null_dust'     # Edge-detected dust TOP (black = dust, white = background)
DISTANCE_CHOP = 'distance_mini' # CHOP with min distance parameter
MAX_PEAKS = 4                   # Maximum bumps to detect
MAX_DUST = 4                    # Maximum dust particles to detect
MIN_DISTANCE = 150              # Default minimum pixels between bumps (overridden by CHOP)
STRONG_THRESHOLD = 0.85         # Strong bump threshold (relative to max)
SUBTLE_THRESHOLD = 0.70         # Subtle bump threshold (relative to max)
EXCLUSION_MULTIPLIER = 2.5      # Exclusion zone size around strong bumps
BLUR_STRONG = 25                # Strong blur radius (pixels)
BLUR_SUBTLE = 7                 # Subtle blur radius (pixels)
BASELINE_PERCENTILE = 50        # Percentile to use for baseline (median)
MIN_BUMP_HEIGHT = 0.20          # Minimum height above baseline to be a bump
DUST_THRESHOLD = 0.10           # Max gray value to consider as dust (pure black = 0.0)
DUST_BLACK_RATIO = 0.25         # Min ratio of black pixels to be considered dust
DUST_EDGE_THRESHOLD = 0.3       # Max value for black in edge-detected dust image
DUST_EXCLUSION_RADIUS = 100     # Radius around dust to exclude bumps (pixels)
EPS = 1e-9

# Global reference/baseline storage
reference_image = None
reference_initialized = False
baseline_value = 0.5  # Default baseline if not initialized

# Global bump tracking for temporal stability
bump_history = []  # List of tracked bumps: [{id, x, y, first_seen, last_seen}, ...]
next_bump_id = 0

# Temporal tracking constants
BUMP_ASSOCIATION_THRESHOLD = 50  # pixels - max distance to associate same bump
BUMP_STABLE_TIME = 1.0  # seconds - time to consider bump "established"
BUMP_TIMEOUT = 0.5  # seconds - time before bump is considered gone


def setupParameters(scriptOp):
    """Called once when Script CHOP is created"""
    return


def onPulse(par):
    """Reset reference on pulse"""
    global reference_initialized, baseline_value
    if par.name == 'Resetpulse':
        reference_initialized = False
        baseline_value = 0.5  # Reset to default
    return


def _associate_bumps_with_history(detected_bumps, current_time):
    """
    Associate newly detected bumps with historical bumps for temporal tracking.

    Args:
        detected_bumps: List of (x, y, intensity) tuples from current frame
        current_time: Current timestamp in seconds

    Returns:
        List of dicts with bump info including age: [{x, y, intensity, age, id, is_stable}, ...]
    """
    global bump_history, next_bump_id

    # Mark all historical bumps as not seen this frame
    for bump in bump_history:
        bump['seen_this_frame'] = False

    associated_bumps = []

    # Try to associate each detected bump with historical bump
    for (x, y, intensity) in detected_bumps:
        best_match = None
        best_distance = float('inf')

        # Find closest historical bump
        for historical_bump in bump_history:
            dist = np.sqrt((x - historical_bump['x'])**2 + (y - historical_bump['y'])**2)
            if dist < best_distance and dist < BUMP_ASSOCIATION_THRESHOLD:
                best_distance = dist
                best_match = historical_bump

        if best_match is not None:
            # Update existing bump
            best_match['x'] = x
            best_match['y'] = y
            best_match['intensity'] = intensity
            best_match['last_seen'] = current_time
            best_match['seen_this_frame'] = True

            age = current_time - best_match['first_seen']
            is_stable = age >= BUMP_STABLE_TIME

            associated_bumps.append({
                'x': x, 'y': y, 'intensity': intensity,
                'age': age, 'id': best_match['id'], 'is_stable': is_stable
            })
        else:
            # New bump - add to history
            bump_id = next_bump_id
            next_bump_id += 1

            new_bump = {
                'id': bump_id,
                'x': x, 'y': y, 'intensity': intensity,
                'first_seen': current_time,
                'last_seen': current_time,
                'seen_this_frame': True
            }
            bump_history.append(new_bump)

            associated_bumps.append({
                'x': x, 'y': y, 'intensity': intensity,
                'age': 0.0, 'id': bump_id, 'is_stable': False
            })

    # Remove bumps that haven't been seen for BUMP_TIMEOUT
    bump_history[:] = [b for b in bump_history
                       if b['seen_this_frame'] or (current_time - b['last_seen']) < BUMP_TIMEOUT]

    return associated_bumps


def _get_gray(top):
    """Convert TOP to grayscale numpy array"""
    arr = top.numpyArray()
    if arr is None:
        return None

    # Handle different formats
    if arr.ndim == 2:
        return arr.astype(np.float32, copy=False)
    if arr.ndim == 3:
        c = arr.shape[2]
        if c >= 3:
            # RGB to grayscale (luma)
            r = arr[..., 0].astype(np.float32, copy=False)
            g = arr[..., 1].astype(np.float32, copy=False)
            b = arr[..., 2].astype(np.float32, copy=False)
            return 0.2126*r + 0.7152*g + 0.0722*b
        return arr[..., 0].astype(np.float32, copy=False)
    return None


def _simple_blur(img, radius):
    """Simple box blur using NumPy (no external dependencies)"""
    if radius < 1:
        return img

    try:
        from scipy.ndimage import uniform_filter
        # Use uniform (box) filter - built into TouchDesigner's scipy
        return uniform_filter(img, size=radius*2+1, mode='nearest')
    except:
        # Fallback: return unblurred if scipy not available
        return img


def _validate_bump(diff_img, x, y, radius=35):
    """
    Validate bump has proper gradient structure.
    Simplified version - checks radial decrease.
    """
    h, w = diff_img.shape
    x1, x2 = max(0, x - radius), min(w, x + radius)
    y1, y2 = max(0, y - radius), min(h, y + radius)

    if x2 - x1 < radius or y2 - y1 < radius:
        return False

    region = diff_img[y1:y2, x1:x2]
    cx, cy = x - x1, y - y1
    center_val = region[cy, cx]

    if center_val < 15:
        return False

    # Sample 8 radial directions
    angles = np.linspace(0, 2*np.pi, 8, endpoint=False)
    good_gradients = 0

    for angle in angles:
        # Sample along this direction
        vals = []
        for dist in range(0, radius, 3):
            px = int(cx + dist * np.cos(angle))
            py = int(cy + dist * np.sin(angle))
            if 0 <= px < region.shape[1] and 0 <= py < region.shape[0]:
                vals.append(region[py, px])

        if len(vals) < 3:
            continue

        # Check if values generally decrease
        increases = sum(1 for i in range(1, len(vals)) if vals[i] > vals[i-1] + 5)
        if increases < len(vals) * 0.3:  # Less than 30% increases = good
            good_gradients += 1

    return good_gradients >= 5  # At least 5 out of 8 directions good


def _detect_peaks(diff_strong, diff_subtle):
    """
    Detect bump peaks using two-pass approach.
    Returns list of (x, y, intensity) tuples.
    """
    peaks = []
    strong_peaks = []

    # Working copies
    strong_copy = diff_strong.copy()
    subtle_copy = diff_subtle.copy()

    global_max = diff_strong.max()
    if global_max < 1:
        return []

    # First pass: strong bumps
    strong_min = global_max * STRONG_THRESHOLD
    for _ in range(MAX_PEAKS):
        max_val = strong_copy.max()
        if max_val < strong_min:
            break

        # Find peak location
        y, x = np.unravel_index(strong_copy.argmax(), strong_copy.shape)
        peaks.append((int(x), int(y), float(max_val)))
        strong_peaks.append((int(x), int(y), float(max_val)))

        # Suppress circular region
        h, w = strong_copy.shape
        for dy in range(-MIN_DISTANCE, MIN_DISTANCE+1):
            for dx in range(-MIN_DISTANCE, MIN_DISTANCE+1):
                if dx*dx + dy*dy <= MIN_DISTANCE*MIN_DISTANCE:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        strong_copy[ny, nx] = 0

        # Large exclusion in subtle
        excl_r = int(MIN_DISTANCE * EXCLUSION_MULTIPLIER)
        for dy in range(-excl_r, excl_r+1):
            for dx in range(-excl_r, excl_r+1):
                if dx*dx + dy*dy <= excl_r*excl_r:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        subtle_copy[ny, nx] = 0

    # Second pass: subtle bumps
    subtle_min = global_max * SUBTLE_THRESHOLD
    for _ in range(MAX_PEAKS - len(peaks)):
        max_val = subtle_copy.max()
        if max_val < subtle_min:
            break

        y, x = np.unravel_index(subtle_copy.argmax(), subtle_copy.shape)

        # Check exclusion zones
        in_exclusion = False
        for px, py, _ in strong_peaks:
            dist = np.sqrt((x-px)**2 + (y-py)**2)
            if dist < MIN_DISTANCE * EXCLUSION_MULTIPLIER:
                in_exclusion = True
                break

        if not in_exclusion:
            # Validate gradient structure
            if _validate_bump(diff_subtle, x, y, radius=35):
                # Check distance from other subtle bumps
                too_close = False
                for px, py, _ in peaks:
                    if (px, py, _) not in strong_peaks:
                        dist = np.sqrt((x-px)**2 + (y-py)**2)
                        if dist < MIN_DISTANCE:
                            too_close = True
                            break

                if not too_close:
                    peaks.append((int(x), int(y), float(max_val)))

        # Suppress
        h, w = subtle_copy.shape
        rad = MIN_DISTANCE // 2
        for dy in range(-rad, rad+1):
            for dx in range(-rad, rad+1):
                if dx*dx + dy*dy <= rad*rad:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        subtle_copy[ny, nx] = 0

    # Sort by intensity
    peaks.sort(key=lambda p: p[2], reverse=True)
    return peaks


def cook(scriptOp):
    """Called every frame - main detection logic"""
    global reference_image, reference_initialized, baseline_value

    # Initialize output channels
    scriptOp.clear()
    scriptOp.numSamples = 1

    for i in range(1, MAX_PEAKS + 1):
        scriptOp.appendChan(f'bump{i}_x')
        scriptOp.appendChan(f'bump{i}_y')
        scriptOp.appendChan(f'bump{i}_intensity')
        scriptOp.appendChan(f'bump{i}_age')  # Age in seconds
        scriptOp.appendChan(f'bump{i}_stable')  # 1.0 if stable (>1s), 0.0 otherwise
    scriptOp.appendChan('bump_count')
    for i in range(1, MAX_DUST + 1):
        scriptOp.appendChan(f'dust{i}_x')  # Dust position X
        scriptOp.appendChan(f'dust{i}_y')  # Dust position Y
    scriptOp.appendChan('dust_count')  # Number of dust particles detected
    scriptOp.appendChan('test_reached_detection')  # Test: did we reach detection loop?
    scriptOp.appendChan('test_baseline')  # Test: baseline value
    scriptOp.appendChan('test_diff_max')  # Test: max diff after baseline
    scriptOp.appendChan('slider_min_distance_bump')  # Slider value from input

    # Set defaults
    for i in range(1, MAX_PEAKS + 1):
        scriptOp[f'bump{i}_x'][0] = 0.0
        scriptOp[f'bump{i}_y'][0] = 0.0
        scriptOp[f'bump{i}_intensity'][0] = 0.0
        scriptOp[f'bump{i}_age'][0] = 0.0
        scriptOp[f'bump{i}_stable'][0] = 0.0
    scriptOp['bump_count'][0] = 0.0
    for i in range(1, MAX_DUST + 1):
        scriptOp[f'dust{i}_x'][0] = 0.0
        scriptOp[f'dust{i}_y'][0] = 0.0
    scriptOp['dust_count'][0] = 0.0
    scriptOp['test_reached_detection'][0] = 0.0
    scriptOp['test_baseline'][0] = 0.0
    scriptOp['test_diff_max'][0] = 0.0

    # Get current frame
    src = op(TOP_PATH)
    if src is None:
        scriptOp['test_baseline'][0] = -1.0  # Error: no source
        return

    gray = _get_gray(src)
    if gray is None:
        scriptOp['test_baseline'][0] = -2.0  # Error: no gray
        return

    h, w = gray.shape[:2]

    # DUST DETECTION: Detect multiple dust particles from null_dust TOP
    dust_positions = []  # List of (x, y) dust centers in pixels
    dust_top = op(DUST_TOP_PATH)
    if dust_top is not None:
        dust_gray = _get_gray(dust_top)
        if dust_gray is not None:
            # In null_dust: black (< 0.3) = dust, white (> 0.7) = background
            dust_mask = dust_gray < DUST_EDGE_THRESHOLD

            if np.any(dust_mask):
                # Create inverted image for peak detection (dust = bright)
                dust_inverted = 1.0 - dust_gray
                dust_inverted[~dust_mask] = 0.0  # Only keep dust regions

                # Find multiple dust peaks
                dust_copy = dust_inverted.copy()
                dust_h, dust_w = dust_copy.shape

                for _ in range(MAX_DUST):
                    max_val = dust_copy.max()
                    if max_val < 0.5:  # Minimum threshold for dust
                        break

                    # Find peak location
                    max_loc = np.unravel_index(dust_copy.argmax(), dust_copy.shape)
                    y_dust, x_dust = max_loc

                    # Store dust position (in pixels)
                    dust_positions.append((int(x_dust), int(y_dust)))

                    # Suppress area around this dust particle
                    dust_radius = 80  # Minimum distance between dust particles (increased from 30)
                    y_min = max(0, y_dust - dust_radius)
                    y_max = min(dust_h, y_dust + dust_radius + 1)
                    x_min = max(0, x_dust - dust_radius)
                    x_max = min(dust_w, x_dust + dust_radius + 1)

                    yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
                    circle_mask = (xx - x_dust)**2 + (yy - y_dust)**2 <= dust_radius**2
                    dust_copy[y_min:y_max, x_min:x_max][circle_mask] = 0.0
                # Note: Dust output is done at the end after temporal filtering

    # Read MIN_DISTANCE from wired input (distance_mini connected to input 0)
    if scriptOp.inputs:
        try:
            raw_value = scriptOp.inputs[0][0]
            scriptOp['slider_min_distance_bump'][0] = raw_value
            min_distance = int(raw_value)
        except:
            scriptOp['slider_min_distance_bump'][0] = MIN_DISTANCE
            min_distance = MIN_DISTANCE
    else:
        scriptOp['slider_min_distance_bump'][0] = MIN_DISTANCE
        min_distance = MIN_DISTANCE

    # CORRECTED: Pressure = DARK pixels (invert the image)
    # Invert: 1.0 - gray so that dark becomes bright (pressure areas)
    diff = 1.0 - gray

    # Get reference image from cache_null TOP
    ref = op(REF_PATH)
    if ref is None:
        scriptOp['test_baseline'][0] = -3.0  # Error: no reference
        return

    ref_gray = _get_gray(ref)
    if ref_gray is None:
        scriptOp['test_baseline'][0] = -4.0  # Error: no ref gray
        return

    # Invert reference (same as current)
    ref_diff = 1.0 - ref_gray

    # Calculate baseline from reference image
    baseline_value = float(np.percentile(ref_diff, BASELINE_PERCENTILE))

    # Subtract baseline so bumps are relative to zero-pressure state
    diff_normalized = np.clip(diff - baseline_value, 0, 1.0)

    # TEST: Output baseline and diff_max
    scriptOp['test_baseline'][0] = baseline_value
    diff_max = float(diff_normalized.max())
    scriptOp['test_diff_max'][0] = diff_max

    # Check if any bump exceeds minimum height above baseline
    if diff_max < MIN_BUMP_HEIGHT:
        # No valid bumps - output zeros (EARLY EXIT HERE)
        return

    # Use normalized diff for detection
    diff = diff_normalized

    # MULTI-BUMP DETECTION with shadow exclusion and dust filtering
    peaks = []
    strong_peaks = []  # Track strong bumps separately
    diff_copy = diff.copy()
    global_max = diff.max()

    # Two-pass detection: strong bumps first, then subtle
    # Pass 1: Find strong bumps (above STRONG_THRESHOLD)
    strong_min = global_max * STRONG_THRESHOLD

    # TEST: Signal that we reached detection loop
    scriptOp['test_reached_detection'][0] = 1.0

    for peak_num in range(MAX_PEAKS):
        max_val = diff_copy.max()

        # Stop if below strong threshold
        if max_val < strong_min:
            break

        # Get location
        max_loc = np.unravel_index(diff_copy.argmax(), diff_copy.shape)
        y_peak, x_peak = max_loc

        # Store as strong peak (dust filtering happens later with temporal priority)
        peaks.append((int(x_peak), int(y_peak), float(max_val)))
        strong_peaks.append((int(x_peak), int(y_peak), float(max_val)))

        # Suppress LARGE area around strong bumps (to exclude shadows)
        exclusion_radius = int(min_distance * EXCLUSION_MULTIPLIER)
        y_min = max(0, y_peak - exclusion_radius)
        y_max = min(h, y_peak + exclusion_radius + 1)
        x_min = max(0, x_peak - exclusion_radius)
        x_max = min(w, x_peak + exclusion_radius + 1)

        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
        circle_mask = (xx - x_peak)**2 + (yy - y_peak)**2 <= exclusion_radius**2
        diff_copy[y_min:y_max, x_min:x_max][circle_mask] = 0.0

    # Pass 2: Find subtle bumps (above SUBTLE_THRESHOLD, outside strong exclusion zones)
    subtle_min = global_max * SUBTLE_THRESHOLD

    for peak_num in range(MAX_PEAKS - len(peaks)):
        max_val = diff_copy.max()

        # Stop if below subtle threshold
        if max_val < subtle_min:
            break

        # Get location
        max_loc = np.unravel_index(diff_copy.argmax(), diff_copy.shape)
        y_peak, x_peak = max_loc

        # Store subtle peak (dust filtering happens later with temporal priority)
        peaks.append((int(x_peak), int(y_peak), float(max_val)))

        # Suppress normal distance for subtle bumps
        y_min = max(0, y_peak - min_distance)
        y_max = min(h, y_peak + min_distance + 1)
        x_min = max(0, x_peak - min_distance)
        x_max = min(w, x_peak + min_distance + 1)

        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
        circle_mask = (xx - x_peak)**2 + (yy - y_peak)**2 <= min_distance**2
        diff_copy[y_min:y_max, x_min:x_max][circle_mask] = 0.0

    # MERGE CLOSE BUMPS: Combine peaks that are closer than min_distance
    # min_distance = fusion threshold: below = merge, above = separate
    merged_peaks = []
    used = [False] * len(peaks)

    for i in range(len(peaks)):
        if used[i]:
            continue

        x1, y1, int1 = peaks[i]
        cluster = [(x1, y1, int1)]
        used[i] = True

        # Find all peaks within fusion distance
        for j in range(i + 1, len(peaks)):
            if used[j]:
                continue

            x2, y2, int2 = peaks[j]
            dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)

            # If distance < min_distance → MERGE (too close)
            # If distance >= min_distance → KEEP SEPARATE
            if dist < min_distance:
                cluster.append((x2, y2, int2))
                used[j] = True

        # Compute weighted average position (weighted by intensity)
        total_intensity = sum(p[2] for p in cluster)
        avg_x = sum(p[0] * p[2] for p in cluster) / total_intensity
        avg_y = sum(p[1] * p[2] for p in cluster) / total_intensity
        avg_intensity = total_intensity / len(cluster)  # Average intensity

        merged_peaks.append((int(avg_x), int(avg_y), float(avg_intensity)))

    peaks = merged_peaks

    # TEMPORAL TRACKING: Associate bumps with history to get age/stability
    current_time = absTime.seconds
    tracked_bumps = _associate_bumps_with_history(peaks, current_time)

    # TEMPORAL PRIORITY: Filter dust based on bump stability
    # If a stable bump (>1s) overlaps with dust, KEEP bump and ignore dust
    final_bumps = []
    valid_dust_indices = set(range(len(dust_positions)))  # Track which dust are valid

    for bump in tracked_bumps:
        x, y = bump['x'], bump['y']
        is_stable = bump['is_stable']

        # Check if bump overlaps with any dust
        overlaps_with_dust = False
        overlapping_dust_idx = None

        for idx, (x_dust, y_dust) in enumerate(dust_positions):
            dist_to_dust = np.sqrt((x - x_dust)**2 + (y - y_dust)**2)
            if dist_to_dust < DUST_EXCLUSION_RADIUS:
                overlaps_with_dust = True
                overlapping_dust_idx = idx
                break

        if overlaps_with_dust:
            if is_stable:
                # Stable bump (>1s) has PRIORITY - keep bump, invalidate dust
                final_bumps.append(bump)
                if overlapping_dust_idx is not None:
                    valid_dust_indices.discard(overlapping_dust_idx)
            else:
                # New bump (<1s) - dust has priority, reject bump
                pass  # Don't add to final_bumps
        else:
            # No overlap - keep bump
            final_bumps.append(bump)

    # Output all final bumps with temporal info
    for i, bump in enumerate(final_bumps):
        # Normalize coordinates to [0, 1]
        nx = (bump['x'] + 0.5) / max(w, 1)
        ny = (bump['y'] + 0.5) / max(h, 1)

        scriptOp[f'bump{i+1}_x'][0] = np.clip(nx, 0.0, 1.0)
        scriptOp[f'bump{i+1}_y'][0] = np.clip(ny, 0.0, 1.0)
        scriptOp[f'bump{i+1}_intensity'][0] = np.clip(bump['intensity'], 0.0, 1.0)
        scriptOp[f'bump{i+1}_age'][0] = float(bump['age'])
        scriptOp[f'bump{i+1}_stable'][0] = 1.0 if bump['is_stable'] else 0.0

    scriptOp['bump_count'][0] = float(len(final_bumps))

    # Update dust outputs (remove invalidated dust)
    final_dust_positions = [dust_positions[i] for i in sorted(valid_dust_indices)]
    for i, (x_dust, y_dust) in enumerate(final_dust_positions):
        # Normalize to [0, 1]
        dust_x_norm = (x_dust + 0.5) / max(w, 1)
        dust_y_norm = (y_dust + 0.5) / max(h, 1)

        scriptOp[f'dust{i+1}_x'][0] = np.clip(dust_x_norm, 0.0, 1.0)
        scriptOp[f'dust{i+1}_y'][0] = np.clip(dust_y_norm, 0.0, 1.0)

    scriptOp['dust_count'][0] = float(len(final_dust_positions))

    return
