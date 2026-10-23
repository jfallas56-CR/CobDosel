"""Ventana «Revisar cortes» del procesamiento por sitio de CobDosel.

Revisión visual del nivel de corte de cada foto, como la pantalla de nivel de corte de GLAMA: foto con
el cielo en naranja y la zona enmascarada en verde azulado, zoom con la rueda del ratón, histograma con
el corte, control deslizante y CaCo aproximado en vivo. El operador acepta, ajusta o excluye cada
foto; las decisiones se devuelven para guardarlas junto a las fotos (CobDosel_revision_cortes.json).

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import datetime
import math
import os

import numpy as np

from qgis.PyQt.QtCore import Qt, QTimer, QRectF, QRect, QPoint, QSize, pyqtSignal
from qgis.PyQt.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QCheckBox, QLineEdit,
    QGraphicsView, QGraphicsScene, QWidget, QMessageBox, QFormLayout, QSizePolicy, QRubberBand,
)

from .exif_gps import load_oriented_rgb_image
from .lens_calibration import scale_calibration_to_image
from .canopy_analysis import extract_channel, compute_radius_grid, compute_zenith_grid, threshold_image
from .glama_engine import glama_ring_counts, glama_indices
from .visualization import SKY_OVERLAY_DEFAULT_COLOR, SKY_OVERLAY_DEFAULT_ALPHA, GLAMA_TEAL, GLAMA_TEAL_LINE

VIEW_MAX_DIM = 1600


def _qimage_from_rgb(arr):
    arr = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = arr.shape[:2]
    fmt = getattr(QImage, "Format_RGB888", None) or QImage.Format.Format_RGB888
    img = QImage(arr.data, w, h, 3 * w, fmt)
    return img.copy()


class _ZoomView(QGraphicsView):
    """
    Vista con zoom (rueda del ratón, centrado en el puntero) y desplazamiento arrastrando.
    0.14.33: rectángulo de zoom con el botón derecho (o Mayús + izquierdo) y zoom fijable en %.
    """

    zoomChanged = pyqtSignal(float)
    MIN_SCALE, MAX_SCALE = 0.05, 8.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._item = None
        drag = getattr(QGraphicsView, "ScrollHandDrag", None) or QGraphicsView.DragMode.ScrollHandDrag
        self.setDragMode(drag)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._band = None
        self._band_origin = None

    def set_pixmap(self, pix, keep_view=False):
        if self._item is None:
            self._item = self.scene().addPixmap(pix)
            self.fit()
        else:
            self._item.setPixmap(pix)
            if not keep_view:
                self.fit()
        self.scene().setSceneRect(QRectF(pix.rect()))

    def current_scale(self):
        return float(self.transform().m11())

    def fit(self):
        if self._item is not None:
            mode = getattr(Qt, "KeepAspectRatio", None) or Qt.AspectRatioMode.KeepAspectRatio
            self.fitInView(self._item, mode)
            self.zoomChanged.emit(self.current_scale())

    def zoom(self, factor, at_center=True):
        new = max(self.MIN_SCALE, min(self.MAX_SCALE, self.current_scale() * factor))
        factor = new / self.current_scale()
        if at_center:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoomChanged.emit(self.current_scale())

    def set_scale(self, scale):
        """Escala absoluta (1.0 = 100 % de la vista previa), manteniendo el centro."""
        cur = self.current_scale()
        if cur > 0:
            self.zoom(float(scale) / cur, at_center=True)

    def zoom_to_rect(self, view_rect):
        """Amplía para que el rectángulo dibujado (coordenadas de la ventana) la llene."""
        if self._item is None or view_rect.width() < 6 or view_rect.height() < 6:
            return
        scene_rect = self.mapToScene(view_rect).boundingRect()
        mode = getattr(Qt, "KeepAspectRatio", None) or Qt.AspectRatioMode.KeepAspectRatio
        self.fitInView(scene_rect, mode)
        if self.current_scale() > self.MAX_SCALE:
            self.set_scale(self.MAX_SCALE)
        self.centerOn(scene_rect.center())
        self.zoomChanged.emit(self.current_scale())

    def wheelEvent(self, event):  # noqa: N802 (API de Qt)
        self.zoom(1.25 if event.angleDelta().y() > 0 else 0.8, at_center=False)

    def mousePressEvent(self, event):  # noqa: N802 (API de Qt)
        btn = event.button()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if btn == Qt.MouseButton.RightButton or (btn == Qt.MouseButton.LeftButton and shift):
            p = event.position() if hasattr(event, "position") else event.pos()
            self._band_origin = QPoint(int(p.x()), int(p.y()))
            if self._band is None:
                self._band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
            self._band.setGeometry(QRect(self._band_origin, QSize()))
            self._band.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 (API de Qt)
        if self._band_origin is not None:
            p = event.position() if hasattr(event, "position") else event.pos()
            self._band.setGeometry(QRect(self._band_origin, QPoint(int(p.x()), int(p.y()))).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 (API de Qt)
        if self._band_origin is not None:
            p = event.position() if hasattr(event, "position") else event.pos()
            rect = QRect(self._band_origin, QPoint(int(p.x()), int(p.y()))).normalized()
            self._band_origin = None
            self._band.hide()
            self.zoom_to_rect(rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _HistogramWidget(QWidget):
    """Histograma de la foto (escala raíz cuadrada para ver las colas) con el corte y el corte automático."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hist = None
        self.cut = None
        self.auto_cut = None
        self.setMinimumHeight(110)

    def set_data(self, hist, cut, auto_cut):
        self.hist, self.cut, self.auto_cut = hist, cut, auto_cut
        self.update()

    def paintEvent(self, _event):  # noqa: N802 (API de Qt)
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(255, 255, 255))
        if self.hist is None:
            p.end()
            return
        v = np.sqrt(np.asarray(self.hist, dtype=np.float64))
        vmax = float(v.max()) or 1.0
        bw = w / 256.0
        for i in range(256):
            bh = (h - 14) * v[i] / vmax
            p.fillRect(int(i * bw), int(h - 14 - bh), max(1, int(math.ceil(bw))), int(bh), QColor(110, 40, 160))
        if self.auto_cut is not None:
            pen = QPen(QColor(30, 90, 200))
            pen.setStyle(getattr(Qt, "DashLine", None) or Qt.PenStyle.DashLine)
            pen.setWidth(2)
            p.setPen(pen)
            x = int((self.auto_cut + 0.5) * bw)
            p.drawLine(x, 0, x, h - 14)
        if self.cut is not None:
            pen = QPen(QColor(220, 30, 30))
            pen.setWidth(2)
            p.setPen(pen)
            x = int((self.cut + 0.5) * bw)
            p.drawLine(x, 0, x, h - 14)
        p.setPen(QColor(40, 40, 40))
        p.drawText(2, h - 2, "0")
        p.drawText(w - 30, h - 2, "255")
        p.drawText(int(w / 2) - 190, h - 2, "rojo = corte · azul discontinuo = automático · escala raíz cuadrada")
        p.end()


class CutReviewDialog(QDialog):
    """Revisión visual de los cortes de las fotos de un lote."""

    def __init__(self, items, folder, calibration, channel_mode, decisions=None, sky_is_bright=True,
                 operator="", parent=None, title_suffix=""):
        """
        items: fotos del lote (dicts con archivo, parcela, punto, corte, corte_auto, revisar,
        motivo_revision, cenit_max, decision). decisions: decisiones previas {archivo: {...}}.
        """
        super().__init__(parent)
        self.setWindowTitle("CobDosel — Revisar cortes" + title_suffix)
        self.resize(1100, 860)
        self.items = [it for it in items if it.get("archivo") and it.get("cenit_max") is not None]
        self.folder = folder
        self.calibration = calibration
        self.channel_mode = channel_mode
        self.sky_is_bright = sky_is_bright
        self.decisions = {k: dict(v) for k, v in (decisions or {}).items()}
        self.idx = 0
        self._cache = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._render)

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.info = QLabel("")
        self.info.setWordWrap(True)
        top.addWidget(self.info, 1)
        self.only_flagged = QCheckBox("Solo fotos a revisar")
        self.only_flagged.toggled.connect(self._on_filter)
        top.addWidget(self.only_flagged)
        lay.addLayout(top)

        self.view = _ZoomView(self)
        lay.addWidget(self.view, 1)
        zr = QHBoxLayout()
        for txt, f in (("Acercar +", 1.25), ("Alejar −", 0.8)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, _f=f: self.view.zoom(_f))
            zr.addWidget(b)
        bfit = QPushButton("Ajustar a la ventana")
        bfit.clicked.connect(self.view.fit)
        zr.addWidget(bfit)
        zr.addWidget(QLabel("Zoom:"))
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(int(_ZoomView.MIN_SCALE * 100), int(_ZoomView.MAX_SCALE * 100))
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setSingleStep(25)
        self.zoom_spin.setKeyboardTracking(False)
        self.zoom_spin.setToolTip("Zoom de la vista (100 % = vista previa de hasta {} px de lado).\n"
                                  "Escriba un valor y pulse Intro. Clic derecho y arrastrar (o Mayús +\n"
                                  "arrastrar) = ampliar la zona del rectángulo.".format(VIEW_MAX_DIM))
        self.zoom_spin.valueChanged.connect(lambda v: self.view.set_scale(v / 100.0)
                                            if abs(v / 100.0 - self.view.current_scale()) >= 0.005 else None)
        self.view.zoomChanged.connect(self._sync_zoom_spin)
        zr.addWidget(self.zoom_spin)
        zr.addWidget(QLabel("(rueda = zoom · arrastrar = mover · clic derecho y arrastrar = ampliar zona)"))
        zr.addStretch(1)
        self.caco_label = QLabel("")
        zr.addWidget(self.caco_label)
        lay.addLayout(zr)

        self.hist = _HistogramWidget(self)
        lay.addWidget(self.hist)
        sr = QHBoxLayout()
        self.slider = QSlider(getattr(Qt, "Horizontal", None) or Qt.Orientation.Horizontal)
        self.slider.setRange(1, 254)
        self.spin = QSpinBox()
        self.spin.setRange(1, 254)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(lambda _v: self._timer.start())
        sr.addWidget(QLabel("Nivel de corte:"))
        sr.addWidget(self.slider, 1)
        sr.addWidget(self.spin)
        lay.addLayout(sr)

        form = QFormLayout()
        self.operator_edit = QLineEdit(operator)
        self.operator_edit.setPlaceholderText("opcional")
        form.addRow("Operador:", self.operator_edit)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("opcional (p. ej. «tronco cercano», «sol directo»)")
        form.addRow("Nota de esta foto:", self.note_edit)
        lay.addLayout(form)

        br = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Anterior")
        self.prev_btn.clicked.connect(lambda: self._move(-1))
        self.reset_btn = QPushButton("Restablecer automático")
        self.reset_btn.clicked.connect(self._on_reset)
        self.accept_btn = QPushButton("Aceptar corte")
        self.accept_btn.setToolTip("Registra el corte actual: «aceptado» si es el automático, «ajustado» si se movió.")
        self.accept_btn.clicked.connect(self._on_accept)
        self.exclude_btn = QPushButton("Excluir foto")
        self.exclude_btn.clicked.connect(self._on_exclude)
        self.next_btn = QPushButton("Siguiente ▶")
        self.next_btn.clicked.connect(lambda: self._move(1))
        for b in (self.prev_btn, self.reset_btn, self.accept_btn, self.exclude_btn, self.next_btn):
            br.addWidget(b)
        lay.addLayout(br)
        fr = QHBoxLayout()
        self.accept_all_btn = QPushButton("Aceptar todas las automáticas sin revisar")
        self.accept_all_btn.setToolTip("Registra como «revisadas sin cambio» las fotos con corte automático válido "
                                       "que aún no tienen decisión.")
        self.accept_all_btn.clicked.connect(self._on_accept_all)
        fr.addWidget(self.accept_all_btn)
        fr.addStretch(1)
        self.done_btn = QPushButton("Terminar y recalcular")
        self.done_btn.clicked.connect(self._on_done)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        fr.addWidget(self.done_btn)
        fr.addWidget(cancel)
        lay.addLayout(fr)

        if not self.items:
            self.info.setText("No hay fotos para revisar.")
            for b in (self.prev_btn, self.reset_btn, self.accept_btn, self.exclude_btn, self.next_btn):
                b.setEnabled(False)
        else:
            first = next((i for i, it in enumerate(self.items) if self._pending(it)), 0)
            self._load(first)

    # ------------------------------------------------------------------
    def _pending(self, it):
        return bool(it.get("revisar")) and it["archivo"] not in self.decisions

    def _visible_indices(self):
        if self.only_flagged.isChecked():
            return [i for i, it in enumerate(self.items) if it.get("revisar")]
        return list(range(len(self.items)))

    def _sync_zoom_spin(self, scale):
        self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(int(round(scale * 100)))
        self.zoom_spin.blockSignals(False)

    def _on_filter(self, *_a):
        vis = self._visible_indices()
        if vis and self.idx not in vis:
            self._load(vis[0])

    def _move(self, step):
        vis = self._visible_indices()
        if not vis:
            return
        pos = vis.index(self.idx) if self.idx in vis else 0
        self._load(vis[(pos + step) % len(vis)])

    def _status_text(self, it):
        dec = self.decisions.get(it["archivo"])
        if dec:
            if dec["decision"] == "excluido":
                return "EXCLUIDA por el operador"
            return "{} (corte {})".format("revisada sin cambio" if dec["decision"] == "aceptado" else "AJUSTADA",
                                          dec["corte"])
        if it.get("revisar"):
            return "A REVISAR — " + (it.get("motivo_revision") or "")
        return "automático (método comprobado)"

    def _load(self, i):
        self.idx = i
        it = self.items[i]
        path = os.path.join(self.folder, it["archivo"])
        img, _s, _o = load_oriented_rgb_image(path, max_dim=VIEW_MAX_DIM)
        arr = np.asarray(img.convert("RGB"))
        h, w = arr.shape[:2]
        cal = scale_calibration_to_image(self.calibration, w, h)
        c = (w / 2.0, h / 2.0)
        zen = compute_zenith_grid(compute_radius_grid((h, w), c), cal)
        inside = zen <= float(it["cenit_max"])
        gray = extract_channel(arr, self.channel_mode)
        hist = np.bincount(gray[inside].astype(np.int64).ravel(), minlength=256)[:256]
        yy, xx = np.ogrid[0:h, 0:w]
        ang = np.degrees(np.arctan2(xx - c[0], -(yy - c[1]))) % 3.0
        spokes = (~inside) & (ang < 0.25)
        base = arr.astype(np.float32)
        a = 0.85
        teal = np.array(GLAMA_TEAL, np.float32)
        base[~inside] = base[~inside] * (1 - a) + teal * a
        base[spokes] = np.array(GLAMA_TEAL_LINE, np.float32)
        self._cache = {"arr": arr, "base": base, "gray": gray, "inside": inside, "hist": hist, "cal": cal,
                       "c": c, "R": cal.get("virtual_radius_px"), "proj": cal.get("projection", "polar"),
                       "zmax": float(it["cenit_max"])}
        dec = self.decisions.get(it["archivo"])
        cut = int(dec["corte"]) if dec and dec.get("corte") else int(it.get("corte_auto") or it.get("corte") or 128)
        self.note_edit.setText(dec.get("nota", "") if dec else "")
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(cut)
        self.slider.setValue(cut)
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        vis = self._visible_indices()
        self.info.setText("<b>Foto {} de {}</b> — parcela {} · {} · {}<br/>Estado: {}<br/>Corte automático: {}".format(
            (vis.index(i) + 1) if i in vis else i + 1, len(vis) if vis else len(self.items), it.get("parcela"),
            it.get("punto"), it["archivo"], self._status_text(it),
            it.get("corte_auto") if it.get("corte_auto") is not None else "— (sin recomendación)"))
        self._render(fit=True)

    def _render(self, fit=False):
        if self._cache is None:
            return
        k = self._cache
        cut = int(self.spin.value())
        sky = threshold_image(k["gray"], cut, sky_is_bright=self.sky_is_bright) & k["inside"]
        out = k["base"].copy()
        col = np.array(SKY_OVERLAY_DEFAULT_COLOR, np.float32)
        a = SKY_OVERLAY_DEFAULT_ALPHA
        out[sky] = out[sky] * (1 - a) + col * a
        self.view.set_pixmap(QPixmap.fromImage(_qimage_from_rgb(np.clip(out, 0, 255))), keep_view=not fit)
        auto = self.items[self.idx].get("corte_auto")
        self.hist.set_data(k["hist"], cut, auto)
        try:
            counts = glama_ring_counts(threshold_image(k["gray"], cut, sky_is_bright=self.sky_is_bright),
                                       k["c"], k["R"], k["zmax"], calibration=k["cal"], projection=k["proj"])
            caco = glama_indices(counts, calibration=k["cal"], radius_px=k["R"])["canopy_cover_index_pct"]
            sky_pct = 100.0 * float(k["hist"][cut:].sum()) / max(float(k["hist"].sum()), 1.0)
            self.caco_label.setText("CaCo de esta foto ≈ {:.2f} % · píxeles claros {:.1f} % "
                                    "(vista reducida; el lote recalcula a resolución completa)".format(caco, sky_pct))
        except Exception as e:      # la vista no debe impedir la revisión
            self.caco_label.setText("CaCo no disponible: {}".format(e))

    # ------------------------------------------------------------------
    def _record(self, decision, cut=None):
        it = self.items[self.idx]
        self.decisions[it["archivo"]] = {
            "decision": decision, "corte": int(cut) if cut is not None else None,
            "corte_auto": it.get("corte_auto"), "operador": self.operator_edit.text().strip(),
            "nota": self.note_edit.text().strip(), "canal": self.channel_mode,
            "parcela": it.get("parcela"), "punto": it.get("punto"),
            "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    def _on_accept(self):
        it = self.items[self.idx]
        cut = int(self.spin.value())
        self._record("aceptado" if it.get("corte_auto") == cut else "ajustado", cut)
        self._load(self.idx)
        self._advance_to_next_pending()

    def _on_exclude(self):
        self._record("excluido", None)
        self._load(self.idx)
        self._advance_to_next_pending()

    def _on_reset(self):
        it = self.items[self.idx]
        self.decisions.pop(it["archivo"], None)
        self._load(self.idx)

    def _advance_to_next_pending(self):
        n = len(self.items)
        for step in range(1, n + 1):
            j = (self.idx + step) % n
            if self._pending(self.items[j]):
                self._load(j)
                return
        vis = self._visible_indices()
        if self.idx in vis and vis.index(self.idx) + 1 < len(vis):
            self._load(vis[vis.index(self.idx) + 1])

    def _on_accept_all(self):
        n = 0
        keep = self.idx
        for i, it in enumerate(self.items):
            if not it.get("revisar") and it["archivo"] not in self.decisions and it.get("corte_auto") is not None:
                self.idx = i
                self._record("aceptado", it["corte_auto"])
                n += 1
        self.idx = keep
        self._load(keep)
        QMessageBox.information(self, "Revisión", "{} fotos registradas como revisadas sin cambio.".format(n))

    def pending_count(self):
        return sum(1 for it in self.items if self._pending(it))

    def _on_done(self):
        n = self.pending_count()
        if n:
            ans = QMessageBox.question(
                self, "Fotos sin revisar",
                "Quedan {} foto(s) marcadas «a revisar» sin decisión. El resultado del sitio será provisional.\n\n"
                "¿Terminar de todos modos?".format(n),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def get_decisions(self):
        return {k: dict(v) for k, v in self.decisions.items()}

    def operator(self):
        return self.operator_edit.text().strip()
