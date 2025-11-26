# =====================================================
# Execute DAT : execute_freeze_manager
# Purpose:
#   Single controller to freeze/unfreeze BOTH caches.
#   Gates:
#     - bump_stop   : freeze if a bump exists
#     - dust_stop   : freeze if dust exists AND no bump exists
#     - double_stop : freeze only if both bump AND dust exist
#   Priority: double_stop > bump_stop > dust_stop
# =====================================================

# --- CONFIG (rename if needed) ---
INFO_BUMP_DAT = 'info_bumpblob'            # Info DAT from bump Blob Track
INFO_DUST_DAT = 'info_dustblob'            # Info DAT from dust Blob Track
CACHE_TOPS    = ['cache_capture_bump', 'cache_capture_dust']

BUMP_GATE     = 'bump_stop'                # Null CHOP 1/0
DUST_GATE     = 'dust_stop'                # Null CHOP 1/0
DOUBLE_GATE   = 'double_stop'              # Null CHOP 1/0 (NEW)

# --- HELPERS ---
def _gate_on(chop_name):
    c = op(chop_name)
    if not c or c.numChans < 1:
        return False
    try:
        return any(ch.eval() >= 1 for ch in c.chans())
    except:
        return bool(c[0])

def _has_any(dat_op):
    """True if Info DAT has at least one row with usable X/Y or U/V."""
    d = op(dat_op)
    if not d or d.numRows <= 1:
        return False
    headers = [c.val for c in d.row(0)]
    def _get(row, keys):
        for k in keys:
            if k in headers:
                v = d[row, headers.index(k)].val
                if v != '' and v is not None:
                    try: return float(v)
                    except: pass
        return None
    for r in range(1, d.numRows):
        x = _get(r, ('x','u','tx','cx','centerx','minx','left'))
        y = _get(r, ('y','v','ty','cy','centery','miny','top'))
        if x is not None and y is not None:
            return True
    return False

def _set_caches_active(active_bool):
    want = 1 if active_bool else 0
    for name in CACHE_TOPS:
        ct = op(name)
        if not ct:
            debug('Cache TOP not found:', name)
            continue
        if int(ct.par.active) != want:
            ct.par.active = want

# --- MAIN (runs each frame) ---
def onFrameEnd(execDAT):
    has_bump = _has_any(INFO_BUMP_DAT)
    has_dust = _has_any(INFO_DUST_DAT)

    bump_gate   = _gate_on(BUMP_GATE)
    dust_gate   = _gate_on(DUST_GATE)
    double_gate = _gate_on(DOUBLE_GATE)

    # Priority:
    if double_gate and has_bump and has_dust:
        _set_caches_active(False)   # both present → freeze
    elif bump_gate and has_bump:
        _set_caches_active(False)   # bump mode → freeze
    elif dust_gate and has_dust and not has_bump:
        _set_caches_active(False)   # dust-only mode → freeze
    else:
        _set_caches_active(True)    # otherwise → unfreeze
    return
