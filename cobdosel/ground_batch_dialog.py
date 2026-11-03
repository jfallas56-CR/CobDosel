"""Ventana «Cobertura del suelo — procesamiento por sitio» (CobDosel 0.16.0).

Elige la carpeta de fotos del sitio, la carpeta de resultados, un formulario de fotos opcional (el mismo del dosel:
parcela, punto, ID o hora), el sitio, el analista, la unidad del resultado (foto o parcela) y la semilla base. «Empezar o
continuar» lleva las fotos a «Cobertura del suelo», que las clasifica una tras otra con los mismos parámetros y guarda
cada una. «Resumen del sitio» calcula la media y el intervalo de 95 % (t de Student). Cálculo en ground_batch.py.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import webbrowser

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
    QFileDialog, QMessageBox, QListWidget, QGroupBox,
)

from ._version import VERSION
from .csv_format import csv_style
from .ui_keys import disable_enter_buttons
from . import ground_batch as gb

HELP = ("Prepare primero en «Cobertura del suelo» los parámetros comunes del sitio: modo de área (con área fija: lado, "
        "altura y calibración), número de puntos, clases, grupos y modo reglamentario. Aquí elija las fotos y pulse "
        "«Empezar o continuar»: cada foto se abre en «Cobertura del suelo» con la semilla <i>base + número de la foto</i>; "
        "«Guardar y foto siguiente» guarda sus CSV e informe en la carpeta de resultados. Si cierra y vuelve, continúa en "
        "la primera foto sin terminar. «Resumen del sitio» usa solo las fotos completas.")


class GroundBatchDialog(QDialog):
    def __init__(self, parent=None, ground_dialog=None):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Cobertura del suelo: procesamiento por sitio")
        self.resize(720, 620)
        self.ground = ground_dialog
        self.photos = []
        lv = QVBoxLayout(self)
        h = QLabel(HELP); h.setWordWrap(True); lv.addWidget(h)
        g = QGroupBox("Sitio"); f = QFormLayout(g)
        self.folder, self.out_dir, self.form = QLineEdit(), QLineEdit(), QLineEdit()
        for le, lbl, kind in ((self.folder, "Carpeta de fotos:", "dir"), (self.out_dir, "Carpeta de resultados:", "dir"),
                              (self.form, "Formulario de fotos (opcional):", "file")):
            row = QHBoxLayout(); row.addWidget(le, 1)
            b = QPushButton("Examinar…"); b.clicked.connect(lambda _c=False, e=le, k=kind: self._browse(e, k))
            row.addWidget(b); f.addRow(lbl, row)
        self.folder.textChanged.connect(lambda t: self.out_dir.setText(t) if not self.out_dir.text() else None)
        self.site, self.analyst = QLineEdit(), QLineEdit()
        f.addRow("Sitio:", self.site); f.addRow("Analista:", self.analyst)
        self.unit = QComboBox(); self.unit.addItem("Fotos (cada foto es una unidad)", "foto")
        self.unit.addItem("Parcelas (media de las fotos de cada parcela; requiere formulario)", "parcela")
        f.addRow("Unidad del resultado:", self.unit)
        self.base_seed = QSpinBox(); self.base_seed.setRange(0, 900000); self.base_seed.setValue(1000)
        self.base_seed.setToolTip("Semilla de cada foto = semilla base + número de la foto (1, 2, 3…), fija de antemano.")
        f.addRow("Semilla base:", self.base_seed)
        lv.addWidget(g)
        row = QHBoxLayout()
        self.list_btn = QPushButton("Ver fotos y estado"); self.list_btn.clicked.connect(self._on_list); row.addWidget(self.list_btn)
        self.start_btn = QPushButton("Empezar o continuar la clasificación"); self.start_btn.clicked.connect(self._on_start)
        row.addWidget(self.start_btn)
        self.sum_btn = QPushButton("Resumen del sitio"); self.sum_btn.clicked.connect(self._on_summary); row.addWidget(self.sum_btn)
        lv.addLayout(row)
        self.lst = QListWidget(); lv.addWidget(self.lst, 1)
        self.msg = QLabel(""); self.msg.setWordWrap(True); lv.addWidget(self.msg)
        close = QPushButton("Cerrar"); close.clicked.connect(self.accept); lv.addWidget(close)
        disable_enter_buttons(self)

    def _browse(self, edit, kind):
        if kind == "dir":
            p = QFileDialog.getExistingDirectory(self, "Carpeta", edit.text() or "")
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Formulario de fotos", "", "Formulario (*.xlsx *.csv)")
        if p:
            edit.setText(p)

    def load_photos(self):
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            raise ValueError("Elija la carpeta de fotos del sitio.")
        out = self.out_dir.text().strip() or folder
        os.makedirs(out, exist_ok=True)
        self.out_dir.setText(out)
        form = self.form.text().strip() or None
        if self.unit.currentData() == "parcela" and not form:
            raise ValueError("La unidad «Parcelas» necesita el formulario de fotos.")
        self.photos, warnings = gb.site_photos(folder, form)
        self.lst.clear()
        for p in self.photos:
            where = " · parcela {} {}".format(p["parcela"], p["punto"] or "") if p.get("parcela") else ""
            self.lst.addItem("{:>3}. {}{} — {}".format(p["numero"], p["nombre"], where,
                                                       gb.photo_status(out, p["nombre"])))
        self.msg.setText("\n".join(warnings[:8]) + ("\n…" if len(warnings) > 8 else ""))
        return self.photos, warnings

    def _on_list(self):
        try:
            self.load_photos()
        except Exception as e:
            QMessageBox.warning(self, "Procesamiento por sitio", str(e))

    def start(self):
        photos, _w = self.load_photos()
        if self.ground is None:
            raise ValueError("Abra «Cobertura del suelo».")
        idx = self.ground.start_batch(photos, self.out_dir.text().strip(), self.base_seed.value(),
                                      self.site.text().strip(), self.analyst.text().strip())
        self.ground.show(); self.ground.raise_()
        return idx

    def _on_start(self):
        try:
            self.start()
        except Exception as e:
            QMessageBox.warning(self, "Procesamiento por sitio", str(e))

    def summary(self):
        photos, _w = self.load_photos()
        out = self.out_dir.text().strip()
        recs, variables, warnings = gb.site_records(photos, out)
        if not recs:
            raise ValueError("Ninguna foto está completa todavía.")
        unit = self.unit.currentData()
        summ, plots = gb.summarize_site(recs, variables, unit)
        sep, dec = csv_style()
        paths = gb.write_site(recs, variables, summ, plots, out, self.site.text().strip(), unit, VERSION, sep, dec,
                              warnings)
        self.msg.setText("Resumen guardado:\n" + "\n".join(paths))
        return paths, summ

    def _on_summary(self):
        try:
            paths, _s = self.summary()
        except Exception as e:
            QMessageBox.warning(self, "Resumen del sitio", str(e))
            return
        html = [p for p in paths if p.endswith(".html")][0]
        if QMessageBox.question(self, "Resumen del sitio", "{}\n\n¿Abrir el informe ahora?".format(html),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == \
                QMessageBox.StandardButton.Yes:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(html)):
                webbrowser.open("file://" + os.path.abspath(html))
