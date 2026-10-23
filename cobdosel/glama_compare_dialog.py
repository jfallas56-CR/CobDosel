"""Diálogo «Comparar con GLAMA (tabla)» de CobDosel (v0.14.41).

Compara varias fotos con los valores anotados de la app GLAMA y separa la diferencia de CaCo en
residuo de la reproducción, efecto del corte y efecto de la geometría (ver glama_compare.py).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import traceback

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QDoubleSpinBox, QFileDialog, QMessageBox, QProgressBar, QTextEdit, QApplication,
)

from .ui_keys import disable_enter_buttons
from .canopy_analysis import CHANNEL_MODES
from .glama_engine import GLAMA_CENTER_DY
from . import glama_compare as gc


class GlamaCompareDialog(QDialog):
    """Comparación por tabla: app GLAMA ↔ reproducción ↔ CobDosel."""

    def showEvent(self, event):  # noqa: N802 (API de Qt)
        disable_enter_buttons(self)
        super().showEvent(event)

    def __init__(self, calibration, calibration_name="", channel_mode="blue_red",
                 center_dy=GLAMA_CENTER_DY, sky_is_bright=True, folder="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparar con GLAMA (tabla)")
        self.calibration = calibration
        self.sky_is_bright = sky_is_bright
        self.out_paths = []
        lay = QVBoxLayout(self)
        intro = QLabel(
            "Para cada foto: A = CaCo de la app GLAMA; B = reproducción de la pantalla de GLAMA con el "
            "corte de GLAMA (B − A ≈ 0 comprueba la reproducción); C = la misma reproducción con el corte "
            "de CobDosel (C − B = efecto del corte, único cambio); D = CobDosel con su geometría "
            "(D − C = efecto de la geometría).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()

        self.table_edit = QLineEdit()
        t_btn = QPushButton("…")
        t_btn.clicked.connect(self._pick_table)
        tpl_btn = QPushButton("Crear plantilla…")
        tpl_btn.setToolTip("Crea un CSV con las fotos de la carpeta y las columnas por llenar.")
        tpl_btn.clicked.connect(self._make_template)
        row = QHBoxLayout()
        row.addWidget(self.table_edit, 1)
        row.addWidget(t_btn)
        row.addWidget(tpl_btn)
        self.table_edit.setToolTip(
            "CSV o Excel. Columnas: {}. Obligatorias: archivo y corte_glama. caco_glama: valor de la\n"
            "app (para comprobar la reproducción). giro_180 / giro_90 / transponer: 1 si la casilla\n"
            "estaba marcada en GLAMA. radio_glama: si falta, se usa el radio global. corte_cobdosel:\n"
            "corte fijo (p. ej. revisado); si falta, el corte recomendado.".format(", ".join(gc.TABLE_COLUMNS)))
        form.addRow("Tabla de GLAMA:", row)

        self.folder_edit = QLineEdit(folder or "")
        f_btn = QPushButton("…")
        f_btn.clicked.connect(self._pick_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder_edit, 1)
        row.addWidget(f_btn)
        self.folder_edit.setToolTip("Carpeta con las fotos originales del teléfono (con su EXIF), las mismas "
                                    "que se analizaron en GLAMA.")
        form.addRow("Carpeta de fotos:", row)

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.0, 20000.0)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSpecialValueText("(columna radio_glama)")
        g_r = (calibration or {}).get("glama_radius_px")
        self.radius_spin.setValue(float(g_r) if g_r else 0.0)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setToolTip("«Hemisph. radius» de GLAMA (px de su vista de 1080 px). La columna "
                                    "radio_glama de la tabla tiene prioridad.")
        form.addRow("Radio de GLAMA:", self.radius_spin)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Polar (lente regular / smartphone)", userData="polar")
        self.model_combo.addItem("Angular (ojo de pez)", userData="orthographic")
        form.addRow("Modelo en GLAMA:", self.model_combo)

        self.gmask_spin = QDoubleSpinBox()
        self.gmask_spin.setRange(0.0, 89.0)
        self.gmask_spin.setDecimals(1)
        self.gmask_spin.setValue(gc.DEFAULT_GLAMA_MASK_DEG)
        self.gmask_spin.setSuffix(" °")
        form.addRow("Máscara en GLAMA:", self.gmask_spin)

        self.cmask_spin = QDoubleSpinBox()
        self.cmask_spin.setRange(0.0, 89.0)
        self.cmask_spin.setDecimals(1)
        self.cmask_spin.setValue(gc.DEFAULT_GLAMA_MASK_DEG)
        self.cmask_spin.setSuffix(" °")
        self.cmask_spin.setToolTip("Máscara para D (CobDosel). Igual a la de GLAMA para que el efecto de la "
                                   "geometría no incluya un cambio de máscara.")
        form.addRow("Máscara en CobDosel (D):", self.cmask_spin)

        self.channel_combo = QComboBox()
        for code, label in CHANNEL_MODES:
            self.channel_combo.addItem(label, userData=code)
        i = self.channel_combo.findData(channel_mode)
        self.channel_combo.setCurrentIndex(max(0, i))
        self.channel_combo.setToolTip("El mismo canal que se usó en GLAMA.")
        form.addRow("Canal de color:", self.channel_combo)

        self.dy_spin = QDoubleSpinBox()
        self.dy_spin.setRange(-400.0, 400.0)
        self.dy_spin.setDecimals(1)
        self.dy_spin.setValue(float(center_dy))
        self.dy_spin.setSuffix(" px")
        form.addRow("Desplazamiento del centro:", self.dy_spin)

        cal_txt = "«{}» · {}".format(calibration_name or "sin guardar",
                                     (calibration or {}).get("projection_label")
                                     or (calibration or {}).get("projection") or "—") if calibration else \
            "ninguna: calibre primero en la ventana principal"
        form.addRow("Calibración de CobDosel (D):", QLabel(cal_txt))

        self.out_edit = QLineEdit()
        o_btn = QPushButton("…")
        o_btn.clicked.connect(self._pick_out)
        row = QHBoxLayout()
        row.addWidget(self.out_edit, 1)
        row.addWidget(o_btn)
        form.addRow("Resultado (CSV):", row)
        lay.addLayout(form)

        self.progress = QProgressBar()
        lay.addWidget(self.progress)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("font-family: monospace;")
        lay.addWidget(self.log_edit, 1)
        btns = QHBoxLayout()
        self.run_btn = QPushButton("Comparar")
        self.run_btn.clicked.connect(self.run)
        self.open_btn = QPushButton("Abrir resultado")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_out)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        for b in (self.run_btn, self.open_btn, close_btn):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.resize(760, 640)

    # ------------------------------------------------------------------
    def _log(self, msg, level="INFO"):
        color = {"WARN": "#b26a00", "ERROR": "#b00020"}.get(level)
        txt = msg.replace("&", "&amp;").replace("<", "&lt;")
        self.log_edit.append("<span style='color:{}'>{}</span>".format(color, txt) if color else txt)

    def _pick_table(self):
        p, _ = QFileDialog.getOpenFileName(self, "Tabla de GLAMA", self.folder_edit.text(),
                                           "Tablas (*.csv *.xlsx *.txt)")
        if p:
            self.table_edit.setText(p)
            if not self.out_edit.text():
                self.out_edit.setText(os.path.splitext(p)[0] + "_comparacion.csv")

    def _pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Carpeta de fotos", self.folder_edit.text())
        if p:
            self.folder_edit.setText(p)

    def _pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, "Resultado", self.out_edit.text(), "CSV (*.csv)")
        if p:
            self.out_edit.setText(p if p.lower().endswith(".csv") else p + ".csv")

    def _make_template(self):
        folder = self.folder_edit.text()
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Plantilla", "Elija primero la carpeta de fotos.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Plantilla", os.path.join(folder, "comparacion_glama.csv"),
                                           "CSV (*.csv)")
        if not p:
            return
        n = gc.write_template(folder, p)
        self.table_edit.setText(p)
        if not self.out_edit.text():
            self.out_edit.setText(os.path.splitext(p)[0] + "_comparacion.csv")
        self._log("Plantilla con {} fotos: {}. Llénela con los valores de GLAMA y vuelva a esta ventana.".format(
            n, p))

    def _open_out(self):
        for p in self.out_paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def run(self):
        if not self.calibration:
            QMessageBox.warning(self, "Comparar con GLAMA", "No hay calibración activa en la ventana principal.")
            return
        table, folder, out = self.table_edit.text(), self.folder_edit.text(), self.out_edit.text()
        if not os.path.isfile(table) or not os.path.isdir(folder) or not out:
            QMessageBox.warning(self, "Comparar con GLAMA", "Indique la tabla, la carpeta de fotos y el resultado.")
            return
        self.run_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.progress.setValue(0)

        def prog(i, n):
            self.progress.setValue(int(100 * i / max(1, n)))
            QApplication.processEvents()
        try:
            res, summary, paths = gc.run_comparison(
                table, folder, self.calibration, out,
                glama_radius_px=self.radius_spin.value() or None,
                glama_mask_deg=self.gmask_spin.value(),
                channel_mode=self.channel_combo.currentData(),
                glama_projection=self.model_combo.currentData(),
                center_dy=self.dy_spin.value(), cob_mask_deg=self.cmask_spin.value(),
                sky_is_bright=self.sky_is_bright, log=self._log, progress=prog)
            self.out_paths = paths
            self._log("")
            for line in gc.summary_text(summary, res, self.gmask_spin.value(), self.cmask_spin.value(),
                                        self.channel_combo.currentData(), self.dy_spin.value()).splitlines():
                self._log(line.replace(" ", " "))
            self._log("Resultados: " + "; ".join(paths))
            self.open_btn.setEnabled(True)
        except Exception as e:
            self._log("ERROR: {}".format(e), "ERROR")
            self._log(traceback.format_exc(), "ERROR")
        finally:
            self.run_btn.setEnabled(True)
