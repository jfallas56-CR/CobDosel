"""
Comprobación de cámara/lente entre una calibración y una foto (sin dependencias de Qt ni de QGIS).

Una calibración describe el campo de visión de UNA lente con UN encuadre. Se puede reescalar a otra
resolución de la misma lente (2560×1920 → 4000×3000, o la foto girada 1920×2560), pero no sirve para
otra lente (principal, gran angular, teleobjetivo), otro teléfono, zoom digital o un recorte.
La huella de cámara se toma del EXIF: fabricante, modelo, distancia focal (mm y equivalente 35 mm),
zoom digital y proporción del fotograma (independiente de la orientación).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

FOCAL_TOLERANCE = 0.02      # 2 % en la distancia focal
ASPECT_TOLERANCE = 0.01     # 1 % en la proporción del fotograma


def camera_fingerprint(exif, width_px, height_px):
    """Huella de cámara a partir del dict de extract_exif() y del tamaño de la foto."""
    exif = exif or {}
    w, h = int(width_px), int(height_px)
    zoom = exif.get("digital_zoom_ratio")
    return {
        "make": (exif.get("camera_make") or "").strip() or None,
        "model": (exif.get("camera_model") or "").strip() or None,
        "focal_length_mm": exif.get("focal_length_mm"),
        "focal_length_35mm": exif.get("focal_length_35mm"),
        "digital_zoom": float(zoom) if zoom not in (None, 0, 0.0) else None,
        "size": [w, h],
        "aspect": round(max(w, h) / float(min(w, h)), 4) if min(w, h) > 0 else None,
    }


def camera_label(cam):
    """Texto corto: «Google Pixel 10, f 4.53 mm, 2560×1920»."""
    if not cam:
        return "sin datos de cámara"
    parts = [" ".join(p for p in (cam.get("make"), cam.get("model")) if p) or "cámara desconocida"]
    if cam.get("focal_length_mm"):
        parts.append("f {:.2f} mm".format(float(cam["focal_length_mm"])))
    if cam.get("focal_length_35mm"):
        parts.append("{:g} mm eq.".format(float(cam["focal_length_35mm"])))
    if cam.get("digital_zoom") and abs(cam["digital_zoom"] - 1.0) > 1e-3:
        parts.append("zoom {:.2f}×".format(cam["digital_zoom"]))
    if cam.get("size"):
        parts.append("{}×{}".format(*cam["size"]))
    return ", ".join(parts)


def camera_group_key(cam):
    """Clave para agrupar fotos de la misma lente y encuadre (sin la resolución ni la orientación)."""
    cam = cam or {}
    f = cam.get("focal_length_mm")
    z = cam.get("digital_zoom")
    return (cam.get("make"), cam.get("model"), round(float(f), 2) if f else None,
            round(float(z), 2) if z and abs(z - 1.0) > 1e-3 else None, cam.get("aspect"))


def _rel_diff(a, b):
    return abs(float(a) - float(b)) / max(abs(float(b)), 1e-9)


def compare_cameras(cal_cam, photo_cam):
    """
    Compara la huella de la calibración con la de la foto.
    Devuelve (estado, motivos): estado True = misma lente (puede diferir la resolución),
    False = otra lente o encuadre (la calibración NO es válida), None = no se puede comprobar.
    """
    if not cal_cam or not photo_cam:
        return None, ["la calibración o la foto no tiene datos de cámara (EXIF)"]
    bad, notes = [], []
    for key, label in (("make", "fabricante"), ("model", "modelo")):
        a, b = cal_cam.get(key), photo_cam.get(key)
        if a and b and a.lower() != b.lower():
            bad.append("{} distinto ({} ≠ {})".format(label, b, a))
    for key, label, unit in (("focal_length_mm", "distancia focal", "mm"),
                             ("focal_length_35mm", "focal equivalente 35 mm", "mm")):
        a, b = cal_cam.get(key), photo_cam.get(key)
        if a and b and _rel_diff(b, a) > FOCAL_TOLERANCE:
            bad.append("{} distinta ({:.2f} ≠ {:.2f} {}): otra lente o zoom".format(label, float(b), float(a), unit))
    za, zb = cal_cam.get("digital_zoom") or 1.0, photo_cam.get("digital_zoom") or 1.0
    if abs(za - zb) > 0.02:
        bad.append("zoom digital distinto ({:.2f}× ≠ {:.2f}×)".format(zb, za))
    aa, ab = cal_cam.get("aspect"), photo_cam.get("aspect")
    if aa and ab and _rel_diff(ab, aa) > ASPECT_TOLERANCE:
        bad.append("proporción del fotograma distinta ({:.3f} ≠ {:.3f}): recorte u otro formato".format(ab, aa))
    if bad:
        return False, bad
    known = [k for k in ("model", "focal_length_mm", "focal_length_35mm") if cal_cam.get(k) and photo_cam.get(k)]
    if not known:
        return None, ["sin modelo ni distancia focal comparables en el EXIF"]
    if cal_cam.get("size") and photo_cam.get("size") and sorted(cal_cam["size"]) != sorted(photo_cam["size"]):
        notes.append("misma lente a otra resolución ({}×{} → {}×{}): la calibración se reescala".format(
            *(cal_cam["size"] + photo_cam["size"])))
    return True, notes
