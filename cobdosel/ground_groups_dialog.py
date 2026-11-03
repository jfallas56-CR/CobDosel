"""Ventana «Grupos de clases» de «Cobertura del suelo» (CobDosel 0.15.13).

Un grupo suma los puntos de varias clases (por ejemplo, «Vegetación total» = vegetación verde + vegetación no verde +
vegetación seca) y CobDosel informa su cobertura con el intervalo de Wilson de esa suma. Los grupos se guardan en
~/.cobdosel/grupos_suelo.json, como las clases nuevas. Cálculo en ground_cover.py.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QComboBox,
    QMessageBox, QGroupBox,
)

from .ui_keys import disable_enter_buttons
from . import ground_cover as gc

NEW = "(grupo nuevo)"
HELP = ("Un <b>grupo</b> suma los puntos de varias clases; por ejemplo, <b>«Vegetación total»</b> = vegetación verde + "
        "vegetación no verde + vegetación seca, cuando se quiere medir toda la vegetación y no solo la verde. CobDosel "
        "informa la cobertura del grupo con el intervalo de Wilson de la suma (no la suma de los intervalos), en la "
        "ventana, el CSV y el informe. Defina los grupos antes de empezar y use los mismos en todas las fotos.")


class GroupsDialog(QDialog):
    def __init__(self, classes, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Grupos de clases")
        self.resize(520, 480)
        self.classes = list(classes)
        self.groups = gc.groups_for(groups, self.classes)
        lv = QVBoxLayout(self)
        h = QLabel(HELP); h.setWordWrap(True); lv.addWidget(h)
        f = QFormLayout()
        self.combo = QComboBox(); self.combo.currentIndexChanged.connect(self._show)
        f.addRow("Grupo:", self.combo)
        self.name = QLineEdit()
        f.addRow("Nombre:", self.name)
        lv.addLayout(f)
        box = QGroupBox("Clases que suma el grupo"); bl = QVBoxLayout(box)
        self.checks = {}
        for k, l, _c in self.classes:
            cb = QCheckBox(l); self.checks[k] = cb; bl.addWidget(cb)
        lv.addWidget(box)
        row = QHBoxLayout()
        self.save_btn = QPushButton("Guardar grupo"); self.save_btn.clicked.connect(self._on_save); row.addWidget(self.save_btn)
        self.del_btn = QPushButton("Quitar grupo"); self.del_btn.clicked.connect(self._on_delete); row.addWidget(self.del_btn)
        lv.addLayout(row)
        self.defs = QLabel(""); self.defs.setWordWrap(True); lv.addWidget(self.defs)
        close = QPushButton("Cerrar"); close.clicked.connect(self.accept); lv.addWidget(close)
        disable_enter_buttons(self)
        self._fill()

    def _fill(self, select=None):
        self.combo.blockSignals(True)
        self.combo.clear()
        for g in self.groups:
            self.combo.addItem(g["nombre"])
        self.combo.addItem(NEW)
        i = self.combo.findText(select) if select else 0
        self.combo.setCurrentIndex(max(0, i))
        self.combo.blockSignals(False)
        self._show()
        self.defs.setText("<br>".join(gc.group_definition(g, self.classes) for g in self.groups) or "Sin grupos.")

    def _show(self, *_a):
        cur = self.combo.currentText()
        g = next((x for x in self.groups if x["nombre"] == cur), None)
        if g is None:                        # grupo nuevo: propone «Vegetación total» con las clases de vegetación
            names = {x["nombre"].lower() for x in self.groups}
            self.name.setText("Vegetación total" if "vegetación total" not in names else "")
            for k, l, _c in self.classes:
                self.checks[k].setChecked(k == "verde" or k == "seca" or "vegetaci" in l.lower())
        else:
            self.name.setText(g["nombre"])
            for k, cb in self.checks.items():
                cb.setChecked(k in g["clases"])
        self.del_btn.setEnabled(g is not None)

    def save_group(self, name, keys):
        cur = self.combo.currentText()
        self.groups = gc.set_group(self.groups, name, keys, self.classes, old_name=None if cur == NEW else cur)
        self._fill(select=name.strip())

    def delete_group(self, name):
        self.groups = [g for g in self.groups if g["nombre"] != name]
        self._fill()

    def _on_save(self):
        try:
            self.save_group(self.name.text(), [k for k, cb in self.checks.items() if cb.isChecked()])
        except ValueError as e:
            QMessageBox.warning(self, "Grupos de clases", str(e))

    def _on_delete(self):
        cur = self.combo.currentText()
        if cur != NEW:
            self.delete_group(cur)
