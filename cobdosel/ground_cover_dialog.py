"""Diálogo «Cobertura del suelo» de CobDosel (v0.15.0): una foto vertical hacia abajo.

1. Cargar la foto. 2. Elegir el área: cuadro (marcar sus 4 esquinas en la foto) o área fija (altura de la cámara y
calibración del teléfono). 3. «Preparar área»: vegetación verde automática (Canopeo) y cuadrícula de puntos.
4. Clasificar los puntos que no son verdes (y corregir cualquiera). 5. Exportar CSV o informe HTML.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import webbrowser

import numpy as np

from qgis.PyQt.QtCore import Qt, QPointF, QUrl
from qgis.PyQt.QtGui import QImage, QPainter, QPen, QColor, QPixmap, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox, QRadioButton, QTextEdit, QWidget,
    QSplitter, QButtonGroup,
)

from ._version import VERSION
from .csv_format import csv_style
from .exif_gps import load_oriented_rgb_image, extract_exif
from .calibration_store import list_calibrations, load_calibration
from .lens_calibration import scale_calibration_to_image
from .ui_keys import disable_enter_buttons
from . import ground_cover as gc

HELP = (
    "<b>Cobertura del suelo</b> con una foto vertical hacia abajo (cámara nivelada, a 1–1,5 m).<br>"
    "1) Cargue la foto. 2) Elija el área: <b>cuadro</b> (haga clic en sus 4 esquinas, en cualquier orden) o "
    "<b>área fija</b> (altura de la cámara y calibración del teléfono). 3) «Preparar área». 4) Clasifique los "
    "puntos blancos: elija la clase (o pulse 1–5) y haga clic en el punto; también puede corregir los verdes. "
    "5) Exporte CSV o el informe.<br>La vegetación verde se calcula sola con la regla de Canopeo; si difiere más de "
    "{:.0f} puntos de ExG − ExR, la foto queda «a revisar».".format(gc.AGREEMENT_LIMIT))


def _qimage(rgb):
    a = np.ascontiguousarray(np.asarray(rgb, dtype=np.uint8))
    h, w = a.shape[:2]
    fmt = QImage.Format.Format_RGB888 if hasattr(QImage, "Format") else QImage.Format_RGB888
    return QImage(a.data, w, h, 3 * w, fmt).copy()


class ImageCanvas(QWidget):
    """Muestra una imagen escalada y devuelve los clics en px de la imagen."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self.on_click = on_click
        self.pix = None
        self.img_w = self.img_h = 1
        self.marks = []          # [(x, y, (r, g, b), radio)] en px de la imagen
        self.polygon = []        # [(x, y)] esquinas del cuadro
        self.setMinimumSize(420, 420)

    def set_image(self, rgb):
        self.img_h, self.img_w = rgb.shape[:2]
        self.pix = QPixmap.fromImage(_qimage(rgb))
        self.update()

    def _geom(self):
        s = min(self.width() / float(self.img_w), self.height() / float(self.img_h))
        ox = (self.width() - self.img_w * s) / 2.0
        oy = (self.height() - self.img_h * s) / 2.0
        return s, ox, oy

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(40, 40, 40))
        if self.pix is None:
            p.end()
            return
        s, ox, oy = self._geom()
        p.drawPixmap(int(ox), int(oy), int(self.img_w * s), int(self.img_h * s), self.pix)
        if self.polygon:
            p.setPen(QPen(QColor(255, 0, 255), 2))
            pts = [QPointF(ox + x * s, oy + y * s) for x, y in self.polygon]
            for i, q in enumerate(pts):
                p.drawEllipse(q, 6, 6)
                if i:
                    p.drawLine(pts[i - 1], q)
            if len(pts) == 4:
                p.drawLine(pts[3], pts[0])
        for x, y, col, rad in self.marks:
            p.setPen(QPen(QColor(0, 0, 0), 2))
            p.setBrush(QColor(*col))
            p.drawEllipse(QPointF(ox + x * s, oy + y * s), rad, rad)
        p.end()

    def mousePressEvent(self, e):
        if self.pix is None:
            return
        s, ox, oy = self._geom()
        pos = e.position() if hasattr(e, "position") else e.pos()
        x, y = (pos.x() - ox) / s, (pos.y() - oy) / s
        if 0 <= x < self.img_w and 0 <= y < self.img_h:
            self.on_click(x, y)


class GroundCoverDialog(QDialog):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("CobDosel v{} — Cobertura del suelo".format(VERSION))
        self.resize(1150, 780)
        self.photo_path = None
        self.rgb = None
        self.exif = {}
        self.corners = []
        self.area = None
        self.green = None
        self.points = []
        self.labels = []
        self.auto = []
        self.seed = None
        self.meta = {}
        self.res = None
        self.current_class = "seca"
        self._build()
        disable_enter_buttons(self)

    # ------------------------------------------------------------ interfaz
    def _build(self):
        root = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)
        left = QWidget(); lv = QVBoxLayout(left)
        g1 = QGroupBox("1. Foto"); f1 = QFormLayout(g1)
        self.photo_edit = QLineEdit(); self.photo_edit.setReadOnly(True)
        b = QPushButton("Cargar foto…"); b.clicked.connect(self._on_load)
        row = QHBoxLayout(); row.addWidget(self.photo_edit); row.addWidget(b)
        f1.addRow("Foto:", row)
        self.site_edit = QLineEdit(); f1.addRow("Sitio:", self.site_edit)
        self.analyst_edit = QLineEdit(); f1.addRow("Analista:", self.analyst_edit)
        lv.addWidget(g1)
        g2 = QGroupBox("2. Área de muestreo"); f2 = QFormLayout(g2)
        self.mode_quad = QRadioButton("Cuadro: clic en sus 4 esquinas"); self.mode_quad.setChecked(True)
        self.mode_fixed = QRadioButton("Área fija desde la altura de la cámara")
        f2.addRow(self.mode_quad); f2.addRow(self.mode_fixed)
        self.side_spin = QDoubleSpinBox(); self.side_spin.setRange(0.05, 10.0); self.side_spin.setDecimals(2)
        self.side_spin.setValue(1.0); self.side_spin.setSuffix(" m")
        f2.addRow("Lado del cuadrado:", self.side_spin)
        self.height_spin = QDoubleSpinBox(); self.height_spin.setRange(0.2, 10.0); self.height_spin.setDecimals(2)
        self.height_spin.setValue(1.3); self.height_spin.setSuffix(" m")
        f2.addRow("Altura de la cámara (área fija):", self.height_spin)
        self.cal_combo = QComboBox()
        for name, _p in list_calibrations():
            self.cal_combo.addItem(name, name)
        f2.addRow("Calibración (área fija):", self.cal_combo)
        self.points_spin = QSpinBox(); self.points_spin.setRange(9, 400); self.points_spin.setValue(gc.DEFAULT_POINTS)
        f2.addRow("Puntos de la cuadrícula:", self.points_spin)
        row2 = QHBoxLayout()
        b = QPushButton("Borrar esquinas"); b.clicked.connect(self._on_clear_corners); row2.addWidget(b)
        self.prepare_btn = QPushButton("Preparar área"); self.prepare_btn.clicked.connect(self._on_prepare)
        row2.addWidget(self.prepare_btn)
        f2.addRow(row2)
        lv.addWidget(g2)
        g3 = QGroupBox("3. Clase para los clics en los puntos (teclas 1–5)"); v3 = QVBoxLayout(g3)
        self.class_group = QButtonGroup(self)
        for i, (key, lbl) in enumerate(gc.CLASSES, 1):
            rb = QRadioButton("{} — {}".format(i, lbl)); rb.setProperty("clase", key)
            if key == self.current_class:
                rb.setChecked(True)
            rb.toggled.connect(lambda on, k=key: on and self._set_class(k))
            self.class_group.addButton(rb, i); v3.addWidget(rb)
        lv.addWidget(g3)
        row3 = QHBoxLayout()
        self.csv_btn = QPushButton("Exportar CSV…"); self.csv_btn.clicked.connect(self._on_csv)
        self.html_btn = QPushButton("Exportar informe HTML…"); self.html_btn.clicked.connect(self._on_html)
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(False); row3.addWidget(bb)
        lv.addLayout(row3)
        self.out = QTextEdit(); self.out.setReadOnly(True); lv.addWidget(self.out, 1)
        help_lbl = QLabel(HELP); help_lbl.setWordWrap(True); lv.addWidget(help_lbl)
        split.addWidget(left)
        self.canvas = ImageCanvas(self._on_canvas_click)
        split.addWidget(self.canvas)
        split.setStretchFactor(1, 2)

    def _set_class(self, key):
        self.current_class = key

    def keyPressEvent(self, e):
        k = e.key()
        keys = [getattr(Qt.Key, "Key_{}".format(i)) for i in range(1, 6)]
        if k in keys:
            self.class_group.button(keys.index(k) + 1).setChecked(True)
            return
        super().keyPressEvent(e)

    def _log(self, msg):
        self.out.append(msg)

    # ------------------------------------------------------------ flujo
    def load_photo(self, path):
        img, _s, _wh = load_oriented_rgb_image(path)
        self.rgb = np.asarray(img)
        self.photo_path = path
        self.exif = extract_exif(path) or {}
        self.corners = []
        self.area = None
        self.points, self.labels, self.auto, self.res = [], [], [], None
        self.photo_edit.setText(path)
        self.canvas.polygon = []
        self.canvas.marks = []
        self.canvas.set_image(self.rgb)
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(False)
        self._log("Foto cargada: {} ({} × {} px).".format(os.path.basename(path), self.rgb.shape[1], self.rgb.shape[0]))

    def _on_load(self):
        p, _ = QFileDialog.getOpenFileName(self, "Foto vertical hacia abajo", "",
                                           "Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.heic *.heif)")
        if p:
            try:
                self.load_photo(p)
            except Exception as e:
                QMessageBox.critical(self, "Cobertura del suelo", "No se pudo abrir la foto: {}".format(e))

    def _on_clear_corners(self):
        self.corners = []
        if self.area is None and self.rgb is not None:
            self.canvas.polygon = []
            self.canvas.update()

    def _on_canvas_click(self, x, y):
        if self.area is None:                      # marcando el cuadro sobre la foto
            if not self.mode_quad.isChecked() or len(self.corners) >= 4:
                return
            self.corners.append((x, y))
            self.canvas.polygon = list(self.corners)
            self.canvas.update()
            if len(self.corners) == 4:
                self._log("Cuadro marcado: pulse «Preparar área».")
            return
        if not self.points:
            return
        d = [(px - x) ** 2 + (py - y) ** 2 for px, py in self.points]
        i = int(np.argmin(d))
        tol = max(self.area.shape[:2]) / 40.0
        if d[i] <= tol * tol:
            self.label_point(i, self.current_class)

    def prepare_area(self):
        """Prepara el área (cuadro enderezado o área fija), la vegetación verde y la cuadrícula de puntos."""
        if self.rgb is None:
            raise ValueError("Cargue una foto primero.")
        side = float(self.side_spin.value())
        meta = {"archivo": os.path.basename(self.photo_path), "fecha_exif": self.exif.get("capture_datetime"),
                "latitud": self.exif.get("latitude"), "longitud": self.exif.get("longitude"),
                "sitio": self.site_edit.text().strip(), "analista": self.analyst_edit.text().strip(),
                "lado_m": side, "area_m2": side * side}
        if self.mode_quad.isChecked():
            if len(self.corners) != 4:
                raise ValueError("Marque las 4 esquinas del cuadro en la foto.")
            self.area = gc.rectify_quadrat(self.rgb, self.corners)
            meta.update(modo_area="Cuadro", altura_camara_m=None, calibracion=None)
        else:
            name = self.cal_combo.currentData()
            if not name:
                raise ValueError("El área fija necesita una calibración guardada del teléfono.")
            h, w = self.rgb.shape[:2]
            cal = scale_calibration_to_image(load_calibration(name), w, h)
            f = cal.get("focal_length_px")
            if cal.get("lens_type") != "regular" or cal.get("projection") != "rectilinear":
                raise ValueError("El área fija necesita una calibración «Rectilínea» de lente regular.")
            self.area, _side_px = gc.crop_fixed_area(self.rgb, f, float(self.height_spin.value()), side)
            meta.update(modo_area="Área fija", altura_camara_m=float(self.height_spin.value()), calibracion=name)
        self.green = gc.canopeo_mask(self.area)
        self.points, self.seed = gc.point_grid(self.area.shape, int(self.points_spin.value()))
        self.auto = gc.auto_labels(self.points, self.green)
        self.labels = list(self.auto)
        meta["semilla"] = self.seed
        self.meta = meta
        shown = self.area.copy()
        shown[self.green] = (0.55 * shown[self.green] + 0.45 * np.array([255, 0, 255])).astype(np.uint8)
        self.canvas.polygon = []
        self.canvas.set_image(shown)
        self._refresh()

    def _on_prepare(self):
        try:
            self.prepare_area()
        except Exception as e:
            QMessageBox.warning(self, "Cobertura del suelo", str(e))

    def label_point(self, i, key):
        self.labels[i] = key
        self._refresh()

    def _refresh(self):
        rad = max(5.0, min(self.canvas.width(), self.canvas.height()) / 90.0)
        self.canvas.marks = [(x, y, gc.CLASS_COLORS.get(lab, (255, 255, 255)), rad)
                             for (x, y), lab in zip(self.points, self.labels)]
        self.canvas.update()
        self.res = gc.summarize(self.area, self.labels)
        r = self.res
        lines = ["Vegetación verde (Canopeo): {:.2f} %   ExG − ExR: {:.2f} %   diferencia {:+.2f}".format(
            r["verde_canopeo_pct"], r["verde_exgexr_pct"], r["diferencia_pct"])]
        if r["revisar"]:
            lines.append("A REVISAR: Canopeo y ExG − ExR difieren más de {:.0f} puntos.".format(gc.AGREEMENT_LIMIT))
        lines.append("Puntos ({}; sin clasificar: {}):".format(r["n_puntos"], r["sin_clasificar"]))
        for key, lbl in gc.CLASSES:
            d = r["clases"][key]
            lines.append("  {:<18} {:>4}  {:6.1f} %  (IC 95 %: {:.1f}–{:.1f} %)".format(
                lbl, d["puntos"], d["pct"], d["ic_inf"], d["ic_sup"]))
        self.out.setPlainText("\n".join(lines))
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(True)

    def _default_prefix(self):
        base = os.path.splitext(os.path.basename(self.photo_path or "foto"))[0]
        return os.path.join(os.path.dirname(self.photo_path or ""), "CobDosel_suelo_{}".format(base))

    def _on_csv(self):
        p, _ = QFileDialog.getSaveFileName(self, "Prefijo de los CSV", self._default_prefix() + ".csv", "CSV (*.csv)")
        if not p:
            return
        p = p[:-4] if p.lower().endswith(".csv") else p
        sep, dec = csv_style()
        paths = gc.write_csvs(self.res, self.meta, self.points, self.labels, self.auto, p, VERSION, sep, dec)
        self._log("CSV guardados: " + "; ".join(paths))
        QMessageBox.information(self, "CSV guardados", "\n".join(paths))

    def _on_html(self):
        p, _ = QFileDialog.getSaveFileName(self, "Informe HTML", self._default_prefix() + "_informe.html",
                                           "HTML (*.html)")
        if not p:
            return
        if not p.lower().endswith((".html", ".htm")):
            p += ".html"
        gc.write_html(self.res, self.meta, self.area, self.points, self.labels, p, VERSION)
        self._log("Informe guardado: " + p)
        ans = QMessageBox.question(self, "Informe guardado", "{}\n\n¿Abrir el informe ahora?".format(p),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(p)):
                webbrowser.open("file://" + os.path.abspath(p))
