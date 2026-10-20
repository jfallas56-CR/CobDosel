"""Diálogo «Procesamiento por sitio (lote)» de CobDosel.

Procesa todas las fotos de un sitio con una configuración fija: calibración guardada, máscara
(fija, 60° por defecto; u opcional desde la altura de un grupo de dosel), canal, nivel de corte recomendado (log-normal; Otsu de respaldo)
y empareja cada foto con el formulario de fotos (ID de fotografía y hora de captura).
Resultado: media por parcela y media del sitio (Índice CaCo); CSV, HTML y capa.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import traceback

import re
import webbrowser

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QGroupBox, QFileDialog, QMessageBox, QProgressBar, QTextEdit,
    QApplication, QRadioButton, QInputDialog,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsField

from ._version import VERSION, fmt_num
from .calibration_store import list_calibrations, load_calibration, save_calibration
from .camera_check import camera_label
from .canopy_analysis import CHANNEL_MODES
from . import batch_core as bc

try:
    from qgis.core import Qgis
    _NEW_TYPES = getattr(Qgis, "QGIS_VERSION_INT", 0) >= 33800
except ImportError:  # pragma: no cover
    _NEW_TYPES = False
if _NEW_TYPES:
    from qgis.PyQt.QtCore import QMetaType
    _STR, _FLOAT, _INT = QMetaType.Type.QString, QMetaType.Type.Double, QMetaType.Type.Int
else:
    from qgis.PyQt.QtCore import QVariant
    _STR, _FLOAT, _INT = QVariant.String, QVariant.Double, QVariant.Int


def _exec(dlg):
    runner = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
    return runner()


class CobDoselBatchDialog(QDialog):
    """Procesamiento de un sitio completo (parcelas × 5 fotos)."""

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.batch = None
        self._last_cal = None
        self.setWindowTitle("CobDosel v{} — Procesamiento por sitio (lote)".format(VERSION))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(900, 760)
        self.setSizeGripEnabled(True)
        self._build()
        self._refresh_calibrations()
        self.group_combo.setCurrentIndex(self.group_combo.findData(4))
        self._on_mask_mode()

    # ------------------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout(self)

        g1 = QGroupBox("1. Datos del sitio")
        f1 = QFormLayout(g1)
        self.site_edit = QLineEdit()
        self.site_edit.setPlaceholderText("Nombre o código del sitio")
        f1.addRow("Sitio:", self.site_edit)
        self.folder_edit = QLineEdit()
        b = QPushButton("Examinar…")
        b.clicked.connect(self._pick_folder)
        r = QHBoxLayout()
        r.addWidget(self.folder_edit, 1)
        r.addWidget(b)
        f1.addRow("Carpeta de fotos:", r)
        self.form_edit = QLineEdit()
        b2 = QPushButton("Examinar…")
        b2.clicked.connect(self._pick_form)
        r2 = QHBoxLayout()
        r2.addWidget(self.form_edit, 1)
        r2.addWidget(b2)
        b_tpl = QPushButton("Guardar plantilla…")
        b_tpl.setToolTip("Guardar una copia vacía de la plantilla del formulario de fotos (Excel).")
        b_tpl.clicked.connect(self._save_template)
        r2.addWidget(b_tpl)
        b_draft = QPushButton("Crear formulario desde las fotos…")
        b_draft.setToolTip(
            "Crea el formulario con todas las fotos de la carpeta ordenadas por hora (ID de fotografía y\n"
            "hora ya escritos) y asigna parcela y punto por orden. Revíselo antes de procesar.")
        b_draft.clicked.connect(self._draft_form)
        r2.addWidget(b_draft)
        f1.addRow("Formulario de fotos (CSV / Excel):", r2)
        self.planned_spin = QSpinBox()
        self.planned_spin.setRange(0, 999)
        self.planned_spin.setValue(0)
        self.planned_spin.setSpecialValueText("— indique —")
        self.planned_spin.setToolTip("Número de parcelas planificadas para el sitio (depende del área).")
        f1.addRow("N.º de parcelas planificadas:", self.planned_spin)
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.0, 100000.0)
        self.area_spin.setDecimals(2)
        self.area_spin.setSuffix(" ha")
        self.area_spin.setSpecialValueText("(opcional)")
        f1.addRow("Área del AOI:", self.area_spin)
        lay.addWidget(g1)

        g2 = QGroupBox("2. Configuración del análisis (igual para todas las fotos)")
        f2 = QFormLayout(g2)
        self.cal_combo = QComboBox()
        rc = QHBoxLayout()
        rc.addWidget(self.cal_combo, 1)
        b3 = QPushButton("Actualizar")
        b3.clicked.connect(self._refresh_calibrations)
        rc.addWidget(b3)
        self.cam_btn = QPushButton("Registrar cámara…")
        self.cam_btn.setToolTip(
            "Para calibraciones guardadas antes de 0.12.4: registra en la calibración la cámara (EXIF) de las\n"
            "fotos de la carpeta. Úselo solo si la calibración se hizo con esa misma cámara y lente.")
        self.cam_btn.clicked.connect(self._register_camera)
        rc.addWidget(self.cam_btn)
        f2.addRow("Calibración guardada:", rc)
        self.cal_info = QLabel("")
        self.cal_info.setWordWrap(True)
        self.cal_info.setToolTip("Las calibraciones se crean en el diálogo principal de CobDosel: calibre con una\n"
                                 "foto de la misma cámara y pulse «Guardar calibración».")
        f2.addRow("", self.cal_info)
        self.cal_combo.currentIndexChanged.connect(self._on_cal_changed)
        self.channel_combo = QComboBox()
        for code, label in CHANNEL_MODES:
            self.channel_combo.addItem(label, userData=code)
        f2.addRow("Canal de color:", self.channel_combo)
        self.cut_label = QLabel("Recomendado (log-normal), iterado desde 128; Otsu si no hay recomendación")
        self.cut_label.setToolTip(
            "Cruce de dos distribuciones log-normales ajustadas a los modos oscuro (dosel) y claro (cielo)\n"
            "del histograma de cada foto. Implementación independiente del procedimiento de la app GLAMA\n"
            "(Tichý 2016), reconstruido a partir de la app y verificado con sus resultados. 128 es una convención\n"
            "de CobDosel (punto de partida de la búsqueda, que va en ambos sentidos), no el nivel de corte: cada\n"
            "foto obtiene el suyo. Se comprueba que el método funcionó; si no, la foto queda «a revisar».")
        f2.addRow("Nivel de corte:", self.cut_label)
        self.mask_fixed_radio = QRadioButton("Máscara fija (recomendada)")
        self.mask_height_radio = QRadioButton("Desde la altura del dosel")
        self.mask_fixed_radio.setChecked(True)
        self.mask_height_radio.toggled.connect(self._on_mask_mode)
        rm = QHBoxLayout()
        rm.addWidget(self.mask_fixed_radio)
        rm.addWidget(self.mask_height_radio)
        f2.addRow("Máscara de horizonte:", rm)
        self.fixed_mask_spin = QDoubleSpinBox()
        self.fixed_mask_spin.setRange(0.0, 85.0)
        self.fixed_mask_spin.setDecimals(1)
        self.fixed_mask_spin.setValue(bc.DEFAULT_MASK_DEG)
        self.fixed_mask_spin.setSuffix(" ° sobre el horizonte")
        self.fixed_mask_spin.setToolTip(
            "Máscara de horizonte. Tichý (2016) recomienda 60° (análisis hasta 30° del cenit)\n"
            "para CaCo y Modif. CaCo. Use el mismo valor en todos los sitios.")
        f2.addRow("Máscara fija:", self.fixed_mask_spin)
        self.group_combo = QComboBox()
        self.group_combo.addItem("Altura escrita a mano", userData=None)
        for code, gname, lo, hi in bc.CANOPY_GROUPS:
            if code < 3:
                continue                  # grupos 1–2 quedan por debajo o cerca de la cámara
            rng_txt = "> {:g} m".format(lo) if hi is None else "{:g} a < {:g} m".format(lo, hi)
            label = "{} {} ({}) → {:g} m".format(code, gname, rng_txt, bc.canopy_group_height(code))
            self.group_combo.addItem(label, userData=code)
        self.group_combo.setToolTip(
            "Grupo de dosel dominante del sitio (el protocolo no mide alturas). Se usa una altura de\n"
            "referencia: punto medio del grupo; 30 m para copas emergentes.")
        self.group_combo.currentIndexChanged.connect(self._on_group)
        f2.addRow("Grupo de dosel dominante:", self.group_combo)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(2.0, 80.0)
        self.height_spin.setDecimals(1)
        self.height_spin.setValue(bc.canopy_group_height(4))
        self.height_spin.setSuffix(" m")
        self.height_spin.setToolTip("Altura de referencia del dosel del sitio (estimada; no medida).")
        f2.addRow("Altura del dosel del sitio:", self.height_spin)
        self.cam_spin = QDoubleSpinBox()
        self.cam_spin.setRange(0.0, 5.0)
        self.cam_spin.setDecimals(2)
        self.cam_spin.setValue(bc.DEFAULT_CAMERA_HEIGHT_M)
        self.cam_spin.setSuffix(" m")
        f2.addRow("Altura de la cámara:", self.cam_spin)
        self.fp_spin = QDoubleSpinBox()
        self.fp_spin.setRange(0.5, 50.0)
        self.fp_spin.setDecimals(2)
        self.fp_spin.setValue(bc.DEFAULT_FOOTPRINT_M)
        self.fp_spin.setSuffix(" m")
        self.fp_spin.setToolTip(
            "Radio del dosel que cubre cada foto. 6.31 m = radio equivalente de un cuadrante de la\n"
            "parcela de 500 m² (5 fotos por parcela). 12.62 m = parcela completa.")
        f2.addRow("Radio de la huella por foto:", self.fp_spin)
        self.mask_info = QLabel("")
        f2.addRow("", self.mask_info)
        for w in (self.height_spin, self.cam_spin, self.fp_spin):
            w.valueChanged.connect(self._update_mask_info)
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(1.0, 3600.0)
        self.tol_spin.setDecimals(0)
        self.tol_spin.setValue(bc.DEFAULT_TOLERANCE_S)
        self.tol_spin.setSuffix(" s")
        f2.addRow("Tolerancia de hora:", self.tol_spin)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-86400.0, 86400.0)
        self.offset_spin.setDecimals(0)
        self.offset_spin.setSuffix(" s")
        self.offset_spin.setToolTip(
            "Se suma a la hora EXIF de cada foto (corrige el reloj de la cámara respecto del reloj\n"
            "con que se llenó el formulario; mídalo fotografiando un reloj de referencia).")
        f2.addRow("Desfase del reloj de la cámara:", self.offset_spin)
        lay.addWidget(g2)

        g3 = QGroupBox("3. Capa de parcelas (opcional, para el mapa)")
        f3 = QFormLayout(g3)
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._fill_fields)
        f3.addRow("Capa de puntos:", self.layer_combo)
        self.field_combo = QComboBox()
        f3.addRow("Campo ID de parcela:", self.field_combo)
        self._fill_layers()
        lay.addWidget(g3)

        rb = QHBoxLayout()
        self.run_btn = QPushButton("▶ Procesar sitio")
        self.run_btn.setStyleSheet("font-weight: bold; padding: 6px 12px;")
        self.run_btn.clicked.connect(self._on_run)
        rb.addWidget(self.run_btn)
        self.review_btn = QPushButton("Revisar cortes…")
        self.review_btn.setToolTip(
            "Revisión visual del nivel de corte de cada foto: aceptar, ajustar o\n"
            "excluir. Las fotos marcadas «a revisar» deben decidirse; las decisiones se guardan junto a las fotos.")
        self.review_btn.clicked.connect(self._on_review)
        self.review_btn.setEnabled(False)
        rb.addWidget(self.review_btn)
        self.csv_btn = QPushButton("Exportar CSV…")
        self.csv_btn.clicked.connect(self._on_csv)
        self.csv_btn.setEnabled(False)
        rb.addWidget(self.csv_btn)
        self.html_btn = QPushButton("Exportar informe HTML…")
        self.html_btn.clicked.connect(self._on_html)
        self.html_btn.setEnabled(False)
        rb.addWidget(self.html_btn)
        self.layer_btn = QPushButton("Añadir capa de parcelas")
        self.layer_btn.clicked.connect(self._on_layer)
        self.layer_btn.setEnabled(False)
        rb.addWidget(self.layer_btn)
        lay.addLayout(rb)

        self.progress = QProgressBar()
        lay.addWidget(self.progress)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setStyleSheet("font-family: monospace;")
        lay.addWidget(self.out, 1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.close)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de fotos del sitio")
        if d:
            self.folder_edit.setText(d)

    def _pick_form(self):
        p, _ = QFileDialog.getOpenFileName(self, "Formulario de fotos", "",
                                           "Formulario (*.xlsx *.csv);;Todos (*)")
        if p:
            self.form_edit.setText(p)

    def _save_template(self):
        import shutil
        src = os.path.join(os.path.dirname(__file__), "plantillas", "Formulario_fotos_CobDosel.xlsx")
        dst, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla del formulario de fotos",
                                             "Formulario_fotos_CobDosel.xlsx", "Excel (*.xlsx)")
        if dst:
            shutil.copyfile(src, dst)
            QMessageBox.information(self, "Plantilla guardada", dst)

    def _draft_form(self):
        folder = self.folder_edit.text().strip()
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Carpeta de fotos", "Indique primero la carpeta de fotos.")
            return
        n, ok = QInputDialog.getInt(self, "Fotos por parcela", "Fotos por parcela (5 = Centro, N-O, N-E, S-E, S-O):",
                                    5, 1, 50, 1)
        if not ok:
            return
        try:
            import openpyxl  # noqa: F401
            default, filt = "Formulario_fotos.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        except ImportError:
            default, filt = "Formulario_fotos.csv", "CSV (*.csv)"
        dst, _ = QFileDialog.getSaveFileName(self, "Guardar formulario prellenado",
                                             os.path.join(folder, default), filt)
        if not dst:
            return
        try:
            path, nph, warns = bc.draft_form_from_photos(folder, dst, n)
        except Exception as e:
            QMessageBox.critical(self, "Formulario", str(e))
            return
        self.form_edit.setText(path)
        if not self.planned_spin.value():
            self.planned_spin.setValue(-(-nph // n))
        QMessageBox.information(
            self, "Formulario creado",
            "{} fotos → {} parcelas de {} fotos (asignación por orden de hora).\n\n"
            "Revise y corrija parcela, punto y calidad antes de procesar.{}".format(
                nph, -(-nph // n), n, ("\n\n" + "\n".join(warns)) if warns else ""))

    def _on_cal_changed(self, *_a):
        name = self.cal_combo.currentData()
        if not name:
            self.cal_info.setText("No hay calibraciones guardadas: calibre y guarde en el diálogo principal.")
            return
        try:
            cal = load_calibration(name)
        except Exception as e:
            self.cal_info.setText("⚠ " + str(e))
            return
        cam = cal.get("camera") or (cal.get("measurement") or {}).get("camera")
        has_cam = bool(cam and (cam.get("model") or cam.get("focal_length_mm") or cam.get("focal_length_35mm")))
        self.cam_btn.setEnabled(not has_cam)
        self.cal_info.setText("R = {:.0f} px en {}×{} px; {}; cámara: {}".format(
            cal.get("virtual_radius_px") or 0, cal.get("image_width_px") or 0, cal.get("image_height_px") or 0,
            (cal.get("measurement") or {}).get("summary") or "medición sin registrar",
            camera_label(cam) if has_cam else "no registrada (use «Registrar cámara…»)"))

    def _register_camera(self):
        """Añade la huella de cámara de las fotos de la carpeta a una calibración que no la tiene."""
        name = self.cal_combo.currentData()
        folder = self.folder_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Calibración", "Elija una calibración guardada.")
            return
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Carpeta de fotos", "Indique la carpeta con fotos de la cámara de la calibración.")
            return
        groups = [g for g in bc.camera_groups(bc.scan_photos(folder))
                  if g[2] and (g[2].get("model") or g[2].get("focal_length_mm") or g[2].get("focal_length_35mm"))]
        if not groups:
            QMessageBox.warning(self, "Sin EXIF", "Las fotos de la carpeta no tienen modelo ni distancia focal en el EXIF.")
            return
        labels = ["{} — {} fotos".format(lbl, n) for lbl, n, _c in groups]
        idx = 0
        if len(groups) > 1:
            item, ok = QInputDialog.getItem(self, "Cámara de la calibración",
                                            "La carpeta tiene fotos de varias lentes. ¿Cuál se usó para calibrar?",
                                            labels, 0, False)
            if not ok:
                return
            idx = labels.index(item)
        cam = dict(groups[idx][2])
        ans = QMessageBox.question(
            self, "Registrar cámara",
            "¿Registrar «{}» en la calibración «{}»?\n\nHágalo solo si la calibración se midió con esta misma "
            "cámara y lente, sin zoom.".format(camera_label(dict(cam, size=None)), name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            from .calibration_store import load_calibration as _load
            payload = _load(name, return_full_payload=True)
            cal = dict(payload["calibration"])
            w, h = cal.get("image_width_px"), cal.get("image_height_px")
            if w and h:
                cam["size"] = [int(w), int(h)]
                cam["aspect"] = round(max(w, h) / float(min(w, h)), 4)
            cal["camera"] = cam
            meta = dict(payload.get("metadata") or {})
            meta["camera_registered"] = {"from_folder": folder, "plugin_version": VERSION}
            path = save_calibration(name, cal, metadata=meta)
        except Exception as e:
            QMessageBox.critical(self, "Registrar cámara", str(e))
            return
        self._on_cal_changed()
        QMessageBox.information(self, "Cámara registrada", "{}\n{}".format(camera_label(cam), path))

    def _refresh_calibrations(self):
        self.cal_combo.clear()
        for name, path in list_calibrations():
            self.cal_combo.addItem(name, userData=name)
        self._on_cal_changed()

    def _fill_layers(self):
        self.layer_combo.clear()
        self.layer_combo.addItem("— ninguna —", userData=None)
        for lid, lyr in QgsProject.instance().mapLayers().items():
            if isinstance(lyr, QgsVectorLayer):
                self.layer_combo.addItem(lyr.name(), userData=lid)

    def _fill_fields(self, _i=None):
        self.field_combo.clear()
        lid = self.layer_combo.currentData()
        lyr = QgsProject.instance().mapLayers().get(lid) if lid else None
        if lyr is not None:
            for fld in lyr.fields():
                self.field_combo.addItem(fld.name())

    def _on_group(self, *_a):
        code = self.group_combo.currentData()
        if code is not None:
            self.height_spin.setValue(bc.canopy_group_height(code))
        self.height_spin.setReadOnly(code is not None)
        self._update_mask_info()

    def _on_mask_mode(self, *_a):
        h = self.mask_height_radio.isChecked()
        for w in (self.group_combo, self.height_spin, self.cam_spin, self.fp_spin):
            w.setEnabled(h)
        self.fixed_mask_spin.setEnabled(not h)
        self._update_mask_info()

    def _update_mask_info(self, *_a):
        if not self.mask_height_radio.isChecked():
            self.mask_info.setText("")
            return
        try:
            z = bc.zenith_from_height(self.height_spin.value(), self.cam_spin.value(), self.fp_spin.value())
            self.mask_info.setText("→ cenit máximo {:.1f}° = máscara {:.1f}° sobre el horizonte".format(z, 90 - z))
        except ValueError as e:
            self.mask_info.setText("⚠ " + str(e))

    def _log(self, msg, level="INFO"):
        self.out.append(("⚠ " if level != "INFO" else "") + msg)

    # ------------------------------------------------------------------
    def _on_run(self):
        folder = self.folder_edit.text().strip()
        form = self.form_edit.text().strip()
        if not os.path.isdir(folder) or not os.path.isfile(form):
            QMessageBox.warning(self, "Datos incompletos", "Indique la carpeta de fotos y el formulario.")
            return
        if self.planned_spin.value() < 1:
            QMessageBox.warning(self, "Parcelas planificadas", "Indique el número de parcelas planificadas.")
            return
        name = self.cal_combo.currentData()
        if not name:
            QMessageBox.warning(self, "Sin calibración", "Guarde una calibración en el diálogo principal.")
            return
        try:
            cal = load_calibration(name)
        except Exception as e:
            QMessageBox.critical(self, "Calibración", str(e))
            return
        height = self.height_spin.value()
        try:
            decisions = bc.load_decisions(folder)
        except Exception as e:
            decisions = {}
            self._log("No se pudieron leer las decisiones de revisión guardadas: {}".format(e), "WARN")
        self._last_cal = cal
        self.out.clear()
        self.progress.setValue(0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.batch = bc.run_batch(
                folder, form, cal, self.planned_spin.value(),
                mask_mode="height" if self.mask_height_radio.isChecked() else "fixed",
                canopy_height_m=height, camera_height_m=self.cam_spin.value(),
                canopy_group=self.group_combo.currentData(),
                footprint_radius_m=self.fp_spin.value(), fixed_mask_deg=self.fixed_mask_spin.value(),
                channel_mode=self.channel_combo.currentData(), cut_rule="glama",
                tolerance_s=self.tol_spin.value(), clock_offset_s=self.offset_spin.value(),
                progress=lambda i, n: (self.progress.setValue(int(100 * i / max(n, 1))),
                                       QApplication.processEvents()),
                log=self._log, decisions=decisions)
            self.batch["parametros"]["calibracion"] = name
            self.batch["parametros"]["revision_cortes"] = (
                "{} decisiones ({})".format(len(decisions), bc.DECISIONS_FILE) if decisions else "sin revisión")
            self.batch["parametros"]["sitio"] = self.site_edit.text().strip()
            self.batch["parametros"]["area_ha"] = self.area_spin.value() or None
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error en el lote", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._show()
        for b in (self.csv_btn, self.html_btn, self.layer_btn, self.review_btn):
            b.setEnabled(True)
        if decisions:
            self._log("Se aplicaron {} decisiones de revisión guardadas ({}).".format(len(decisions), bc.DECISIONS_FILE))
        pend = self.batch["sitio"].get("pendientes_revision") or 0
        if pend:
            QMessageBox.information(
                self, "Revisión de cortes",
                "{} foto(s) necesitan revisión visual del corte (el método automático no se pudo comprobar).\n\n"
                "Pulse «Revisar cortes…». Mientras tanto el resultado del sitio es provisional.".format(pend))

    def _on_review(self):
        if not self.batch:
            return
        from .cut_review_dialog import CutReviewDialog
        folder = self.folder_edit.text().strip()
        try:
            previous = bc.load_decisions(folder)
        except Exception:
            previous = {}
        items = [r for r in self.batch["fotos"] if r.get("archivo") and (r.get("valida") or r.get("decision") == "excluido")]
        dlg = CutReviewDialog(items, folder, self._last_cal, self.channel_combo.currentData(), previous,
                              operator=getattr(self, "_operator", ""), parent=self,
                              title_suffix=" — " + (self.site_edit.text().strip() or os.path.basename(folder)))
        if not _exec(dlg):
            return
        self._operator = dlg.operator()
        try:
            path = bc.save_decisions(folder, dlg.get_decisions(), VERSION)
        except Exception as e:
            QMessageBox.critical(self, "Revisión", "No se pudieron guardar las decisiones: {}".format(e))
            return
        self._log("Decisiones de revisión guardadas: " + path)
        self._on_run()

    def _show(self):
        b = self.batch
        s = b["sitio"]
        lines = ["SITIO: {}".format(self.site_edit.text().strip() or "—"),
                 "Cobertura del dosel del sitio (media de parcelas, CaCo): {} %".format(
                     fmt_num(s["caco_sitio"]) if s["caco_sitio"] is not None else "—"),
                 "Parcelas con resultado: {} de {} planificadas · fotos válidas {} de {}".format(
                     s["parcelas_con_resultado"], s["parcelas_planificadas"], s["fotos_validas"], s["fotos_total"]),
                 "Nivel de corte: " + (s.get("revision") or "—"),
                 "", "PARCELAS:"]
        if s.get("pendientes_revision"):
            lines.insert(0, "⚠ RESULTADO PROVISIONAL: {} foto(s) pendientes de revisión del corte.".format(
                s["pendientes_revision"]))
        for p in b["parcelas"]:
            lines.append("  {:<8} {:<20} fotos {}/{}  CaCo {}".format(
                p["parcela"], ("reemplazo de " + str(p["reemplaza_a"])) if p.get("reemplaza_a") else "",
                p["validas"], p["fotos"], fmt_num(p["caco_media"]) if p["caco_media"] is not None else "—"))
        lines += ["", "FOTOS:"]
        for r in b["fotos"]:
            lines.append("  {:<6} {:<7} {:<28} corte {:>4}  CaCo {:>7}  {:<22} {}".format(
                r["parcela"], r["punto"], r["archivo"] or "—", r.get("corte", "—"),
                fmt_num(r["caco"]) if r.get("caco") is not None else "—", r.get("decision") or "",
                r.get("motivo") or ""))
        if b["avisos"]:
            lines += ["", "AVISOS:"] + ["  ⚠ " + w for w in b["avisos"]]
        self.out.setPlainText("\n".join(lines))

    def _default_output(self, suffix):
        """Ruta por defecto en la carpeta de fotos: CobDosel_<sitio>_sitio<suffix>."""
        site = re.sub(r"[^\w\-]+", "_", self.site_edit.text().strip()).strip("_")
        name = "CobDosel_{}sitio{}".format(site + "_" if site else "", suffix)
        folder = self.folder_edit.text().strip()
        return os.path.join(folder, name) if os.path.isdir(folder) else name

    def _on_csv(self):
        base, _ = QFileDialog.getSaveFileName(self, "Prefijo de los CSV", self._default_output(""), "CSV (*.csv)")
        if not base:
            return
        base = base[:-4] if base.lower().endswith(".csv") else base
        paths = bc.write_csvs(self.batch, base, VERSION)
        QMessageBox.information(self, "CSV guardados", "\n".join(paths))

    def _on_html(self):
        p, _ = QFileDialog.getSaveFileName(self, "Informe HTML", self._default_output(".html"), "HTML (*.html)")
        if not p:
            return
        if not p.lower().endswith((".html", ".htm")):
            p += ".html"
        bc.write_html(self.batch, p, VERSION, self.site_edit.text().strip())
        self._log("Informe HTML guardado: " + p)
        ans = QMessageBox.question(self, "Informe guardado", "{}\n\n¿Abrir el informe ahora?".format(p),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self._open_file(p)

    def _open_file(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            try:
                webbrowser.open("file://" + os.path.abspath(path))
            except webbrowser.Error as e:
                QMessageBox.warning(self, "Abrir", "No se pudo abrir {}: {}".format(path, e))

    def _on_layer(self):
        """Capa de memoria con la media de cada parcela, unida por ID a la capa de parcelas."""
        lid = self.layer_combo.currentData()
        src = QgsProject.instance().mapLayers().get(lid) if lid else None
        fld = self.field_combo.currentText()
        if src is None or not fld:
            QMessageBox.warning(self, "Capa de parcelas", "Elija la capa de puntos y el campo ID de parcela.")
            return
        by_id = {str(p["parcela"]).strip().lower(): p for p in self.batch["parcelas"]}
        crs = src.crs().authid() if hasattr(src, "crs") else "EPSG:4326"
        out = QgsVectorLayer("Point?crs={}".format(crs),
                             "CobDosel — parcelas {}".format(self.site_edit.text().strip()), "memory")
        pr = out.dataProvider()
        pr.addAttributes([QgsField("parcela", _STR), QgsField("reemplaza", _STR), QgsField("fotos", _INT),
                          QgsField("validas", _INT), QgsField("caco", _FLOAT), QgsField("version", _STR)])
        out.updateFields()
        feats, matched = [], 0
        for f in src.getFeatures():
            key = str(f[fld]).strip().lower()
            p = by_id.get(key)
            if p is None:
                continue
            matched += 1
            nf = QgsFeature(out.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes([str(p["parcela"]), str(p.get("reemplaza_a") or ""), int(p["fotos"]),
                              int(p["validas"]), p["caco_media"], "CobDosel " + VERSION])
            feats.append(nf)
        pr.addFeatures(feats)
        out.updateExtents()
        QgsProject.instance().addMapLayer(out)
        missing = len(by_id) - matched
        QMessageBox.information(self, "Capa añadida", "{} parcelas unidas{}.".format(
            matched, "" if missing <= 0 else "; {} sin punto en la capa".format(missing)))
