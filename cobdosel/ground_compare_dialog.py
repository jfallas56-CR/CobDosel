"""Ventana «Comparar clasificaciones» de «Cobertura del suelo» (CobDosel 0.15.12).

Compara dos CobDosel_suelo_<foto>_puntos.csv de la misma foto y la misma cuadrícula (doble clasificación del
protocolo): acuerdo observado, kappa de Cohen, tabla de confusión y puntos en desacuerdo. Si la foto y la cuadrícula
están abiertas en «Cobertura del suelo», doble clic en un desacuerdo lleva la vista a ese punto. Cálculo en
ground_compare.py.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import webbrowser

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QTextEdit, QListWidget, QListWidgetItem, QGroupBox,
)

from ._version import VERSION
from .ui_keys import disable_enter_buttons
from . import ground_compare as gcmp

HELP = ("Dos analistas clasifican la misma foto con la <b>misma área y la misma semilla</b> (el segundo usa «Cargar área "
        "y cuadrícula de un CSV…» con el CSV de foto del primero) y exportan su CSV de puntos. Elija los dos "
        "<i>_puntos.csv</i> y pulse «Comparar». Con la foto abierta en «Cobertura del suelo», doble clic en un punto "
        "en desacuerdo lleva la vista a ese punto para resolverlo por consenso.")


class GroundCompareDialog(QDialog):
    def __init__(self, parent=None, ground_dialog=None):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Comparar clasificaciones")
        self.resize(820, 680)
        self.ground = ground_dialog
        self.res = None
        lv = QVBoxLayout(self)
        h = QLabel(HELP); h.setWordWrap(True); lv.addWidget(h)
        g = QGroupBox("Clasificaciones"); f = QFormLayout(g)
        self.file_a, self.file_b = QLineEdit(), QLineEdit()
        self.name_a, self.name_b = QLineEdit("Analista A"), QLineEdit("Analista B")
        for le, nm, lbl in ((self.file_a, self.name_a, "A"), (self.file_b, self.name_b, "B")):
            row = QHBoxLayout(); row.addWidget(le, 1)
            b = QPushButton("Examinar…"); b.clicked.connect(lambda _c=False, e=le: self._browse(e)); row.addWidget(b)
            f.addRow("CSV de puntos {}:".format(lbl), row)
            f.addRow("Nombre {}:".format(lbl), nm)
        lv.addWidget(g)
        g2 = QGroupBox("Criterio"); f2 = QFormLayout(g2)
        self.only_unc = QCheckBox("Comparar solo los puntos que la regla de Canopeo dejó sin clasificar")
        self.only_unc.setChecked(True)
        self.only_unc.setToolTip("En el modo reglamentario los puntos verdes automáticos son iguales para todos los "
                                 "analistas; el acuerdo se mide en los demás.")
        f2.addRow(self.only_unc)
        self.min_ag = QDoubleSpinBox(); self.min_ag.setRange(0, 100); self.min_ag.setDecimals(0)
        self.min_ag.setSuffix(" %"); self.min_ag.setValue(gcmp.DEFAULT_MIN_AGREEMENT)
        self.min_k = QDoubleSpinBox(); self.min_k.setRange(0, 1); self.min_k.setDecimals(2); self.min_k.setSingleStep(0.05)
        self.min_k.setValue(gcmp.DEFAULT_MIN_KAPPA)
        f2.addRow("Acuerdo mínimo:", self.min_ag)
        f2.addRow("Kappa mínimo:", self.min_k)
        lv.addWidget(g2)
        row = QHBoxLayout()
        self.cmp_btn = QPushButton("Comparar"); self.cmp_btn.clicked.connect(self._on_compare); row.addWidget(self.cmp_btn)
        self.html_btn = QPushButton("Exportar informe HTML…"); self.html_btn.setEnabled(False)
        self.html_btn.clicked.connect(self._on_html); row.addWidget(self.html_btn)
        lv.addLayout(row)
        self.out = QTextEdit(); self.out.setReadOnly(True); lv.addWidget(self.out, 1)
        lv.addWidget(QLabel("Puntos en desacuerdo (doble clic: ir al punto en «Cobertura del suelo»):"))
        self.dis_list = QListWidget(); self.dis_list.itemDoubleClicked.connect(self._on_goto); lv.addWidget(self.dis_list, 1)
        close = QPushButton("Cerrar"); close.clicked.connect(self.accept); lv.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        disable_enter_buttons(self)

    def _browse(self, edit):
        p, _ = QFileDialog.getOpenFileName(self, "CSV de puntos de CobDosel", "", "CSV de puntos (*_puntos.csv);;CSV (*.csv)")
        if p:
            edit.setText(p)

    def compare(self):
        a = gcmp.read_points_csv(self.file_a.text().strip())
        b = gcmp.read_points_csv(self.file_b.text().strip())
        self.res = gcmp.compare(a, b, self.only_unc.isChecked(), self.min_ag.value(), self.min_k.value())
        na, nb = self.name_a.text().strip() or "A", self.name_b.text().strip() or "B"
        lines = gcmp.summary_lines(self.res, na, nb)
        cats = self.res["categorias"]
        if cats:
            lines += ["", "Tabla de confusión (filas: {}; columnas: {}):".format(na, nb)]
            lines.append("{:<22}".format("") + "".join("{:>14}".format(c[:13]) for c in cats))
            for ca in cats:
                lines.append("{:<22}".format(ca[:21]) + "".join("{:>14}".format(self.res["matriz"][(ca, cb)])
                                                                 for cb in cats))
        self.out.setPlainText("\n".join(lines))
        self.dis_list.clear()
        for d in self.res["desacuerdos"]:
            it = QListWidgetItem("Punto {}: {} = {} · {} = {}".format(d["punto"], na, d["clase_a"], nb, d["clase_b"]))
            it.setData(Qt.ItemDataRole.UserRole, d["punto"])
            self.dis_list.addItem(it)
        self.html_btn.setEnabled(True)
        return self.res

    def _on_compare(self):
        try:
            self.compare()
        except Exception as e:
            self.res = None
            self.html_btn.setEnabled(False)
            QMessageBox.warning(self, "Comparar clasificaciones", str(e))

    def goto_point(self, punto):
        """Lleva la vista de «Cobertura del suelo» al punto (número 1…n) si la misma foto y cuadrícula están abiertas."""
        g = self.ground
        if g is None or not self.res or not getattr(g, "points", None):
            return False, "Abra la foto en «Cobertura del suelo» y prepare la misma área y cuadrícula."
        if os.path.basename(g.photo_path or "") != self.res["archivo"] or len(g.points) != self.res["n_puntos"]:
            return False, ("En «Cobertura del suelo» está abierta otra foto u otra cuadrícula: abra {} con la misma área "
                           "y semilla.".format(self.res["archivo"]))
        d = next((x for x in self.res["desacuerdos"] if x["punto"] == punto), None)
        x, y = g.points[punto - 1]
        if d is not None and (abs(x - d["x"]) > gcmp.POINT_TOL_PX or abs(y - d["y"]) > gcmp.POINT_TOL_PX):
            return False, "La cuadrícula abierta no coincide con la del CSV (otra semilla o otra área)."
        g.goto_point(punto - 1)
        return True, ""

    def _on_goto(self, item):
        ok, msg = self.goto_point(int(item.data(Qt.ItemDataRole.UserRole)))
        if not ok:
            QMessageBox.information(self, "Ir al punto", msg)

    def _on_html(self):
        if not self.res:
            return
        base = os.path.splitext(self.file_a.text().strip())[0].replace("_puntos", "")
        p, _ = QFileDialog.getSaveFileName(self, "Informe de la comparación", base + "_comparacion.html", "HTML (*.html)")
        if not p:
            return
        if not p.lower().endswith((".html", ".htm")):
            p += ".html"
        gcmp.write_html(self.res, p, self.name_a.text().strip() or "A", self.name_b.text().strip() or "B",
                        os.path.basename(self.file_a.text()), os.path.basename(self.file_b.text()), VERSION)
        if QMessageBox.question(self, "Informe guardado", "{}\n\n¿Abrir el informe ahora?".format(p),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == \
                QMessageBox.StandardButton.Yes:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(p)):
                webbrowser.open("file://" + os.path.abspath(p))
