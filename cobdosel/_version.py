"""Versión única del complemento CobDosel (fuente de verdad para todos los módulos).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

VERSION = "0.14.40"


def fmt_int(value):
    """Entero con espacio como separador de miles: 1234567 -> '1 234 567'."""
    try:
        return "{:,}".format(int(value)).replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def fmt_num(value, decimals=2):
    """Real con punto decimal y espacio de miles: 1234.5 -> '1 234.50'."""
    try:
        return "{:,.{d}f}".format(float(value), d=decimals).replace(",", " ")
    except (TypeError, ValueError):
        return "—"
