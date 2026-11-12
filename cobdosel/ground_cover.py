"""Cobertura del suelo con fotos verticales hacia abajo (CobDosel, v0.15.0). Sin Qt ni QGIS.

Herramienta general (no supone un diseño de muestreo):
- Área de muestreo: un cuadro físico en la foto (se marcan sus 4 esquinas y se rectifica a un cuadrado de tamaño
  conocido) o un área fija calculada con la altura de la cámara y la focal de la calibración del teléfono.
- Vegetación verde: automática, con la regla de Canopeo (Patrignani y Ochsner 2015: R/G < P1, B/G < P2,
  2G − R − B > P3; por defecto 0,95, 0,95 y 20). Se compara con ExG − ExR > 0 (Meyer y Neto 2008); si difieren
  más de AGREEMENT_LIMIT puntos, la foto queda «a revisar».
- Vegetación seca, hojarasca y suelo desnudo: por intercepción de puntos. Una cuadrícula regular de puntos con
  un desfase aleatorio (semilla registrada); los puntos verdes según Canopeo se marcan solos y el analista
  clasifica los demás (y puede corregir cualquiera). Cobertura de cada clase = % de puntos, con IC 95 % (Wilson).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import base64
import csv
import html as _h
import io
import json
import math
import os
import re
import unicodedata

import numpy as np

CLASSES = (
    ("verde", "Vegetación verde"),
    ("seca", "Vegetación seca"),
    ("hojarasca", "Hojarasca"),
    ("suelo", "Suelo desnudo"),
    ("no_id", "No identificable"),
)
CLASS_LABELS = dict(CLASSES)
CLASS_COLORS = {"verde": (0, 200, 0), "seca": (230, 190, 40), "hojarasca": (150, 90, 30),
                "suelo": (120, 120, 120), "no_id": (60, 120, 255), None: (255, 255, 255)}
# v0.15.7: clases nuevas del usuario (archivo JSON en ~/.cobdosel); colores que se asignan en orden
CUSTOM_CLASSES_FILE = os.path.join(os.path.expanduser("~"), ".cobdosel", "clases_suelo.json")
CUSTOM_PALETTE = ((200, 220, 0), (255, 105, 180), (0, 150, 136), (128, 0, 128), (255, 69, 0), (70, 130, 180),
                  (154, 205, 50), (210, 105, 30))
MAX_CLASSES = 9                # teclas 1–9
# v0.15.13: grupos de clases (p. ej. «Vegetación total» = verde + no verde + seca), guardados como las clases
GROUPS_FILE = os.path.join(os.path.expanduser("~"), ".cobdosel", "grupos_suelo.json")
# v0.15.7: diferencias entre las reglas en la vista y el informe
ONLY_EXGEXR_COLOR = (0, 230, 255)       # cian: verde solo para ExG − ExR
ONLY_CANOPEO_COLOR = (255, 140, 0)      # naranja: verde solo para Canopeo
GREEN_SHADE_COLOR = (255, 0, 255)       # magenta: verde según Canopeo
CANOPEO_DEFAULT = (0.95, 0.95, 20.0)
AGREEMENT_LIMIT = 5.0          # puntos de diferencia Canopeo − ExG−ExR que dejan la foto «a revisar»
DEFAULT_POINTS = 100
QUADRAT_PX = 1000              # lado del cuadro rectificado (px)


# ---------------------------------------------------------------- vegetación verde
def canopeo_mask(rgb, p1=CANOPEO_DEFAULT[0], p2=CANOPEO_DEFAULT[1], p3=CANOPEO_DEFAULT[2]):
    """Máscara de vegetación verde con la regla de Canopeo (Patrignani y Ochsner 2015)."""
    a = np.asarray(rgb, dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    gs = np.maximum(g, 1.0)
    return (r / gs < p1) & (b / gs < p2) & ((2.0 * g - r - b) > p3)


def exg_exr_mask(rgb):
    """Máscara ExG − ExR > 0 con coordenadas cromáticas (Meyer y Neto 2008)."""
    a = np.asarray(rgb, dtype=np.float32)
    s = np.maximum(a.sum(axis=-1), 1.0)
    r, g, b = a[..., 0] / s, a[..., 1] / s, a[..., 2] / s
    return ((2.0 * g - r - b) - (1.4 * r - g)) > 0.0


def disagreement_masks(rgb, params=CANOPEO_DEFAULT):
    """(verde solo para ExG − ExR, verde solo para Canopeo): dónde difieren las dos reglas (v0.15.7)."""
    c = canopeo_mask(rgb, *params)
    x = exg_exr_mask(rgb)
    return x & ~c, c & ~x


def shade(rgb, green=None, only_x=None, only_c=None):
    """Copia de la imagen con el verde de Canopeo en magenta (55/45) y las diferencias entre las reglas en cian
    (solo ExG − ExR) y naranja (solo Canopeo), opacos para que se vean (v0.15.7)."""
    a = np.asarray(rgb, dtype=np.uint8).copy()
    if green is not None:
        a[green] = (0.55 * a[green] + 0.45 * np.array(GREEN_SHADE_COLOR)).astype(np.uint8)
    if only_x is not None:
        a[only_x] = ONLY_EXGEXR_COLOR
    if only_c is not None:
        a[only_c] = ONLY_CANOPEO_COLOR
    return a


def agreement_note(res, where="ventana"):
    """Texto del aviso cuando Canopeo y ExG − ExR difieren más de AGREEMENT_LIMIT puntos, o ''.

    v0.15.15: texto para el usuario final: qué pasa, qué valor se informa y por qué (Canopeo es la regla publicada
    que CobDosel usa por convención, no «la correcta»), qué significa la diferencia y dónde verla. where: «ventana»
    (tecla C) o «informe» (sección de las diferencias)."""
    if not res.get("revisar"):
        return ""
    see = ("pulse C en la ventana" if where == "ventana"
           else "vea la imagen «Dónde difieren Canopeo y ExG − ExR» más abajo")
    x_more = res["verde_exgexr_pct"] > res["verde_canopeo_pct"]
    cause = ("casi siempre píxeles mezcla en el borde entre hojas verdes y material seco (también tejido amarillento u "
             "hojas en sombra)" if x_more
             else "por ejemplo, suelo, piedras o algas de color verdoso, o reflejos")
    counts = ("que no cuenta esa parte dudosa; con ExG − ExR, que sí la cuenta" if x_more
              else "que sí cuenta esa parte dudosa; con ExG − ExR, que no la cuenta")
    return ("Las dos reglas del verde difieren {d:.1f} puntos (Canopeo {c:.1f} %; ExG − ExR {x:.1f} %; el aviso aparece "
            "con más de {lim:.0f}). Una parte del área es verde para una regla y no para la otra: {cause}. No es un "
            "error de la foto ni de la clasificación. El valor que se informa es el de Canopeo, la regla publicada que "
            "usa CobDosel, {counts}, el verde sería {x:.1f} %. Para ver dónde está, {see} (cian: verde solo para "
            "ExG − ExR; naranja: verde solo para Canopeo).").format(
        d=abs(res["diferencia_pct"]), c=res["verde_canopeo_pct"], x=res["verde_exgexr_pct"], lim=AGREEMENT_LIMIT,
        see=see, cause=cause, counts=counts)


# ---------------------------------------------------------------- clases
def class_key_for(name, existing=()):
    """Clave para el CSV a partir del nombre: minúsculas sin tildes, «_» en lugar de espacios; única."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "clase"
    key, k = s, 2
    while key in existing:
        key, k = "{}_{}".format(s, k), k + 1
    return key


def load_custom_classes(path=None):
    """Clases nuevas guardadas: [{"clave", "nombre", "color"}]. Lista vacía si no hay archivo o no se lee."""
    try:
        with open(path or CUSTOM_CLASSES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [{"clave": str(d["clave"]), "nombre": str(d["nombre"]), "color": tuple(int(v) for v in d["color"])}
                for d in data if d.get("clave") and d.get("nombre")]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_custom_classes(items, path=None):
    path = path or CUSTOM_CLASSES_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"clave": d["clave"], "nombre": d["nombre"], "color": list(d["color"])} for d in items], f,
                  ensure_ascii=False, indent=2)
    return path


def class_list(custom=None):
    """Lista de clases [(clave, nombre, color)]: las 5 fijas y luego las nuevas."""
    out = [(k, l, CLASS_COLORS[k]) for k, l in CLASSES]
    for d in custom or []:
        out.append((d["clave"], d["nombre"], tuple(d["color"])))
    return out


def new_custom_class(name, custom, color=None):
    """Agrega una clase nueva (devuelve la lista actualizada). Error si el nombre ya existe o hay 9 clases."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Escriba el nombre de la clase.")
    cl = class_list(custom)
    if any(l.lower() == name.lower() for _k, l, _c in cl):
        raise ValueError("Ya existe la clase «{}».".format(name))
    if len(cl) >= MAX_CLASSES:
        raise ValueError("Se admiten hasta {} clases (teclas 1–9).".format(MAX_CLASSES))
    used = {c for _k, _l, c in cl}
    if color is None:
        color = next((c for c in CUSTOM_PALETTE if c not in used), CUSTOM_PALETTE[len(custom) % len(CUSTOM_PALETTE)])
    return list(custom) + [{"clave": class_key_for(name, [k for k, _l, _c in cl]), "nombre": name,
                            "color": tuple(color)}]


# ---------------------------------------------------------------- grupos de clases (v0.15.13)
def load_groups(path=None):
    """Grupos guardados: [{"nombre", "clases": [claves]}]. Lista vacía si no hay archivo o no se lee."""
    try:
        with open(path or GROUPS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [{"nombre": str(g["nombre"]), "clases": [str(k) for k in g["clases"]]}
                for g in data if g.get("nombre") and g.get("clases")]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_groups(groups, path=None):
    path = path or GROUPS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"nombre": g["nombre"], "clases": list(g["clases"])} for g in groups], f, ensure_ascii=False,
                  indent=2)
    return path


def set_group(groups, name, keys, classes, old_name=None):
    """Crea o reemplaza un grupo (devuelve la lista nueva). Errores claros: sin nombre, menos de una clase, clase
    desconocida, nombre repetido o igual al de una clase."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Escriba el nombre del grupo.")
    valid = [k for k, _l, _c in classes]
    keys = [k for k in valid if k in set(keys)]          # orden de la lista de clases
    if not keys:
        raise ValueError("Marque al menos una clase para el grupo «{}».".format(name))
    if any(l.lower() == name.lower() for _k, l, _c in classes):
        raise ValueError("«{}» ya es el nombre de una clase: use otro nombre para el grupo.".format(name))
    others = [g for g in groups if g["nombre"] != (old_name or name)]
    if any(g["nombre"].lower() == name.lower() for g in others):
        raise ValueError("Ya existe el grupo «{}».".format(name))
    new = {"nombre": name, "clases": keys}
    out, done = [], False
    for g in groups:
        if g["nombre"] == (old_name or name):
            out.append(new); done = True
        else:
            out.append(g)
    if not done:
        out.append(new)
    return out


def groups_for(groups, classes):
    """Grupos válidos para una lista de clases: quita las clases que ya no existen y los grupos que quedan vacíos."""
    valid = {k for k, _l, _c in classes}
    out = []
    for g in groups or []:
        ks = [k for k in g["clases"] if k in valid]
        if ks:
            out.append({"nombre": g["nombre"], "clases": ks})
    return out


def group_definition(group, classes):
    names = dict((k, l) for k, l, _c in classes)
    return "{} = {}".format(group["nombre"], " + ".join(names.get(k, k) for k in group["clases"]))


# ---------------------------------------------------------------- área de muestreo
def order_corners(pts):
    """Ordena 4 puntos (x, y) como superior izquierda, superior derecha, inferior derecha, inferior izquierda."""
    p = np.asarray(pts, dtype=float)
    if p.shape != (4, 2):
        raise ValueError("Se necesitan exactamente 4 esquinas.")
    s = p.sum(axis=1)
    d = p[:, 0] - p[:, 1]
    tl, br = p[np.argmin(s)], p[np.argmax(s)]
    tr, bl = p[np.argmax(d)], p[np.argmin(d)]
    out = np.array([tl, tr, br, bl])
    if len({tuple(x) for x in out}) < 4:
        raise ValueError("Las 4 esquinas no forman un cuadrilátero (revise el orden o repita los clics).")
    return out


def homography(src, dst):
    """Homografía 3 × 3 que lleva los 4 puntos src a dst (solución directa de 8 ecuaciones)."""
    A, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(rhs, float))
    return np.append(h, 1.0).reshape(3, 3)


def rectify_quadrat(rgb, corners, out_px=QUADRAT_PX):
    """Endereza el cuadro marcado (4 esquinas, en px de la foto) a un cuadrado de out_px × out_px px."""
    src = order_corners(corners)
    n = int(out_px)
    dst = np.array([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]], float)
    Hinv = homography(dst, src)                  # de la salida a la foto (muestreo inverso)
    vv, uu = np.mgrid[0:n, 0:n]
    pts = np.stack([uu.ravel(), vv.ravel(), np.ones(n * n)])
    xs, ys, ws = Hinv @ pts
    xs, ys = xs / ws, ys / ws
    h, w = rgb.shape[:2]
    inside = (xs >= 0) & (xs <= w - 1) & (ys >= 0) & (ys <= h - 1)
    if not inside.all():
        raise ValueError("Parte del cuadro queda fuera de la foto.")
    xi = np.clip(np.rint(xs).astype(int), 0, w - 1)
    yi = np.clip(np.rint(ys).astype(int), 0, h - 1)
    return np.asarray(rgb)[yi, xi].reshape(n, n, 3)


def fixed_area_side_px(focal_px, height_m, side_m):
    """Lado en px del cuadrado de side_m metros visto desde height_m metros con focal focal_px (lente rectilínea,
    cámara vertical sobre suelo plano)."""
    if not focal_px or height_m <= 0 or side_m <= 0:
        raise ValueError("La focal, la altura y el lado deben ser positivos.")
    return float(side_m) * float(focal_px) / float(height_m)


FIT_MARGIN = 0.05              # v0.15.9: margen recomendado (cámara unos cm más baja de lo previsto; bordes de la foto)


def fixed_area_fit(focal_px, short_side_px, height_m, side_m, margin=FIT_MARGIN):
    """Qué cuadrado cabe en la foto con área fija (v0.15.9). El cuadrado debe caber en el lado corto de la foto:
    lado máximo = H · lado corto / f; altura mínima para un lado = lado · f / lado corto. Devuelve dict con
    max_side_m, max_side_margin_m, min_height_m, min_height_margin_m, fits (exacto) y fits_margin."""
    if not focal_px or not short_side_px or height_m <= 0 or side_m <= 0:
        raise ValueError("La focal, el lado corto de la foto, la altura y el lado deben ser positivos.")
    k = float(short_side_px) / float(focal_px)          # lado máximo / altura
    max_side = float(height_m) * k
    min_h = float(side_m) / k
    return {"max_side_m": max_side, "max_side_margin_m": max_side * (1.0 - margin),
            "min_height_m": min_h, "min_height_margin_m": min_h / (1.0 - margin),
            "fits": side_m <= max_side, "fits_margin": side_m <= max_side * (1.0 - margin)}


def aspect_mismatch(cal, width_px, height_px, tol=0.01):
    """Texto del error si la foto y la calibración tienen distinta proporción (v0.15.9), o ''. Una foto 16:9 es un
    recorte de la 4:3: la calibración no se puede reescalar por el lado corto (la focal quedaría 25 % baja)."""
    cw, ch = cal.get("image_width_px"), cal.get("image_height_px")
    if not cw or not ch:
        return ""
    a_cal = max(cw, ch) / float(min(cw, ch))
    a_img = max(width_px, height_px) / float(min(width_px, height_px))
    if abs(a_cal - a_img) <= tol * a_img:
        return ""
    return ("La foto ({}×{} px, proporción {:.3f}) y la calibración ({}×{} px, {:.3f}) tienen distinta proporción: "
            "una foto 16:9 es un recorte de la 4:3 y el área fija quedaría mal. Use fotos con la proporción de la "
            "calibración (4:3) o calibre con esa proporción.".format(width_px, height_px, a_img, int(cw), int(ch), a_cal))


def fit_table(focal_px, short_side_px, heights=(0.6, 0.8, 1.0, 1.2, 1.5, 2.0),
              sides=(0.25, 0.5, 0.75, 1.0, 1.25, 1.5), margin=FIT_MARGIN):
    """Tablas de la ayuda y el manual: [(H, lado máx., lado máx. con margen)] y [(lado, H mín., H mín. con margen)]."""
    k = float(short_side_px) / float(focal_px)
    return ([(h, h * k, h * k * (1.0 - margin)) for h in heights],
            [(s, s / k, s / k / (1.0 - margin)) for s in sides])


def crop_fixed_area(rgb, focal_px, height_m, side_m, center=None):
    """Recorta el cuadrado central de side_m × side_m m. Devuelve (recorte, lado_px). Falla si no cabe."""
    h, w = rgb.shape[:2]
    side = fixed_area_side_px(focal_px, height_m, side_m)
    cx, cy = center if center is not None else (w / 2.0, h / 2.0)
    half = side / 2.0
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    x1, y1 = int(round(cx + half)), int(round(cy + half))
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        raise ValueError("El área de {:g} × {:g} m ({:.0f} px de lado) no cabe en la foto ({} × {} px) desde "
                         "{:g} m: reduzca el lado o aumente la altura.".format(side_m, side_m, side, w, h, height_m))
    return np.asarray(rgb)[y0:y1, x0:x1], side


# ---------------------------------------------------------------- cuadrícula de puntos
def point_grid(shape, n_points=DEFAULT_POINTS, seed=None):
    """Cuadrícula regular de ~n_points puntos (k × k, k = redondeo de √n) con un desfase aleatorio común dentro
    de cada celda. Devuelve (lista de (x, y) en px del área, semilla usada)."""
    h, w = shape[:2]
    k = max(1, int(round(math.sqrt(int(n_points)))))
    if seed is None:
        seed = int(np.random.SeedSequence().entropy % 1_000_000)
    rng = np.random.default_rng(int(seed))
    ox, oy = rng.random(2)
    cw, ch = w / float(k), h / float(k)
    pts = [(min(w - 1.0, (i + ox) * cw), min(h - 1.0, (j + oy) * ch)) for j in range(k) for i in range(k)]
    return pts, int(seed)


def auto_labels(points, green_mask):
    """Clase inicial de cada punto: «verde» si el píxel es verde según la máscara; si no, sin clasificar (None)."""
    out = []
    for x, y in points:
        out.append("verde" if green_mask[int(round(y)), int(round(x))] else None)
    return out


def point_zones(points, only_x, only_c):
    """Zona de cada punto según las diferencias entre las reglas (v0.15.16): «cian» si su píxel es verde solo para
    ExG − ExR, «naranja» si es verde solo para Canopeo, None si las dos reglas coinciden. Son los puntos que conviene
    revisar con más cuidado."""
    out = []
    for x, y in points:
        yi, xi = int(round(y)), int(round(x))
        out.append("cian" if only_x[yi, xi] else ("naranja" if only_c[yi, xi] else None))
    return out


DOUBT_MIN = 0.5               # v0.15.17: puntaje desde el que un verde automático se revisa
DOUBT_WINDOW = 3              # semiancho (px) de la ventana del borde: 7 × 7 px alrededor del punto
DOUBT_REASONS = {"naranja": "verde solo para Canopeo (ExG − ExR no lo ve verde)",
                 "umbral": "su color está cerca de los umbrales de Canopeo",
                 "borde": "está en el borde de una hoja: buena parte de los píxeles vecinos no son verdes"}


def green_doubt(rgb, points, params=CANOPEO_DEFAULT, window=DOUBT_WINDOW):
    """Duda de cada punto verde automático (v0.15.17): None si el punto no es verde según Canopeo; si no, (puntaje 0–1,
    motivos). El puntaje es el mayor de: 1 si ExG − ExR no lo ve verde (zona naranja); cercanía del píxel a los umbrales
    de Canopeo (1 en el umbral, 0 a 0,08 de R/G o B/G o a 15 de 2G − R − B); fracción de píxeles no verdes en una ventana
    de 7 × 7 px (borde de hoja). Un verde con puntaje ≥ DOUBT_MIN conviene revisarlo; los demás son verdes claros."""
    a = np.asarray(rgb, dtype=np.float32)
    green = canopeo_mask(rgb, *params)
    exr = exg_exr_mask(rgb)
    h, w = green.shape
    p1, p2, p3 = params
    out = []
    for x, y in points:
        yi, xi = int(round(y)), int(round(x))
        if not green[yi, xi]:
            out.append(None)
            continue
        r, g, b = (float(v) for v in a[yi, xi])
        gs = max(g, 1.0)
        near = max(1.0 - (p1 - r / gs) / 0.08, 1.0 - (p2 - b / gs) / 0.08, 1.0 - ((2 * g - r - b) - p3) / 15.0)
        near = min(1.0, max(0.0, near))
        win = green[max(0, yi - window):min(h, yi + window + 1), max(0, xi - window):min(w, xi + window + 1)]
        edge = 1.0 - float(win.mean())
        orange = 0.0 if exr[yi, xi] else 1.0
        score = max(orange, near, edge)
        reasons = [k for k, v in (("naranja", orange), ("umbral", near), ("borde", edge)) if v >= DOUBT_MIN]
        out.append((score, reasons))
    return out


def doubtful_order(doubt, min_score=DOUBT_MIN):
    """Índices de los verdes dudosos, del más al menos dudoso."""
    idx = [i for i, d in enumerate(doubt) if d is not None and d[0] >= min_score]
    return sorted(idx, key=lambda i: (-doubt[i][0], i))


ZONE_HELP = {"cian": "verde solo para ExG − ExR: casi siempre un píxel mezcla en el borde entre una hoja verde y material "
                     "seco (también tejido amarillento u hoja en sombra); Canopeo no lo cuenta como verde",
             "naranja": "verde solo para Canopeo: compruebe que sea vegetación (no suelo, piedra o alga verdosa)"}


def wilson_ci(k, n, z=1.96):
    """Intervalo de confianza de Wilson (%) para una proporción k/n."""
    if n <= 0:
        return None, None
    p = k / float(n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100.0 * max(0.0, c - half), 100.0 * min(1.0, c + half)


# ---------------------------------------------------------------- resultado
def summarize(area_rgb, labels, params=(CANOPEO_DEFAULT), classes=None, groups=None):
    """Resultado de una foto: verde por píxeles (Canopeo y ExG − ExR) y % de puntos por clase con IC 95 %.
    classes: [(clave, nombre, color)] (v0.15.7; por defecto las 5 fijas). groups: grupos de clases (v0.15.13): su
    cobertura es la suma de los puntos de sus clases, con el IC de Wilson de esa suma (no la suma de los IC)."""
    classes = list(classes) if classes else class_list()
    groups = groups_for(groups, classes)
    cano = canopeo_mask(area_rgb, *params)
    exr = exg_exr_mask(area_rgb)
    green_c = 100.0 * float(cano.mean())
    green_x = 100.0 * float(exr.mean())
    n = len(labels)
    counts = {}
    for key, _lbl, _col in classes:
        k = sum(1 for lab in labels if lab == key)
        lo, hi = wilson_ci(k, n)
        counts[key] = {"puntos": k, "pct": 100.0 * k / n if n else None, "ic_inf": lo, "ic_sup": hi}
    gres = {}
    for g in groups:
        k = sum(1 for lab in labels if lab in set(g["clases"]))
        lo, hi = wilson_ci(k, n)
        gres[g["nombre"]] = {"puntos": k, "pct": 100.0 * k / n if n else None, "ic_inf": lo, "ic_sup": hi,
                             "clases": list(g["clases"]), "definicion": group_definition(g, classes)}
    pending = sum(1 for lab in labels if lab is None)
    diff = green_c - green_x
    return {
        "grupos": gres, "lista_grupos": groups,
        "verde_canopeo_pct": green_c, "verde_exgexr_pct": green_x, "diferencia_pct": diff,
        "solo_exgexr_pct": 100.0 * float((exr & ~cano).mean()), "solo_canopeo_pct": 100.0 * float((cano & ~exr).mean()),
        "revisar": abs(diff) > AGREEMENT_LIMIT, "n_puntos": n, "sin_clasificar": pending,
        "completo": pending == 0, "clases": counts, "lista_clases": classes,
        "canopeo_p1": float(params[0]), "canopeo_p2": float(params[1]), "canopeo_p3": float(params[2]),
    }


_BASE_COLUMNS = (
    "archivo", "fecha_exif", "latitud", "longitud", "sitio", "analista", "numero_foto", "parcela", "punto",
    "modo_area", "lado_m", "area_m2",
    "altura_camara_m", "calibracion", "regla_verde", "canopeo_p1", "canopeo_p2", "canopeo_p3",
    "verde_canopeo_pct", "verde_exgexr_pct", "diferencia_pct", "solo_exgexr_pct", "solo_canopeo_pct", "revisar",
    "n_puntos", "semilla", "sin_clasificar", "completo", "modo_reglamentario", "esquinas_px",
)


def group_column_key(name):
    return "grupo_" + class_key_for(name)


def csv_columns(classes=None, groups=None):
    """Columnas del CSV por foto: las fijas, 4 por clase (puntos, %, IC 95 %) y 4 por grupo de clases."""
    classes = classes or class_list()
    return _BASE_COLUMNS + tuple("{}_{}".format(c[0], s) for c in classes
                                 for s in ("puntos", "pct", "ic95_inf", "ic95_sup")) + tuple(
        "{}_{}".format(group_column_key(g["nombre"]), s) for g in (groups or [])
        for s in ("puntos", "pct", "ic95_inf", "ic95_sup")) + ("clases_nuevas", "grupos", "plugin", "plugin_version")


CSV_COLUMNS = csv_columns()


def result_row(res, meta):
    """Fila del CSV (en el orden de csv_columns(res["lista_clases"])) a partir del resultado y los metadatos."""
    classes = res.get("lista_clases") or class_list()
    row = dict(meta)
    row.update({k: res.get(k) for k in ("verde_canopeo_pct", "verde_exgexr_pct", "diferencia_pct", "solo_exgexr_pct",
                                        "solo_canopeo_pct", "revisar", "n_puntos", "sin_clasificar", "completo",
                                        "canopeo_p1", "canopeo_p2", "canopeo_p3")})
    row["regla_verde"] = "Canopeo (Patrignani y Ochsner 2015)"
    fixed = {k for k, _l in CLASSES}
    row["clases_nuevas"] = "; ".join(l for k, l, _c in classes if k not in fixed) or None
    for c, _l, _col in classes:
        d = res["clases"][c]
        row["{}_puntos".format(c)] = d["puntos"]
        row["{}_pct".format(c)] = d["pct"]
        row["{}_ic95_inf".format(c)] = d["ic_inf"]
        row["{}_ic95_sup".format(c)] = d["ic_sup"]
    groups = res.get("lista_grupos") or []
    for g in groups:
        d, gk = res["grupos"][g["nombre"]], group_column_key(g["nombre"])
        row[gk + "_puntos"], row[gk + "_pct"] = d["puntos"], d["pct"]
        row[gk + "_ic95_inf"], row[gk + "_ic95_sup"] = d["ic_inf"], d["ic_sup"]
    row["grupos"] = "; ".join(res["grupos"][g["nombre"]]["definicion"] for g in groups) or None
    return [row.get(k) for k in csv_columns(classes, groups)]


# v0.16.3: descripciones en español de las variables del CSV de foto (que desde 0.16.3 se escribe transpuesto)
GROUND_DESCRIPTIONS = {
    "archivo": "Archivo de la foto", "fecha_exif": "Fecha y hora de captura (EXIF)",
    "latitud": "Latitud del EXIF (grados, WGS84)", "longitud": "Longitud del EXIF (grados, WGS84)",
    "sitio": "Sitio", "analista": "Analista", "numero_foto": "Número de la foto en el procesamiento por sitio",
    "parcela": "Parcela (del formulario de fotos)", "punto": "Punto de la parcela (del formulario de fotos)",
    "modo_area": "Modo del área analizada (cuadro, área fija o foto entera)", "lado_m": "Lado del área (m)",
    "area_m2": "Área analizada (m²)", "altura_camara_m": "Altura de la cámara (m)", "calibracion": "Calibración de la cámara",
    "regla_verde": "Regla de vegetación verde", "canopeo_p1": "Canopeo: umbral R/G", "canopeo_p2": "Canopeo: umbral B/G",
    "canopeo_p3": "Canopeo: umbral 2G − R − B", "verde_canopeo_pct": "Vegetación verde por píxeles, Canopeo (%)",
    "verde_exgexr_pct": "Vegetación verde por píxeles, ExG − ExR (%; comprobación interna)",
    "diferencia_pct": "Diferencia entre las dos reglas (puntos porcentuales)",
    "solo_exgexr_pct": "Píxeles verdes solo para ExG − ExR (%; zona cian: borde entre hoja verde y material seco)",
    "solo_canopeo_pct": "Píxeles verdes solo para Canopeo (%; zona naranja)",
    "revisar": "A revisar: las dos reglas difieren más de 5 puntos (Sí/No)", "n_puntos": "Número de puntos de la cuadrícula",
    "semilla": "Semilla de la cuadrícula", "sin_clasificar": "Puntos sin clasificar",
    "completo": "Clasificación completa (Sí/No)", "modo_reglamentario": "Modo reglamentario (Sí/No)",
    "esquinas_px": "Esquinas del cuadro en la foto (px)", "clases_nuevas": "Clases añadidas por el analista",
    "grupos": "Grupos de clases (definición)", "plugin": "Complemento", "plugin_version": "Versión del complemento",
}
_SUFFIX_ES = {"puntos": "puntos", "pct": "cobertura (%)", "ic95_inf": "IC 95 % de Wilson, límite inferior (%)",
              "ic95_sup": "IC 95 % de Wilson, límite superior (%)"}


def describe_column(key, classes=None, groups=None):
    """Descripción en español de una columna del CSV de foto; para clases y grupos usa su nombre."""
    if key in GROUND_DESCRIPTIONS:
        return GROUND_DESCRIPTIONS[key]
    names = {k: l for k, l, _c in (classes or class_list())}
    for g in (groups or []):
        names[group_column_key(g["nombre"])] = "grupo «{}»".format(g["nombre"])
    for suf, text in _SUFFIX_ES.items():
        if key.endswith("_" + suf):
            base = key[:-len(suf) - 1]
            if base in names:
                return "{}: {}".format(names[base] if base.startswith("grupo_") else "Clase «{}»".format(names[base]), text)
    return key


def corners_text(corners):
    """Esquinas del cuadro como texto para el CSV: «x y | x y | x y | x y» (px de la foto, punto decimal)."""
    return " | ".join("{:.1f} {:.1f}".format(float(x), float(y)) for x, y in corners) if corners else None


def parse_corners(text):
    """Inverso de corners_text. Devuelve [(x, y)] o [] si el texto no tiene 4 esquinas."""
    try:
        pts = [tuple(float(v) for v in part.split()) for part in str(text or "").split("|") if part.strip()]
    except ValueError:
        return []
    return pts if len(pts) == 4 and all(len(p) == 2 for p in pts) else []


PHOTO_CSV_HEADER = ("variable", "descripcion", "valor")     # v0.16.3: CSV de foto transpuesto


def read_photo_csv(path):
    """Lee CobDosel_suelo_<foto>.csv («,» o «;», coma o punto decimal), en el formato transpuesto (desde 0.16.3: una fila
    por variable) o en el ancho anterior (una fila por foto). Devuelve {columna: valor (texto)}."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r]
    if rows and [c.strip() for c in rows[0][:3]] == list(PHOTO_CSV_HEADER):
        row = {r[0]: (r[2] if len(r) > 2 else "") for r in rows[1:]}
    elif len(rows) >= 2:
        row = dict(zip(rows[0], rows[1]))
    else:
        row = {}
    if "semilla" not in row or "modo_area" not in row:
        raise ValueError("«{}» no es un CSV de foto de «Cobertura del suelo» de CobDosel.".format(os.path.basename(path)))
    return row


def write_csvs(res, meta, points, labels, auto, out_prefix, version="", delimiter=",", decimal=".", zones=None,
               doubt=None):
    """<prefijo>.csv (una fila por foto) y <prefijo>_puntos.csv (un punto por fila). Devuelve las rutas."""
    from .csv_format import csv_row, NO_DATA
    meta = dict(meta, plugin="CobDosel", plugin_version=version)
    for k in ("fecha_exif", "latitud", "longitud"):        # dato faltante del EXIF: «Sin datos»
        if meta.get(k) in (None, ""):
            meta[k] = NO_DATA
    p1 = out_prefix + ".csv"
    classes, groups = res.get("lista_clases"), res.get("lista_grupos")
    with open(p1, "w", newline="", encoding="utf-8-sig") as f:        # v0.16.3: transpuesto, una fila por variable
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(PHOTO_CSV_HEADER)
        for k, v in zip(csv_columns(classes, groups), csv_row(result_row(res, meta), decimal)):
            w.writerow((k, describe_column(k, classes, groups), v))
    names = {k: l for k, l, _c in (res.get("lista_clases") or class_list())}
    p2 = out_prefix + "_puntos.csv"
    with open(p2, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(("archivo", "punto", "x_px", "y_px", "clase", "clase_automatica", "corregido", "zona_reglas",
                    "duda_verde"))
        zones = list(zones) if zones else [None] * len(points)
        doubt = list(doubt) if doubt else [None] * len(points)
        for i, ((x, y), lab, a, z, dd) in enumerate(zip(points, labels, auto, zones, doubt), 1):
            w.writerow(csv_row([meta.get("archivo"), i, round(x, 1), round(y, 1),
                                names.get(lab, lab) if lab else "Sin clasificar",
                                names.get(a, a) if a else None, lab != a, z,
                                round(dd[0], 2) if dd else None], decimal))
    return [p1, p2]


def overlay_image(area_rgb, labels, points, max_px=900, green=None, colors=None, only_x=None, only_c=None):
    """Imagen del área con la vegetación verde (Canopeo) sombreada, las diferencias entre las reglas (opcional) y
    los puntos por clase (PIL.Image). colors: {clave: (r, g, b)} (v0.15.7: incluye las clases nuevas)."""
    from PIL import Image, ImageDraw
    colors = dict(CLASS_COLORS, **(colors or {}))
    a = shade(area_rgb, green, only_x, only_c)
    im = Image.fromarray(a)
    s = min(1.0, float(max_px) / max(im.size))
    if s < 1.0:
        im = im.resize((int(im.size[0] * s), int(im.size[1] * s)))
    d = ImageDraw.Draw(im)
    rad = max(4, int(min(im.size) / 90))
    for (x, y), lab in zip(points, labels):
        cx, cy = x * s, y * s
        col = colors.get(lab, (255, 255, 255))
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(0, 0, 0), width=2, fill=col)
    return im


def write_html(res, meta, area_rgb, points, labels, path, version=""):
    """Informe HTML autocontenido de una foto."""
    from ._version import fmt_num
    classes = res.get("lista_clases") or class_list()
    colors = {k: c for k, _l, c in classes}
    prm3 = (res["canopeo_p1"], res["canopeo_p2"], res["canopeo_p3"])
    im = overlay_image(area_rgb, labels, points, green=canopeo_mask(area_rgb, *prm3), colors=colors)
    buf = io.BytesIO(); im.save(buf, format="PNG")
    img64 = base64.b64encode(buf.getvalue()).decode("ascii")
    # v0.15.16 (opción A): ExG − ExR es una comprobación interna; el informe lo muestra solo cuando hay «a revisar»,
    # con la imagen de dónde difieren las reglas y los puntos que caen allí
    f0 = lambda v, d=2: "—" if v is None else fmt_num(v, d)
    diffsec = ""
    if res["revisar"]:
        ox, oc = disagreement_masks(area_rgb, prm3)
        both = canopeo_mask(area_rgb, *prm3) & ~oc
        im2 = overlay_image(area_rgb, [], [], green=both, only_x=ox, only_c=oc)
        buf2 = io.BytesIO(); im2.save(buf2, format="PNG")
        img2 = base64.b64encode(buf2.getvalue()).decode("ascii")
        zs = point_zones(points, ox, oc) if points else []
        nz_x, nz_c = zs.count("cian"), zs.count("naranja")
        diffsec = ("<section><h2>Dónde difieren Canopeo y ExG − ExR</h2><img alt=\"Diferencias entre las reglas\" "
                   "src=\"data:image/png;base64,{img}\"><p class=\"note\">Magenta: verde para las dos reglas. <b>Cian</b>: "
                   "verde solo para ExG − ExR ({ox} % del área). <b>Naranja</b>: verde solo para Canopeo ({oc} % del área). "
                   "Puntos de la cuadrícula en esas zonas: {nx} en cian y {nc} en naranja (columna zona_reglas del CSV de "
                   "puntos); son los que conviene revisar.</p></section>").format(
            img=img2, ox=f0(res.get("solo_exgexr_pct")), oc=f0(res.get("solo_canopeo_pct")), nx=nz_x, nc=nz_c)
        check = ""
    else:
        check = ("<p class=\"note\">Comprobación con ExG − ExR (Meyer y Neto 2008): las dos reglas coinciden dentro de "
                 "{:.0f} puntos.</p>".format(AGREEMENT_LIMIT))
    f = lambda v, d=2: "—" if v is None else fmt_num(v, d)
    rows = "".join(
        "<tr><td><span class='sw' style='background:rgb{}'></span> {}</td><td class='n'>{}</td><td class='n'>{} %</td>"
        "<td class='n'>{} – {} %</td></tr>".format(
            tuple(col), _h.escape(lbl), res["clases"][c]["puntos"], f(res["clases"][c]["pct"], 1),
            f(res["clases"][c]["ic_inf"], 1), f(res["clases"][c]["ic_sup"], 1))
        for c, lbl, col in classes)
    dd = green_doubt(area_rgb, points, prm3) if points else []
    n_auto = sum(1 for x in dd if x is not None)
    dudosos = ("Verdes automáticos dudosos (revisados por el analista): {} de {} (puntaje ≥ {:g}: zona naranja, color cerca "
               "de los umbrales de Canopeo o borde de hoja).".format(len(doubtful_order(dd)), n_auto, DOUBT_MIN)
               if n_auto else "")
    groups_html = ""
    if res.get("lista_grupos"):
        grows = "".join("<tr><td>{}</td><td>{}</td><td class='n'>{}</td><td class='n'>{} %</td><td class='n'>{} – {} %"
                        "</td></tr>".format(_h.escape(g["nombre"]), _h.escape(res["grupos"][g["nombre"]]["definicion"]
                                                                             .split(" = ", 1)[1]),
                                           res["grupos"][g["nombre"]]["puntos"], f(res["grupos"][g["nombre"]]["pct"], 1),
                                           f(res["grupos"][g["nombre"]]["ic_inf"], 1),
                                           f(res["grupos"][g["nombre"]]["ic_sup"], 1))
                        for g in res["lista_grupos"])
        groups_html = ("<section><h2>Grupos de clases</h2><table><tr><th>Grupo</th><th>Clases</th><th class='n'>Puntos"
                       "</th><th class='n'>Cobertura</th><th class='n'>IC 95 % (Wilson)</th></tr>{}</table><p class='note'>"
                       "Cobertura del grupo = puntos de sus clases / {} puntos; el intervalo es el de Wilson para esa "
                       "suma (no la suma de los intervalos de las clases).</p></section>").format(grows, res["n_puntos"])
    warn = []
    if res["revisar"]:
        warn.append(agreement_note(res, where="informe"))
    if res["sin_clasificar"]:
        warn.append("Resultado provisional: {} de {} puntos sin clasificar.".format(res["sin_clasificar"],
                                                                                   res["n_puntos"]))
    warn_html = "".join("<p class='warn'>{}</p>".format(_h.escape(w)) for w in warn)
    params = [
        ("Archivo", meta.get("archivo")), ("Fecha (EXIF)", meta.get("fecha_exif") or "Sin datos"),
        ("Coordenadas GNSS (WGS84)", "{}, {}".format(meta["latitud"], meta["longitud"])
         if meta.get("latitud") is not None else "Sin datos"),
        ("Área de muestreo", "{} de {} × {} m ({} m²)".format(meta.get("modo_area"), f(meta.get("lado_m")),
                                                              f(meta.get("lado_m")), f(meta.get("area_m2")))),
        ("Altura de la cámara", f(meta.get("altura_camara_m")) + " m" if meta.get("altura_camara_m") else "No aplica"),
        ("Calibración", meta.get("calibracion") or "No aplica"),
        ("Regla de la vegetación verde", "Canopeo (Patrignani y Ochsner 2015): R/G < {}, B/G < {}, 2G − R − B > {}"
         .format(f(res["canopeo_p1"]), f(res["canopeo_p2"]), f(res["canopeo_p3"], 0))),
        ("Cuadrícula de puntos", "{} puntos, desfase aleatorio con semilla {}".format(res["n_puntos"],
                                                                                    meta.get("semilla"))),
        ("Modo reglamentario", "Sí: el verde lo decide la regla de Canopeo; el analista no lo cambia"
         if meta.get("modo_reglamentario") == "Sí" else "No"),
    ]
    prm = "".join("<tr><td>{}</td><td>{}</td></tr>".format(_h.escape(k), _h.escape(str(v))) for k, v in params)
    head = " · ".join(x for x in ("Sitio: " + _h.escape(meta.get("sitio") or "—"),
                                  ("Analista: " + _h.escape(meta["analista"])) if meta.get("analista") else "") if x)
    page = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>CobDosel — Cobertura del suelo</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1f2933;margin:0;padding:16px}}
.c{{max-width:1000px;margin:0 auto}} header{{background:#3d5a1e;color:#fff;padding:18px 24px;border-radius:10px}}
section{{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:16px 20px;margin-top:16px}}
.big{{font-size:2.2rem;font-weight:800}} table{{width:100%;border-collapse:collapse;font-size:.92rem}}
th,td{{padding:6px 8px;border-bottom:1px solid #e4e7eb;text-align:left}} th{{background:#f0f4f8}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} .warn{{color:#9a3412;font-weight:700}}
.sw{{display:inline-block;width:12px;height:12px;border:1px solid #333;border-radius:6px;vertical-align:middle}}
img{{max-width:100%;border-radius:6px}} .note{{font-size:.84rem;color:#52606d}}
</style></head><body><div class="c">
<header><h1>CobDosel v{version} — Cobertura del suelo</h1><div>{head}</div></header>
<section><div>Vegetación verde (píxeles, regla de Canopeo; Patrignani y Ochsner 2015)</div><div class="big">{green} %</div>
{check}{warn}</section>
<section><h2>Cobertura por clase (intercepción de puntos)</h2><table>
<tr><th>Clase</th><th class='n'>Puntos</th><th class='n'>Cobertura</th><th class='n'>IC 95 % (Wilson)</th></tr>{rows}</table>
<p class="note">Cobertura de cada clase = puntos de la clase / {n} puntos. Los puntos verdes según Canopeo se marcan
solos; el analista clasifica los demás y puede corregir cualquiera. {dudosos} La vegetación verde por píxeles usa toda el área;
por puntos, solo los {n} puntos.</p></section>{groups}
<section><h2>Área analizada</h2><img alt="Área analizada" src="data:image/png;base64,{img}">
<p class="note">Magenta: vegetación verde según Canopeo. Círculos: puntos de la cuadrícula, con el color de su clase
(blanco: sin clasificar).</p></section>
{diffsec}<section><h2>Parámetros</h2><table>{prm}</table></section>
<footer style="text-align:center;color:#52606d;margin-top:16px">Vegetación verde: Patrignani y Ochsner (2015); comprobación:
Meyer y Neto (2008).<br/><strong>CobDosel v{version}</strong> para QGIS · Autor: Jorge Fallas · Contacto:
<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer></div></body></html>""".format(
        version=version, head=head, green=f(res["verde_canopeo_pct"]), check=check, diffsec=diffsec, warn=warn_html, rows=rows, n=res["n_puntos"], img=img64, prm=prm, groups=groups_html, dudosos=_h.escape(dudosos))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
