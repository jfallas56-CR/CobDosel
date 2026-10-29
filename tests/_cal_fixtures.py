"""Calibraciones de prueba (v0.14.63).

La calibración con el radio de la app GLAMA se retiró del complemento en v0.14.63. Muchas pruebas la
usaban solo como una calibración «Lineal» de R conocido; esta copia, solo para las pruebas, la mantiene.
Se marca con calibration_method = "lineal_R_prueba" (no "glama_radius") para no disparar el aviso de
calibración retirada; las pruebas de ese aviso usan legacy=True.
"""
import math

from cobdosel.lens_calibration import PROJECTIONS, is_fisheye_projection

GLAMA_VIEW_WIDTH_PX = 1080


def _calibrate_from_glama_radius(glama_radius_px, image_width_px, image_height_px,
                                glama_view_width_px=GLAMA_VIEW_WIDTH_PX,
                                scale_side="short", glama_projection="polar"):
    """
    Calibración a partir del radio del hemisferio de la app GLAMA («Hemisph. radius»).

    GLAMA expresa el radio en píxeles de su vista (1080 px de ancho). En la pantalla de
    análisis la app muestra el RECORTE CUADRADO CENTRAL de la foto (lado = lado menor), de
    modo que la escala por el lado menor reproduce la geometría con que GLAMA calcula sus
    resultados: R_foto = R_GLAMA × lado_menor / 1080. v0.14.53: se quitó la escala por el lado
    mayor («long»): no reproducía a GLAMA ni la geometría de la cámara (Pixel 10, máscara 63°:
    analizaba 0–31.7° reales, el círculo salía de la foto y el CaCo variaba hasta 4.7 puntos).

    glama_projection: "polar" (equidistante, cámaras integradas) u "angular" (GLAMA;
    equivale a ortográfica, r = R·sin θ).
    """
    if glama_radius_px <= 0 or glama_view_width_px <= 0:
        raise ValueError("El radio de GLAMA y el ancho de la vista deben ser positivos.")
    if scale_side != "short":
        raise ValueError("La escala por el lado mayor ya no se ofrece: use el lado menor (reproduce "
                         "GLAMA) o la calibración por círculo D/H.")
    w, h = float(image_width_px), float(image_height_px)
    side = min(w, h)
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



def lineal_cal(glama_radius_px, image_width_px, image_height_px, legacy=False, **kw):
    cal = _calibrate_from_glama_radius(glama_radius_px, image_width_px, image_height_px, **kw)
    if not legacy:
        cal["calibration_method"] = "lineal_R_prueba"
    return cal


def glama_equivalent_radius(calibration, image_width_px, image_height_px, glama_view_width_px=GLAMA_VIEW_WIDTH_PX):
    R = calibration.get("virtual_radius_px")
    if not R:
        return None
    return float(R) * float(glama_view_width_px) / float(min(image_width_px, image_height_px))


def apply_to_dialog(d, glama_radius_px=1618.0, legacy=False):
    """Lo que hacía el botón retirado «Calibrar con radio GLAMA» en el diálogo principal."""
    h, w = d.image_array.shape[:2]
    proj = "angular" if d._current_projection_code() == "orthographic" else "polar"
    cal = lineal_cal(glama_radius_px, w, h, legacy=legacy, glama_projection=proj)
    cal["measurement"] = {"mode": "glama_radius",
                          "summary": "radio GLAMA {:.1f} px, escala por el lado menor".format(glama_radius_px)}
    cal["camera"] = d._current_camera()
    d.calibration = cal
    d._cal_name = None
    d.center_xy = (w / 2.0, h / 2.0)
    d.lens_combo.setCurrentIndex(0 if is_fisheye_projection(cal["projection"]) else 1)
    d._set_projection_by_code(cal["projection"])
    d.save_cal_btn.setEnabled(True)
    d._show_calibration_summary(cal, "Calibración de prueba (R fijo)")
    d._update_run_button()
    return cal


def calibrate_from_glama_radius(glama_radius_px, image_width_px, image_height_px, **kw):
    """Nombre antiguo, para las pruebas: calibración Lineal de prueba (sin aviso de calibración retirada)."""
    return lineal_cal(glama_radius_px, image_width_px, image_height_px, **kw)
