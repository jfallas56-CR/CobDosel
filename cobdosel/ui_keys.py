"""Comportamiento de teclado común a las ventanas de CobDosel (v0.14.39).

En un diálogo de Qt, Intro «pulsa» el botón predeterminado; si no hay uno, el primer botón con
autoDefault (p. ej. «Cargar imagen…»). Al escribir un valor en una casilla (zoom, D, H, corte) y pulsar
Intro, se abría el selector de archivos o se cerraba la ventana. Con esta función Intro solo confirma
el valor de la casilla y nunca pulsa un botón; Esc sigue cerrando la ventana.
"""

from qgis.PyQt.QtWidgets import QPushButton


def disable_enter_buttons(dialog):
    """Ningún botón del diálogo se activa con Intro."""
    for b in dialog.findChildren(QPushButton):
        b.setAutoDefault(False)
        b.setDefault(False)
