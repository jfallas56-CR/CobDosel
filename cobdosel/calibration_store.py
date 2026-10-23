"""Persistencia de calibraciones de lente en archivos JSON para reutilizar entre sesiones.

v0.11.0 (CobDosel): carpeta ~/.cobdosel/calibrations. Las calibraciones guardadas con CAnOPY
(~/.canopy/calibrations) se siguen listando y cargando (solo lectura); al guardarlas de nuevo
quedan en la carpeta nueva.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import json
import datetime
import logging

_LOG = logging.getLogger("CobDosel")


DEFAULT_DIR = os.path.join(
    os.path.expanduser("~"), ".cobdosel", "calibrations"
)
# Carpeta de CAnOPY ≤ 0.10 (nombre anterior): solo lectura
LEGACY_DIR = os.path.join(
    os.path.expanduser("~"), ".canopy", "calibrations"
)


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def calibration_path(lens_name, directory=None):
    directory = directory or DEFAULT_DIR
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in lens_name)
    return os.path.join(directory, safe + ".json")


def save_calibration(lens_name, calibration, metadata=None, directory=None):
    directory = directory or DEFAULT_DIR
    _ensure_dir(directory)

    payload = {
        "lens_name": lens_name,
        "saved_at": datetime.datetime.now().isoformat(),
        "calibration": calibration,
        "metadata": metadata or {},
    }

    path = calibration_path(lens_name, directory)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def load_calibration(lens_name, directory=None, return_full_payload=False):
    path = calibration_path(lens_name, directory)
    if not os.path.isfile(path) and directory is None:
        legacy = calibration_path(lens_name, LEGACY_DIR)
        if os.path.isfile(legacy):
            path = legacy
    if not os.path.isfile(path):
        raise FileNotFoundError("No se encontró la calibración: " + path)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if return_full_payload:
        return payload
    cal = dict(payload["calibration"])
    if "metadata" in payload and isinstance(payload["metadata"], dict):
        cal.setdefault("calibration_metadata", payload["metadata"])
    cal.setdefault("lens_name", payload.get("lens_name", lens_name))
    cal.setdefault("saved_at", payload.get("saved_at"))
    return cal


def list_calibrations(directory=None):
    """Lista (nombre, ruta). Sin directorio explícito incluye también las de CAnOPY."""
    dirs = [directory] if directory else [DEFAULT_DIR, LEGACY_DIR]
    result = []
    seen = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json") or fname in seen:
                continue
            path = os.path.join(d, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                seen.add(fname)
                result.append((payload.get("lens_name", fname), path))
            except (OSError, ValueError) as e:
                # JSON dañado o ilegible: se omite de la lista, pero queda registrado.
                _LOG.warning("[list_calibrations] %s: %s", path, e)
                continue
    return result


# v0.14.27: nombre de la última calibración usada (cargada o guardada), para aplicarla al abrir CobDosel
LAST_FILE = "_ultima_calibracion.txt"


def get_last_calibration(directory=None):
    """Nombre de la última calibración usada, o None si no hay o ya no existe."""
    path = os.path.join(directory or DEFAULT_DIR, LAST_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            name = f.read().strip()
    except OSError:
        return None
    if not name:
        return None
    if not (os.path.isfile(calibration_path(name, directory))
            or (directory is None and os.path.isfile(calibration_path(name, LEGACY_DIR)))):
        return None
    return name


def set_last_calibration(name, directory=None):
    """Recuerda el nombre de la última calibración usada (no crítico si falla)."""
    directory = directory or DEFAULT_DIR
    try:
        _ensure_dir(directory)
        with open(os.path.join(directory, LAST_FILE), "w", encoding="utf-8") as f:
            f.write(str(name))
    except OSError as e:
        _LOG.warning("[set_last_calibration] %s", e)
