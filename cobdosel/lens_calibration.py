"""Calibración de lentes ojo de pez y cámaras regulares de teléfonos inteligentes.

Soporta seis modelos de proyección:
- polar (equidistante)     r = f * θ                 — mayoría de lentes ojo de pez
- equisolid (igual área)   r = 2f * sin(θ/2)         — ojo de pez moderno
- orthographic             r = f * sin(θ)            — ojo de pez clásico
- stereographic            r = 2f * tan(θ/2)         — algunos ojo de pez / gran angular
- rectilinear              r = f * tan(θ)            — lente regular (geométrico)
- angular                  r = r_half * (θ / θ_max)  — lineal (≡ «Polar» de GLAMA), lente regular

Nota sobre la nomenclatura de GLAMA (Manual v3.0, cap. 7): su «Polar» es equidistante
(recomendada para cámaras integradas) y su «Angular» comprime los ángulos cenitales altos
(ojos de pez externos); la Fig. 12F es coherente con una proyección ortográfica. El código
interno "angular" de CobDosel se conserva por compatibilidad con calibraciones guardadas, pero
matemáticamente es lineal (equivalente a "polar" anclado al círculo inscrito).

v0.11.0 (CobDosel):
- La proyección lineal ("angular") ya no se recorta en θ_máx (semiángulo del lado corto):
  se extiende linealmente hasta 90°, de modo que las esquinas de la foto y los anillos
  parcialmente visibles hasta la máscara de horizonte tienen su ángulo cenital real.
- Nueva clave «max_zenith_frame_deg»: ángulo cenital en la esquina más lejana del fotograma.
- calibrate_from_glama_radius(): calibración a partir del «Hemisph. radius» de la app GLAMA
  (pantalla de 1080 px; la pantalla de análisis muestra el recorte cuadrado central de la foto).

v0.10.0 (2026-10-17):
- Alias de proyección sin entradas inalcanzables; excepción acotada en el cálculo de θ_máx.

v0.9.0:
- Corrige el factor 2x en el cálculo de θ_max para proyección angular (usa el
  semiángulo cenital θ_ref_half = atan(D / 2H) de forma consistente).
- Escala automáticamente los radios y longitudes focales cuando una calibración
  se aplica a una imagen de distinta resolución (p. ej. imagen reescalada vs. original).
- Preserva center_xy y los parámetros físicos del círculo de referencia.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import math
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


PROJECTIONS = {
    "polar": {
        "label": "Polar (equidistante)",
        "forward": lambda f, theta: f * theta,
        "inverse": lambda f, r: r / f,
        "f_from_ref": lambda r_ref, theta_ref_half: r_ref / theta_ref_half,
        "virtual_radius": lambda f: f * (math.pi / 2.0),
        "note": "Nikkor 8mm f/2.8 y la mayoría de lentes ojo de pez científicos (r = f·θ).",
        "fisheye": True,
    },
    "equisolid": {
        "label": "Equisólida (igual área)",
        "forward": lambda f, theta: 2.0 * f * math.sin(theta / 2.0),
        "inverse": lambda f, r: 2.0 * math.asin(
            min(max(r / (2.0 * f), -1.0), 1.0)
        ),
        "f_from_ref": lambda r_ref, theta_ref_half: r_ref / (
            2.0 * math.sin(theta_ref_half / 2.0)
        ),
        "virtual_radius": lambda f: f * math.sqrt(2.0),
        "note": "Nikkor 10.5mm, Sigma 8mm y la mayoría de lentes ojo de pez modernos (r = 2f·sin(θ/2)).",
        "fisheye": True,
    },
    "orthographic": {
        "label": "Ortográfica",
        "forward": lambda f, theta: f * math.sin(theta),
        "inverse": lambda f, r: math.asin(min(max(r / f, -1.0), 1.0)),
        "f_from_ref": lambda r_ref, theta_ref_half: r_ref / math.sin(theta_ref_half),
        "virtual_radius": lambda f: f,
        "note": "Diseños clásicos de ojo de pez (r = f·sin(θ)).",
        "fisheye": True,
    },
    "stereographic": {
        "label": "Estereográfica",
        "forward": lambda f, theta: 2.0 * f * math.tan(theta / 2.0),
        "inverse": lambda f, r: 2.0 * math.atan(r / (2.0 * f)),
        "f_from_ref": lambda r_ref, theta_ref_half: r_ref / (
            2.0 * math.tan(theta_ref_half / 2.0)
        ),
        "virtual_radius": lambda f: f * 2.0,
        "note": "Algunos lentes ojo de pez y gran angular (r = 2f·tan(θ/2)).",
        "fisheye": True,
    },
    "rectilinear": {
        "label": "Rectilínea (geométrica)",
        "forward": lambda f, theta: f * math.tan(theta),
        "inverse": lambda f, r: math.atan(r / f),
        "f_from_ref": lambda r_ref, theta_ref_half: r_ref / math.tan(theta_ref_half),
        "virtual_radius": lambda f: None,
        "note": ("Cámara principal (1x) de los teléfonos y lentes regulares que conservan rectas las líneas "
                 "rectas: r = f·tan θ. La calibración da la distancia focal f; con una lente rectilínea es "
                 "exacta en todos los ángulos y con cualquier tamaño de círculo."),
        "fisheye": False,
    },
    "angular": {
        "label": "Lineal (compatible con Polar de GLAMA)",
        "forward": None,
        "inverse": None,
        "f_from_ref": None,
        "virtual_radius": None,
        "note": (
            "El ángulo cenital crece en proporción a la distancia al centro (θ ∝ r), anclado en el "
            "borde del círculo de calibración: exacto en ese ángulo y aproximado fuera de él. "
            "Equivale al modelo «Polar» de GLAMA; úselo para comparar con GLAMA o con "
            "calibraciones anteriores hechas con este modelo."
        ),
        "fisheye": False,
    },
}


# Las claves usan "_" porque normalize_projection() sustituye "-" por "_" antes de buscar.
PROJECTION_ALIASES = {
    "equi_solid": "equisolid",
    "equal_area": "equisolid",
    "equisólida": "equisolid",
    "equisolida": "equisolid",
    "equidistant": "polar",
    "equidistante": "polar",
    "equi_distortion": "equisolid",
    "angle_true": "equisolid",
    "ortográfica": "orthographic",
    "ortografica": "orthographic",
    "estereográfica": "stereographic",
    "estereografica": "stereographic",
    "rectilínea": "rectilinear",
    "rectilinea": "rectilinear",
}


def normalize_projection(name):
    """Convierte nombres legibles de proyección a códigos internos."""
    if not name:
        return "polar"
    key = name.lower().split("(")[0].strip()
    key = key.replace("-", "_")
    if key in PROJECTIONS:
        return key
    if key in PROJECTION_ALIASES:
        return PROJECTION_ALIASES[key]
    for alias, code in PROJECTION_ALIASES.items():
        if alias in key:
            return code
    for code in PROJECTIONS:
        if code in key:
            return code
    raise ValueError("Proyección desconocida: " + str(name))


# ----------------------------------------------------------------------
# Funciones auxiliares para proyección angular
# ----------------------------------------------------------------------
def _angular_forward(theta, theta_max, r_image_half):
    """Ángulo cenital (rad) -> radio en píxeles."""
    if r_image_half is None or r_image_half <= 0:
        raise ValueError("La proyección angular requiere r_image_half > 0.")
    if theta <= 0:
        return 0.0
    # Lineal hasta 90° (sin recorte en θ_máx): r ∝ θ también fuera del círculo inscrito
    return r_image_half * (min(theta, math.pi / 2.0) / theta_max)


def _angular_inverse(r, theta_max, r_image_half):
    """Radio en píxeles -> ángulo cenital (rad)."""
    if r_image_half is None or r_image_half <= 0:
        raise ValueError("La proyección angular requiere r_image_half > 0.")
    if r <= 0:
        return 0.0
    theta = theta_max * (r / r_image_half)
    return min(theta, math.pi / 2.0)


def _angular_f_from_ref(r_ref, theta_ref_half):
    """Longitud focal equivalente (px/rad) para reporte."""
    if theta_ref_half <= 0:
        raise ValueError("El ángulo de referencia debe ser positivo.")
    return r_ref / theta_ref_half


# ----------------------------------------------------------------------
# Detección automática de círculo ojo de pez
# ----------------------------------------------------------------------
def detect_fisheye_circle(image_array):
    """Detecta automáticamente el borde circular de un lente ojo de pez con Hough."""
    if not HAS_CV2:
        return None

    if image_array.ndim == 3:
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_array

    gray = cv2.medianBlur(gray, 5)
    h, w = gray.shape
    min_radius = int(min(h, w) * 0.30)
    max_radius = int(min(h, w) * 0.55)

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min(h, w),
        param1=100,
        param2=30,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    if circles is None:
        return None

    circles = np.round(circles[0, :]).astype("int")
    cx_img, cy_img = w / 2.0, h / 2.0
    best = min(
        circles,
        key=lambda c: (c[0] - cx_img) ** 2 + (c[1] - cy_img) ** 2,
    )
    return int(best[0]), int(best[1]), int(best[2])


# ----------------------------------------------------------------------
# Calibración
# ----------------------------------------------------------------------
def calibrate_regular_lens(circle_diameter_cm, camera_height_cm,
                           pixel_diameter_px, image_width_px, image_height_px,
                           projection="angular", glama_compat=False):
    """
    Calibra un lente regular (o ojo de pez) usando un círculo de diámetro conocido.

    Geometría:
    - Radio físico del círculo: R_cm = circle_diameter_cm / 2
    - Semiángulo cenital al borde del círculo: θ_ref_half = atan(R_cm / camera_height_cm)
    - Ángulo de apertura total del círculo: θ_ref_full = 2 * θ_ref_half
    """
    projection = normalize_projection(projection)

    if circle_diameter_cm <= 0 or camera_height_cm <= 0 or pixel_diameter_px <= 0:
        raise ValueError("Todos los valores de entrada deben ser positivos.")

    # Semiángulo cenital (desde el eje óptico hasta el borde del círculo).
    # Exacto: atan(D / 2H). Compatible con GLAMA (botón «Calculate» de la pantalla de calibración):
    # atan(D / H) / 2, aproximación que sobrestima el radio del hemisferio
    # (+1 % con D/H = 0.2; +5 % con 0.475; +10.6 % con 0.714, ejemplo de la Fig. 6D).
    if glama_compat:
        theta_ref_half_rad = math.atan(circle_diameter_cm / camera_height_cm) / 2.0
    else:
        theta_ref_half_rad = math.atan(circle_diameter_cm / (2.0 * camera_height_cm))
    theta_ref_half_deg = math.degrees(theta_ref_half_rad)
    theta_ref_full_deg = 2.0 * theta_ref_half_deg

    r_ref_px = pixel_diameter_px / 2.0
    half_w = image_width_px / 2.0
    half_h = image_height_px / 2.0
    r_image_half = min(half_w, half_h)
    center_xy = [half_w, half_h]

    proj = PROJECTIONS[projection]

    # ------------------------------------------------------------------
    # Proyección angular (estilo GLAMA)
    # ------------------------------------------------------------------
    if projection == "angular":
        # El borde del círculo de referencia está a r_ref_px con ángulo cenital theta_ref_half_rad.
        # Por tanto, en el borde del círculo inscrito (r_image_half), el ángulo cenital máximo es:
        theta_max_rad = theta_ref_half_rad * (r_image_half / r_ref_px)
        theta_max_deg = math.degrees(theta_max_rad)

        if theta_max_deg > 90.0:
            # v0.14.38: antes se limitaba a 90° y el borde del círculo de referencia dejaba de estar en
            # su ángulo (p. ej. 12° en lugar de 51°). Un ángulo mayor que 90° en el borde del lado corto
            # es imposible con una lente regular: D, H o el diámetro medido están mal.
            raise ValueError(
                "Con estos valores el borde del lado corto de la foto quedaría a {:.0f}° del cenit (más de 90°): "
                "revise el diámetro real D, la distancia H y el diámetro medido en píxeles.".format(theta_max_deg))
        if theta_max_deg < 1.0:
            raise ValueError(
                "El semiángulo de visión calculado es demasiado pequeño ({:.2f}°). "
                "Verifique las mediciones del círculo de referencia.".format(theta_max_deg)
            )

        f_virtual = _angular_f_from_ref(r_ref_px, theta_ref_half_rad)
        R_virtual = r_image_half * (90.0 / theta_max_deg)
        frame_max_deg = min(90.0, 90.0 * math.hypot(half_w, half_h) / R_virtual)

        return {
            "lens_type": "regular",
            "angular_size_deg": theta_ref_full_deg,
            "zenith_ref_deg": theta_ref_half_deg,
            "focal_length_px": f_virtual,
            "virtual_radius_px": R_virtual,
            "max_zenith_deg": theta_max_deg,
            "max_zenith_frame_deg": frame_max_deg,
            "full_fov_deg": 2.0 * theta_max_deg,
            "theta_max_rad": theta_max_rad,
            "r_image_half_px": r_image_half,
            "r_ref_px": r_ref_px,
            "circle_diameter_cm": float(circle_diameter_cm),
            "camera_height_cm": float(camera_height_cm),
            "pixel_diameter_px": float(pixel_diameter_px),
            "center_xy": center_xy,
            "projection": "angular",
            "projection_label": proj["label"],
            "image_width_px": int(image_width_px),
            "image_height_px": int(image_height_px),
            "glama_compat": bool(glama_compat),
            # Máscara recomendada por GLAMA: cenit en la mitad del lado corto de la imagen
            "glama_recommended_horizon_deg": round(90.0 - theta_max_deg, 1),
        }

    # ------------------------------------------------------------------
    # Proyecciones estándar
    # ------------------------------------------------------------------
    f_px = proj["f_from_ref"](r_ref_px, theta_ref_half_rad)
    virtual_radius_px = proj["virtual_radius"](f_px)

    if projection == "rectilinear":
        max_zenith_rad = math.atan(r_image_half / f_px)
        max_zenith_deg = math.degrees(max_zenith_rad)
        if virtual_radius_px is None:
            virtual_radius_px = r_image_half * (90.0 / max_zenith_deg) if max_zenith_deg > 0 else r_image_half
    else:
        # Para proyecciones ojo de pez calibradas con círculo de referencia,
        # calculamos el ángulo cenital alcanzable en el círculo inscrito si es menor que 90°
        try:
            inv_rad = proj["inverse"](f_px, r_image_half)
            max_zenith_deg = min(90.0, math.degrees(inv_rad))
        except (ValueError, ZeroDivisionError):
            max_zenith_deg = 90.0
    try:
        frame_max_deg = min(90.0, math.degrees(proj["inverse"](f_px, math.hypot(half_w, half_h))))
    except (ValueError, ZeroDivisionError):
        frame_max_deg = 90.0

    return {
        "lens_type": "fisheye" if proj["fisheye"] else "regular",
        "angular_size_deg": theta_ref_full_deg,
        "zenith_ref_deg": theta_ref_half_deg,
        "focal_length_px": f_px,
        "max_zenith_deg": max_zenith_deg,
        "max_zenith_frame_deg": frame_max_deg,
        "full_fov_deg": 2.0 * max_zenith_deg,
        "theta_max_rad": math.radians(max_zenith_deg),
        "virtual_radius_px": virtual_radius_px,
        "r_image_half_px": r_image_half,
        "r_ref_px": r_ref_px,
        "circle_diameter_cm": float(circle_diameter_cm),
        "camera_height_cm": float(camera_height_cm),
        "pixel_diameter_px": float(pixel_diameter_px),
        "center_xy": center_xy,
        "projection": projection,
        "projection_label": proj["label"],
        "image_width_px": int(image_width_px),
        "image_height_px": int(image_height_px),
        "glama_compat": bool(glama_compat),
        "glama_recommended_horizon_deg": round(90.0 - max_zenith_deg, 1),
    }


GLAMA_VIEW_WIDTH_PX = 1080   # ancho de la vista de la app GLAMA (pantalla de análisis)


def calibrate_from_glama_radius(glama_radius_px, image_width_px, image_height_px,
                                glama_view_width_px=GLAMA_VIEW_WIDTH_PX,
                                scale_side="short", glama_projection="polar"):
    """
    Calibración a partir del radio del hemisferio de la app GLAMA («Hemisph. radius»).

    GLAMA expresa el radio en píxeles de su vista (1080 px de ancho). En la pantalla de
    análisis la app muestra el RECORTE CUADRADO CENTRAL de la foto (lado = lado menor), de
    modo que «short» (por defecto) reproduce la geometría con que GLAMA calcula sus
    resultados: R_foto = R_GLAMA × lado_menor / 1080. «long» usa el lado mayor (escala de la
    pantalla de calibración cuando la foto del círculo se muestra a lo ancho); en fotos 4:3
    ambas difieren en 4/3.

    glama_projection: "polar" (equidistante, cámaras integradas) u "angular" (GLAMA;
    equivale a ortográfica, r = R·sin θ).
    """
    if glama_radius_px <= 0 or glama_view_width_px <= 0:
        raise ValueError("El radio de GLAMA y el ancho de la vista deben ser positivos.")
    w, h = float(image_width_px), float(image_height_px)
    side = min(w, h) if scale_side == "short" else max(w, h)
    R = float(glama_radius_px) * side / float(glama_view_width_px)
    half_w, half_h = w / 2.0, h / 2.0
    r_image_half = min(half_w, half_h)
    corner = math.hypot(half_w, half_h)
    common = {
        "lens_type": "regular",
        "virtual_radius_px": R,
        "r_image_half_px": r_image_half,
        "center_xy": [half_w, half_h],
        "image_width_px": int(image_width_px),
        "image_height_px": int(image_height_px),
        "calibration_method": "glama_radius",
        "glama_radius_px": float(glama_radius_px),
        "glama_view_width_px": float(glama_view_width_px),
        "glama_scale_side": scale_side,
        "glama_compat": True,
    }
    if glama_projection == "polar":
        theta_max_deg = min(90.0, 90.0 * r_image_half / R)
        cal = {
            "focal_length_px": R / (math.pi / 2.0),
            "max_zenith_deg": theta_max_deg,
            "max_zenith_frame_deg": min(90.0, 90.0 * corner / R),
            "full_fov_deg": 2.0 * theta_max_deg,
            "theta_max_rad": math.radians(theta_max_deg),
            "projection": "angular",
            "projection_label": PROJECTIONS["angular"]["label"],
        }
    else:
        theta_max_deg = math.degrees(math.asin(min(1.0, r_image_half / R)))
        cal = {
            "focal_length_px": R,
            "max_zenith_deg": theta_max_deg,
            "max_zenith_frame_deg": math.degrees(math.asin(min(1.0, corner / R))),
            "full_fov_deg": 2.0 * theta_max_deg,
            "theta_max_rad": math.radians(theta_max_deg),
            "projection": "orthographic",
            "projection_label": PROJECTIONS["orthographic"]["label"],
        }
    cal.update(common)
    cal["glama_recommended_horizon_deg"] = round(90.0 - cal["max_zenith_deg"], 1)
    return cal


def glama_equivalent_radius(calibration, image_width_px, image_height_px,
                            glama_view_width_px=GLAMA_VIEW_WIDTH_PX):
    """Radio del hemisferio expresado como «Hemisph. radius» de GLAMA (lado menor / 1080)."""
    R = calibration.get("virtual_radius_px")
    if not R:
        return None
    return float(R) * float(glama_view_width_px) / float(min(image_width_px, image_height_px))


def calibrate_fisheye_from_radius(radius_px, projection="polar",
                                  center_xy=None, image_width_px=None,
                                  image_height_px=None):
    """Calibra un lente ojo de pez a partir del radio circular detectado."""
    projection = normalize_projection(projection)
    if projection in ("rectilinear", "angular"):
        raise ValueError(
            "'{}' no es una proyección ojo de pez. "
            "Use calibrate_regular_lens en su lugar.".format(projection)
        )
    proj = PROJECTIONS[projection]
    f_px = proj["f_from_ref"](radius_px, math.pi / 2.0)

    if center_xy is None and image_width_px and image_height_px:
        center_xy = [image_width_px / 2.0, image_height_px / 2.0]

    return {
        "lens_type": "fisheye",
        "focal_length_px": f_px,
        "virtual_radius_px": float(radius_px),
        "r_image_half_px": float(radius_px),
        "max_zenith_deg": 90.0,
        "full_fov_deg": 180.0,
        "theta_max_rad": math.pi / 2.0,
        "center_xy": list(center_xy) if center_xy is not None else None,
        "projection": projection,
        "projection_label": proj["label"],
        "image_width_px": int(image_width_px) if image_width_px else None,
        "image_height_px": int(image_height_px) if image_height_px else None,
    }


def scale_calibration_to_image(calibration, target_width_px, target_height_px):
    """
    Devuelve una copia de la calibración escalada a las dimensiones (target_width_px, target_height_px).
    Esto garantiza coherencia exacta entre imágenes reescaladas (4096 px) e imágenes a resolución completa.
    """
    cal = dict(calibration)
    cal_w = cal.get("image_width_px")
    cal_h = cal.get("image_height_px")

    if not cal_w or not cal_h or (cal_w == target_width_px and cal_h == target_height_px):
        if cal.get("r_image_half_px") is None:
            cal["r_image_half_px"] = min(target_width_px, target_height_px) / 2.0
        if cal.get("center_xy") is None:
            cal["center_xy"] = [target_width_px / 2.0, target_height_px / 2.0]
        return cal

    scale = float(min(target_width_px, target_height_px)) / float(min(cal_w, cal_h))
    scale_x = float(target_width_px) / float(cal_w)
    scale_y = float(target_height_px) / float(cal_h)

    for key in ("focal_length_px", "virtual_radius_px", "r_image_half_px", "r_ref_px", "pixel_diameter_px"):
        if cal.get(key) is not None:
            cal[key] = float(cal[key]) * scale

    rotated = (cal_w != cal_h) and ((cal_w > cal_h) != (target_width_px > target_height_px))
    if cal.get("center_xy") is not None:
        cx, cy = cal["center_xy"]
        if not rotated:
            cal["center_xy"] = [float(cx) * scale_x, float(cy) * scale_y]
        else:
            # v0.14.38: foto girada 90° respecto de la calibración. Un centro desplazado (ojo de pez
            # detectado fuera del centro) no se puede trasladar sin saber el sentido del giro; antes se
            # escalaban x e y por separado y el centro quedaba mal. Se usa el centro de la imagen y se avisa.
            off = math.hypot(float(cx) - cal_w / 2.0, float(cy) - cal_h / 2.0)
            cal["center_xy"] = [target_width_px / 2.0, target_height_px / 2.0]
            if off * scale > 0.005 * min(target_width_px, target_height_px):
                cal["center_note"] = (
                    "foto girada 90° respecto de la foto de calibración y centro de la calibración desplazado "
                    "{:.0f} px: se usa el centro de la imagen; detecte de nuevo el círculo en una foto con esta "
                    "orientación para un resultado exacto".format(off * scale))
    else:
        cal["center_xy"] = [target_width_px / 2.0, target_height_px / 2.0]

    cal["image_width_px"] = int(target_width_px)
    cal["image_height_px"] = int(target_height_px)
    return cal


# ----------------------------------------------------------------------
# Conversión ángulo <-> píxeles
# ----------------------------------------------------------------------
def _r_image_half_from_calibration(calibration):
    r = calibration.get("r_image_half_px")
    if r is not None and r > 0:
        return r
    w = calibration.get("image_width_px")
    h = calibration.get("image_height_px")
    if w and h:
        return min(w, h) / 2.0
    vr = calibration.get("virtual_radius_px")
    if vr is not None and vr > 0:
        return vr
    raise ValueError(
        "La proyección requiere 'r_image_half_px' o "
        "'image_width_px'/'image_height_px' en la calibración."
    )


def zenith_to_pixel_radius(zenith_deg, calibration):
    """Convierte un ángulo cenital (grados) a radio en píxeles desde el centro óptico."""
    theta = math.radians(zenith_deg)
    f = calibration["focal_length_px"]
    proj_code = calibration.get("projection", "polar")

    if proj_code == "angular":
        theta_max = calibration.get(
            "theta_max_rad",
            math.radians(calibration.get("max_zenith_deg", 90.0)),
        )
        r_image_half = _r_image_half_from_calibration(calibration)
        return _angular_forward(theta, theta_max, r_image_half)

    proj = PROJECTIONS[proj_code]
    return proj["forward"](f, theta)


def pixel_radius_to_zenith(r_px, calibration):
    """Proyección inversa: radio en píxeles -> ángulo cenital (grados)."""
    f = calibration["focal_length_px"]
    proj_code = calibration.get("projection", "polar")

    if proj_code == "angular":
        theta_max = calibration.get(
            "theta_max_rad",
            math.radians(calibration.get("max_zenith_deg", 90.0)),
        )
        r_image_half = _r_image_half_from_calibration(calibration)

        if np.isscalar(r_px):
            return math.degrees(_angular_inverse(r_px, theta_max, r_image_half))

        with np.errstate(invalid="ignore", divide="ignore"):
            theta = (r_px / r_image_half) * theta_max
        theta = np.clip(theta, 0.0, math.pi / 2.0)
        return np.degrees(theta)

    proj = PROJECTIONS[proj_code]

    if np.isscalar(r_px):
        return math.degrees(proj["inverse"](f, r_px))

    with np.errstate(invalid="ignore", divide="ignore"):
        if proj_code == "polar":
            theta = r_px / f
        elif proj_code == "rectilinear":
            theta = np.arctan(r_px / f)
        elif proj_code == "orthographic":
            theta = np.arcsin(np.clip(r_px / f, -1.0, 1.0))
        elif proj_code == "equisolid":
            theta = 2.0 * np.arcsin(np.clip(r_px / (2.0 * f), -1.0, 1.0))
        elif proj_code == "stereographic":
            theta = 2.0 * np.arctan(r_px / (2.0 * f))
        else:
            raise ValueError("Proyección no soportada: " + str(proj_code))
    return np.degrees(theta)


# Modelos por tipo de lente, el primero es el predeterminado (0.14.33: Rectilínea para lente regular)
PROJECTIONS_REGULAR = ("rectilinear", "angular")
PROJECTIONS_FISHEYE = ("polar", "equisolid", "orthographic", "stereographic")


def list_projections():
    return [(code, proj["label"]) for code, proj in PROJECTIONS.items()]


def projection_note(code):
    return PROJECTIONS.get(code, {}).get("note", "")


def is_fisheye_projection(code):
    return PROJECTIONS.get(code, {}).get("fisheye", False)
