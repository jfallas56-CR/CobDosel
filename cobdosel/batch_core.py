"""Procesamiento por lotes de CobDosel (sin dependencias de Qt ni de QGIS).

Diseño de ejemplo (cualquier diseño sirve: el formulario indica parcela y punto de cada foto):
- parcelas circulares de 500 m² (radio 12.62 m);
- 5 fotos verticales por parcela: Centro y N-O (315°), N-E (45°), S-E (135°), S-O (225°) a 8.9 m
  del centro;
- CaCo de cada foto con 2 decimales (redondeo a la mitad hacia arriba); todos los cálculos usan ese valor;
- valor de la parcela = media de las fotos válidas disponibles (descriptivo), con 2 decimales;
- valor del sitio = media de todas las fotos válidas del sitio (Índice CaCo), con 2 decimales (v0.14.62).

Entradas: carpeta de fotos (nombres de la cámara), formulario de campo digital (CSV o Excel con las
columnas de la plantilla; opcional desde v0.14.42: sin formulario, parcela y punto se asignan por orden de
hora), calibración guardada, máscara de horizonte (fija, 63° por defecto, el estándar de CobDosel; Tichý 2016
usó 60°; u opcionalmente desde una altura del dosel del sitio) y, opcionalmente, el número de parcelas.
El protocolo no mide alturas: los árboles se asignan a grupos de dosel (CANOPY_GROUPS). El nivel de corte de cada foto es el recomendado
(cruce de dos log-normales, método de la app GLAMA; iterado hasta estabilizarse desde 128); si no hay
recomendación se usa Otsu.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import csv
import datetime
import math
import os
import re
import unicodedata

import numpy as np

from .exif_gps import load_oriented_rgb_image, extract_exif
from .focal_check import calibration_focal_mm
from .camera_check import camera_fingerprint, camera_label, camera_group_key, compare_cameras
from .lens_calibration import scale_calibration_to_image, zenith_to_pixel_radius
from .canopy_analysis import (
    extract_channel, threshold_image, compute_otsu_threshold, compute_radius_grid,
    compute_zenith_grid, analysis_circle_visibility, sky_uniformity_range, sky_uniformity_warning,
    CHANNEL_LABELS,
)
from .glama_engine import (  # noqa: F401  (glama_cut_iterated se reexporta por compatibilidad)
    glama_ring_counts, glama_ring_counts_with_gray, glama_indices, glama_recommended_cut,
    glama_cut_iterated, GLAMA_CUT_START, glama_cut_diagnosis,
)
import json
from decimal import Decimal, ROUND_HALF_UP

PLOT_RADIUS_M = 12.62            # parcela circular de 500 m²
DEFAULT_FOOTPRINT_M = 6.31       # radio equivalente del cuadrante (125 m²) cubierto por cada foto
DEFAULT_CAMERA_HEIGHT_M = 1.3
DEFAULT_TOLERANCE_S = 60.0
# v0.14.63: la calibración con el radio de la app GLAMA se retiró; una guardada aún se puede leer
GLAMA_RADIUS_WARNING = ("La calibración se creó con el radio de la app GLAMA (función retirada en v0.14.63): su "
                        "geometría no es la de la cámara y el área analizada no corresponde a la máscara indicada. "
                        "Recalibre con el círculo D/H.")
DEFAULT_MASK_DEG = 63.0          # v0.14.29: estándar de CobDosel (cenit ≤ 27°): círculo completo con teléfonos de 23–25 mm; Tichý (2016) usó 60°

# Grupos de dosel del protocolo (posición del árbol; no se mide la altura). (código, nombre, min m, max m)
CANOPY_GROUPS = (
    (1, "Rastrero: herbáceas y helechos", 0.0, 1.0),
    (2, "Sotobosque: regeneración y arbustos", 1.0, 5.0),
    (3, "Copa inferior / Subdosel", 5.0, 15.0),
    (4, "Copa superior / Dosel principal", 15.0, 30.0),
    (5, "Copas emergentes (no compactas)", 30.0, None),
)


def canopy_group_height(code):
    """Altura de referencia de un grupo de dosel (punto medio; límite inferior en el grupo 5)."""
    for c, _name, lo, hi in CANOPY_GROUPS:
        if c == int(code):
            return lo if hi is None else (lo + hi) / 2.0
    raise ValueError("Grupo de dosel desconocido: {}".format(code))


MAX_ANALYSIS_DIM = 4096
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif")

# Puntos del diseño de ejemplo (orden del formulario) y sus sinónimos aceptados
POINTS = ("Centro", "N-O", "N-E", "S-E", "S-O")
_POINT_ALIASES = {
    "c": "Centro", "centro": "Centro", "center": "Centro", "0": "Centro",
    "no": "N-O", "nw": "N-O", "315": "N-O", "q4": "N-O",
    "ne": "N-E", "45": "N-E", "q1": "N-E",
    "se": "S-E", "135": "S-E", "q2": "S-E",
    "so": "S-O", "sw": "S-O", "225": "S-O", "q3": "S-O",
}

# Columnas de la plantilla y sinónimos (comparación sin tildes ni mayúsculas)
FORM_COLUMNS = ("parcela", "reemplaza_a", "punto", "distancia_m",
                "id_foto", "hora_captura", "calidad", "observaciones")
_COLUMN_ALIASES = {
    "parcela": ("parcela", "plot", "id_parcela", "n_parcela"),
    "reemplaza_a": ("reemplaza_a", "reemplaza", "reemplazo_de", "reemplaza_a_parcela"),
    "punto": ("punto", "posicion", "point"),
    "distancia_m": ("distancia_m", "distancia", "distancia_diagonal_m", "distancia_diagonal"),
    "id_foto": ("id_foto", "id_de_fotografia", "id_fotografia", "foto", "archivo"),
    "hora_captura": ("hora_captura", "hora_de_captura", "fecha_hora", "hora"),
    "calidad": ("calidad", "estado"),
    "observaciones": ("observaciones", "obs", "comentarios"),
}
# Calidades que excluyen la foto del cálculo. v0.14.38: se compara el valor completo (o cada parte
# separada por «,», «;» o «/»), no fragmentos: «sin sol» o «buena (no repetir)» ya no excluyen la foto.
_BAD_QUALITY = ("sol", "sol directo", "movida", "foto movida", "desenfocada", "repetir", "mala",
                "descartar", "excluir", "excluida", "no valida", "invalida")


def quality_excludes(value):
    """True si la calidad anotada excluye la foto (valor completo o una de sus partes)."""
    parts = re.split(r"[,;/]", str(value or ""))
    return any(_norm(p).replace("_", " ") in _BAD_QUALITY for p in parts if p.strip())


def _norm(text):
    """minúsculas, sin tildes, espacios y signos → «_»."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def normalize_point(value):
    """«N-O (315°)», «NO», «nw», «315» → «N-O»; «Centro», «C» → «Centro». None si no se reconoce."""
    key = _norm(value).replace("_", "")
    if key in _POINT_ALIASES:
        return _POINT_ALIASES[key]
    for k in ("centro", "no", "ne", "se", "so", "nw", "sw"):
        if key.startswith(k):
            return _POINT_ALIASES[k]
    digits = re.findall(r"\d+", key)
    if digits and digits[0] in _POINT_ALIASES:
        return _POINT_ALIASES[digits[0]]
    return None


# ----------------------------------------------------------------------
# Fechas y horas
# ----------------------------------------------------------------------
_DT_PATTERNS = (
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y:%m:%d %H:%M:%S", "%d/%m/%y %H:%M:%S",
    "%d/%m/%y %H:%M",
)


def parse_datetime(value, default_date=None):
    """
    Fecha y hora del formulario, día primero (DD/MM/AAAA). Acepta «17/10/2026 / 19:49:43»,
    «17/10/2026 19:49», «2026-10-17T19:49:43», objetos datetime y, con default_date, solo la hora.
    Devuelve datetime o None.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.time) and default_date is not None:
        return datetime.datetime.combine(default_date, value)
    s = str(value).strip().replace("T", " ")
    s = re.sub(r"\s*/\s*(?=\d{1,2}:)", " ", s)      # «17/10/2026 / 19:49:43» → «17/10/2026 19:49:43»
    s = re.sub(r"\s+", " ", s)
    for fmt in _DT_PATTERNS:
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    if default_date is not None:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.datetime.combine(default_date, datetime.datetime.strptime(s, fmt).time())
            except ValueError:
                continue
    return None


# ----------------------------------------------------------------------
# Formulario de campo
# ----------------------------------------------------------------------
def _map_header(header):
    mapping = {}
    normed = [_norm(h) for h in header]
    for key, aliases in _COLUMN_ALIASES.items():
        for i, h in enumerate(normed):
            if h in aliases and i not in mapping.values():
                mapping[key] = i
                break
    return mapping


def _read_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            return [row for row in csv.reader(f, dialect)]
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.worksheets[0]
            rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
            wb.close()
            return rows
        except ImportError:
            pass
        try:
            from osgeo import ogr      # disponible en QGIS
        except ImportError:
            raise ValueError("Para leer Excel se necesita openpyxl o GDAL; guarde el formulario como CSV.")
        ds = ogr.Open(path)
        if ds is None:
            raise ValueError("No se pudo abrir el formulario: " + path)
        lyr = ds.GetLayer(0)
        defn = lyr.GetLayerDefn()
        header = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
        rows = [header]
        for feat in lyr:
            rows.append([feat.GetField(i) for i in range(defn.GetFieldCount())])
        return rows
    raise ValueError("Formato de formulario no soportado (use .csv o .xlsx): " + path)


def read_field_form(path):
    """
    Lee el formulario de fotos. Devuelve (filas, avisos). Cada fila: dict con las claves de
    FORM_COLUMNS, más «fila» (n.º de fila en el archivo), «punto_norm» y «hora_dt».
    Las celdas vacías de parcela y reemplaza_a heredan el valor de la fila anterior (el formulario en
    papel solo las anota una vez por parcela). Otras columnas (p. ej. una altura de 0.12.0) se ignoran.
    """
    table = _read_table(path)
    header_idx = None
    for i, row in enumerate(table[:20]):
        mp = _map_header(row)
        if "parcela" in mp and ("id_foto" in mp or "hora_captura" in mp):
            header_idx, mapping = i, mp
            break
    if header_idx is None:
        raise ValueError("No se encontró la fila de encabezados (se esperan al menos «parcela» e "
                         "«id_foto» o «hora_captura»).")
    rows, warnings = [], []
    carry = {"parcela": None, "reemplaza_a": None}
    for n, raw in enumerate(table[header_idx + 1:], start=header_idx + 2):
        if raw is None or all((c is None or str(c).strip() == "") for c in raw):
            continue
        # Fila descriptiva de la plantilla («Parcela», «ID de fotografía», …): se omite
        if len(_map_header(raw)) >= 3 or _norm(raw[mapping["parcela"]]) == "parcela":
            continue
        rec = {}
        for key in FORM_COLUMNS:
            idx = mapping.get(key)
            val = raw[idx] if idx is not None and idx < len(raw) else None
            rec[key] = val.strip() if isinstance(val, str) else val
        if rec["parcela"] not in (None, ""):
            # Nueva parcela: sus datos de cabecera valen hasta la próxima parcela
            carry = {"parcela": rec["parcela"], "reemplaza_a": rec["reemplaza_a"]}
        else:
            rec["parcela"] = carry["parcela"]
            if rec["reemplaza_a"] in (None, ""):
                rec["reemplaza_a"] = carry["reemplaza_a"]
            else:
                carry["reemplaza_a"] = rec["reemplaza_a"]
        if rec["parcela"] in (None, ""):
            warnings.append("Fila {}: sin parcela; se omite.".format(n))
            continue
        rec["parcela"] = str(rec["parcela"]).strip()
        if re.fullmatch(r"\d+\.0", rec["parcela"]):        # 7.0 leído de Excel → «7»
            rec["parcela"] = rec["parcela"][:-2]
        rec["fila"] = n
        rec["punto_norm"] = normalize_point(rec["punto"]) if rec["punto"] not in (None, "") else None
        m_foto = re.fullmatch(r"foto_?(\d+)", _norm(rec["punto"])) if rec["punto"] not in (None, "") else None
        if rec["punto_norm"] is None and m_foto:
            # v0.14.43: «Foto N» (diseños sin los 5 puntos y asignación automática) es un punto válido
            rec["punto_norm"] = "Foto {}".format(int(m_foto.group(1)))
        if rec["punto"] not in (None, "") and rec["punto_norm"] is None:
            warnings.append("Fila {}: punto «{}» no reconocido.".format(n, rec["punto"]))
        rec["hora_dt"] = parse_datetime(rec["hora_captura"])
        if rec["hora_captura"] not in (None, "") and rec["hora_dt"] is None:
            warnings.append("Fila {}: hora «{}» no reconocida (use DD/MM/AAAA HH:MM:SS).".format(
                n, rec["hora_captura"]))
        rec["excluida_por_calidad"] = quality_excludes(rec["calidad"])
        rows.append(rec)
    return rows, warnings


# ----------------------------------------------------------------------
# Fotos y emparejamiento
# ----------------------------------------------------------------------
def photo_datetime(path):
    """Fecha y hora EXIF (DateTimeOriginal o DateTime) de la foto, o None."""
    info = extract_exif(path)
    return parse_datetime(info.get("capture_datetime"))


def _photo_camera(path):
    """Huella de cámara de una foto (EXIF + tamaño del archivo; la proporción no depende del giro)."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return None
    return camera_fingerprint(extract_exif(path), w, h)


def scan_photos(folder):
    """Lista de dicts {ruta, nombre, base, hora_exif, camara} de las imágenes de la carpeta (no recursivo)."""
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and name.lower().endswith(IMAGE_EXT):
            out.append({"ruta": p, "nombre": name, "base": os.path.splitext(name)[0],
                        "hora_exif": photo_datetime(p), "camara": _photo_camera(p)})
    return out




def draft_form_from_photos(folder, out_path, photos_per_plot=5, template_xlsx=None, delimiter=","):
    """
    Crea un formulario de fotos prellenado con todas las fotos de la carpeta, ordenadas por hora EXIF
    (o por nombre si no hay hora): id_foto y hora_captura escritos; parcela y punto asignados por orden,
    photos_per_plot fotos por parcela, puntos «Foto 1», «Foto 2»… El usuario debe revisarlo.
    Escribe .xlsx (desde la plantilla, con openpyxl) o .csv. Devuelve (ruta, n.º de fotos, avisos).
    """
    photos = scan_photos(folder)
    if not photos:
        raise ValueError("La carpeta no contiene fotos ({}).".format(", ".join(IMAGE_EXT)))
    far = datetime.datetime(9999, 1, 1)
    photos.sort(key=lambda p: (p["hora_exif"] or far, p["nombre"].lower()))
    n = max(1, int(photos_per_plot))
    warnings = []
    no_time = [p["nombre"] for p in photos if p["hora_exif"] is None]
    if no_time:
        warnings.append("{} foto(s) sin hora EXIF, al final por nombre: {}.".format(
            len(no_time), ", ".join(no_time[:5]) + (" …" if len(no_time) > 5 else "")))
    # v0.14.61: la nota solo en las parcelas cuyas fotos abarcan más de 20 min (antes en todas las filas)
    far_plots = set()
    for start in range(0, len(photos), n):
        grp = [p["hora_exif"] for p in photos[start:start + n] if p["hora_exif"]]
        if len(grp) > 1 and (max(grp) - min(grp)).total_seconds() > 20 * 60:
            far_plots.add(start // n + 1)
    rows = []
    for i, ph in enumerate(photos):
        k = i % n
        # v0.14.48: siempre «Foto N»; los nombres de punto (Centro, N-O…) dependen del protocolo del estudio
        punto, dist = "Foto {}".format(k + 1), ""
        hora = ph["hora_exif"].strftime("%d/%m/%Y / %H:%M:%S") if ph["hora_exif"] else ""
        note = "revise: fotos con más de 20 min de diferencia" if (i // n + 1) in far_plots else ""
        rows.append([str(i // n + 1), "", punto, dist, ph["base"], hora, "OK", note])
    if len(photos) % n:
        warnings.append("{} fotos no es múltiplo de {}: la última parcela queda incompleta.".format(
            len(photos), n))
    # Saltos de tiempo dentro de una parcela (posible asignación errónea)
    for start in range(0, len(photos), n):
        grp = [p["hora_exif"] for p in photos[start:start + n] if p["hora_exif"]]
        if len(grp) > 1 and (max(grp) - min(grp)).total_seconds() > 20 * 60:
            warnings.append("Parcela {}: sus fotos abarcan más de 20 min; revise la asignación.".format(
                start // n + 1))
    if out_path.lower().endswith(".xlsx"):
        import openpyxl
        tpl = template_xlsx or os.path.join(os.path.dirname(__file__), "plantillas",
                                            "Formulario_fotos_CobDosel.xlsx")
        wb = openpyxl.load_workbook(tpl)
        ws = wb.worksheets[0]
        if ws.max_row >= 3:
            ws.delete_rows(3, ws.max_row)
        for r in rows:
            ws.append(r)
        wb.save(out_path)
    else:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=delimiter)      # v0.14.63: «;» donde la coma es decimal
            w.writerow(FORM_COLUMNS)
            w.writerows(rows)
    return out_path, len(photos), warnings


def camera_groups(photos):
    """[(etiqueta, n.º de fotos, huella)] por lente/encuadre, de más a menos fotos."""
    groups = {}
    for ph in photos:
        cam = ph.get("camara")
        key = camera_group_key(cam)
        g = groups.setdefault(key, {"n": 0, "cam": cam, "sizes": set()})
        g["n"] += 1
        if cam and cam.get("size"):
            g["sizes"].add("{}×{}".format(*cam["size"]))
    out = []
    for g in sorted(groups.values(), key=lambda v: -v["n"]):
        base = camera_label(dict(g["cam"] or {}, size=None))
        out.append(("{} [{}]".format(base, ", ".join(sorted(g["sizes"])) or "—"), g["n"], g["cam"]))
    return out


def calibration_camera_check(photo_folder, calibration, saved=None):
    """
    v0.14.44: antes de procesar, compara la cámara de la calibración con las cámaras de las fotos de la carpeta.
    saved: lista opcional de (nombre, calibración) guardadas, para proponer una que coincida.
    Devuelve dict: total (fotos), mismatch (fotos de otra cámara/lente), unverified (fotos sin EXIF
    comparable), cal_label, groups [(etiqueta, n, estado)], matches [nombres que coinciden con la cámara
    mayoritaria de las fotos de otra cámara], checked (False si la calibración no registra la cámara).
    """
    photos = scan_photos(photo_folder)
    cal_cam = calibration.get("camera") or (calibration.get("measurement") or {}).get("camera")
    if cal_cam and not (cal_cam.get("model") or cal_cam.get("focal_length_mm") or cal_cam.get("focal_length_35mm")):
        cal_cam = None
    out = {"total": len(photos), "mismatch": 0, "unverified": 0, "groups": [], "matches": [],
           "cal_label": camera_label(cal_cam) if cal_cam else "no registrada", "checked": bool(cal_cam)}
    if not cal_cam:
        return out
    other = None
    for label, n, cam in camera_groups(photos):
        state = compare_cameras(cal_cam, cam)[0]
        out["groups"].append((label, n, state))
        if state is False:
            out["mismatch"] += n
            other = other or cam
        elif state is None:
            out["unverified"] += n
    if other is not None:
        for name, cal in (saved or []):
            cam2 = cal.get("camera") or (cal.get("measurement") or {}).get("camera")
            if cam2 and compare_cameras(cam2, other)[0] is True:
                out["matches"].append(name)
    return out


def match_photos(rows, photos, tolerance_s=DEFAULT_TOLERANCE_S, clock_offset_s=0.0):
    """
    Empareja cada fila del formulario con una foto: primero por ID (nombre de archivo, sin
    extensión ni mayúsculas); si no hay ID o no aparece, por la hora EXIF más cercana dentro de la
    tolerancia. clock_offset_s se suma a la hora EXIF (corrige el reloj de la cámara).
    Devuelve (pares, avisos); cada par = (fila, foto o None, método, diferencia_s o None).
    """
    by_id = {}
    for ph in photos:
        by_id.setdefault(ph["base"].lower(), ph)
        by_id.setdefault(ph["nombre"].lower(), ph)
    used = set()
    pairs, warnings = [], []
    pending = []
    for r in rows:
        pid = str(r.get("id_foto") or "").strip()
        ph = None
        if pid:
            key = pid.lower()
            ph = by_id.get(key) or by_id.get(os.path.splitext(key)[0])
            if ph is None:
                cands = [p for p in photos if key in p["base"].lower()]
                ph = cands[0] if len(cands) == 1 else None
        if ph is not None and ph["ruta"] not in used:
            diff = None
            if r.get("hora_dt") and ph.get("hora_exif"):
                diff = (ph["hora_exif"] + datetime.timedelta(seconds=clock_offset_s)
                        - r["hora_dt"]).total_seconds()
                if abs(diff) > tolerance_s:
                    warnings.append(
                        "Parcela {} {}: la foto {} coincide por ID, pero su hora difiere {:+.0f} s del "
                        "formulario (revise).".format(r["parcela"], r.get("punto_norm") or "", ph["nombre"], diff))
            used.add(ph["ruta"])
            pairs.append((r, ph, "id", diff))
        else:
            if pid and ph is None:
                warnings.append("Parcela {} {}: ID «{}» no encontrado en la carpeta; se intenta por hora."
                                .format(r["parcela"], r.get("punto_norm") or "", pid))
            pending.append(r)
    for r in pending:
        best, best_d = None, None
        if r.get("hora_dt"):
            for ph in photos:
                if ph["ruta"] in used or ph.get("hora_exif") is None:
                    continue
                d = (ph["hora_exif"] + datetime.timedelta(seconds=clock_offset_s) - r["hora_dt"]).total_seconds()
                if abs(d) <= tolerance_s and (best_d is None or abs(d) < abs(best_d)):
                    best, best_d = ph, d
        if best is not None:
            used.add(best["ruta"])
            pairs.append((r, best, "hora", best_d))
        else:
            warnings.append("Parcela {} {} (fila {}): sin foto correspondiente.".format(
                r["parcela"], r.get("punto_norm") or "", r["fila"]))
            pairs.append((r, None, "sin foto", None))
    for ph in photos:
        if ph["ruta"] not in used:
            warnings.append("Foto {} sin fila en el formulario (no se usa).".format(ph["nombre"]))
    pairs.sort(key=lambda t: t[0]["fila"])
    return pairs, warnings


# ----------------------------------------------------------------------
# Máscara desde la altura del dosel
# ----------------------------------------------------------------------
def zenith_from_height(canopy_height_m, camera_height_m=DEFAULT_CAMERA_HEIGHT_M,
                       footprint_radius_m=DEFAULT_FOOTPRINT_M):
    """Ángulo cenital límite θ = atan(radio de la huella / (altura del dosel − altura de la cámara))."""
    h = float(canopy_height_m) - float(camera_height_m)
    if h <= 0:
        raise ValueError("La altura del dosel debe ser mayor que la altura de la cámara.")
    return math.degrees(math.atan(float(footprint_radius_m) / h))


# ----------------------------------------------------------------------
# Análisis de una foto
# ----------------------------------------------------------------------
_SKY_SPLIT_RE = re.compile(r"otro punto de partida da otro corte \(([^)]*)\) que separa dos brillos del cielo.*")


def short_reason(reason):
    """v0.14.46: etiqueta breve de un motivo para cada foto del lote; la explicación completa va en los avisos."""
    m = _SKY_SPLIT_RE.match(reason)
    if m:
        return "otro corte separa dos brillos del cielo ({})".format(m.group(1))
    return reason


def analyze_photo(path, calibration, zenith_max_deg, channel_mode="blue_red", sky_is_bright=True,
                  cut_rule="glama", fixed_cut=None):
    """
    Analiza una foto con la calibración dada y la máscara (cenit máximo, grados). Devuelve dict con
    caco, modif_caco, apertura, cierre, fraccion_claros, corte, metodo_corte, visible_pct, tamaño y avisos.
    """
    # v0.14.38: sin parámetros ignorados en silencio
    if cut_rule == "fixed" and fixed_cut is None:
        raise ValueError("cut_rule='fixed' requiere fixed_cut.")
    if cut_rule != "fixed" and fixed_cut is not None:
        raise ValueError("fixed_cut solo se usa con cut_rule='fixed' (se recibió cut_rule={!r}).".format(cut_rule))
    if cut_rule not in ("glama", "otsu", "fixed"):
        raise ValueError("cut_rule desconocido: {!r}".format(cut_rule))
    img, _scale, orig = load_oriented_rgb_image(path, max_dim=MAX_ANALYSIS_DIM)
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    cal = scale_calibration_to_image(calibration, w, h)
    R = cal.get("virtual_radius_px")
    if not R:
        raise ValueError("La calibración no define el radio del hemisferio.")
    # v0.14.23: centro de la calibración (como en el análisis de una foto); antes siempre el centro de
    # la imagen, distinto del diálogo con un ojo de pez cuyo círculo detectado no está centrado.
    cc = cal.get("center_xy")
    c = (float(cc[0]), float(cc[1])) if cc is not None else (w / 2.0, h / 2.0)
    proj = cal.get("projection", "polar")
    gray = extract_channel(arr, channel_mode)
    warns = []
    if cal.pop("center_note", None):
        warns.append("foto girada respecto de la calibración con centro desplazado: se usó el centro de la imagen")
    meas = calibration.get("measurement") or {}
    ref = meas.get("image_size")
    if ref:
        a_ref = max(ref) / float(min(ref))
        a_now = max(w, h) / float(min(w, h))
        if abs(a_ref - a_now) > 0.01 * a_now:
            warns.append("proporción de la foto distinta de la calibración")
    method = cut_rule
    # Corte automático (recomendado log-normal) y comprobación del método: siempre se registra
    diag = {"cut": None, "ok": False, "reasons": ["cielo oscuro: sin corte automático"], "starts": {}}
    if sky_is_bright:
        hist = glama_ring_counts_with_gray(gray, GLAMA_CUT_START, c, R, zenith_max_deg,
                                           calibration=cal, projection=proj)["histogram"]
        diag = glama_cut_diagnosis(hist)
    auto_cut = diag["cut"]
    revisar = False
    if cut_rule == "fixed":
        t = int(fixed_cut)
        method = "fijo"          # el lote lo cambia a «revisado (decisión guardada)» si viene de la revisión
    elif cut_rule == "otsu":
        rp = compute_radius_grid((h, w), c)
        area = compute_zenith_grid(rp, cal) <= zenith_max_deg
        t = compute_otsu_threshold(gray, area)
    else:
        revisar = not diag["ok"]
        if auto_cut is None:
            rp = compute_radius_grid((h, w), c)
            area = compute_zenith_grid(rp, cal) <= zenith_max_deg
            t = compute_otsu_threshold(gray, area)
            method = "otsu provisional (sin recomendación log-normal)"
        else:
            t = auto_cut
            method = "recomendado (log-normal)"
    sky = threshold_image(gray, t, sky_is_bright=sky_is_bright)
    # Uniformidad del cielo. v0.14.46: con cielo no uniforme la foto queda «a revisar» (verificar el corte en
    # «Revisar cortes…»); en v0.14.42–45 era solo un aviso.
    area = compute_zenith_grid(compute_radius_grid((h, w), c), cal) <= zenith_max_deg
    sky_range = sky_uniformity_range(gray, sky & area, area) if sky_is_bright else None
    sky_short = sky_uniformity_warning(sky_range, short=True)
    reasons = list(diag["reasons"]) if not diag["ok"] else []
    if sky_short:
        reasons.append(sky_short)
    if cut_rule == "glama":
        revisar = bool(reasons)
        if revisar:
            warns.append("revisar el corte: " + "; ".join(short_reason(r) for r in reasons))
    elif sky_short:
        warns.append(sky_short)
    counts = glama_ring_counts(sky, c, R, zenith_max_deg, calibration=cal, projection=proj)
    idx = glama_indices(counts, calibration=cal, radius_px=R)
    try:
        vis = analysis_circle_visibility((h, w), c, float(zenith_to_pixel_radius(zenith_max_deg, cal)))
    except (ValueError, KeyError, ZeroDivisionError):
        vis = None
    if vis is not None and vis < 99.5:
        warns.append("círculo de análisis visible {:.1f} %".format(vis))
    return {
        # v0.14.62: el CaCo de la foto se registra con 2 decimales y todos los cálculos usan ese valor
        "caco": round_pct(idx["canopy_cover_index_pct"]),
        "modif_caco": idx["spherical_cover_pct"],
        "apertura": idx["canopy_openness_pct"],
        "cierre": idx["canopy_closure_pct"],
        "fraccion_claros": idx["gap_fraction_pct"],
        # v0.14.51: apertura y cierre siguen la convención de GLAMA: referidos a los anillos que alcanza
        # la foto (hasta este cenit), no al hemisferio
        "apertura_ref_cenit": round(float(idx.get("reference_zenith_deg") or 0.0), 2),
        "corte": int(t),
        "metodo_corte": method,
        "corte_auto": auto_cut,
        "revisar": revisar,
        "motivo_revision": "; ".join(reasons),
        "inicios": "; ".join("{}→{}".format(k, v) for k, v in diag.get("starts", {}).items()),
        "visible_pct": vis,
        "cielo_rango": sky_range,
        "ancho": w, "alto": h, "original": orig,
        "avisos": warns,
    }


# ----------------------------------------------------------------------
# Lote completo
# ----------------------------------------------------------------------
def _auto_form_rows(photo_folder, photos_per_plot=5):
    """Filas del formulario creadas desde las fotos (orden de hora), sin archivo. Devuelve (filas, avisos)."""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".csv", prefix="cobdosel_form_")
    os.close(fd)
    try:
        _p, nph, warns = draft_form_from_photos(photo_folder, tmp, photos_per_plot)
        rows, w2 = read_field_form(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    n = max(1, int(photos_per_plot))
    msg = ("Sin formulario de fotos: {} fotos asignadas por orden de hora a {} parcelas de {} fotos. Las parcelas "
           "se forman por hora de captura, no por ubicación: verifique la asignación antes de usar las medias de "
           "parcela (o use un formulario).".format(nph, -(-nph // n), n))
    warns = [w for w in warns if not w.endswith("abarcan más de 20 min; revise la asignación.")]   # v0.14.69
    return rows, [msg] + warns + w2


def run_batch(photo_folder, form_path, calibration, planned_plots, mask_mode="fixed",
              canopy_height_m=None, camera_height_m=DEFAULT_CAMERA_HEIGHT_M,
              footprint_radius_m=DEFAULT_FOOTPRINT_M, fixed_mask_deg=DEFAULT_MASK_DEG, channel_mode="blue_red",
              sky_is_bright=True, cut_rule="glama", fixed_cut=None,
              tolerance_s=DEFAULT_TOLERANCE_S, clock_offset_s=0.0, progress=None, log=None,
              canopy_group=None, decisions=None, photos_per_plot=5):
    """
    Ejecuta el lote. mask_mode: «fixed» (fixed_mask_deg sobre el horizonte; 63° por defecto) o
    «height» (máscara desde canopy_height_m, una altura de referencia del sitio, p. ej. la de un grupo
    de dosel). decisions: decisiones de la revisión visual de cortes {archivo: {decision, corte, ...}}
    (ver load_decisions). form_path y planned_plots son opcionales (v0.14.42): sin formulario, las fotos se
    ordenan por hora y se asignan a parcelas de photos_per_plot fotos, como «Crear formulario desde las
    fotos». Devuelve dict con fotos, parcelas, sitio, avisos y parámetros. v0.14.64: sitio["tiempo_proceso_s"]
    = duración del procesamiento (s).
    """
    import time as _time
    _t0 = _time.perf_counter()
    decisions = decisions or {}
    if mask_mode == "height":
        if canopy_height_m is None:
            raise ValueError("Máscara desde la altura: indique la altura del dosel del sitio.")
        zen_height = zenith_from_height(canopy_height_m, camera_height_m, footprint_radius_m)
    elif mask_mode == "fixed":
        if fixed_mask_deg is None or not 0.0 <= float(fixed_mask_deg) < 90.0:
            raise ValueError("Máscara fija no válida (0–90° sobre el horizonte).")
    else:
        raise ValueError("mask_mode desconocido: {}".format(mask_mode))

    def _log(msg, level="INFO"):
        if callable(log):
            log(msg, level)

    if form_path:
        rows, warnings = read_field_form(form_path)
    else:
        rows, warnings = _auto_form_rows(photo_folder, photos_per_plot)
    photos = scan_photos(photo_folder)
    pairs, w2 = match_photos(rows, photos, tolerance_s, clock_offset_s)
    warnings += w2
    if calibration.get("calibration_method") == "glama_radius":       # v0.14.63: función retirada
        warnings.insert(0, GLAMA_RADIUS_WARNING)
    # Cámaras/lentes: una calibración vale para una lente y un encuadre (no para otra lente o zoom)
    cal_cam = calibration.get("camera") or (calibration.get("measurement") or {}).get("camera")
    if cal_cam and not (cal_cam.get("model") or cal_cam.get("focal_length_mm") or cal_cam.get("focal_length_35mm")):
        cal_cam = None          # huella sin EXIF útil (foto de calibración sin modelo ni focal)
    used = [ph for _r, ph, _h, _d in pairs if ph is not None]
    groups = camera_groups(used)
    if groups:
        warnings.append("Fotos por cámara/lente: " + "; ".join("{}: {}".format(lbl, n) for lbl, n, _c in groups))
    if not cal_cam and len(groups) > 1:
        raise ValueError(
            "Las fotos son de {} cámaras/lentes distintas y la calibración no registra la cámara:\n• {}\n"
            "Separe las fotos por cámara y procese cada grupo con su calibración, o vuelva a guardar la "
            "calibración en CobDosel ≥ 0.12.4 con una foto de esa cámara.".format(
                len(groups), "\n• ".join("{}: {} fotos".format(lbl, n) for lbl, n, _c in groups)))
    if not cal_cam and len(groups) == 1:
        warnings.append("La calibración no registra la cámara. Todas las fotos son de una misma lente ({}): "
                        "verifique que sea la de la calibración y regístrela con «Registrar cámara…».".format(
                            groups[0][0]))
    elif not cal_cam:
        warnings.append("La calibración no registra la cámara: no se pudo verificar la lente de las fotos.")
    results = []
    n = len(pairs)
    for i, (r, ph, how, diff) in enumerate(pairs):
        rec = {"parcela": r["parcela"], "reemplaza_a": r.get("reemplaza_a") or "",
               "punto": r.get("punto_norm") or (r.get("punto") or ""), "fila": r["fila"],
               "id_foto": r.get("id_foto") or "", "hora_formulario": r.get("hora_captura") or "",
               "archivo": ph["nombre"] if ph else "", "emparejado_por": how,
               "dif_hora_s": diff,
               "hora_exif": ph["hora_exif"].isoformat(sep=" ") if ph and ph.get("hora_exif") else "",
               "calidad": r.get("calidad") or "", "valida": False, "motivo": "",
               "camara": camera_label(ph.get("camara")) if ph else "",
               "tamano_px": "{}×{}".format(*ph["camara"]["size"]) if ph and ph.get("camara") else "",
               "mascara_horizonte": None, "cenit_max": None}
        try:
            if ph is None:
                rec["motivo"] = "sin foto"
            elif r.get("excluida_por_calidad"):
                rec["motivo"] = "excluida por calidad («{}»)".format(r.get("calidad"))
            elif cal_cam and compare_cameras(cal_cam, ph.get("camara"))[0] is False:
                rec["motivo"] = "calibración de otra cámara/lente: " + "; ".join(
                    compare_cameras(cal_cam, ph.get("camara"))[1])
            else:
                # v0.14.23: foto sin EXIF comparable → se analiza, pero se deja constancia en la fila
                cam_unverified = bool(cal_cam) and compare_cameras(cal_cam, ph.get("camara"))[0] is None
                zen = 90.0 - float(fixed_mask_deg) if mask_mode == "fixed" else zen_height
                rec["cenit_max"] = zen
                rec["mascara_horizonte"] = 90.0 - zen
                dec = decisions.get(ph["nombre"])
                if dec and dec.get("canal") and dec.get("canal") != channel_mode:
                    warnings.append("{}: la revisión se hizo con otro canal ({}); se ignora.".format(
                        ph["nombre"], dec.get("canal")))
                    dec = None
                rec.update({"decision": "", "analista": "", "nota": ""})
                if dec and dec.get("decision") == "excluido":
                    rec.update({"decision": "excluido", "analista": dec.get("operador", ""),
                                "nota": dec.get("nota", ""), "corte_auto": dec.get("corte_auto")})
                    when = (dec.get("fecha") or "").replace("T", " ")[:16]
                    rec["revision_guardada"] = "{}{}".format(when + ", " if when else "", dec.get("operador") or
                                                             "analista sin nombre")
                    rec["motivo"] = "excluida por el analista (decisión guardada: {})".format(rec["revision_guardada"]) + (
                        " — {}".format(dec["nota"]) if dec.get("nota") else "")
                else:
                    use_fixed = dec and dec.get("decision") in ("aceptado", "ajustado")
                    res = analyze_photo(ph["ruta"], calibration, zen, channel_mode, sky_is_bright,
                                        "fixed" if use_fixed else cut_rule,
                                        int(dec["corte"]) if use_fixed else (fixed_cut if cut_rule == "fixed" else None))
                    rec.update(res)
                    rec["valida"] = True
                    if use_fixed:
                        rec["decision"] = dec["decision"] if dec["decision"] == "aceptado" or (
                            res.get("corte_auto") == int(dec["corte"])) else "ajustado"
                        if rec["decision"] == "ajustado":
                            rec["decision"] = "ajustado ({} → {})".format(res.get("corte_auto"), int(dec["corte"]))
                        rec["analista"], rec["nota"] = dec.get("operador", ""), dec.get("nota", "")
                        rec["metodo_corte"] = "revisado (decisión guardada)"
                        rec["revisar"] = False
                        res["avisos"] = [a for a in res["avisos"] if not a.startswith("revisar el corte")]
                        # v0.14.45: la decisión viene del archivo de revisión guardado; se dice cuándo y quién
                        when = (dec.get("fecha") or "").replace("T", " ")[:16]
                        who = dec.get("operador") or "analista sin nombre"
                        rec["revision_guardada"] = "{}{}".format(when + ", " if when else "", who)
                        tag = "decisión guardada ({})".format(rec["revision_guardada"])
                        orig = []
                        if res.get("motivo_revision"):   # v0.14.42: por qué el método automático no se comprobó
                            orig = [short_reason(x) for x in res["motivo_revision"].split("; ")]
                            tag += "; motivo original: " + "; ".join(orig)
                        # v0.14.56: sin repetir en «Observaciones» lo que ya dice el motivo original
                        res["avisos"] = [a for a in res["avisos"] if a not in orig]
                        res["avisos"].insert(0, tag)
                    elif cut_rule == "glama":
                        rec["decision"] = "pendiente de revisión" if res.get("revisar") else "automático"
                    if cam_unverified:
                        res["avisos"].append("cámara no verificada (la foto no tiene modelo ni distancia focal en el EXIF)")
                    rec["motivo"] = "; ".join(res["avisos"])
        except Exception as e:      # una foto defectuosa no detiene el lote
            rec["motivo"] = "error: {}".format(e)
            _log("{}: {}".format(rec.get("archivo") or rec["parcela"], e), "WARN")
        results.append(rec)
        if callable(progress):
            progress(i + 1, n)
    common = summarize_common_warnings(results)
    summary = aggregate(results, planned_plots)
    summary["sitio"]["tiempo_proceso_s"] = round(_time.perf_counter() - _t0, 1)      # v0.14.64
    warnings = common + warnings          # v0.14.46: los avisos comunes primero (tras «Resultado provisional»)
    return {"fotos": results, "parcelas": summary["parcelas"], "sitio": summary["sitio"],
            "avisos": sorted(warnings + summary["avisos"], key=lambda w: not w.startswith("Resultado provisional")),
            "parametros": {"carpeta": photo_folder,
                           "formulario": form_path or "sin formulario: asignación por orden de hora, {} fotos por "
                                                       "parcela".format(int(photos_per_plot)),
                           "calibracion": calibration.get("lens_name") or calibration.get("projection_label"),
                           "camara_calibracion": camera_label(cal_cam) if cal_cam else "no registrada",
                           # v0.14.27: la calibración completa queda registrada con el resultado
                           **calibration_record(calibration),
                           "mascara_modo": "fija" if mask_mode == "fixed" else "altura del dosel",
                           "mascara_horizonte_deg": (float(fixed_mask_deg) if mask_mode == "fixed"
                                                     else round(90.0 - zen_height, 2)),
                           # v0.14.48: la máscara desde la altura del dosel ya no está en la ventana; sus
                           # parámetros solo se registran si se usa desde código
                           **({"grupo_dosel": canopy_group, "altura_dosel_sitio_m": canopy_height_m,
                               "altura_camara_m": camera_height_m, "radio_huella_m": footprint_radius_m}
                              if mask_mode == "height" else {}),
                           # v0.14.45: nombres legibles, no códigos internos
                           "canal": CHANNEL_LABELS.get(channel_mode, channel_mode),
                           "regla_corte": CUT_RULE_LABELS.get(cut_rule, cut_rule),
                           "tolerancia_s": tolerance_s, "desfase_reloj_s": clock_offset_s,
                           "parcelas_planificadas": planned_plots or None}}


def calibration_record(calibration):
    """Datos de la calibración para el registro del lote (CSV del sitio e informe HTML)."""
    cal = calibration or {}
    meta = cal.get("calibration_metadata") or {}
    d = cal.get("circle_diameter_cm") or meta.get("circle_diameter_cm")
    h = cal.get("camera_height_cm") or meta.get("camera_height_cm")
    method = cal.get("calibration_method")
    if method == "glama_radius":
        method = "radio de GLAMA ({:g} px)".format(float(cal.get("glama_radius_px") or 0))
    elif not method:
        method = ("círculo D/H" if d else
                  "detección del círculo de 180°" if cal.get("lens_type") == "fisheye" else "—")
    w, hh = cal.get("image_width_px"), cal.get("image_height_px")
    fmm = calibration_focal_mm(dict(cal, circle_diameter_cm=d, camera_height_cm=h))
    return {
        "calibracion_modelo": cal.get("projection_label") or cal.get("projection"),
        "calibracion_metodo": method,
        "circulo_D_cm": round(float(d), 2) if d else None,
        "altura_H_cm": round(float(h), 2) if h else None,
        "radio_hemisferio_px": round(float(cal["virtual_radius_px"]), 1) if cal.get("virtual_radius_px") else None,
        "calibracion_foto_px": "{}×{}".format(w, hh) if w and hh else None,
        "calibracion_guardada": cal.get("saved_at"),
        "focal_equivalente_mm": round(fmm, 2) if fmm else None,
    }


CUT_RULE_LABELS = {
    "glama": "recomendado (log-normal) por foto, iterado desde 128; Otsu provisional si no hay recomendación",
    "otsu": "automático: Otsu (1979) por foto",
    "fixed": "fijo (mismo valor para todas las fotos)",
}
DECISIONS_FILE = "CobDosel_revision_cortes.json"


def _decision_summary(results):
    """Texto «20 fotos: 16 automáticas, 2 aceptadas, 1 ajustada, 1 excluida»."""
    from collections import Counter
    cnt = Counter()
    for r in results:
        d = (r.get("decision") or "").split(" (")[0]
        if d:
            cnt[d] += 1
    if not cnt:
        return ""
    order = ("automático", "aceptado", "ajustado", "excluido", "pendiente de revisión")
    labels = {"automático": ("automática", "automáticas"),
              "aceptado": ("revisada sin cambio", "revisadas sin cambio"),
              "ajustado": ("ajustada", "ajustadas"),
              "excluido": ("excluida por el analista", "excluidas por el analista"),
              "pendiente de revisión": ("pendiente de revisión", "pendientes de revisión")}
    return "{} fotos: {}".format(sum(cnt.values()), ", ".join(
        "{} {}".format(cnt[k], labels[k][0 if cnt[k] == 1 else 1]) for k in order if cnt.get(k)))


def load_decisions(folder):
    """Decisiones de la revisión visual guardadas junto a las fotos ({} si no hay archivo)."""
    p = os.path.join(folder, DECISIONS_FILE)
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return dict(data.get("fotos") or {})


def applied_text(decisions):
    """v0.14.61: «Se aplicó 1 decisión guardada (…)» / «Se aplicaron 3 decisiones guardadas (…)»."""
    return "{} {}".format("Se aplicó" if len(decisions) == 1 else "Se aplicaron", decisions_summary(decisions))


def decisions_summary(decisions):
    """v0.14.45: «7 decisiones guardadas (2026-10-24 10:40 a 10:52; analista: J. Fallas)»."""
    if not decisions:
        return ""
    dates = sorted((d.get("fecha") or "").replace("T", " ")[:16] for d in decisions.values() if d.get("fecha"))
    ops = sorted({d.get("operador") for d in decisions.values() if d.get("operador")})
    when = ""
    if dates:
        when = dates[0] if dates[0] == dates[-1] else "{} a {}".format(
            dates[0], dates[-1][11:] if dates[-1][:10] == dates[0][:10] else dates[-1])
    n = len(decisions)          # v0.14.61: singular y plural correctos
    return "{} {}{}".format(
        n, "decisión guardada" if n == 1 else "decisiones guardadas", " ({}{})".format(when, "; analista: " + ", ".join(ops) if ops else "; sin nombre de analista")
        if (when or ops) else "")


def save_decisions(folder, decisions, version=""):
    """Guarda las decisiones (archivo JSON en la carpeta de fotos). Devuelve la ruta."""
    p = os.path.join(folder, DECISIONS_FILE)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"plugin": "CobDosel", "version": version,
                   "guardado": datetime.datetime.now().isoformat(timespec="seconds"),
                   "fotos": decisions}, f, indent=2, ensure_ascii=False)
    return p


def _scope(n, total, noun="fotos"):
    return ("Todas las {} ({} de {})".format(noun, n, total) if n == total else
            "{} de {} {}".format(n, total, noun))


def summarize_common_warnings(results):
    """
    v0.14.46: un aviso por tipo de observación, diciendo a cuántas fotos se aplica («Todas las fotos (9 de 9)»
    o «3 de 9 fotos»), con la explicación completa una sola vez; en cada foto queda una etiqueta breve.
    Modifica en el lugar el motivo de las fotos excluidas por otra cámara (etiqueta breve). Devuelve la lista
    de avisos.
    """
    out = []
    with_photo = [r for r in results if r.get("archivo")]
    valid = [r for r in with_photo if r.get("valida")]
    cam = [r for r in with_photo if str(r.get("motivo", "")).startswith("calibración de otra cámara/lente")]
    if cam:
        detail = cam[0]["motivo"].split(": ", 1)[1] if ": " in cam[0]["motivo"] else ""
        out.append("{}: calibración de otra cámara o lente ({}); se excluyen. Calibre esa cámara o elija su "
                   "calibración.".format(_scope(len(cam), len(with_photo)), detail))
        for r in cam:
            r["motivo"] = "calibración de otra cámara/lente (ver avisos)"
    # v0.14.63: el cielo no uniforme ya no va en los avisos: lo dice sky_review_line junto al resultado del
    # sitio (antes aparecía dos veces en el informe y en el panel)
    split = [r for r in valid if "separa dos brillos del cielo" in str(r.get("motivo_revision") or "")]
    if split:
        out.append("{}: otro punto de partida da otro corte que separa dos brillos de lo que ya es cielo (nubes de "
                   "distinto brillo, cielo azul o sol). El corte de la foto se mantiene; verifíquelo en «Revisar "
                   "cortes…».".format(_scope(len(split), len(valid), "fotos válidas")))
    return out


def duration_text(seconds, n_photos=None):
    """v0.14.64: «42 s», «3 min 05 s» o «1 h 02 min», y «(22 fotos; 1.9 s por foto)»."""
    from ._version import fmt_num
    if seconds is None:
        return "—"
    s = max(0.0, float(seconds))
    if s < 60:
        txt = "{} s".format(fmt_num(s, 1) if s < 10 else int(round(s)))
    elif s < 3600:
        m, r = divmod(int(round(s)), 60)
        txt = "{} min {:02d} s".format(m, r)
    else:
        h, r = divmod(int(round(s)), 3600)
        txt = "{} h {:02d} min".format(h, r // 60)
    if n_photos:
        txt += " ({} foto{}; {} s por foto)".format(n_photos, "" if n_photos == 1 else "s",
                                                    fmt_num(s / float(n_photos), 1))
    return txt


def round_pct(value, decimals=2):
    """v0.14.62: redondeo a la mitad hacia arriba sobre el valor decimal escrito (70.005 -> 70.01), no el
    redondeo bancario de round(); así el número mostrado es el número calculado."""
    if value is None:
        return None
    q = Decimal(1).scaleb(-int(decimals))
    return float(Decimal(repr(float(value))).quantize(q, rounding=ROUND_HALF_UP))


PLOT_TIME_SPREAD_S = 20 * 60     # v0.14.69: fotos de una parcela con más de 20 min de diferencia
PLOT_RANGE_POINTS = 30.0         # v0.14.69: rango del CaCo dentro de una parcela que pide revisión


def _parse_time(txt):
    try:
        return datetime.datetime.fromisoformat(str(txt).strip()) if txt else None
    except ValueError:
        return None


def plot_consistency_warnings(results):
    """v0.14.69: avisos (no cambian el resultado) cuando las fotos de una parcela no parecen de una misma
    parcela: de más de un día, con más de 20 min entre la primera y la última, o con un rango del CaCo de más
    de 30 puntos. Sirve con cualquier diseño de muestreo y con o sin formulario."""
    from ._version import fmt_num
    by_plot, order = {}, []
    for r in results:
        p = r.get("parcela")
        if p not in by_plot:
            by_plot[p] = []
            order.append(p)
        by_plot[p].append(r)
    out = []
    for p in order:
        rs = by_plot[p]
        times = [t for t in (_parse_time(r.get("hora_exif")) for r in rs if r.get("archivo")) if t]
        days = sorted({t.date() for t in times})
        if len(days) > 1:
            out.append("Parcela {}: fotos de {} días ({}); revise la asignación de parcelas.".format(
                p, len(days), ", ".join(d.strftime("%d/%m/%Y") for d in days)))
        elif len(times) > 1 and (max(times) - min(times)).total_seconds() > PLOT_TIME_SPREAD_S:
            out.append("Parcela {}: fotos con {} de diferencia (más de {} min); revise la asignación de "
                       "parcelas.".format(p, duration_text((max(times) - min(times)).total_seconds()),
                                         PLOT_TIME_SPREAD_S // 60))
        vals = [r["caco"] for r in rs if r.get("valida") and r.get("caco") is not None]
        if len(vals) > 1 and max(vals) - min(vals) > PLOT_RANGE_POINTS:
            out.append("Parcela {}: el CaCo de sus fotos va de {} a {} % ({} puntos, más de {:.0f}); revise si son "
                       "de la misma parcela o si hay un claro o una copa aislada.".format(
                           p, fmt_num(min(vals)), fmt_num(max(vals)), fmt_num(max(vals) - min(vals)),
                           PLOT_RANGE_POINTS))
    return out


def mean_pct(values, decimals=2):
    """v0.14.62: media exacta en decimal de valores ya redondeados (sin error de coma flotante: la media de
    70.00 y 70.01 es 70.005 -> 70.01), redondeada a la mitad hacia arriba."""
    vals = [Decimal(repr(float(v))) for v in values]
    if not vals:
        return None
    q = Decimal(1).scaleb(-int(decimals))
    return float((sum(vals) / len(vals)).quantize(q, rounding=ROUND_HALF_UP))


def aggregate(results, planned_plots):
    """Medias por parcela (fotos válidas disponibles) y media del sitio (Índice CaCo).

    v0.14.62: el sitio es la media de TODAS las fotos válidas (una sola muestra), no la media de las medias de
    parcela; si una parcela tiene menos fotos válidas, pesa menos. Fotos, parcelas y sitio con 2 decimales."""
    plots = {}
    order = []
    for r in results:
        p = r["parcela"]
        if p not in plots:
            plots[p] = {"parcela": p, "reemplaza_a": r.get("reemplaza_a") or "", "fotos": 0,
                        "validas": 0, "caco": []}
            order.append(p)
        plots[p]["fotos"] += 1
        if r.get("valida"):
            plots[p]["validas"] += 1
            plots[p]["caco"].append(r["caco"])
        if r.get("reemplaza_a"):
            plots[p]["reemplaza_a"] = r["reemplaza_a"]
    rows, warnings, all_valid = [], [], []
    for p in order:
        d = plots[p]
        vals = [round_pct(v) for v in d.pop("caco")]
        all_valid.extend(vals)
        d["caco_media"] = mean_pct(vals)
        d["caco_min"] = min(vals) if vals else None
        d["caco_max"] = max(vals) if vals else None
        if not vals:
            warnings.append("Parcela {}: sin fotos válidas; no entra en la media del sitio "
                            "(aplique el mecanismo de reemplazo).".format(p))
        rows.append(d)
    warnings += plot_consistency_warnings(results)        # v0.14.69
    empty = [d for d in rows if d["caco_media"] is None]
    if rows and len(empty) == len(rows) and len(rows) > 1:      # v0.14.46: un solo aviso si ninguna tiene
        warnings = [w for w in warnings if not w.endswith("(aplique el mecanismo de reemplazo).")]
        warnings.append("Ninguna parcela tiene fotos válidas ({} parcelas): no hay resultado del sitio.".format(len(rows)))
    means = [d["caco_media"] for d in rows if d["caco_media"] is not None]
    # v0.14.62: media de todas las fotos válidas (con 2 decimales), no media de las medias de parcela
    site_mean = mean_pct(all_valid)
    n_ok = len(means)
    if planned_plots and n_ok != int(planned_plots):
        warnings.append("Parcelas con resultado: {} de {}.".format(n_ok, int(planned_plots)))
    site = {
        "parcelas_planificadas": int(planned_plots) if planned_plots else None,
        "parcelas_con_resultado": n_ok,
        "fotos_validas": sum(d["validas"] for d in rows),
        "fotos_total": sum(d["fotos"] for d in rows),
        "caco_sitio": site_mean,
        "completo": bool(planned_plots) and n_ok == int(planned_plots),
        "pendientes_revision": sum(1 for r in results if r.get("valida") and r.get("revisar")),
        "revision": _decision_summary(results),
    }
    # v0.14.63: «Resultado provisional» ya no va en los avisos: el informe y el panel lo dicen junto al resultado
    return {"parcelas": rows, "sitio": site, "avisos": warnings}


# ----------------------------------------------------------------------
# Salidas
# ----------------------------------------------------------------------
PHOTO_CSV_COLUMNS = ("parcela", "reemplaza_a", "punto", "archivo", "id_foto", "emparejado_por",
                     "hora_formulario", "hora_exif", "dif_hora_s", "calidad", "valida", "motivo",
                     "camara", "tamano_px",
                     "mascara_horizonte", "cenit_max", "corte", "metodo_corte", "corte_auto", "decision",
                     "analista", "nota", "motivo_revision", "inicios",
                     "caco", "modif_caco", "apertura", "cierre", "fraccion_claros", "visible_pct",
                     "cielo_rango", "apertura_ref_cenit")
PLOT_CSV_COLUMNS = ("parcela", "reemplaza_a", "fotos", "validas", "caco_media", "caco_min", "caco_max")


def write_csvs(batch, out_prefix, version="", delimiter=",", decimal="."):
    """Escribe <prefijo>_fotos.csv, <prefijo>_parcelas.csv y <prefijo>_sitio.csv. Devuelve las rutas.

    v0.14.63: separador de columnas y decimal elegibles (el diálogo usa los de la configuración regional,
    csv_format.csv_style: «;» y coma decimal donde la coma es decimal, para que Excel abra las columnas)."""
    from .csv_format import csv_row
    paths = []
    p1 = out_prefix + "_fotos.csv"
    with open(p1, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(PHOTO_CSV_COLUMNS)
        for r in batch["fotos"]:
            w.writerow(csv_row([r.get(k) for k in PHOTO_CSV_COLUMNS], decimal))
    paths.append(p1)
    p2 = out_prefix + "_parcelas.csv"
    with open(p2, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(PLOT_CSV_COLUMNS)
        for r in batch["parcelas"]:
            w.writerow(csv_row([r.get(k) for k in PLOT_CSV_COLUMNS], decimal))
    paths.append(p2)
    p3 = out_prefix + "_sitio.csv"
    with open(p3, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=delimiter)
        s = batch["sitio"]
        prm = batch["parametros"]
        keys = list(s.keys()) + ["param_" + k for k in prm.keys()] + ["plugin", "plugin_version"]
        w.writerow(keys)
        w.writerow(csv_row(list(s.values()) + list(prm.values()), decimal) + ["CobDosel", version])
    paths.append(p3)
    return paths


def sky_review_line(results, analyst=None):
    """v0.14.48: línea del cielo no uniforme en el informe: cuántas fotos y quién verificó sus cortes."""
    from .canopy_analysis import SKY_UNIFORMITY_LIMIT
    valid = [r for r in results if r.get("valida")]
    sky = [r for r in valid if (r.get("cielo_rango") or 0) > SKY_UNIFORMITY_LIMIT]
    if not sky:
        return ""
    vals = [r["cielo_rango"] for r in sky]
    rng = "{:.0f}".format(vals[0]) if len(vals) == 1 else "{:.0f}–{:.0f}".format(min(vals), max(vals))
    # v0.14.63: única mención del cielo no uniforme en el informe y el panel (antes también en los avisos)
    head = ("{}: cielo no uniforme (rango de brillo del cielo {}, límite {:.0f}: nubes de distinto brillo, cielo "
            "azul, sol o resplandor).").format(_scope(len(sky), len(valid), "fotos válidas"), rng, SKY_UNIFORMITY_LIMIT)
    done = [r for r in sky if str(r.get("decision") or "").startswith(("aceptado", "ajustado"))]
    names = sorted({str(r.get("analista") or "").strip() for r in done if str(r.get("analista") or "").strip()})
    who = ", ".join(names) or (str(analyst).strip() if analyst and str(analyst).strip() else "analista sin nombre")
    if done and len(done) == len(sky):
        return "{} Verificadas por {}.".format(head, who)
    if done:
        return "{} Verificadas por {}: {}; sin verificar: {} (use «Revisar cortes…»).".format(
            head, who, len(done), len(sky) - len(done))
    return ("{} Sin verificar: revise sus cortes en «Revisar cortes…»; si es posible, repita esas fotos con cielo "
            "uniforme.".format(head))


# v0.14.55: nombres legibles de los parámetros en el informe HTML (el CSV conserva las claves)
PARAM_LABELS = {
    "carpeta": "Carpeta de fotos", "formulario": "Formulario de fotos", "calibracion": "Calibración",
    "camara_calibracion": "Cámara de la calibración", "calibracion_modelo": "Modelo de proyección",
    "calibracion_metodo": "Método de calibración", "circulo_D_cm": "Círculo de referencia D (cm)",
    "altura_H_cm": "Distancia H (cm)", "radio_hemisferio_px": "Radio del hemisferio R (px)",
    "calibracion_foto_px": "Tamaño de la foto de calibración (px)", "calibracion_guardada": "Calibración guardada",
    "focal_equivalente_mm": "Focal equivalente (mm)", "mascara_modo": "Máscara",
    "mascara_horizonte_deg": "Máscara de horizonte (°)", "grupo_dosel": "Grupo de dosel",
    "altura_dosel_sitio_m": "Altura del dosel del sitio (m)", "altura_camara_m": "Altura de la cámara (m)",
    "radio_huella_m": "Radio de la huella (m)", "canal": "Canal de color", "regla_corte": "Nivel de corte",
    "tolerancia_s": "Tolerancia de hora (s)", "desfase_reloj_s": "Desfase del reloj (s)",
    "parcelas_planificadas": "Número de parcelas", "revision_cortes": "Revisión de cortes",
    "sitio": "Sitio", "area_ha": "Área del AOI (ha)", "analista": "Analista",
}
_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(:\d{2}(\.\d+)?)?$")


def _param_text(v):
    """v0.14.55: «—» para valores vacíos (antes «None») y fechas ISO como «2026-10-23 11:56»."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return "—"
    if isinstance(v, str):
        m = _ISO_RE.match(v.strip())
        if m:
            return "{} {}".format(m.group(1), m.group(2))
    return str(v)


def write_html(batch, path, version="", site_name=""):
    """Informe HTML autocontenido del lote (sitio, parcelas, fotos, avisos y parámetros)."""
    import html as _h
    from ._version import fmt_num

    def _f(v, d=2):
        return "—" if v is None else fmt_num(v, d)

    s = batch["sitio"]
    prm = batch["parametros"]
    # v0.14.48: «Reemplazo» solo si alguna parcela reemplaza a otra; «Fotos válidas» como «4 de 5», centrado
    has_repl = any(p.get("reemplaza_a") for p in batch["parcelas"])
    plot_rows = "".join(
        "<tr><td>{}</td>{}<td class='c'>{} de {}</td><td class='n'><b>{}</b></td>"
        "<td class='n'>{}</td><td class='n'>{}</td></tr>".format(
            _h.escape(str(p["parcela"])),
            ("<td>{}</td>".format(_h.escape("reemplaza a " + str(p["reemplaza_a"])) if p.get("reemplaza_a")
                                  else "—")) if has_repl else "",
            p["validas"], p["fotos"], _f(p["caco_media"]),
            # v0.14.57: con una sola foto válida, mín. = máx. = media no son tres mediciones: «—»
            _f(p["caco_min"]) if (p.get("validas") or 0) > 1 else "—",
            _f(p["caco_max"]) if (p.get("validas") or 0) > 1 else "—")
        for p in batch["parcelas"])
    # v0.14.45: «Observaciones» en una segunda fila bajo cada foto, a todo el ancho
    def _photo_row(r):
        cls = "" if r.get("valida") else " bad"
        main = ("<tr class='ph{}'><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class='n'>{}</td><td>{}</td>"
                "<td>{}</td><td class='n'>{}</td><td class='n'>{}</td><td class='n'><b>{}</b></td></tr>").format(
            cls, _h.escape(str(r["parcela"])), _h.escape(str(r["punto"])), _h.escape(str(r["archivo"])),
            _h.escape(str(r["emparejado_por"])), r.get("corte", "—"),
            _h.escape(str(r.get("metodo_corte") or "—")), _h.escape(str(r.get("decision") or "")),
            _f(r.get("mascara_horizonte"), 1), _f(r.get("visible_pct"), 1), _f(r.get("caco")))
        obs = str(r.get("motivo") or "")
        if not obs:
            return main.replace("class='ph", "class='ph last", 1)
        items = "".join("<li>{}</li>".format(_h.escape(t.strip())) for t in obs.split("; ") if t.strip())
        return main + "<tr class='obs{}'><td></td><td colspan='9'><ul>{}</ul></td></tr>".format(cls, items)
    photo_rows = "".join(_photo_row(r) for r in batch["fotos"])
    # v0.14.47: fotos con cielo no uniforme, junto al resultado del sitio
    from .canopy_analysis import SKY_UNIFORMITY_LIMIT
    nsky = sum(1 for r in batch["fotos"] if r.get("valida") and (r.get("cielo_rango") or 0) > SKY_UNIFORMITY_LIMIT)
    sky_html = ("<p style='color:#9a3412;font-weight:700'>{}</p>".format(
        _h.escape(sky_review_line(batch["fotos"], prm.get("analista"))))) if nsky else ""
    pending = s.get("pendientes_revision") or 0
    pending_html = ("<p style='color:#9a3412;font-weight:700'>Resultado provisional: {} pendiente{} de revisión "
                    "del nivel de corte («Revisar cortes…»).</p>".format(
                        "1 foto" if pending == 1 else "{} fotos".format(pending), "" if pending == 1 else "s")
                    ) if pending else ""
    warn = "".join("<li>{}</li>".format(_h.escape(w)) for w in batch["avisos"]) or "<li>Ninguno.</li>"
    params = "".join("<tr><td>{}</td><td>{}</td></tr>".format(_h.escape(PARAM_LABELS.get(k, k)),
                                                              _h.escape(_param_text(v)))
                     for k, v in prm.items())
    doc = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<title>CobDosel — lote {site}</title>
<style>
body{{font-family:Segoe UI,Roboto,Arial,sans-serif;background:#f4f7f6;color:#1f2933;margin:0;padding:24px}}
.c{{max-width:1080px;margin:0 auto}} header{{background:#0b4f5e;color:#fff;padding:18px 24px;border-radius:10px}}
section{{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:16px 20px;margin-top:16px}}
.big{{font-size:2.4rem;font-weight:800}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
th,td{{padding:6px 8px;border-bottom:1px solid #e4e7eb;text-align:left}}
th{{background:#f0f4f8}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} td.c,th.c{{text-align:center}} tr.bad td{{color:#9a3412}}
tr.ph td{{border-bottom:none}} tr.ph.last td{{border-bottom:1px solid #e4e7eb}}
tr.obs td{{font-size:.82rem;color:#52606d;padding-top:0}} tr.obs ul{{margin:0;padding-left:18px}}
</style></head><body><div class="c">
<header><h1>CobDosel v{version} — Cobertura del dosel por sitio</h1>
<div>Sitio: {site}{op}</div></header>
<section><div>Cobertura del dosel del sitio (media de todas las fotos válidas, Índice CaCo)</div>
<div class="big">{mean} %</div>
<p>Parcelas con resultado: {nok}{nplan} · Fotos válidas: {fv} de {ft}</p>
<p>Método del nivel de corte: {rule}</p>
<p>Revisión del nivel de corte: {rev}</p>
<p>Tiempo de procesamiento: {dur}</p>{pending_html}{sky_html}</section>
<section><h2>Parcelas</h2><table><tr><th>Parcela</th>{repl_th}<th class='c'>Fotos válidas</th>
<th class='n'>CaCo media (%)</th><th class='n'>Mín.</th><th class='n'>Máx.</th></tr>{plots}</table>
<p style='font-size:.82rem;color:#52606d'>Mín. y Máx.: entre las fotos válidas de la parcela; «—» si tiene una sola.
Cálculo: CaCo de cada foto con 2 decimales; la media de cada parcela es descriptiva; el resultado del sitio es la
media de todas las fotos válidas, redondeada a 2 decimales.</p></section>
<section><h2>Fotos</h2><table><tr><th>Parcela</th><th>Punto</th><th>Archivo</th><th>Emparejado por</th>
<th class='n'>Corte</th><th>Método del corte</th><th>Decisión</th><th class='n'>Máscara (°)</th><th class='n'>Visible (%)</th><th class='n'>CaCo (%)</th>
</tr>{photos}</table><p style='font-size:.82rem;color:#52606d'>Debajo de cada foto, sus observaciones.</p></section>
<section><h2>Avisos</h2><ul>{warn}</ul></section>
<section><h2>Parámetros</h2><table>{params}</table></section>
<footer style="text-align:center;color:#52606d;margin-top:16px">Basado en Tichý (2016),
<a href="https://doi.org/10.1111/jvs.12350" target="_blank">doi:10.1111/jvs.12350</a>.<br/>
<strong>CobDosel v{version}</strong> para QGIS · Autor: Jorge Fallas · Contacto:
<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer></div></body></html>""".format(
        site=_h.escape(site_name or "—"), version=version, mean=_f(s["caco_sitio"]),
        rev=_h.escape(s.get("revision") or "—"), pending_html=pending_html,
        dur=_h.escape(duration_text(s.get("tiempo_proceso_s"), s.get("fotos_total"))),
        rule=_h.escape(CUT_RULE_LABELS.get(prm.get("regla_corte"), str(prm.get("regla_corte")))),
        op=(" · Analista: " + _h.escape(str(prm["analista"]))) if prm.get("analista") else "",
        sky_html=sky_html, repl_th="<th>Reemplazo</th>" if has_repl else "",
        nok=s["parcelas_con_resultado"], nplan=(" de {}".format(s["parcelas_planificadas"]) if s.get("parcelas_planificadas") else ""),
        fv=s["fotos_validas"], ft=s["fotos_total"], plots=plot_rows, photos=photo_rows, warn=warn,
        params=params)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
