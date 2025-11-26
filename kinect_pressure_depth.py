import numpy as np

TOP_PATH = 'null_Kinect'  # chemin vers le TOP source
THRESH = 0.5              # seuil d’activation
MASK_WHT = 0.999          # seuil pour exclure les pixels blancs
EPS = 1e-9

def cook(scriptOp):
    scriptOp.clear()
    scriptOp.numSamples = 1
    scriptOp.appendChan('area')  # On ne garde que le canal "area"

    src = op(TOP_PATH)
    if src is None:
        scriptOp['area'][0] = 0.0
        return

    arr = src.numpyArray()
    if arr is None:
        scriptOp['area'][0] = 0.0
        return

    # Convertir en niveaux de gris
    if arr.ndim == 3 and arr.shape[2] >= 3:
        r = arr[..., 0].astype(np.float32)
        g = arr[..., 1].astype(np.float32)
        b = arr[..., 2].astype(np.float32)
        gray = 0.2126*r + 0.7152*g + 0.0722*b
    elif arr.ndim == 2:
        gray = arr.astype(np.float32)
    else:
        gray = arr[..., 0].astype(np.float32)

    H, W = gray.shape
    mask_white = (gray >= MASK_WHT)
    active = (gray > THRESH) & (~mask_white)

    if not np.any(active):
        scriptOp['area'][0] = 0.0
        return

    w = np.where(active, gray, 0.0)
    sumw = float(w.sum())
    area = sumw / (H * W) if sumw > EPS else 0.0

    scriptOp['area'][0] = np.clip(area, 0.0, 1.0)
