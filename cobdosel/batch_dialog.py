"""Diálogo «Procesamiento por sitio (lote)» de CobDosel.

Procesa todas las fotos de un sitio con una configuración fija: calibración guardada, máscara
(fija, 63° por defecto; u opcional desde la altura de un grupo de dosel), canal, nivel de corte recomendado (log-normal; Otsu de respaldo)
y empareja cada foto con el formulario de fotos (ID de fotografía y hora de captura).
Resultado: media por parcela y media del sitio (Índice CaCo); CSV, HTML y capa.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import math
import os
import traceback

import re
import webbrowser

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QGroupBox, QFileDialog, QMessageBox, QProgressBar, QTextEdit,
    QApplication, QRadioButton, QInputDialog, QScrollArea, QSplitter, QWidget,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsField

from .ui_keys import disable_enter_buttons
from ._version import VERSION, fmt_num
from .calibration_store import list_calibrations, load_calibration, save_calibration, get_last_calibration
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


def saved_files_text(paths):
    """v0.14.59: «Carpeta: …» una vez y los nombres de archivo debajo (antes la ruta completa se repetía)."""
    folders = {os.path.dirname(p) for p in paths}
    if len(folders) != 1:
        return "\n".join(paths)
    return "Carpeta: {}\n\n{}".format(folders.pop(), "\n".join("• " + os.path.basename(p) for p in paths))


class CobDoselBatchDialog(QDialog):
    """Procesamiento de un sitio completo (parcelas × 5 fotos)."""


    def showEvent(self, event):  # noqa: N802 (API de Qt)
        """v0.14.39: Intro confirma el valor de una casilla y nunca pulsa un botón."""
        disable_enter_buttons(self)
        super().showEvent(event)

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.batch = None
        self._last_cal = None
        self.setWindowTitle("CobDosel v{} — Procesamiento por sitio (lote)".format(VERSION))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(900, 760)
        self.setMinimumSize(480, 360)          # v0.14.42: se puede achicar; el contenido se desplaza
        self.setSizeGripEnabled(True)
        self._build()
        self._refresh_calibrations()

    # ------------------------------------------------------------------
    def _build(self):
        # v0.14.42: ventana redimensionable en ambos sentidos: la configuración va en un área con barras
        # de desplazamiento y un divisor la separa del registro.
        outer = QVBoxLayout(self)
        top_w = QWidget()
        lay = QVBoxLayout(top_w)
        lay.setContentsMargins(0, 0, 0, 0)

        g1 = QGroupBox("1. Datos del sitio")
        f1 = QFormLayout(g1)
        self.site_edit = QLineEdit()
        self.site_edit.setPlaceholderText("Nombre o código del sitio (aparece en el informe y en los archivos)")
        f1.addRow("Nombre del sitio:", self.site_edit)
        self.operator_edit = QLineEdit()
        self.operator_edit.setPlaceholderText("Nombre de quien procesa y revisa (aparece en el informe y en el CSV)")
        self.operator_edit.setToolTip("Analista: queda registrado con el resultado del sitio y se propone en «Revisar\n"
                                      "cortes…» para cada decisión.")
        f1.addRow("Analista:", self.operator_edit)
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
        self.form_edit.setPlaceholderText("(opcional) sin formulario, parcela y punto se asignan por orden de hora")
        self.form_edit.setToolTip(
            "Formulario de fotos (CSV o Excel), opcional. Con formulario, cada foto se empareja por su ID o su\n"
            "hora con la parcela y el punto anotados, y se aplican las calidades («sol directo», «movida»…).\n"
            "Sin formulario, las fotos se ordenan por hora y se asignan a parcelas de «Fotos por parcela» fotos.")
        f1.addRow("Formulario de fotos (opcional):", r2)
        self.per_plot_spin = QSpinBox()
        self.per_plot_spin.setRange(1, 50)
        self.per_plot_spin.setValue(5)
        self.per_plot_spin.setToolTip("Sin formulario: número de fotos por parcela según el protocolo del estudio,\n"
                                      "asignadas por orden de hora (puntos «Foto 1», «Foto 2»…). Con formulario no se usa.")
        f1.addRow("Fotos por parcela (sin formulario):", self.per_plot_spin)
        self.planned_spin = QSpinBox()
        self.planned_spin.setRange(0, 999)
        self.planned_spin.setValue(0)
        self.planned_spin.setSpecialValueText("(opcional)")
        self.planned_spin.setToolTip("Número de parcelas del sitio, opcional. Si se indica, el resultado dice cuántas\n"
                                     "tienen resultado de ese total (sitio completo o incompleto).")
        f1.addRow("Número de parcelas:", self.planned_spin)
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
            "Para calibraciones que no registran la cámara: registra en la calibración la cámara (EXIF) de las\n"
            "fotos de la carpeta. Úselo solo si la calibración se hizo con esa misma cámara y lente.")
        self.cam_btn.clicked.connect(self._register_camera)
        rc.addWidget(self.cam_btn)
        f2.addRow("Calibración guardada:", rc)
        self.cal_info = QLabel("")
        self.cal_info.setWordWrap(True)
        self.cal_info.setToolTip("Las calibraciones se crean en el diálogo principal de CobDosel: calibre con una\n"
                                 "foto de la misma cámara y pulse «Guardar calibración».\n\n"
                                 "Modelo: «Rectilínea» es la geometría de la cámara principal (1x) de los teléfonos y es\n"
                                 "exacta con cualquier círculo; «Lineal» (compatible con Polar de GLAMA) es exacto solo\n"
                                 "en el borde del círculo de calibración y sirve para comparar con resultados de GLAMA.")
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
        self.fixed_mask_spin = QDoubleSpinBox()
        self.fixed_mask_spin.setRange(0.0, 85.0)
        self.fixed_mask_spin.setDecimals(1)
        self.fixed_mask_spin.setValue(bc.DEFAULT_MASK_DEG)
        self.fixed_mask_spin.setSuffix(" ° sobre el horizonte")
        self.fixed_mask_spin.setToolTip(
            "Máscara de horizonte. Estándar de CobDosel: 63° (análisis hasta 27° del cenit), con el\n"
            "que el círculo de análisis cabe entero en la foto de cualquier teléfono de 23–25 mm;\n"
            "Tichý (2016) usó 60°. Use el mismo valor en todos los sitios.")
        f2.addRow("Máscara de horizonte:", self.fixed_mask_spin)
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
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(top_w)
        scroll.setMinimumHeight(120)
        bottom_w = QWidget()
        lay = QVBoxLayout(bottom_w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(scroll)
        self.splitter.addWidget(bottom_w)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)

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
        self.clear_rev_btn = QPushButton("Borrar revisión guardada…")
        self.clear_rev_btn.setToolTip("Las decisiones de «Revisar cortes…» se guardan junto a las fotos y se aplican cada vez\n"
                                      "que se procesa el sitio. Este botón las retira (el archivo se renombra como copia de\n"
                                      "seguridad) para procesar con los cortes automáticos.")
        self.clear_rev_btn.clicked.connect(self._on_clear_review)
        rb.addWidget(self.clear_rev_btn)
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
        self.out.setMinimumHeight(60)
        lay.addWidget(self.out, 1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.close)
        outer.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

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
        n, ok = QInputDialog.getInt(self, "Fotos por parcela", "Fotos por parcela (según el protocolo del estudio):",
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
        rec = bc.calibration_record(cal)
        parts = [rec.get("calibracion_modelo") or "modelo sin registrar"]
        if rec.get("circulo_D_cm") and rec.get("altura_H_cm"):
            parts.append("D = {:g} cm a H = {:g} cm (borde a {:.1f}° del cenit)".format(
                rec["circulo_D_cm"], rec["altura_H_cm"],
                math.degrees(math.atan(rec["circulo_D_cm"] / (2.0 * rec["altura_H_cm"])))))
        else:
            parts.append(rec.get("calibracion_metodo") or "—")
        if rec.get("focal_equivalente_mm"):
            parts.append("focal equivalente {:.1f} mm".format(rec["focal_equivalente_mm"]))
        parts.append("R = {:.0f} px en {}×{} px".format(
            cal.get("virtual_radius_px") or 0, cal.get("image_width_px") or 0, cal.get("image_height_px") or 0))
        parts.append("medición: " + ((cal.get("measurement") or {}).get("summary") or "sin registrar"))
        parts.append("cámara: " + (camera_label(cam) if has_cam else "no registrada (use «Registrar cámara…»)"))
        txt = " · ".join(parts)
        if cal.get("glama_scale_side") == "long":            # v0.14.53
            txt = "⚠ " + bc.LONG_SIDE_WARNING + "\n" + txt
        self.cal_info.setText(txt)

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
        self.cal_combo.blockSignals(True)
        self.cal_combo.clear()
        for name, path in list_calibrations():
            self.cal_combo.addItem(name, userData=name)
        # v0.14.27: propone la última calibración usada en CobDosel
        last = get_last_calibration()
        if last:
            i = self.cal_combo.findData(last)
            if i >= 0:
                self.cal_combo.setCurrentIndex(i)
        self.cal_combo.blockSignals(False)
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

    def _log(self, msg, level="INFO"):
        self.out.append(("⚠ " if level != "INFO" else "") + msg)

    # ------------------------------------------------------------------
    def _on_run(self):
        folder = self.folder_edit.text().strip()
        form = self.form_edit.text().strip()
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Datos incompletos", "Indique la carpeta de fotos.")
            return
        if form and not os.path.isfile(form):
            QMessageBox.warning(self, "Formulario de fotos", "No se encuentra el formulario:\n{}\n\n"
                                "Corrija la ruta o déjela vacía para asignar las fotos por orden de hora.".format(form))
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
        # v0.14.44: la calibración debe ser de la cámara de las fotos; se comprueba antes de procesar
        self._precheck_note = None
        pick = self._check_calibration_camera(folder, name, cal)
        if pick is None:
            return
        if pick != name:
            name = pick
            self.cal_combo.setCurrentIndex(self.cal_combo.findData(name))
            cal = load_calibration(name)
        try:
            decisions = bc.load_decisions(folder)
        except Exception as e:
            decisions = {}
            self._log("No se pudieron leer las decisiones de revisión guardadas: {}".format(e), "WARN")
        self._last_cal = cal
        self.out.clear()
        if self._precheck_note:
            self._log(*self._precheck_note)
        self.progress.setValue(0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.batch = bc.run_batch(
                folder, form or None, cal, self.planned_spin.value() or None,
                mask_mode="fixed", fixed_mask_deg=self.fixed_mask_spin.value(),   # v0.14.48: solo máscara fija
                channel_mode=self.channel_combo.currentData(), cut_rule="glama",
                tolerance_s=self.tol_spin.value(), clock_offset_s=self.offset_spin.value(),
                progress=lambda i, n: (self.progress.setValue(int(100 * i / max(n, 1))),
                                       QApplication.processEvents()),
                log=self._log, decisions=decisions, photos_per_plot=self.per_plot_spin.value())
            self.batch["parametros"]["calibracion"] = name
            self.batch["parametros"]["revision_cortes"] = (
                "{} ({})".format(bc.decisions_summary(decisions), bc.DECISIONS_FILE) if decisions else "sin revisión")
            if decisions:
                self.batch["avisos"].insert(0, "{} en «Revisar cortes…».".format(bc.applied_text(decisions)))
            self.batch["parametros"]["sitio"] = self.site_edit.text().strip()
            self.batch["parametros"]["area_ha"] = self.area_spin.value() or None
            self.batch["parametros"]["analista"] = self.operator_edit.text().strip()
            if self._precheck_note:                  # v0.14.44: queda en los avisos del sitio (panel, informe)
                self.batch["avisos"].insert(0, self._precheck_note[0])
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
            # v0.14.48: decisiones tomadas en «Revisar cortes…» (archivo en la carpeta de fotos) y cómo quitarlas
            self._log("{} en «Revisar cortes…» ({}, en la carpeta de fotos). Para procesar sin ellas, "
                      "use «Borrar revisión guardada…».".format(bc.applied_text(decisions), bc.DECISIONS_FILE),
                      "WARN")
        pend = self.batch["sitio"].get("pendientes_revision") or 0
        if pend:
            QMessageBox.information(
                self, "Revisión de cortes",
                "{} foto(s) necesitan revisión visual del corte (método automático no comprobado o cielo no uniforme).\n\n"
                "Pulse «Revisar cortes…». Mientras tanto el resultado del sitio es provisional.".format(pend))

    def _check_calibration_camera(self, folder, name, cal):
        """
        v0.14.44: compara la cámara de la calibración con las fotos de la carpeta antes de procesar. Si hay fotos
        de otra cámara/lente, pregunta: usar una calibración guardada que coincida (si la hay), procesar igual
        (esas fotos se excluyen) o cancelar. Devuelve el nombre de la calibración a usar, o None para cancelar.
        """
        saved = []
        for n, _p in list_calibrations():
            if n == name:
                continue
            try:
                saved.append((n, load_calibration(n)))
            except Exception:
                continue
        chk = bc.calibration_camera_check(folder, cal, saved)
        if not chk["checked"] or not chk["mismatch"]:
            return name
        others = "\n".join("• {}: {} foto(s)".format(lbl, n) for lbl, n, st in chk["groups"] if st is False)
        txt = ("{} de {} fotos de la carpeta son de otra cámara o lente que la calibración «{}» ({}):\n{}\n\n"
               "Con esta calibración, esas fotos se excluyen del resultado.").format(
                   chk["mismatch"], chk["total"], name, chk["cal_label"], others)
        if chk["matches"]:
            txt += ("\n\nCalibración guardada de esa cámara: «{}».\n\nSí: usar «{}».\nNo: procesar con «{}» "
                    "(se excluyen esas fotos).\nCancelar: no procesar.").format(
                        "», «".join(chk["matches"]), chk["matches"][0], name)
            buttons = (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                       QMessageBox.StandardButton.Cancel)
        else:
            txt += ("\n\nNo hay una calibración guardada de esa cámara: calíbrela en la ventana principal (círculo de "
                    "referencia) y guárdela.\n\nNo: procesar igual (se excluyen esas fotos).\nCancelar: no procesar.")
            buttons = QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        ans = QMessageBox.question(self, "Calibración de otra cámara", txt, buttons)
        if ans == QMessageBox.StandardButton.Yes and chk["matches"]:
            self._precheck_note = ("Calibración cambiada a «{}» (cámara de las fotos).".format(chk["matches"][0]), "INFO")
            return chk["matches"][0]
        if ans == QMessageBox.StandardButton.No:
            self._precheck_note = ("Se procesa con «{}»: {} foto(s) de otra cámara se excluyen.".format(
                name, chk["mismatch"]), "WARN")
            return name
        return None

    def _on_clear_review(self):
        """v0.14.45: retira las decisiones guardadas (renombra el archivo; no lo borra)."""
        folder = self.folder_edit.text().strip()
        path = os.path.join(folder, bc.DECISIONS_FILE)
        if not os.path.isfile(path):
            QMessageBox.information(self, "Revisión guardada", "No hay decisiones de revisión guardadas en esta carpeta.")
            return
        try:
            summary = bc.decisions_summary(bc.load_decisions(folder))
        except Exception:
            summary = "decisiones guardadas"
        ans = QMessageBox.question(
            self, "Borrar revisión guardada",
            "La carpeta tiene {}.\n\nSe retirarán (el archivo se guarda como copia de seguridad) y el sitio se "
            "procesará con los cortes automáticos. ¿Continuar?".format(summary),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        import datetime as _dt
        bak = os.path.join(folder, "CobDosel_revision_cortes_{}.bak.json".format(
            _dt.datetime.now().strftime("%Y%m%d_%H%M%S")))
        try:
            os.replace(path, bak)
        except OSError as e:
            QMessageBox.critical(self, "Revisión guardada", "No se pudo retirar el archivo: {}".format(e))
            return
        self._log("Revisión guardada retirada (copia: {}).".format(os.path.basename(bak)))
        if self.batch is not None:
            self._on_run()

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
                              operator=self.operator_edit.text().strip(), parent=self,
                              title_suffix=" — " + (self.site_edit.text().strip() or os.path.basename(folder)))
        accepted = bool(_exec(dlg))
        if dlg.operator():                        # el nombre escrito en la revisión pasa a la ventana
            self.operator_edit.setText(dlg.operator())
        # v0.14.42: las decisiones se guardan al aceptarlas; al cerrar sin «Terminar y recalcular» también se
        # recalcula si hubo cambios, para que los resultados coincidan con el archivo de decisiones.
        if not accepted and not dlg.changed:
            return
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
                 "ANALISTA: {}".format(self.operator_edit.text().strip() or "—"),
                 "Cobertura del dosel del sitio (media de todas las fotos válidas, CaCo): {} %".format(
                     fmt_num(s["caco_sitio"]) if s["caco_sitio"] is not None else "—"),
                 "Parcelas con resultado: {}{} · fotos válidas {} de {}".format(
                     s["parcelas_con_resultado"],
                     " de {}".format(s["parcelas_planificadas"]) if s.get("parcelas_planificadas") else "",
                     s["fotos_validas"], s["fotos_total"]),
                 "Nivel de corte: " + (s.get("revision") or "—"),
                 "", "PARCELAS:"]
        if s.get("pendientes_revision"):
            lines.insert(0, "⚠ RESULTADO PROVISIONAL: {} foto(s) pendientes de revisión del corte.".format(
                s["pendientes_revision"]))
        from .canopy_analysis import SKY_UNIFORMITY_LIMIT
        nval = sum(1 for r in b["fotos"] if r.get("valida"))
        nsky = sum(1 for r in b["fotos"] if r.get("valida") and (r.get("cielo_rango") or 0) > SKY_UNIFORMITY_LIMIT)
        if nsky:                                         # v0.14.47: junto al resultado del sitio
            lines.insert(1 if s.get("pendientes_revision") else 0,
                         "⚠ " + bc.sky_review_line(b["fotos"], self.operator_edit.text().strip()))
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
        """Ruta por defecto en la carpeta de fotos: CobDosel_<sitio><suffix> (v0.14.58: sin el «_sitio» que,
        con el CSV del sitio, daba «…_sitio_sitio.csv»); sin nombre de sitio, CobDosel_sitio<suffix>."""
        site = re.sub(r"[^\w\-]+", "_", self.site_edit.text().strip()).strip("_")
        name = "CobDosel_{}{}".format(site or "sitio", suffix)
        folder = self.folder_edit.text().strip()
        return os.path.join(folder, name) if os.path.isdir(folder) else name

    def _guarded(self, button, func):
        """v0.14.59: una exportación por clic. El botón queda inactivo mientras se exporta y los clics que
        llegaron mientras tanto (doble clic, barra espaciadora) se descartan antes de reactivarlo."""
        if getattr(self, "_exporting", False):
            return
        self._exporting = True
        button.setEnabled(False)
        try:
            func()
        finally:
            QApplication.processEvents()          # los clics en cola llegan a un botón inactivo y se pierden
            button.setEnabled(self.batch is not None)
            self._exporting = False

    def _on_csv(self):
        self._guarded(self.csv_btn, self._export_csv)

    def _export_csv(self):
        base, _ = QFileDialog.getSaveFileName(self, "Prefijo de los CSV", self._default_output(""), "CSV (*.csv)")
        if not base:
            return
        base = base[:-4] if base.lower().endswith(".csv") else base
        paths = bc.write_csvs(self.batch, base, VERSION)
        self._log("CSV guardados: " + "; ".join(paths))
        QMessageBox.information(self, "CSV guardados", saved_files_text(paths))

    def _on_html(self):
        self._guarded(self.html_btn, self._export_html)

    def _export_html(self):
        p, _ = QFileDialog.getSaveFileName(self, "Informe HTML", self._default_output("_informe.html"), "HTML (*.html)")
        if not p:
            return
        if not p.lower().endswith((".html", ".htm")):
            p += ".html"
        bc.write_html(self.batch, p, VERSION, self.site_edit.text().strip())
        self._log("Informe HTML guardado: " + p)
        ans = QMessageBox.question(self, "Informe guardado", "{}\n\n¿Abrir el informe ahora?".format(
            saved_files_text([p])), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
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
