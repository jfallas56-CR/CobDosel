"""Formato de los CSV de CobDosel para que Excel los abra en columnas (v0.14.63).

Excel abre un CSV con el separador de listas y el separador decimal de la configuración regional de
Windows. Con coma decimal (Costa Rica, España…) el separador de listas es «;»: un CSV con «,» y punto
decimal se abre en una sola columna, o los números se leen como texto o como fechas. CobDosel escribe
entonces «;» y coma decimal; con punto decimal, «,» y punto. Los textos con el separador van entre comillas.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import numbers


def csv_style():
    """(separador de columnas, separador decimal) según la configuración regional de QGIS/Qt.

    Sin Qt (pruebas, scripts): («,», «.»)."""
    try:
        from qgis.PyQt.QtCore import QLocale
        dp = QLocale().decimalPoint()
        dp = dp if isinstance(dp, str) else str(dp)
    except Exception:          # sin Qt: formato internacional
        return ",", "."
    return (";", ",") if dp == "," else (",", ".")


NOT_APPLICABLE = "No aplica"     # v0.14.67: celdas sin valor (una base de datos no debe tener celdas vacías)
NO_DATA = "Sin datos"            # v0.14.68: dato que debía existir pero falta (p. ej., coordenadas del EXIF)


def csv_cell(value, decimal="."):
    """Valor de una celda: reales con el separador decimal indicado; None, texto vacío o lista vacía →
    «No aplica» (v0.14.67); lo demás sin cambio."""
    if value is None or (isinstance(value, str) and not value.strip()) or (
            isinstance(value, (list, tuple)) and not value):
        return NOT_APPLICABLE
    if isinstance(value, bool) or type(value).__name__ in ("bool_", "bool"):   # numpy 1 y 2
        return "Sí" if value else "No"           # v0.14.70: «Sí»/«No» en lugar de True/False
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        txt = repr(float(value))
        return txt.replace(".", decimal) if decimal != "." else txt
    return value


def csv_row(values, decimal="."):
    return [csv_cell(v, decimal) for v in values]
