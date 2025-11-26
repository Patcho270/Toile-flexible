# =====================================================
# Execute DAT : Bump Validation (age gate + -1 fill)
# =====================================================

# ---------------- CONFIG ----------------
BUMP_INFO_OP = 'info_bumpblob'
DUST_INFO_OP = 'info_dustblob'
OUT_DAT_OP   = 'bump_checked'
DEBUG_DAT_OP = 'bump_dust_debug'   # optional

BUMP_X_OP = 'bump_x'
BUMP_Y_OP = 'bump_y'
DUST_X_OP = 'dust_x'
DUST_Y_OP = 'dust_y'

# ---- Kinematic (anti fast / tiny) ----
FAST_WINDOW         = 3
V_THRESH_PX         = 10.0
JUMP_THRESH_PX      = 15.0
A_THRESH_PX         = 8.0
AREA_MIN_PX         = 18.0

# If coords are normalized (0..1)
V_THRESH_UV         = 0.02
JUMP_THRESH_UV      = 0.03
A_THRESH_UV         = 0.02
AREA_MIN_UV         = 0.0003

# ---- Dust overlap (size-aware) ----
IOU_MIN                = 0.08
OVERLAP_SMALL_MIN      = 0.45
CENTER_FRACTION        = 0.50
MIN_DUST_FRAC_OF_BUMP  = 0.40
STRONG_IOU             = 0.30
CONFIRM_FRAMES         = 2

# ---- UV proximity fallback ----
UV_BOX_X               = 0.05
UV_BOX_Y               = 0.05
UV_MIN_DIST            = 0.03

# ---- Publish / Age gates ----
PUBLISH_OK_FRAMES      = 2       # debounce to avoid 1-frame flashes
MIN_BUMP_AGE           = 8       # NEW: must be at least this old (frames) to be publishable

# ---- Output slots ----
MAX_BUMPS              = 4
MAX_DUSTS              = 4
EMPTY_FILL             = -1.0    # NEW: fill unused slots with -1

# housekeeping
STALE_FRAMES           = 60
# -----------------------------------------

# --------------- persistent state ---------------
def _state():
    if 'map' not in me.storage: me.storage['map'] = {}
    return me.storage['map']      # per-bump dust confirm/pair

def _kin_state():
    if 'kin' not in me.storage: me.storage['kin'] = {}
    return me.storage['kin']      # per-bump life/pos/vel

def _pub_state():
    if 'pub' not in me.storage: me.storage['pub'] = {}
    return me.storage['pub']      # per-bump publish debounce

# ----------------- DAT helpers --------------
def _headers(dat):
    return [c.val for c in dat.row(0)] if dat and dat.numRows>0 else []

def _rows(dat):
    if dat is None or dat.numRows <= 1: return []
    heads = _headers(dat); out=[]
    for r in range(1, dat.numRows):
        d={}
        for c in range(min(dat.numCols,len(heads))):
            d[heads[c]] = dat[r,c].val
        out.append(d)
    return out

_DEF = {
    'id': ('id','ID','index','blobid'),
    'x':  ('x','tx','cx','centerx','minx','left','u'),
    'y':  ('y','ty','cy','centery','miny','top','v'),
    'w':  ('w','width','tw'),
    'h':  ('h','height','th'),
}

def _pick(row, keys, default=None, cast=float):
    for k in keys:
        if k in row and row[k] != '':
            try: return cast(row[k])
            except: pass
    return default

def _row_id(row):  return _pick(row, _DEF['id'], None, cast=str)
def _rect_xywh(row):
    x=_pick(row,_DEF['x'],0.0); y=_pick(row,_DEF['y'],0.0)
    w=_pick(row,_DEF['w'],0.0); h=_pick(row,_DEF['h'],0.0)
    return x,y,w,h
def _rect_xyxy(row):
    x,y,w,h=_rect_xywh(row); return (x,y,x+w,y+h)
def _center_xy(row):
    x,y,w,h=_rect_xywh(row); return (x+0.5*w, y+0.5*h)

# ---------------- geometry helpers -----------------
def _iou_stats(a,b):
    ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b
    ix1,iy1=max(ax1,bx1),max(ay1,by1)
    ix2,iy2=min(ax2,bx2),min(ay2,by2)
    iw,ih=max(0.0,ix2-ix1),max(0.0,iy2-iy1)
    inter=iw*ih
    areaA=max(0.0,ax2-ax1)*max(0.0,ay2-ay1)
    areaB=max(0.0,bx2-bx1)*max(0.0,by2-by1)
    denom=areaA+areaB-inter
    iou=(inter/denom) if denom>0 else 0.0
    return iou, inter, areaA, areaB

# ----------------- outputs helpers -----------------
def _update_constant(op_name, values, maxn, fill):
    ch = op(op_name)
    if not ch: return
    for i in range(maxn):
        v = values[i] if i < len(values) else fill
        par = getattr(ch.par, f'value{i}', None)
        if par is not None:
            if abs(par.eval() - v) > 1e-9:
                par.val = v

def _write_out(rows):
    out = op(OUT_DAT_OP)
    if not out: return
    out.clear()
    out.appendRow(['id','valid','reason','iou','overlapSmall','distNorm','areaRatio',
                   'dx','dy','uvDist','x','y','confirm','pub_ok','life'])
    for r in rows:
        out.appendRow([r['id'], str(r['valid']), r['reason'],
            f"{r['iou']:.3f}", f"{r['overlapSmall']:.3f}", f"{r['distNorm']:.3f}", f"{r['areaRatio']:.3f}",
            f"{r['dx']:.4f}", f"{r['dy']:.4f}", f"{r['uvDist']:.4f}",
            f"{r['x']:.4f}", f"{r['y']:.4f}", str(r.get('confirm',0)), str(r.get('pub_ok',0)), str(r.get('life',0))])

def _write_debug(rows):
    dbg = op(DEBUG_DAT_OP)
    if not dbg: return
    dbg.clear()
    dbg.appendRow(['bump_id','dust_id','iou','overlapSmall','distNorm','areaRatio','dx','dy','uvDist','confirm','life'])
    for r in rows:
        dbg.appendRow([r['bump_id'], r['dust_id'] if r['dust_id'] is not None else '-',
            f"{r['iou']:.3f}", f"{r['overlapSmall']:.3f}", f"{r['distNorm']:.3f}", f"{r['areaRatio']:.3f}",
            f"{r['dx']:.4f}", f"{r['dy']:.4f}", f"{r['uvDist']:.4f}", str(r['confirm']), str(r.get('life',0))])

# -------------- pairing & tests --------------
def _best_dust_for_bump(b, dust_rows):
    if not dust_rows:
        return None, {'iou':0.0,'overlapSmall':0.0,'distNorm':9e9,'dx':0.0,'dy':0.0,'uvDist':9e9,'areaRatio':0.0}, None
    rb=_rect_xyxy(b); bx,by=_center_xy(b)
    bW=_pick(b,_DEF['w'],0.0); bH=_pick(b,_DEF['h'],0.0)
    bArea=max(0.0,bW)*max(0.0,bH); bSize=max(bW,bH)
    best=None; bestM={'iou':0.0,'overlapSmall':0.0,'distNorm':9e9,'dx':0.0,'dy':0.0,'uvDist':9e9,'areaRatio':0.0}; bestId=None
    for d in dust_rows:
        rd=_rect_xyxy(d)
        iou,inter,aB,aD=_iou_stats(rb,rd)
        dW=_pick(d,_DEF['w'],0.0); dH=_pick(d,_DEF['h'],0.0)
        dArea=max(0.0,dW)*max(0.0,dH); dSize=max(dW,dH)
        overlapSmall = inter / max(1e-9, min(aB, aD))
        cx,cy=_center_xy(d); dx=abs(bx-cx); dy=abs(by-cy)
        uvDist=(dx*dx+dy*dy)**0.5
        distNorm = uvDist / max(1e-9, min(bSize, dSize))
        areaRatio = dArea / max(1e-9, bArea)
        if (overlapSmall, iou, -distNorm, areaRatio) > (bestM['overlapSmall'], bestM['iou'], -bestM['distNorm'], bestM['areaRatio']):
            best=d; bestM={'iou':iou,'overlapSmall':overlapSmall,'distNorm':distNorm,'dx':dx,'dy':dy,'uvDist':uvDist,'areaRatio':areaRatio}; bestId=_row_id(d)
    return best, bestM, str(bestId) if bestId is not None else None

def _candidate_reject(m):
    if m['iou']>=STRONG_IOU: return True,'iou_strong'
    if m['iou']>=IOU_MIN: return True,'iou'
    if m['overlapSmall']>=OVERLAP_SMALL_MIN: return True,'overlapSmall'
    if m['distNorm']<=CENTER_FRACTION: return True,'centerDist'
    if (m['dx']<=UV_BOX_X and m['dy']<=UV_BOX_Y): return True,'box'
    if m['uvDist']<=UV_MIN_DIST: return True,'uv'
    return False,'-'

def _passes_size_guard(m):
    if m['iou']>=STRONG_IOU: return True
    return m['areaRatio']>=MIN_DUST_FRAC_OF_BUMP

# ------------------ kinematic filter ------------------
def _is_uv_coords(row):
    w=_pick(row,_DEF['w'],0.0); h=_pick(row,_DEF['h'],0.0)
    return (max(w,h)<1.5)

def _fast_reject(bid,row,kin,frame):
    x=_pick(row,_DEF['x'],0.0); y=_pick(row,_DEF['y'],0.0)
    w=_pick(row,_DEF['w'],0.0); h=_pick(row,_DEF['h'],0.0)
    area=max(0.0,w)*max(0.0,h)
    in_uv=_is_uv_coords(row)
    Vt=V_THRESH_UV if in_uv else V_THRESH_PX
    Jt=JUMP_THRESH_UV if in_uv else JUMP_THRESH_PX
    At=A_THRESH_UV if in_uv else A_THRESH_PX
    Amin=AREA_MIN_UV if in_uv else AREA_MIN_PX
    if area>0.0 and area<Amin:
        kin[bid]={'life':1,'px':x,'py':y,'v':0.0,'last':frame}
        return True,'too_small',{'v':0,'a':0,'disp':0,'life':1,'area':area,'uv':in_uv}
    st=kin.get(bid)
    if st is None:
        kin[bid]={'life':1,'px':x,'py':y,'v':0.0,'last':frame}
        return False,'-',{ 'v':0,'a':0,'disp':0,'life':1,'area':area,'uv':in_uv }
    life=st.get('life',0)+1
    dx=x-st.get('px',x); dy=y-st.get('py',y)
    disp=(dx*dx+dy*dy)**0.5; v=disp; a=v-st.get('v',0.0)
    st.update({'life':life,'px':x,'py':y,'v':v,'last':frame}); kin[bid]=st
    if life<=FAST_WINDOW:
        if v>=Vt:   return True,'too_fast_v',   {'v':v,'a':a,'disp':disp,'life':life,'area':area,'uv':in_uv}
        if disp>=Jt:return True,'jump_disp',    {'v':v,'a':a,'disp':disp,'life':life,'area':area,'uv':in_uv}
        if abs(a)>=At:return True,'too_fast_acc',{'v':v,'a':a,'disp':disp,'life':life,'area':area,'uv':in_uv}
    return False,'-',{ 'v':v,'a':a,'disp':disp,'life':life,'area':area,'uv':in_uv }

def _purge_kin(seen_ids, frame, ttl=90):
    kin=_kin_state()
    drop=[k for k,v in kin.items() if k not in seen_ids or (frame - v.get('last',frame))>ttl]
    for k in drop: kin.pop(k,None)

# ------------------ per-frame core ------------------
def _process_frame():
    bumps_dat=op(BUMP_INFO_OP); dust_dat=op(DUST_INFO_OP)
    if not bumps_dat or not dust_dat: return
    bumps=_rows(bumps_dat); dusts=_rows(dust_dat)

    S=_state(); kin=_kin_state(); pub=_pub_state()
    frame=absTime.frame; seen=set()
    results=[]; valid_bumps_rows=[]; debug_rows=[]

    for b in bumps:
        bid=_row_id(b)
        if bid is None: continue
        seen.add(bid)

        bx=_pick(b,_DEF['x'],0.0); by=_pick(b,_DEF['y'],0.0)

        # 1) Kinematic prefilter
        k_rej,k_why,kM=_fast_reject(bid,b,kin,frame)
        life_now = kM.get('life', 1)
        if k_rej:
            pub[bid]={'ok':0}
            results.append({'id':str(bid),'valid':0,'reason':k_why,
                'iou':0.0,'overlapSmall':0.0,'distNorm':9e9,'areaRatio':0.0,
                'dx':kM.get('disp',0.0),'dy':0.0,'uvDist':kM.get('disp',0.0),
                'x':bx,'y':by,'confirm':0,'pub_ok':0,'life':life_now})
            debug_rows.append({'bump_id':str(bid),'dust_id':'-','iou':0.0,'overlapSmall':0.0,'distNorm':9e9,
                'areaRatio':0.0,'dx':kM.get('disp',0.0),'dy':0.0,'uvDist':kM.get('disp',0.0),'confirm':0,'life':life_now})
            continue

        # 2) Dust overlap + confirm
        st=S.get(bid,{'last':frame,'confirm':0,'pair':None}); st['last']=frame
        best_d,m,did=_best_dust_for_bump(b,dusts)
        cand,why=_candidate_reject(m)
        if cand and _passes_size_guard(m):
            same=(did is not None and did==st.get('pair'))
            st['confirm'] = st.get('confirm',0)+1 if same else 1
            st['pair']=did
        else:
            st['confirm']=0; st['pair']=None
            why='-' if not cand else 'size_guard'

        reject=(st['confirm']>=CONFIRM_FRAMES)
        valid = 0 if reject else 1

        # 3) Publish debounce + NEW: age gate
        ps=pub.get(bid,{'ok':0})
        if valid==1 and life_now>=MIN_BUMP_AGE:
            ps['ok']=min(PUBLISH_OK_FRAMES, ps.get('ok',0)+1)
        else:
            ps['ok']=0
        pub[bid]=ps
        publish_now = (ps['ok']>=PUBLISH_OK_FRAMES)

        # If too young, mark reason
        reason_out = ('too_young' if life_now < MIN_BUMP_AGE and valid==1 else (why if reject or cand else '-'))

        res_row={'id':str(bid),'valid': (1 if (publish_now and valid==1) else 0),
                 'reason':reason_out,'iou':m['iou'],'overlapSmall':m['overlapSmall'],'distNorm':m['distNorm'],
                 'dx':m['dx'],'dy':m['dy'],'uvDist':m['uvDist'],'areaRatio':m['areaRatio'],
                 'x':bx,'y':by,'confirm':st['confirm'],'pub_ok':ps['ok'],'life':life_now}
        results.append(res_row)

        debug_rows.append({'bump_id':str(bid),'dust_id': did if did is not None else '-',
            'iou':m['iou'],'overlapSmall':m['overlapSmall'],'distNorm':m['distNorm'],
            'areaRatio':m['areaRatio'],'dx':m['dx'],'dy':m['dy'],'uvDist':m['uvDist'],
            'confirm':st['confirm'],'life':life_now})

        if publish_now and valid==1:
            valid_bumps_rows.append(res_row)

        S[bid]=st

    # purge
    drop=[k for k,v in _state().items() if k not in seen and (frame - v.get('last',frame))>STALE_FRAMES]
    for k in drop: _state().pop(k,None)
    _purge_kin(seen, frame, ttl=90)

    # outputs
    _write_out(results)
    _write_debug(debug_rows)

    # Prepare CHOP values; empty slots filled with -1
    _update_constant(BUMP_X_OP, [b['x'] for b in valid_bumps_rows], MAX_BUMPS, EMPTY_FILL)
    _update_constant(BUMP_Y_OP, [b['y'] for b in valid_bumps_rows], MAX_BUMPS, EMPTY_FILL)
    _update_constant(DUST_X_OP, [_pick(d,_DEF['x'],EMPTY_FILL) for d in dusts], MAX_DUSTS, EMPTY_FILL)
    _update_constant(DUST_Y_OP, [_pick(d,_DEF['y'],EMPTY_FILL) for d in dusts], MAX_DUSTS, EMPTY_FILL)

# -------------- callbacks (run once per frame) --------------
def _run_once_per_frame():
    f=absTime.frame; last=me.storage.get('last_run_frame',-1)
    if f!=last:
        _process_frame()
        me.storage['last_run_frame']=f

def onFrameStart(execDAT):
    _run_once_per_frame(); return

def onFrameEnd(execDAT):
    _run_once_per_frame(); return
