"""«¿Desea abrirlo ahora en Excel?» (CobDosel 0.16.3): después de guardar CSV, ofrece abrirlos con el programa asociado a
los archivos .csv del sistema (Excel en Windows, LibreOffice Calc u otro). Una sola pregunta para uno o varios archivos.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import webbrowser

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMessageBox

OPEN_ONE = "¿Desea abrirlo ahora en Excel?"
OPEN_MANY = "¿Desea abrir los archivos ahora en Excel?"
OPEN_NOTE = "(se abre con el programa asociado a los archivos CSV)"


def saved_files_text(paths):
    """«Carpeta: …» una vez y los nombres de archivo debajo."""
    paths = list(paths)
    folders = {os.path.dirname(p) for p in paths}
    if len(folders) != 1:
        return "\n".join(paths)
    return "Carpeta: {}\n\n{}".format(folders.pop(), "\n".join("• " + os.path.basename(p) for p in paths))


def open_file(path, parent=None):
    """Abre un archivo con el programa asociado; devuelve False (y avisa) si no se pudo."""
    if QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
        return True
    try:
        return bool(webbrowser.open("file://" + os.path.abspath(path)))
    except webbrowser.Error as e:
        QMessageBox.warning(parent, "Abrir", "No se pudo abrir {}: {}".format(path, e))
        return False


def ask_open_csv(parent, paths, title="CSV guardados"):
    """Muestra los archivos guardados y pregunta si abrirlos en Excel; los abre si el usuario acepta.
    Devuelve True si se abrieron."""
    paths = [p for p in paths if p]
    if not paths:
        return False
    q = OPEN_ONE if len(paths) == 1 else OPEN_MANY
    ans = QMessageBox.question(parent, title, "{}\n\n{} {}".format(saved_files_text(paths), q, OPEN_NOTE),
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No)
    if ans != QMessageBox.StandardButton.Yes:
        return False
    for p in paths:
        open_file(p, parent)
    return True
