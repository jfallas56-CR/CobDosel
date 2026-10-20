"""
Diálogo interactivo de ajuste de umbral con vista previa en vivo para CobDosel.

Historial:
- 0.11.0 (CobDosel): colores del histograma con el mismo criterio que el análisis
  (claro si valor ≥ nivel de corte); el área válida incluye la máscara de horizonte.
- 0.10.0 (2026-10-17): histograma, estadísticas y Otsu restringidos al área válida
  (círculo de análisis / sin borde negro del ojo de pez); colores del histograma
  según la opción «cielo más brillante»; enums Qt con ámbito (Qt5/Qt6).
- 0.9.x: corrige el orden de inicialización en _build_ui() para conectar
  histogram_widget.thresholdDragged después de crear threshold_slider.
- Interfaz completamente en español.
- Histograma interactivo arrastrable con el ratón (clic y arrastre sobre el histograma).
- 0.14.17: inspector de píxeles (valor bajo el puntero frente al nivel de corte).
- Selector «Claro / Oscuro» («Light / Dark» de la app GLAMA):
  permite alternar entre resaltar los claros de cielo (Claro) o la máscara inversa del dosel en rojo (Oscuro)
  para verificar que ningún claro sea clasificado como vegetación ni viceversa.
- Zoom con la rueda del ratón, desplazamiento arrastrando con el botón izquierdo y botón "Ajustar".
- Redimensionable horizontal y verticalmente.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import numpy as np
from PIL import Image

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QFont,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QCheckBox, QGroupBox, QScrollArea, QSizePolicy,
    QWidget, QComboBox, QRadioButton, QButtonGroup, QMessageBox,
)

from ._version import fmt_int
from .canopy_analysis import (
    threshold_image,
    clean_binary_mask,
    extract_channel,
    compute_auto_threshold,
    CHANNEL_MODES,
    AUTO_THRESHOLD_METHODS,
    AUTO_THRESHOLD_LABELS,
)


# Superposición de la vista previa (Claro = cielo, Oscuro = dosel); misma opacidad en ambos modos
SKY_OVERLAY_COLOR = (255, 90, 30)     # Tinte rojo-anaranjado para claros (modo Claro)
CANOPY_INVERSE_COLOR = (230, 30, 30)  # Máscara inversa roja para vegetación (modo Oscuro)
OVERLAY_ALPHA = 0.65                  # opacidad por defecto, igual en Claro y Oscuro (ajustable)


def _event_x(event):
    """Coordenada x de un QMouseEvent compatible con Qt5 (pos) y Qt6 (position)."""
    if hasattr(event, "position"):
        return event.position().x()
    return event.pos().x()


class HistogramWidget(QWidget):
    """Dibuja el histograma de intensidades y permite arrastrar la línea de umbral."""

    thresholdDragged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.histogram = None
        self.threshold = 128
        self.bg_color = QColor(245, 245, 245)
        self.grid_color = QColor(220, 220, 220)
        self.line_color = QColor(220, 0, 0)
        self.sky_is_bright = True
        self._dragging = False

    def set_histogram(self, histogram):
        self.histogram = histogram
        self.update()

    def set_threshold(self, value):
        self.threshold = int(value)
        self.update()

    def set_sky_bright(self, is_bright):
        self.sky_is_bright = bool(is_bright)
        self.update()

    def _pos_to_threshold(self, x):
        w = max(1, self.width())
        val = int(round((float(x) / float(w)) * 255.0))
        return max(1, min(254, val))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            t = self._pos_to_threshold(_event_x(event))
            self.set_threshold(t)
            self.thresholdDragged.emit(t)

    def mouseMoveEvent(self, event):
        if self._dragging:
            t = self._pos_to_threshold(_event_x(event))
            self.set_threshold(t)
            self.thresholdDragged.emit(t)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = self.width()
        H = self.height()

        painter.fillRect(0, 0, W, H, self.bg_color)

        if self.histogram is None or len(self.histogram) == 0:
            painter.setPen(QPen(QColor(120, 120, 120)))
            painter.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter, "Sin datos de histograma")
            return

        n_bins = len(self.histogram)
        bin_width = W / float(n_bins)

        hist = self.histogram.astype(np.float64)
        hist_log = np.log1p(hist)
        max_val = hist_log.max() if hist_log.max() > 0 else 1.0

        painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DotLine))
        for i in range(1, 10):
            y = int(H * i / 10)
            painter.drawLine(0, y, W, y)

        for i in range(n_bins):
            x = int(i * bin_width)
            bar_h = int(hist_log[i] / max_val * (H - 4))
            if bar_h <= 0:
                continue
            # Rojo = píxeles clasificados como cielo; azul = dosel
            is_sky = (i >= self.threshold) if self.sky_is_bright else (i < self.threshold)
            if is_sky:
                color = QColor(210, 80, 80, 190)
            else:
                color = QColor(65, 90, 210, 190)
            painter.fillRect(
                x, H - bar_h, max(1, int(bin_width)), bar_h, color
            )

        tx = int(self.threshold * bin_width)
        painter.setPen(QPen(self.line_color, 2))
        painter.drawLine(tx, 0, tx, H)

        painter.setPen(QPen(QColor(0, 0, 0)))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        label = "Nivel de corte T = {}".format(self.threshold)
        if tx > W - 150:
            painter.drawText(W - 150, 20, label)
        else:
            painter.drawText(tx + 5, 20, label)

        painter.setPen(QPen(QColor(80, 80, 80)))
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(2, H - 4, "0 (Negro)")
        painter.drawText(W - 75, H - 4, "255 (Blanco)")
        painter.drawText(W // 2 - 10, H - 4, "128")


class ThresholdPreviewCanvas(QLabel):
    """Muestra la imagen umbralizada con modo Claro (resaltar cielo) u Oscuro (máscara inversa de dosel)."""

    zoomChanged = pyqtSignal(float)
    pixelInspected = pyqtSignal(str)     # inspector de píxeles (0.14.17)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 150)
        self.setStyleSheet("background-color: #2c2c2c;")

        self.original_pil = None
        self.display_pil = None
        self.gray_array = None
        self.channel_mode = "blue_red"
        self.sky_is_bright = True
        self.highlight_sky = True  # True = Claro (resalta cielo), False = Oscuro (máscara inversa del dosel)
        self.threshold = 128
        self.apply_cleanup = False
        self.overlay_alpha = OVERLAY_ALPHA
        self.zoom = 1.0
        self.valid_mask_full = None
        self.valid_mask = None
        self.setMouseTracking(True)

    def set_image(self, pil_image, gray_array=None, max_dim=1400, valid_mask=None):
        self.original_pil = pil_image
        self.valid_mask_full = valid_mask

        w, h = pil_image.size
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            self.display_pil = pil_image.resize(new_size, Image.LANCZOS)
        else:
            self.display_pil = pil_image.copy()

        self.valid_mask = None
        if self.valid_mask_full is not None:
            dw, dh = self.display_pil.size
            m = Image.fromarray(self.valid_mask_full.astype(np.uint8) * 255, "L")
            self.valid_mask = np.array(m.resize((dw, dh), Image.NEAREST)) > 127

        self._recompute_channel()
        self._redraw()

    def _recompute_channel(self):
        if self.display_pil is None:
            return
        arr = np.array(self.display_pil)
        self.gray_array = extract_channel(arr, self.channel_mode)

    def set_channel_mode(self, mode):
        self.channel_mode = mode
        self._recompute_channel()
        self._redraw()

    def set_threshold(self, value):
        self.threshold = int(value)
        self._redraw()

    def set_sky_bright(self, is_bright):
        self.sky_is_bright = bool(is_bright)
        self._redraw()

    def set_highlight_sky(self, highlight_sky):
        self.highlight_sky = bool(highlight_sky)
        self._redraw()

    def set_overlay_alpha(self, alpha):
        self.overlay_alpha = max(0.0, min(1.0, float(alpha)))
        self._redraw()

    def set_cleanup(self, do_cleanup):
        self.apply_cleanup = bool(do_cleanup)
        self._redraw()

    def set_zoom(self, zoom):
        self.zoom = max(0.15, min(6.0, float(zoom)))
        self._redraw()
        self.zoomChanged.emit(self.zoom)

    def fit_to_viewport(self, viewport_w, viewport_h):
        if self.display_pil is None or viewport_w <= 0 or viewport_h <= 0:
            self.set_zoom(1.0)
            return
        iw, ih = self.display_pil.size
        fit = min((viewport_w - 8) / float(iw), (viewport_h - 8) / float(ih), 1.0)
        self.set_zoom(max(0.15, fit))

    def wheelEvent(self, event):  # noqa: N802 (API de Qt)
        """Rueda del ratón = zoom (centrado en el puntero cuando hay barras de desplazamiento)."""
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        old = self.zoom
        self.set_zoom(old * (1.15 if delta > 0 else 1 / 1.15))
        area = getattr(self, "scroll_area", None)
        if area is not None and old > 0:
            f = self.zoom / old
            pos = event.position() if hasattr(event, "position") else event.posF()
            for bar, p in ((area.horizontalScrollBar(), pos.x()), (area.verticalScrollBar(), pos.y())):
                bar.setValue(int(bar.value() + (f - 1.0) * p))
        event.accept()

    def mousePressEvent(self, event):  # noqa: N802 (API de Qt)
        """Arrastrar con el botón izquierdo = mover la imagen ampliada."""
        area = getattr(self, "scroll_area", None)
        if area is not None and event.button() == Qt.MouseButton.LeftButton:
            gp = event.globalPosition() if hasattr(event, "globalPosition") else event.globalPos()
            self._drag = (gp.x(), gp.y(), area.horizontalScrollBar().value(), area.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def inspect_at(self, x_widget, y_widget):
        """
        Inspector de píxeles: valor del píxel bajo el puntero en la foto a resolución completa,
        en el canal elegido, frente al nivel de corte. Devuelve el texto (o None fuera de la foto).
        """
        if self.original_pil is None or self.display_pil is None:
            return None
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None
        pw, ph = pm.width(), pm.height()
        ox = max(0, (self.width() - pw) // 2)
        oy = max(0, (self.height() - ph) // 2)
        dx = (x_widget - ox) / self.zoom
        dy = (y_widget - oy) / self.zoom
        dw, dh = self.display_pil.size
        if not (0 <= dx < dw and 0 <= dy < dh):
            return None
        W, H = self.original_pil.size
        X = min(W - 1, int(dx * W / float(dw)))
        Y = min(H - 1, int(dy * H / float(dh)))
        rgb = self.original_pil.getpixel((X, Y))
        if isinstance(rgb, int):
            rgb = (rgb, rgb, rgb)
        rgb = tuple(int(v) for v in rgb[:3])
        val = int(extract_channel(np.array([[rgb]], dtype=np.uint8), self.channel_mode)[0, 0])
        t = int(self.threshold)
        is_sky = (val >= t) if self.sky_is_bright else (val < t)
        diff = val - t
        rel = ("igual al corte" if diff == 0 else
               "{} {} del corte".format(abs(diff), "por encima" if diff > 0 else "por debajo"))
        text = "Píxel ({}, {}): R {} G {} B {} → valor {} · corte {} → {} ({})".format(
            X, Y, rgb[0], rgb[1], rgb[2], val, t, "CIELO" if is_sky else "DOSEL", rel)
        if self.valid_mask_full is not None:
            vm = self.valid_mask_full
            if vm.shape[:2] == (H, W) and not bool(vm[Y, X]):
                text += " · fuera de la máscara (no se analiza)"
        return text

    def leaveEvent(self, event):  # noqa: N802 (API de Qt)
        self.pixelInspected.emit("Inspector: mueva el puntero sobre la foto.")
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 (API de Qt)
        pos = event.position() if hasattr(event, "position") else event.pos()
        info = self.inspect_at(pos.x(), pos.y())
        self.pixelInspected.emit(info or "Inspector: mueva el puntero sobre la foto.")
        drag = getattr(self, "_drag", None)
        area = getattr(self, "scroll_area", None)
        if drag is not None and area is not None:
            gp = event.globalPosition() if hasattr(event, "globalPosition") else event.globalPos()
            area.horizontalScrollBar().setValue(int(drag[2] - (gp.x() - drag[0])))
            area.verticalScrollBar().setValue(int(drag[3] - (gp.y() - drag[1])))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 (API de Qt)
        if getattr(self, "_drag", None) is not None:
            self._drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _redraw(self):
        if self.display_pil is None or self.gray_array is None:
            self.setText("No hay ninguna imagen cargada.")
            self.setPixmap(QPixmap())
            return

        sky_mask = threshold_image(
            self.gray_array, self.threshold,
            sky_is_bright=self.sky_is_bright,
        )
        if self.apply_cleanup:
            sky_mask = clean_binary_mask(sky_mask, iterations=1)

        img_np = np.array(self.display_pil).astype(np.float32)

        if self.highlight_sky:
            # Modo Claro: tiñe los píxeles de cielo (claros)
            target_mask = sky_mask
            overlay_rgb = SKY_OVERLAY_COLOR
            a = self.overlay_alpha
        else:
            # Modo Oscuro / máscara inversa: tiñe el dosel (oscuros) de rojo intenso
            target_mask = ~sky_mask
            overlay_rgb = CANOPY_INVERSE_COLOR
            a = self.overlay_alpha

        for c in range(3):
            img_np[:, :, c] = np.where(
                target_mask,
                img_np[:, :, c] * (1.0 - a) + overlay_rgb[c] * a,
                img_np[:, :, c],
            )
        result = Image.fromarray(img_np.astype("uint8"), "RGB")

        dw, dh = result.size
        if self.zoom != 1.0:
            zw = max(1, int(dw * self.zoom))
            zh = max(1, int(dh * self.zoom))
            interp = Image.NEAREST if self.zoom > 1.0 else Image.LANCZOS
            result = result.resize((zw, zh), interp)

        result_np = np.ascontiguousarray(np.array(result))
        rh, rw = result_np.shape[:2]
        qimg = QImage(result_np.data, rw, rh, rw * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self.setPixmap(pixmap)
        self.setMinimumSize(rw, rh)      # barras de desplazamiento cuando la imagen supera la ventana
        self.resize(rw, rh)

    def get_statistics(self):
        if self.gray_array is None:
            return 0, 0.0, 0, 0.0, 0

        sky_mask = threshold_image(
            self.gray_array, self.threshold,
            sky_is_bright=self.sky_is_bright,
        )
        if self.apply_cleanup:
            sky_mask = clean_binary_mask(sky_mask, iterations=1)

        if self.valid_mask is not None:
            total = int(self.valid_mask.sum())
            n_sky = int((sky_mask & self.valid_mask).sum())
        else:
            total = int(sky_mask.size)
            n_sky = int(sky_mask.sum())
        n_canopy = total - n_sky
        sky_pct = 100.0 * n_sky / total if total > 0 else 0.0
        canopy_pct = 100.0 - sky_pct
        return n_sky, sky_pct, n_canopy, canopy_pct, total


class ThresholdDialog(QDialog):
    """Diálogo interactivo de umbralización con vista previa en vivo estilo GLAMA."""

    def __init__(self, pil_image, gray_array=None,
                 initial_threshold=128,
                 initial_sky_bright=True,
                 initial_cleanup=True,
                 initial_channel="blue_red",
                 parent=None,
                 valid_mask=None):
        super().__init__(parent)
        self.setWindowTitle(
            "CobDosel — Definir área de cielo y nivel de corte (vista previa en vivo)"
        )
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumSize(520, 460)
        self.resize(1100, 860)
        self.setSizeGripEnabled(True)

        self.pil_image = pil_image
        self.gray_array = gray_array
        self._initial_channel = initial_channel

        self._build_ui()

        init_t = max(1, min(254, int(initial_threshold)))
        self.threshold_slider.setValue(init_t)
        self.sky_bright_check.setChecked(initial_sky_bright)
        self.cleanup_check.setChecked(initial_cleanup)

        for i in range(self.channel_combo.count()):
            if self.channel_combo.itemData(i) == initial_channel:
                self.channel_combo.setCurrentIndex(i)
                break

        self.canvas.set_image(pil_image, gray_array, valid_mask=valid_mask)
        self.canvas.set_threshold(init_t)
        self.canvas.set_sky_bright(initial_sky_bright)
        self.histogram_widget.set_sky_bright(initial_sky_bright)
        self.canvas.set_cleanup(initial_cleanup)

        self._compute_histogram()
        self._update_stats()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Ajuste el control deslizante o arrastre directamente la línea roja en el histograma.\n"
            "• Modo «Claro (resaltar cielo)»: tiñe los píxeles de cielo; sirve para ver si el corte es demasiado alto "
            "(cielo abierto sin teñir).\n"
            "• Modo «Oscuro (máscara inversa del dosel)»: tiñe la vegetación; sirve para ver si el corte es demasiado "
            "bajo (hojas o ramas en blanco).\n"
            "Los píxeles claros sin teñir en el modo Claro, en bordes de claros y ramillas, son píxeles mixtos "
            "(parte cielo, parte dosel) por debajo del corte: cuentan como dosel."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        top_opts_row = QHBoxLayout()
        top_opts_row.addWidget(QLabel("Canales de color:"))
        self.channel_combo = QComboBox()
        for code, label in CHANNEL_MODES:
            self.channel_combo.addItem(label, userData=code)
        top_opts_row.addWidget(self.channel_combo, stretch=1)

        top_opts_row.addSpacing(16)
        top_opts_row.addWidget(QLabel("Modo de máscara:"))
        self.radio_light = QRadioButton("Claro (resaltar cielo)")
        self.radio_light.setChecked(True)
        self.radio_dark = QRadioButton("Oscuro (máscara inversa del dosel)")
        self.mask_btn_group = QButtonGroup(self)
        self.mask_btn_group.addButton(self.radio_light)
        self.mask_btn_group.addButton(self.radio_dark)
        top_opts_row.addWidget(self.radio_light)
        top_opts_row.addWidget(self.radio_dark)
        top_opts_row.addWidget(QLabel("Opacidad:"))
        self.alpha_spin = QSpinBox()
        self.alpha_spin.setRange(10, 100)
        self.alpha_spin.setSingleStep(5)
        self.alpha_spin.setValue(int(round(OVERLAY_ALPHA * 100)))
        self.alpha_spin.setSuffix(" %")
        self.alpha_spin.setToolTip("Opacidad del color superpuesto, la misma en Claro (cielo) y Oscuro (dosel).")
        top_opts_row.addWidget(self.alpha_spin)

        layout.addLayout(top_opts_row)

        hist_group = QGroupBox(
            "Histograma de intensidad de píxeles (clic/arrastre para mover el nivel de corte)"
        )
        hist_layout = QVBoxLayout(hist_group)

        self.histogram_widget = HistogramWidget()
        hist_layout.addWidget(self.histogram_widget)

        slider_row = QHBoxLayout()

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(1, 254)
        self.threshold_slider.setValue(128)
        slider_row.addWidget(self.threshold_slider, stretch=1)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 254)
        self.threshold_spin.setValue(128)
        slider_row.addWidget(self.threshold_spin)

        slider_row.addWidget(QLabel("Automático:"))
        self.auto_method_combo = QComboBox()
        for code, label in AUTO_THRESHOLD_METHODS:
            self.auto_method_combo.addItem(label, userData=code)
        self.auto_method_combo.setToolTip(
            "Otsu (1979): maximiza la varianza entre clases.\n"
            "Mínimo (Prewitt y Mendelsohn 1966): corta en el mínimo entre los modos de dosel y\n"
            "cielo del histograma suavizado; si no hay dos modos se usa Otsu.")
        slider_row.addWidget(self.auto_method_combo)
        self.otsu_btn = QPushButton("Calcular")
        self.otsu_btn.setToolTip("Calcular el nivel de corte con el método automático elegido.")
        slider_row.addWidget(self.otsu_btn)

        hist_layout.addLayout(slider_row)
        layout.addWidget(hist_group)

        options_row = QHBoxLayout()

        self.sky_bright_check = QCheckBox("El cielo es más brillante que el dosel")
        self.sky_bright_check.setChecked(True)
        options_row.addWidget(self.sky_bright_check)

        self.cleanup_check = QCheckBox("Aplicar limpieza morfológica")
        self.cleanup_check.setChecked(True)
        options_row.addWidget(self.cleanup_check)

        options_row.addStretch()
        options_row.addWidget(QLabel("Zoom:"))

        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setMaximumWidth(40)
        options_row.addWidget(self.zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        options_row.addWidget(self.zoom_label)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setMaximumWidth(40)
        options_row.addWidget(self.zoom_in_btn)

        self.zoom_fit_btn = QPushButton("Ajustar")
        options_row.addWidget(self.zoom_fit_btn)
        options_row.addWidget(QLabel("(rueda = zoom · arrastrar = mover)"))

        layout.addLayout(options_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.canvas = ThresholdPreviewCanvas(self)
        self.canvas.scroll_area = self.scroll
        self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        self.canvas.setToolTip("Rueda del ratón: acercar / alejar · Arrastrar: mover la imagen")
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, stretch=1)

        self.pixel_label = QLabel("Inspector: mueva el puntero sobre la foto.")
        self.pixel_label.setStyleSheet("font-family: monospace;")
        self.pixel_label.setToolTip(
            "Valor del píxel bajo el puntero (foto a resolución completa, canal elegido) frente al nivel\n"
            "de corte: indica si cuenta como cielo o dosel y a cuántas unidades está del corte.")
        layout.addWidget(self.pixel_label)
        self.canvas.pixelInspected.connect(self.pixel_label.setText)

        self.stats_label = QLabel("—")
        self.stats_label.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.stats_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.apply_btn = QPushButton("Aplicar nivel de corte")
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setDefault(True)
        btn_row.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

        # Conectar señales únicamente después de haber creado todos los widgets
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        self.radio_light.toggled.connect(self._on_highlight_mode_toggled)
        self.histogram_widget.thresholdDragged.connect(
            self.threshold_slider.setValue
        )
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self.threshold_spin.valueChanged.connect(self._on_threshold_spin_changed)
        self.otsu_btn.clicked.connect(self._on_otsu)
        self.sky_bright_check.toggled.connect(self._on_sky_bright_toggled)
        self.cleanup_check.toggled.connect(self._on_cleanup_toggled)
        self.alpha_spin.valueChanged.connect(lambda v: self.canvas.set_overlay_alpha(v / 100.0))
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        self.zoom_fit_btn.clicked.connect(self._on_zoom_fit)
        self.canvas.zoomChanged.connect(lambda _: self._update_zoom_label())

    def _compute_histogram(self):
        if self.canvas.gray_array is None:
            return
        if self.canvas.valid_mask is not None:
            flat = self.canvas.gray_array[self.canvas.valid_mask]
        else:
            flat = self.canvas.gray_array.ravel()
        if flat.size > 2_000_000:
            step = flat.size // 2_000_000
            sample = flat[::step]
        else:
            sample = flat
        hist = np.bincount(sample.astype(np.uint8), minlength=256)
        self.histogram_widget.set_histogram(hist)
        self.histogram_widget.set_threshold(self.threshold_slider.value())

    def _on_channel_changed(self, idx):
        mode = self.channel_combo.itemData(idx)
        self.canvas.set_channel_mode(mode)
        self._compute_histogram()
        self._update_stats()

    def _on_highlight_mode_toggled(self, checked):
        self.canvas.set_highlight_sky(self.radio_light.isChecked())

    def _on_threshold_changed(self, value):
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(value)
        self.threshold_spin.blockSignals(False)
        self.histogram_widget.set_threshold(value)
        self.canvas.set_threshold(value)
        self._update_stats()

    def _on_threshold_spin_changed(self, value):
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(value)
        self.threshold_slider.blockSignals(False)
        self.histogram_widget.set_threshold(value)
        self.canvas.set_threshold(value)
        self._update_stats()

    def _on_sky_bright_toggled(self, checked):
        self.canvas.set_sky_bright(checked)
        self.histogram_widget.set_sky_bright(checked)
        self._update_stats()

    def _on_cleanup_toggled(self, checked):
        self.canvas.set_cleanup(checked)
        self._update_stats()

    def _on_otsu(self):
        """Nivel de corte automático con el método elegido (Otsu o Mínimo)."""
        if self.canvas.gray_array is None:
            return
        method = self.auto_method_combo.currentData() or "otsu"
        t, used, note = compute_auto_threshold(self.canvas.gray_array, self.canvas.valid_mask, method)
        self.last_auto = ("automático: " + AUTO_THRESHOLD_LABELS.get(used, used), int(t))
        self.threshold_slider.setValue(t)
        if note:
            QMessageBox.information(self, "Nivel de corte automático", note)

    def _on_zoom_in(self):
        self.canvas.set_zoom(self.canvas.zoom * 1.25)
        self._update_zoom_label()

    def _on_zoom_out(self):
        self.canvas.set_zoom(self.canvas.zoom / 1.25)
        self._update_zoom_label()

    def _on_zoom_fit(self):
        vp = self.scroll.viewport()
        self.canvas.fit_to_viewport(vp.width(), vp.height())
        self._update_zoom_label()

    def _update_zoom_label(self):
        self.zoom_label.setText("{:.0f}%".format(self.canvas.zoom * 100))

    def _update_stats(self):
        n_sky, sky_pct, n_canopy, canopy_pct, total = self.canvas.get_statistics()
        if total == 0:
            self.stats_label.setText("—")
            return
        self.stats_label.setText(
            "Píxeles claros / blancos (cielo): {} px ({:.2f}%)   |   "
            "Píxeles oscuros / negros (dosel): {} px ({:.2f}%)   |   "
            "Total área válida (vista previa): {} px".format(
                fmt_int(n_sky), sky_pct, fmt_int(n_canopy), canopy_pct, fmt_int(total)
            )
        )

    def get_threshold(self):
        return self.threshold_slider.value()

    def get_sky_bright(self):
        return self.sky_bright_check.isChecked()

    def get_cleanup(self):
        return self.cleanup_check.isChecked()

    def get_channel(self):
        return self.channel_combo.currentData()
