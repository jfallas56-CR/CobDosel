"""Ventana «Calibrar con baldosas o un rectángulo conocido» de CobDosel (v0.15.3).

Una o dos fotos tomadas hacia abajo de un rectángulo de tamaño conocido en el suelo (bloque de baldosas, cuadro de
muestreo, hoja de papel). Se marcan sus 4 esquinas en cada foto; con dos alturas medidas desde el mismo punto del
teléfono se cancela la distancia entre ese punto y el lente. Cálculo en tile_calibration.py.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os

import numpy as np

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QGroupBox,
    QFileDialog, QMessageBox, QTextEdit, QWidget, QSplitter, QCheckBox, QScrollArea, QRadioButton, QButtonGroup,
)

from .exif_gps import load_oriented_rgb_image, extract_exif
from .camera_check import camera_fingerprint
from .ground_cover_dialog import ImageCanvas, LEFT, RIGHT
from .ui_keys import disable_enter_buttons
from .lens_calibration import calibrate_regular_lens
from . import tile_calibration as tc

DISPLAY_MAX = 3000          # lado mayor de la foto mostrada (los clics se pasan a px nativos)

HELP = (
    "<b>Ayuda corta.</b> 1) Tome la foto hacia abajo, con el teléfono nivelado, sobre baldosas (o un cuadro o una "
    "hoja de tamaño conocido) que cubran el centro de la foto. 2) Mida la altura <b>H</b> hasta el suelo. "
    "3) Escriba los lados del rectángulo que va a marcar (con baldosas: paso entre juntas × número de baldosas, "
    "y «Aplicar»). 4) Marque sus 4 esquinas en el centro de las juntas (clic; clic derecho quita la última; rueda "
    "o +/− para acercar; arrastre para mover). 5) Recomendado: una segunda foto a otra altura (40–60 cm más) "
    "medida desde el <b>mismo punto</b> del teléfono: así no importa dónde está el lente. 6) «Calcular».")


class _Photo:
    def __init__(self):
        self.path = None
        self.rgb = None
        self.scale = 1.0           # px mostrados / px nativos
        self.native = None         # (ancho, alto) nativos
        self.corners = []          # en px mostrados


class TileCalibrationDialog(QDialog):
    def __init__(self, parent=None, start_path=None):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Calibrar con baldosas o un rectángulo conocido")
        self.resize(1250, 820)
        self.photos = [_Photo(), _Photo()]
        self.active = 0
        self.result = None
        self._build()
        disable_enter_buttons(self)
        if start_path:
            try:
                self.load_photo(0, start_path)
            except Exception:
                pass

    # ------------------------------------------------------------ interfaz
    def _build(self):
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)

        hl = QLabel(HELP); hl.setWordWrap(True)
        lv.addWidget(hl)

        g = QGroupBox("Rectángulo conocido en el suelo")
        f = QFormLayout(g)
        self.side1 = QDoubleSpinBox(); self.side1.setRange(1, 10000); self.side1.setDecimals(1)
        self.side1.setSuffix(" cm"); self.side1.setValue(2 * tc.TILE_PITCH_DEFAULT_CM)
        self.side2 = QDoubleSpinBox(); self.side2.setRange(1, 10000); self.side2.setDecimals(1)
        self.side2.setSuffix(" cm"); self.side2.setValue(2 * tc.TILE_PITCH_DEFAULT_CM)
        f.addRow("Lado a lo ancho de la foto (esquinas 1–2):", self.side1)
        f.addRow("Lado a lo alto de la foto (esquinas 2–3):", self.side2)
        self.pitch = QDoubleSpinBox(); self.pitch.setRange(1, 500); self.pitch.setDecimals(1)
        self.pitch.setSuffix(" cm"); self.pitch.setValue(tc.TILE_PITCH_DEFAULT_CM)
        self.pitch.setToolTip("Distancia del centro de una junta al centro de la siguiente (baldosa + junta).")
        self.n1 = QSpinBox(); self.n1.setRange(1, 50); self.n1.setValue(2)
        self.n2 = QSpinBox(); self.n2.setRange(1, 50); self.n2.setValue(2)
        row = QHBoxLayout()
        row.addWidget(self.pitch); row.addWidget(QLabel("×")); row.addWidget(self.n1)
        row.addWidget(QLabel("a lo ancho ×")); row.addWidget(self.n2); row.addWidget(QLabel("a lo alto"))
        ab = QPushButton("Aplicar"); ab.clicked.connect(self.apply_tiles); row.addWidget(ab)
        f.addRow("Baldosas (paso entre juntas):", row)
        lv.addWidget(g)

        self.view_group = QButtonGroup(self)
        self.h_spins, self.file_lbls, self.corner_lbls, self.view_radios = [], [], [], []
        self.two_check = QCheckBox("Usar una segunda foto a otra altura (recomendado)")
        self.two_check.setChecked(False)
        self.two_check.toggled.connect(self._update_enabled)
        self.photo_boxes = []
        for i in range(2):
            box = QGroupBox("Foto {}".format(i + 1))
            fl = QFormLayout(box)
            rb = QRadioButton("Ver y marcar esta foto"); self.view_group.addButton(rb, i)
            rb.toggled.connect(lambda on, k=i: on and self.show_photo(k))
            fl.addRow(rb)
            b = QPushButton("Cargar foto…"); b.clicked.connect(lambda _c=False, k=i: self._on_load(k))
            lbl = QLabel("sin foto"); lbl.setWordWrap(True)
            r = QHBoxLayout(); r.addWidget(b); r.addWidget(lbl, 1)
            fl.addRow(r)
            hs = QDoubleSpinBox(); hs.setRange(5, 1000); hs.setDecimals(1); hs.setSuffix(" cm")
            hs.setValue(100.0 if i == 0 else 150.0)
            hs.setToolTip("Altura hasta el suelo. Con dos fotos, mida ambas desde el mismo punto del teléfono.")
            fl.addRow("Altura medida H:", hs)
            cl = QLabel("Esquinas: 0 de 4")
            cb = QPushButton("Borrar esquinas"); cb.clicked.connect(lambda _c=False, k=i: self.clear_corners(k))
            r2 = QHBoxLayout(); r2.addWidget(cl, 1); r2.addWidget(cb)
            fl.addRow(r2)
            self.h_spins.append(hs); self.file_lbls.append(lbl); self.corner_lbls.append(cl)
            self.view_radios.append(rb); self.photo_boxes.append(box)
            lv.addWidget(box)
            if i == 0:
                lv.addWidget(self.two_check)
        self.view_radios[0].setChecked(True)

        zr = QHBoxLayout()
        for txt, fn in (("Acercar (+)", lambda: self.canvas.zoom_by(1.5)),
                        ("Alejar (−)", lambda: self.canvas.zoom_by(1 / 1.5)),
                        ("Ajustar vista (F)", lambda: self.canvas.fit())):
            zb = QPushButton(txt); zb.clicked.connect(fn); zr.addWidget(zb)
        lv.addLayout(zr)

        self.calc_btn = QPushButton("Calcular"); self.calc_btn.clicked.connect(self._on_calc)
        lv.addWidget(self.calc_btn)
        self.out = QTextEdit(); self.out.setReadOnly(True)
        lv.addWidget(self.out, 1)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(left)
        split.addWidget(scroll)
        self.canvas = ImageCanvas(self._on_canvas_click)
        split.addWidget(self.canvas)
        split.setSizes([430, 820])
        root.addWidget(split, 1)

        br = QHBoxLayout(); br.addStretch(1)
        self.ok_btn = QPushButton("Usar esta calibración"); self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.reject)
        br.addWidget(self.ok_btn); br.addWidget(cancel)
        root.addLayout(br)
        self._update_enabled()

    def _update_enabled(self, *_a):
        two = self.two_check.isChecked()
        self.photo_boxes[1].setEnabled(two)
        if not two and self.active == 1:
            self.view_radios[0].setChecked(True)
        self.result = None
        self.ok_btn.setEnabled(False)

    def apply_tiles(self):
        self.side1.setValue(self.pitch.value() * self.n1.value())
        self.side2.setValue(self.pitch.value() * self.n2.value())

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom_by(1.5); return
        if k == Qt.Key.Key_Minus:
            self.canvas.zoom_by(1 / 1.5); return
        if k == Qt.Key.Key_F:
            self.canvas.fit(); return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ fotos y esquinas
    def load_photo(self, i, path):
        img, scale, wh = load_oriented_rgb_image(path, max_dim=DISPLAY_MAX)
        p = self.photos[i]
        p.path, p.rgb, p.scale, p.native, p.corners = path, np.asarray(img), float(scale), tuple(wh), []
        self.file_lbls[i].setText("{} ({}×{} px)".format(os.path.basename(path), wh[0], wh[1]))
        self.result = None
        self.ok_btn.setEnabled(False)
        if i == 1 and not self.two_check.isChecked():
            self.two_check.setChecked(True)
        self.view_radios[i].setChecked(True)
        self.show_photo(i)
        self._update_corner_label(i)

    def _on_load(self, i):
        path, _ = QFileDialog.getOpenFileName(self, "Foto del rectángulo conocido", "",
                                              "Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.heic *.heif)")
        if path:
            try:
                self.load_photo(i, path)
            except Exception as e:
                QMessageBox.critical(self, "Calibrar con baldosas", "No se pudo abrir la foto: {}".format(e))

    def show_photo(self, i):
        self.active = i
        if not hasattr(self, "canvas"):
            return
        p = self.photos[i]
        self.canvas.marks = []
        self.canvas.current = None
        if p.rgb is None:
            self.canvas.pix = None
            self.canvas.polygon = []
            self.canvas.update()
            return
        self.canvas.set_image(p.rgb)
        self.canvas.polygon = list(p.corners)
        self.canvas.update()

    def set_corners(self, i, corners_display):
        self.photos[i].corners = [tuple(map(float, c)) for c in corners_display][:4]
        if i == self.active:
            self.canvas.polygon = list(self.photos[i].corners)
            self.canvas.update()
        self._update_corner_label(i)

    def clear_corners(self, i):
        self.set_corners(i, [])

    def _update_corner_label(self, i):
        self.corner_lbls[i].setText("Esquinas: {} de 4 (clic derecho quita la última)".format(
            len(self.photos[i].corners)))
        self.result = None
        self.ok_btn.setEnabled(False)

    def _on_canvas_click(self, x, y, button=LEFT):
        p = self.photos[self.active]
        if p.rgb is None:
            return
        pts = list(p.corners)
        if button == RIGHT:
            if pts:
                pts.pop()
        elif x is not None and len(pts) < 4:
            pts.append((x, y))
        self.set_corners(self.active, pts)

    # ------------------------------------------------------------ cálculo
    def _measurement(self, i):
        p = self.photos[i]
        if p.rgb is None:
            raise ValueError("Cargue la foto {}.".format(i + 1))
        if len(p.corners) != 4:
            raise ValueError("Marque las 4 esquinas en la foto {} ({} de 4).".format(i + 1, len(p.corners)))
        return {"corners_px": [(x / p.scale, y / p.scale) for x, y in p.corners],
                "side1_cm": self.side1.value(), "side2_cm": self.side2.value(),
                "height_cm": self.h_spins[i].value(), "width_px": p.native[0], "height_px": p.native[1]}

    def compute(self):
        m1 = self._measurement(0)
        m2 = self._measurement(1) if self.two_check.isChecked() else None
        res = tc.calibrate_tiles(m1, m2)
        res["side1_cm"], res["side2_cm"] = self.side1.value(), self.side2.value()
        res["files"] = [self.photos[k].path for k in range(res["n_photos"])]
        try:
            res["camera"] = camera_fingerprint(extract_exif(self.photos[0].path) or {}, *self.photos[0].native)
        except Exception:
            res["camera"] = None
        res["lines"] = tc.summary_lines(res)
        self.result = res
        return res

    def _on_calc(self):
        try:
            res = self.compute()
        except Exception as e:
            self.result = None
            self.ok_btn.setEnabled(False)
            QMessageBox.warning(self, "Calibrar con baldosas", str(e))
            return
        self.out.setPlainText("\n".join(res["lines"]))
        self.ok_btn.setEnabled(True)


def measurement_record(res):
    """Registro trazable que se guarda con la calibración (campo «measurement»)."""
    D, H, d = tc.equivalent_circle(res, res["side1_cm"])
    parts = ["rectángulo de {:g} × {:g} cm".format(res["side1_cm"], res["side2_cm"]),
             "{} foto(s)".format(res["n_photos"]),
             "f = {:.1f} px".format(res["focal_px"]),
             "inclinación " + ", ".join("{:.1f}°".format(p["tilt_deg"]) for p in res["photos"])]
    if res["offset_cm"] is not None:
        parts.append("lente a {:+.1f} cm del punto de medición".format(res["offset_cm"]))
    parts.append("foto {}×{} px".format(res["width_px"], res["height_px"]))
    return {"file": os.path.basename(res["files"][0]) if res.get("files") else None,
            "files": [os.path.basename(x) for x in res.get("files") or []],
            "image_size": [res["width_px"], res["height_px"]],
            "mode": "baldosas", "diameter_native_px": d, "diff_pct": None, "centre_offset_pct": None,
            "fit_rms_px": None, "arc_deg": None, "warnings": [l for l in res["lines"] if l.startswith("Aviso")],
            "notes": [], "verdict": None, "camera": res.get("camera"), "summary": "; ".join(parts),
            "tiles": {"side1_cm": res["side1_cm"], "side2_cm": res["side2_cm"], "focal_px": res["focal_px"],
                      "offset_cm": res["offset_cm"], "lens_height_cm": res["lens_height_cm"],
                      "photos": res["photos"]}}


def build_calibration(res):
    """Calibración «Rectilínea» de CobDosel (círculo equivalente) en el tamaño nativo de la foto."""
    D = round(float(res["side1_cm"]), 2)
    H = round(float(res["lens_height_cm"]), 2)
    cal = calibrate_regular_lens(circle_diameter_cm=D, camera_height_cm=H,
                                 pixel_diameter_px=res["focal_px"] * D / H,
                                 image_width_px=res["width_px"], image_height_px=res["height_px"],
                                 projection="rectilinear")
    cal["measurement"] = measurement_record(res)
    cal["camera"] = res.get("camera")
    cal["calibration_method"] = "baldosas"
    return cal
