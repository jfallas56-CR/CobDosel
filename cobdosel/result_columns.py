"""Diccionario en español de las variables del CSV de una foto (Resultados_CobDosel_<foto>.csv), CobDosel 0.16.2.

Desde 0.16.2 ese CSV se escribe transpuesto: una fila por variable con las columnas «variable» (clave estable, la misma
desde 0.14.x), «descripcion» (en español, con la unidad) y «valor». Así se lee en Excel sin desplazarse por 60 columnas y
cada valor lleva su explicación. read_results_csv() lee los dos formatos (el ancho anterior y el transpuesto).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import csv
import re

RESULT_HEADER = ("variable", "descripcion", "valor")

DESCRIPTIONS = {
    "image_id": "Archivo de la foto",
    "latitude": "Latitud del EXIF (grados, WGS84)",
    "longitude": "Longitud del EXIF (grados, WGS84)",
    "elevation_m": "Altitud del EXIF (m)",
    "capture_datetime": "Fecha y hora de captura (EXIF)",
    "projection": "Modelo de proyección del lente",
    "circle_diameter_cm": "Calibración: diámetro del círculo D (cm)",
    "camera_height_cm": "Calibración: altura de la cámara sobre el círculo H (cm)",
    "pixel_diameter_px": "Calibración: diámetro medido del círculo en la foto (px)",
    "focal_length_px": "Focal del lente f (px, en el tamaño de la foto)",
    "half_fov_deg": "Semiángulo de visión del lente (grados)",
    "full_fov_deg": "Ángulo de visión completo del lente (grados)",
    "hemisphere_fraction_pct": "Fracción del hemisferio de referencia (convención de GLAMA) dentro de la foto (%)",
    "horizon_mask_deg": "Máscara de horizonte artificial (grados sobre el horizonte)",
    "zenith_max_deg": "Ángulo cenital máximo analizado (grados)",
    "n_rings": "Número de anillos cenitales",
    "measurement_type": "Tipo de medida (caco = Índice CaCo, Tichý 2016)",
    "channel_mode": "Canal de color usado para el corte",
    "cut_level_threshold": "Nivel de corte (0–255)",
    "total_pixels_in_circle": "Píxeles dentro del área analizada",
    "total_pixels_in_frame": "Píxeles de la foto",
    "light_pixels": "Píxeles claros (cielo)",
    "dark_pixels": "Píxeles oscuros (copa)",
    "gap_fraction_selected_area_pct": "Fracción de claros del área analizada (%)",
    "gap_fraction_unmasked_pct": "Fracción de claros sin máscara (%)",
    "canopy_openness_pct": "Apertura del dosel, convención de GLAMA (%)",
    "canopy_closure_pct": "Cierre del dosel, convención de GLAMA (%)",
    "canopy_openness_analysed_pct": "Apertura del área analizada (%)",
    "canopy_cover_caco_index_pct": "Índice CaCo: cobertura del dosel estimada (%)",
    "lai_effective": "LAI efectivo (Miller 1967; solo ojo de pez de 180°)",
    "lai_zenith_max_deg": "Ángulo cenital máximo usado en el LAI (grados)",
    "lai_reliable": "LAI fiable (Sí/No)",
    "sky_is_bright": "El cielo es la parte clara de la foto (Sí/No)",
    "calibration_approx_formula": "Calibración con la fórmula aproximada de GLAMA (Sí/No)",
    "horizon_angles": "Máscara por direcciones: ángulos del horizonte (grados, separados por «;»)",
    "plugin": "Complemento",
    "plugin_version": "Versión del complemento",
    "hemisphere_radius_px": "Radio del hemisferio en la foto R (px)",
    "zenith_frame_max_deg": "Ángulo cenital máximo que alcanza la foto (grados)",
    "circle_visible_pct": "Parte del círculo de análisis visible en la foto (%)",
    "calibration_method": "Método de calibración",
    "measurement_mode": "Medición del círculo: modo",
    "measurement_file": "Medición del círculo: archivo",
    "measurement_image_size": "Medición del círculo: tamaño de la foto (px)",
    "measurement_diff_pct": "Medición del círculo: diferencia entre los dos diámetros (%)",
    "measurement_fit_rms_px": "Medición del círculo: residuo del ajuste (px)",
    "measurement_centre_offset_pct": "Medición del círculo: desplazamiento del centro (%)",
    "exif_orientation": "Orientación EXIF (etiqueta 274)",
    "exif_image_direction_deg": "Rumbo de la cámara del EXIF (grados)",
    "cut_level_method": "Método del nivel de corte",
    "site_name": "Sitio",
    "analyst": "Analista",
    "glama_reference_zenith_deg": "Cenit de referencia de la apertura y el cierre (convención de GLAMA, grados)",
    "hemisphere_fraction_abs_pct": "Fracción del hemisferio real que cubre la foto (%)",
    "analysed_fraction_abs_pct": "Fracción del hemisferio real que cubre el área analizada (%)",
}

_PATTERNS = (
    (re.compile(r"^cover_pct_ring(\d+)$"), "Cobertura del anillo {0} (%)"),
    (re.compile(r"^gap_fraction_ring(\d+)$"), "Fracción de claros del anillo {0}"),
    (re.compile(r"^cover_vertical_pct_ring(\d+)$"),
     "Cobertura del anillo {0} llevada a la vertical (%; Beer–Lambert, follaje al azar, G = 0,5)"),
    (re.compile(r"^caco_weight_pct_ring(\d+)$"), "Peso del anillo {0} en el Índice CaCo (%)"),
    (re.compile(r"^gap_pct_ring(\d+)_S(\d+)$"), "Fracción de claros del anillo {0}, sector S{1} (%)"),
    (re.compile(r"^lai_ring(\d+)_([\d.]+)-([\d.]+)deg$"), "LAI del anillo {0} ({1}–{2}°)"),
    (re.compile(r"^lai_ring(\d+)$"), "LAI del anillo {0}"),
)


def describe(key):
    """Descripción en español de una variable del CSV; la clave misma si no está en el diccionario."""
    if key in DESCRIPTIONS:
        return DESCRIPTIONS[key]
    for rx, fmt in _PATTERNS:
        m = rx.match(key)
        if m:
            return fmt.format(*m.groups())
    return key


def transpose_rows(header, row):
    """Filas (variable, descripcion, valor) a partir del encabezado y la fila del formato ancho."""
    return [(k, describe(k), v) for k, v in zip(header, row)]


def read_results_csv(path):
    """Lee Resultados_CobDosel_<foto>.csv en cualquiera de sus dos formatos y devuelve {variable: valor (texto)}."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        rows = [r for r in csv.reader(f, dialect) if r]
    if not rows:
        return {}
    if [c.strip() for c in rows[0][:3]] == list(RESULT_HEADER):
        return {r[0]: (r[2] if len(r) > 2 else "") for r in rows[1:]}
    if len(rows) >= 2:
        return dict(zip(rows[0], rows[1]))
    return {}
