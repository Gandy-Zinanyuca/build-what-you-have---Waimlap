"""Lee piezas desde una foto con vision clasica: separa, mide y estima el color. Sin entrenamiento."""
import cv2
import numpy as np

# L, a, b (OpenCV, 8 bits) calibrados con la foto de la coleccion de prueba
PALETTE = {
    0: (33, 130, 125),
    15: (197, 128, 136),
    25: (140, 161, 170),
    10: (108, 96, 152),
    71: (123, 131, 130),
    272: (42, 129, 113),
    288: (40, 115, 133),
    322: (103, 113, 113),
}
PART_BY_SHAPE = {(1, 1): "3005", (1, 2): "3004", (1, 4): "3010", (1, 6): "3009", (2, 2): "3003"}


def _background(lab):
    h, w = lab.shape[:2]
    small = cv2.resize(lab, (w // 8, h // 8), interpolation=cv2.INTER_AREA)
    return cv2.resize(cv2.medianBlur(small, 41), (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def segment(rgb):
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (5, 5), 0), cv2.COLOR_RGB2LAB)
    bg = _background(lab)
    d = lab.astype(np.float32) - bg
    chroma = np.hypot(d[..., 1], d[..., 2])
    mask = ((chroma > 16) | (d[..., 0] < -42) | (d[..., 0] > 16)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = rgb.shape[:2]
    margin = 0.012 * max(h, w)
    out = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if cv2.contourArea(c) < 4e-5 * h * w:
            continue
        if x < margin or y < margin or x + bw > w - margin or y + bh > h - margin:
            continue
        out.append(c)
    return out, lab


def nearest_color(value):
    v = np.array(value, dtype=np.float32)
    w = np.array([.45, 1, 1], dtype=np.float32)
    return min(PALETTE, key=lambda k: float(np.sum(((v - np.array(PALETTE[k], dtype=np.float32)) * w) ** 2)))


def _median_lab(lab, contour):
    mask = np.zeros(lab.shape[:2], np.uint8)
    cv2.drawContours(mask, [contour], -1, 1, -1)
    core = cv2.erode(mask, np.ones((9, 9), np.uint8))
    if core.sum() < 20:
        core = mask
    return np.median(lab[core == 1], axis=0).tolist()


def _is_pale(value):
    return value[0] > 100 and abs(value[1] - 128) < 8 and abs(value[2] - 128) < 14


def _merge_pale(cnts, lab, unit, shape):
    """Una pieza clara sobre fondo claro aparece partida en sus studs: se unen los trozos vecinos."""
    pale = [c for c in cnts if _is_pale(_median_lab(lab, c))]
    rest = [c for c in cnts if not _is_pale(_median_lab(lab, c))]
    if not pale:
        return cnts
    mask = np.zeros(shape, np.uint8)
    cv2.drawContours(mask, pale, -1, 1, -1)
    k = max(3, int(unit * 0.9)) | 1
    grouped, _ = cv2.findContours(cv2.dilate(mask, np.ones((k, k), np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    merged = []
    for g in grouped:
        pts = []
        for c in pale:
            x, y = c[0][0]
            if cv2.pointPolygonTest(g, (float(x), float(y)), False) >= 0:
                pts.append(c)
        if pts:
            merged.append(cv2.convexHull(np.vstack(pts)))
    return rest + merged


def detect(rgb):
    cnts, lab = segment(rgb)
    if not cnts:
        return []
    unit = float(np.median([min(cv2.minAreaRect(c)[1]) for c in cnts]))
    cnts = _merge_pale(cnts, lab, unit, lab.shape[:2])
    pieces = []
    for c in cnts:
        r = cv2.minAreaRect(c)
        long_, short = max(r[1]), min(r[1])
        if long_ / max(short, 1) >= 1.55:
            ratio = long_ / unit
            shape = (1, 2 if ratio < 2.7 else 4 if ratio < 4.2 else 6)
        else:
            shape = (2, 2) if short / unit >= 1.4 else (1, 1)
        value = _median_lab(lab, c)
        pieces.append({
            "part": PART_BY_SHAPE[shape],
            "color": nearest_color(value),
            "lab": [round(float(v)) for v in value],
            "box": cv2.boxPoints(r).round().astype(int).tolist(),
            "long": round(long_ / unit, 2),
            "short": round(short / unit, 2),
        })
    return pieces


def to_rows(pieces):
    counts = {}
    for p in pieces:
        k = (p["part"], p["color"])
        counts[k] = counts.get(k, 0) + 1
    return [{"part": k[0], "color": k[1], "qty": v} for k, v in sorted(counts.items())]
