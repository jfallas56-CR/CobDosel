"""Herramienta interactiva para medir el diámetro en píxeles de un círculo de referencia.

v0.14.31:
- Zoom por rectángulo (clic derecho y arrastrar, o Mayús + arrastrar), valor de zoom editable
  (5–800 % de los píxeles reales), Ctrl + rueda centrado en el puntero y desplazamiento con el
  botón central. Solo se pinta la parte visible: el zoom alto ya no crea una copia gigante.

v0.11.0 (CobDosel):
- Tres modos: diámetro (2 puntos), dos diámetros E–O y N–S (4 puntos) y ajuste de círculo
  por mínimos cuadrados (≥ 5 puntos). Guías E–O / N–S por el centro de la imagen;
  centro del círculo medido (+) y línea de desplazamiento en todos los modos (0.14.5).
  0.14.6: en dos diámetros, círculo dibujado = el que pasa por los 4 puntos.
- Informa diferencia entre diámetros, residuo del ajuste y desplazamiento del centro del
  círculo respecto del centro de la foto (circle_measure.py).

v0.10.0 (2026-10-17):
- Enums Qt con ámbito y posición del ratón compatibles con Qt5/Qt6.

v0.9.0:
- Interfaz completamente en español.
- Redimensionable horizontal y verticalmente con el ratón.
- Usa load_oriented_rgb_image con max_dim coherente con el diálogo principal
  para evitar desajustes de escala y orientación EXIF.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import math
import numpy as np
from PIL import Image

from qgis.PyQt.QtCore import Qt, QPoint, QRect, QRectF, QSize
from qgis.PyQt.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QScrollArea, QGroupBox, QSizePolicy, QComboBox, QDoubleSpinBox,
    QSpinBox, QRubberBand, QSplitter, QWidget,
)

from .exif_gps import load_oriented_rgb_image
from .circle_measure import measure, MAX_POINTS

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False


# v0.14.31: límites del zoom (escala de pantalla respecto de los píxeles reales de la foto)
MIN_SCALE = 0.05     # 5 %
MAX_SCALE = 8.0      # 800 %
_MIN_BAND_PX = 6     # rectángulos más pequeños se ignoran (clic accidental)


class ImageCanvas(QLabel):
    """
    Lienzo que muestra la imagen y permite marcar puntos del borde.

    v0.14.31: se pinta solo la parte visible (paintEvent); por encima de 100 % no se crea una
    copia ampliada de toda la foto, así el zoom alto no consume memoria. Rectángulo de zoom con
    botón derecho (o Mayús + izquierdo) y desplazamiento con el botón central.
    """

    def __init__(self, parent=None, max_dim=4096):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.max_dim = max_dim
        self.original_pil = None
        self.original_np = None
        self._qimg = None
        self._cache_pix = None
        self._cache_scale = None
        self.load_scale = 1.0
        self.original_file_size = None
        self.display_scale = 1.0
        self.fit_mode = True          # True = ajustar a la ventana; False = zoom fijo del usuario
        self.points = []
        self.mode = "diametro"
        self.on_points_changed = None
        self.on_zoom_rect = None      # llamada con el rectángulo en coordenadas de la imagen
        self.on_scale_changed = None
        self.scroll_area = None
        self._band = None
        self._band_origin = None
        self._pan = None

    # ------------------------------------------------------------------ imagen
    def load_image(self, path):
        try:
            img, scale, orig_wh = load_oriented_rgb_image(
                path, max_dim=self.max_dim
            )
            self.original_pil = img
            self.load_scale = scale
            self.original_file_size = orig_wh
        except Exception as e:
            raise RuntimeError("No se pudo cargar la imagen: " + str(e))

        self.original_np = np.ascontiguousarray(np.array(self.original_pil.convert("RGB")))
        h, w = self.original_np.shape[:2]
        self._qimg = QImage(self.original_np.data, w, h, w * 3, QImage.Format.Format_RGB888)
        self._cache_pix = None
        self._cache_scale = None
        self.setText("")
        self.points = []
        self.fit_mode = True
        self._recompute_scale()
        self._redraw()
        self._notify()

    def reset_points(self):
        self.points = []
        self._redraw()
        self._notify()

    def _viewport_size(self):
        area = self.scroll_area
        if area is not None:
            vp = area.viewport()
            return vp.width() - 4, vp.height() - 4
        parent = self.parentWidget()
        if parent is None:
            return 0, 0
        return parent.width() - 4, parent.height() - 4

    def fit_scale(self):
        """Escala que hace caber la foto completa en la ventana (máx. 100 %)."""
        if self.original_pil is None:
            return 1.0
        vw, vh = self._viewport_size()
        iw, ih = self.original_pil.size
        if vw <= 0 or vh <= 0:
            return 1.0
        return max(MIN_SCALE, min(vw / float(iw), vh / float(ih), 1.0))

    def _recompute_scale(self):
        if self.original_pil is None:
            self.display_scale = 1.0
            return
        if self.fit_mode:
            self.display_scale = self.fit_scale()

    def set_scale(self, scale):
        """Fija la escala de pantalla (1.0 = 100 % = un píxel de la foto por píxel de pantalla)."""
        self.fit_mode = False
        self.display_scale = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
        self._redraw()
        if callable(self.on_scale_changed):
            self.on_scale_changed(self.display_scale)

    def set_fit(self):
        self.fit_mode = True
        self._recompute_scale()
        self._redraw()
        if callable(self.on_scale_changed):
            self.on_scale_changed(self.display_scale)

    def _redraw(self):
        if self.original_np is None:
            self.setText("No hay ninguna imagen cargada.")
            self.setPixmap(QPixmap())
            return
        iw, ih = self.original_pil.size
        sc = self.display_scale
        dw = max(1, int(round(iw * sc)))
        dh = max(1, int(round(ih * sc)))
        # Por debajo de 100 %: copia reducida (LANCZOS) en caché; por encima se pinta el recorte visible
        if sc < 1.0:
            if self._cache_pix is None or self._cache_scale != sc:
                small = np.ascontiguousarray(np.array(self.original_pil.resize((dw, dh), Image.LANCZOS)))
                qs = QImage(small.data, dw, dh, dw * 3, QImage.Format.Format_RGB888)
                self._cache_pix = QPixmap.fromImage(qs.copy())
                self._cache_scale = sc
        else:
            self._cache_pix = None
            self._cache_scale = None
        self.setFixedSize(dw, dh)
        self.update()

    # ------------------------------------------------------------------ pintado
    def paintEvent(self, event):  # noqa: N802 (API de Qt)
        if self._qimg is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        sc = self.display_scale
        exposed = event.rect()
        if self._cache_pix is not None:
            painter.drawPixmap(exposed, self._cache_pix, exposed)
        else:
            # Píxeles nítidos (vecino más cercano) para marcar el borde con precisión
            src = QRectF(exposed.x() / sc, exposed.y() / sc, exposed.width() / sc, exposed.height() / sc)
            painter.drawImage(QRectF(exposed), self._qimg, src)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_overlays(painter, sc)
        painter.end()

    def _draw_overlays(self, painter, sc):
        iw, ih = self.original_pil.size
        dw, dh = self.width(), self.height()
        # Guías E–O y N–S por el centro de la imagen (el círculo debe quedar centrado)
        pen_guide = QPen(QColor(0, 220, 255), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_guide)
        painter.drawLine(0, int(ih / 2.0 * sc), dw, int(ih / 2.0 * sc))
        painter.drawLine(int(iw / 2.0 * sc), 0, int(iw / 2.0 * sc), dh)

        pen_point = QPen(QColor(255, 0, 0), 2)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        for i, (x_img, y_img) in enumerate(self.points):
            painter.setPen(pen_point)
            x_disp = int(x_img * sc)
            y_disp = int(y_img * sc)
            painter.drawEllipse(x_disp - 6, y_disp - 6, 12, 12)
            painter.drawLine(x_disp - 10, y_disp, x_disp + 10, y_disp)
            painter.drawLine(x_disp, y_disp - 10, x_disp, y_disp + 10)
            painter.drawText(x_disp + 12, y_disp - 12, str(i + 1))

        pen_line = QPen(QColor(0, 200, 0), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen_line)
        pairs = []
        if self.mode in ("diametro", "cruz") and len(self.points) >= 2:
            pairs.append(self.points[0:2])
        if self.mode == "cruz" and len(self.points) >= 4:
            pairs.append(self.points[2:4])
        for (x1, y1), (x2, y2) in pairs:
            painter.drawLine(int(x1 * sc), int(y1 * sc), int(x2 * sc), int(y2 * sc))
            mx = int((x1 + x2) / 2 * sc)
            my = int((y1 + y2) / 2 * sc)
            text = "{:.1f} px".format(math.hypot(x2 - x1, y2 - y1))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawText(mx + 8, my - 8, text)
            painter.setPen(QPen(QColor(255, 255, 0), 1))
            painter.drawText(mx + 7, my - 9, text)
            painter.setPen(pen_line)

        res = measure(self.points, self.mode, (iw, ih)) if self.points else None
        if res is not None and res.get("centre_xy") is not None:
            cx, cy = res["centre_xy"]
            r = res["diameter_px"] / 2.0
            painter.setPen(QPen(QColor(255, 140, 0), 2))
            painter.drawEllipse(QRectF((cx - r) * sc, (cy - r) * sc, 2 * r * sc, 2 * r * sc))
            painter.drawLine(int(cx * sc) - 8, int(cy * sc), int(cx * sc) + 8, int(cy * sc))
            painter.drawLine(int(cx * sc), int(cy * sc) - 8, int(cx * sc), int(cy * sc) + 8)
            # Desplazamiento: línea del centro de la foto al centro del círculo, con el % del diámetro
            if res.get("centre_offset_pct") is not None:
                icx, icy = iw / 2.0 * sc, ih / 2.0 * sc
                painter.setPen(QPen(QColor(255, 140, 0), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(icx), int(icy), int(cx * sc), int(cy * sc))
                text = "centro desplazado {:.1f} %".format(res["centre_offset_pct"])
                tx, ty = int(cx * sc) + 12, int(cy * sc) + 20
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawText(tx + 1, ty + 1, text)
                painter.setPen(QPen(QColor(255, 140, 0), 1))
                painter.drawText(tx, ty, text)

    def render_view(self):
        """Imagen de lo que se ve en el lienzo (para pruebas y capturas)."""
        return self.grab().toImage()

    def _notify(self):
        if callable(self.on_points_changed):
            self.on_points_changed(self.points)

    # ------------------------------------------------------------------ ratón
    @staticmethod
    def _pos(event):
        p = event.position() if hasattr(event, "position") else event.pos()
        return QPoint(int(p.x()), int(p.y()))

    @staticmethod
    def _gpos(event):
        p = event.globalPosition() if hasattr(event, "globalPosition") else event.globalPos()
        return p.x(), p.y()

    def mousePressEvent(self, event):  # noqa: N802 (API de Qt)
        if self.original_np is None:
            return
        btn = event.button()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        # Rectángulo de zoom: botón derecho, o Mayús + botón izquierdo
        if btn == Qt.MouseButton.RightButton or (btn == Qt.MouseButton.LeftButton and shift):
            self._band_origin = self._pos(event)
            if self._band is None:
                self._band = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self._band.setGeometry(QRect(self._band_origin, QSize()))
            self._band.show()
            event.accept()
            return
        # Mover la imagen: botón central
        if btn == Qt.MouseButton.MiddleButton and self.scroll_area is not None:
            gx, gy = self._gpos(event)
            self._pan = (gx, gy, self.scroll_area.horizontalScrollBar().value(),
                         self.scroll_area.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if btn != Qt.MouseButton.LeftButton:
            return

        pos = event.position() if hasattr(event, "position") else event.pos()
        x_img = pos.x() / self.display_scale
        y_img = pos.y() / self.display_scale

        iw, ih = self.original_pil.size
        x_img = max(0.0, min(float(iw - 1), x_img))
        y_img = max(0.0, min(float(ih - 1), y_img))

        self.points.append((x_img, y_img))
        limit = MAX_POINTS.get(self.mode, 2)
        if len(self.points) > limit:
            self.points = self.points[-limit:] if limit <= 2 else self.points[:limit]

        self._redraw()
        self._notify()

    def mouseMoveEvent(self, event):  # noqa: N802 (API de Qt)
        if self._band_origin is not None and self._band is not None:
            self._band.setGeometry(QRect(self._band_origin, self._pos(event)).normalized())
            event.accept()
            return
        if self._pan is not None and self.scroll_area is not None:
            gx, gy = self._gpos(event)
            self.scroll_area.horizontalScrollBar().setValue(int(self._pan[2] - (gx - self._pan[0])))
            self.scroll_area.verticalScrollBar().setValue(int(self._pan[3] - (gy - self._pan[1])))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 (API de Qt)
        if self._band_origin is not None:
            rect = QRect(self._band_origin, self._pos(event)).normalized()
            self._band_origin = None
            if self._band is not None:
                self._band.hide()
            if rect.width() >= _MIN_BAND_PX and rect.height() >= _MIN_BAND_PX:
                sc = self.display_scale
                self.zoom_to_image_rect(QRectF(rect.x() / sc, rect.y() / sc,
                                               rect.width() / sc, rect.height() / sc))
            event.accept()
            return
        if self._pan is not None:
            self._pan = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ zoom
    def zoom_to_image_rect(self, rect):
        """Amplía para que el rectángulo (coordenadas de la imagen) llene la ventana y lo centra."""
        if self.original_pil is None or rect.width() <= 0 or rect.height() <= 0:
            return
        vw, vh = self._viewport_size()
        if vw <= 0 or vh <= 0:
            return
        self.set_scale(min(vw / rect.width(), vh / rect.height()))
        self.center_on(rect.center().x(), rect.center().y())
        if callable(self.on_zoom_rect):
            self.on_zoom_rect(rect)

    def view_center(self):
        """Punto de la imagen que está en el centro de la ventana."""
        area = self.scroll_area
        iw, ih = self.original_pil.size
        if area is None:
            return iw / 2.0, ih / 2.0
        vp = area.viewport()
        sc = self.display_scale
        # self.x()/self.y() = posición del lienzo dentro de la ventana (negativa al desplazarse)
        x = (vp.width() / 2.0 - self.x()) / sc
        y = (vp.height() / 2.0 - self.y()) / sc
        return min(max(x, 0.0), float(iw)), min(max(y, 0.0), float(ih))

    def center_on(self, x_img, y_img):
        area = self.scroll_area
        if area is None:
            return
        vp = area.viewport()
        sc = self.display_scale
        area.horizontalScrollBar().setValue(int(round(x_img * sc - vp.width() / 2.0)))
        area.verticalScrollBar().setValue(int(round(y_img * sc - vp.height() / 2.0)))

    def zoom_keep_center(self, scale):
        if self.original_pil is None:
            return
        cx, cy = self.view_center()
        self.set_scale(scale)
        self.center_on(cx, cy)

    def wheelEvent(self, event):  # noqa: N802 (API de Qt)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.original_pil is not None:
            delta = event.angleDelta().y()
            old = self.display_scale
            pos = event.position() if hasattr(event, "position") else event.posF()
            x_img, y_img = pos.x() / old, pos.y() / old
            self.set_scale(old * (1.15 if delta > 0 else 1 / 1.15))
            area = self.scroll_area
            if area is not None:
                # El punto bajo el puntero queda bajo el puntero
                vx = pos.x() + self.x()
                vy = pos.y() + self.y()
                sc = self.display_scale
                area.horizontalScrollBar().setValue(int(round(x_img * sc - vx)))
                area.verticalScrollBar().setValue(int(round(y_img * sc - vy)))
            event.accept()
        else:
            super().wheelEvent(event)


_VERDICT_COLOURS = {"repetir_foto": "#b71c1c", "repetir_medicion": "#b71c1c",
                    "usable_avisos": "#8a5a00", "ok": "#1b5e20"}
_SCOPE_TITLES = (("fotografia", "Fotografía"), ("medicion", "Medición (puntos marcados)"))


def quality_html(res):
    """
    Control de calidad en HTML: veredicto global en negrita y, debajo, los mensajes agrupados
    por ámbito (fotografía / medición), ⚠ en rojo para lo que hay que repetir y ⓘ en ámbar para
    las notas informativas.
    """
    import html as _html
    code, text = res.get("verdict") or ("ok", "Dentro de tolerancia.")
    icon = {"ok": "✓", "usable_avisos": "ⓘ"}.get(code, "⚠")
    parts = ["<p style='color:{};font-weight:bold;margin:0 0 4px 0'>{} {}</p>".format(
        _VERDICT_COLOURS.get(code, "#1b5e20"), icon, _html.escape(text))]
    for scope, title in _SCOPE_TITLES:
        items = [i for i in res.get("issues") or [] if i["scope"] == scope]
        if not items:
            continue
        parts.append("<p style='margin:4px 0 0 0'><b>{}:</b></p>".format(title))
        for i in items:
            colour, mark = ("#b71c1c", "⚠") if i["level"] == "warn" else ("#8a5a00", "ⓘ")
            parts.append("<p style='color:{};margin:0 0 2px 12px'>{} {}</p>".format(
                colour, mark, _html.escape(i["text"]).replace("\n", "<br/>")))
    return "".join(parts)


class MeasureCircleDialog(QDialog):
    """Diálogo redimensionable para medir el diámetro en píxeles de un círculo de referencia."""

    def __init__(self, image_path=None, parent=None, max_dim=4096, diameter_cm=None, height_cm=None):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Medir círculo de referencia")
        # v0.14.30: D y H reales del círculo que se mide (se piden junto con la medición)
        self._init_d = diameter_cm
        self._init_h = height_cm
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumSize(480, 420)
        self.resize(1000, 750)
        self.setSizeGripEnabled(True)

        self.max_dim = max_dim
        self.image_path = None
        self._build_ui()

        if image_path:
            self.load_image(image_path)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Marque puntos sobre el BORDE del círculo de referencia según el modo elegido.\n"
            "Las líneas cian discontinuas pasan por el centro de la foto (no por el del círculo). "
            "Al completar los puntos se dibuja en naranja el círculo medido, su centro (+) y una "
            "línea hasta el centro de la foto con el desplazamiento en % del diámetro.\n"
            "Clic en el centro de la línea del círculo; puntos repartidos alrededor de todo el "
            "círculo.\nZoom: clic derecho y arrastrar (o Mayús + arrastrar) = ampliar esa zona · "
            "escriba el % en «Zoom» · Ctrl + rueda = acercar/alejar · botón central = mover."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo de medición:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Diámetro (2 puntos opuestos)", userData="diametro")
        self.mode_combo.addItem(
            "Dos diámetros E–O y N–S (4 puntos en los extremos del círculo: 1–2 horizontal, 3–4 vertical) — recomendado",
            userData="cruz")
        self.mode_combo.addItem("Ajuste de círculo (≥ 5 puntos; ideal 8, uno cada 45°)", userData="ajuste")
        self.mode_combo.setToolTip(
            "Dos diámetros: promedia dos mediciones independientes (reduce el error de clic\n"
            "≈ √2) y detecta una elipse (cámara no paralela al círculo) si difieren > 1 %.\n"
            "Ajuste de círculo: mínimos cuadrados sobre 5–64 puntos; da diámetro, centro y\n"
            "residuo, y es poco sensible a un clic erróneo. Con 8 puntos repartidos es el modo\n"
            "más preciso; puntos concentrados en un arco < 180° dan un ajuste inestable.")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, stretch=1)
        layout.addLayout(mode_row)

        toolbar = QHBoxLayout()

        self.load_btn = QPushButton("Cargar imagen…")
        self.load_btn.clicked.connect(self._on_load)
        toolbar.addWidget(self.load_btn)

        self.reset_btn = QPushButton("Reiniciar puntos")
        self.reset_btn.clicked.connect(self._on_reset)
        toolbar.addWidget(self.reset_btn)

        self.zoom_in_btn = QPushButton("Acercar (+)")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        toolbar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Alejar (−)")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        toolbar.addWidget(self.zoom_out_btn)

        self.zoom_reset_btn = QPushButton("Ajustar a ventana")
        self.zoom_reset_btn.clicked.connect(self._on_zoom_reset)
        toolbar.addWidget(self.zoom_reset_btn)

        self.zoom_100_btn = QPushButton("100 %")
        self.zoom_100_btn.setToolTip("Un píxel de la foto por píxel de pantalla.")
        self.zoom_100_btn.clicked.connect(lambda: self._set_zoom_pct(100))
        toolbar.addWidget(self.zoom_100_btn)

        toolbar.addStretch()
        toolbar.addWidget(QLabel("Zoom:"))
        # v0.14.31: valor de zoom editable (Intro para aplicar)
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(int(MIN_SCALE * 100), int(MAX_SCALE * 100))
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setSingleStep(25)
        self.zoom_spin.setKeyboardTracking(False)
        self.zoom_spin.setAccelerated(True)
        self.zoom_spin.setToolTip(
            "Escala de pantalla en % de los píxeles reales de la foto (100 % = un píxel de la foto\n"
            "por píxel de pantalla). Escriba un valor ({}–{} %) y pulse Intro.\n"
            "También: clic derecho y arrastrar (o Mayús + arrastrar) = ampliar el rectángulo;\n"
            "Ctrl + rueda = acercar/alejar en el puntero; botón central y arrastrar = mover.".format(
                int(MIN_SCALE * 100), int(MAX_SCALE * 100)))
        self.zoom_spin.valueChanged.connect(self._set_zoom_pct)
        toolbar.addWidget(self.zoom_spin)
        self.zoom_label = QLabel("ajustado")
        self.zoom_label.setMinimumWidth(60)
        toolbar.addWidget(self.zoom_label)

        layout.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.canvas = ImageCanvas(self, max_dim=self.max_dim)
        self.canvas.on_points_changed = self._on_points_changed
        self.canvas.scroll_area = self.scroll
        self.canvas.on_scale_changed = lambda _s: self._update_zoom_label()
        self.scroll.setWidget(self.canvas)
        # v0.14.31: imagen a la izquierda (toda la altura) y datos/resultado a la derecha
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.scroll)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter.addWidget(side)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, stretch=1)

        ref_group = QGroupBox("Círculo de referencia de esta foto")
        ref_layout = QFormLayout(ref_group)
        ref_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.d_spin = QDoubleSpinBox()
        self.d_spin.setRange(0.1, 1000.0)
        self.d_spin.setDecimals(2)
        self.d_spin.setSuffix(" cm")
        self.d_spin.setValue(float(self._init_d) if self._init_d else 33.0)
        self.d_spin.setToolTip("Diámetro real del círculo que va a marcar. Con círculos concéntricos, el del círculo marcado.")
        ref_layout.addRow("Diámetro real del círculo marcado (D):", self.d_spin)
        self.h_spin = QDoubleSpinBox()
        self.h_spin.setRange(0.1, 1000.0)
        self.h_spin.setDecimals(2)
        self.h_spin.setSuffix(" cm")
        self.h_spin.setValue(float(self._init_h) if self._init_h else 40.0)
        self.h_spin.setToolTip("Distancia del vidrio de la cámara al papel cuando se tomó ESTA foto.")
        ref_layout.addRow("Distancia del lente al círculo (H):", self.h_spin)
        self.theta_label = QLabel("—")
        ref_layout.addRow("Borde del círculo:", self.theta_label)
        self.d_spin.valueChanged.connect(self._update_theta)
        self.h_spin.valueChanged.connect(self._update_theta)
        self.theta_label.setWordWrap(True)
        self._update_theta()
        side_layout.addWidget(ref_group)

        result_group = QGroupBox("Medición")
        result_layout = QFormLayout(result_group)
        result_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.distance_label = QLabel("—")
        self.distance_label.setStyleSheet(
            "font-weight: bold; font-size: 14pt; color: #1b5e20;"
        )
        result_layout.addRow("Diámetro en píxeles:", self.distance_label)

        self.points_label = QLabel("—")
        self.points_label.setWordWrap(True)
        result_layout.addRow("Detalle:", self.points_label)

        self.quality_label = QLabel("—")
        self.quality_label.setTextFormat(Qt.TextFormat.RichText)
        self.quality_label.setWordWrap(True)
        result_layout.addRow("Control de calidad:", self.quality_label)

        side_layout.addWidget(result_group)
        side_layout.addStretch()
        side.setMinimumWidth(300)
        side.setMaximumWidth(460)
        self.splitter.setSizes([700, 330])

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.accept_btn = QPushButton("Usar este valor")
        self.accept_btn.clicked.connect(self.accept)
        self.accept_btn.setEnabled(False)
        btn_row.addWidget(self.accept_btn)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

        # Modo por defecto: dos diámetros E–O y N–S
        self.mode_combo.setCurrentIndex(1)
        self.canvas.mode = self.mode_combo.currentData()

    def load_image(self, path):
        try:
            self.canvas.load_image(path)
        except RuntimeError as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        self.image_path = path
        self._update_zoom_label()

    def _on_load(self):
        filters = "Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"
        if HEIF_SUPPORTED:
            filters += " *.heic *.heif"
        filters += ");;Todos los archivos (*)"

        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir imagen de calibración", "", filters
        )
        if path:
            self.load_image(path)

    def _on_reset(self):
        self.canvas.reset_points()

    def _on_zoom_in(self):
        self.canvas.zoom_keep_center(self.canvas.display_scale * 1.25)

    def _on_zoom_out(self):
        self.canvas.zoom_keep_center(self.canvas.display_scale / 1.25)

    def _on_zoom_reset(self):
        self.canvas.set_fit()

    def _set_zoom_pct(self, pct):
        """Zoom escrito por el usuario (en % de los píxeles reales)."""
        if self.canvas.original_pil is None:
            return
        if abs(pct / 100.0 - self.canvas.display_scale) < 0.005:
            return
        self.canvas.zoom_keep_center(pct / 100.0)

    def _update_zoom_label(self):
        self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(int(round(self.canvas.display_scale * 100.0)))
        self.zoom_spin.blockSignals(False)
        self.zoom_label.setText("ajustado" if self.canvas.fit_mode else "")

    def resizeEvent(self, event):  # noqa: N802 (API de Qt)
        """En modo «Ajustar a ventana» la foto sigue el tamaño de la ventana."""
        super().resizeEvent(event)
        if self.canvas.original_pil is not None and self.canvas.fit_mode:
            self.canvas._recompute_scale()
            self.canvas._redraw()
            self._update_zoom_label()

    def showEvent(self, event):  # noqa: N802 (API de Qt)
        super().showEvent(event)
        if self.canvas.original_pil is not None and self.canvas.fit_mode:
            self.canvas.set_fit()

    def _on_mode_changed(self, _idx):
        self.canvas.mode = self.mode_combo.currentData() or "diametro"
        self.canvas.reset_points()

    def _update_theta(self, *_):
        d, h = self.d_spin.value(), self.h_spin.value()
        self.theta_label.setText("θ = atan(D / 2H) = {:.2f}° del cenit.\nD debe ser el del círculo que marca.".format(
            math.degrees(math.atan(d / (2.0 * h))) if h > 0 else 0.0))

    def get_diameter_cm(self):
        return float(self.d_spin.value())

    def get_height_cm(self):
        return float(self.h_spin.value())

    def get_measurement(self):
        """Resultado completo de circle_measure.measure() o None."""
        if self.canvas.original_pil is None:
            return None
        return measure(self.canvas.points, self.canvas.mode, self.canvas.original_pil.size)

    def _on_points_changed(self, points):
        res = self.get_measurement() if points else None
        if res is None:
            need = {"diametro": 2, "cruz": 4, "ajuste": 5}.get(self.canvas.mode, 2)
            self.distance_label.setText("—")
            self.points_label.setText("{} de {} puntos marcados.".format(len(points), need))
            if len(points) >= need:
                # v0.14.23: puntos completos pero repetidos o alineados
                self.points_label.setText("{} puntos marcados, pero no definen un círculo (puntos repetidos "
                                          "o alineados). Use «Reiniciar puntos» y márquelos de nuevo sobre la "
                                          "línea del círculo.".format(len(points)))
            self.quality_label.setText("—")
            self.accept_btn.setEnabled(False)
            return

        self.distance_label.setText("{:.2f} px".format(res["diameter_px"]))
        det = []
        if res["mode"] == "cruz":
            det.append("E–O = {:.2f} px, N–S = {:.2f} px, diferencia = {:.2f} %; diámetro del círculo "
                       "por los 4 puntos = {:.2f} px".format(
                           res["d_ew_px"], res["d_ns_px"], res["diff_pct"] or 0.0, res["diameter_px"]))
        if res["mode"] == "ajuste":
            det.append("{} puntos, residuo RMS = {:.2f} px".format(
                res["n_points"], res["fit_rms_px"]))
        if res.get("centre_xy") is not None:
            det.append("centro del círculo = ({:.1f}, {:.1f})".format(*res["centre_xy"]))
        if res.get("centre_offset_px") is not None:
            det.append("desplazamiento respecto del centro de la foto = {:.1f} px ({:.1f} %)".format(
                res["centre_offset_px"], res["centre_offset_pct"]))
        self.points_label.setText("; ".join(det))
        if res.get("arc_deg") is not None:
            det.append("arco cubierto por los puntos = {:.0f}°".format(res["arc_deg"]))
            self.points_label.setText("; ".join(det))
        self.quality_label.setText(quality_html(res))
        self.quality_label.setStyleSheet("")
        self.accept_btn.setEnabled(True)

    def get_pixel_diameter(self):
        res = self.get_measurement()
        return None if res is None else res["diameter_px"]

    def get_native_measurement(self):
        """
        (diámetro en píxeles de la foto ORIGINAL, (ancho, alto) originales orientados).
        Permite reescalar la medición a una foto de análisis de otra resolución.
        """
        d = self.get_pixel_diameter()
        if d is None or self.canvas.original_file_size is None:
            return None
        scale = self.canvas.load_scale or 1.0
        return d / scale, tuple(self.canvas.original_file_size)
