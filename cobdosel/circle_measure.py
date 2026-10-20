"""Geometría de la medición del círculo de referencia (sin dependencias de Qt).

Tres modos de medición sobre la foto de calibración:
- "diametro": 2 puntos opuestos del borde → un diámetro.
- "cruz": 4 puntos → líneas E–O (puntos 1–2) y N–S (puntos 3–4); se informa su diferencia
  (elipse = cámara no paralela al círculo o clic impreciso). Desde 0.14.6 el diámetro y el
  centro son los del círculo que pasa por los 4 puntos (igual al promedio de las dos líneas
  cuando ambas son diámetros) y se avisa si las líneas no se cruzan en su punto medio:
  nota informativa si los 4 puntos están sobre un mismo círculo (0.14.7), advertencia si no.
- "ajuste": ≥ 5 puntos del borde → círculo por mínimos cuadrados (método algebraico de
  Kåsa); diámetro, centro y error cuadrático medio de los puntos.

En todos los casos se informa el desplazamiento del centro del círculo respecto del centro
de la imagen (Tichý 2015: el círculo debe fotografiarse en el centro). Aviso graduado
(0.14.5): ≤ 5 % sin mensaje; 5–15 % nota informativa (``notes``, la calibración es usable);
> 15 % advertencia de repetir la foto (``warnings``). En el modo ajuste se avisa si los
puntos cubren un arco < 180°.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import math

import numpy as np

MODES = ("diametro", "cruz", "ajuste")
MIN_POINTS = {"diametro": 2, "cruz": 4, "ajuste": 5}
MAX_POINTS = {"diametro": 2, "cruz": 4, "ajuste": 64}

# Tolerancias de calidad (fracción del diámetro)
TOL_DIAMETER_DIFF = 0.01     # diámetros E–O y N–S deben coincidir dentro del 1 %
TOL_CENTRE_OFFSET = 0.05     # centro del círculo a ≤ 5 % del diámetro del centro de la foto
TOL_CENTRE_RETAKE = 0.15     # > 15 %: repetir la foto (puede haber inclinación o distorsión)
TOL_MIDPOINT_GAP = 0.02      # modo cruz: puntos medios de las dos líneas a ≤ 2 % del diámetro
TOL_FIT_RMS = 0.005          # residuo del ajuste ≤ 0.5 % del diámetro
MIN_ARC_DEG = 180.0          # modo ajuste: puntos repartidos en un arco ≥ 180° (ideal ≥ 270°)


def _line_intersection(p1, p2, p3, p4):
    """Intersección de las rectas p1–p2 y p3–p4 (None si son paralelas)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return None
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / den,
            (a * (y3 - y4) - (y1 - y2) * b) / den)


def fit_circle(points):
    """Círculo por mínimos cuadrados (Kåsa). Devuelve (cx, cy, r, rms) o None."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 3:
        return None
    x, y = pts[:, 0], pts[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    try:
        sol, _res, rank, _sv = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < 3:
        return None      # v0.14.23: puntos repetidos o alineados → no definen un círculo
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r2 = sol[2] + cx * cx + cy * cy
    if not np.isfinite(r2) or r2 <= 0:
        return None
    r = math.sqrt(r2)
    resid = np.hypot(x - cx, y - cy) - r
    return float(cx), float(cy), float(r), float(math.sqrt(np.mean(resid ** 2)))


def measure(points, mode="diametro", image_size=None):
    """
    Resultado de la medición o None si faltan puntos.

    Devuelve dict con: mode, diameter_px, centre_xy (o None), d_ew_px, d_ns_px,
    diff_pct, fit_rms_px, centre_offset_px, centre_offset_pct, warnings (lista).
    """
    if mode not in MODES:
        raise ValueError("Modo de medición desconocido: {}".format(mode))
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < MIN_POINTS[mode]:
        return None
    res = {"mode": mode, "n_points": len(pts), "centre_xy": None, "d_ew_px": None,
           "d_ns_px": None, "diff_pct": None, "fit_rms_px": None,
           "centre_offset_px": None, "centre_offset_pct": None, "arc_deg": None,
           "midpoint_gap_pct": None,
           "warnings": [], "notes": [], "issues": [], "verdict": None}

    if mode == "diametro":
        (x1, y1), (x2, y2) = pts[:2]
        res["diameter_px"] = math.hypot(x2 - x1, y2 - y1)
        if not res["diameter_px"] > 0:
            return None      # v0.14.23: dos clics en el mismo punto
        res["centre_xy"] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    elif mode == "cruz":
        p1, p2, p3, p4 = pts[:4]
        d1 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        d2 = math.hypot(p4[0] - p3[0], p4[1] - p3[1])
        res["d_ew_px"], res["d_ns_px"] = d1, d2
        # Centro y diámetro: círculo que pasa por los 4 puntos (0.14.6). La intersección de las
        # dos líneas solo es el centro si ambas son diámetros; si una línea se marcó fuera del
        # centro (p. ej. sobre la guía cian) es una cuerda y el círculo dibujado quedaba desplazado.
        fit = fit_circle(pts[:4])
        if fit is not None:
            res["centre_xy"] = (fit[0], fit[1])
            res["diameter_px"] = 2.0 * fit[2]
            res["fit_rms_px"] = fit[3]
        else:
            res["centre_xy"] = _line_intersection(p1, p2, p3, p4)
            res["diameter_px"] = (d1 + d2) / 2.0
        if not res["diameter_px"] > 0:
            return None      # v0.14.23: puntos repetidos → diámetro 0 (antes ZeroDivisionError)
        res["diff_pct"] = 100.0 * abs(d1 - d2) / res["diameter_px"] if res["diameter_px"] > 0 else None
        m1 = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        m2 = ((p3[0] + p4[0]) / 2.0, (p3[1] + p4[1]) / 2.0)
        res["midpoint_gap_pct"] = 100.0 * math.hypot(m1[0] - m2[0], m1[1] - m2[1]) / res["diameter_px"]
        if res["midpoint_gap_pct"] > 100.0 * TOL_MIDPOINT_GAP:
            base = ("Las dos líneas no se cruzan en su punto medio (separación de {:.1f} % del "
                    "diámetro): al menos una de ellas no es un diámetro. Marque los extremos "
                    "este–oeste y norte–sur del propio círculo, no sobre las guías cian que pasan "
                    "por el centro de la fotografía.\n").format(res["midpoint_gap_pct"])
            consistent = (res["fit_rms_px"] is not None
                          and res["fit_rms_px"] <= TOL_FIT_RMS * res["diameter_px"])
            if consistent:
                # Los 4 puntos están sobre un mismo círculo: el resultado es válido (0.14.7)
                _add(res, "note", "medicion",
                     base + "El diámetro y el centro se calculan con el círculo que pasa por los "
                     "cuatro puntos; como los cuatro puntos están sobre el mismo círculo, la medición "
                     "es correcta.")
            else:
                _add(res, "warn", "medicion",
                     base + "Los cuatro puntos no están sobre un mismo círculo (residuo de {:.1f} px): "
                     "algún clic no cayó en la línea del círculo. Repita la medición.".format(
                        res["fit_rms_px"] or 0.0))
        # La diferencia E–O/N–S solo indica elipse si ambas líneas son diámetros
        if (res["diff_pct"] is not None and res["diff_pct"] > 100.0 * TOL_DIAMETER_DIFF
                and res["midpoint_gap_pct"] <= 100.0 * TOL_MIDPOINT_GAP):
            _add(res, "warn", "fotografia",
                 "Los diámetros este–oeste y norte–sur difieren {:.1f} % (más de {:.0f} %): el "
                 "círculo se ve como una elipse (teléfono no paralelo al círculo) o un clic no cayó "
                 "en el borde.\nRepita la fotografía o la medición.".format(res["diff_pct"], 100.0 * TOL_DIAMETER_DIFF))
    else:
        fit = fit_circle(pts)
        if fit is None:
            return None
        cx, cy, r, rms = fit
        res["diameter_px"] = 2.0 * r
        res["centre_xy"] = (cx, cy)
        res["fit_rms_px"] = rms
        if rms > TOL_FIT_RMS * res["diameter_px"]:
            _add(res, "warn", "medicion",
                 "Residuo del ajuste de {:.1f} px (más de {:.1f} % del diámetro): revise los puntos "
                 "del borde.".format(rms, 100.0 * TOL_FIT_RMS))

        res["arc_deg"] = arc_coverage_deg(pts, (cx, cy))
        if res["arc_deg"] < MIN_ARC_DEG:
            _add(res, "warn", "medicion",
                 "Los puntos cubren solo un arco de {:.0f}° del círculo: el ajuste es inestable y "
                 "tiende a subestimar el diámetro.\nDistribuya los puntos alrededor de todo el "
                 "círculo (al menos tres cuartos; lo ideal son 8 puntos, uno cada 45°).".format(res["arc_deg"]))

    if image_size is not None and res["centre_xy"] is not None and res["diameter_px"] > 0:
        w, h = image_size
        off = math.hypot(res["centre_xy"][0] - w / 2.0, res["centre_xy"][1] - h / 2.0)
        res["centre_offset_px"] = off
        res["centre_offset_pct"] = 100.0 * off / res["diameter_px"]
        pct = res["centre_offset_pct"]
        if pct > 100.0 * TOL_CENTRE_RETAKE:
            _add(res, "warn", "fotografia",
                 "El centro del círculo está a {:.0f} px ({:.1f} % del diámetro) del centro de la "
                 "fotografía: con un desplazamiento tan grande puede haber también inclinación o "
                 "distorsión del lente.\nRepita la fotografía con el círculo en el centro.".format(off, pct))
        elif pct > 100.0 * TOL_CENTRE_OFFSET:
            _add(res, "note", "fotografia",
                 "El centro del círculo está a {:.0f} px ({:.1f} % del diámetro) del centro de la "
                 "fotografía. Puede usar la calibración: con lente regular y el teléfono paralelo al "
                 "círculo, el efecto en el radio es despreciable; con lente ojo de pez puede ser "
                 "hasta aproximadamente {:.1f} %.\nPara mayor exactitud, centre el círculo en la "
                 "próxima fotografía.".format(
                    off, pct, fisheye_offset_error_pct(pct)))
    res["verdict"] = _verdict(res["issues"])
    return res


def _add(res, level, scope, text):
    """Registra un mensaje de control de calidad: nivel «warn» o «note», ámbito «fotografia» o «medicion»."""
    res["issues"].append({"level": level, "scope": scope, "text": text})
    (res["warnings"] if level == "warn" else res["notes"]).append(text)


def _verdict(issues):
    """
    Veredicto global (código, texto), para que los mensajes no se contradigan: un aviso de la
    fotografía obliga a repetirla aunque la medición (los clics) sea correcta.
    """
    warn_scopes = {i["scope"] for i in issues if i["level"] == "warn"}
    if "fotografia" in warn_scopes:
        return "repetir_foto", "No use esta calibración: repita la fotografía del círculo."
    if "medicion" in warn_scopes:
        return "repetir_medicion", "Repita la medición (marque de nuevo los puntos); la fotografía es válida."
    if issues:
        return "usable_avisos", "Calibración utilizable (ver notas)."
    return "ok", "Dentro de tolerancia."


def arc_coverage_deg(points, centre):
    """Arco del círculo cubierto por los puntos (360° menos el mayor hueco angular)."""
    cx, cy = centre
    ang = sorted(math.degrees(math.atan2(y - cy, x - cx)) % 360.0 for x, y in points)
    if len(ang) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(ang, ang[1:])] + [ang[0] + 360.0 - ang[-1]]
    return 360.0 - max(gaps)


def fisheye_offset_error_pct(offset_pct_of_diameter, edge_zenith_deg=30.0):
    """
    Error relativo (%) del diámetro medido con un ojo de pez equidistante cuando el círculo
    está desplazado (borde del círculo a ``edge_zenith_deg`` del cenit). Con lente regular
    (proyección central) y el teléfono paralelo al círculo el error es 0.
    """
    k = 2.0 * offset_pct_of_diameter / 100.0          # desplazamiento / radio
    t = math.tan(math.radians(edge_zenith_deg))
    d = math.atan((1.0 + k) * t) + math.atan(max(1.0 - k, -1e9) * t)
    return 100.0 * abs(d / (2.0 * math.atan(t)) - 1.0)
