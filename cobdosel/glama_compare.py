"""
Comparación GLAMA ↔ CobDosel con la misma foto (CobDosel 0.14.41).

Objetivo: que la diferencia de CaCo entre la app GLAMA y CobDosel quede explicada paso a paso, de
modo que la parte que se debe al nivel de corte se aísle de la parte que se debe a la geometría.

Para cada foto se calculan cuatro valores:

  A  CaCo de la app GLAMA (anotado por el analista) con el corte de GLAMA.
  B  Reproducción de la pantalla de GLAMA con el corte de GLAMA: orden guardado de los píxeles
     (GLAMA no lee la etiqueta EXIF de orientación), casillas de giro usadas en la app, recorte
     cuadrado central a 1080 px, centro desplazado, franjas fuera de la foto contadas como dosel,
     radio «Hemisph. radius» y máscara de GLAMA.        B − A = residuo de la reproducción (≈ 0).
  C  La misma reproducción con el corte de CobDosel.    C − B = efecto del corte (único cambio).
  D  CobDosel: foto completa, calibración propia, píxeles reales, corte de CobDosel.
                                                        D − C = efecto de la geometría.

D − A = (B − A) + (C − B) + (D − C): residuo + corte + geometría.

Formato numérico de las salidas: punto decimal (CSV y textos).
"""

import csv
import math
import os

import numpy as np

from .batch_core import _read_table, _norm, analyze_photo, IMAGE_EXT, MAX_ANALYSIS_DIM
from .exif_gps import load_stored_rgb_image
from .glama_engine import (glama_rotate, glama_boxes_label, glama_screen_indices, GLAMA_CENTER_DY)

DEFAULT_GLAMA_MASK_DEG = 60.0
RESIDUAL_TOL = 0.15          # puntos de CaCo: por encima, revisar giro, radio, canal o máscara

TABLE_COLUMNS = ("archivo", "corte_glama", "caco_glama", "giro_180", "giro_90", "transponer",
                 "radio_glama", "corte_cobdosel")
_ALIASES = {
    "archivo": ("archivo", "foto", "file", "nombre", "imagen"),
    "corte_glama": ("corte_glama", "corte glama", "cut glama", "nivel de corte glama", "corte_app"),
    "caco_glama": ("caco_glama", "caco glama", "caco app", "caco_app", "cover glama"),
    "giro_180": ("giro_180", "180", "180°", "giro 180"),
    "giro_90": ("giro_90", "90", "90°", "giro 90"),
    "transponer": ("transponer", "tr", "tr.", "transpose"),
    "radio_glama": ("radio_glama", "radio glama", "hemisph. radius", "hemisph radius", "radio"),
    "corte_cobdosel": ("corte_cobdosel", "corte cobdosel", "corte fijo cobdosel"),
}

OUT_COLUMNS = ("archivo", "orientacion_exif", "casillas_glama", "radio_glama", "mascara_glama",
               "corte_glama", "caco_glama_app", "caco_reproduccion", "residuo_reproduccion",
               "corte_cobdosel", "metodo_corte_cobdosel", "caco_reproduccion_corte_cobdosel",
               "efecto_corte", "mascara_cobdosel", "caco_cobdosel", "efecto_geometria",
               "diferencia_total", "giro_sugerido", "residuo_giro_sugerido", "avisos")

_ORIENT_TEXT = {1: "1 (normal)", 2: "2 (espejo)", 3: "3 (180°)", 4: "4 (espejo vertical)",
                5: "5 (transpuesta)", 6: "6 (girar 90° horario)", 7: "7 (transversa)",
                8: "8 (girar 90° antihorario)"}


def _num(value):
    """Número desde texto o celda; acepta coma o punto decimal. None si está vacío."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    s = str(value).strip().replace(" ", "").replace("%", "")
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    return float(s)


def _flag(value):
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return _norm(str(value)) in ("1", "x", "si", "s", "true", "verdadero", "yes", "y", "marcada", "v")


def read_comparison_table(path):
    """Lee la tabla de comparación (.csv o .xlsx). Devuelve lista de dicts con TABLE_COLUMNS."""
    return read_comparison_table_ex(path)[0]


def read_comparison_table_ex(path):
    """
    Como read_comparison_table, pero devuelve (filas, omitidas). v0.14.54: una fila sin corte de GLAMA
    (foto no analizada en la app, o plantilla aún sin llenar) o con un corte no numérico se omite y se
    informa, en lugar de detener toda la comparación. omitidas = [(fila, archivo, motivo)].
    """
    rows = [r for r in _read_table(path) if r and any(c not in (None, "") for c in r)]
    if not rows:
        raise ValueError("La tabla está vacía: " + path)
    header = [_norm(str(h or "")) for h in rows[0]]
    idx = {}
    for key, names in _ALIASES.items():
        for i, h in enumerate(header):
            if h in [_norm(n) for n in names]:
                idx[key] = i
                break
    for req in ("archivo", "corte_glama"):
        if req not in idx:
            raise ValueError("Falta la columna «{}» en la tabla (columnas: {}).".format(
                req, ", ".join(TABLE_COLUMNS)))
    out, skipped = [], []
    for n, r in enumerate(rows[1:], start=2):
        def cell(k):
            i = idx.get(k)
            return r[i] if i is not None and i < len(r) else None
        name = cell("archivo")
        if name in (None, ""):
            continue
        try:
            cut = _num(cell("corte_glama"))
        except ValueError:
            skipped.append((n, str(name).strip(), "corte de GLAMA no numérico («{}»)".format(cell("corte_glama"))))
            continue
        if cut is None:
            skipped.append((n, str(name).strip(), "sin corte de GLAMA"))
            continue
        try:
            rec = {
                "fila": n,
                "archivo": str(name).strip(),
                "corte_glama": int(round(cut)),
                "caco_glama": _num(cell("caco_glama")),
                "giro_180": _flag(cell("giro_180")),
                "giro_90": _flag(cell("giro_90")),
                "transponer": _flag(cell("transponer")),
                "radio_glama": _num(cell("radio_glama")),
                "corte_cobdosel": _num(cell("corte_cobdosel")),
            }
        except ValueError as e:
            raise ValueError("Fila {} de la tabla: {}".format(n, e))
        if not 0 <= rec["corte_glama"] <= 255:
            raise ValueError("Fila {}: corte de GLAMA fuera de 0–255.".format(n))
        if rec["corte_cobdosel"] is not None:
            rec["corte_cobdosel"] = int(round(rec["corte_cobdosel"]))
        out.append(rec)
    if not out:
        if skipped:
            raise ValueError(
                "La tabla no tiene ningún corte de GLAMA ({} fotos sin corte). Llene, para cada foto analizada "
                "en GLAMA, al menos «corte_glama» (y de preferencia «caco_glama»), guarde la tabla y vuelva a "
                "pulsar «Comparar».".format(len(skipped)))
        raise ValueError("La tabla no tiene filas con archivo.")
    return out, skipped


def write_template(folder, out_path, delimiter=","):
    """Plantilla CSV con las fotos de la carpeta y las columnas por llenar. Devuelve n.º de fotos.
    delimiter: «;» donde la coma es el separador decimal (Excel en español la abre en columnas)."""
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT))
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(TABLE_COLUMNS)
        for n in names:
            w.writerow([n, "", "", 0, 0, 0, "", ""])
    return len(names)


def _caco(display, R, zen, cut, channel, projection, dy):
    return glama_screen_indices(display, R, zen, cut, channel, projection=projection,
                                center_dy=dy)["canopy_cover_index_pct"]


ROTATION_BOXES = [(False, False, False), (False, True, False), (True, False, False), (True, True, False)]


def compare_photo(path, calibration, cut_glama, glama_radius_px, glama_mask_deg=DEFAULT_GLAMA_MASK_DEG,
                  caco_glama=None, boxes=(False, False, False), channel_mode="blue_red",
                  glama_projection="polar", center_dy=GLAMA_CENTER_DY, cob_mask_deg=None,
                  corte_cobdosel=None, sky_is_bright=True):
    """Compara una foto. Devuelve un dict con OUT_COLUMNS (números sin redondear)."""
    if cob_mask_deg is None:
        cob_mask_deg = glama_mask_deg
    warns = []
    img, _s, _wh, tag, note = load_stored_rgb_image(path, max_dim=MAX_ANALYSIS_DIM)
    stored = np.asarray(img)
    if note:
        warns.append(note)
    zen_g = 90.0 - float(glama_mask_deg)
    R = float(glama_radius_px)
    disp = glama_rotate(stored, *boxes)
    B = _caco(disp, R, zen_g, cut_glama, channel_mode, glama_projection, center_dy)

    if corte_cobdosel is not None:
        cob = analyze_photo(path, calibration, 90.0 - float(cob_mask_deg), channel_mode, sky_is_bright,
                            cut_rule="fixed", fixed_cut=int(corte_cobdosel))
        method = "fijo (tabla)"
    else:
        cob = analyze_photo(path, calibration, 90.0 - float(cob_mask_deg), channel_mode, sky_is_bright)
        method = cob["metodo_corte"]
    warns.extend(cob.get("avisos") or [])
    c_cut = int(cob["corte"])
    C = _caco(disp, R, zen_g, c_cut, channel_mode, glama_projection, center_dy)
    D = cob["caco"]

    res = (B - caco_glama) if caco_glama is not None else None
    sug, sug_res = "", None
    if res is not None and abs(res) > RESIDUAL_TOL:
        warns.append("residuo de la reproducción {:+.2f} puntos: revise casillas de giro, radio, máscara, "
                     "canal y corte".format(res))
        # Solo los cuatro giros: una imagen y su reflejo izquierda-derecha dan el mismo CaCo (la banda
        # queda en el mismo borde), así que «Tr.» no se puede distinguir con el CaCo.
        trials = []
        for bx in ROTATION_BOXES:
            v = _caco(glama_rotate(stored, *bx), R, zen_g, cut_glama, channel_mode, glama_projection,
                      center_dy)
            trials.append((abs(v - caco_glama), v - caco_glama, bx))
        trials.sort()
        best = trials[0]
        # se sugieren los giros que reproducen la app; si varios dan casi el mismo CaCo (escena
        # simétrica), se nombran todos: el CaCo no permite distinguirlos
        if best[0] <= RESIDUAL_TOL:
            cands = [t for t in trials if t[0] <= RESIDUAL_TOL and t[0] - best[0] <= 0.05]
            sug, sug_res = " o ".join(glama_boxes_label(*t[2]) for t in cands), best[1]
    return {
        "archivo": os.path.basename(path),
        "orientacion_exif": _ORIENT_TEXT.get(tag, "sin etiqueta" if tag is None else str(tag)),
        "casillas_glama": glama_boxes_label(*boxes),
        "radio_glama": R,
        "mascara_glama": float(glama_mask_deg),
        "corte_glama": int(cut_glama),
        "caco_glama_app": caco_glama,
        "caco_reproduccion": B,
        "residuo_reproduccion": res,
        "corte_cobdosel": c_cut,
        "metodo_corte_cobdosel": method,
        "caco_reproduccion_corte_cobdosel": C,
        "efecto_corte": C - B,
        "mascara_cobdosel": float(cob_mask_deg),
        "caco_cobdosel": D,
        "efecto_geometria": D - C,
        "diferencia_total": D - (caco_glama if caco_glama is not None else B),
        "giro_sugerido": sug,
        "residuo_giro_sugerido": sug_res,
        "avisos": "; ".join(warns),
    }


def _stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return None
    n = len(v)
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "media": m, "de": sd, "min": min(v), "max": max(v),
            "media_abs": sum(abs(x) for x in v) / n}


def summarize(results):
    """Resumen de los efectos (media, DE, mín., máx., media absoluta)."""
    ok = [r for r in results if not r.get("error")]
    return {k: _stats([r.get(k) for r in ok]) for k in
            ("residuo_reproduccion", "efecto_corte", "efecto_geometria", "diferencia_total")}


def _fmt(v, d):
    if v is None:
        return ""
    if isinstance(v, float):
        return "{:.{}f}".format(v, d)
    return v


_DEC = {"radio_glama": 1, "mascara_glama": 1, "mascara_cobdosel": 1}


def run_comparison(table_path, photo_folder, calibration, out_csv, glama_radius_px=None,
                   glama_mask_deg=DEFAULT_GLAMA_MASK_DEG, channel_mode="blue_red", glama_projection="polar",
                   center_dy=GLAMA_CENTER_DY, cob_mask_deg=None, sky_is_bright=True, log=None, progress=None):
    """
    Compara todas las fotos de la tabla. glama_radius_px: radio global (la columna radio_glama de la
    tabla tiene prioridad). Escribe out_csv y <out>_resumen.txt. Devuelve (resultados, resumen, rutas).
    """
    def _log(msg, level="INFO"):
        if log:
            log(msg, level)
    rows, skipped = read_comparison_table_ex(table_path)
    if skipped:
        _log("{} foto(s) de la tabla sin corte de GLAMA, omitidas: {}".format(
            len(skipped), "; ".join("{} (fila {}: {})".format(a, n, why) for n, a, why in skipped)), "WARN")
    results = []
    for i, rec in enumerate(rows):
        path = os.path.join(photo_folder, rec["archivo"])
        R = rec["radio_glama"] or glama_radius_px
        base = {"archivo": rec["archivo"], "corte_glama": rec["corte_glama"],
                "caco_glama_app": rec["caco_glama"]}
        try:
            if not os.path.isfile(path):
                raise ValueError("no se encontró la foto en la carpeta")
            if not R:
                raise ValueError("sin radio de GLAMA (columna radio_glama o valor global)")
            r = compare_photo(path, calibration, rec["corte_glama"], R, glama_mask_deg,
                              caco_glama=rec["caco_glama"],
                              boxes=(rec["giro_180"], rec["giro_90"], rec["transponer"]),
                              channel_mode=channel_mode, glama_projection=glama_projection,
                              center_dy=center_dy, cob_mask_deg=cob_mask_deg,
                              corte_cobdosel=rec["corte_cobdosel"], sky_is_bright=sky_is_bright)
            results.append(r)
            _log("{}: GLAMA {} → reproducción {:.2f}; corte {}→{}: efecto del corte {:+.2f}; "
                 "CobDosel {:.2f} (geometría {:+.2f})".format(
                     rec["archivo"], _fmt(rec["caco_glama"], 2) or "—", r["caco_reproduccion"],
                     r["corte_glama"], r["corte_cobdosel"], r["efecto_corte"], r["caco_cobdosel"],
                     r["efecto_geometria"]),
                 "WARN" if r["avisos"] else "INFO")
        except Exception as e:      # una foto con problemas no detiene la comparación
            base.update(error=True, avisos="ERROR: {}".format(e))
            results.append(base)
            _log("{}: {}".format(rec["archivo"], e), "ERROR")
        if progress:
            progress(i + 1, len(rows))
    summary = summarize(results)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(OUT_COLUMNS)
        for r in results:
            w.writerow([_fmt(r.get(k), _DEC.get(k, 3)) for k in OUT_COLUMNS])
    txt = os.path.splitext(out_csv)[0] + "_resumen.txt"
    with open(txt, "w", encoding="utf-8") as f:
        f.write(summary_text(summary, results, glama_mask_deg, cob_mask_deg, channel_mode, center_dy))
    return results, summary, [out_csv, txt]


def summary_text(summary, results, glama_mask_deg, cob_mask_deg, channel_mode, center_dy):
    n_err = sum(1 for r in results if r.get("error"))
    lines = ["Comparación GLAMA ↔ CobDosel (CaCo, puntos porcentuales; punto decimal)",
             "Fotos: {} ({} con error)".format(len(results), n_err),
             "Máscara GLAMA {:.1f}°, máscara CobDosel {:.1f}°, canal {}, desplazamiento del centro {:+.1f} px".format(
                 glama_mask_deg, glama_mask_deg if cob_mask_deg is None else cob_mask_deg, channel_mode,
                 center_dy),
             "",
             "{:<34}{:>4}{:>9}{:>8}{:>9}{:>9}{:>11}".format("", "n", "media", "DE", "mín.", "máx.", "media |x|")]
    names = (("residuo_reproduccion", "Residuo reproducción (B − A)"),
             ("efecto_corte", "Efecto del corte (C − B)"),
             ("efecto_geometria", "Efecto de la geometría (D − C)"),
             ("diferencia_total", "Diferencia total (D − A)"))
    for k, label in names:
        s = summary.get(k)
        if s:
            lines.append("{:<34}{:>4}{:>+9.2f}{:>8.2f}{:>+9.2f}{:>+9.2f}{:>11.2f}".format(
                label, s["n"], s["media"], s["de"], s["min"], s["max"], s["media_abs"]))
        else:
            lines.append("{:<34}  sin datos".format(label))
    lines += ["",
              "A = CaCo de la app GLAMA; B = reproducción de la pantalla de GLAMA con el corte de GLAMA;",
              "C = la misma reproducción con el corte de CobDosel; D = CobDosel (foto completa, calibración propia).",
              "Con |B − A| ≤ {:.2f} la reproducción es fiel y C − B es el efecto del corte, sin otra causa.".format(
                  RESIDUAL_TOL)]
    big = [r["archivo"] for r in results
           if r.get("residuo_reproduccion") is not None and abs(r["residuo_reproduccion"]) > RESIDUAL_TOL]
    if big:
        lines.append("Fotos con residuo > {:.2f} (revisar casillas de giro, radio, máscara o canal): {}".format(
            RESIDUAL_TOL, ", ".join(big)))
    return "\n".join(lines) + "\n"
