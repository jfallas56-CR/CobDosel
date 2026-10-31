"""Cobertura del suelo con fotos verticales hacia abajo (CobDosel, v0.15.0). Sin Qt ni QGIS.

Herramienta general (no supone un diseño de muestreo):
- Área de muestreo: un cuadro físico en la foto (se marcan sus 4 esquinas y se endereza a un cuadrado de tamaño
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
import math

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
CANOPEO_DEFAULT = (0.95, 0.95, 20.0)
AGREEMENT_LIMIT = 5.0          # puntos de diferencia Canopeo − ExG−ExR que dejan la foto «a revisar»
DEFAULT_POINTS = 100
QUADRAT_PX = 1000              # lado del cuadro enderezado (px)


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
def summarize(area_rgb, labels, params=(CANOPEO_DEFAULT)):
    """Resultado de una foto: verde por píxeles (Canopeo y ExG − ExR) y % de puntos por clase con IC 95 %."""
    cano = canopeo_mask(area_rgb, *params)
    exr = exg_exr_mask(area_rgb)
    green_c = 100.0 * float(cano.mean())
    green_x = 100.0 * float(exr.mean())
    n = len(labels)
    classes = {}
    for key, _lbl in CLASSES:
        k = sum(1 for lab in labels if lab == key)
        lo, hi = wilson_ci(k, n)
        classes[key] = {"puntos": k, "pct": 100.0 * k / n if n else None, "ic_inf": lo, "ic_sup": hi}
    pending = sum(1 for lab in labels if lab is None)
    diff = green_c - green_x
    return {
        "verde_canopeo_pct": green_c, "verde_exgexr_pct": green_x, "diferencia_pct": diff,
        "revisar": abs(diff) > AGREEMENT_LIMIT, "n_puntos": n, "sin_clasificar": pending,
        "completo": pending == 0, "clases": classes,
        "canopeo_p1": float(params[0]), "canopeo_p2": float(params[1]), "canopeo_p3": float(params[2]),
    }


CSV_COLUMNS = (
    "archivo", "fecha_exif", "latitud", "longitud", "sitio", "analista", "modo_area", "lado_m", "area_m2",
    "altura_camara_m", "calibracion", "regla_verde", "canopeo_p1", "canopeo_p2", "canopeo_p3",
    "verde_canopeo_pct", "verde_exgexr_pct", "diferencia_pct", "revisar", "n_puntos", "semilla", "sin_clasificar",
    "completo",
) + tuple("{}_{}".format(c, s) for c, _l in CLASSES for s in ("puntos", "pct", "ic95_inf", "ic95_sup")) + (
    "plugin", "plugin_version")


def result_row(res, meta):
    """Fila del CSV (en el orden de CSV_COLUMNS) a partir del resultado y los metadatos de la foto."""
    row = dict(meta)
    row.update({k: res[k] for k in ("verde_canopeo_pct", "verde_exgexr_pct", "diferencia_pct", "revisar",
                                    "n_puntos", "sin_clasificar", "completo", "canopeo_p1", "canopeo_p2",
                                    "canopeo_p3")})
    row["regla_verde"] = "Canopeo (Patrignani y Ochsner 2015)"
    for c, _l in CLASSES:
        d = res["clases"][c]
        row["{}_puntos".format(c)] = d["puntos"]
        row["{}_pct".format(c)] = d["pct"]
        row["{}_ic95_inf".format(c)] = d["ic_inf"]
        row["{}_ic95_sup".format(c)] = d["ic_sup"]
    return [row.get(k) for k in CSV_COLUMNS]


def write_csvs(res, meta, points, labels, auto, out_prefix, version="", delimiter=",", decimal="."):
    """<prefijo>.csv (una fila por foto) y <prefijo>_puntos.csv (un punto por fila). Devuelve las rutas."""
    from .csv_format import csv_row, NO_DATA
    meta = dict(meta, plugin="CobDosel", plugin_version=version)
    for k in ("fecha_exif", "latitud", "longitud"):        # dato faltante del EXIF: «Sin datos»
        if meta.get(k) in (None, ""):
            meta[k] = NO_DATA
    p1 = out_prefix + ".csv"
    with open(p1, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(CSV_COLUMNS)
        w.writerow(csv_row(result_row(res, meta), decimal))
    p2 = out_prefix + "_puntos.csv"
    with open(p2, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(("archivo", "punto", "x_px", "y_px", "clase", "clase_automatica", "corregido"))
        for i, ((x, y), lab, a) in enumerate(zip(points, labels, auto), 1):
            w.writerow(csv_row([meta.get("archivo"), i, round(x, 1), round(y, 1),
                                CLASS_LABELS.get(lab, "Sin clasificar") if lab else "Sin clasificar",
                                CLASS_LABELS.get(a) if a else None, lab != a], decimal))
    return [p1, p2]


def overlay_image(area_rgb, labels, points, max_px=900, green=None):
    """Imagen del área con la vegetación verde (Canopeo) sombreada y los puntos por clase (PIL.Image)."""
    from PIL import Image, ImageDraw
    a = np.asarray(area_rgb, dtype=np.uint8).copy()
    if green is not None:
        a[green] = (0.55 * a[green] + 0.45 * np.array([255, 0, 255])).astype(np.uint8)
    im = Image.fromarray(a)
    s = min(1.0, float(max_px) / max(im.size))
    if s < 1.0:
        im = im.resize((int(im.size[0] * s), int(im.size[1] * s)))
    d = ImageDraw.Draw(im)
    rad = max(4, int(min(im.size) / 90))
    for (x, y), lab in zip(points, labels):
        cx, cy = x * s, y * s
        col = CLASS_COLORS.get(lab, (255, 255, 255))
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(0, 0, 0), width=2, fill=col)
    return im


def write_html(res, meta, area_rgb, points, labels, path, version=""):
    """Informe HTML autocontenido de una foto."""
    from ._version import fmt_num
    im = overlay_image(area_rgb, labels, points, green=canopeo_mask(area_rgb, res["canopeo_p1"],
                                                                    res["canopeo_p2"], res["canopeo_p3"]))
    buf = io.BytesIO(); im.save(buf, format="PNG")
    img64 = base64.b64encode(buf.getvalue()).decode("ascii")
    f = lambda v, d=2: "—" if v is None else fmt_num(v, d)
    rows = "".join(
        "<tr><td><span class='sw' style='background:rgb{}'></span> {}</td><td class='n'>{}</td><td class='n'>{} %</td>"
        "<td class='n'>{} – {} %</td></tr>".format(
            CLASS_COLORS[c], _h.escape(lbl), res["clases"][c]["puntos"], f(res["clases"][c]["pct"], 1),
            f(res["clases"][c]["ic_inf"], 1), f(res["clases"][c]["ic_sup"], 1))
        for c, lbl in CLASSES)
    warn = []
    if res["revisar"]:
        warn.append("Canopeo y ExG − ExR difieren {} puntos (más de {:.0f}): revise la foto (sombras, luz directa, "
                    "colores del suelo).".format(f(abs(res["diferencia_pct"]), 1), AGREEMENT_LIMIT))
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
<section><div>Vegetación verde (píxeles, regla de Canopeo)</div><div class="big">{green} %</div>
<p>ExG − ExR (comprobación): {gx} % · diferencia {diff} puntos</p>{warn}</section>
<section><h2>Cobertura por clase (intercepción de puntos)</h2><table>
<tr><th>Clase</th><th class='n'>Puntos</th><th class='n'>Cobertura</th><th class='n'>IC 95 % (Wilson)</th></tr>{rows}</table>
<p class="note">Cobertura de cada clase = puntos de la clase / {n} puntos. Los puntos verdes según Canopeo se marcan
solos; el analista clasifica los demás y puede corregir cualquiera. La vegetación verde por píxeles usa toda el área;
por puntos, solo los {n} puntos.</p></section>
<section><h2>Área analizada</h2><img alt="Área analizada" src="data:image/png;base64,{img}">
<p class="note">Magenta: vegetación verde según Canopeo. Círculos: puntos de la cuadrícula, con el color de su clase
(blanco: sin clasificar).</p></section>
<section><h2>Parámetros</h2><table>{prm}</table></section>
<footer style="text-align:center;color:#52606d;margin-top:16px">Vegetación verde: Patrignani y Ochsner (2015); comprobación:
Meyer y Neto (2008).<br/><strong>CobDosel v{version}</strong> para QGIS · Autor: Jorge Fallas · Contacto:
<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer></div></body></html>""".format(
        version=version, head=head, green=f(res["verde_canopeo_pct"]), gx=f(res["verde_exgexr_pct"]),
        diff=f(res["diferencia_pct"]), warn=warn_html, rows=rows, n=res["n_puntos"], img=img64, prm=prm)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
