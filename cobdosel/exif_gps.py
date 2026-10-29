"""Extracción de coordenadas GPS y fecha/hora desde metadatos EXIF.

El GPS es opcional en CobDosel — el análisis funciona sin él. Cuando está
presente, permite crear una capa vectorial de puntos georreferenciados en QGIS.

v0.11.0 (CobDosel): se registran la orientación EXIF (etiqueta 274, aplicada al cargar) y la
brújula GPSImgDirection, para trazabilidad y para orientar la máscara por direcciones.

v0.10.0 (2026-10-17): errores de lectura EXIF registrados (clave «exif_error») en
lugar de silenciados.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import datetime
import logging
from PIL import Image, ImageOps

# v0.14.39: soporte HEIC/HEIF (fotos de iPhone) registrado aquí, en el módulo que usan todas las ventanas
# y el procesamiento por sitio. Antes solo lo registraban la ventana principal y la de medición, y el lote
# abierto directamente desde el menú no podía leer fotos HEIC.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

HEIF_MISSING_MSG = ("Las fotos HEIC/HEIF (formato predeterminado del iPhone) requieren el paquete «pillow-heif», "
                    "que no está instalado en este QGIS. Instálelo (Windows: OSGeo4W Shell → "
                    "python -m pip install pillow-heif) o configure el iPhone para guardar en JPEG "
                    "(Ajustes → Cámara → Formatos → «Más compatible»).")


def _check_heif(path):
    if str(path).lower().endswith((".heic", ".heif")) and not HEIF_SUPPORTED:
        raise RuntimeError(HEIF_MISSING_MSG)
from PIL.ExifTags import TAGS, GPSTAGS

_LOG = logging.getLogger("CobDosel")


def _rational_to_float(val):
    """Convierte un valor racional EXIF (IFDRational, tupla o número) a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "numerator") and hasattr(val, "denominator"):
        if val.denominator == 0:
            return 0.0
        return float(val.numerator) / float(val.denominator)
    if isinstance(val, (tuple, list)) and len(val) == 2:
        num, den = val
        if den == 0:
            return 0.0
        return float(num) / float(den)
    return float(val)


def _to_degrees(value):
    """Convierte una tupla GPS (grados, minutos, segundos) a grados decimales."""
    try:
        d, m, s = value
        deg = _rational_to_float(d)
        minutes = _rational_to_float(m)
        seconds = _rational_to_float(s)
        if deg is None or minutes is None or seconds is None:
            return None
        return deg + (minutes / 60.0) + (seconds / 3600.0)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def load_oriented_rgb_image(image_path, max_dim=None):
    """
    Carga una imagen aplicando la orientación EXIF y convirtiéndola a RGB.

    Args:
        image_path: ruta al archivo de imagen
        max_dim: si se especifica, redimensiona manteniendo proporción
                 para que max(ancho, alto) <= max_dim.

    Returns:
        tupla (pil_image, scale_factor, original_size_wh)
        donde scale_factor = nuevo_ancho / ancho_original_orientado
    """
    _check_heif(image_path)
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    orig_w, orig_h = img.size
    scale = 1.0

    if max_dim is not None and max(orig_w, orig_h) > max_dim:
        scale = float(max_dim) / float(max(orig_w, orig_h))
        new_size = (max(1, int(round(orig_w * scale))),
                    max(1, int(round(orig_h * scale))))
        img = img.resize(new_size, Image.LANCZOS)

    return img, scale, (orig_w, orig_h)


def extract_exif(image_path):
    """
    Extrae coordenadas GPS, altitud, fecha/hora de captura y modelo de cámara.

    Retorna un diccionario con las claves:
        latitude, longitude, elevation_m, capture_datetime,
        camera_make, camera_model, focal_length_mm, has_gps,
        orientation (etiqueta EXIF 274, 1–8; se aplica al cargar la imagen),
        image_direction_deg y image_direction_ref (brújula GPSImgDirection, si existe)
    """
    result = {
        "latitude": None,
        "longitude": None,
        "elevation_m": None,
        "capture_datetime": None,
        "camera_make": None,
        "camera_model": None,
        "focal_length_mm": None,
        "focal_length_35mm": None,
        "digital_zoom_ratio": None,
        "has_gps": False,
        "orientation": None,
        "image_direction_deg": None,
        "image_direction_ref": None,
        "exif_error": None,
    }

    try:
        img = Image.open(image_path)
        exif = None
        if hasattr(img, "getexif"):
            exif = img.getexif()
        elif hasattr(img, "_getexif"):
            exif = img._getexif()

        if not exif:
            return result

        # Recorrer etiquetas principales
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag in ("DateTimeOriginal", "DateTime") and not result["capture_datetime"]:
                try:
                    dt_str = str(value).strip().rstrip("\x00")
                    result["capture_datetime"] = datetime.datetime.strptime(
                        dt_str, "%Y:%m:%d %H:%M:%S"
                    ).isoformat()
                except (ValueError, TypeError) as e:
                    _LOG.debug("[exif fecha/altitud] %s", e)
            elif tag == "Orientation":
                try:
                    result["orientation"] = int(value)
                except (TypeError, ValueError) as e:
                    _LOG.debug("[exif Orientation] %s", e)
            elif tag == "Make":
                result["camera_make"] = str(value).strip().rstrip("\x00")
            elif tag == "Model":
                result["camera_model"] = str(value).strip().rstrip("\x00")
            elif tag == "FocalLength":
                try:
                    result["focal_length_mm"] = _rational_to_float(value)
                except (TypeError, ValueError, ZeroDivisionError) as e:
                    _LOG.debug("[exif FocalLength] %s", e)

        # Intentar obtener sub-IFD Exif (0x8769) para DateTimeOriginal y FocalLength
        if hasattr(exif, "get_ifd"):
            try:
                exif_ifd = exif.get_ifd(0x8769)
                for tag_id, value in exif_ifd.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "DateTimeOriginal" and not result["capture_datetime"]:
                        try:
                            dt_str = str(value).strip().rstrip("\x00")
                            result["capture_datetime"] = datetime.datetime.strptime(
                                dt_str, "%Y:%m:%d %H:%M:%S"
                            ).isoformat()
                        except (ValueError, TypeError) as e:
                            _LOG.debug("[exif fecha/altitud] %s", e)
                    elif tag == "FocalLength" and result["focal_length_mm"] is None:
                        try:
                            result["focal_length_mm"] = _rational_to_float(value)
                        except (TypeError, ValueError, ZeroDivisionError) as e:
                            _LOG.debug("[exif FocalLength sub-IFD] %s", e)
                    elif tag == "FocalLengthIn35mmFilm":
                        try:
                            result["focal_length_35mm"] = float(value) or None
                        except (TypeError, ValueError) as e:
                            _LOG.debug("[exif FocalLengthIn35mmFilm] %s", e)
                    elif tag == "DigitalZoomRatio":
                        try:
                            result["digital_zoom_ratio"] = _rational_to_float(value) or None
                        except (TypeError, ValueError, ZeroDivisionError) as e:
                            _LOG.debug("[exif DigitalZoomRatio] %s", e)
            except Exception as e:
                _LOG.debug("[exif sub-IFD 0x8769] %s", e)

        # Obtener información GPS (0x8825 = 34853)
        gps_info = None
        if hasattr(exif, "get_ifd"):
            try:
                gps_info = exif.get_ifd(0x8825)
            except Exception as e:
                _LOG.debug("[exif GPS IFD 0x8825] %s", e)
                gps_info = None
        if not gps_info:
            raw_gps = exif.get(34853)
            if isinstance(raw_gps, dict):
                gps_info = raw_gps
            elif hasattr(img, "_getexif"):
                try:
                    legacy = img._getexif()
                    if legacy and isinstance(legacy.get(34853), dict):
                        gps_info = legacy.get(34853)
                except Exception as e:
                    _LOG.debug("[exif GPS legacy] %s", e)

        if not gps_info:
            return result

        gps = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}

        if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
            lat = _to_degrees(gps["GPSLatitude"])
            ref = str(gps["GPSLatitudeRef"]).strip().upper()
            if lat is not None:
                if ref.startswith("S"):
                    lat = -abs(lat)
                result["latitude"] = lat

        if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
            lon = _to_degrees(gps["GPSLongitude"])
            ref = str(gps["GPSLongitudeRef"]).strip().upper()
            if lon is not None:
                if ref.startswith("W"):
                    lon = -abs(lon)
                result["longitude"] = lon

        if "GPSImgDirection" in gps:
            try:
                result["image_direction_deg"] = _rational_to_float(gps["GPSImgDirection"])
                ref = str(gps.get("GPSImgDirectionRef", "")).strip().upper()
                result["image_direction_ref"] = (
                    "magnético" if ref.startswith("M") else "verdadero" if ref.startswith("T") else None
                )
            except (TypeError, ValueError, ZeroDivisionError) as e:
                _LOG.debug("[exif GPSImgDirection] %s", e)

        if "GPSAltitude" in gps:
            try:
                alt = _rational_to_float(gps["GPSAltitude"])
                alt_ref = gps.get("GPSAltitudeRef", 0)
                if alt is not None:
                    if alt_ref in (1, b"\x01", "1"):
                        alt = -abs(alt)
                    result["elevation_m"] = alt
            except (ValueError, TypeError) as e:
                _LOG.debug("[exif fecha/altitud] %s", e)

        if result["latitude"] is not None and result["longitude"] is not None:
            result["has_gps"] = True

    except Exception as e:
        # EXIF ilegible: el análisis continúa sin GPS, pero la causa queda visible.
        result["exif_error"] = str(e)
        _LOG.warning("[extract_exif] %s: %s", image_path, e)

    return result
