"""
Análisis principal del dosel (versión GLAMA v3.0 para QGIS):
umbralización, máscara de horizonte artificial, métricas GLAMA (Tichý 2016) y LAI efectivo.

Referencias principales:
- Tichý, L. (2016). Field test of canopy cover estimation by hemispherical
  photographs taken with a smartphone. Journal of Vegetation Science, 27(2), 427–435.
  https://doi.org/10.1111/jvs.12350
- Tichý, L. (2015). GLAMA – Gap Light Analysis Mobile App. User's manual v3.0.
  Masaryk University, Brno. https://www.sci.muni.cz/botany/glama/GLAMA%20manual.pdf

Autor del complemento QGIS: Jorge Fallas (jfallas56@gmail.com)

Historial:
- 0.11.0 (CobDosel): compute_sector_gap_fractions() (fracción de claros por anillo × sector de
  acimut, al estilo del CI-110); analysis_circle_visibility() (porcentaje visible del círculo
  de análisis dentro de la foto).
- 0.10.0 (2026-10-17): LAI efectivo con rango cenital propio y estimador de Miller
  normalizado (antes se truncaba en la máscara de horizonte: −71 % a 45°);
  «(en el fotograma)» = intersección fotograma ∩ círculo virtual (Fig. 12J del manual);
  rejillas radio/cenit calculadas una sola vez en float32; scipy opcional (HAS_SCIPY).
  La «Fracción de claros del área seleccionada» se mantiene = claros / total del círculo
  virtual: verificado contra las 6 capturas de la Fig. 12 del Manual GLAMA v3.0.
- 0.9.0: versión inicial.
"""

import math
import numpy as np

try:
    from scipy import ndimage
    HAS_SCIPY = True
except ImportError:
    ndimage = None
    HAS_SCIPY = False

# Rango cenital por defecto para el LAI efectivo (independiente de la máscara de horizonte)
LAI_DEFAULT_ZENITH_MAX_DEG = 60.0
# Por debajo de este rango cenital el LAI se marca como «indicativo»
LAI_MIN_RELIABLE_ZENITH_DEG = 45.0


# ======================================================================
# Tabla 1 del Manual de GLAMA (Tichý 2015, pág. 7):
# Ángulos de máscara de horizonte (° sobre el horizonte) según tamaño de
# parcela y altura máxima del dosel cuando la foto se toma en el centro.
# Nota: ángulo_cenital_máx = 90° - ángulo_horizonte
# ======================================================================
GLAMA_HORIZON_MASK_TABLE = {
    "10x10": {10: 55, 15: 65, 20: 71, 30: 77, 40: 80},
    "15x15": {10: 44, 15: 55, 20: 63, 30: 71, 40: 76},
    "20x20": {10: 36, 15: 47, 20: 55, 30: 65, 40: 71},
    "25x25": {10: 30, 15: 41, 20: 49, 30: 60, 40: 67},
}


def recommended_horizon_mask_deg(plot_size_key, canopy_height_m):
    """
    Devuelve (horizon_mask_deg, zenith_max_deg) según la Tabla 1 de GLAMA.
    """
    row = GLAMA_HORIZON_MASK_TABLE.get(str(plot_size_key), {})
    horiz_deg = row.get(int(canopy_height_m))
    if horiz_deg is None:
        return 45.0, 45.0
    return float(horiz_deg), float(90 - horiz_deg)


# ======================================================================
# Selección de canal de color (Sección 7 del Manual de GLAMA, Fig. 8)
# ======================================================================
def extract_channel(image_array, channel_mode="blue_red"):
    """
    Extrae una imagen monocanal (uint8) para la clasificación cielo/dosel.
    """
    if image_array.ndim == 2:
        return image_array.astype(np.uint8)

    r = image_array[:, :, 0].astype(np.float32)
    g = image_array[:, :, 1].astype(np.float32)
    b = image_array[:, :, 2].astype(np.float32)

    if channel_mode == "red":
        return r.astype(np.uint8)
    if channel_mode == "green":
        return g.astype(np.uint8)
    if channel_mode == "blue":
        return b.astype(np.uint8)
    if channel_mode == "blue_red":
        return ((b + r) / 2.0).astype(np.uint8)
    if channel_mode == "all_rgb":
        return ((r + g + b) / 3.0).astype(np.uint8)
    if channel_mode == "excess_blue":
        return np.clip(2.0 * b - r, 0, 255).astype(np.uint8)
    # Por defecto: luminancia en escala de grises
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)


CHANNEL_MODES = [
    ("blue_red",    "Azul + Rojo (recomendado)"),
    ("blue",        "Solo azul"),
    ("all_rgb",     "Todos RGB"),
    ("grayscale",   "Escala de grises (luminancia ITU-R 601)"),
    ("red",         "Solo Rojo"),
    ("green",       "Solo Verde"),
    ("excess_blue", "Exceso de azul (2B − R)"),
]

CHANNEL_LABELS = dict(CHANNEL_MODES)


# ======================================================================
# Umbralización
# ======================================================================
def compute_otsu_threshold(gray_image, valid_mask=None):
    """Umbral de Otsu vectorizado en NumPy. Rápido (<200 ms en 5 MP)."""
    if valid_mask is not None:
        flat = gray_image[valid_mask]
    else:
        flat = gray_image.ravel()

    if flat.size == 0:
        return 128

    target_size = 1_000_000
    if flat.size > target_size:
        step = max(1, flat.size // target_size)
        sample = flat[::step]
    else:
        sample = flat

    if sample.dtype != np.uint8:
        sample = sample.astype(np.uint8)

    hist = np.bincount(sample, minlength=256).astype(np.float64)

    total = hist.sum()
    if total == 0:
        return 128

    bin_values = np.arange(256, dtype=np.float64)
    cum_sum = np.cumsum(hist)
    cum_mean = np.cumsum(hist * bin_values)
    total_mean = cum_mean[-1]

    with np.errstate(divide="ignore", invalid="ignore"):
        w0 = cum_sum / total
        w1 = 1.0 - w0
        mu0 = cum_mean / cum_sum
        mu1 = (total_mean - cum_mean) / (total - cum_sum)
        variance_between = w0 * w1 * (mu0 - mu1) ** 2

    variance_between = np.nan_to_num(
        variance_between, nan=0.0, posinf=0.0, neginf=0.0
    )

    return int(np.clip(np.argmax(variance_between), 1, 254))


# Métodos automáticos de nivel de corte (código, etiqueta en la interfaz)
AUTO_THRESHOLD_METHODS = [
    ("otsu", "Otsu (1979)"),
    ("minimum", "Mínimo (Prewitt y Mendelsohn 1966)"),
]
AUTO_THRESHOLD_LABELS = dict(AUTO_THRESHOLD_METHODS)
MINIMUM_MAX_ITER = 10000
MINIMUM_MIN_CLASS_PCT = 0.5   # % mínimo de píxeles a cada lado del corte (igual que el recomendado)


def _sample_histogram(gray_image, valid_mask=None, target_size=1_000_000):
    """Histograma de 256 clases del área válida (muestreo regular si hay > 1 M de píxeles)."""
    flat = gray_image[valid_mask] if valid_mask is not None else gray_image.ravel()
    if flat.size == 0:
        return None
    if flat.size > target_size:
        flat = flat[::max(1, flat.size // target_size)]
    if flat.dtype != np.uint8:
        flat = flat.astype(np.uint8)
    return np.bincount(flat, minlength=256).astype(np.float64)


def _local_maxima_count(h):
    """Número de máximos locales (h[i-1] < h[i] > h[i+1]) del histograma."""
    return int(np.sum((h[1:-1] > h[:-2]) & (h[1:-1] > h[2:])))


def minimum_threshold_from_hist(hist, max_iter=MINIMUM_MAX_ITER):
    """
    Método del mínimo (Prewitt y Mendelsohn 1966; implementación de ImageJ «Minimum»):
    suaviza el histograma con medias móviles de 3 clases, repetidamente, hasta que quedan
    exactamente dos máximos locales; el nivel de corte es el mínimo entre ambos.
    Devuelve (nivel, iteraciones) o (None, iteraciones) si el histograma no llega a ser
    bimodal (p. ej. sin cielo o sin dosel).
    """
    h = np.asarray(hist, dtype=np.float64).copy()
    if h.size != 256 or h.sum() <= 0:
        return None, 0
    it = 0
    while _local_maxima_count(h) != 2:
        prev = h
        h = np.empty_like(prev)
        h[0] = (prev[0] + prev[1]) / 3.0
        h[1:-1] = (prev[:-2] + prev[1:-1] + prev[2:]) / 3.0
        h[-1] = (prev[-2] + prev[-1]) / 3.0
        it += 1
        if it > max_iter or _local_maxima_count(h) < 2 and np.ptp(h) <= 1e-12:
            return None, it
    # v0.14.23: el corte es el mínimo ENTRE los dos máximos. Buscar el primer mínimo local
    # desde la clase 1 (como ImageJ) fallaba con muchos píxeles en 0 (dosel saturado a negro):
    # la caída 0 → 1 se tomaba como mínimo y el corte quedaba en 1 (casi todo «cielo»).
    peaks = np.nonzero((h[1:-1] > h[:-2]) & (h[1:-1] > h[2:]))[0] + 1
    if peaks.size != 2:
        return None, it
    p1, p2 = int(peaks[0]), int(peaks[1])
    seg = h[p1:p2 + 1]
    i = p1 + int(np.argmin(seg))
    if not (p1 < i < p2):
        return None, it
    # Cada clase debe tener al menos MINIMUM_MIN_CLASS_PCT de los píxeles: con un solo modo
    # (sin cielo o sin dosel) el suavizado deja un «máximo» en una cola y el corte no tiene
    # sentido (p. ej. 177 con 99.99 % de píxeles por debajo).
    raw = np.asarray(hist, dtype=np.float64)
    below = 100.0 * float(raw[:i].sum()) / float(raw.sum())
    if below < MINIMUM_MIN_CLASS_PCT or 100.0 - below < MINIMUM_MIN_CLASS_PCT:
        return None, it
    return int(np.clip(i, 1, 254)), it


def compute_minimum_threshold(gray_image, valid_mask=None):
    """Nivel de corte por el método del mínimo en el área válida; None si no es bimodal."""
    hist = _sample_histogram(gray_image, valid_mask)
    if hist is None:
        return None
    return minimum_threshold_from_hist(hist)[0]


def compute_auto_threshold(gray_image, valid_mask=None, method="otsu"):
    """
    Nivel de corte automático con el método elegido.
    Devuelve (nivel, método_usado, nota). Si el método del mínimo no encuentra dos modos,
    se usa Otsu y la nota lo explica.
    """
    if method == "minimum":
        t = compute_minimum_threshold(gray_image, valid_mask)
        if t is not None:
            return t, "minimum", ""
        return (compute_otsu_threshold(gray_image, valid_mask), "otsu",
                "El histograma no tiene dos modos (cielo y dosel) separables por el método "
                "del mínimo; se usó Otsu. Revise el nivel de corte con la vista previa.")
    return compute_otsu_threshold(gray_image, valid_mask), "otsu", ""


def threshold_image(gray_image, threshold, sky_is_bright=True):
    """Clasifica la imagen en máscara binaria de cielo (True = claro) / dosel (False = oscuro).

    Igual que GLAMA: claro si valor ≥ nivel de corte (hasta v0.9.x era «>»).
    """
    if sky_is_bright:
        return (gray_image >= threshold).astype(bool)
    else:
        return (gray_image < threshold).astype(bool)


def clean_binary_mask(mask, iterations=1, do_open=True, do_close=True):
    """Aplica apertura y cierre morfológico para eliminar ruido de píxeles aislados.

    Advertencia: elimina también claros reales de 1–2 px (follaje fino), lo que
    sesga la cobertura hacia arriba. Sin scipy devuelve la máscara sin cambios.
    """
    if iterations <= 0 or not HAS_SCIPY:
        return mask
    if do_open:
        mask = ndimage.binary_opening(mask, iterations=iterations)
    if do_close:
        mask = ndimage.binary_closing(mask, iterations=iterations)
    return mask


# ======================================================================
# Anillos cenitales
# ======================================================================
def compute_radius_grid(image_shape, center_xy):
    """Rejilla float32 de distancias (px) al centro óptico, sin matrices int64 intermedias."""
    h, w = image_shape[:2]
    cx, cy = float(center_xy[0]), float(center_xy[1])
    yy, xx = np.ogrid[0:h, 0:w]
    dy2 = (yy.astype(np.float32) - np.float32(cy)) ** 2
    dx2 = (xx.astype(np.float32) - np.float32(cx)) ** 2
    return np.sqrt(dx2 + dy2, dtype=np.float32)


def compute_zenith_grid(r_px, calibration):
    """Rejilla float32 de ángulos cenitales (°) a partir de la rejilla de radios."""
    from .lens_calibration import pixel_radius_to_zenith
    return np.asarray(pixel_radius_to_zenith(r_px, calibration), dtype=np.float32)


def frame_circle_pixel_count(image_shape, center_xy, radius_px):
    """
    Número de píxeles del fotograma que caen dentro del círculo de radio radius_px
    (intersección rectángulo ∩ círculo), calculado fila a fila sin rejillas 2D.
    """
    h, w = image_shape[:2]
    if radius_px is None or radius_px <= 0:
        return 0
    cx, cy = float(center_xy[0]), float(center_xy[1])
    y = np.arange(h, dtype=np.float64)
    dy2 = (y - cy) ** 2
    half = np.sqrt(np.clip(float(radius_px) ** 2 - dy2, 0.0, None))
    x0 = np.clip(np.ceil(cx - half), 0, w)
    x1 = np.clip(np.floor(cx + half) + 1, 0, w)
    counts = np.where(dy2 <= float(radius_px) ** 2, np.clip(x1 - x0, 0, None), 0)
    return int(counts.sum())


def create_zenith_rings(image_shape, center_xy, calibration,
                        zenith_max_deg, n_rings=4, r_px=None, zenith_deg=None):
    """
    Crea una matriz de etiquetas de anillos cenitales concéntricos.

    r_px y zenith_deg (rejillas precalculadas) son opcionales; pasarlas evita
    recalcularlas cuando se generan varios conjuntos de anillos (cobertura y LAI).
    """
    from .lens_calibration import zenith_to_pixel_radius

    h, w = image_shape[:2]
    if r_px is None:
        r_px = compute_radius_grid(image_shape, center_xy)
    if zenith_deg is None:
        zenith_deg = compute_zenith_grid(r_px, calibration)

    max_r_px = zenith_to_pixel_radius(zenith_max_deg, calibration)

    boundaries = np.linspace(0.0, float(zenith_max_deg), int(n_rings) + 1)

    ring_labels = np.zeros((h, w), dtype=np.uint8)
    for i in range(n_rings):
        lo, hi = boundaries[i], boundaries[i + 1]
        if i == n_rings - 1:
            cond = (zenith_deg >= lo) & (zenith_deg <= hi) & (r_px <= max_r_px + 0.5)
        else:
            cond = (zenith_deg >= lo) & (zenith_deg < hi)
        ring_labels[cond] = i + 1

    ring_boundaries = [
        (float(boundaries[i]), float(boundaries[i + 1])) for i in range(n_rings)
    ]
    return ring_labels, ring_boundaries


# ======================================================================
# Cobertura y conteo exacto de píxeles según Manual de GLAMA (pág. 11 y Fig. 12)
# ======================================================================
def compute_canopy_cover(sky_mask, ring_labels, valid_mask=None,
                         calibration=None, precision_step=1, center_xy=None):
    """
    Calcula las fracciones de cobertura y conteos de píxeles por anillo y en el círculo.

    Implementa fielmente las definiciones de la Sección 9 (pág. 11 y Fig. 12) del Manual de GLAMA:
    - Total No. of Pixels in Circle: área en píxeles del círculo completo del hemisferio virtual
      (round(π * R_virtual²)), independiente de la máscara de horizonte definida.
    - (in Frame): número de píxeles del círculo del hemisferio que son visibles dentro del fotograma
      de la imagen (independiente de la máscara de horizonte). Si se dan calibration con
      virtual_radius_px y center_xy, se calcula como intersección fotograma ∩ círculo virtual;
      en caso contrario, como la suma de valid_mask.
    - No. of Light (Dark) Pixels:
      * Light Pixels = número de píxeles blancos (cielo) dentro del área visible no enmascarada.
      * Dark Pixels = Total No. of Pixels in Circle − Light Pixels (tal como especifica el manual
        de GLAMA pág. 11: "All masked 'white' pixels are counted as 'black'", razón por la cual en
        todas las capturas de GLAMA Light + Dark == Total No. of Pixels in Circle).
      * También se almacena unmasked_circle_pixels y unmasked_dark_pixels para consulta directa.
    """
    step = max(1, int(precision_step))
    scale_area = step * step

    if step > 1:
        sky_s = sky_mask[::step, ::step]
        rings_s = ring_labels[::step, ::step]
        valid_s = valid_mask[::step, ::step] if valid_mask is not None else None
    else:
        sky_s = sky_mask
        rings_s = ring_labels
        valid_s = valid_mask

    total_frame_pixels = int(sky_mask.size)
    in_rings = rings_s > 0

    if valid_s is not None:
        circle_valid = in_rings & valid_s
        visible_in_frame = int(valid_s.sum()) * scale_area
    else:
        circle_valid = in_rings
        visible_in_frame = int(in_rings.sum()) * scale_area

    sky_in_circle = sky_s & circle_valid

    unmasked_circle_pixels = int(circle_valid.sum()) * scale_area
    light_pixels = int(sky_in_circle.sum()) * scale_area
    unmasked_dark_pixels = max(0, unmasked_circle_pixels - light_pixels)

    # Círculo virtual completo del hemisferio (90°): round(π * R_virtual²) y su parte
    # visible en el fotograma (intersección rectángulo ∩ círculo).
    virtual_circle_pixels = visible_in_frame
    if calibration is not None and calibration.get("virtual_radius_px"):
        r_virt = float(calibration["virtual_radius_px"])
        virtual_circle_pixels = int(round(math.pi * (r_virt ** 2)))
        if center_xy is not None:
            visible_in_frame = frame_circle_pixel_count(
                sky_mask.shape, center_xy, r_virt
            )
        # El conteo discreto de píxeles puede superar a π·R² en O(R) px por redondeo.
        tolerance = max(10, int(0.01 * virtual_circle_pixels))
        visible_in_frame_check = max(visible_in_frame, unmasked_circle_pixels)
        if visible_in_frame_check > virtual_circle_pixels + tolerance:
            # Calibración incoherente (círculo virtual menor que lo visible): se informa
            # en lugar de forzar en silencio los píxeles oscuros a 0.
            raise ValueError(
                "Calibración incoherente: el círculo virtual de 90° ({} px) es menor que "
                "el área visible ({} px). Recalcule la calibración.".format(
                    virtual_circle_pixels, visible_in_frame_check
                )
            )
        visible_in_frame = min(visible_in_frame, virtual_circle_pixels)

    # En GLAMA (pág. 11 y Fig. 12): Dark Pixels = Total No. of Pixels in Circle - Light Pixels
    glama_dark_pixels = max(0, virtual_circle_pixels - light_pixels)

    overall_openness = (
        100.0 * light_pixels / unmasked_circle_pixels
        if unmasked_circle_pixels > 0 else 0.0
    )
    overall_cover = 100.0 - overall_openness

    n_rings = int(rings_s.max())
    per_ring = []

    for i in range(1, n_rings + 1):
        ring_mask = (rings_s == i) & circle_valid
        n_valid = int(ring_mask.sum()) * scale_area
        if n_valid == 0:
            per_ring.append({
                "ring": i,
                "cover_pct": None,
                "openness_pct": None,
                "gap_fraction": None,
                "cover_fraction": None,
                "n_pixels": 0,
                "n_light_pixels": 0,
                "n_dark_pixels": 0,
            })
            continue
        n_sky = int((sky_s & ring_mask).sum()) * scale_area
        n_canopy = max(0, n_valid - n_sky)
        openness = 100.0 * n_sky / n_valid
        cover = 100.0 - openness
        gap_fraction = n_sky / float(n_valid)
        cover_fraction = 1.0 - gap_fraction
        per_ring.append({
            "ring": i,
            "cover_pct": cover,
            "openness_pct": openness,
            "gap_fraction": gap_fraction,
            "cover_fraction": cover_fraction,
            "n_pixels": n_valid,
            "n_light_pixels": n_sky,
            "n_dark_pixels": n_canopy,
        })

    return {
        "overall_cover_pct": overall_cover,
        "overall_openness_pct": overall_openness,
        "total_pixels_in_circle": virtual_circle_pixels,
        "total_pixels_in_frame": visible_in_frame,
        "total_image_rect_pixels": total_frame_pixels,
        "unmasked_circle_pixels": unmasked_circle_pixels,
        "light_pixels": light_pixels,
        "dark_pixels": glama_dark_pixels,
        "unmasked_dark_pixels": unmasked_dark_pixels,
        "per_ring": per_ring,
    }


# ======================================================================
# Métricas canónicas del dosel y resultados completos de GLAMA (Tichý 2016)
# ======================================================================
def compute_canopy_metrics(per_ring_results, ring_boundaries, cover_summary=None,
                           half_fov_deg=90.0, threshold=128):
    """
    Calcula las métricas canónicas del dosel y todos los indicadores reportados por GLAMA
    (Tichý 2016, https://doi.org/10.1111/jvs.12350; Manual GLAMA v3.0, pág. 11 y Fig. 12):

    - Total No. of Pixels in Circle (in Frame): píxeles del círculo virtual del hemisferio
      (π * R_virtual²) y, entre paréntesis, píxeles visibles del círculo en el fotograma.
    - No. of Light (Dark) Pixels: píxeles claros (blancos) en el área no enmascarada y
      píxeles oscuros (Total en el círculo − Claros).
    - Gap Fraction of Selected Area (%): 100 * Light Pixels / Total No. of Pixels in Circle
      (π·R_virtual²). Aunque el texto del manual dice «within the visible part of the circle»,
      las 6 capturas de la Fig. 12 (Manual GLAMA v3.0) solo cuadran con el círculo total:
      p. ej. 12710/157633 = 8.06 % y 37486/3230173 = 1.16 % (con el fotograma serían 8.08 %
      y 12.59 %). También se reporta gap_fraction_unmasked_pct sobre el área analizada.
    - Part of Hemisphere Taken by Camera (%): (1 - cos(θ_max)) * 100.
    - Cut Level between Black and White Pixels (1-254): valor del umbral T.
    - Canopy Openness (%): ángulo sólido de cielo abierto / ángulo sólido del HEMISFERIO COMPLETO
      («Open sky area / whole hemisphere area»; lo enmascarado cuenta como obstruido). Verificado
      con la Fig. 12 B/D del Manual GLAMA v3.0 (programa lineal de factibilidad: la normalización
      al área no enmascarada es incompatible con los valores publicados).
    - Canopy Closure (%): 100 − Canopy Openness.
    - canopy_openness_analysed_pct: apertura normalizada solo al área analizada (0–θ_máx),
      criterio de CAnOPY (nombre anterior de CobDosel) ≤ 0.9.x, conservada como dato adicional.
    - canopy_cover_index_pct / modified_caco_index_pct: índices LINEALES de CAnOPY ≤ 0.10 (nombre anterior)
      (cf·cos θ·sin θ y cf·cos² θ·sin θ). Desde 0.10.0 el diálogo los sustituye por los del
      algoritmo de GLAMA (glama_engine.py: T^cos θ, anillos de 1/90 del radio) y conserva el
      lineal como «caco_linear_pct» para comparar con resultados antiguos.
    """
    n = len(ring_boundaries)
    hemi_frac_pct = compute_hemisphere_fraction(half_fov_deg)

    total_circle_px = 0
    total_frame_px = 0
    unmasked_circle_px = 0
    light_px = 0
    dark_px = 0
    unmasked_dark_px = 0

    if cover_summary is not None:
        total_circle_px = int(cover_summary.get("total_pixels_in_circle", 0))
        total_frame_px = int(cover_summary.get("total_pixels_in_frame", 0))
        unmasked_circle_px = int(
            cover_summary.get("unmasked_circle_pixels", total_circle_px)
        )
        light_px = int(cover_summary.get("light_pixels", 0))
        dark_px = int(cover_summary.get("dark_pixels", max(0, total_circle_px - light_px)))
        unmasked_dark_px = int(
            cover_summary.get("unmasked_dark_pixels", max(0, unmasked_circle_px - light_px))
        )
    else:
        for ring in per_ring_results:
            n_px = int(ring.get("n_pixels") or 0)
            gf = ring.get("gap_fraction")
            total_circle_px += n_px
            unmasked_circle_px += n_px
            if gf is not None:
                l_px = int(round(gf * n_px))
                light_px += l_px
                dark_px += (n_px - l_px)
                unmasked_dark_px += (n_px - l_px)
        total_frame_px = total_circle_px

    if n == 0:
        return {
            "total_pixels_in_circle": total_circle_px,
            "total_pixels_in_frame": total_frame_px,
            "unmasked_circle_pixels": unmasked_circle_px,
            "light_pixels": light_px,
            "dark_pixels": dark_px,
            "unmasked_dark_pixels": unmasked_dark_px,
            "gap_fraction_pct": 0.0,
            "gap_fraction_unmasked_pct": 0.0,
            "hemisphere_fraction_pct": hemi_frac_pct,
            "cut_level": int(threshold),
            "canopy_openness_pct": 0.0,
            "canopy_closure_pct": 0.0,
            "canopy_openness_analysed_pct": 0.0,
            "canopy_cover_pct": 0.0,
            "canopy_cover_index_pct": 0.0,
            "modified_caco_index_pct": 0.0,
        }

    # 1. Gap Fraction of Selected Area — verificada contra la Fig. 12 del Manual GLAMA v3.0:
    #    100 * Light Pixels / Total No. of Pixels in Circle
    if total_circle_px > 0:
        gap_fraction_selected_pct = 100.0 * light_px / float(total_circle_px)
    else:
        gap_fraction_selected_pct = 0.0

    if unmasked_circle_px > 0:
        gap_fraction_unmasked_pct = 100.0 * light_px / float(unmasked_circle_px)
    else:
        gap_fraction_unmasked_pct = gap_fraction_selected_pct

    # 2. Ponderaciones esféricas y de proyección horizontal por anillo
    openness_num = 0.0
    closure_num = 0.0
    solid_angle_den = 0.0

    caco_num = 0.0
    caco_den = 0.0

    mod_caco_num = 0.0
    mod_caco_den = 0.0

    for i, (lo, hi) in enumerate(ring_boundaries):
        cf = per_ring_results[i].get("cover_fraction")
        gf = per_ring_results[i].get("gap_fraction")
        if cf is None:
            continue
        if gf is None:
            gf = 1.0 - cf

        theta_lo = math.radians(lo)
        theta_hi = math.radians(hi)

        # Peso exacto de ángulo sólido del anillo: ∫ sin(θ) dθ = cos(θ_lo) - cos(θ_hi)
        sin_w = max(1e-12, math.cos(theta_lo) - math.cos(theta_hi))

        # Peso de proyección horizontal (CaCo Index): ∫ cos(θ) sin(θ) dθ = 0.5 * (sin²(θ_hi) - sin²(θ_lo))
        cos_sin_w = max(
            1e-12,
            0.5 * (math.sin(theta_hi) ** 2 - math.sin(theta_lo) ** 2),
        )

        # Peso de cobertura en proyección esférica (Modif. CaCo Index, Tichý 2016):
        # atenúa la sensibilidad a claros irregulares cerca del horizonte mediante ∫ cos²(θ) sin(θ) dθ
        cos2_sin_w = max(
            1e-12,
            (math.cos(theta_lo) ** 3 - math.cos(theta_hi) ** 3) / 3.0,
        )

        openness_num += gf * sin_w
        closure_num += cf * sin_w
        solid_angle_den += sin_w

        caco_num += cf * cos_sin_w
        caco_den += cos_sin_w

        mod_caco_num += cf * cos2_sin_w
        mod_caco_den += cos2_sin_w

    # Pesos sin θ ya normalizados al hemisferio: Σ(cos θ_lo − cos θ_hi) en 0–90° = 1
    openness_pct = 100.0 * openness_num
    closure_pct = 100.0 - openness_pct
    openness_analysed_pct = (
        100.0 * openness_num / solid_angle_den if solid_angle_den > 0 else 0.0
    )
    _ = closure_num  # cierre del área analizada = 100 − openness_analysed_pct
    caco_pct = 100.0 * caco_num / caco_den if caco_den > 0 else 0.0
    mod_caco_pct = (
        100.0 * mod_caco_num / mod_caco_den if mod_caco_den > 0 else 0.0
    )

    return {
        "total_pixels_in_circle": total_circle_px,
        "total_pixels_in_frame": total_frame_px,
        "unmasked_circle_pixels": unmasked_circle_px,
        "light_pixels": light_px,
        "dark_pixels": dark_px,
        "unmasked_dark_pixels": unmasked_dark_px,
        "gap_fraction_pct": gap_fraction_selected_pct,
        "gap_fraction_unmasked_pct": gap_fraction_unmasked_pct,
        "hemisphere_fraction_pct": hemi_frac_pct,
        "cut_level": int(threshold),
        "canopy_openness_pct": openness_pct,
        "canopy_closure_pct": closure_pct,
        "canopy_openness_analysed_pct": openness_analysed_pct,
        "canopy_cover_pct": caco_pct,
        "canopy_cover_index_pct": caco_pct,
        "modified_caco_index_pct": mod_caco_pct,
    }


# ======================================================================
# Clasificación del tipo de medición según el ángulo de visión
# ======================================================================
def classify_measurement_type(half_fov_deg, threshold_deg=30.0):
    """
    Clasifica el tipo de medición según el semiángulo de visión (half-FOV).
    Siguiendo a Tichý (2016), Paletto y Tosi (2009) y Bunnell y Vales (1990):
    - Semiángulo < 30° -> "cover" (Cobertura del dosel — proyección perpendicular)
    - Semiángulo >= 30° -> "closure" (Cierre del dosel — proyección hemisférica, reescalada mediante CaCo)
    """
    if half_fov_deg < threshold_deg:
        return {
            "type": "cover",
            "label": "Cobertura del dosel (proyección perpendicular)",
            "note": (
                "Ángulo de visión estrecho (semiángulo < 30°) — mide directamente la "
                "proyección perpendicular de las copas sobre una superficie "
                "horizontal. Comparable al densiómetro GRS y estimación visual."
            ),
        }
    else:
        return {
            "type": "closure",
            "label": "Cobertura del dosel mediante el Índice CaCo (Tichý 2016)",
            "note": (
                "Ángulo de visión amplio (semiángulo ≥ 30°). Como demuestra Tichý (2016, "
                "doi:10.1111/jvs.12350), el Índice CaCo reescala la "
                "proyección hemisférica a proyección perpendicular de copas, logrando un "
                "ajuste óptimo (pendiente ~1, intercepto ~0) frente a la estimación visual "
                "experta cuando se aplica una máscara de horizonte artificial > 45° (cenit ≤ 45°)."
            ),
        }


def compute_hemisphere_fraction(half_fov_deg):
    """
    Calcula la fracción del hemisferio celeste captada por la cámara (%).
    Fórmula: (1 - cos(half_FOV)) * 100
    """
    if half_fov_deg >= 90.0:
        return 100.0
    if half_fov_deg <= 0.0:
        return 0.0
    theta_rad = math.radians(half_fov_deg)
    return 100.0 * (1.0 - math.cos(theta_rad))


# ======================================================================
# Índice de Área Foliar Efectivo (LAI efectivo de Miller)
# ======================================================================
def compute_effective_lai(per_ring_results, ring_boundaries):
    """
    Calcula el LAI efectivo con la fórmula de Miller (1967) normalizada al rango cenital
    efectivamente observado.

    Miller: LAI_e = 2 ∫₀^{π/2} −ln T(θ) cos θ sin θ dθ solo es exacto si se integra el
    hemisferio completo. Integrar hasta θ_máx < 90° sin normalizar subestima el LAI en
    un factor (1 − cos θ_máx) (−71 % a 45°, error de v0.9.0). Aquí se usa:

        LAI_e = 2 · Σ(−ln Tᵢ · cos θᵢ · sin θᵢ · Δθᵢ) / Σ(sin θᵢ · Δθᵢ)

    que es exacto para una distribución esférica de ángulos foliares (G = 0.5) en
    cualquier rango cenital, y se reduce a Miller cuando θ_máx = 90°. Para otras
    distribuciones el sesgo crece al reducir el rango; por debajo de
    LAI_MIN_RELIABLE_ZENITH_DEG el resultado se marca como indicativo.

    Si un anillo está totalmente cubierto (T = 0) se usa T_min = 0.5 / n_pixels.
    Anillos sin píxeles válidos se excluyen del numerador y del denominador.

    Devuelve lai_per_ring como contribución normalizada de cada anillo (suman lai_effective).
    """
    terms = []
    den = 0.0
    zen_max = 0.0
    for ring, (lo, hi) in zip(per_ring_results, ring_boundaries):
        T = ring.get("gap_fraction")
        n_pixels = int(ring.get("n_pixels") or 0)
        theta_mid = math.radians((lo + hi) / 2.0)
        dtheta = math.radians(hi - lo)

        if T is None or n_pixels <= 0:
            terms.append(None)
            continue
        zen_max = max(zen_max, float(hi))
        den += math.sin(theta_mid) * dtheta
        if T >= 1.0:
            terms.append(0.0)
        else:
            t_eff = T if T > 0.0 else (0.5 / float(max(1, n_pixels)))
            terms.append(
                2.0 * math.log(1.0 / t_eff)
                * math.cos(theta_mid) * math.sin(theta_mid) * dtheta
            )

    if den <= 0.0:
        lai_per_ring = [0.0 for _ in terms]
        lai_total = 0.0
    else:
        lai_per_ring = [(t / den) if t is not None else 0.0 for t in terms]
        lai_total = float(sum(lai_per_ring))

    return {
        "lai_effective": lai_total,
        "lai_per_ring": lai_per_ring,
        "lai_zenith_max_deg": zen_max,
        "lai_method": "Miller (1967) normalizado al rango 0–{:.1f}°".format(zen_max),
        "lai_reliable": zen_max >= LAI_MIN_RELIABLE_ZENITH_DEG,
    }


# ======================================================================
# Sectores de acimut y visibilidad del círculo de análisis (v0.11.0)
# ======================================================================
def azimuth_grid(image_shape, center_xy):
    """Acimut (°) de cada píxel desde «arriba» de la imagen, sentido horario (como GLAMA)."""
    h, w = image_shape[:2]
    yy, xx = np.ogrid[0:h, 0:w]
    dx = (xx - float(center_xy[0])).astype(np.float32)
    dy = (yy - float(center_xy[1])).astype(np.float32)
    return np.mod(np.degrees(np.arctan2(dx, -dy)), 360.0).astype(np.float32)


def compute_sector_gap_fractions(sky_mask, valid_mask, zenith_deg, az_deg,
                                 ring_boundaries, n_sectors=8):
    """
    Fracción de claros por anillo cenital × sector de acimut (sector 1 = arriba, horario).

    Devuelve una lista de dicts: ring, ring_lo, ring_hi, sector, az_lo, az_hi,
    n_pixels, n_light, gap_pct (None si el sector no tiene píxeles visibles).
    """
    n_sectors = int(n_sectors)
    if n_sectors < 1:
        return []
    valid = np.ones(sky_mask.shape, dtype=bool) if valid_mask is None else valid_mask
    sector_idx = np.minimum((az_deg / (360.0 / n_sectors)).astype(np.int32), n_sectors - 1)
    out = []
    n_rings = len(ring_boundaries)
    for i, (lo, hi) in enumerate(ring_boundaries):
        if i == n_rings - 1:
            in_ring = (zenith_deg >= lo) & (zenith_deg <= hi)
        else:
            in_ring = (zenith_deg >= lo) & (zenith_deg < hi)
        in_ring &= valid
        sec = sector_idx[in_ring]
        light = sky_mask[in_ring]
        tot = np.bincount(sec, minlength=n_sectors)
        lit = np.bincount(sec, weights=light.astype(np.float64), minlength=n_sectors)
        for k in range(n_sectors):
            n_px = int(tot[k])
            out.append({
                "ring": i + 1, "ring_lo": float(lo), "ring_hi": float(hi),
                "sector": k + 1,
                "az_lo": k * 360.0 / n_sectors, "az_hi": (k + 1) * 360.0 / n_sectors,
                "n_pixels": n_px, "n_light": int(lit[k]),
                "gap_pct": (100.0 * float(lit[k]) / n_px) if n_px > 0 else None,
            })
    return out


def analysis_circle_visibility(image_shape, center_xy, radius_px):
    """
    Porcentaje del círculo de análisis (radio en px) que cae dentro de la foto.
    100 % = el círculo completo está en la imagen; < 100 % = parte del círculo queda fuera
    (esos píxeles se excluyen; GLAMA los cuenta como dosel si caen en su vista).
    """
    r = float(radius_px)
    if r <= 0:
        return 100.0
    inside = frame_circle_pixel_count(image_shape, center_xy, r)
    return min(100.0, 100.0 * inside / (math.pi * r * r))
