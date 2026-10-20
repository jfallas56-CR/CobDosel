"""CobDosel — Cobertura del dosel a partir de fotografías (basado en Tichý 2016) para QGIS.

La versión se define en _version.py (VERSION).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""


def classFactory(iface):
    """Punto de entrada del complemento en QGIS."""
    from .cobdosel_plugin import CobDosel
    return CobDosel(iface)
