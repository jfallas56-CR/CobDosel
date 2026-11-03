"""Diálogo «Cobertura del suelo» de CobDosel: una foto vertical hacia abajo.

1. Cargar la foto. 2. Elegir el área: cuadro (marcar sus 4 esquinas en la foto) o área fija (altura de la cámara y
calibración del teléfono). 3. «Preparar área»: vegetación verde automática (Canopeo) y cuadrícula de puntos.
4. Clasificar los puntos que no son verdes (y corregir cualquiera). 5. Exportar CSV o informe HTML.

v0.15.1: la vegetación verde sombreada se muestra solo si se pide («Mostrar vegetación verde», tecla V), para ver
los colores reales al clasificar; los puntos son anillos con cruz (se ve lo que hay debajo); zoom con la rueda del
ratón y «Ajustar vista» (tecla F); «Siguiente sin clasificar» (tecla N); semilla visible que se conserva, aviso antes
de descartar puntos ya clasificados y «Nueva cuadrícula»; campos del modo que no se usa desactivados; contador de
esquinas; clic derecho quita la última esquina.

v0.15.2: «Siguiente sin clasificar» avanza por la cuadrícula (no vuelve siempre al primero) y marca el punto actual;
las teclas 1–5 clasifican el punto actual y pasan al siguiente; zoom con botones (+/−) y teclas, y arrastre para
mover la vista; pestaña «Ayuda» con la ayuda completa; «Sombrear vegetación verde (magenta)».

v0.15.6: «Siguiente» (N) asigna la clase marcada al punto actual y pasa al siguiente (la primera vez solo muestra el
primer punto); «Saltar sin clasificar» (S); contador «Sin clasificar: k de n puntos» y número del punto actual.

v0.15.7: «Nueva clase…» y «Quitar clase nueva…» (clases del usuario, guardadas en ~/.cobdosel/clases_suelo.json;
teclas 1–9); «Diferencias entre las reglas» (C): cian donde solo ExG − ExR ve verde, naranja donde solo Canopeo.

v0.15.8: cursor en cruz y líneas guía por el cursor mientras se marcan las esquinas (también en «Calibrar con
baldosas»); ayuda corta y completa con buenas prácticas y fotos que conviene evitar.

v0.15.9: área fija: la ventana indica qué cuadrado cabe a la altura escrita y la altura mínima para el lado elegido,
con la calibración elegida y el tamaño de la foto (ground_cover.fixed_area_fit); tablas en la ayuda y el manual.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import webbrowser

import numpy as np

from qgis.PyQt.QtCore import Qt, QPointF, QUrl
from qgis.PyQt.QtGui import QImage, QPainter, QPen, QColor, QPixmap, QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox, QRadioButton, QTextEdit, QWidget,
    QSplitter, QButtonGroup, QCheckBox, QTabWidget, QTextBrowser, QScrollArea, QInputDialog,
)

from ._version import VERSION
from .csv_format import csv_style
from .exif_gps import load_oriented_rgb_image, extract_exif
from .calibration_store import list_calibrations, load_calibration, save_calibration
from .lens_calibration import scale_calibration_to_image
from .ui_keys import disable_enter_buttons
from . import ground_cover as gc
from .help_texts import GROUND_HELP_HTML

HELP = (
    "<b>Foto:</b> hacia abajo, nivelada, 1x, a altura fija, con luz difusa (nublado o sombra pareja), suelo plano y "
    "vegetación baja. <b>Evite:</b> sol directo con sombras duras, cámara inclinada, plantas a distintas alturas, "
    "follaje morado o plateado (no cuenta como verde), fotos movidas, zoom o copias de chat. Detalles: pestaña "
    "«Ayuda».<br>"
    "<b>Ayuda corta.</b> 1) Cargue la foto. 2) Área: <b>cuadro</b> (clic en sus 4 esquinas con la cruz y las líneas guía; clic derecho "
    "quita la última) o <b>área fija</b>. 3) «Preparar área». 4) Marque la clase y pulse «Siguiente» (<b>N</b>): "
    "asigna esa clase al punto actual (anillo amarillo) y pasa al siguiente; la primera vez solo muestra el punto 1. "
    "<b>1–9</b> (número de la clase) cambia la clase y la asigna; <b>S</b> salta el punto. «Nueva clase…» agrega una "
    "clase. <b>C</b> muestra dónde difieren las reglas del verde (cian y naranja). También puede hacer clic en cualquier punto. Zoom: rueda, <b>+</b>/<b>−</b>; arrastre o <b>flechas</b> para mover (Mayús: paso mayor); <b>F</b> ajusta la vista; "
    "<b>V</b> sombrea la vegetación verde en magenta. 5) Exporte. Ayuda completa: pestaña «Ayuda».")

RIGHT = "right"
LEFT = "left"


def _qimage(rgb):
    a = np.ascontiguousarray(np.asarray(rgb, dtype=np.uint8))
    h, w = a.shape[:2]
    fmt = QImage.Format.Format_RGB888 if hasattr(QImage, "Format") else QImage.Format_RGB888
    return QImage(a.data, w, h, 3 * w, fmt).copy()


class ImageCanvas(QWidget):
    """Muestra una imagen con zoom (rueda del ratón) y devuelve los clics en px de la imagen."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self.on_click = on_click
        self.pix = None
        self.img_w = self.img_h = 1
        self.zoom = 1.0
        self.center = (0.5, 0.5)       # centro de la vista, en px de la imagen
        self.marks = []                # [(x, y, (r, g, b))] en px de la imagen
        self.polygon = []              # [(x, y)] esquinas del cuadro
        self.current = None            # (x, y) del punto actual (anillo amarillo)
        self.guides_fn = None          # v0.15.8: función → True si se dibujan las líneas guía (marcando esquinas)
        self.hover = None              # posición del cursor en pantalla (para las líneas guía)
        self.setCursor(Qt.CursorShape.CrossCursor)     # v0.15.8: cruz, con el punto de clic en su centro
        self._press = None             # posición de pantalla del clic izquierdo (para distinguir clic y arrastre)
        self._dragged = False
        self.setMinimumSize(420, 420)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)      # recibe los movimientos del arrastre en todas las plataformas

    def set_image(self, rgb, keep_view=False):
        h, w = rgb.shape[:2]
        same = keep_view and (w, h) == (self.img_w, self.img_h)
        self.img_h, self.img_w = h, w
        self.pix = QPixmap.fromImage(_qimage(rgb))
        if not same:
            self.fit()
        self.update()

    def fit(self):
        self.zoom = 1.0
        self.center = (self.img_w / 2.0, self.img_h / 2.0)
        self.update()

    def center_on(self, x, y, zoom=None):
        if zoom is not None:
            self.zoom = max(1.0, float(zoom))
        self.center = (float(x), float(y))
        self.update()

    def zoom_by(self, factor):
        """Acerca o aleja la vista manteniendo el centro."""
        self.zoom = min(40.0, max(1.0, self.zoom * float(factor)))
        self.update()

    def pan_by(self, fx, fy):
        """Mueve la vista una fracción del área visible (v0.15.4: flechas del teclado). El centro queda dentro de la
        imagen para no perderla de vista."""
        if self.pix is None:
            return
        s, _ox, _oy = self._geom()
        cx = self.center[0] + fx * self.width() / s
        cy = self.center[1] + fy * self.height() / s
        self.center = (min(max(cx, 0.0), float(self.img_w)), min(max(cy, 0.0), float(self.img_h)))
        self.update()

    def pan_key(self, e):
        """Flechas: mueven la vista 10 % del área visible (Mayús: 50 %), como en la ventana de medición del círculo.
        Devuelve True si la tecla era una flecha."""
        K = Qt.Key
        dirs = {K.Key_Left: (-1, 0), K.Key_Right: (1, 0), K.Key_Up: (0, -1), K.Key_Down: (0, 1)}
        d = dirs.get(e.key())
        if d is None:
            return False
        step = 0.5 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.1
        self.pan_by(d[0] * step, d[1] * step)
        return True

    def keyPressEvent(self, e):
        if self.pan_key(e):
            e.accept()
            return
        super().keyPressEvent(e)      # las demás teclas (1–9, N, S, C, F, V, +/−) siguen a la ventana

    def _geom(self):
        base = min(self.width() / float(self.img_w), self.height() / float(self.img_h))
        s = base * self.zoom
        ox = self.width() / 2.0 - self.center[0] * s
        oy = self.height() / 2.0 - self.center[1] * s
        return s, ox, oy

    def to_image(self, px, py):
        s, ox, oy = self._geom()
        return (px - ox) / s, (py - oy) / s

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(40, 40, 40))
        if self.pix is None:
            p.end()
            return
        s, ox, oy = self._geom()
        p.drawPixmap(int(round(ox)), int(round(oy)), int(round(self.img_w * s)), int(round(self.img_h * s)), self.pix)
        if self.polygon:
            p.setPen(QPen(QColor(255, 0, 255), 3))
            pts = [QPointF(ox + x * s, oy + y * s) for x, y in self.polygon]
            for i, q in enumerate(pts):
                p.drawEllipse(q, 10, 10)
                p.drawLine(QPointF(q.x() - 14, q.y()), QPointF(q.x() + 14, q.y()))
                p.drawLine(QPointF(q.x(), q.y() - 14), QPointF(q.x(), q.y() + 14))
                if i:
                    p.drawLine(pts[i - 1], q)
            if len(pts) == 4:
                p.drawLine(pts[3], pts[0])
        rad = max(6.0, min(14.0, 6.0 * self.zoom))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for x, y, col in self.marks:
            c = QPointF(ox + x * s, oy + y * s)
            p.setPen(QPen(QColor(0, 0, 0), 4))           # contorno negro para que se vea sobre cualquier fondo
            p.drawEllipse(c, rad, rad)
            p.setPen(QPen(QColor(*col), 2))
            p.drawEllipse(c, rad, rad)
            p.drawLine(QPointF(c.x() - rad * 0.5, c.y()), QPointF(c.x() + rad * 0.5, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - rad * 0.5), QPointF(c.x(), c.y() + rad * 0.5))
        if self.current is not None:
            c = QPointF(ox + self.current[0] * s, oy + self.current[1] * s)
            p.setPen(QPen(QColor(0, 0, 0), 5))
            p.drawEllipse(c, rad * 1.9, rad * 1.9)
            p.setPen(QPen(QColor(255, 230, 0), 3))
            p.drawEllipse(c, rad * 1.9, rad * 1.9)
        if self.guides_on() and self.hover is not None:
            # v0.15.8: líneas guía de lado a lado por el cursor (negro debajo y blanco encima: se ven sobre cualquier fondo)
            hx, hy = self.hover
            x0, x1 = max(0.0, ox), min(float(self.width()), ox + self.img_w * s)
            y0, y1 = max(0.0, oy), min(float(self.height()), oy + self.img_h * s)
            if x0 <= hx <= x1 and y0 <= hy <= y1:
                for pen in (QPen(QColor(0, 0, 0), 3), QPen(QColor(255, 255, 255), 1)):
                    p.setPen(pen)
                    p.drawLine(QPointF(hx, y0), QPointF(hx, y1))
                    p.drawLine(QPointF(x0, hy), QPointF(x1, hy))
        p.end()

    def guides_on(self):
        try:
            return bool(self.guides_fn and self.guides_fn())
        except Exception:
            return False

    def leaveEvent(self, _e):
        self.hover = None
        self.update()

    def wheelEvent(self, e):
        if self.pix is None:
            return
        pos = e.position() if hasattr(e, "position") else e.posF()
        x, y = self.to_image(pos.x(), pos.y())
        step = 1.25 if e.angleDelta().y() > 0 else 0.8
        new_zoom = min(40.0, max(1.0, self.zoom * step))
        # mantener bajo el cursor el mismo punto de la imagen
        base = min(self.width() / float(self.img_w), self.height() / float(self.img_h))
        s2 = base * new_zoom
        self.zoom = new_zoom
        self.center = (x - (pos.x() - self.width() / 2.0) / s2, y - (pos.y() - self.height() / 2.0) / s2)
        self.update()

    @staticmethod
    def _pos(e):
        return e.position() if hasattr(e, "position") else e.pos()

    def mousePressEvent(self, e):
        if self.pix is None:
            return
        self.setFocus()
        pos = self._pos(e)
        if e.button() == Qt.MouseButton.RightButton:
            x, y = self.to_image(pos.x(), pos.y())
            inside = 0 <= x < self.img_w and 0 <= y < self.img_h
            self.on_click(x if inside else None, y if inside else None, RIGHT)
            return
        self._press = (pos.x(), pos.y(), self.center)
        self._dragged = False

    def mouseMoveEvent(self, e):
        pos = self._pos(e)
        if self._press is None:
            if self.guides_on():
                self.hover = (pos.x(), pos.y())
                self.update()
            return
        dx, dy = pos.x() - self._press[0], pos.y() - self._press[1]
        if not self._dragged and dx * dx + dy * dy < 36:      # menos de 6 px: todavía es un clic
            return
        self._dragged = True
        s, _ox, _oy = self._geom()
        cx, cy = self._press[2]
        self.center = (cx - dx / s, cy - dy / s)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        pos = self._pos(e)
        dragged, self._press = self._dragged, None
        self.setCursor(Qt.CursorShape.CrossCursor)
        if dragged:
            return
        x, y = self.to_image(pos.x(), pos.y())
        if 0 <= x < self.img_w and 0 <= y < self.img_h:
            self.on_click(x, y, LEFT)


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
        self.current_idx = None         # punto actual (anillo amarillo)
        self.only_x = self.only_c = None    # v0.15.7: verde solo para ExG − ExR / solo para Canopeo
        self.zones = []                     # v0.15.16: zona de cada punto («cian», «naranja» o None)
        self.custom_classes = gc.load_custom_classes()
        self.classes = gc.class_list(self.custom_classes)
        self.groups = gc.groups_for(gc.load_groups(), self.classes)     # v0.15.13
        self._build()
        self._on_mode()
        disable_enter_buttons(self)

    # ------------------------------------------------------------ interfaz
    def _build(self):
        root = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)
        tabs = QTabWidget()
        left = QWidget(); lv = QVBoxLayout(left)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(left)
        tabs.addTab(scroll, "Parámetros")
        self.help_browser = QTextBrowser(); self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setHtml(GROUND_HELP_HTML)
        tabs.addTab(self.help_browser, "Ayuda")
        self.tabs = tabs
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
        self.mode_quad.toggled.connect(self._on_mode)
        f2.addRow(self.mode_quad)
        self.corner_lbl = QLabel("Esquinas: 0 de 4 (clic derecho quita la última)")
        f2.addRow("", self.corner_lbl)
        f2.addRow(self.mode_fixed)
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
        # v0.15.9: qué cuadrado cabe con esta altura y esta calibración (se actualiza al escribir)
        self.fit_lbl = QLabel("")
        self.fit_lbl.setWordWrap(True)
        f2.addRow("", self.fit_lbl)
        for w in (self.side_spin, self.height_spin):
            w.valueChanged.connect(self._update_fit)
        self.cal_combo.currentIndexChanged.connect(self._update_fit)
        self.tiles_btn = QPushButton("Calibrar con baldosas o un rectángulo conocido…")
        self.tiles_btn.setToolTip("Crea y guarda una calibración «Rectilínea» con una o dos fotos de baldosas, un "
                                  "cuadro o una hoja de tamaño conocido.")
        self.tiles_btn.clicked.connect(self._on_tiles)
        f2.addRow("", self.tiles_btn)
        self.points_spin = QSpinBox(); self.points_spin.setRange(9, 400); self.points_spin.setValue(gc.DEFAULT_POINTS)
        f2.addRow("Puntos de la cuadrícula:", self.points_spin)
        self.seed_spin = QSpinBox(); self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(int(np.random.default_rng().integers(0, 1000000)))
        self.seed_spin.setToolTip("La misma semilla da la misma cuadrícula; queda registrada en el CSV y el informe.")
        f2.addRow("Semilla de la cuadrícula:", self.seed_spin)
        row2 = QHBoxLayout()
        self.clear_btn = QPushButton("Borrar esquinas"); self.clear_btn.clicked.connect(self._on_clear_corners)
        row2.addWidget(self.clear_btn)
        self.prepare_btn = QPushButton("Preparar área"); self.prepare_btn.clicked.connect(self._on_prepare)
        row2.addWidget(self.prepare_btn)
        self.new_grid_btn = QPushButton("Nueva cuadrícula"); self.new_grid_btn.clicked.connect(self._on_new_grid)
        self.new_grid_btn.setToolTip("Otra semilla: otra cuadrícula (descarta las clases asignadas).")
        row2.addWidget(self.new_grid_btn)
        f2.addRow(row2)
        # v0.15.12: doble clasificación: el segundo analista usa la misma área y la misma cuadrícula que el primero
        self.load_area_btn = QPushButton("Cargar área y cuadrícula de un CSV…")
        self.load_area_btn.setToolTip("Lee el CSV de foto (CobDosel_suelo_<foto>.csv) de otro analista y repite su área "
                                      "(esquinas o área fija), su semilla y su número de puntos, para la doble "
                                      "clasificación del protocolo.")
        self.load_area_btn.clicked.connect(self._on_load_area)
        f2.addRow(self.load_area_btn)
        lv.addWidget(g2)
        self.g3 = g3 = QGroupBox("3. Clasificar los puntos (teclas 1–{})".format(len(self.classes)))
        v3 = QVBoxLayout(g3)
        self.progress_lbl = QLabel("Prepare el área para ver los puntos.")
        self.progress_lbl.setWordWrap(True)
        v3.addWidget(self.progress_lbl)
        # v0.15.12: modo reglamentario (protocolo): el verde lo decide la regla de Canopeo, no el analista
        self.reg_check = QCheckBox("Modo reglamentario: el verde lo decide la regla de Canopeo")
        self.reg_check.setToolTip("Los puntos verdes automáticos no se cambian (salvo a «No identificable», si caen "
                                  "sobre algo que no es vegetación) y ningún punto pasa a verde a mano. Así dos "
                                  "analistas obtienen los mismos puntos verdes con la misma semilla.")
        self.reg_check.toggled.connect(self._on_reg_toggled)
        v3.addWidget(self.reg_check)
        self.class_group = QButtonGroup(self)
        self.class_box = QVBoxLayout()
        v3.addLayout(self.class_box)
        self._build_class_radios()
        rowc = QHBoxLayout()
        self.new_class_btn = QPushButton("Nueva clase…")
        self.new_class_btn.setToolTip("Agrega una clase (por ejemplo, «Vegetación amarillenta»); queda guardada para "
                                      "las próximas fotos. Hasta 9 clases (teclas 1–9).")
        self.new_class_btn.clicked.connect(self._on_new_class)
        self.del_class_btn = QPushButton("Quitar clase nueva…")
        self.del_class_btn.setToolTip("Quita una clase agregada por el usuario (las 5 fijas no se quitan). No se puede "
                                      "quitar si algún punto de esta foto la tiene.")
        self.del_class_btn.clicked.connect(self._on_del_class)
        rowc.addWidget(self.new_class_btn); rowc.addWidget(self.del_class_btn)
        self.groups_btn = QPushButton("Grupos de clases…")
        self.groups_btn.setToolTip("Suma de varias clases, por ejemplo «Vegetación total» = verde + no verde + seca, con "
                                   "su intervalo de Wilson; se guardan para las próximas fotos.")
        self.groups_btn.clicked.connect(self._on_groups)
        rowc.addWidget(self.groups_btn)
        v3.addLayout(rowc)
        row4 = QHBoxLayout()
        self.show_green = QCheckBox("Sombrear vegetación verde en magenta (V)")
        self.show_green.setChecked(False)
        self.show_green.setToolTip("Sombrea en magenta lo que Canopeo clasifica como verde. Desactívelo para ver los "
                                   "colores reales al clasificar.")
        self.show_green.toggled.connect(self._redraw_area)
        row4.addWidget(self.show_green)
        v3.addLayout(row4)
        self.show_diff = QCheckBox("Diferencias entre las reglas: cian = verde solo para ExG − ExR, naranja = solo "
                                   "para Canopeo (C)")
        self.show_diff.setChecked(False)
        self.show_diff.setToolTip("Muestra dónde difieren Canopeo y ExG − ExR (suele ser vegetación amarillenta u hojas "
                                  "en sombra). Una diferencia no es un error de la foto ni de la clasificación.")
        self.show_diff.toggled.connect(self._redraw_area)
        v3.addWidget(self.show_diff)
        # v0.15.6: «Siguiente» asigna la clase marcada al punto actual y pasa al siguiente; «Saltar» no clasifica
        row6 = QHBoxLayout()
        self.next_btn = QPushButton("Siguiente (N): asigna la clase marcada")
        self.next_btn.setToolTip("Asigna la clase marcada arriba al punto actual (anillo amarillo) y pasa al siguiente "
                                 "sin clasificar. La primera vez solo muestra el primer punto. Si el punto siguiente "
                                 "es de otra clase, márquela (o pulse su número) antes de «Siguiente».")
        self.next_btn.clicked.connect(self.advance)
        self.skip_btn = QPushButton("Saltar sin clasificar (S)")
        self.skip_btn.setToolTip("Pasa al siguiente punto sin clasificar el actual; se vuelve a él al final de la vuelta.")
        self.skip_btn.clicked.connect(self.next_unclassified)
        row6.addWidget(self.next_btn); row6.addWidget(self.skip_btn)
        v3.addLayout(row6)
        # v0.15.16: puntos que caen donde las dos reglas del verde difieren
        self.doubt_btn = QPushButton("Siguiente punto dudoso (D)")
        self.doubt_btn.setToolTip("Lleva la vista al siguiente punto que cae donde Canopeo y ExG − ExR difieren (cian: "
                                  "tejido amarillento u hoja en sombra; naranja: compruebe que sea vegetación). Son los "
                                  "puntos que conviene revisar con más cuidado.")
        self.doubt_btn.clicked.connect(self.next_doubtful)
        v3.addWidget(self.doubt_btn)
        row5 = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Acercar (+)"); self.zoom_in_btn.clicked.connect(lambda: self.canvas.zoom_by(1.5))
        self.zoom_out_btn = QPushButton("Alejar (−)"); self.zoom_out_btn.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.5))
        self.fit_btn = QPushButton("Ajustar vista (F)"); self.fit_btn.clicked.connect(lambda: self.canvas.fit())
        for w in (self.zoom_in_btn, self.zoom_out_btn, self.fit_btn):
            row5.addWidget(w)
        v3.addLayout(row5)
        self.auto_next = QCheckBox("Al clasificar con las teclas de número, pasar al siguiente sin clasificar")
        self.auto_next.setChecked(True)
        v3.addWidget(self.auto_next)
        lv.addWidget(g3)
        row3 = QHBoxLayout()
        self.csv_btn = QPushButton("Exportar CSV…"); self.csv_btn.clicked.connect(self._on_csv)
        self.html_btn = QPushButton("Exportar informe HTML…"); self.html_btn.clicked.connect(self._on_html)
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(False); row3.addWidget(bb)
        self.compare_btn = QPushButton("Comparar clasificaciones…")
        self.compare_btn.setToolTip("Compara dos CSV de puntos de la misma foto y cuadrícula: acuerdo, kappa de Cohen y "
                                    "puntos en desacuerdo (doble clasificación del protocolo).")
        self.compare_btn.clicked.connect(self._on_compare)
        row3.addWidget(self.compare_btn)
        lv.addLayout(row3)
        # v0.15.14: retomar o revisar una clasificación exportada
        self.load_cls_btn = QPushButton("Cargar clasificación de un CSV…")
        self.load_cls_btn.setToolTip("Vuelve a cargar la clase de cada punto desde un CobDosel_suelo_<foto>_puntos.csv de "
                                     "la misma foto. Si el área no está preparada, la toma del CSV de foto que está al "
                                     "lado. Sirve para continuar una clasificación, revisarla, agregar grupos o "
                                     "exportar de nuevo sin clasificar otra vez.")
        self.load_cls_btn.clicked.connect(self._on_load_classification)
        lv.addWidget(self.load_cls_btn)
        self.out = QTextEdit(); self.out.setReadOnly(True); lv.addWidget(self.out, 1)
        help_lbl = QLabel(HELP); help_lbl.setWordWrap(True); lv.addWidget(help_lbl)
        split.addWidget(tabs)
        self.canvas = ImageCanvas(self._on_canvas_click)
        self.canvas.guides_fn = lambda: (self.rgb is not None and self.area is None and self.mode_quad.isChecked()
                                         and len(self.corners) < 4)
        split.addWidget(self.canvas)
        split.setStretchFactor(1, 2)
        self._grid_buttons(False)

    def _on_tiles(self):
        """v0.15.3: calibración con baldosas; se guarda con un nombre y queda elegida para el área fija."""
        from .tile_calibration_dialog import TileCalibrationDialog     # aquí: ese módulo usa ImageCanvas de este
        dlg = TileCalibrationDialog(self, start_path=self.photo_path)
        run = getattr(dlg, "exec", None) or dlg.exec_
        if run() != QDialog.DialogCode.Accepted or not dlg.result:
            return
        from .tile_calibration_dialog import default_name
        name, ok = QInputDialog.getText(self, "Guardar calibración", "Nombre del lente / cámara (se propone uno):",
                                        QLineEdit.EchoMode.Normal, default_name(dlg.result))
        if ok and name.strip():
            self.save_tile_calibration(dlg.result, name.strip())
        else:
            self._log("Calibración con baldosas no guardada: el área fija solo usa calibraciones guardadas.")

    def save_tile_calibration(self, res, name):
        from .tile_calibration_dialog import build_calibration
        cal = build_calibration(res)
        path = save_calibration(name, cal, metadata={
            "circle_diameter_cm": cal["circle_diameter_cm"], "camera_height_cm": cal["camera_height_cm"],
            "pixel_diameter_px": cal["pixel_diameter_px"], "image_size": [res["width_px"], res["height_px"]],
            "original_image_size": [res["width_px"], res["height_px"]], "calibration_method": "baldosas"})
        self.cal_combo.clear()
        for n, _p in list_calibrations():
            self.cal_combo.addItem(n, n)
        i = self.cal_combo.findData(name)
        if i < 0:
            i = self.cal_combo.findText(name)
        if i >= 0:
            self.cal_combo.setCurrentIndex(i)
        for line in res.get("lines") or []:
            self._log(line)
        self._log("Calibración «{}» guardada ({}).".format(name, path))
        return path

    def _grid_buttons(self, on):
        for w in (self.new_grid_btn, self.next_btn, self.skip_btn, self.doubt_btn):
            w.setEnabled(on)

    def _update_fit(self, *_a):
        """Indica el cuadrado más grande que cabe a esta altura y la altura mínima para el lado elegido (v0.15.9)."""
        if not hasattr(self, "fit_lbl"):
            return
        if self.mode_quad.isChecked():
            self.fit_lbl.setText("")
            return
        name = self.cal_combo.currentData()
        if not name:
            self.fit_lbl.setText("Elija una calibración «Rectilínea» del teléfono para calcular qué cuadrado cabe.")
            return
        try:
            cal = load_calibration(name)
            if self.rgb is not None:
                h, w = self.rgb.shape[:2]
                bad = gc.aspect_mismatch(cal, w, h)
                if bad:
                    self.fit_lbl.setText("<b>No se puede usar:</b> " + bad)
                    return
                cal = scale_calibration_to_image(cal, w, h)
            else:
                w, h = cal.get("image_width_px"), cal.get("image_height_px")
            if cal.get("lens_type") != "regular" or cal.get("projection") != "rectilinear":
                self.fit_lbl.setText("La calibración elegida no es «Rectilínea»: el área fija necesita una.")
                return
            H, side = float(self.height_spin.value()), float(self.side_spin.value())
            r = gc.fixed_area_fit(cal["focal_length_px"], min(w, h), H, side)
        except Exception as e:      # calibración ilegible: se informa y no se calcula
            self.fit_lbl.setText("No se pudo leer la calibración: {}".format(e))
            return
        txt = ("A {:.2f} m de altura cabe un cuadrado de hasta {:.2f} m ({:.2f} m con 5 % de margen). Para {:.2f} m "
               "de lado: altura mínima {:.2f} m ({:.2f} m con margen).").format(
            H, r["max_side_m"], r["max_side_margin_m"], side, r["min_height_m"], r["min_height_margin_m"])
        if not r["fits"]:
            txt = "<b>No cabe.</b> " + txt
        elif not r["fits_margin"]:
            txt = ("<b>Cabe sin margen:</b> si la foto se toma unos centímetros más abajo, ya no cabe y el cuadrado "
                   "queda pegado a los bordes de la foto. ") + txt
        self.fit_lbl.setText(txt)

    def _on_mode(self, *_a):
        quad = self.mode_quad.isChecked()
        self.corner_lbl.setEnabled(quad)
        self.clear_btn.setEnabled(quad)
        for w in (self.height_spin, self.cal_combo):
            w.setEnabled(not quad)
        self._update_fit()
        if not quad and self.area is None:
            self.corners = []
            self.canvas.polygon = []
            self.canvas.update()
            self._update_corner_label()

    def _update_corner_label(self):
        self.corner_lbl.setText("Esquinas: {} de 4 (clic derecho quita la última)".format(len(self.corners)))

    def _set_class(self, key):
        self.current_class = key

    # ------------------------------------------------------------ clases (v0.15.7: clases nuevas)
    @staticmethod
    def _swatch(col):
        pm = QPixmap(14, 14)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(*col))
        p.drawEllipse(1, 1, 12, 12)
        p.end()
        return QIcon(pm)

    def _build_class_radios(self):
        for b in list(self.class_group.buttons()):
            self.class_group.removeButton(b)
            b.setParent(None)
            b.deleteLater()
        keys = [k for k, _l, _c in self.classes]
        if self.current_class not in keys:
            self.current_class = "seca"
        for i, (key, lbl, col) in enumerate(self.classes, 1):
            rb = QRadioButton("{} — {}".format(i, lbl)); rb.setProperty("clase", key)
            rb.setIcon(self._swatch(col))           # color de la clase (como en la vista y el informe)
            if key == self.current_class:
                rb.setChecked(True)
            rb.toggled.connect(lambda on, k=key: on and self._set_class(k))
            self.class_group.addButton(rb, i)
            self.class_box.addWidget(rb)
        if hasattr(self, "g3"):
            self.g3.setTitle("3. Clasificar los puntos (teclas 1–{})".format(len(self.classes)))

    def set_groups(self, groups):
        """Guarda los grupos de clases y actualiza el resultado (v0.15.13)."""
        self.groups = gc.groups_for(groups, self.classes)
        try:
            gc.save_groups(self.groups)
        except OSError as e:
            self._log("No se pudieron guardar los grupos de clases: {}".format(e))
        if self.points:
            self._refresh()

    def _on_groups(self):
        from .ground_groups_dialog import GroupsDialog
        dlg = GroupsDialog(self.classes, self.groups, self)
        run = getattr(dlg, "exec", None) or dlg.exec_
        run()
        self.set_groups(dlg.groups)

    def _set_classes(self, custom):
        self.custom_classes = custom
        self.classes = gc.class_list(custom)
        self.groups = gc.groups_for(getattr(self, "groups", []), self.classes)
        try:
            gc.save_groups(self.groups)
        except OSError:
            pass
        try:
            gc.save_custom_classes(custom)
        except OSError as e:
            self._log("No se pudieron guardar las clases nuevas: {}".format(e))
        self._build_class_radios()
        if self.points:
            self._refresh()

    def add_class(self, name):
        """Agrega una clase nueva (guardada para las próximas fotos) y la deja marcada."""
        custom = gc.new_custom_class(name, self.custom_classes)
        self.current_class = custom[-1]["clave"]
        self._set_classes(custom)
        self._log("Clase nueva: «{}» (tecla {}).".format(custom[-1]["nombre"], len(self.classes)))
        return custom[-1]["clave"]

    def remove_class(self, key):
        if any(lab == key for lab in self.labels):
            raise ValueError("Hay puntos de esta foto con esa clase: cámbielos antes de quitarla.")
        custom = [d for d in self.custom_classes if d["clave"] != key]
        if len(custom) == len(self.custom_classes):
            raise ValueError("Solo se pueden quitar las clases agregadas por el usuario.")
        self._set_classes(custom)

    def _on_new_class(self):
        names = {l.lower() for _k, l, _c in self.classes}
        sug = "Vegetación amarillenta" if "vegetación amarillenta" not in names else ""
        name, ok = QInputDialog.getText(self, "Nueva clase", "Nombre de la clase:", QLineEdit.EchoMode.Normal, sug)
        if not ok:
            return
        try:
            self.add_class(name)
        except ValueError as e:
            QMessageBox.warning(self, "Nueva clase", str(e))

    def _on_del_class(self):
        if not self.custom_classes:
            QMessageBox.information(self, "Quitar clase", "No hay clases agregadas por el usuario.")
            return
        names = [d["nombre"] for d in self.custom_classes]
        name, ok = QInputDialog.getItem(self, "Quitar clase", "Clase agregada:", names, 0, False)
        if not ok:
            return
        try:
            self.remove_class(self.custom_classes[names.index(name)]["clave"])
        except ValueError as e:
            QMessageBox.warning(self, "Quitar clase", str(e))

    def keyPressEvent(self, e):
        k = e.key()
        keys = [getattr(Qt.Key, "Key_{}".format(i)) for i in range(1, len(self.classes) + 1)]
        if self.canvas.pan_key(e):
            return
        if k in keys:
            self.class_key(keys.index(k) + 1)
            return
        if k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom_by(1.5)
            return
        if k in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.canvas.zoom_by(1 / 1.5)
            return
        if k == Qt.Key.Key_V:
            self.show_green.setChecked(not self.show_green.isChecked())
            return
        if k == Qt.Key.Key_N:
            self.advance()
            return
        if k == Qt.Key.Key_S:
            self.next_unclassified()
            return
        if k == Qt.Key.Key_C:
            self.show_diff.setChecked(not self.show_diff.isChecked())
            return
        if k == Qt.Key.Key_D:
            self.next_doubtful()
            return
        if k == Qt.Key.Key_F:
            self.canvas.fit()
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
        self.zones = []
        self._update_progress()
        self.photo_edit.setText(path)
        self.canvas.polygon = []
        self.canvas.marks = []
        self.canvas.current = None
        self.current_idx = None
        self.canvas.set_image(self.rgb)
        self.canvas.setFocus()          # flechas, +/− y F funcionan sin hacer clic antes en la foto
        self._update_fit()              # v0.15.9: el lado corto de esta foto
        self._update_corner_label()
        self._grid_buttons(False)
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

    def _show_photo(self):
        """Vuelve a la foto completa para marcar o corregir el cuadro."""
        self.area = None
        self.points, self.labels, self.auto, self.res = [], [], [], None
        self.zones = []
        self._update_progress()
        self.canvas.marks = []
        self.canvas.set_image(self.rgb)
        self._grid_buttons(False)
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(False)

    def _on_clear_corners(self):
        if self.rgb is None:
            return
        if self.area is not None and not self._confirm_discard():
            return
        if self.area is not None:
            self._show_photo()
        self.corners = []
        self.canvas.polygon = []
        self.canvas.update()
        self._update_corner_label()

    def _on_canvas_click(self, x, y, button=LEFT):
        if self.area is None:                      # marcando el cuadro sobre la foto
            if not self.mode_quad.isChecked():
                return
            if button == RIGHT:
                if self.corners:
                    self.corners.pop()
            elif len(self.corners) < 4 and x is not None:
                self.corners.append((x, y))
            self.canvas.polygon = list(self.corners)
            self.canvas.update()
            self._update_corner_label()
            if len(self.corners) == 4:
                self._log("Cuadro marcado: pulse «Preparar área».")
            return
        if not self.points or x is None or button == RIGHT:
            return
        d = [(px - x) ** 2 + (py - y) ** 2 for px, py in self.points]
        i = int(np.argmin(d))
        tol = max(self.area.shape[:2]) / 40.0
        if d[i] <= tol * tol:
            self.current_idx = i
            self.canvas.current = self.points[i]
            self.label_point(i, self.current_class)

    def _manual_labels(self):
        """Número de puntos cuya clase puso o cambió el analista."""
        return sum(1 for lab, a in zip(self.labels, self.auto) if lab != a)

    def _confirm_discard(self):
        n = self._manual_labels()
        if not n:
            return True
        ans = QMessageBox.question(self, "Cobertura del suelo",
                                   "Hay {} puntos clasificados a mano. Se descartarán. ¿Continuar?".format(n),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return ans == QMessageBox.StandardButton.Yes

    def prepare_area(self, confirm=True):
        """Prepara el área (cuadro enderezado o área fija), la vegetación verde y la cuadrícula de puntos (con la
        semilla del campo «Semilla de la cuadrícula»)."""
        if self.rgb is None:
            raise ValueError("Cargue una foto primero.")
        if confirm and self.points and not self._confirm_discard():
            return False
        side = float(self.side_spin.value())
        meta = {"archivo": os.path.basename(self.photo_path), "fecha_exif": self.exif.get("capture_datetime"),
                "latitud": self.exif.get("latitude"), "longitud": self.exif.get("longitude"),
                "sitio": self.site_edit.text().strip(), "analista": self.analyst_edit.text().strip(),
                "lado_m": side, "area_m2": side * side}
        if self.mode_quad.isChecked():
            if len(self.corners) != 4:
                raise ValueError("Marque las 4 esquinas del cuadro en la foto ({} de 4).".format(len(self.corners)))
            area = gc.rectify_quadrat(self.rgb, self.corners)
            meta.update(modo_area="Cuadro", altura_camara_m=None, calibracion=None,
                        esquinas_px=gc.corners_text(self.corners))
        else:
            name = self.cal_combo.currentData()
            if not name:
                raise ValueError("El área fija necesita una calibración guardada del teléfono.")
            h, w = self.rgb.shape[:2]
            raw = load_calibration(name)
            bad = gc.aspect_mismatch(raw, w, h)        # v0.15.9: antes no se comprobaba
            if bad:
                raise ValueError(bad)
            cal = scale_calibration_to_image(raw, w, h)
            f = cal.get("focal_length_px")
            if cal.get("lens_type") != "regular" or cal.get("projection") != "rectilinear":
                raise ValueError("El área fija necesita una calibración «Rectilínea» de lente regular.")
            area, _side_px = gc.crop_fixed_area(self.rgb, f, float(self.height_spin.value()), side)
            meta.update(modo_area="Área fija", altura_camara_m=float(self.height_spin.value()), calibracion=name)
        self.area = area
        self.green = gc.canopeo_mask(self.area)
        self.only_x, self.only_c = gc.disagreement_masks(self.area)
        self.points, self.seed = gc.point_grid(self.area.shape, int(self.points_spin.value()),
                                               seed=int(self.seed_spin.value()))
        self.auto = gc.auto_labels(self.points, self.green)
        self.zones = gc.point_zones(self.points, self.only_x, self.only_c)      # v0.15.16
        self.labels = list(self.auto)
        self.current_idx = None
        self.canvas.current = None
        meta["semilla"] = self.seed
        self.meta = meta
        self.canvas.polygon = []
        self._redraw_area(fit=True)
        self._grid_buttons(True)
        self._refresh()
        return True

    def _on_prepare(self):
        try:
            self.prepare_area()
        except Exception as e:
            QMessageBox.warning(self, "Cobertura del suelo", str(e))

    def new_grid(self, confirm=True):
        """Otra semilla y otra cuadrícula sobre la misma área."""
        if self.area is None:
            return False
        if confirm and not self._confirm_discard():
            return False
        seed = int(np.random.default_rng().integers(0, 1000000))
        while seed == self.seed:
            seed = int(np.random.default_rng().integers(0, 1000000))
        self.seed_spin.setValue(seed)
        self.points, self.seed = gc.point_grid(self.area.shape, int(self.points_spin.value()), seed=seed)
        self.auto = gc.auto_labels(self.points, self.green)
        self.zones = gc.point_zones(self.points, self.only_x, self.only_c)      # v0.15.16
        self.labels = list(self.auto)
        self.current_idx = None
        self.canvas.current = None
        self.meta["semilla"] = self.seed
        self._log("Nueva cuadrícula (semilla {}).".format(self.seed))
        self._refresh()
        return True

    def _on_new_grid(self):
        self.new_grid()

    def _redraw_area(self, *_a, fit=False):
        if self.area is None:
            return
        shown = self.area
        diff = self.show_diff.isChecked() and self.only_x is not None
        if self.show_green.isChecked() or diff:
            green = self.green if self.show_green.isChecked() else None
            if green is not None and diff:
                green = self.green & ~self.only_c          # magenta: verde para las dos reglas
            shown = gc.shade(self.area, green, self.only_x if diff else None, self.only_c if diff else None)
        self.canvas.set_image(shown, keep_view=not fit)

    def advance(self):
        """«Siguiente» (N): asigna la clase marcada al punto actual, si aún no tiene clase, y pasa al siguiente sin
        clasificar. Sin punto actual (primera vez), solo muestra el primer punto sin clasificar. Si el modo
        reglamentario no admite la clase, el punto queda sin clasificar y la vista no avanza."""
        i = self.current_idx
        if i is not None and self.points and self.labels[i] is None:
            if not self.label_point(i, self.current_class):
                return i
        return self.next_unclassified()

    # ------------------------------------------------------------ modo reglamentario (v0.15.12)
    def regulatory(self):
        return self.reg_check.isChecked()

    def rule_violation(self, i, key):
        """Texto del motivo si el modo reglamentario no admite la clase key en el punto i, o ''."""
        if not self.regulatory() or not self.auto:
            return ""
        if self.auto[i] == "verde" and key not in ("verde", "no_id"):
            return ("Modo reglamentario: el punto {} es verde según la regla de Canopeo; solo puede pasar a «No "
                    "identificable» si cae sobre algo que no es vegetación.".format(i + 1))
        if self.auto[i] != "verde" and key == "verde":
            return ("Modo reglamentario: el punto {} no es verde según la regla de Canopeo; no se pasa a verde a mano "
                    "(use otra clase, por ejemplo «Vegetación seca» o una clase propia).".format(i + 1))
        return ""

    def violations(self):
        return [i for i, lab in enumerate(self.labels) if lab is not None and self.rule_violation(i, lab)]

    def _on_reg_toggled(self, on):
        if not on or not self.labels:
            self._update_progress()
            return
        bad = self.violations()
        if not bad:
            self._log("Modo reglamentario activado: el verde lo decide la regla de Canopeo.")
            self._update_progress()
            return
        ans = QMessageBox.question(
            self, "Modo reglamentario",
            "{} puntos ya clasificados no cumplen la regla del modo reglamentario (verde cambiado o pasado a verde a "
            "mano). ¿Devolverles la clase automática (verde, o sin clasificar) y activar el modo?".format(len(bad)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            for i in bad:
                self.labels[i] = self.auto[i]
            self._log("Modo reglamentario activado; {} puntos volvieron a su clase automática.".format(len(bad)))
            self._refresh()
        else:
            self.reg_check.blockSignals(True)
            self.reg_check.setChecked(False)
            self.reg_check.blockSignals(False)

    def export_meta(self):
        """Metadatos del CSV y el informe con el estado del modo reglamentario."""
        return dict(self.meta, modo_reglamentario="Sí" if self.regulatory() and not self.violations() else "No")

    def goto_point(self, i):
        """Hace actual el punto i y centra la vista en él (desde «Comparar clasificaciones»)."""
        self.current_idx = i
        x, y = self.points[i]
        self.canvas.current = (x, y)
        self.canvas.center_on(x, y, zoom=max(self.canvas.zoom, 6.0))
        self.canvas.setFocus()
        self._update_progress()

    # ------------------------------------------------------------ doble clasificación (v0.15.12)
    def load_area_from_csv(self, path, confirm=True):
        """Repite el área, la semilla y el número de puntos del CSV de foto de otro analista y prepara el área."""
        if self.rgb is None:
            raise ValueError("Cargue primero la foto.")
        r = gc.read_photo_csv(path)
        name = os.path.basename(self.photo_path or "")
        if (r.get("archivo") or "").strip() != name:
            raise ValueError("El CSV es de la foto «{}» y la foto abierta es «{}».".format(r.get("archivo"), name))
        num = lambda k: float(str(r.get(k)).strip().replace(",", "."))
        self.side_spin.setValue(num("lado_m"))
        self.points_spin.setValue(int(round(num("n_puntos"))))
        self.seed_spin.setValue(int(round(num("semilla"))))
        if (r.get("modo_area") or "").strip() == "Área fija":
            cal = (r.get("calibracion") or "").strip()
            i = self.cal_combo.findData(cal)
            if i < 0:
                raise ValueError("La calibración «{}» del CSV no está guardada en esta computadora: copie su archivo "
                                 "a ~/.cobdosel/calibrations.".format(cal))
            self.mode_fixed.setChecked(True)
            self.cal_combo.setCurrentIndex(i)
            self.height_spin.setValue(num("altura_camara_m"))
        else:
            corners = gc.parse_corners(r.get("esquinas_px"))
            if not corners:
                raise ValueError("El CSV no tiene las esquinas del cuadro (columna esquinas_px): fue exportado con una "
                                 "versión anterior a 0.15.12 o con área fija.")
            self.mode_quad.setChecked(True)
            self.corners = list(corners)
            self.canvas.polygon = list(self.corners)
            self._update_corner_label()
        self._log("Área y cuadrícula de «{}»: modo {}, lado {:g} m, semilla {}, {} puntos.".format(
            os.path.basename(path), r.get("modo_area"), self.side_spin.value(), self.seed_spin.value(),
            self.points_spin.value()))
        return self.prepare_area(confirm=confirm)

    def _on_load_area(self):
        if self.rgb is None:
            QMessageBox.information(self, "Cargar área", "Cargue primero la foto.")
            return
        p, _ = QFileDialog.getOpenFileName(self, "CSV de foto de otro analista", os.path.dirname(self.photo_path or ""),
                                           "CSV de foto (*.csv)")
        if not p:
            return
        try:
            self.load_area_from_csv(p)
        except Exception as e:
            QMessageBox.warning(self, "Cargar área y cuadrícula", str(e))

    # ------------------------------------------------------------ cargar una clasificación (v0.15.14)
    def load_classification_from_csv(self, path, confirm=True):
        """Carga la clase de cada punto de un _puntos.csv de la misma foto, área y cuadrícula. Si el área no está
        preparada (o es otra cuadrícula), la prepara antes con el CSV de foto del mismo prefijo. Las clases propias que
        falten se crean (si caben). Devuelve el número de puntos clasificados."""
        from . import ground_compare as gcmp
        if self.rgb is None:
            raise ValueError("Cargue primero la foto.")
        pts = gcmp.read_points_csv(path)
        name = os.path.basename(self.photo_path or "")
        files = {p["archivo"] for p in pts}
        if files != {name}:
            raise ValueError("El CSV de puntos es de la foto «{}» y la foto abierta es «{}».".format(
                ", ".join(sorted(files)), name))
        pts = sorted(pts, key=lambda p: p["punto"])

        def same_grid():
            return (len(self.points) == len(pts) and all(
                abs(x - p["x"]) <= gcmp.POINT_TOL_PX and abs(y - p["y"]) <= gcmp.POINT_TOL_PX
                for (x, y), p in zip(self.points, pts)))
        if not same_grid():
            photo_csv = path[:-len("_puntos.csv")] + ".csv" if path.endswith("_puntos.csv") else ""
            if not photo_csv or not os.path.isfile(photo_csv):
                raise ValueError("Los puntos del CSV no coinciden con la cuadrícula abierta y no se encontró el CSV de "
                                 "foto «{}» para preparar la misma área: prepare el área y la semilla de esa "
                                 "clasificación.".format(os.path.basename(photo_csv or path)))
            if self.load_area_from_csv(photo_csv, confirm=confirm) is False:
                return 0
            if not same_grid():
                raise ValueError("Con el área del CSV de foto, los puntos siguen sin coincidir: revise que los dos CSV "
                                 "sean de la misma clasificación.")
        elif confirm and self._manual_labels() and not self._confirm_discard():
            return 0
        # nombres de clase → claves; las clases propias que falten se crean
        names = {l: k for k, l, _c in self.classes}
        norm = {gc.class_key_for(l): k for k, l, _c in self.classes}
        missing = []
        for p in pts:
            for lab in (p["clase"],):
                if lab and lab != "Sin clasificar" and lab not in names and gc.class_key_for(lab) not in norm \
                        and lab not in missing:
                    missing.append(lab)
        prev = self.current_class
        for lab in missing:
            self.add_class(lab)                       # error claro si no caben (hasta 9)
        if missing:
            self.current_class = prev                 # la clase marcada no cambia al cargar
            self._build_class_radios()
        names = {l: k for k, l, _c in self.classes}
        norm = {gc.class_key_for(l): k for k, l, _c in self.classes}
        labels = []
        for p in pts:
            lab = p["clase"]
            labels.append(None if not lab or lab == "Sin clasificar" else names.get(lab, norm.get(gc.class_key_for(lab))))
        auto_csv = [names.get(p["automatica"], norm.get(gc.class_key_for(p["automatica"]))) if p["automatica"] else None
                    for p in pts]
        if auto_csv != list(self.auto):
            n = sum(1 for a, b in zip(auto_csv, self.auto) if a != b)
            raise ValueError("La clase automática de {} puntos no coincide con el área abierta (otra área o una versión "
                             "distinta de la regla): no se carga.".format(n))
        if self.regulatory():
            bad = [i for i, lab in enumerate(labels) if lab is not None and self.rule_violation(i, lab)]
            if bad:
                raise ValueError("La clasificación tiene {} puntos que no cumplen el modo reglamentario (por ejemplo, el "
                                 "{}): desactive el modo para cargarla y revisarla.".format(len(bad), bad[0] + 1))
        self.labels = labels
        self.current_idx = None
        self.canvas.current = None
        self._refresh()
        done = sum(1 for lab in labels if lab is not None)
        self._log("Clasificación cargada de «{}»: {} de {} puntos con clase{}.".format(
            os.path.basename(path), done, len(labels),
            "; clases creadas: " + ", ".join(missing) if missing else ""))
        return done

    def _on_load_classification(self):
        if self.rgb is None:
            QMessageBox.information(self, "Cargar clasificación", "Cargue primero la foto.")
            return
        p, _ = QFileDialog.getOpenFileName(self, "CSV de puntos", os.path.dirname(self.photo_path or ""),
                                           "CSV de puntos (*_puntos.csv);;CSV (*.csv)")
        if not p:
            return
        try:
            self.load_classification_from_csv(p)
        except Exception as e:
            QMessageBox.warning(self, "Cargar clasificación de un CSV", str(e))

    def _on_compare(self):
        from .ground_compare_dialog import GroundCompareDialog
        dlg = GroundCompareDialog(self, ground_dialog=self)
        dlg.show()
        self._compare_dlg = dlg

    def _update_progress(self):
        if not self.labels:
            self.progress_lbl.setText("Prepare el área para ver los puntos.")
            return
        n = len(self.labels)
        pend = sum(1 for lab in self.labels if lab is None)
        txt = "<b>Sin clasificar: {} de {} puntos</b>".format(pend, n)
        if self.current_idx is not None:
            lab = self.labels[self.current_idx]
            txt += " · punto actual: n.º {} ({})".format(
                self.current_idx + 1, dict((k, l) for k, l, _c in self.classes).get(lab, lab) if lab else "sin clasificar")
            z = self.zones[self.current_idx] if self.current_idx < len(self.zones) else None
            if z:
                txt += "<br><b>Punto dudoso, zona {}</b>: {}.".format(z, gc.ZONE_HELP[z])
        elif pend:
            txt += " · pulse «Siguiente» (N) para ir al primero"
        else:
            txt += " · todos clasificados"
        self.progress_lbl.setText(txt)

    def next_doubtful(self):
        """Centra la vista en el siguiente punto en zona cian o naranja (clasificado o no), a partir del actual."""
        n = len(self.zones)
        if not n:
            return None
        start = -1 if self.current_idx is None else self.current_idx
        nxt = next((i for i in ((start + k) % n for k in range(1, n + 1)) if self.zones[i]), None)
        if nxt is None:
            self._log("Ningún punto cae donde las dos reglas del verde difieren.")
            return None
        self.goto_point(nxt)
        return nxt

    def next_unclassified(self):
        """Centra la vista (con zoom) en el siguiente punto sin clasificar, a partir del punto actual (orden de la
        cuadrícula, de izquierda a derecha y de arriba abajo; al final vuelve al principio). Lo marca como actual."""
        n = len(self.labels)
        if not n:
            return None
        start = -1 if self.current_idx is None else self.current_idx
        order = [(start + k) % n for k in range(1, n + 1)]
        nxt = next((i for i in order if self.labels[i] is None), None)
        if nxt is None:
            self.current_idx = None
            self.canvas.current = None
            self.canvas.update()
            self._log("No quedan puntos sin clasificar.")
            self._update_progress()
            return None
        self.current_idx = nxt
        x, y = self.points[nxt]
        self.canvas.current = (x, y)
        self.canvas.center_on(x, y, zoom=max(self.canvas.zoom, 4.0))
        self.canvas.setFocus()
        self._update_progress()
        return nxt

    def class_key(self, k):
        """Tecla 1–9: elige la clase y, si hay un punto actual, lo clasifica y (opcional) pasa al siguiente."""
        if not 1 <= k <= len(self.classes):
            return
        self.class_group.button(k).setChecked(True)
        key = self.classes[k - 1][0]
        if self.current_idx is not None and self.points:
            if self.label_point(self.current_idx, key) and self.auto_next.isChecked():
                self.next_unclassified()

    def label_point(self, i, key):
        """Asigna la clase; devuelve False (sin cambiar nada) si el modo reglamentario no la admite."""
        why = self.rule_violation(i, key)
        if why:
            self._log(why)
            self.progress_lbl.setText("<b>{}</b>".format(why))
            return False
        self.labels[i] = key
        self._refresh()
        return True

    def _refresh(self):
        colors = {k: c for k, _l, c in self.classes}
        self.canvas.marks = [(x, y, colors.get(lab, (255, 255, 255)))
                             for (x, y), lab in zip(self.points, self.labels)]
        self.canvas.update()
        self.res = gc.summarize(self.area, self.labels, classes=self.classes, groups=self.groups)
        r = self.res
        # v0.15.16 (opción A): se muestra Canopeo; ExG − ExR solo aparece en el aviso «a revisar»
        lines = ["Vegetación verde (Canopeo): {:.2f} %".format(r["verde_canopeo_pct"])]
        if r["revisar"]:
            lines.append("A revisar: " + gc.agreement_note(r))
        nzx, nzc = self.zones.count("cian"), self.zones.count("naranja")
        if nzx or nzc:
            lines.append("Puntos dudosos (donde las dos reglas del verde difieren): {} en zona cian y {} en zona naranja; "
                         "revíselos con «Siguiente punto dudoso» (D).".format(nzx, nzc))
        lines.append("Puntos ({}; sin clasificar: {}; semilla {}):".format(r["n_puntos"], r["sin_clasificar"], self.seed))
        for key, lbl, _col in self.classes:
            d = r["clases"][key]
            lines.append("  {:<18} {:>4}  {:6.1f} %  (IC 95 %: {:.1f}–{:.1f} %)".format(
                lbl, d["puntos"], d["pct"], d["ic_inf"], d["ic_sup"]))
        if r.get("lista_grupos"):
            lines.append("Grupos de clases:")
            for g in r["lista_grupos"]:
                d = r["grupos"][g["nombre"]]
                lines.append("  {:<18} {:>4}  {:6.1f} %  (IC 95 %: {:.1f}–{:.1f} %)  [{}]".format(
                    g["nombre"], d["puntos"], d["pct"], d["ic_inf"], d["ic_sup"], d["definicion"].split(" = ", 1)[1]))
        self.out.setPlainText("\n".join(lines))
        for bb in (self.csv_btn, self.html_btn):
            bb.setEnabled(True)
        self._update_progress()

    def _default_prefix(self):
        base = os.path.splitext(os.path.basename(self.photo_path or "foto"))[0]
        return os.path.join(os.path.dirname(self.photo_path or ""), "CobDosel_suelo_{}".format(base))

    def _on_csv(self):
        p, _ = QFileDialog.getSaveFileName(self, "Prefijo de los CSV", self._default_prefix() + ".csv", "CSV (*.csv)")
        if not p:
            return
        p = p[:-4] if p.lower().endswith(".csv") else p
        sep, dec = csv_style()
        paths = gc.write_csvs(self.res, self.export_meta(), self.points, self.labels, self.auto, p, VERSION, sep, dec,
                              zones=self.zones)
        self._log("CSV guardados: " + "; ".join(paths))
        QMessageBox.information(self, "CSV guardados", "\n".join(paths))

    def _on_html(self):
        p, _ = QFileDialog.getSaveFileName(self, "Informe HTML", self._default_prefix() + "_informe.html",
                                           "HTML (*.html)")
        if not p:
            return
        if not p.lower().endswith((".html", ".htm")):
            p += ".html"
        gc.write_html(self.res, self.export_meta(), self.area, self.points, self.labels, p, VERSION)
        self._log("Informe guardado: " + p)
        ans = QMessageBox.question(self, "Informe guardado", "{}\n\n¿Abrir el informe ahora?".format(p),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(p)):
                webbrowser.open("file://" + os.path.abspath(p))
