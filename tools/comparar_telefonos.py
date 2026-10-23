#!/usr/bin/env python3
"""Comparación de modelos de teléfono con CobDosel (fotos pareadas en los mismos puntos).

Cada teléfono se procesa por separado con «Procesamiento por sitio (lote)», con la misma máscara
y el mismo método de corte; cada lote produce un archivo <prefijo>_fotos.csv. Este script empareja
las fotos de cada teléfono con las del teléfono de referencia por parcela y punto, y calcula para
cada modelo la diferencia de CaCo (modelo − referencia):

- sesgo (media de las diferencias) con su intervalo de confianza del 95 %;
- desviación típica y límites de concordancia de Bland y Altman (sesgo ± 1,96 DT);
- tendencia de la diferencia con la cobertura (pendiente de la diferencia frente a la media);
- sesgo por clase de cobertura (0–50, 51–75, 76–100 %, según la referencia);
- veredicto frente al criterio de aceptación: |sesgo| ≤ tolerancia (2 puntos por defecto) y la recta de
  tendencia dentro de ± tolerancia en todo el rango de cobertura observado. La significación (p) de la
  pendiente se informa, pero no decide: con muchos puntos una tendencia minúscula sale significativa.

Uso:
    python comparar_telefonos.py Pixel10=lote_pixel_fotos.csv GalaxyA56=lote_a56_fotos.csv \\
        [Otro=otro_fotos.csv ...] [--salida carpeta] [--tolerancia 2]

El primer teléfono es la referencia. Requiere numpy y matplotlib (incluidos en QGIS); scipy es
opcional (valores exactos de t de Student; sin scipy se usa 1,96).

Salidas en la carpeta de salida:
    comparacion_pares.csv        una fila por punto y modelo, con los dos CaCo y la diferencia
    comparacion_resumen.csv      una fila por modelo con todos los estadísticos
    bland_altman_<modelo>.png    gráfico de Bland y Altman de cada modelo frente a la referencia
    comparacion_resumen.txt      el mismo resumen en texto

Autor: Jorge Fallas (jfallas56@gmail.com) — complemento CobDosel
Versión: 1.0 (2026-10-20)
"""

import argparse
import csv
import math
import os
import sys

import numpy as np

try:
    from scipy import stats as _st
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

CLASES = (("0–50 %", 0.0, 50.0), ("51–75 %", 50.0, 75.0), ("76–100 %", 75.0, 100.01))
TOLERANCIA_PTS = 2.0      # |sesgo| aceptable, puntos de CaCo


def _t(gl):
    """t de Student bilateral al 95 % (1,96 sin scipy)."""
    return float(_st.t.ppf(0.975, gl)) if HAS_SCIPY and gl > 0 else 1.96


def _es_verdadero(v):
    return str(v).strip().lower() in ("true", "1", "sí", "si", "verdadero")


def leer_lote(ruta):
    """{(parcela, punto): (caco, archivo)} de las fotos válidas de un <prefijo>_fotos.csv del lote."""
    datos, repetidos = {}, []
    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if not _es_verdadero(fila.get("valida", "")):
                continue
            try:
                caco = float(fila["caco"])
            except (KeyError, TypeError, ValueError):
                continue
            clave = (str(fila.get("parcela", "")).strip(), str(fila.get("punto", "")).strip())
            if clave in datos:
                repetidos.append(clave)
                continue
            datos[clave] = (caco, fila.get("archivo", ""))
    return datos, repetidos


def clase_de(c):
    for nombre, lo, hi in CLASES:
        if lo <= c < hi or (nombre == CLASES[0][0] and c <= hi):
            return nombre
    return CLASES[-1][0]


def comparar(ref, mod, tolerancia=TOLERANCIA_PTS):
    """Estadísticos de concordancia de mod frente a ref (diccionarios de leer_lote)."""
    claves = sorted(set(ref) & set(mod))
    r = np.array([ref[k][0] for k in claves])
    m = np.array([mod[k][0] for k in claves])
    d = m - r
    n = len(claves)
    out = {"n": n, "claves": claves, "ref": r, "mod": m, "dif": d,
           "solo_ref": len(set(ref) - set(mod)), "solo_mod": len(set(mod) - set(ref))}
    if n < 3:
        out["veredicto"] = "insuficiente (menos de 3 puntos pareados)"
        return out
    sesgo, dt = float(d.mean()), float(d.std(ddof=1))
    t = _t(n - 1)
    out.update(sesgo=sesgo, dt=dt, ic_lo=sesgo - t * dt / math.sqrt(n), ic_hi=sesgo + t * dt / math.sqrt(n),
               lca_lo=sesgo - 1.96 * dt, lca_hi=sesgo + 1.96 * dt)
    # Tendencia: diferencia frente a la media de los dos valores (proporcional a la cobertura)
    media = (r + m) / 2.0
    if np.ptp(media) > 0:
        b, a = np.polyfit(media, d, 1)
        resid = d - (a + b * media)
        se_b = math.sqrt((resid ** 2).sum() / (n - 2) / ((media - media.mean()) ** 2).sum()) if n > 2 else float("nan")
        tb = b / se_b if se_b > 0 else float("inf")
        p = float(2 * _st.t.sf(abs(tb), n - 2)) if HAS_SCIPY else (0.0 if abs(tb) > 2 else 1.0)
        lo_x, hi_x = float(media.min()), float(media.max())
        out.update(pendiente=float(b), p_pendiente=p, tend_lo=(lo_x, float(a + b * lo_x)), tend_hi=(hi_x, float(a + b * hi_x)))
    else:
        out.update(pendiente=0.0, p_pendiente=1.0, tend_lo=(float(media.min()), sesgo), tend_hi=(float(media.max()), sesgo))
    out["por_clase"] = []
    for nombre, _lo, _hi in CLASES:
        sel = np.array([clase_de(x) == nombre for x in r])
        if sel.any():
            out["por_clase"].append((nombre, int(sel.sum()), float(d[sel].mean())))
        else:
            out["por_clase"].append((nombre, 0, None))
    # Criterio práctico: la recta de tendencia no sale de ± tolerancia en el rango observado
    sin_tendencia = max(abs(out["tend_lo"][1]), abs(out["tend_hi"][1])) <= tolerancia
    sesgo_ok = abs(sesgo) <= tolerancia
    if sesgo_ok and sin_tendencia:
        out["veredicto"] = "aceptable"
    else:
        motivos = []
        if not sesgo_ok:
            motivos.append("sesgo {:+.2f} > ±{:g}".format(sesgo, tolerancia))
        if not sin_tendencia:
            motivos.append("la diferencia cambia con la cobertura: {:+.2f} con CaCo {:.0f} % y {:+.2f} con {:.0f} %".format(
                out["tend_lo"][1], out["tend_lo"][0], out["tend_hi"][1], out["tend_hi"][0]))
        out["veredicto"] = "revisar: " + "; ".join(motivos)
    if n < 20:
        out["veredicto"] += " (pocos puntos: se recomiendan 20–30)"
    return out


def grafico(nombre, ref_nombre, res, ruta, tolerancia):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, muted, acc, grid, band = "#18201e", "#5b6866", "#2a78d6", "#d5dcda", "#e8f1f3"
    media = (res["ref"] + res["mod"]) / 2.0
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=160)
    ax.axhspan(-tolerancia, tolerancia, color=band, zorder=0, label="aceptación ±{:g}".format(tolerancia))
    ax.axhline(0, color=muted, lw=0.8)
    ax.axhline(res["sesgo"], color=acc, lw=1.6, label="sesgo {:+.2f}".format(res["sesgo"]))
    for v in (res["lca_lo"], res["lca_hi"]):
        ax.axhline(v, color=acc, lw=1, ls=(0, (4, 3)))
    ax.text(101, res["lca_hi"], "{:+.2f}".format(res["lca_hi"]), va="center", fontsize=8, color=ink)
    ax.text(101, res["lca_lo"], "{:+.2f}".format(res["lca_lo"]), va="center", fontsize=8, color=ink)
    ax.scatter(media, res["dif"], s=28, color=acc, edgecolor="white", linewidth=1.2, zorder=3)
    if res.get("pendiente") is not None and np.ptp(media) > 0:
        xs = np.array([media.min(), media.max()])
        a = res["dif"].mean() - res["pendiente"] * media.mean()
        ax.plot(xs, a + res["pendiente"] * xs, color=muted, lw=1, label="tendencia (p = {:.3f})".format(res["p_pendiente"]))
    ax.set_xlim(0, 100)
    ax.set_xlabel("CaCo medio de los dos teléfonos (%)")
    ax.set_ylabel("{} − {} (puntos)".format(nombre, ref_nombre))
    ax.set_title("Bland–Altman: {} frente a {} (n = {})".format(nombre, ref_nombre, res["n"]), loc="left", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color=grid, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(ruta, facecolor="white")
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compara modelos de teléfono con fotos pareadas (CSV del lote de CobDosel).")
    ap.add_argument("lotes", nargs="+", help="NOMBRE=ruta_fotos.csv; el primero es la referencia")
    ap.add_argument("--salida", default=".", help="carpeta de salida (por defecto, la actual)")
    ap.add_argument("--tolerancia", type=float, default=TOLERANCIA_PTS, help="|sesgo| aceptable en puntos (2)")
    a = ap.parse_args(argv)
    if len(a.lotes) < 2:
        ap.error("se necesitan al menos dos teléfonos (referencia y un modelo)")
    lotes = []
    for item in a.lotes:
        if "=" not in item:
            ap.error("use NOMBRE=ruta.csv: «{}»".format(item))
        nombre, ruta = item.split("=", 1)
        datos, rep = leer_lote(ruta)
        if rep:
            print("Aviso: {}: {} puntos repetidos; se usa la primera foto de cada uno.".format(nombre, len(rep)))
        lotes.append((nombre.strip(), datos))
    os.makedirs(a.salida, exist_ok=True)
    ref_nombre, ref = lotes[0]
    filas_pares, filas_res, lineas = [], [], []
    lineas.append("Referencia: {} ({} fotos válidas). Tolerancia: ±{:g} puntos.".format(ref_nombre, len(ref), a.tolerancia))
    for nombre, mod in lotes[1:]:
        res = comparar(ref, mod, a.tolerancia)
        for k, rv, mv, dv in zip(res["claves"], res["ref"], res["mod"], res["dif"]):
            filas_pares.append([nombre, k[0], k[1], ref[k][1], mod[k][1], "{:.3f}".format(rv), "{:.3f}".format(mv),
                                "{:.3f}".format(dv), clase_de(rv)])
        lineas.append("")
        lineas.append("{} frente a {}: {} puntos pareados (solo en la referencia: {}; solo en {}: {})".format(
            nombre, ref_nombre, res["n"], res["solo_ref"], nombre, res["solo_mod"]))
        if res["n"] >= 3:
            lineas.append("  Sesgo {:+.2f} puntos (IC 95 % {:+.2f} a {:+.2f}); DT {:.2f}; límites de concordancia {:+.2f} a {:+.2f}".format(
                res["sesgo"], res["ic_lo"], res["ic_hi"], res["dt"], res["lca_lo"], res["lca_hi"]))
            lineas.append("  Tendencia con la cobertura: {:+.3f} puntos por punto de CaCo (p = {:.3f}); diferencia ajustada "
                          "{:+.2f} con CaCo {:.0f} % y {:+.2f} con {:.0f} %".format(
                              res["pendiente"], res["p_pendiente"], res["tend_lo"][1], res["tend_lo"][0],
                              res["tend_hi"][1], res["tend_hi"][0]))
            lineas.append("  Por clase (según la referencia): " + "; ".join(
                "{} n={} {}".format(c, n, "—" if v is None else "{:+.2f}".format(v)) for c, n, v in res["por_clase"]))
            png = os.path.join(a.salida, "bland_altman_{}.png".format("".join(ch if ch.isalnum() else "_" for ch in nombre)))
            grafico(nombre, ref_nombre, res, png, a.tolerancia)
            lineas.append("  Gráfico: " + png)
        lineas.append("  Veredicto: " + res["veredicto"])
        filas_res.append([nombre, ref_nombre, res["n"]] + (
            ["{:.3f}".format(res[x]) for x in ("sesgo", "ic_lo", "ic_hi", "dt", "lca_lo", "lca_hi", "pendiente", "p_pendiente")]
            if res["n"] >= 3 else [""] * 8) + [
            ("" if res["n"] < 3 else "; ".join("{} n={} {}".format(c, n, "" if v is None else "{:+.2f}".format(v))
                                              for c, n, v in res["por_clase"])), res["veredicto"]])
    with open(os.path.join(a.salida, "comparacion_pares.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["modelo", "parcela", "punto", "archivo_referencia", "archivo_modelo", "caco_referencia",
                    "caco_modelo", "diferencia", "clase_referencia"])
        w.writerows(filas_pares)
    with open(os.path.join(a.salida, "comparacion_resumen.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["modelo", "referencia", "n", "sesgo", "ic95_inf", "ic95_sup", "dt", "lca_inf", "lca_sup",
                    "pendiente", "p_pendiente", "por_clase", "veredicto"])
        w.writerows(filas_res)
    with open(os.path.join(a.salida, "comparacion_resumen.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
