"""Punto de entrada del complemento CobDosel para QGIS.

Autor: Jorge Fallas (jfallas56@gmail.com)

Historial:
- 0.12.0: entrada de menú «Procesamiento por sitio (lote)».
- 0.11.0: cambio de nombre a CobDosel (clase, menú, icono y registro).
- 0.10.0 (2026-10-17): el diálogo se importa al abrirlo (initGui no falla si falta
  una dependencia); aviso claro de dependencias faltantes; unload() no borra
  temporales que siguen cargados como capas; QAction compatible Qt5/Qt6.
"""

import os
import logging

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox

try:  # Qt6: QAction vive en QtGui
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction

from ._version import VERSION

_LOG = logging.getLogger("CobDosel")

MENU_NAME = "&CobDosel"


def _missing_dependencies():
    """Lista de paquetes Python obligatorios que no se pueden importar."""
    missing = []
    for module, package in (("numpy", "numpy"), ("PIL", "Pillow")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing


class CobDosel:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.batch_action = None
        self.dialog = None
        self.batch_dialog = None

    def _icon(self):
        path = os.path.join(self.plugin_dir, "cobdosel.svg")
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
        return QIcon.fromTheme("mIconRaster")

    def initGui(self):
        self.action = QAction(
            self._icon(),
            "CobDosel: Cobertura del dosel",
            self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU_NAME, self.action)
        self.batch_action = QAction(
            self._icon(), "CobDosel: Procesamiento por sitio (lote)", self.iface.mainWindow())
        self.batch_action.triggered.connect(self.run_batch)
        self.iface.addPluginToMenu(MENU_NAME, self.batch_action)

    def unload(self):
        if self.dialog is not None:
            try:
                self.dialog.cleanup_temp_files(only_unused=True)
                self.dialog.close()
                self.dialog.deleteLater()
            except RuntimeError as e:  # objeto Qt ya destruido
                _LOG.debug("[unload] %s", e)
        if self.action:
            self.iface.removePluginMenu(MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.batch_action:
            self.iface.removePluginMenu(MENU_NAME, self.batch_action)
        if self.batch_dialog is not None:
            try:
                self.batch_dialog.close()
                self.batch_dialog.deleteLater()
            except RuntimeError as e:
                _LOG.debug("[unload lote] %s", e)
        self.action = None
        self.batch_action = None
        self.dialog = None
        self.batch_dialog = None

    def run(self):
        if self.dialog is None:
            missing = _missing_dependencies()
            if missing:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "CobDosel v{} — Dependencias faltantes".format(VERSION),
                    "Faltan paquetes de Python necesarios: {}.\n\n"
                    "Instálelos en el Python de QGIS (OSGeo4W Shell en Windows):\n"
                    "    python -m pip install {}".format(
                        ", ".join(missing), " ".join(missing)
                    ),
                )
                return
            from .canopy_dialog import CobDoselDialog
            self.dialog = CobDoselDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def run_batch(self):
        missing = _missing_dependencies()
        if missing:
            QMessageBox.critical(self.iface.mainWindow(), "CobDosel — Dependencias faltantes",
                                 "Faltan paquetes de Python: {}.".format(", ".join(missing)))
            return
        if self.batch_dialog is None:
            from .batch_dialog import CobDoselBatchDialog
            self.batch_dialog = CobDoselBatchDialog(self.iface, self.iface.mainWindow())
        self.batch_dialog.show()
        self.batch_dialog.raise_()
        self.batch_dialog.activateWindow()
