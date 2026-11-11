"""Cobertura del suelo: procesamiento por sitio (CobDosel 0.16.0). Sin Qt ni QGIS.

Una carpeta de fotos de un sitio se clasifica foto por foto con los mismos parámetros (modo de área, puntos, clases,
grupos, modo reglamentario). Cada foto guarda sus CSV e informe como en la herramienta de una foto; la semilla de la
cuadrícula de cada foto es la semilla base + el número de la foto en la lista (fija de antemano y reproducible). Con un
formulario de fotos (el mismo del procesamiento por sitio del dosel) cada foto lleva su parcela y su punto.

El resumen del sitio lee los CSV de foto y calcula, para la vegetación verde por píxeles (Canopeo), cada clase y cada
grupo de clases, la media y el intervalo de 95 % con la t de Student: media ± t(0,975; n − 1) · s / √n, con las fotos
o con las medias de las parcelas como unidades. Solo entran las fotos completas (sin puntos sin clasificar).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import csv
import html as _h
import math
import os

from . import batch_core as bc
from . import ground_cover as gc

PREFIX = "CobDosel_suelo_"


# ---------------------------------------------------------------- t de Student sin scipy
def _norm_ppf(p):
    """Cuantil de la normal estándar (Acklam; error relativo < 1,2e-9)."""
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > hi:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _t_two_sided(t, df):
    """A(t|ν) = P(|T| < t) para ν entero, con las series finitas de Abramowitz y Stegun (1964, 26.7.3–26.7.4)."""
    th = math.atan(t / math.sqrt(df))
    c2, sn, cs = math.cos(th) ** 2, math.sin(th), math.cos(th)
    if df % 2:                                   # ν impar
        if df == 1:
            return 2 * th / math.pi
        term, acc = cs, cs
        for k in range(3, df - 1, 2):            # cos θ + 2/3 cos³θ + … + (2·4…(ν−3))/(1·3…(ν−2)) cos^(ν−2) θ
            term *= c2 * (k - 1) / k
            acc += term
        return 2 / math.pi * (th + sn * acc)
    term, acc = 1.0, 1.0                         # ν par: 1 + 1/2 cos²θ + 1·3/(2·4) cos⁴θ + …
    for k in range(2, df - 1, 2):
        term *= c2 * (k - 1) / k
        acc += term
    return sn * acc


def t_quantile(p, df):
    """Cuantil p (> 0,5) de la t de Student con df grados de libertad enteros: bisección sobre la distribución exacta
    (series de Abramowitz y Stegun 26.7.3–26.7.4), sin scipy; error < 1e-9."""
    df = int(df)
    if df < 1:
        raise ValueError("Se necesitan al menos 2 unidades para el intervalo.")
    if df == 1:
        return math.tan(math.pi * (p - 0.5))
    target = 2 * p - 1                            # P(|T| < t)
    lo, hi = 0.0, max(1.0, _norm_ppf(p))
    while _t_two_sided(hi, df) < target:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if _t_two_sided(mid, df) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-11:
            break
    return (lo + hi) / 2


def mean_ci(values, conf=0.95):
    """(n, media, desviación estándar, error estándar, t, IC inferior, IC superior) de una lista de valores."""
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if not n:
        return n, None, None, None, None, None, None
    m = sum(vals) / n
    if n < 2:
        return n, m, None, None, None, None, None
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    se = sd / math.sqrt(n)
    t = t_quantile(0.5 + conf / 2.0, n - 1)
    return n, m, sd, se, t, m - t * se, m + t * se


# ---------------------------------------------------------------- lista de fotos del sitio
def site_photos(folder, form_path=None):
    """Fotos del sitio en orden: [{ruta, nombre, numero, parcela, punto}] y avisos. Con formulario, en el orden del
    formulario (emparejadas por ID o por hora, como en el dosel); las filas con calidad que excluye se omiten. Sin
    formulario, todas las fotos de la carpeta por nombre."""
    photos = bc.scan_photos(folder)
    warnings = []
    out = []
    if form_path:
        rows, w1 = bc.read_field_form(form_path)
        pairs, w2 = bc.match_photos(rows, photos)
        warnings += list(w1) + list(w2)
        for r, ph, _how, _d in pairs:
            if ph is None:
                continue
            if bc.quality_excludes(r.get("calidad")):
                warnings.append("Foto {} excluida por el formulario (calidad «{}»).".format(ph["nombre"], r.get("calidad")))
                continue
            out.append({"ruta": ph["ruta"], "nombre": ph["nombre"], "parcela": str(r.get("parcela") or "").strip() or None,
                        "punto": str(r.get("punto_norm") or r.get("punto") or "").strip() or None})
    else:
        out = [{"ruta": ph["ruta"], "nombre": ph["nombre"], "parcela": None, "punto": None} for ph in photos]
    for i, p in enumerate(out, 1):
        p["numero"] = i
    if not out:
        warnings.append("No hay fotos para procesar.")
    return out, warnings


def photo_seed(base_seed, numero):
    """Semilla de la foto n.º numero: semilla base + número (fija de antemano; cualquiera puede repetir la cuadrícula)."""
    return int(base_seed) + int(numero)


def output_prefix(out_dir, photo_name):
    return os.path.join(out_dir, PREFIX + os.path.splitext(os.path.basename(photo_name))[0])


def photo_status(out_dir, photo_name):
    """«pendiente» (sin CSV), «incompleta» (puntos sin clasificar) o «completa»."""
    p = output_prefix(out_dir, photo_name) + ".csv"
    if not os.path.isfile(p):
        return "pendiente"
    try:
        r = gc.read_photo_csv(p)
        n = int(round(float(str(r.get("sin_clasificar") or "0").replace(",", "."))))
    except (ValueError, OSError):
        return "incompleta"
    return "completa" if n == 0 else "incompleta"


# ---------------------------------------------------------------- resumen del sitio
def _num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def site_records(photos, out_dir):
    """Lee los CSV de foto del sitio. Devuelve (registros de fotos completas, lista de variables, avisos). Cada
    variable: (columna del CSV, nombre). Las variables son la vegetación verde por píxeles (Canopeo), cada clase y cada
    grupo presentes en las fotos (en el orden en que aparecen)."""
    recs, warnings = [], []
    variables = [("verde_canopeo_pct", "Vegetación verde por píxeles (Canopeo)")]
    seen = {v[0] for v in variables}
    for ph in photos:
        st = photo_status(out_dir, ph["nombre"])
        if st != "completa":
            warnings.append("Foto {} {}: no entra en el resumen.".format(ph["nombre"], st))
            continue
        r = gc.read_photo_csv(output_prefix(out_dir, ph["nombre"]) + ".csv")
        names = {}
        for k in r:
            if k.endswith("_pct") and k not in ("verde_canopeo_pct", "verde_exgexr_pct", "diferencia_pct",
                                                "solo_exgexr_pct", "solo_canopeo_pct"):
                names[k] = k
        groups_def = r.get("grupos") or ""
        for k in names:
            if k not in seen:
                seen.add(k)
                variables.append((k, _var_name(k, groups_def)))
        recs.append({"archivo": ph["nombre"], "numero": ph["numero"], "parcela": ph.get("parcela"),
                     "punto": ph.get("punto"), "valores": {k: _num(v) for k, v in r.items()},
                     "revisar": (r.get("revisar") or "").strip(), "semilla": r.get("semilla")})
    return recs, variables, warnings


def _var_name(col, groups_def):
    base = col[:-len("_pct")]
    if base.startswith("grupo_"):
        key = base[len("grupo_"):]
        for part in groups_def.split(";"):
            name = part.split("=")[0].strip()
            if name and gc.class_key_for(name) == key:
                return "Grupo: " + name
        return "Grupo: " + key.replace("_", " ")
    names = dict((k, l) for k, l, _c in gc.class_list(gc.load_custom_classes()))
    return names.get(base, base.replace("_", " ").capitalize())


def summarize_site(recs, variables, unit="foto"):
    """Resumen por variable. unit «foto»: las fotos son las unidades; «parcela»: las medias de las parcelas."""
    out, plots = [], {}
    if unit == "parcela":
        for r in recs:
            plots.setdefault(r["parcela"] or "(sin parcela)", []).append(r)
    for col, name in variables:
        if unit == "parcela":
            units = [sum(x["valores"].get(col) or 0.0 for x in rs) / len(rs) for rs in plots.values()]
        else:
            units = [r["valores"].get(col) if r["valores"].get(col) is not None else 0.0 for r in recs]
        n, m, sd, se, t, lo, hi = mean_ci(units)
        if lo is not None:
            lo = max(0.0, lo); hi = min(100.0, hi)
        out.append({"columna": col, "variable": name, "unidad": unit, "n": n, "media": m, "de": sd, "ee": se,
                    "t": t, "ic_inf": lo, "ic_sup": hi})
    plot_rows = []
    if unit == "parcela":
        for p, rs in plots.items():
            plot_rows.append({"parcela": p, "n_fotos": len(rs),
                              "medias": {col: sum(x["valores"].get(col) or 0.0 for x in rs) / len(rs)
                                         for col, _n in variables}})
    return out, plot_rows


def write_site(recs, variables, summary, plot_rows, out_dir, site="", unit="foto", version="", delimiter=",",
               decimal=".", warnings=()):
    """CobDosel_suelo_sitio_<sitio>.csv (resumen), _fotos.csv y, con parcelas, _parcelas.csv; e informe HTML."""
    from .csv_format import csv_row
    tag = gc.class_key_for(site or "sitio")
    base = os.path.join(out_dir, PREFIX + "sitio_" + tag)
    paths = []
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(("sitio", "variable", "columna", "unidad", "n", "media_pct", "de", "ee", "t", "ic95_inf", "ic95_sup",
                    "plugin_version"))
        for s in summary:
            w.writerow(csv_row([site, s["variable"], s["columna"], s["unidad"], s["n"], s["media"], s["de"], s["ee"],
                                s["t"], s["ic_inf"], s["ic_sup"], version], decimal))
    paths.append(base + ".csv")
    with open(base + "_fotos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(("numero", "archivo", "parcela", "punto", "semilla", "revisar") + tuple(c for c, _n in variables))
        for r in recs:
            w.writerow(csv_row([r["numero"], r["archivo"], r["parcela"], r["punto"], r["semilla"], r["revisar"]]
                               + [r["valores"].get(c) for c, _n in variables], decimal))
    paths.append(base + "_fotos.csv")
    if plot_rows:
        with open(base + "_parcelas.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=delimiter)
            w.writerow(("parcela", "n_fotos") + tuple(c for c, _n in variables))
            for p in plot_rows:
                w.writerow(csv_row([p["parcela"], p["n_fotos"]] + [p["medias"][c] for c, _n in variables], decimal))
        paths.append(base + "_parcelas.csv")
    paths.append(write_site_html(summary, recs, plot_rows, base + "_informe.html", site, unit, version, warnings))
    return paths


def write_site_html(summary, recs, plot_rows, path, site="", unit="foto", version="", warnings=()):
    e = _h.escape
    f = lambda v, d=2: "—" if v is None else "{:.{d}f}".format(v, d=d)
    rows = "".join("<tr><td>{}</td><td class='n'>{}</td><td class='n'>{} %</td><td class='n'>{}</td>"
                   "<td class='n'>{} – {} %</td></tr>".format(e(s["variable"]), s["n"], f(s["media"]), f(s["de"]),
                                                               f(s["ic_inf"]), f(s["ic_sup"])) for s in summary)
    unidad = ("las medias de las parcelas ({} parcelas)".format(len(plot_rows)) if unit == "parcela"
              else "las fotos ({} fotos completas)".format(len(recs)))
    warn = "".join("<li>{}</li>".format(e(w)) for w in warnings)
    nrev = sum(1 for r in recs if r["revisar"] in ("Sí", "True", "1"))
    page = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>CobDosel — Cobertura del suelo del sitio</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1f2933;margin:0;padding:16px}}
.c{{max-width:1000px;margin:0 auto}} header{{background:#3d5a1e;color:#fff;padding:18px 24px;border-radius:10px}}
section{{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:16px 20px;margin-top:16px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:.92rem}} th,td{{padding:6px 8px;border-bottom:1px solid #e4e7eb;text-align:left}}
th{{background:#f0f4f8}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} .note{{font-size:.84rem;color:#52606d}}
</style></head><body><div class="c">
<header><h1>CobDosel v{version} — Cobertura del suelo del sitio</h1><div>Sitio: {site}</div></header>
<section><h2>Resultado del sitio</h2><table><tr><th>Variable</th><th class='n'>n</th><th class='n'>Media</th>
<th class='n'>DE</th><th class='n'>IC 95 % (t de Student)</th></tr>{rows}</table>
<p class="note">Unidades: {unidad}. Intervalo = media ± t(0,975; n − 1) · DE / √n, truncado en 0 y 100 %. La variación entre
unidades ya incluye el error de los puntos de cada foto, de modo que no se suman los intervalos de las fotos. Fotos con
«a revisar» (Canopeo y ExG − ExR difieren más de 5 puntos): {nrev}.</p>
<p class="note"><strong>Por qué dos intervalos distintos.</strong> En cada foto la cobertura de una clase es una proporción de puntos
(k de n) y su intervalo es el de Wilson: el único error es la ubicación al azar de los puntos dentro de esa foto. En el sitio la
pregunta cambia («¿cuál es la cobertura del sitio?») y la unidad de muestreo es la foto o la parcela: la dispersión entre
unidades ya contiene el error de puntos de cada foto más la variación real del terreno, y el intervalo de la media es el de la
t de Student. Juntar los puntos de todas las fotos en un solo intervalo de Wilson los trataría como independientes cuando los de
una misma foto comparten el mismo pedazo de suelo.</p></section>
<section><h2>Avisos</h2><ul>{warn}</ul></section>
<footer style="text-align:center;color:#52606d;margin-top:16px">Vegetación verde: Patrignani y Ochsner (2015).<br/>
<strong>CobDosel v{version}</strong> para QGIS · Autor: Jorge Fallas · Contacto:
<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer></div></body></html>""".format(
        version=e(version), site=e(site or "—"), rows=rows, unidad=e(unidad), nrev=nrev,
        warn=warn or "<li>Sin avisos.</li>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
