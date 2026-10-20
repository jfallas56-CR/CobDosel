"""Herramienta interactiva para medir el diámetro en píxeles de un círculo de referencia.

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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QScrollArea, QGroupBox, QSizePolicy, QComboBox,
)

from .exif_gps import load_oriented_rgb_image
from .circle_measure import measure, MAX_POINTS

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False


class ImageCanvas(QLabel):
    """Lienzo QLabel que muestra la imagen escalada y permite marcar puntos del borde."""

    def __init__(self, parent=None, max_dim=4096):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.max_dim = max_dim
        self.original_pil = None
        self.original_np = None
        self.load_scale = 1.0
        self.original_file_size = None
        self.display_scale = 1.0
        self.user_zoom = 1.0
        self.points = []
        self.mode = "diametro"
        self.on_points_changed = None

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

        self.original_np = np.array(self.original_pil)
        self.points = []
        self.user_zoom = 1.0
        self._recompute_scale()
        self._redraw()
        self._notify()

    def reset_points(self):
        self.points = []
        self._redraw()
        self._notify()

    def _recompute_scale(self):
        if self.original_pil is None:
            self.display_scale = 1.0
            return

        parent = self.parentWidget()
        if parent is None:
            fit = 1.0
        else:
            vw = (
                parent.viewport().width() - 4
                if hasattr(parent, "viewport")
                else parent.width() - 4
            )
            vh = (
                parent.viewport().height() - 4
                if hasattr(parent, "viewport")
                else parent.height() - 4
            )
            iw, ih = self.original_pil.size
            if vw <= 0 or vh <= 0:
                fit = 1.0
            else:
                fit = min(vw / float(iw), vh / float(ih), 1.0)

        self.display_scale = fit * self.user_zoom

    def _redraw(self):
        if self.original_np is None:
            self.setText("No hay ninguna imagen cargada.")
            self.setPixmap(QPixmap())
            return

        iw, ih = self.original_pil.size
        dw = max(1, int(iw * self.display_scale))
        dh = max(1, int(ih * self.display_scale))

        display_pil = self.original_pil.resize((dw, dh), Image.LANCZOS)
        display_np = np.ascontiguousarray(np.array(display_pil))

        qimg = QImage(
            display_np.data, dw, dh, dw * 3, QImage.Format.Format_RGB888
        )
        pixmap = QPixmap.fromImage(qimg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        sc = self.display_scale
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
            painter.drawEllipse(int((cx - r) * sc), int((cy - r) * sc),
                                int(2 * r * sc), int(2 * r * sc))
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

        painter.end()
        self.setPixmap(pixmap)
        self.resize(dw, dh)

    def _notify(self):
        if callable(self.on_points_changed):
            self.on_points_changed(self.points)

    def mousePressEvent(self, event):
        if self.original_np is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
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

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.user_zoom *= 1.15
            else:
                self.user_zoom /= 1.15
            self.user_zoom = max(0.1, min(20.0, self.user_zoom))
            self._recompute_scale()
            self._redraw()
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.original_pil is not None:
            self._recompute_scale()
            self._redraw()


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

    def __init__(self, image_path=None, parent=None, max_dim=4096):
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Medir círculo de referencia")
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
            "círculo. Consejo: use Ctrl + rueda del ratón para acercar/alejar."
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

        toolbar.addStretch()
        self.zoom_label = QLabel("Zoom: ajustar")
        toolbar.addWidget(self.zoom_label)

        layout.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.canvas = ImageCanvas(self, max_dim=self.max_dim)
        self.canvas.on_points_changed = self._on_points_changed
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, stretch=1)

        result_group = QGroupBox("Medición")
        result_layout = QFormLayout(result_group)

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

        layout.addWidget(result_group)

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
        self.canvas.user_zoom = min(20.0, self.canvas.user_zoom * 1.25)
        self.canvas._recompute_scale()
        self.canvas._redraw()
        self._update_zoom_label()

    def _on_zoom_out(self):
        self.canvas.user_zoom = max(0.1, self.canvas.user_zoom / 1.25)
        self.canvas._recompute_scale()
        self.canvas._redraw()
        self._update_zoom_label()

    def _on_zoom_reset(self):
        self.canvas.user_zoom = 1.0
        self.canvas._recompute_scale()
        self.canvas._redraw()
        self._update_zoom_label()

    def _update_zoom_label(self):
        self.zoom_label.setText(
            "Zoom: {:.0f}%".format(self.canvas.display_scale * 100.0)
        )

    def _on_mode_changed(self, _idx):
        self.canvas.mode = self.mode_combo.currentData() or "diametro"
        self.canvas.reset_points()

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
