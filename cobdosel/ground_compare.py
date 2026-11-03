"""Comparar clasificaciones de puntos de «Cobertura del suelo» (CobDosel 0.15.12). Sin Qt ni QGIS.

Dos analistas clasifican la misma foto con la misma cuadrícula (misma semilla) y exportan su
CobDosel_suelo_<foto>_puntos.csv. Este módulo los lee, comprueba que son los mismos puntos y calcula el acuerdo
observado, el acuerdo esperado por azar y el kappa de Cohen (Cohen 1960), con la tabla de confusión y la lista de
puntos en desacuerdo. Por defecto se comparan solo los puntos que la regla de Canopeo dejó sin clasificar (en el modo
reglamentario los puntos verdes automáticos son iguales para todos los analistas).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import csv
import html as _h
import io
import os

POINT_TOL_PX = 0.6           # los mismos puntos: coordenadas iguales (el CSV las redondea a 0,1 px)
DEFAULT_MIN_AGREEMENT = 90.0  # % (sugerencia del protocolo)
DEFAULT_MIN_KAPPA = 0.80      # «casi perfecto» (Landis y Koch 1977)
NOT_APPLICABLE = ("", "No aplica", "Sin datos")


def landis_koch(kappa):
    """Escala de Landis y Koch (1977) para kappa."""
    if kappa is None:
        return "—"
    if kappa < 0:
        return "pobre"
    for lim, txt in ((0.20, "leve"), (0.40, "aceptable"), (0.60, "moderado"), (0.80, "sustancial")):
        if kappa <= lim:
            return txt
    return "casi perfecto"


def _num(txt):
    return float(str(txt).strip().replace(",", "."))


def read_points_csv(path):
    """Lee un _puntos.csv de CobDosel («,» o «;»). Devuelve lista de dicts: archivo, punto, x, y, clase,
    automatica (None si la regla no lo marcó), corregido."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    need = {"archivo", "punto", "x_px", "y_px", "clase", "clase_automatica"}
    if not rows or not need.issubset(rows[0].keys()):
        raise ValueError("«{}» no es un CSV de puntos de CobDosel (faltan columnas: {}).".format(
            os.path.basename(path), ", ".join(sorted(need - set(rows[0].keys() if rows else [])))))
    out = []
    for r in rows:
        auto = (r.get("clase_automatica") or "").strip()
        out.append({"archivo": (r.get("archivo") or "").strip(), "punto": int(_num(r["punto"])),
                    "x": _num(r["x_px"]), "y": _num(r["y_px"]), "clase": (r.get("clase") or "").strip(),
                    "automatica": None if auto in NOT_APPLICABLE else auto,
                    "corregido": (r.get("corregido") or "").strip()})
    return out


def cohen_kappa(pairs):
    """(acuerdo observado, acuerdo esperado, kappa) de una lista de pares (clase A, clase B)."""
    n = len(pairs)
    if not n:
        return None, None, None
    po = sum(1 for a, b in pairs if a == b) / float(n)
    cats = sorted({a for a, _b in pairs} | {b for _a, b in pairs})
    pe = sum((sum(1 for a, _b in pairs if a == c) / float(n)) * (sum(1 for _a, b in pairs if b == c) / float(n))
             for c in cats)
    kappa = None if pe >= 1.0 else (po - pe) / (1.0 - pe)
    return po, pe, kappa


def compare(points_a, points_b, only_unclassified=True, min_agreement=DEFAULT_MIN_AGREEMENT,
            min_kappa=DEFAULT_MIN_KAPPA):
    """Compara dos clasificaciones de los mismos puntos. Error si no son la misma foto o la misma cuadrícula."""
    if len(points_a) != len(points_b):
        raise ValueError("Las dos clasificaciones tienen distinto número de puntos ({} y {}): no son la misma "
                         "cuadrícula.".format(len(points_a), len(points_b)))
    fa = {p["archivo"] for p in points_a}
    fb = {p["archivo"] for p in points_b}
    if fa != fb:
        raise ValueError("Las clasificaciones son de fotos distintas ({} y {}).".format(", ".join(sorted(fa)),
                                                                                    ", ".join(sorted(fb))))
    pa = sorted(points_a, key=lambda p: p["punto"])
    pb = sorted(points_b, key=lambda p: p["punto"])
    for a, b in zip(pa, pb):
        if a["punto"] != b["punto"] or abs(a["x"] - b["x"]) > POINT_TOL_PX or abs(a["y"] - b["y"]) > POINT_TOL_PX:
            raise ValueError("El punto {} está en otra posición en las dos clasificaciones: use la misma área y la "
                             "misma semilla de la cuadrícula.".format(a["punto"]))
    # misma cuadrícula pero distinta área (esquinas marcadas por cada analista): la clase automática puede diferir;
    # esos puntos no se comparan y se avisa (use «Cargar área y cuadrícula de un CSV…» para la misma área)
    auto_diff = [a["punto"] for a, b in zip(pa, pb) if a["automatica"] != b["automatica"]]
    sel = [(a, b) for a, b in zip(pa, pb) if a["automatica"] == b["automatica"]
           and not (only_unclassified and a["automatica"])]
    pairs = [(a["clase"], b["clase"]) for a, b in sel]
    po, pe, kappa = cohen_kappa(pairs)
    cats = sorted({x for pr in pairs for x in pr})
    matrix = {(ca, cb): sum(1 for a, b in pairs if a == ca and b == cb) for ca in cats for cb in cats}
    disagree = [{"punto": a["punto"], "x": a["x"], "y": a["y"], "clase_a": a["clase"], "clase_b": b["clase"],
                 "automatica": a["automatica"]} for a, b in sel if a["clase"] != b["clase"]]
    # puntos verdes automáticos que algún analista cambió (en modo reglamentario no debería haber)
    auto_changed = [a["punto"] for a, b in zip(pa, pb) if a["automatica"]
                    and (a["clase"] != a["automatica"] or b["clase"] != b["automatica"])]
    unclassified = sum(1 for a, b in sel if a["clase"] == "Sin clasificar" or b["clase"] == "Sin clasificar")
    ok = (po is not None and kappa is not None and 100.0 * po >= min_agreement and kappa >= min_kappa)
    return {"archivo": next(iter(fa)), "n_puntos": len(pa), "n_comparados": len(pairs),
            "solo_sin_clasificar": bool(only_unclassified), "acuerdo_obs": po, "acuerdo_esp": pe, "kappa": kappa,
            "escala": landis_koch(kappa), "categorias": cats, "matriz": matrix, "desacuerdos": disagree,
            "automaticos_cambiados": auto_changed, "sin_clasificar": unclassified, "automatica_distinta": auto_diff,
            "min_acuerdo": float(min_agreement), "min_kappa": float(min_kappa), "cumple": ok}


def summary_lines(res, name_a="A", name_b="B"):
    f = lambda v, d=3: "—" if v is None else "{:.{d}f}".format(v, d=d)
    out = ["Foto: {} · {} puntos; comparados: {} ({}).".format(
        res["archivo"], res["n_puntos"], res["n_comparados"],
        "solo los que la regla de Canopeo dejó sin clasificar" if res["solo_sin_clasificar"] else "todos")]
    out.append("Acuerdo observado: {} ({} %) · acuerdo esperado por azar: {} · kappa de Cohen: {} ({}).".format(
        f(res["acuerdo_obs"]), f(None if res["acuerdo_obs"] is None else 100 * res["acuerdo_obs"], 1),
        f(res["acuerdo_esp"]), f(res["kappa"], 2), res["escala"]))
    out.append("Puntos en desacuerdo: {}.".format(len(res["desacuerdos"])))
    out.append("Mínimo del protocolo: acuerdo ≥ {:.0f} % y kappa ≥ {:.2f} → {}.".format(
        res["min_acuerdo"], res["min_kappa"], "CUMPLE" if res["cumple"] else "NO CUMPLE"))
    if res["automaticos_cambiados"]:
        out.append("Aviso: {} puntos verdes automáticos fueron cambiados por algún analista (puntos {}): en el modo "
                   "reglamentario no se cambian.".format(len(res["automaticos_cambiados"]),
                                                         ", ".join(str(p) for p in res["automaticos_cambiados"][:10])))
    if res["automatica_distinta"]:
        out.append("Aviso: en {} puntos la clase automática difiere entre las dos clasificaciones (el área no fue "
                   "exactamente la misma); no se comparan. Para la doble clasificación, el segundo analista usa "
                   "«Cargar área y cuadrícula de un CSV…» con el CSV del primero.".format(len(res["automatica_distinta"])))
    if res["sin_clasificar"]:
        out.append("Aviso: {} puntos comparados están «Sin clasificar» en alguna de las dos clasificaciones.".format(
            res["sin_clasificar"]))
    return out


def write_html(res, path, name_a="A", name_b="B", file_a="", file_b="", version=""):
    """Informe HTML de la comparación."""
    e = _h.escape
    f = lambda v, d=3: "—" if v is None else "{:.{d}f}".format(v, d=d).replace(".", ",")
    cats = res["categorias"]
    head = "".join("<th class='n'>{}: {}</th>".format(e(name_b), e(c)) for c in cats)
    rows = ""
    for ca in cats:
        cells = "".join("<td class='n{}'>{}</td>".format(" d" if ca == cb else "", res["matriz"][(ca, cb)])
                        for cb in cats)
        rows += "<tr><th>{}: {}</th>{}<td class='n'>{}</td></tr>".format(
            e(name_a), e(ca), cells, sum(res["matriz"][(ca, cb)] for cb in cats))
    tot = "".join("<td class='n'>{}</td>".format(sum(res["matriz"][(ca, cb)] for ca in cats)) for cb in cats)
    dis = "".join("<tr><td class='n'>{}</td><td>{}</td><td>{}</td><td class='n'>{} ; {}</td></tr>".format(
        d["punto"], e(d["clase_a"]), e(d["clase_b"]), f(d["x"], 1), f(d["y"], 1)) for d in res["desacuerdos"]) or \
        "<tr><td colspan='4'>Sin desacuerdos.</td></tr>"
    lines = "".join("<p{}>{}</p>".format(" class='warn'" if ln.startswith("Aviso") else "", e(ln))
                    for ln in summary_lines(res, name_a, name_b)[3:])
    verdict = "Cumple" if res["cumple"] else "No cumple"
    page = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>CobDosel — Comparar clasificaciones</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1f2933;margin:0;padding:16px}}
.c{{max-width:1000px;margin:0 auto}} header{{background:#3d5a1e;color:#fff;padding:18px 24px;border-radius:10px}}
section{{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:16px 20px;margin-top:16px;overflow-x:auto}}
.big{{font-size:2rem;font-weight:800}} table{{border-collapse:collapse;font-size:.92rem}}
th,td{{padding:6px 8px;border-bottom:1px solid #e4e7eb;text-align:left}} th{{background:#f0f4f8}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} td.d{{background:#e3f2e1;font-weight:700}}
.warn{{color:#9a3412;font-weight:700}} .note{{font-size:.84rem;color:#52606d}}
</style></head><body><div class="c">
<header><h1>CobDosel v{version} — Comparar clasificaciones</h1><div>Foto: {foto}</div></header>
<section><table>
<tr><td>Clasificación {na}</td><td>{fa}</td></tr><tr><td>Clasificación {nb}</td><td>{fb}</td></tr>
<tr><td>Puntos de la cuadrícula</td><td>{n}</td></tr><tr><td>Puntos comparados</td><td>{nc} ({quien})</td></tr>
</table></section>
<section><div>Kappa de Cohen</div><div class="big">{kappa} ({escala})</div>
<p>Acuerdo observado: {po} ({pop} %) · acuerdo esperado por azar: {pe}</p>
<p><b>{verdict}</b> el mínimo del protocolo: acuerdo ≥ {mina} % y kappa ≥ {mink}.</p>{lines}</section>
<section><h2>Tabla de confusión</h2><table><tr><th></th>{head}<th class='n'>Total {na}</th></tr>{rows}
<tr><th>Total {nb}</th>{tot}<td class='n'>{nc}</td></tr></table>
<p class="note">En verde, los puntos en que coinciden. Kappa = (acuerdo observado − acuerdo esperado) / (1 − acuerdo
esperado) (Cohen 1960); escala de Landis y Koch (1977): ≤ 0,20 leve, 0,21–0,40 aceptable, 0,41–0,60 moderado,
0,61–0,80 sustancial, &gt; 0,80 casi perfecto.</p></section>
<section><h2>Puntos en desacuerdo</h2><table><tr><th class='n'>Punto</th><th>{na}</th><th>{nb}</th>
<th class='n'>x ; y (px del área)</th></tr>{dis}</table>
<p class="note">Los puntos en desacuerdo se revisan juntos y se resuelven por consenso con las reglas del protocolo.</p>
</section>
<footer style="text-align:center;color:#52606d;margin-top:16px">Cohen (1960); Landis y Koch (1977).<br/>
<strong>CobDosel v{version}</strong> para QGIS · Autor: Jorge Fallas · Contacto:
<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer></div></body></html>""".format(
        version=e(version), foto=e(res["archivo"]), na=e(name_a), nb=e(name_b), fa=e(file_a), fb=e(file_b),
        n=res["n_puntos"], nc=res["n_comparados"],
        quien="solo los que la regla de Canopeo dejó sin clasificar" if res["solo_sin_clasificar"] else "todos",
        kappa=f(res["kappa"], 2), escala=e(res["escala"]), po=f(res["acuerdo_obs"]),
        pop=f(None if res["acuerdo_obs"] is None else 100 * res["acuerdo_obs"], 1), pe=f(res["acuerdo_esp"]),
        verdict=verdict, mina=f(res["min_acuerdo"], 0), mink=f(res["min_kappa"], 2), lines=lines, head=head,
        rows=rows, tot=tot, dis=dis)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
