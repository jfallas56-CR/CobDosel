"""Comprobación de la distancia focal implicada por la calibración (CobDosel 0.14.33).

La cámara principal de un teléfono es rectilínea: un círculo de diámetro D a la distancia H
mide d = f·D/H píxeles, de modo que la medición implica f = d·H/D (en píxeles), con cualquier
modelo de proyección elegido. Convertida a focal equivalente de 35 mm (por la diagonal, como
el EXIF), se compara con:

1. la última calibración guardada de la misma cámara (referencia propia, validada), o
2. si no hay, el valor FocalLengthIn35mmFilm del EXIF de la foto.

Umbrales (avisos informativos, nunca impiden guardar la calibración):
- con el EXIF: hasta 8 % coherente; 8–15 % nota (revise H y D); más de 15 % aviso (otra lente,
  zoom digital o H muy mal medida). Una calibración correcta puede diferir del EXIF hasta unos
  6 %: el EXIF guarda un número entero (±2 %), el valor nominal del fabricante difiere del real
  (Pixel 10: EXIF 24 mm, real 25,4 mm, +5,9 %) y el enfoque cercano cambia la focal (1–3 %).
- con una calibración propia de la misma cámara: hasta 3 % coherente; 3–8 % nota; más de 8 % aviso.
"""

import math

FULL_FRAME_DIAG_MM = 43.27          # diagonal del formato de 35 mm (36 × 24 mm)
EXIF_NOTE_PCT = 8.0
EXIF_WARN_PCT = 15.0
OWN_NOTE_PCT = 3.0
OWN_WARN_PCT = 8.0


def implied_focal_px(cal):
    """f (px) implicada por la medición del círculo, con la geometría exacta: f = d·H/D. None si no aplica."""
    if not cal:
        return None
    d = cal.get("pixel_diameter_px")
    D = cal.get("circle_diameter_cm")
    H = cal.get("camera_height_cm")
    if d and D and H and float(D) > 0:
        return float(d) * float(H) / float(D)
    return None


def equivalent_focal_mm(f_px, width_px, height_px):
    """Focal equivalente de 35 mm por la diagonal (convención del EXIF)."""
    if not f_px or not width_px or not height_px:
        return None
    return float(f_px) * FULL_FRAME_DIAG_MM / math.hypot(float(width_px), float(height_px))


def calibration_focal_mm(cal):
    """Focal equivalente (mm) de una calibración por círculo D/H, o None."""
    f = implied_focal_px(cal)
    if f is None:
        return None
    return equivalent_focal_mm(f, cal.get("image_width_px"), cal.get("image_height_px"))


def check_focal(cal, exif_35mm=None, own_reference=None):
    """
    Compara la focal de la calibración con una referencia.

    own_reference: (nombre, focal_mm) de una calibración guardada de la misma cámara, o None.
    Devuelve dict con level ('ok', 'note', 'warn' o None si no se puede comprobar), focal_mm,
    ref_kind ('propia', 'exif' o None), ref_name, ref_mm, diff_pct y text (una línea en español).
    """
    out = {"level": None, "focal_mm": calibration_focal_mm(cal), "ref_kind": None,
           "ref_name": None, "ref_mm": None, "diff_pct": None, "text": ""}
    fmm = out["focal_mm"]
    if fmm is None:
        out["text"] = "Focal equivalente: no se puede calcular (calibración sin círculo D/H)."
        return out
    if own_reference and own_reference[1]:
        name, ref = own_reference
        diff = 100.0 * (fmm / float(ref) - 1.0)
        level = "ok" if abs(diff) <= OWN_NOTE_PCT else ("note" if abs(diff) <= OWN_WARN_PCT else "warn")
        out.update(level=level, ref_kind="propia", ref_name=name, ref_mm=float(ref), diff_pct=diff)
        base = "Focal equivalente {:.1f} mm; calibración «{}» de la misma cámara: {:.1f} mm ({:+.1f} %)".format(
            fmm, name, float(ref), diff)
        out["text"] = base + {
            "ok": " — coherente (tolerancia ±{:g} %).".format(OWN_NOTE_PCT),
            "note": " — revise H y D: dos calibraciones de la misma cámara suelen coincidir dentro de ±{:g} %.".format(
                OWN_NOTE_PCT),
            "warn": " — diferencia grande: revise H, D, la lente (1x) y el zoom digital antes de usarla.",
        }[level]
        return out
    if exif_35mm:
        diff = 100.0 * (fmm / float(exif_35mm) - 1.0)
        level = "ok" if abs(diff) <= EXIF_NOTE_PCT else ("note" if abs(diff) <= EXIF_WARN_PCT else "warn")
        out.update(level=level, ref_kind="exif", ref_mm=float(exif_35mm), diff_pct=diff)
        base = "Focal equivalente {:.1f} mm; EXIF de la foto: {:g} mm ({:+.1f} %)".format(fmm, float(exif_35mm), diff)
        out["text"] = base + {
            "ok": " — coherente (hasta ±{:g} % es normal: el EXIF redondea y el valor nominal difiere del real).".format(
                EXIF_NOTE_PCT),
            "note": " — mayor que lo habitual (±{:g} %): revise H (del vidrio de la cámara al papel) y D.".format(
                EXIF_NOTE_PCT),
            "warn": " — posible lente distinta (0.5x, 2x), zoom digital o H mal medida; revise antes de usarla.",
        }[level]
        return out
    out["text"] = ("Focal equivalente {:.1f} mm; sin referencia para comprobarla (la foto no tiene focal "
                   "equivalente en el EXIF y no hay otra calibración de esta cámara).".format(fmm))
    return out
