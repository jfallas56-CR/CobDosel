"""Motor GLAMA de CobDosel: reimplementación del cálculo de resultados del método GLAMA
(Tichý 2016; app GLAMA v3.0), verificada contra el comportamiento de la app.

Referencias de comportamiento: pantallas de resultados y de nivel de corte recomendado de la
app GLAMA v3.0 y Manual de GLAMA v3.0 (Fig. 11–12). Glosario de las magnitudes intermedias
(nombres usados por la app) para trazabilidad:
    pos      = píxeles claros no enmascarados (por anillo de 1°)
    neg      = píxeles oscuros en el fotograma (lo enmascarado cuenta como oscuro)
    negneg   = píxeles oscuros no enmascarados
    celk     = píxeles del anillo en el círculo COMPLETO (incluye fuera del fotograma)
    rozdil   = cos θ_lo − cos θ_hi (ángulo sólido del anillo)
    canopen  = apertura del dosel (sobre los anillos con píxeles visibles)
    celkove  = «Part of Hemisph. Taken by Camera» (pantalla de resultados)
    kuloproj = «Modif. CaCo Index» en pantalla (T^cos θ, pesos sin θ)
    vodoproj = «Canopy Cover (CaCo) Index» en pantalla (T^cos θ, pesos sin θ·cos θ)
             → coincide con el «Canopy Cover Index» publicado (Fig. 12 B/D del manual,
               residuo ≤ 0.02 pts; ver tests/log_glama_source_fit.txt)

Rarezas del original que se reproducen a propósito (para igualar a GLAMA):
- Píxel claro si valor ≥ nivel de corte (no «>»).
- Anillos sin píxeles claros se excluyen de los denominadores de kuloproj/vodoproj.
- Proyección «Angular» de GLAMA (= ortográfica): el exponente usa cos(j°) y el peso
  horizontal cos((j+0.5)°) con j = índice del anillo, no el ángulo cenital real.

Autor del complemento QGIS: Jorge Fallas (jfallas56@gmail.com)
"""

import math
import numpy as np

N_BINS = 90  # GLAMA: 90 anillos de igual ancho en radio (0..R)

# Proyecciones de CobDosel que equivalen a la «Polar» de GLAMA (r ∝ θ)
_GLAMA_POLAR = ("polar", "angular")
# Proyección de CobDosel que equivale a la «Angular» de GLAMA (r = R·sin θ)
_GLAMA_ANGULAR = ("orthographic",)


def glama_mode(projection_code):
    """'polar', 'angular' (GLAMA) o 'general' (otras proyecciones de CobDosel)."""
    if projection_code in _GLAMA_POLAR:
        return "polar"
    if projection_code in _GLAMA_ANGULAR:
        return "angular"
    return "general"


def _pixel_zenith_deg(r_px, radius_px, calibration, mode):
    """Ángulo cenital (°) por píxel, igual que GLAMA para sus dos proyecciones."""
    rho = np.clip(r_px / float(radius_px), 0.0, 1.0)
    if mode == "polar":
        return 90.0 * rho
    if mode == "angular":
        return np.degrees(np.arcsin(rho))
    from .lens_calibration import pixel_radius_to_zenith
    return np.asarray(pixel_radius_to_zenith(r_px, calibration), dtype=np.float64)


def horizon_zenith_limit(azimuth_deg, horizon_angles_deg):
    """
    Cenit máximo no enmascarado para cada acimut, como la máscara por direcciones de GLAMA.

    azimuth_deg: acimut desde «arriba» de la imagen, sentido horario (0–360°), igual que
        la pantalla «Horizon definition» de GLAMA.
    horizon_angles_deg: ángulos de máscara sobre el horizonte (1, 4, 8 o 16 direcciones);
        la dirección k está en (k−1)·360°/n y entre direcciones vecinas el límite cenital
        se interpola linealmente.
    """
    h = np.asarray(horizon_angles_deg, dtype=np.float64).ravel()
    n = h.size
    if n == 1:
        return np.full(np.shape(azimuth_deg), 90.0 - h[0])
    az = np.mod(np.asarray(azimuth_deg, dtype=np.float64), 360.0)
    mezi = az / (360.0 / n)
    i1 = np.floor(mezi).astype(np.int64) % n
    i2 = (i1 + 1) % n
    t = mezi - np.floor(mezi)
    return (90.0 - h[i1]) * (1.0 - t) + (90.0 - h[i2]) * t


def _java_azimuth(aix, aiy):
    """Acimut (°) como la pantalla «Horizon definition»: 0 = arriba, sentido horario."""
    aiz = np.sqrt(aix * aix + aiy * aiy)
    vy = np.degrees(np.arcsin(np.clip(aiy / (0.01 + aiz), -1.0, 1.0)))
    return np.where(aix >= 0, 90.0 - vy, vy + 270.0)


def _java_trunc(x):
    """Conversión a entero de la app: trunca hacia cero."""
    return np.trunc(x).astype(np.int64)


def glama_ring_counts(sky_mask, center_xy, radius_px, zenith_max_deg,
                      calibration=None, projection="polar"):
    """
    Conteo por anillo de 1/90 del radio, reproduciendo EXACTAMENTE el muestreo de
    conteo de GLAMA (precisión «All pixels»): columnas i3 = −R + k y, en cada
    columna, filas j = −j_di + k con j_di = R·√(1 − (i3/R)² + 1e−5); píxel = ((int)(X+i3),
    (int)(Y+j)); anillo EE = round(−0.499999 + 90·√(i3² + j²)/R).

    sky_mask: bool (True = claro, umbralizado con «≥ nivel de corte»).
    zenith_max_deg: máscara de horizonte simple (cenit máximo no enmascarado).
    zenith_max_deg también acepta ("dirs", [h1, …, hn]): máscara de GLAMA por direcciones,
    con hk = ángulo sobre el horizonte de la dirección k (ver horizon_zenith_limit()).
    Devuelve dict con pos, neg, negneg, celk (arrays de 92), lightpix, totpix, visibpix
    e histogram (0–255 de los píxeles no enmascarados; requiere gray en
    glama_ring_counts_with_gray).
    """
    return _glama_counts(sky_mask, None, center_xy, radius_px, zenith_max_deg,
                         calibration, projection)


def glama_ring_counts_with_gray(gray, cut_level, center_xy, radius_px, zenith_max_deg,
                                calibration=None, projection="polar"):
    """Como glama_ring_counts, clasificando con gray ≥ cut_level y devolviendo el histograma."""
    return _glama_counts(None, (gray, int(cut_level)), center_xy, radius_px,
                         zenith_max_deg, calibration, projection)


def _glama_counts(sky_mask, gray_cut, center_xy, radius_px, zenith_max_deg,
                  calibration, projection):
    if gray_cut is not None:
        gray, cut = gray_cut
        h, w = gray.shape[:2]
    else:
        h, w = sky_mask.shape[:2]
    R = float(radius_px)
    if R <= 0:
        raise ValueError("Radio del hemisferio no válido: {}".format(radius_px))
    X, Y = float(center_xy[0]), float(center_xy[1])
    mode = glama_mode(projection)
    # zenith_max_deg: escalar (máscara única) o lista de ángulos SOBRE EL HORIZONTE por
    # dirección (horizon_angles) pasada como tupla ("dirs", [...])
    directional = isinstance(zenith_max_deg, tuple) and zenith_max_deg[0] == "dirs"
    if directional:
        horizon_angles = zenith_max_deg[1]
    else:
        zmax = float(zenith_max_deg)

    pos = np.zeros(N_BINS + 2)
    neg = np.zeros(N_BINS + 2)
    negneg = np.zeros(N_BINS + 2)
    hist = np.zeros(256)
    lightpix = 0
    visibpix = 0

    # Columnas: i3 = −R + k, k = 1, 2, … mientras i3 previo < R
    n_cols = int(math.ceil(2.0 * R))
    i3_all = -R + np.arange(1, n_cols + 1, dtype=np.float64)
    ii_all = _java_trunc(X + i3_all)
    in_cols = (ii_all > 0) & (ii_all + 1 < w)
    for i3, ii in zip(i3_all[in_cols], ii_all[in_cols]):
        arg = (1.0 - (i3 / R) ** 2) + 1.0e-5
        if arg <= 0.0:
            # v0.14.26: con R no entero la última columna queda un poco más allá de R (i3 > R) y
            # math.sqrt fallaba («math domain error») si el círculo cabía entero en el ancho de la
            # foto (ojo de pez, calibración reescalada). En la app la raíz da NaN y la columna no
            # aporta píxeles: se omite igual.
            continue
        j_di = R * math.sqrt(arg)
        n_rows = int(math.ceil(2.0 * j_di))
        if n_rows <= 0:
            continue
        jv = -j_di + np.arange(1, n_rows + 1, dtype=np.float64)
        dd = i3 * i3 + jv * jv
        jj = _java_trunc(Y + jv)
        ok = (dd <= R * R) & (jj > 0) & (jj + 1 < h)
        if not ok.any():
            continue
        jv, dd, jj = jv[ok], dd[ok], jj[ok]
        rr = np.sqrt(dd)
        ee = np.where(dd > 0, np.floor(-0.499999 + 90.0 * rr / R + 0.5), 0).astype(np.int64)
        ee = np.clip(ee, 0, N_BINS + 1)
        zen = _pixel_zenith_deg(rr, R, calibration, mode)
        if directional:
            # acimut desde arriba, horario (x a la derecha, y hacia arriba = −j), con la
            # misma fórmula que la app (asin con +0.01 en el radio)
            az = _java_azimuth(np.full(jv.shape, i3), -jv)
            unmasked = zen <= horizon_zenith_limit(az, horizon_angles) + 1e-9
        else:
            unmasked = zen <= zmax + 1e-9
        if gray_cut is not None:
            vals = gray[jj, ii].astype(np.int64)
            hist += np.bincount(vals[unmasked], minlength=256)[:256]
            light = unmasked & (vals >= cut)
        else:
            light = unmasked & sky_mask[jj, ii]
        visibpix += int(ok.sum())
        lightpix += int(light.sum())
        pos += np.bincount(ee[light], minlength=N_BINS + 2)
        neg += np.bincount(ee[~light], minlength=N_BINS + 2)
        negneg += np.bincount(ee[~light & unmasked], minlength=N_BINS + 2)

    # celk: muestras de la retícula de GLAMA en cada anillo del círculo COMPLETO (incluido
    # fuera del fotograma). Solo se necesitan los anillos con píxeles visibles; se cuentan
    # con la misma retícula para reproducir el déficit de muestras junto al borde.
    visible_rings = np.nonzero(pos + neg > 0)[0]
    celk = np.zeros(N_BINS + 2)
    if visible_rings.size:
        ring_max = int(visible_rings.max())
        r_lim = min(R, (ring_max + 1) * R / 90.0)
        for i3 in i3_all:
            if abs(i3) > r_lim:
                continue
            j_di = R * math.sqrt((1.0 - (i3 / R) ** 2) + 1.0e-5)
            n_rows = int(math.ceil(2.0 * j_di))
            half = math.sqrt(max(r_lim * r_lim - i3 * i3, 0.0))
            k0 = max(1, int(math.floor(j_di - half)))
            k1 = min(n_rows, int(math.ceil(j_di + half)) + 1)
            if k1 < k0:
                continue
            jv = -j_di + np.arange(k0, k1 + 1, dtype=np.float64)
            dd = i3 * i3 + jv * jv
            keep = dd <= R * R
            rr = np.sqrt(dd[keep])
            ee = np.where(dd[keep] > 0, np.floor(-0.499999 + 90.0 * rr / R + 0.5), 0)
            ee = np.clip(ee.astype(np.int64), 0, N_BINS + 1)
            celk += np.bincount(ee, minlength=N_BINS + 2)
        # anillos completos dentro de r_lim: exactos; el último puede quedar truncado,
        # pero solo se usan anillos ≤ ring_max, todos contenidos en r_lim.

    return {
        "pos": pos, "neg": neg, "negneg": negneg, "celk": celk,
        "lightpix": lightpix,
        "totpix": int(math.floor(math.pi * R * R + 0.5)),
        "visibpix": visibpix,
        "histogram": hist,
        "mode": mode,
    }


def _ring_angles(mode, calibration, radius_px):
    """θ_lo, θ_hi (°), ángulo del exponente y del peso horizontal por anillo."""
    j = np.arange(N_BINS, dtype=np.float64)
    if mode == "polar":
        lo, hi = j, j + 1.0
        expo = j + 0.5
        horiz = j + 0.5
    elif mode == "angular":
        lo = np.degrees(np.arcsin(j / N_BINS))
        hi = np.degrees(np.arcsin(np.minimum((j + 1.0) / N_BINS, 1.0)))
        expo = j            # rareza de GLAMA: índice del anillo, no el cenit
        horiz = j + 0.5     # rareza de GLAMA
    else:
        from .lens_calibration import pixel_radius_to_zenith
        R = float(radius_px)
        edges = np.asarray(
            pixel_radius_to_zenith(np.linspace(0.0, R, N_BINS + 1), calibration),
            dtype=np.float64,
        )
        lo, hi = edges[:-1], edges[1:]
        mid = (lo + hi) / 2.0
        expo = mid
        horiz = mid
    return lo, hi, expo, horiz


def glama_indices(counts, calibration=None, radius_px=None, papa=90):
    """
    Índices de GLAMA. papa = n.º de anillos considerados (90 = hemisferio).
    Devuelve porcentajes: canopy_openness, canopy_closure, canopy_cover_index (vodoproj),
    spherical_cover (kuloproj), unmasked_cover (canopenfree) y gap_fraction.
    """
    pos, neg, negneg, celk = (counts[k] for k in ("pos", "neg", "negneg", "celk"))
    lo, hi, expo, horiz = _ring_angles(counts["mode"], calibration, radius_px)
    n = int(min(papa, N_BINS))

    canopen = canopen_den = 0.0
    celkove = 0.0
    free_num = free_den = 0.0
    kulo_num = kulo_den = vodo_num = vodo_den = 0.0
    for i in range(n):
        posneg = pos[i] + neg[i]
        posnegneg = pos[i] + negneg[i]
        if posneg <= 0.0 or celk[i] <= 0.0:
            continue
        rozdil = math.cos(math.radians(lo[i])) - math.cos(math.radians(hi[i]))
        canopen += (pos[i] / celk[i]) * rozdil
        canopen_den += rozdil
        celkove += (posneg / celk[i]) * rozdil
        free_num += (pos[i] / celk[i]) * rozdil
        free_den += (posnegneg / celk[i]) * rozdil
        if posnegneg > 0.0 and pos[i] > 0.0:
            c_exp = math.cos(math.radians(expo[i]))
            c_hor = math.cos(math.radians(horiz[i]))
            posupr = posnegneg * (pos[i] / posnegneg) ** c_exp
            kulo_num += (posupr / celk[i]) * rozdil
            kulo_den += (posnegneg / celk[i]) * rozdil
            vodo_num += (posupr / celk[i]) * rozdil * c_hor
            vodo_den += (posnegneg / celk[i]) * rozdil * c_hor

    openness = 100.0 * canopen / canopen_den if canopen_den > 0 else 0.0
    totpix = counts["totpix"]
    return {
        "gap_fraction_pct": 100.0 * counts["lightpix"] / totpix if totpix > 0 else 0.0,
        "canopy_openness_pct": openness,
        "canopy_closure_pct": 100.0 - openness,
        "canopy_cover_index_pct": 100.0 * (1.0 - vodo_num / vodo_den) if vodo_den > 0 else 0.0,
        "spherical_cover_pct": 100.0 * (1.0 - kulo_num / kulo_den) if kulo_den > 0 else 0.0,
        "unmasked_cover_pct": 100.0 * (1.0 - free_num / free_den) if free_den > 0 else 0.0,
        # «Part of Hemisph. Taken by Camera» (celkove)
        "hemisphere_fraction_pct": 100.0 * celkove / canopen_den if canopen_den > 0 else 0.0,
        "total_pixels_in_circle": totpix,
        "total_pixels_in_frame": counts["visibpix"],
        "light_pixels": counts["lightpix"],
        "dark_pixels": max(0, totpix - counts["lightpix"]),
    }


# Geometría de la pantalla de análisis de GLAMA (comprobada con capturas de la app):
# la foto se muestra como RECORTE CUADRADO CENTRAL (lado = lado menor) escalado al ancho de
# la vista (1080 px) y centrado en una vista de 1080 × 1836 px; las franjas fuera de la foto
# dentro de la vista son negras y GLAMA las cuenta como píxeles oscuros (dosel).
GLAMA_VIEW_W = 1080
GLAMA_VIEW_H = 1836
# Centro del hemisferio de GLAMA respecto del centro de la vista (px de vista, + = hacia
# abajo). 39 px reproduce EXACTAMENTE dos pantallas de resultados de la app en el teléfono
# del autor: «(in Frame)» = 1 976 452 px con radio 1082 y «Part of Hemisph.» = 52.66 % con
# radio 1618. Depende del teléfono (disposición de la pantalla): ajústelo si hace falta.
GLAMA_CENTER_DY = 39.0


def glama_view_image(image_rgb, view_w=GLAMA_VIEW_W, view_h=GLAMA_VIEW_H, center_dy=GLAMA_CENTER_DY):
    """
    Reproduce la imagen que analiza GLAMA: recorte cuadrado central → view_w × view_w
    (bilineal) → centrado verticalmente en una vista negra de view_w × view_h.
    Devuelve (array RGB uint8 de view_h × view_w × 3, centro (x, y) del hemisferio), con el
    centro desplazado center_dy px hacia abajo respecto del centro de la vista.
    """
    from PIL import Image
    arr = np.asarray(image_rgb)
    h, w = arr.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    crop = Image.fromarray(np.ascontiguousarray(arr[y0:y0 + side, x0:x0 + side]))
    crop = crop.convert("RGB").resize((int(view_w), int(view_w)), Image.BILINEAR)
    view = np.zeros((int(view_h), int(view_w), 3), dtype=np.uint8)
    top = (int(view_h) - int(view_w)) // 2
    view[top:top + int(view_w), :, :] = np.asarray(crop)
    return view, (view_w / 2.0, view_h / 2.0 + float(center_dy))


def glama_cut_details(histogram, current_cut):
    """
    Nivel de corte recomendado (cruce de dos log-normales; procedimiento del «Recommended cut level»
    de la app GLAMA, Tichý 2016, manual Fig. 11) con los elementos intermedios:
      1. modos oscuro y claro buscados desde current_cut hacia abajo y hacia arriba (cada búsqueda
         se detiene cuando la frecuencia cae por debajo de 1/10 del máximo hallado);
      2. mínimo de frecuencia entre ambos modos (línea roja de la Fig. 11);
      3. corrección lineal por la distinta cantidad de píxeles a cada lado del mínimo;
      4. centro (escala logarítmica, oscuro medido desde 0 y claro desde 255) y dispersión de cada lado;
      5. corte = centro_oscuro + (centro_claro − centro_oscuro) · disp_oscuro / (disp_oscuro + disp_claro).
    Devuelve dict {cut (int 1–254 o None), dark_peak, bright_peak, valley, h_dark, h_bright, h_valley}.
    """
    out = {"cut": None, "dark_peak": None, "bright_peak": None, "valley": None,
           "h_dark": 0.0, "h_bright": 0.0, "h_valley": 0.0}
    ppx = np.zeros(257, dtype=np.float64)
    hist = np.asarray(histogram, dtype=np.float64)
    ppx[:min(256, hist.size)] = hist[:256]
    ired = max(1, min(255, int(current_cut)))

    meanik1, errik1 = 0.0, 0
    for a in range(ired, 0, -1):
        if meanik1 < ppx[a]:
            meanik1, errik1 = ppx[a], a
        if meanik1 > 1.0 + 10.0 * ppx[a]:
            break
    meanik2, errik2 = 0.0, 0
    for a in range(ired, 256):
        if meanik2 < ppx[a]:
            meanik2, errik2 = ppx[a], a
        if meanik2 > 1.0 + 10.0 * ppx[a]:
            break

    minik, pocminik = 1.0e8, 0
    for a in range(errik1, errik2):
        if minik > ppx[a]:
            minik, pocminik = ppx[a], a
    out.update(dark_peak=errik1, bright_peak=errik2, valley=pocminik, h_dark=float(meanik1),
               h_bright=float(meanik2), h_valley=float(minik if minik < 1.0e8 else 0.0))
    soum1 = float(ppx[errik1:pocminik].sum()) if pocminik > errik1 else 0.0
    soum2 = float(ppx[pocminik + 1:errik2 + 1].sum()) if errik2 > pocminik else 0.0
    if errik2 == errik1 or soum1 <= 0.0:
        return out
    stopa = ((soum2 - soum1) / float(errik2 - errik1)) / soum1
    sanitka = 1.0
    for a in range(errik1, errik2):
        ppx[a] = (ppx[a] - minik / 2.0) * sanitka
        sanitka += stopa

    odch1 = pocodch1 = manik1 = 0.0
    for a in range(errik1, pocminik):
        d = max(ppx[a], 0.0)
        odch1 += 2.0 * d * (a - errik1) ** 2
        manik1 += math.log(a + 1) * d
        pocodch1 += 2.0 * d
    odch3 = pocodch2 = manik3 = 0.0
    for a in range(errik2, pocminik, -1):
        d = max(ppx[a], 0.0)
        manik3 += math.log(256 - a) * d
        odch3 += 2.0 * d * (a - errik2) ** 2
        pocodch2 += 2.0 * d
    if pocodch1 <= 0.0 or pocodch2 <= 0.0:
        return out
    odch2 = math.sqrt(odch1 / pocodch1)
    odch4 = math.sqrt(odch3 / pocodch2)
    if odch2 + odch4 <= 0.0:
        return out
    manik2 = math.exp((manik1 / pocodch1) * 2.0)
    res = manik2 + ((256.0 - math.exp((manik3 / pocodch2) * 2.0)) - manik2) * (
        odch2 / (odch2 + odch4)
    )
    if not math.isfinite(res):
        return out
    # Redondeo de la app = floor(x + 0.5); se limita al rango del control (1–254)
    out["cut"] = int(max(1, min(254, math.floor(res + 0.5))))
    return out


def glama_recommended_cut(histogram, current_cut):
    """Nivel de corte recomendado (int 1–254) o None; ver glama_cut_details."""
    return glama_cut_details(histogram, current_cut)["cut"]


GLAMA_CUT_START = 128


def glama_cut_iterated(gray, center_xy, radius_px, zenith_max_deg, calibration, projection,
                       start=None, max_iter=6):
    """
    Nivel de corte recomendado por GLAMA iterado desde «start» (128 por defecto) hasta
    estabilizarse (±1). Una sola pasada desde el nivel actual, como en la app, se queda en el
    mismo valor si ese nivel cae en una cola del histograma (p. ej. 21 → 21).
    """
    t = int(GLAMA_CUT_START if start is None else start)
    seen = []
    for _ in range(max_iter):
        counts = glama_ring_counts_with_gray(gray, t, center_xy, radius_px, zenith_max_deg,
                                             calibration=calibration, projection=projection)
        t_new = glama_recommended_cut(counts["histogram"], t)
        if t_new is None:
            return None
        seen.append(t_new)
        if abs(t_new - t) <= 1:
            return t_new
        t = t_new
    return seen[-1] if seen else None


def glama_cut_iterated_hist(histogram, start=None, max_iter=6):
    """Como glama_cut_iterated pero sobre un histograma ya calculado (no depende del corte)."""
    t = int(GLAMA_CUT_START if start is None else start)
    last = None
    for _ in range(max_iter):
        t_new = glama_recommended_cut(histogram, t)
        if t_new is None:
            return None
        last = t_new
        if abs(t_new - t) <= 1:
            return t_new
        t = t_new
    return last


CUT_CHECK_STARTS = (96, 160, 192)
CUT_STABILITY_UNITS = 2
CUT_MIN_CLASS_PCT = 0.5          # % mínimo de píxeles de cielo y de dosel
CUT_VALLEY_RATIO = 0.5           # el mínimo debe ser ≤ 50 % del modo menor


def glama_cut_diagnosis(histogram, start=None):
    """
    Nivel de corte recomendado y comprobación de que el método funcionó (dos modos con un mínimo
    entre ellos, algo de cielo y de dosel, y el mismo resultado desde otros puntos de partida).
    Devuelve dict {cut, ok, reasons [str], starts {inicio: corte}, details, sky_pct}.
    """
    hist = np.asarray(histogram, dtype=np.float64)[:256]
    total = float(hist.sum())
    start = int(GLAMA_CUT_START if start is None else start)
    cut = glama_cut_iterated_hist(hist, start)
    res = {"cut": cut, "ok": False, "reasons": [], "starts": {start: cut}, "details": None, "sky_pct": None}
    if cut is None or total <= 0:
        res["reasons"].append("sin recomendación (el histograma no tiene dos modos)")
        return res
    det = glama_cut_details(hist, cut)
    res["details"] = det
    sky_pct = 100.0 * float(hist[cut:].sum()) / total
    res["sky_pct"] = sky_pct
    first = glama_recommended_cut(hist, start)
    if first == start and det["dark_peak"] is not None and not (det["dark_peak"] < cut < det["bright_peak"]):
        res["reasons"].append("la búsqueda no salió del punto de partida")
    if not (det["dark_peak"] is not None and det["bright_peak"] is not None
            and det["dark_peak"] < cut < det["bright_peak"]):
        res["reasons"].append("el corte no queda entre un modo oscuro y uno claro")
    else:
        sm = np.convolve(hist, np.ones(5) / 5.0, mode="same")
        lo, hi = det["dark_peak"], det["bright_peak"]
        valley = float(sm[lo:hi + 1].min())
        smaller = min(float(sm[lo]), float(sm[hi]))
        if smaller <= 0 or valley > CUT_VALLEY_RATIO * smaller:
            res["reasons"].append("no hay un mínimo claro entre el modo oscuro y el claro")
    if sky_pct < CUT_MIN_CLASS_PCT:
        res["reasons"].append("casi sin cielo ({:.2f} % de píxeles claros)".format(sky_pct))
    if 100.0 - sky_pct < CUT_MIN_CLASS_PCT:
        res["reasons"].append("casi sin dosel ({:.2f} % de píxeles oscuros)".format(100.0 - sky_pct))
    disagree = []
    for s0 in CUT_CHECK_STARTS:
        c2 = glama_cut_iterated_hist(hist, s0)
        res["starts"][s0] = c2
        if c2 is None:
            continue
        d2 = glama_cut_details(hist, c2)
        degenerate = not (d2["dark_peak"] is not None and d2["bright_peak"] is not None
                          and d2["dark_peak"] < c2 < d2["bright_peak"])
        if not degenerate and abs(c2 - cut) > CUT_STABILITY_UNITS:
            disagree.append("{}→{}".format(s0, c2))
    if disagree:
        res["reasons"].append("otro punto de partida da otro corte ({})".format(", ".join(disagree)))
    res["ok"] = not res["reasons"]
    return res
