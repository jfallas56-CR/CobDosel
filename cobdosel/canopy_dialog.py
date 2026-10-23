"""
Diálogo principal de CobDosel — Cobertura del dosel a partir de fotografías
(basado en Tichý 2016).

Basado en:
- Lubomír Tichý (2016). Field test of canopy cover estimation by hemispherical
  photographs taken with a smartphone. Journal of Vegetation Science, 27(2), 427–435.
  https://doi.org/10.1111/jvs.12350
- Manual de GLAMA v3.0: https://www.sci.muni.cz/botany/glama/GLAMA%20manual.pdf

v0.9.0:
- Interfaz completamente en español.
- Panel redimensionable horizontal y verticalmente mediante QSplitter y QScrollArea.
- Pestañas al estilo QGIS: "Parámetros", "Registro" (ventana de bitácora detallada) y "Ayuda".
- Panel lateral desplegable de "Ayuda corta" contextual y pestaña de "Ayuda completa".
- Incluye máscara de horizonte artificial interactiva y calculadora de la Tabla 1 de GLAMA
  (Tamaño de parcela × Altura máxima del dosel) y el óptimo > 45° demostrado por Tichý (2016).
- Reporta todos los resultados de GLAMA en pantalla, CSV, capa GPS e Informe HTML.
- Créditos: Jorge Fallas (jfallas56@gmail.com).

v0.11.1 (CobDosel):
- Geometría de pantalla de GLAMA: centro del hemisferio desplazado 39 px hacia abajo en la
  vista (ajustable); reproduce exactamente «(in Frame)» y «Part of Hemisph.» de la app.

v0.11.0 (CobDosel):
- Cambio de nombre CAnOPY → CobDosel (cobertura del dosel).
- Anillos y rango analizado hasta la máscara de horizonte (antes se limitaban al semiángulo
  del lado corto de la foto; las esquinas y los anillos parcialmente visibles se excluían).
- Radio del hemisferio (R) y su equivalente en GLAMA visibles en la calibración; la
  calibración guarda la foto y el tamaño en que se midió el círculo y avisa al cargarla en
  una foto de otra proporción.
- Calibración directa con el «Hemisph. radius» de GLAMA; modo opcional «geometría de pantalla
  de GLAMA» (recorte cuadrado de 1080 px y franjas negras) para estudios de transición.
- Medición del círculo con dos diámetros E–O/N–S o ajuste de ≥ 5 puntos.
- Aviso cuando el círculo de análisis queda parcialmente fuera de la foto (% visible).
- Vista «Anillos cenitales» nueva (anillos a intervalos fijos con etiquetas, cielo en
  naranja, máscara en verde azulado, sectores de acimut) y tabla de fracción de claros por
  sector; orientación y rumbo EXIF en el informe.
- Encabezado de resultados «RESULTADOS (método GLAMA, Tichý 2016)»; el CaCo se identifica como
  el valor de cobertura del dosel.

v0.10.0 (2026-10-17):
- LAI efectivo con rango cenital propio (no la máscara de horizonte) y Miller normalizado.
- «Fracción de claros del área seleccionada» = claros / píxeles del círculo visibles.
- Otsu e histograma restringidos al área válida (sin borde negro del ojo de pez).
- Limpieza morfológica desactivada por defecto; la superposición y el informe muestran
  la máscara analizada.
- Estado inicial coherente del tipo de lente; máscara válida según la calibración.
- Rejillas radio/cenit calculadas una vez en float32 (≈ −50 % de memoria).
- Tipos de campo y enums Qt compatibles con Qt5/Qt6; separador de miles con espacio.
"""

import os
import json
import csv
import datetime
import traceback
import webbrowser

import numpy as np
from PIL import Image

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QCheckBox,
    QGroupBox, QFileDialog, QMessageBox, QProgressBar, QTextEdit,
    QTextBrowser, QInputDialog, QApplication, QTabWidget, QSplitter,
    QScrollArea, QWidget, QSizePolicy,
)

from qgis.core import (
    Qgis, QgsProject, QgsPointXY, QgsFeature, QgsGeometry, QgsField,
    QgsVectorLayer, QgsRasterLayer,
)


try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

from .ui_keys import disable_enter_buttons
from ._version import VERSION, fmt_int
from .exif_gps import extract_exif, load_oriented_rgb_image
from .lens_calibration import (
    HAS_CV2,
    detect_fisheye_circle,
    calibrate_regular_lens,
    calibrate_fisheye_from_radius,
    calibrate_from_glama_radius,
    glama_equivalent_radius,
    zenith_to_pixel_radius,
    GLAMA_VIEW_WIDTH_PX,
    scale_calibration_to_image,
    list_projections,
    PROJECTIONS_REGULAR,
    PROJECTIONS_FISHEYE,
    projection_note,
    is_fisheye_projection,
)
from .canopy_analysis import (
    compute_auto_threshold,
    AUTO_THRESHOLD_METHODS,
    AUTO_THRESHOLD_LABELS,
    threshold_image,
    clean_binary_mask,
    create_zenith_rings,
    compute_canopy_cover,
    compute_effective_lai,
    compute_radius_grid,
    compute_zenith_grid,
    LAI_DEFAULT_ZENITH_MAX_DEG,
    LAI_MIN_RELIABLE_ZENITH_DEG,
    HAS_SCIPY,
    compute_canopy_metrics,
    classify_measurement_type,
    compute_hemisphere_fraction,
    extract_channel,
    recommended_horizon_mask_deg,
    CHANNEL_MODES,
    CHANNEL_LABELS,
    azimuth_grid,
    compute_sector_gap_fractions,
    analysis_circle_visibility,
)
from .glama_engine import (
    glama_mode,
    horizon_zenith_limit,
    glama_ring_counts,
    glama_indices,
    glama_cut_iterated,
    glama_cut_diagnosis,
    glama_ring_counts_with_gray,
    GLAMA_CUT_START,
    glama_view_image,
    GLAMA_VIEW_W,
    GLAMA_VIEW_H,
    GLAMA_CENTER_DY,
)
from .measure_circle_dialog import MeasureCircleDialog
from .calibration_store import (
    save_calibration,
    load_calibration,
    list_calibrations,
    calibration_path,
    get_last_calibration,
    set_last_calibration,
)
from .visualization import render_glama_rings, render_threshold_overlay, oriented_copy_for_qgis
from .threshold_dialog import ThresholdDialog
from .html_report import generate_html_report
from .help_texts import SHORT_HELP_TOPICS, FULL_HELP_HTML
from .camera_check import camera_fingerprint, camera_label, compare_cameras
from .focal_check import check_focal, calibration_focal_mm

_ORIENTATION_TEXT = {2: "espejo horizontal", 3: "girada 180°", 4: "espejo vertical",
                     5: "espejo y giro 90°", 6: "girada 90° a la derecha", 7: "espejo y giro 270°",
                     8: "girada 90° a la izquierda"}

def _proj_label(cal):
    """v0.14.38: nombre del modelo para el usuario (CSV, capas, registro); nunca el código interno."""
    cal = cal or {}
    code = cal.get("projection")
    return str(cal.get("projection_label") or dict(list_projections()).get(code, code or ""))


# Tipos de campo compatibles con QGIS 3.28 LTR (QVariant) y QGIS >= 3.38 / 4.x (QMetaType)
_FIELD_TYPES_SET = False
if getattr(Qgis, "QGIS_VERSION_INT", 0) >= 33800:
    try:
        from qgis.PyQt.QtCore import QMetaType
        _STR = QMetaType.Type.QString
        _FLOAT = QMetaType.Type.Double
        _INT = QMetaType.Type.Int
        _LONG = QMetaType.Type.LongLong
        _FIELD_TYPES_SET = True
    except (ImportError, AttributeError):
        _FIELD_TYPES_SET = False
if not _FIELD_TYPES_SET:
    from qgis.PyQt.QtCore import QVariant
    _STR = QVariant.String
    _FLOAT = QVariant.Double
    _INT = QVariant.Int
    _LONG = QVariant.LongLong


MAX_ANALYSIS_DIM = 4096


SHORT_HELP_TOPICS = {
    key: text.replace("__VERSION__", VERSION) for key, text in SHORT_HELP_TOPICS.items()
}
FULL_HELP_HTML = FULL_HELP_HTML.replace("__VERSION__", VERSION)


def _exec_dialog(dlg):
    """exec() en Qt6 / PyQt5 moderno; exec_() como respaldo."""
    runner = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
    return runner()


class CobDoselDialog(QDialog):
    """Diálogo principal de CobDosel (basado en Tichý 2016). Redimensionable H y V."""


    def showEvent(self, event):  # noqa: N802 (API de Qt)
        """v0.14.39: Intro confirma el valor de una casilla y nunca pulsa un botón."""
        disable_enter_buttons(self)
        super().showEvent(event)

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle(
            "CobDosel v{} — Cobertura del dosel a partir de fotografías (basado en Tichý 2016)".format(
                VERSION)
        )
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumSize(540, 420)
        self.resize(1140, 880)
        self.setSizeGripEnabled(True)

        self.image_path = None
        self.image_array = None
        self.original_image_size = None
        self.image_load_scale = 1.0
        self.gray_array = None
        self.calibration = None
        self.center_xy = None
        self.sky_mask = None
        self.ring_labels = None
        self.ring_boundaries = None
        self.exif_data = None
        self.last_results = None
        self.last_measured_pixel_diameter = None
        # Medición del círculo en otra foto: (diámetro nativo, (ancho, alto) nativos)
        self._calib_measure_native = None
        # Origen de la medición del círculo (archivo, tamaño original, modo, control de calidad)
        self._measure_info = None
        self._temp_files = []

        # Método con el que se fijó el nivel de corte (se registra en panel, HTML y CSV)
        self.cut_method = "manual"
        self._cut_auto = None          # (etiqueta del método, valor) del último corte automático
        self._cut_for = None           # foto para la que se calculó o ajustó el nivel de corte
        self._build_ui()
        self._update_run_button()
        self._log(
            "CobDosel v{} (basado en Tichý 2016, doi:10.1111/jvs.12350) iniciado.".format(VERSION)
        )
        if not HAS_SCIPY:
            self._log(
                "scipy no está instalado: la limpieza morfológica queda desactivada.",
                "WARN",
            )

    # ------------------------------------------------------------------
    # Construcción de la interfaz (Español, redimensionable H y V)
    # ------------------------------------------------------------------
    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # === Panel izquierdo: Pestañas (Parámetros | Registro | Ayuda) ===
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._build_parameters_tab()
        self._build_log_tab()
        self._build_help_tab()

        self.main_splitter.addWidget(self.tabs)

        # === Panel derecho: Ayuda corta ===
        self._build_short_help_panel()
        self.main_splitter.addWidget(self.short_help_panel)

        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([780, 350])

        root_layout.addWidget(self.main_splitter, stretch=1)

        # === Barra inferior ===
        bottom_bar = QHBoxLayout()

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setMinimumWidth(180)
        bottom_bar.addWidget(self.progress, stretch=1)

        self.toggle_short_help_btn = QPushButton("Ocultar ayuda corta")
        self.toggle_short_help_btn.setToolTip(
            "Mostrar u ocultar el panel lateral de ayuda rápida."
        )
        self.toggle_short_help_btn.clicked.connect(self._toggle_short_help)
        bottom_bar.addWidget(self.toggle_short_help_btn)

        self.open_log_btn = QPushButton("Ver Registro")
        self.open_log_btn.setToolTip("Abrir la ventana de registro de ejecución.")
        self.open_log_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        bottom_bar.addWidget(self.open_log_btn)

        self.open_help_btn = QPushButton("? Ayuda")
        self.open_help_btn.setToolTip("Abrir el manual completo en español.")
        self.open_help_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        bottom_bar.addWidget(self.open_help_btn)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.clicked.connect(self.close)
        bottom_bar.addWidget(self.close_btn)

        root_layout.addLayout(bottom_bar)

        # Conectar señales de widgets una vez que toda la interfaz ha sido construida
        self.lens_combo.currentIndexChanged.connect(self._on_lens_changed)
        self.pixel_diameter.valueChanged.connect(self._update_run_button)
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self.threshold_spin.valueChanged.connect(self._on_threshold_spin_changed)
        self.zenith_max.valueChanged.connect(self._on_zenith_max_changed)
        self.horizon_mask_spin.valueChanged.connect(self._on_horizon_mask_changed)
        self.short_help_combo.currentIndexChanged.connect(
            self._on_short_help_topic_changed
        )

        # Estado inicial coherente con el tipo de lente seleccionado
        self.lens_combo.blockSignals(True)
        self.lens_combo.setCurrentIndex(1)          # lente regular / teléfono por defecto
        self.lens_combo.blockSignals(False)
        self._on_lens_changed(self.lens_combo.currentIndex(), update_help=False)

        # v0.14.27: la última calibración usada se aplica al cargar la primera foto
        self._cal_name = None
        self._autoload_done = False
        last = get_last_calibration()
        if not last:
            self.calib_result.setText(
                "Sin calibrar. Cargue una calibración guardada («Cargar calibración…») o mida el "
                "círculo de referencia; la que use quedará recordada para las próximas sesiones.")
        if last:
            self.calib_result.setText(
                "Sin calibrar. Última calibración usada: «{}»; se aplicará al cargar la foto "
                "(o use «Cargar calibración…» para elegir otra).".format(last))

    def _build_parameters_tab(self):
        param_tab = QWidget()
        param_tab_layout = QVBoxLayout(param_tab)
        param_tab_layout.setContentsMargins(4, 4, 4, 4)

        self.param_splitter = QSplitter(Qt.Orientation.Vertical, param_tab)
        self.param_splitter.setChildrenCollapsible(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        form_container = QWidget()
        layout = QVBoxLayout(form_container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # --- 1. Imagen ---
        file_group = QGroupBox("1. Imagen")
        file_layout = QFormLayout(file_group)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Seleccione una fotografía de dosel…")
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self._on_browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(browse_btn)
        file_layout.addRow("Archivo de imagen:", path_row)

        self.exif_label = QLabel("Ninguna imagen cargada.")
        self.exif_label.setWordWrap(True)
        file_layout.addRow("Metadatos EXIF:", self.exif_label)

        layout.addWidget(file_group)

        # --- 2. Calibración del lente ---
        cal_group = QGroupBox("2. Calibración del lente (definición del hemisferio)")
        cal_layout = QFormLayout(cal_group)

        self.lens_combo = QComboBox()
        self.lens_combo.addItems([
            "Ojo de pez (circular 180°)",
            "Lente regular / smartphone (círculo de diámetro conocido)",
        ])
        self.lens_combo.setToolTip(
            "Lente regular / smartphone: cámara principal (1x) de teléfonos Android y iPhone (iOS), o cualquier\n"
            "cámara cuya foto llena el fotograma; se calibra con el círculo de diámetro conocido D a la distancia H.\n"
            "Ojo de pez (circular 180°): la foto muestra el círculo de imagen completo con esquinas negras\n"
            "(lente ojo de pez adicional o cámara hemisférica); se calibra detectando ese círculo.")
        cal_layout.addRow("Tipo de lente:", self.lens_combo)

        self.projection_combo = QComboBox()
        # v0.14.26: solo los modelos que corresponden al tipo de lente (lente regular por defecto)
        self._populate_projections(is_fisheye=False)
        self.projection_combo.currentIndexChanged.connect(
            self._update_projection_tooltip
        )
        # v0.14.34: cambiar el modelo actualiza la calibración activa (círculo D/H) o lo advierte
        self._proj_sync_off = False
        self.projection_combo.currentIndexChanged.connect(self._on_projection_changed)
        self._update_projection_tooltip()
        cal_layout.addRow("Modelo de proyección:", self.projection_combo)

        self.detect_btn = QPushButton(
            "Detectar círculo automáticamente (transformada de Hough)"
        )
        self.detect_btn.clicked.connect(self._on_detect_circle)
        cal_layout.addRow("", self.detect_btn)

        self.circle_diameter = QDoubleSpinBox()
        self.circle_diameter.setRange(0.1, 1000.0)
        self.circle_diameter.setDecimals(2)
        self.circle_diameter.setValue(33.0)      # v0.14.27: valores del manual (antes 12,2 y 25,7 de GLAMA)
        self.circle_diameter.setSuffix(" cm")
        cal_layout.addRow("Diámetro del círculo de referencia:", self.circle_diameter)

        self.camera_height = QDoubleSpinBox()
        self.camera_height.setRange(0.1, 1000.0)
        self.camera_height.setDecimals(2)
        self.camera_height.setValue(40.0)
        self.camera_height.setSuffix(" cm")
        cal_layout.addRow("Distancia / altura del lente al círculo:", self.camera_height)

        self.pixel_diameter = QDoubleSpinBox()
        self.pixel_diameter.setRange(0.0, 100000.0)
        self.pixel_diameter.setDecimals(2)
        # v0.14.27: sin calibración el campo muestra «sin medir» (antes 1975 px fijos, que parecían
        # una medición y no correspondían a los D y H mostrados)
        self.pixel_diameter.setSpecialValueText("sin medir")
        self.pixel_diameter.setValue(0.0)
        self.pixel_diameter.setSuffix(" px")
        # pixel_diameter.valueChanged connected after UI build

        self.measure_image_btn = QPushButton("Medir en imagen…")
        self.measure_image_btn.clicked.connect(self._on_measure_in_image)

        self.measure_file_btn = QPushButton("Medir desde archivo…")
        self.measure_file_btn.clicked.connect(self._on_measure_from_file)

        pixel_row = QHBoxLayout()
        pixel_row.addWidget(self.pixel_diameter, stretch=1)
        pixel_row.addWidget(self.measure_image_btn)
        pixel_row.addWidget(self.measure_file_btn)
        cal_layout.addRow("Diámetro medido del círculo:", pixel_row)

        self.glama_cal_check = QCheckBox(
            "Fórmula aproximada (semiángulo = atan(D/H)/2), solo calibraciones antiguas"
        )
        self.glama_cal_check.setToolTip(
            "Oculta. CobDosel y la app GLAMA usan la geometría exacta atan(D/2H) (comprobado con\n"
            "la app en 2026-10). La aproximación sobrestima el radio del hemisferio (+1 % con\n"
            "D/H = 0.2, +10.6 % con 0.714); se conserva solo para leer calibraciones antiguas."
        )
        self.glama_cal_check.setChecked(False)
        self.glama_cal_check.setVisible(False)   # la calibración usa siempre la geometría exacta atan(D/2H)

        self.calibrate_btn = QPushButton("Calcular calibración")
        self.calibrate_btn.clicked.connect(self._on_calibrate)

        self.load_cal_btn = QPushButton("Cargar calibración…")
        self.load_cal_btn.clicked.connect(self._on_load_calibration)

        self.save_cal_btn = QPushButton("Guardar calibración…")
        self.save_cal_btn.clicked.connect(self._on_save_calibration)
        self.save_cal_btn.setEnabled(False)

        cal_btn_row = QHBoxLayout()
        cal_btn_row.addWidget(self.calibrate_btn)
        cal_btn_row.addWidget(self.load_cal_btn)
        cal_btn_row.addWidget(self.save_cal_btn)
        cal_layout.addRow("", cal_btn_row)

        # Calibración directa con el radio del hemisferio de la app GLAMA
        glama_row = QHBoxLayout()
        self.glama_radius_spin = QDoubleSpinBox()
        self.glama_radius_spin.setRange(1.0, 20000.0)
        self.glama_radius_spin.setDecimals(1)
        self.glama_radius_spin.setValue(1618.0)
        self.glama_radius_spin.setSuffix(" px (GLAMA)")
        self.glama_radius_spin.setToolTip(
            "«Hemisph. radius» que muestra la app GLAMA (píxeles de su vista de {} px).".format(
                GLAMA_VIEW_WIDTH_PX))
        glama_row.addWidget(self.glama_radius_spin)
        self.glama_side_combo = QComboBox()
        self.glama_side_combo.addItem(
            "lado menor (reproduce los resultados de GLAMA)", userData="short")
        self.glama_side_combo.addItem(
            "lado mayor (pantalla de calibración de GLAMA)", userData="long")
        self.glama_side_combo.setToolTip(
            "La pantalla de ANÁLISIS de GLAMA muestra el recorte cuadrado central de la foto:\n"
            "1080 px de la app = lado MENOR de la foto. «Lado menor» reproduce los resultados\n"
            "de GLAMA. Si la foto del círculo se mostró a lo ancho en la pantalla de\n"
            "calibración, la escala física corresponde al lado MAYOR (en fotos 4:3 difieren\n"
            "en 4/3). Para la geometría correcta use la calibración por círculo D/H.")
        glama_row.addWidget(self.glama_side_combo, stretch=1)
        self.glama_radius_btn = QPushButton("Calibrar con radio GLAMA")
        self.glama_radius_btn.setToolTip(
            "Crea la calibración a partir del radio de GLAMA: proyección «Polar» de GLAMA\n"
            "(Lineal en CobDosel), o «Angular» de GLAMA si elige Tipo de lente «Ojo de pez»\n"
            "y el modelo Ortográfica.")
        self.glama_radius_btn.clicked.connect(self._on_calibrate_glama_radius)
        glama_row.addWidget(self.glama_radius_btn)
        cal_layout.addRow("Opcional — radio de la app GLAMA:", glama_row)

        self.calib_result = QLabel("Sin calibrar.")
        self.calib_result.setWordWrap(True)
        cal_layout.addRow("Estado de calibración:", self.calib_result)

        layout.addWidget(cal_group)

        # --- 3. Umbral cielo / dosel ---
        thr_group = QGroupBox("3. Nivel de corte entre cielo y dosel")
        thr_layout = QFormLayout(thr_group)

        self.channel_combo = QComboBox()
        for code, label in CHANNEL_MODES:
            self.channel_combo.addItem(label, userData=code)
        # channel_combo.currentIndexChanged connected after UI build
        self.channel_combo.setToolTip(
            "Canales de color utilizados para clasificar cielo y dosel:\n\n"
            "• Azul + Rojo (recomendado): las hojas absorben azul y rojo,\n"
            "  mientras que el cielo los dispersa (máximo contraste).\n"
            "• Solo Azul: sencillo y eficaz en cielos despejados o nublados.\n"
            "• Escala de grises: luminancia estándar.\n"
            "• Solo Rojo / Solo Verde: bandas individuales.\n"
            "• Exceso de azul (2B − R): resalta la dispersión azul del cielo."
        )
        thr_layout.addRow("Canales de color:", self.channel_combo)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(1, 254)
        self.threshold_slider.setValue(128)
        # threshold_slider.valueChanged connected after UI build

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 254)
        self.threshold_spin.setValue(128)
        # threshold_spin.valueChanged connected after UI build

        thr_row = QHBoxLayout()
        thr_row.addWidget(self.threshold_slider, stretch=1)
        thr_row.addWidget(self.threshold_spin)
        thr_layout.addRow("Nivel de corte (1–254):", thr_row)

        thr_btns_row = QHBoxLayout()
        thr_btns_row.addWidget(QLabel("Automático:"))
        self.auto_method_combo = QComboBox()
        for code, label in AUTO_THRESHOLD_METHODS:
            self.auto_method_combo.addItem(label, userData=code)
        self.auto_method_combo.setToolTip(
            "Método automático de nivel de corte sobre el histograma del área analizada:\n"
            "• Otsu (1979): maximiza la varianza entre clases; puede fallar con cielo sobreexpuesto.\n"
            "• Mínimo (Prewitt y Mendelsohn 1966): suaviza el histograma hasta dejar dos modos\n"
            "  (dosel y cielo) y corta en el mínimo entre ellos; el más acertado en la comparación\n"
            "  de Glatthorn y Beckschäfer (2014). Si no hay dos modos se usa Otsu."
        )
        thr_btns_row.addWidget(self.auto_method_combo)
        self.otsu_btn = QPushButton("Calcular")
        self.otsu_btn.setToolTip("Calcular el nivel de corte con el método automático elegido.")
        self.otsu_btn.clicked.connect(self._on_otsu)
        thr_btns_row.addWidget(self.otsu_btn)
        thr_btns_row.addSpacing(12)

        self.glama_cut_btn = QPushButton("Recomendado (log-normal)")
        self.glama_cut_btn.setToolTip(
            "Nivel de corte recomendado: cruce de dos distribuciones log-normales ajustadas\n"
            "a los modos oscuro (dosel) y claro (cielo) del histograma del área analizada.\n"
            "Implementación independiente del procedimiento de la app GLAMA (Tichý 2016),\n"
            "reconstruido a partir de la app y verificado con sus resultados. Parte de 128\n"
            "(busca en ambos sentidos) e itera hasta estabilizarse. Requiere calibración."
        )
        self.glama_cut_btn.clicked.connect(self._on_glama_cut)
        thr_btns_row.addWidget(self.glama_cut_btn)

        self.adjust_btn = QPushButton("Ajustar umbral (vista previa en vivo)…")
        self.adjust_btn.setToolTip(
            "Abrir una ventana interactiva con vista previa en vivo de la\n"
            "clasificación cielo/dosel y un histograma arrastrable."
        )
        self.adjust_btn.clicked.connect(self._on_adjust_threshold)
        self.adjust_btn.setEnabled(False)
        thr_btns_row.addWidget(self.adjust_btn)
        thr_layout.addRow("", thr_btns_row)

        self.sky_bright_check = QCheckBox("El cielo es más brillante que el dosel")
        self.sky_bright_check.setChecked(True)
        thr_layout.addRow("", self.sky_bright_check)

        self.clean_check = QCheckBox(
            "Aplicar limpieza morfológica (apertura + cierre)"
        )
        # Desactivada por defecto: elimina claros reales de 1–2 px (sesgo hacia más cobertura)
        self.clean_check.setChecked(False)
        self.clean_check.setEnabled(HAS_SCIPY)
        self.clean_check.setToolTip(
            "Elimina píxeles aislados, pero también claros reales de 1–2 px en follaje fino,\n"
            "lo que sobreestima la cobertura. Úsela solo con imágenes ruidosas."
            + ("" if HAS_SCIPY else "\n(No disponible: falta el paquete scipy.)")
        )
        thr_layout.addRow("", self.clean_check)

        layout.addWidget(thr_group)

        # --- 4. Máscara de horizonte artificial, rango cenital y LAI (Tichý 2016) ---
        zen_group = QGroupBox(
            "4. Máscara de horizonte artificial, Rango cenital y LAI (Tichý, 2016)"
        )
        zen_layout = QFormLayout(zen_group)

        # Sincronización entre Ángulo cenital máximo (0–90°) y Máscara de horizonte (90° - cenit)
        angles_row = QHBoxLayout()

        self.zenith_max = QDoubleSpinBox()
        self.zenith_max.setRange(5.0, 90.0)
        self.zenith_max.setDecimals(1)
        self.zenith_max.setValue(27.0)            # v0.14.29: máscara estándar de 63° (cenit 0–27°), igual que el lote
        self.zenith_max.setSuffix(" ° (cenital máx.)")
        self.zenith_max.setToolTip(
            "Ángulo cenital máximo medido desde el cenit (0° = vertical hacia arriba).\n"
            "Equivale a: 90° − Máscara de horizonte artificial."
        )
        # zenith_max.valueChanged connected after UI build
        angles_row.addWidget(self.zenith_max)

        angles_row.addWidget(QLabel("⇄ Máscara de horizonte:"))

        self.horizon_mask_spin = QDoubleSpinBox()
        self.horizon_mask_spin.setRange(0.0, 85.0)
        self.horizon_mask_spin.setDecimals(1)
        self.horizon_mask_spin.setValue(63.0)
        self.horizon_mask_spin.setSuffix(" ° sobre horizonte")
        self.horizon_mask_spin.setToolTip(
            "Máscara de horizonte artificial en grados desde el horizonte hacia arriba.\n"
            "Tichý (2016, doi:10.1111/jvs.12350) demostró que una máscara > 45° produce\n"
            "el mejor ajuste (pendiente ~1 e intercepto 0) frente a la cobertura visual."
        )
        # horizon_mask_spin.valueChanged connected after UI build
        angles_row.addWidget(self.horizon_mask_spin)

        zen_layout.addRow("Delimitación hemisférica:", angles_row)

        # Máscara por direcciones (GLAMA: 1, 4, 8 o 16 direcciones)
        dirs_row = QHBoxLayout()
        self.horizon_dirs_combo = QComboBox()
        for n_dirs in (1, 4, 8, 16):
            self.horizon_dirs_combo.addItem(str(n_dirs), userData=n_dirs)
        dirs_row.addWidget(self.horizon_dirs_combo)
        self.horizon_dirs_edit = QLineEdit()
        self.horizon_dirs_edit.setPlaceholderText(
            "Ángulos sobre el horizonte, separados por «;» (dirección 1 = arriba, horario)"
        )
        self.horizon_dirs_edit.setToolTip(
            "Máscara de horizonte por direcciones: la dirección 1 está arriba en la imagen\n"
            "y las demás siguen en sentido\n"
            "horario cada 360°/n. Entre direcciones vecinas el límite se interpola\n"
            "linealmente. Ejemplo con 4 direcciones: 30; 60; 45; 10\n"
            "Con «1» se usa el valor único de «Máscara de horizonte»."
        )
        self.horizon_dirs_edit.setEnabled(False)
        self.horizon_dirs_combo.currentIndexChanged.connect(
            lambda _i: self.horizon_dirs_edit.setEnabled(self.horizon_dirs_combo.currentData() > 1)
        )
        dirs_row.addWidget(self.horizon_dirs_edit, stretch=1)
        zen_layout.addRow("Direcciones de máscara:", dirs_row)

        # Calculadora de Tabla 1 del Manual de GLAMA (Parcela x Altura del dosel)
        table1_row = QHBoxLayout()
        self.plot_size_combo = QComboBox()
        self.plot_size_combo.addItem("10 × 10 m", userData="10x10")
        self.plot_size_combo.addItem("15 × 15 m", userData="15x15")
        self.plot_size_combo.addItem("20 × 20 m", userData="20x20")
        self.plot_size_combo.addItem("25 × 25 m", userData="25x25")
        self.plot_size_combo.setCurrentIndex(1)
        table1_row.addWidget(QLabel("Parcela:"))
        table1_row.addWidget(self.plot_size_combo)

        self.canopy_height_combo = QComboBox()
        for h_m in (10, 15, 20, 30, 40):
            self.canopy_height_combo.addItem("{} m".format(h_m), userData=h_m)
        self.canopy_height_combo.setCurrentIndex(1)
        table1_row.addWidget(QLabel("Altura dosel:"))
        table1_row.addWidget(self.canopy_height_combo)

        apply_t1_btn = QPushButton("Aplicar máscara recomendada (Tabla 1)")
        apply_t1_btn.setToolTip(
            "Calcula y aplica el ángulo de máscara de horizonte artificial de la Tabla 1\n"
            "(Tichý 2015) según el tamaño de la parcela y la altura de los árboles."
        )
        apply_t1_btn.clicked.connect(self._on_apply_glama_table1)
        table1_row.addWidget(apply_t1_btn)
        zen_layout.addRow("Máscara según parcela:", table1_row)

        self.n_rings = QSpinBox()
        self.n_rings.setRange(1, 10)
        self.n_rings.setValue(4)
        self.n_rings.setToolTip(
            "Anillos de la tabla de detalle, del CSV y de la tabla por sectores. Los índices\n"
            "usan siempre 90 anillos de 1/90 del radio. Los anillos de referencia de la\n"
            "vista «Anillos cenitales» se dibujan cada 5° o 10°, aparte.")
        zen_layout.addRow("Número de anillos cenitales:", self.n_rings)

        self.n_sectors_combo = QComboBox()
        for n_sec in (0, 4, 8, 12, 16):
            self.n_sectors_combo.addItem(
                "Sin sectores" if n_sec == 0 else "{} sectores".format(n_sec), userData=n_sec)
        self.n_sectors_combo.setCurrentIndex(2)
        self.n_sectors_combo.setToolTip(
            "Fracción de claros por anillo × sector de acimut (sector 1 arriba, sentido\n"
            "horario). Útil para detectar un sector con sol directo u obstrucciones.")
        zen_layout.addRow("Sectores de acimut:", self.n_sectors_combo)

        self.glama_geometry_check = QCheckBox(
            "Reproducir la geometría de pantalla de GLAMA (solo estudios de transición)")
        self.glama_geometry_check.setToolTip(
            "Calcula los índices como la app GLAMA: recorte cuadrado central de la foto\n"
            "reducido a {0} × {0} px, centrado en una vista de {0} × {1} px cuyas franjas negras\n"
            "cuentan como dosel, y radio = «Hemisph. radius» de GLAMA. Reproduce los sesgos\n"
            "de la app (escala 3:4 en fotos 4:3, franja negra contada como dosel); úselo solo\n"
            "para comparar con resultados antiguos de GLAMA, nunca para el valor oficial.".format(
                GLAMA_VIEW_W, GLAMA_VIEW_H))
        geo_row = QHBoxLayout()
        geo_row.addWidget(self.glama_geometry_check, stretch=1)
        geo_row.addWidget(QLabel("Desplazamiento del centro:"))
        self.glama_dy_spin = QDoubleSpinBox()
        self.glama_dy_spin.setRange(-400.0, 400.0)
        self.glama_dy_spin.setDecimals(1)
        self.glama_dy_spin.setValue(GLAMA_CENTER_DY)
        self.glama_dy_spin.setSuffix(" px")
        self.glama_dy_spin.setToolTip(
            "Posición vertical del centro del hemisferio de GLAMA respecto del centro de su\n"
            "vista (px de la vista de {} px; + = hacia abajo). {:g} px reproduce exactamente\n"
            "las pantallas de resultados de GLAMA en el teléfono del autor («in Frame» y «Part\n"
            "of Hemisph.»). Para otro teléfono, ajústelo hasta igualar «Part of Hemisph.».".format(
                GLAMA_VIEW_W, GLAMA_CENTER_DY))
        geo_row.addWidget(self.glama_dy_spin)
        zen_layout.addRow("", geo_row)

        self.lai_zenith_max = QDoubleSpinBox()
        self.lai_zenith_max.setRange(10.0, 90.0)
        self.lai_zenith_max.setDecimals(1)
        self.lai_zenith_max.setValue(LAI_DEFAULT_ZENITH_MAX_DEG)
        self.lai_zenith_max.setSuffix(" ° (cenital máx. LAI)")
        self.lai_zenith_max.setToolTip(
            "Rango cenital usado para el LAI efectivo, independiente de la máscara de\n"
            "horizonte (se limita al semiángulo del lente). Por defecto 0–60°.\n"
            "Con rangos < {:.0f}° el LAI es solo indicativo.".format(LAI_MIN_RELIABLE_ZENITH_DEG)
        )
        zen_layout.addRow("Rango cenital para LAI:", self.lai_zenith_max)

        preset_row = QHBoxLayout()
        for label, val in [
            ("★ 0–27° (Másc. 63°, estándar)", 27.0),
            ("0–30° (Másc. 60°, Tichý 2016)", 30.0),
            ("0–45° (Másc. 45°)", 45.0),
            ("0–60° (Másc. 30°)", 60.0),
            ("0–75° (Másc. 15°)", 75.0),
            ("0–90° (Sin máscara)", 90.0),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, v=val: self.zenith_max.setValue(v))
            preset_row.addWidget(btn)
        zen_layout.addRow("Preajustes rápidos:", preset_row)

        layout.addWidget(zen_group)

        # --- 5. Ejecutar y exportar ---
        run_group = QGroupBox("5. Ejecución e informes (HTML / CSV)")
        run_layout = QHBoxLayout(run_group)

        self.run_btn = QPushButton("▶ Ejecutar análisis")
        self.run_btn.setStyleSheet("font-weight: bold; padding: 6px 12px;")
        self.run_btn.clicked.connect(self._on_run)
        run_layout.addWidget(self.run_btn)

        self.html_btn = QPushButton("Exportar informe HTML…")
        self.html_btn.setToolTip(
            "Generar un informe HTML autocontenido con parámetros de calibración,\n"
            "nombre de la imagen, todos los resultados y gráficos."
        )
        self.html_btn.clicked.connect(self._on_export_html)
        self.html_btn.setEnabled(False)
        run_layout.addWidget(self.html_btn)

        self.export_btn = QPushButton("Exportar resultados a CSV…")
        self.export_btn.clicked.connect(self._on_export_csv)
        self.export_btn.setEnabled(False)
        run_layout.addWidget(self.export_btn)

        layout.addWidget(run_group)

        # --- 6. Visualización y capas QGIS ---
        viz_group = QGroupBox("6. Visualización y Capas en QGIS")
        viz_layout = QVBoxLayout(viz_group)

        opts_row = QHBoxLayout()

        opts_row.addWidget(QLabel("Anillos cada:"))
        self.viz_ring_interval = QComboBox()
        self.viz_ring_interval.addItem("Automático (según lo que cubre la foto)", userData=None)
        for step in (1.0, 2.0, 2.5, 5.0, 10.0, 15.0):
            self.viz_ring_interval.addItem("{:g}°".format(step), userData=step)
        opts_row.addWidget(self.viz_ring_interval)

        self.viz_show_sky_overlay = QCheckBox("Cielo en naranja")
        self.viz_show_sky_overlay.setChecked(True)
        opts_row.addWidget(self.viz_show_sky_overlay)

        self.viz_outside_mask = QCheckBox("Sombrear fuera de la máscara")
        self.viz_outside_mask.setChecked(True)
        opts_row.addWidget(self.viz_outside_mask)

        opts_row.addStretch()
        viz_layout.addLayout(opts_row)

        viz_btn_row = QHBoxLayout()

        self.glama_viz_btn = QPushButton("Añadir «Anillos cenitales»")
        self.glama_viz_btn.clicked.connect(self._on_add_glama_visualization)
        self.glama_viz_btn.setEnabled(False)
        viz_btn_row.addWidget(self.glama_viz_btn)

        self.threshold_viz_btn = QPushButton("Añadir máscara de umbral")
        self.threshold_viz_btn.clicked.connect(self._on_add_threshold_overlay)
        self.threshold_viz_btn.setEnabled(False)
        viz_btn_row.addWidget(self.threshold_viz_btn)

        self.image_btn = QPushButton("Añadir imagen original")
        self.image_btn.clicked.connect(self._on_add_image_raster)
        self.image_btn.setEnabled(False)
        viz_btn_row.addWidget(self.image_btn)

        self.gps_point_btn = QPushButton("Añadir punto GPS al mapa")
        self.gps_point_btn.setToolTip(
            "Crear o actualizar una capa vectorial de puntos en QGIS con las\n"
            "coordenadas GPS EXIF y todos los resultados del análisis."
        )
        self.gps_point_btn.clicked.connect(self._on_add_gps_point_layer)
        self.gps_point_btn.setEnabled(False)
        viz_btn_row.addWidget(self.gps_point_btn)

        viz_layout.addLayout(viz_btn_row)
        layout.addWidget(viz_group)
        layout.addStretch()

        scroll.setWidget(form_container)
        self.param_splitter.addWidget(scroll)

        # Panel inferior del divisor: Resumen de resultados
        results_container = QWidget()
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 4, 0, 0)
        results_lbl = QLabel("<b>Resultados del análisis (basado en Tichý 2016):</b>")
        results_layout.addWidget(results_lbl)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet("font-family: monospace;")
        self.results_text.setMinimumHeight(110)
        results_layout.addWidget(self.results_text, stretch=1)

        self.param_splitter.addWidget(results_container)
        self.param_splitter.setStretchFactor(0, 3)
        self.param_splitter.setStretchFactor(1, 2)
        self.param_splitter.setSizes([530, 240])

        param_tab_layout.addWidget(self.param_splitter)
        self.tabs.addTab(param_tab, "Parámetros")

    def _build_log_tab(self):
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)

        info_lbl = QLabel(
            "<b>Ventana de Registro de Ejecución:</b> Muestra la bitácora detallada con fecha y hora "
            "de todas las operaciones de carga, calibración, máscara de horizonte, cálculo y exportación."
        )
        info_lbl.setWordWrap(True)
        log_layout.addWidget(info_lbl)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 10pt;")
        log_layout.addWidget(self.log_text, stretch=1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copiar registro al portapapeles")
        copy_btn.clicked.connect(self._on_copy_log)
        btn_row.addWidget(copy_btn)

        save_btn = QPushButton("Guardar registro (.txt)…")
        save_btn.clicked.connect(self._on_save_log)
        btn_row.addWidget(save_btn)

        clear_btn = QPushButton("Limpiar registro")
        clear_btn.clicked.connect(self.log_text.clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()
        log_layout.addLayout(btn_row)

        self.tabs.addTab(log_tab, "Registro")

    def _build_help_tab(self):
        help_tab = QWidget()
        help_layout = QVBoxLayout(help_tab)

        self.full_help_browser = QTextBrowser()
        self.full_help_browser.setOpenExternalLinks(True)
        self.full_help_browser.setHtml(FULL_HELP_HTML)
        help_layout.addWidget(self.full_help_browser, stretch=1)

        self.tabs.addTab(help_tab, "Ayuda")

    def _build_short_help_panel(self):
        self.short_help_panel = QWidget()
        self.short_help_panel.setMinimumWidth(220)
        sh_layout = QVBoxLayout(self.short_help_panel)
        sh_layout.setContentsMargins(4, 4, 4, 4)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("<b>Ayuda corta:</b>"))
        self.short_help_combo = QComboBox()
        self.short_help_combo.addItem("Resumen rápido", userData="resumen")
        self.short_help_combo.addItem("1. Imagen y EXIF", userData="imagen")
        self.short_help_combo.addItem("2. Calibración del lente", userData="calibracion")
        self.short_help_combo.addItem("3. Umbral cielo / dosel", userData="umbral")
        self.short_help_combo.addItem("4–6. Máscara, métricas y vistas", userData="glama")
        # short_help_combo.currentIndexChanged connected after UI build
        top_row.addWidget(self.short_help_combo, stretch=1)
        sh_layout.addLayout(top_row)

        self.short_help_browser = QTextBrowser()
        self.short_help_browser.setOpenExternalLinks(True)
        self.short_help_browser.setHtml(SHORT_HELP_TOPICS["resumen"])
        sh_layout.addWidget(self.short_help_browser, stretch=1)

    # ------------------------------------------------------------------
    # Sincronización de Máscara de Horizonte Artificial (GLAMA)
    # ------------------------------------------------------------------
    def _on_zenith_max_changed(self, val):
        self.horizon_mask_spin.blockSignals(True)
        self.horizon_mask_spin.setValue(max(0.0, 90.0 - float(val)))
        self.horizon_mask_spin.blockSignals(False)
        self._mark_cut_stale("la máscara")

    def _on_horizon_mask_changed(self, val):
        self.zenith_max.blockSignals(True)
        self.zenith_max.setValue(max(5.0, 90.0 - float(val)))
        self.zenith_max.blockSignals(False)
        self._mark_cut_stale("la máscara")

    def _mark_cut_stale(self, what):
        """
        v0.14.38: un corte automático o recomendado se calculó con el área analizada, el canal y la
        calibración del momento. Si cambian, el método registrado lo indica hasta que se recalcule.
        """
        auto = getattr(self, "_cut_auto", None)
        if auto is None or getattr(self, "_cut_for", None) != getattr(self, "image_path", None):
            return
        if "calculado antes de cambiar" in (self.cut_method or ""):
            return
        self.cut_method = "{}, calculado antes de cambiar {}".format(self.cut_method, what)
        self._log("El nivel de corte {} se calculó antes de cambiar {}: pulse de nuevo «Recomendado» o "
                  "«Calcular» para recalcularlo.".format(self.threshold_spin.value(), what), "WARN")

    def _on_apply_glama_table1(self):
        self._set_short_help_topic("glama")
        plot_key = self.plot_size_combo.currentData()
        height_m = self.canopy_height_combo.currentData()
        horiz_deg, zen_deg = recommended_horizon_mask_deg(plot_key, height_m)
        self.zenith_max.setValue(zen_deg)
        self._log(
            "Máscara de horizonte (Tabla 1) aplicada para parcela {} m y altura {} m: "
            "horizonte = {:.0f}° (ángulo cenital máx. = {:.0f}°).".format(
                plot_key, height_m, horiz_deg, zen_deg
            )
        )

    # ------------------------------------------------------------------
    # Registro (Log) y Ayuda corta
    # ------------------------------------------------------------------
    def _log(self, message, level="INFO"):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "[{}] [{}] {}".format(ts, level, message)
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.append(line)

    def _on_copy_log(self):
        QApplication.clipboard().setText(self.log_text.toPlainText())
        QMessageBox.information(
            self, "Registro copiado",
            "El contenido del registro se copió al portapapeles."
        )

    def _default_output_path(self, filename):
        """Ruta propuesta para guardar: la carpeta de la foto analizada (o de la foto cargada)."""
        src = None
        if getattr(self, "last_results", None):
            src = self.last_results.get("image_path")
        src = src or getattr(self, "image_path", None)
        folder = os.path.dirname(os.path.abspath(src)) if src else ""
        return os.path.join(folder, filename) if folder and os.path.isdir(folder) else filename

    def _on_save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar registro de CobDosel", self._default_output_path("Registro_CobDosel.txt"),
            "Archivos de texto (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(
                self, "Registro guardado",
                "Registro guardado en:\n" + str(path)
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))

    def _on_short_help_topic_changed(self, idx):
        key = self.short_help_combo.itemData(idx)
        html_content = SHORT_HELP_TOPICS.get(key, SHORT_HELP_TOPICS["resumen"])
        self.short_help_browser.setHtml(html_content)

    def _set_short_help_topic(self, key):
        for i in range(self.short_help_combo.count()):
            if self.short_help_combo.itemData(i) == key:
                self.short_help_combo.setCurrentIndex(i)
                break

    def _toggle_short_help(self):
        vis = not self.short_help_panel.isVisible()
        self.short_help_panel.setVisible(vis)
        self.toggle_short_help_btn.setText(
            "Ocultar ayuda corta" if vis else "Mostrar ayuda corta"
        )

    def cleanup_temp_files(self, only_unused=False):
        """
        Borra los PNG temporales generados por el complemento.
        only_unused=True conserva los que siguen cargados como capas en el proyecto
        (borrarlos dejaría capas rotas).
        """
        in_use = set()
        if only_unused:
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    in_use.add(os.path.normcase(os.path.abspath(lyr.source())))
                except (RuntimeError, AttributeError) as e:
                    self._log("[cleanup] capa no legible: {}".format(e), "DEBUG")
        remaining = []
        for path in list(self._temp_files):
            if not path or not os.path.isfile(path):
                continue
            if os.path.normcase(os.path.abspath(path)) in in_use:
                remaining.append(path)
                continue
            try:
                os.remove(path)
            except OSError as e:
                self._log("[cleanup] No se pudo borrar {}: {}".format(path, e), "DEBUG")
                remaining.append(path)
        self._temp_files = remaining

    # ------------------------------------------------------------------
    # Funciones auxiliares
    # ------------------------------------------------------------------
    def _current_projection_code(self):
        return self.projection_combo.currentData()

    def _current_channel_mode(self):
        return self.channel_combo.currentData()

    def _populate_projections(self, is_fisheye, keep=None):
        """Llena «Modelo de proyección» solo con los modelos del tipo de lente (v0.14.26).

        Lente regular / smartphone: Rectilínea (por defecto) y Lineal (compatible con Polar de GLAMA).
        Ojo de pez: Polar (por defecto), Equisólida, Ortográfica y Estereográfica.
        """
        allowed = PROJECTIONS_FISHEYE if is_fisheye else PROJECTIONS_REGULAR
        labels = dict(list_projections())
        target = keep if keep in allowed else allowed[0]
        self.projection_combo.blockSignals(True)
        self.projection_combo.clear()
        for code in allowed:
            self.projection_combo.addItem(labels[code], userData=code)
        self.projection_combo.setCurrentIndex(allowed.index(target))
        self.projection_combo.blockSignals(False)
        if hasattr(self, "lens_combo"):
            self._update_projection_tooltip()

    def _set_projection_by_code(self, code):
        codes = [
            self.projection_combo.itemData(i)
            for i in range(self.projection_combo.count())
        ]
        if code in codes:
            self.projection_combo.setCurrentIndex(codes.index(code))

    def _update_projection_tooltip(self):
        code = self._current_projection_code()
        note = projection_note(code)
        if is_fisheye_projection(code):
            head = ("Modelos para lente ojo de pez:\n\n"
                    "• Polar (equidistante): Nikkor 8mm y la mayoría de ojo de pez científicos\n"
                    "• Equisólida (igual área): Nikkor 10.5mm, Sigma 8mm\n"
                    "• Ortográfica: diseños clásicos de ojo de pez («Angular» de GLAMA)\n"
                    "• Estereográfica: algunos ojo de pez y gran angular\n\n")
        else:
            head = ("Modelos para lente regular / smartphone:\n\n"
                    "• Rectilínea (geométrica), predeterminado: r = f·tan θ. Es la geometría de la cámara\n"
                    "  principal (1x) de los teléfonos, que corrigen la distorsión por software; si la lente es\n"
                    "  rectilínea, es exacta en todos los ángulos y con cualquier tamaño de círculo\n"
                    "  (Pixel 10: misma focal con círculos de 12,1, 20,6 y 23,4 cm, ±0,2 %).\n"
                    "• Lineal (compatible con Polar de GLAMA): θ ∝ r, exacto solo en el borde del círculo de\n"
                    "  calibración; para comparar con resultados de GLAMA o con calibraciones anteriores.\n\n")
        label = dict(list_projections()).get(code, code)
        self.projection_combo.setToolTip(head + "Seleccionado: «" + str(label) + "»\n" + str(note))

    def _on_channel_changed(self, idx):
        self._set_short_help_topic("umbral")
        self._mark_cut_stale("el canal de color")
        if self.image_array is not None:
            mode = self._current_channel_mode()
            self.gray_array = extract_channel(self.image_array, mode)
            self._log(
                "Canal de color cambiado a '{}'.".format(
                    CHANNEL_LABELS.get(mode, mode)
                )
            )
            if self.last_results is not None:
                self.calib_result.setText(
                    self.calib_result.text().split("\n")[0]
                    + "\n⚠ El canal de color cambió — vuelva a ejecutar el análisis."
                )

    def _analysis_valid_mask(self, r_px=None, include_horizon_mask=False):
        """
        Máscara del área válida según la calibración (no según el combo):
        - ojo de pez: círculo de radio virtual_radius_px;
        - lente regular: todo el fotograma (desde 0.11.0 también las esquinas fuera del
          círculo inscrito, como GLAMA).
        include_horizon_mask=True limita además al área no enmascarada (cenit ≤ máscara,
        única o por direcciones): es el área que usan Otsu y la vista previa del umbral.
        Sin calibración: toda la foto con «Lente regular»; con «Ojo de pez» se excluyen los píxeles
        casi negros (esquinas fuera del círculo de imagen).
        Devuelve None si todo el fotograma es válido.
        """
        if self.image_array is None:
            return None
        h, w = self.image_array.shape[:2]
        cal = self.calibration
        if cal is not None and self.center_xy is not None:
            if r_px is None:
                r_px = compute_radius_grid((h, w), self.center_xy)
            base = None
            if cal.get("lens_type") == "fisheye":
                vr = cal.get("virtual_radius_px")
                base = (r_px <= float(vr)) if vr else None
            if not include_horizon_mask:
                return base
            scaled = scale_calibration_to_image(cal, w, h)
            zen = compute_zenith_grid(r_px, scaled)
            try:
                _zarg, angles = self._horizon_mask_arg()
            except ValueError:
                angles = None
            if angles:
                az = azimuth_grid((h, w), self.center_xy)
                unmasked = zen <= horizon_zenith_limit(az, angles) + 1e-9
            else:
                unmasked = zen <= float(self.zenith_max.value()) + 1e-9
            return unmasked if base is None else (base & unmasked)
        # v0.14.38: sin calibración y con «Lente regular» se usa toda la foto (antes se excluían los
        # píxeles casi negros también aquí, y en dosel denso eso quitaba sombra real del histograma).
        if self.lens_combo.currentIndex() != 0:
            return None
        if self.image_array.ndim == 3:
            non_black = self.image_array.max(axis=2) > 8
        else:
            non_black = self.image_array > 8
        if non_black.mean() > 0.98:
            return None
        return non_black

    def _update_run_button(self):
        has_image = self.image_array is not None
        has_calibration = (
            self.calibration is not None
            and self.center_xy is not None
        )
        self.run_btn.setEnabled(has_image and has_calibration)

    def _load_image_into_dialog(self, path):
        self._set_short_help_topic("imagen")
        if path.lower().endswith((".heic", ".heif")) and not HEIF_SUPPORTED:
            QMessageBox.warning(
                self, "Formato HEIC no disponible",
                "Las imágenes HEIC/HEIF requieren el paquete 'pillow-heif'.\n\n"
                "Instálelo con:\n    pip install pillow-heif\n\n"
                "O convierta la imagen a JPEG/PNG primero."
            )
            self._log("Intento de carga HEIC sin pillow-heif: " + path, "WARN")
            return False

        try:
            img, scale, orig_wh = load_oriented_rgb_image(
                path, max_dim=MAX_ANALYSIS_DIM
            )
            self.image_path = path
            self.path_edit.setText(path)
            self.original_image_size = orig_wh
            self.image_load_scale = scale
            self.image_array = np.array(img)
            self.gray_array = extract_channel(
                self.image_array, self._current_channel_mode()
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "No se pudo cargar la imagen:\n" + str(e)
            )
            self._log("Error al cargar imagen '{}': {}".format(path, e), "ERROR")
            return False

        self.exif_data = extract_exif(path)
        parts = []
        if self.exif_data.get("has_gps"):
            parts.append(
                "GPS: {:.6f}, {:.6f}".format(
                    self.exif_data["latitude"], self.exif_data["longitude"]
                )
            )
        elif self.exif_data.get("exif_error"):
            parts.append("EXIF ilegible: " + str(self.exif_data["exif_error"])[:80])
            self._log("EXIF ilegible en '{}': {}".format(
                os.path.basename(path), self.exif_data["exif_error"]), "WARN")
        else:
            parts.append("Sin GPS en EXIF")
        if self.exif_data.get("capture_datetime"):
            parts.append("captura: " + self.exif_data["capture_datetime"])
        parts.append(
            "tamaño: {}×{} px".format(
                self.image_array.shape[1], self.image_array.shape[0]
            )
        )
        if self.original_image_size != (
            self.image_array.shape[1], self.image_array.shape[0]
        ):
            parts.append(
                "original: {}×{} px".format(
                    self.original_image_size[0], self.original_image_size[1]
                )
            )
        self.exif_label.setText("  |  ".join(parts))

        self._log(
            "Imagen cargada: '{}' ({}x{} px, escala={:.4f}, GPS={}).".format(
                os.path.basename(path),
                self.image_array.shape[1],
                self.image_array.shape[0],
                self.image_load_scale,
                "Sí" if self.exif_data.get("has_gps") else "No",
            )
        )

        # El nivel de corte es propio de cada foto (0.14.13): el valor queda en el control, pero se
        # marca como heredado hasta que se calcule o ajuste para la foto nueva.
        if self._cut_for is not None and self._cut_for != path:
            self._log("Nivel de corte {} heredado de la foto anterior: calcúlelo o ajústelo para esta "
                      "foto.".format(self.threshold_spin.value()), "WARN")
        if self._cut_for != path:
            self.cut_method = "heredado (no calculado para esta foto)"
            self._cut_auto = None
            self._cut_for = None

        # Reiniciar estado aguas abajo. La calibración se conserva (v0.14.27): se vuelve a aplicar
        # a esta foto al final, si es de la misma cámara y proporción.
        prev_cal = self.calibration
        self.calibration = None
        self.center_xy = None
        self.sky_mask = None
        self.last_results = None
        self.export_btn.setEnabled(False)
        self.html_btn.setEnabled(False)
        self.glama_viz_btn.setEnabled(False)
        self.threshold_viz_btn.setEnabled(False)
        self.image_btn.setEnabled(True)
        self.gps_point_btn.setEnabled(False)
        self.save_cal_btn.setEnabled(False)
        self.calib_result.setText("Sin calibrar.")
        self.results_text.clear()
        self.adjust_btn.setEnabled(True)

        self._carry_calibration(prev_cal)
        self._update_run_button()
        return True

    def _calibration_photo_aspect(self, cal):
        """Proporción (lado mayor / menor) de la foto en la que se midió la calibración, o None."""
        meta = cal.get("calibration_metadata") or {}
        meas = cal.get("measurement") or meta.get("measurement") or {}
        ref = (meas.get("image_size") or meta.get("original_image_size") or meta.get("image_size")
               or ([cal.get("image_width_px"), cal.get("image_height_px")]
                   if cal.get("image_width_px") and cal.get("image_height_px") else None))
        if not ref:
            return None
        return max(float(ref[0]), float(ref[1])) / min(float(ref[0]), float(ref[1]))

    def _carry_calibration(self, prev_cal):
        """
        v0.14.27: conserva la calibración de la foto anterior (reescalada a esta foto) o, en la primera
        foto, aplica la última calibración usada. No se aplica si la foto es de otra cámara/lente o de
        otra proporción: se avisa y se pide calibrar.
        """
        source, origin = prev_cal, "se mantiene de la foto anterior"
        if source is None and not self._autoload_done:
            self._autoload_done = True
            last = get_last_calibration()
            if last:
                try:
                    source = load_calibration(last)
                    self._cal_name = last
                    origin = "última calibración usada, aplicada automáticamente"
                except Exception as e:      # archivo dañado o borrado: se sigue sin calibrar
                    self._log("No se pudo aplicar la última calibración «{}»: {}".format(last, e), "WARN")
                    source = None
        if source is None:
            return
        name = self._cal_name or "sin guardar"
        h, w = self.image_array.shape[:2]
        reasons = []
        a_ref = self._calibration_photo_aspect(source)
        a_now = max(w, h) / float(min(w, h))
        if a_ref and abs(a_ref - a_now) > 0.01 * a_now:
            reasons.append("proporción de la foto distinta ({:.3f} frente a {:.3f})".format(a_now, a_ref))
        cam_ok, cam_why = compare_cameras(source.get("camera"), self._current_camera())
        if cam_ok is False:
            reasons.extend(cam_why)
        if reasons:
            self._cal_name = None
            msg = ("La calibración «{}» no corresponde a esta foto: {}.\nCargue o calcule la calibración de "
                   "esta cámara.").format(name, "; ".join(reasons))
            self._log(msg, "WARN")
            self.calib_result.setText("Sin calibrar. " + msg.replace("\n", " "))
            QMessageBox.warning(self, "Calibración no aplicable", msg)
            return
        self._apply_calibration(source, name, interactive=False,
                                title="Calibración «{}» ({})".format(name, origin))

    # ------------------------------------------------------------------
    # Carga de imagen y cambio de lente
    # ------------------------------------------------------------------
    def _on_browse(self):
        filters = "Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"
        if HEIF_SUPPORTED:
            filters += " *.heic *.heif"
        filters += ");;Todos los archivos (*)"

        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir fotografía de dosel", "", filters
        )
        if path:
            self._load_image_into_dialog(path)

    def _on_lens_changed(self, idx, update_help=True):
        if update_help:
            self._set_short_help_topic("calibracion")
        is_fisheye = (idx == 0)
        self.detect_btn.setEnabled(is_fisheye)
        # La calibración por círculo de referencia es solo para lentes regulares
        self.calibrate_btn.setEnabled(not is_fisheye)
        self.circle_diameter.setEnabled(not is_fisheye)
        self.camera_height.setEnabled(not is_fisheye)
        self.pixel_diameter.setEnabled(not is_fisheye)
        self.measure_image_btn.setEnabled(not is_fisheye)
        self.measure_file_btn.setEnabled(not is_fisheye)

        # v0.14.38: la lista de modelos muestra siempre el modelo de la calibración activa. Si la
        # calibración activa es de otro tipo de lente, queda «en espera» (no se usa) y vuelve al
        # elegir de nuevo su tipo; así la lista y el análisis nunca difieren.
        cal = self.calibration
        parked = getattr(self, "_parked_cal", None)
        if cal is not None and is_fisheye_projection(cal.get("projection")) != is_fisheye:
            self._parked_cal = (cal, self._cal_name, self.center_xy)
            self.calibration = None
            self.center_xy = None
            self.save_cal_btn.setEnabled(False)
            name = self._cal_name or "sin guardar"
            tipo = "Ojo de pez" if not is_fisheye else "Lente regular / smartphone"
            msg = ("Sin calibración para este tipo de lente. La calibración «{}» ({}) queda en espera: no se usa "
                   "en el análisis y vuelve al elegir de nuevo «{}».".format(
                       name, cal.get("projection_label", cal.get("projection")), tipo))
            self._calib_base = msg
            if getattr(self, "calib_result", None):
                self.calib_result.setText(msg)
            self._log(msg, "WARN")
            self._update_run_button()
        elif cal is None and parked and is_fisheye_projection(parked[0].get("projection")) == is_fisheye:
            self.calibration, self._cal_name, self.center_xy = parked
            self._parked_cal = None
            self.save_cal_btn.setEnabled(True)
            self._show_calibration_summary(self.calibration, "Calibración recuperada («{}»)".format(
                self._cal_name or "sin guardar"))
            self._log("Calibración en espera recuperada al volver al tipo de lente.")
            self._update_run_button()
        cal_proj = (self.calibration or {}).get("projection")
        self._proj_sync_off = True
        try:
            self._populate_projections(is_fisheye, keep=cal_proj)
        finally:
            self._proj_sync_off = False

    def _on_projection_changed(self, *_a):
        """
        v0.14.34: el modelo elegido debe ser el de la calibración activa. Con una calibración por
        círculo D/H se recalcula con los mismos D, H y diámetro medido; con otras calibraciones
        (radio de GLAMA, círculo de 180° detectado) se indica cómo aplicar el modelo nuevo.
        """
        if self._proj_sync_off:
            return
        cal = self.calibration
        code = self._current_projection_code()
        parked = getattr(self, "_parked_cal", None)
        if cal is None and parked and code and parked[0].get("projection") == code:
            # vuelve el modelo de la calibración en espera → se recupera
            self.calibration, self._cal_name, self.center_xy = parked
            self._parked_cal = None
            self.save_cal_btn.setEnabled(True)
            self._show_calibration_summary(self.calibration, "Calibración recuperada («{}»)".format(
                self._cal_name or "sin guardar"))
            self._update_run_button()
            return
        if not cal or not code or cal.get("projection") == code:
            return
        label = dict(list_projections()).get(code, code)
        meas_mode = (cal.get("measurement") or {}).get("mode")
        is_glama = bool(cal.get("glama_radius_px")) or meas_mode == "glama_radius"
        is_circle = bool(cal.get("circle_diameter_cm") and cal.get("camera_height_cm")
                         and cal.get("pixel_diameter_px") and not is_glama)
        is_detected = (not is_circle and not is_glama and cal.get("lens_type") == "fisheye"
                       and cal.get("r_image_half_px") and is_fisheye_projection(code))
        if is_detected:
            self._recalc_detected_fisheye(cal, code, label)
            return
        if not is_circle:
            # v0.14.38: la calibración con el radio de GLAMA no se puede recalcular con otro modelo. Queda en
            # espera (no se usa); el modelo elegido se aplica a la próxima calibración y, si se vuelve a elegir
            # el modelo de GLAMA, se recupera. Así la lista y el análisis nunca difieren.
            self._parked_cal = (cal, self._cal_name, self.center_xy)
            self.calibration = None
            self.center_xy = None
            self.save_cal_btn.setEnabled(False)
            old_label = cal.get("projection_label", cal.get("projection"))
            msg = ("Sin calibración con «{}». La calibración con el radio de GLAMA («{}», {}) conserva el modelo de "
                   "GLAMA y queda en espera: no se usa en el análisis y vuelve al elegir de nuevo «{}». Para usar "
                   "«{}», calibre con el círculo de referencia.".format(
                       label, self._cal_name or "sin guardar", old_label, old_label, label))
            self._calib_base = msg
            self.calib_result.setText(msg)
            self._log(msg, "WARN")
            self._update_run_button()
            return
        old_label = cal.get("projection_label", cal.get("projection"))
        try:
            new = calibrate_regular_lens(
                circle_diameter_cm=cal["circle_diameter_cm"],
                camera_height_cm=cal["camera_height_cm"],
                pixel_diameter_px=cal["pixel_diameter_px"],
                image_width_px=cal.get("image_width_px") or self.image_array.shape[1],
                image_height_px=cal.get("image_height_px") or self.image_array.shape[0],
                projection=code,
                glama_compat=bool(cal.get("glama_compat")),
            )
        except Exception as e:
            QMessageBox.critical(self, "Error de calibración", str(e))
            self._log("No se pudo recalcular la calibración con «{}»: {}".format(label, e), "ERROR")
            return
        for key in ("measurement", "camera", "center_xy"):
            if cal.get(key) is not None and new.get(key) is None:
                new[key] = cal[key]
        fc = self._focal_check(new)
        new["focal_check"] = {k: fc[k] for k in ("level", "focal_mm", "ref_kind", "ref_name", "ref_mm", "diff_pct")}
        self.calibration = new
        self._cal_name = None      # calibración modificada: «sin guardar» hasta que se guarde
        self.save_cal_btn.setEnabled(True)
        self._show_calibration_summary(new, "Calibración recalculada con el modelo «{}»".format(label))
        stale = " Ejecute de nuevo el análisis: los resultados mostrados usan el modelo anterior." if self.last_results else ""
        self._log("Calibración recalculada al cambiar el modelo: «{}» → «{}» (mismos D = {:g} cm, H = {:g} cm y "
                  "diámetro {:.2f} px); R = {:.1f} px.{}".format(
                      old_label, label, new["circle_diameter_cm"], new["camera_height_cm"],
                      new["pixel_diameter_px"], new.get("virtual_radius_px") or 0.0, stale))
        if stale:
            self._set_calib_note("ⓘ" + stale)
        self._update_run_button()

    def _set_calib_note(self, note):
        """Muestra una nota debajo del resumen de la calibración (reemplaza la nota anterior)."""
        base = getattr(self, "_calib_base", None) or self.calib_result.text()
        self.calib_result.setText(base + ("\n" + note if note else ""))

    def _recalc_detected_fisheye(self, cal, code, label):
        """Calibración ojo de pez detectada: se recalcula con el mismo radio y centro y el modelo nuevo."""
        try:
            new = calibrate_fisheye_from_radius(
                cal["r_image_half_px"], projection=code, center_xy=cal.get("center_xy"),
                image_width_px=cal.get("image_width_px"), image_height_px=cal.get("image_height_px"))
        except Exception as e:
            QMessageBox.critical(self, "Error de calibración", str(e))
            return
        for key in ("measurement", "camera"):
            if cal.get(key) is not None:
                new[key] = cal[key]
        self.calibration = new
        self._cal_name = None
        self.save_cal_btn.setEnabled(True)
        self._show_calibration_summary(new, "Calibración ojo de pez recalculada con el modelo «{}»".format(label))
        if self.last_results:
            self._set_calib_note("ⓘ Ejecute de nuevo el análisis: los resultados mostrados usan el modelo anterior.")
        self._log("Calibración ojo de pez recalculada con «{}» (mismo radio {:.1f} px y centro).".format(
            label, cal["r_image_half_px"]))
        self._update_run_button()

    # ------------------------------------------------------------------
    # Medición del círculo de referencia
    # ------------------------------------------------------------------
    def _on_measure_in_image(self):
        self._set_short_help_topic("calibracion")
        if self.image_path is None:
            QMessageBox.warning(
                self, "Sin imagen",
                "Cargue una imagen primero o use 'Medir desde archivo…'."
            )
            return

        dialog = MeasureCircleDialog(
            self.image_path, parent=self, max_dim=MAX_ANALYSIS_DIM,
            diameter_cm=self.circle_diameter.value(), height_cm=self.camera_height.value(),
        )
        if _exec_dialog(dialog) == QDialog.DialogCode.Accepted:
            dist_px = dialog.get_pixel_diameter()
            if dist_px is not None and dist_px > 0:
                self._set_reference_circle(dialog)
                self._set_measured_diameter(dist_px)
                # v0.14.38: si dentro de la ventana de medición se cargó otra foto, la medición es de esa
                # foto: se registra su archivo y se reescala como en «Medir desde archivo».
                mpath = dialog.image_path or self.image_path
                if os.path.abspath(mpath) != os.path.abspath(self.image_path):
                    native = dialog.get_native_measurement()
                    self._calib_measure_native = native
                    self._measure_info = self._measurement_record(dialog, mpath, native[1] if native else None)
                    self._log("La medición se hizo en otra foto ({}); se reescala a la foto de análisis.".format(
                        os.path.basename(mpath)))
                else:
                    self._calib_measure_native = None
                    self._measure_info = self._measurement_record(
                        dialog, self.image_path, self.original_image_size)
                self._log(
                    "Diámetro del círculo medido en imagen: {:.2f} px ({}).".format(
                        dist_px, self._measure_info.get("summary", "")
                    )
                )
                QMessageBox.information(
                    self, "Medición aceptada",
                    "Círculo de D = {:.2f} cm a H = {:.2f} cm: {:.2f} px\n{}\n\n"
                    "Haga clic en 'Calcular calibración' para finalizar.".format(
                        dialog.get_diameter_cm(), dialog.get_height_cm(), dist_px,
                        self._measure_info.get("summary", ""))
                )
                self._update_run_button()

    def _set_reference_circle(self, dialog):
        """v0.14.30: D y H escritos en el diálogo de medición pasan a la ventana principal."""
        self.circle_diameter.setValue(dialog.get_diameter_cm())
        self.camera_height.setValue(dialog.get_height_cm())

    def _set_measured_diameter(self, dist_px):
        """
        Escribe el diámetro medido en el campo D_px y lo recuerda tal como quedó en el campo.
        El campo redondea a 2 decimales: comparar con el valor sin redondear hacía que toda
        medición se guardara como «escrita a mano» (error de 0.11.0–0.14.0).
        """
        self.pixel_diameter.setValue(float(dist_px))
        self.last_measured_pixel_diameter = float(self.pixel_diameter.value())

    def _diameter_is_measured(self):
        """True si D_px es el valor medido (no editado a mano después de medir)."""
        if self.last_measured_pixel_diameter is None:
            return False
        return abs(float(self.pixel_diameter.value()) - float(self.last_measured_pixel_diameter)) < 0.006

    def _measurement_record(self, dialog, path, orig_size):
        """Registro trazable de la medición del círculo (se guarda con la calibración)."""
        res = dialog.get_measurement() or {}
        scale = getattr(dialog.canvas, "load_scale", 1.0) or 1.0
        rec = {
            "file": os.path.basename(path) if path else None,
            "image_size": list(orig_size) if orig_size else None,
            "mode": res.get("mode"),
            "diameter_native_px": (res["diameter_px"] / scale) if res.get("diameter_px") else None,
            "diff_pct": res.get("diff_pct"),
            "centre_offset_pct": res.get("centre_offset_pct"),
            "fit_rms_px": (res["fit_rms_px"] / scale) if res.get("fit_rms_px") is not None else None,
            "arc_deg": res.get("arc_deg"),
            "warnings": list(res.get("warnings") or []),
            "notes": list(res.get("notes") or []),
            "verdict": (res.get("verdict") or (None, None))[1],
        }
        try:
            if path and orig_size:
                rec["camera"] = camera_fingerprint(extract_exif(path), orig_size[0], orig_size[1])
        except Exception as e:      # el EXIF es informativo; no impide medir
            self._log("EXIF de la foto de calibración ilegible: {}".format(e), "WARN")
        parts = ["modo {}".format({"diametro": "un diámetro", "cruz": "dos diámetros E–O/N–S",
                                   "ajuste": "ajuste de círculo"}.get(rec["mode"], "—"))]
        if rec["diff_pct"] is not None:
            parts.append("diferencia E–O/N–S {:.2f} %".format(rec["diff_pct"]))
        if rec["fit_rms_px"] is not None:
            parts.append("residuo {:.2f} px".format(rec["fit_rms_px"]))
        if rec["centre_offset_pct"] is not None:
            parts.append("centro desplazado {:.1f} % del diámetro".format(rec["centre_offset_pct"]))
        if rec["image_size"]:
            parts.append("foto {}×{} px".format(*rec["image_size"]))
        rec["summary"] = "; ".join(parts)
        if rec.get("verdict"):
            self._log("Medición del círculo — control de calidad: " + rec["verdict"],
                      "WARN" if rec["warnings"] else "INFO")
        for wmsg in rec["warnings"]:
            self._log("Medición del círculo: " + wmsg, "WARN")
        for nmsg in rec["notes"]:
            self._log("Medición del círculo: " + nmsg)
        return rec

    def _on_measure_from_file(self):
        self._set_short_help_topic("calibracion")
        filters = "Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"
        if HEIF_SUPPORTED:
            filters += " *.heic *.heif"
        filters += ");;Todos los archivos (*)"

        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir fotografía de calibración", "", filters
        )
        if not path:
            return

        dialog = MeasureCircleDialog(
            path, parent=self, max_dim=MAX_ANALYSIS_DIM,
            diameter_cm=self.circle_diameter.value(), height_cm=self.camera_height.value(),
        )
        if _exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return

        dist_px = dialog.get_pixel_diameter()
        if dist_px is None or dist_px <= 0:
            return

        # v0.14.30: si no hay foto, se carga ANTES de escribir la medición. Al cargar la primera foto se
        # aplica la última calibración usada, que sobrescribía el diámetro recién medido, D y H.
        loaded_now = False
        if self.image_path is None:
            loaded_now = self._load_image_into_dialog(path)

        native = dialog.get_native_measurement()
        self._calib_measure_native = native
        self._set_reference_circle(dialog)
        self._set_measured_diameter(dist_px)
        path = dialog.image_path or path      # v0.14.38: la foto realmente medida
        self._measure_info = self._measurement_record(
            dialog, path, native[1] if native else None)
        self._log(
            "Diámetro medido desde archivo '{}': {:.2f} px ({} px en la foto original de {}×{}).".format(
                os.path.basename(path), dist_px,
                "{:.2f}".format(native[0]) if native else "—",
                native[1][0] if native else "?", native[1][1] if native else "?",
            )
        )

        QMessageBox.information(
            self, "Medición aceptada",
            "Círculo de D = {:.2f} cm a H = {:.2f} cm: {:.2f} px\n\n{}"
            "Haga clic en 'Calcular calibración' para aplicar este valor.".format(
                dialog.get_diameter_cm(), dialog.get_height_cm(), dist_px,
                "La foto de calibración se cargó en CobDosel.\n" if loaded_now else "")
        )
        self._update_run_button()

    # ------------------------------------------------------------------
    # Detección automática de ojo de pez
    # ------------------------------------------------------------------
    def _on_detect_circle(self):
        self._set_short_help_topic("calibracion")
        if self.image_array is None:
            QMessageBox.warning(self, "Sin imagen", "Cargue una imagen primero.")
            return

        result = detect_fisheye_circle(self.image_array)
        if result is None:
            self._log(
                "No se pudo detectar automáticamente un círculo ojo de pez.",
                "WARN",
            )
            QMessageBox.warning(
                self, "Detección fallida",
                ("La detección automática requiere OpenCV (paquete «opencv-python»), que no está instalado en "
                 "este QGIS." if not HAS_CV2 else
                 "No se pudo detectar automáticamente el borde circular ojo de pez.") + "\n\n"
                "Compruebe que la foto muestra el círculo de imagen completo, rodeado de esquinas negras. Si la "
                "foto llena todo el fotograma (cámara normal del teléfono), elija «Lente regular / smartphone» "
                "y calibre con el círculo de referencia."
            )
            return

        cx, cy, r = result
        self.center_xy = (cx, cy)

        proj_code = self._current_projection_code()
        if not is_fisheye_projection(proj_code):
            proj_code = "polar"
            self._proj_sync_off = True     # la calibración nueva reemplaza a la activa
            try:
                self._set_projection_by_code("polar")
            finally:
                self._proj_sync_off = False

        try:
            cal = calibrate_fisheye_from_radius(
                r,
                projection=proj_code,
                center_xy=self.center_xy,
                image_width_px=self.image_array.shape[1],
                image_height_px=self.image_array.shape[0],
            )
        except Exception as e:
            QMessageBox.critical(self, "Error de calibración", str(e))
            self._log("Error en calibración ojo de pez: " + str(e), "ERROR")
            return

        self.calibration = cal
        self._cal_name = None      # calibración nueva: «sin guardar» hasta que se guarde
        self.save_cal_btn.setEnabled(True)

        msg = (
            "Ojo de pez detectado: centro=({}, {}), radio={} px\n"
            "Proyección: {}, f={:.1f} px".format(
                cx, cy, r,
                cal.get("projection_label", proj_code),
                cal.get("focal_length_px", 0.0),
            )
        )
        self._calib_base = msg
        self._parked_cal = None
        self.calib_result.setText(msg)
        self._log(msg.replace("\n", " | "))
        self._update_run_button()

    # ------------------------------------------------------------------
    # Calibración regular y persistencia
    # ------------------------------------------------------------------
    def _on_calibrate(self):
        self._set_short_help_topic("calibracion")
        if self.image_array is None:
            QMessageBox.warning(
                self, "Sin imagen cargada",
                "Cargue una imagen primero para conocer sus dimensiones."
            )
            return

        proj_code = self._current_projection_code()

        pixel_diameter = self._pixel_diameter_for_analysis()
        if pixel_diameter is None:
            return

        try:
            cal = calibrate_regular_lens(
                circle_diameter_cm=self.circle_diameter.value(),
                camera_height_cm=self.camera_height.value(),
                pixel_diameter_px=pixel_diameter,
                image_width_px=self.image_array.shape[1],
                image_height_px=self.image_array.shape[0],
                projection=proj_code,
                glama_compat=self.glama_cal_check.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Error de calibración", str(e))
            self._log("Error al calcular calibración: " + str(e), "ERROR")
            return

        # Trazabilidad: origen de la medición (o «manual» si el valor se escribió a mano)
        measured = bool(self._measure_info) and self._diameter_is_measured()
        cal["measurement"] = dict(self._measure_info) if measured else {
            "mode": "manual", "summary": "diámetro escrito a mano (sin medición registrada)"}
        cal["camera"] = (cal["measurement"].get("camera") if measured else None) or self._current_camera()

        # v0.14.33: comprobación de la focal equivalente (calibración propia de la misma cámara o EXIF)
        fc = self._focal_check(cal)
        cal["focal_check"] = {k: fc[k] for k in ("level", "focal_mm", "ref_kind", "ref_name", "ref_mm", "diff_pct")}

        self.calibration = cal
        self._cal_name = None      # calibración nueva: «sin guardar» hasta que se guarde
        self.center_xy = (
            self.image_array.shape[1] / 2.0,
            self.image_array.shape[0] / 2.0,
        )
        self.save_cal_btn.setEnabled(True)
        self._show_calibration_summary(cal, "Calibración")
        self._log(fc["text"], "WARN" if fc["level"] in ("note", "warn") else "INFO")
        if fc["level"] == "warn":
            QMessageBox.warning(
                self, "Comprobación de la distancia focal",
                fc["text"] + "\n\nLa calibración se puede guardar igualmente; este aviso solo orienta. "
                "Consulte «Comprobación de la distancia focal» en la ayuda.")
        half_fov = cal.get("max_zenith_deg", 90.0)
        self._log(
            "Calibración completada ({}): proy={}, D={} cm, H={} cm, D_px={:.2f} px, "
            "θ_máx={:.2f}°, R={:.1f} px, f={:.1f} px; medición: {}.".format(
                "compatible GLAMA" if cal.get("glama_compat") else "geometría exacta",
                _proj_label(cal),
                self.circle_diameter.value(),
                self.camera_height.value(),
                self.pixel_diameter.value(),
                half_fov,
                cal.get("virtual_radius_px") or 0.0,
                cal["focal_length_px"],
                cal["measurement"].get("summary", "—"),
            )
        )
        self._update_run_button()

    def _on_calibrate_glama_radius(self):
        """Calibración a partir del «Hemisph. radius» de la app GLAMA."""
        self._set_short_help_topic("calibracion")
        if self.image_array is None:
            QMessageBox.warning(self, "Sin imagen cargada",
                                "Cargue una imagen primero para conocer sus dimensiones.")
            return
        h, w = self.image_array.shape[:2]
        glama_proj = "angular" if self._current_projection_code() == "orthographic" else "polar"
        try:
            cal = calibrate_from_glama_radius(
                self.glama_radius_spin.value(), w, h,
                scale_side=self.glama_side_combo.currentData() or "short",
                glama_projection=glama_proj,
            )
        except ValueError as e:
            QMessageBox.critical(self, "Error de calibración", str(e))
            return
        cal["measurement"] = {
            "mode": "glama_radius",
            "summary": "radio GLAMA {:.1f} px, escala por el {}".format(
                self.glama_radius_spin.value(),
                "lado menor" if cal["glama_scale_side"] == "short" else "lado mayor")}
        cal["camera"] = self._current_camera()
        self.calibration = cal
        self._cal_name = None      # calibración nueva: «sin guardar» hasta que se guarde
        self.center_xy = (w / 2.0, h / 2.0)
        # antes del modelo: el cambio de lente vuelve a llenar la lista de modelos
        self.lens_combo.setCurrentIndex(0 if is_fisheye_projection(cal["projection"]) else 1)
        self._set_projection_by_code(cal["projection"])
        self.save_cal_btn.setEnabled(True)
        self._show_calibration_summary(cal, "Calibración con radio GLAMA")
        self._log("Calibración con radio GLAMA: R_GLAMA={:.1f} px → R={:.1f} px en la foto "
                  "({}×{} px, {}; proyección GLAMA «{}»).".format(
                      cal["glama_radius_px"], cal["virtual_radius_px"], w, h,
                      cal["measurement"]["summary"], "Polar" if glama_proj == "polar" else "Angular"))
        self._update_run_button()

    def _current_camera(self):
        """Huella de cámara (EXIF + tamaño) de la foto cargada, o None."""
        if self.image_array is None:
            return None
        h, w = self.image_array.shape[:2]
        return camera_fingerprint(self.exif_data or {}, w, h)

    def _own_focal_reference(self, cal):
        """(nombre, focal mm) de la calibración guardada más reciente de la misma cámara, o None."""
        cam = cal.get("camera")
        if not cam:
            return None
        best = None
        for name, _path in list_calibrations():
            try:
                other = load_calibration(name)
            except Exception as e:
                self._log("[focal] No se pudo leer «{}»: {}".format(name, e), "DEBUG")
                continue
            fmm = calibration_focal_mm(other)
            ocam = other.get("camera") or (other.get("measurement") or {}).get("camera")
            if fmm is None or not ocam:
                continue
            same, _why = compare_cameras(ocam, cam)
            if same is not True or not (ocam.get("model") and cam.get("model")):
                continue
            stamp = other.get("saved_at") or ""
            if best is None or stamp > best[0]:
                best = (stamp, name, fmm)
        return (best[1], best[2]) if best else None

    def _focal_check(self, cal):
        cam = cal.get("camera") or {}
        exif35 = cam.get("focal_length_35mm") or (self.exif_data or {}).get("focal_length_35mm")
        return check_focal(cal, exif_35mm=exif35, own_reference=self._own_focal_reference(cal))

    def _show_calibration_summary(self, cal, title):
        """Texto del estado de calibración: ángulos, R y trazabilidad."""
        w = cal.get("image_width_px") or (
            self.image_array.shape[1] if self.image_array is not None else None)
        half_fov = cal.get("max_zenith_deg", 90.0)
        frame_max = cal.get("max_zenith_frame_deg")
        R = cal.get("virtual_radius_px")
        lines = ["{} ({}):".format(title, cal.get("projection_label", cal.get("projection", "")))]
        if cal.get("angular_size_deg"):
            lines.append("  Ángulo ref. (θ_ref) = {:.2f}° (semiángulo = {:.2f}°)  |  Fórmula: {}".format(
                cal["angular_size_deg"],
                cal.get("zenith_ref_deg", cal["angular_size_deg"] / 2.0),
                "aproximada atan(D/H)/2 (calibración antigua)" if cal.get("glama_compat") else "exacta atan(D/2H)"))
        lines.append("  Semiángulo del lado corto (θ_máx) = {:.2f}°{}".format(
            half_fov,
            "  |  esquina de la foto = {:.2f}°".format(frame_max) if frame_max else ""))
        if R:
            lines.append("  Radio del hemisferio (90°) R = {:.1f} px  |  f = {:.1f} px".format(
                R, cal.get("focal_length_px", 0.0)))
        if cal.get("pixel_diameter_px") and w:
            dh = ""
            if cal.get("circle_diameter_cm") and cal.get("camera_height_cm"):
                dh = "D = {:.2f} cm a H = {:.2f} cm → ".format(cal["circle_diameter_cm"], cal["camera_height_cm"])
            lines.append("  Círculo de referencia: {}{:.1f} px = {:.1f} % del ancho de la foto".format(
                dh, cal["pixel_diameter_px"], 100.0 * cal["pixel_diameter_px"] / float(w)))
        meas = cal.get("measurement") or {}
        if meas.get("summary"):
            lines.append("  Medición: " + meas["summary"])
        lines.append("  Cámara de la calibración: " + camera_label(cal.get("camera")))
        fc = cal.get("focal_check")
        if fc and fc.get("focal_mm"):
            mark = {"ok": "✓", "note": "ⓘ", "warn": "⚠"}.get(fc.get("level"), "·")
            if fc.get("ref_kind") == "propia":
                ref = "calibración «{}» de la misma cámara: {:.1f} mm".format(fc.get("ref_name"), fc["ref_mm"])
            elif fc.get("ref_kind") == "exif":
                ref = "EXIF: {:g} mm".format(fc["ref_mm"])
            else:
                ref = "sin referencia"
            lines.append("  {} Focal equivalente {:.1f} mm ({}{})".format(
                mark, fc["focal_mm"], ref,
                "; {:+.1f} %".format(fc["diff_pct"]) if fc.get("diff_pct") is not None else ""))
        lines.append("  Máscara con el círculo de análisis dentro de la foto: ≥ {:.1f}° — no se aplica "
                     "automáticamente".format(cal.get("glama_recommended_horizon_deg", 90.0 - half_fov)))
        self._calib_base = "\n".join(lines)
        self._mark_cut_stale("la calibración")
        self._parked_cal = None          # una calibración nueva o recuperada reemplaza a la que estaba en espera
        self.calib_result.setText(self._calib_base)

    def _pixel_diameter_for_analysis(self):
        """
        Diámetro del círculo de referencia expresado en píxeles de la imagen de ANÁLISIS.

        Si se midió en otra foto («Medir desde archivo») de distinta resolución (p. ej. la
        foto nativa del teléfono de 4128×3096 frente a la foto de análisis de 2560×1920),
        se reescala por la relación de lados mayores; sin esta corrección el radio del
        hemisferio queda multiplicado por esa relación (error de v0.9.x). Requiere la misma
        cámara y el mismo campo de visión (igual proporción de aspecto).
        """
        value = float(self.pixel_diameter.value())
        if value <= 0.0:
            QMessageBox.warning(
                self, "Círculo sin medir",
                "Mida el círculo de referencia con «Medir en imagen…» o «Medir desde archivo…»,\n"
                "o escriba su diámetro en píxeles, antes de calcular la calibración."
            )
            self._log("Calibración cancelada: diámetro del círculo sin medir.", "WARN")
            return None
        native = self._calib_measure_native
        if (native is None or self.original_image_size is None
                or not self._diameter_is_measured()):
            return value                      # medido en esta imagen o editado a mano
        d_native, (cw, ch) = native
        aw, ah = self.original_image_size
        cal_aspect = max(cw, ch) / float(min(cw, ch))
        an_aspect = max(aw, ah) / float(min(aw, ah))
        if abs(cal_aspect - an_aspect) > 0.01 * an_aspect:
            QMessageBox.warning(
                self, "Proporción distinta",
                "La foto de calibración ({}×{}) y la de análisis ({}×{}) tienen distinta\n"
                "proporción de aspecto: no se puede reescalar la medición con seguridad.\n"
                "Mida el círculo en una foto con la misma configuración de cámara.".format(cw, ch, aw, ah)
            )
            self._log("Calibración cancelada: proporción de aspecto distinta.", "WARN")
            return None
        ratio = max(aw, ah) / float(max(cw, ch))
        d_analysis = d_native * ratio * float(self.image_load_scale or 1.0)
        if abs(d_analysis - value) > 0.01:
            self._log(
                "Diámetro reescalado a la imagen de análisis: {:.2f} px (medido {:.2f} px en "
                "la foto de calibración de {}×{}; análisis {}×{}).".format(
                    d_analysis, value, cw, ch, aw, ah
                ),
                "WARN",
            )
            self.pixel_diameter.setValue(d_analysis)
            self.last_measured_pixel_diameter = self.pixel_diameter.value()
            self._calib_measure_native = None
        return float(self.pixel_diameter.value())

    def _on_save_calibration(self):
        if self.calibration is None:
            QMessageBox.warning(
                self, "Sin calibrar", "Calcule la calibración primero."
            )
            return

        lens_name, ok = QInputDialog.getText(
            self, "Guardar calibración",
            "Nombre del lente / cámara (p. ej., 'Cámara principal iPhone 13'):"
        )
        if not ok or not lens_name.strip():
            return
        # v0.14.23: no sobrescribir en silencio (nombres como «Pixel 10» y «Pixel_10» comparten archivo)
        target = calibration_path(lens_name.strip())
        if os.path.isfile(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    old_name = json.load(f).get("lens_name") or os.path.basename(target)
            except (OSError, ValueError):
                old_name = os.path.basename(target)
            reply = QMessageBox.question(
                self, "Calibración existente",
                "Ya existe una calibración guardada como «{}» ({}).\n¿Desea reemplazarla?".format(
                    old_name, target),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._log("Calibración no guardada: el nombre «{}» ya existe.".format(lens_name.strip()), "WARN")
                return

        try:
            path = save_calibration(
                lens_name.strip(),
                self.calibration,
                metadata={
                    # v0.14.27: los valores de la propia calibración (no los que haya en los campos ahora)
                    "circle_diameter_cm": self.calibration.get("circle_diameter_cm"),
                    "camera_height_cm": self.calibration.get("camera_height_cm"),
                    "pixel_diameter_px": self.calibration.get("pixel_diameter_px"),
                    "center_xy": list(self.center_xy) if self.center_xy else None,
                    "image_size": [
                        self.image_array.shape[1],
                        self.image_array.shape[0],
                    ] if self.image_array is not None else None,
                    "original_image_size": list(self.original_image_size)
                    if self.original_image_size else None,
                    "measurement": self.calibration.get("measurement"),
                    "plugin": "CobDosel",
                    "plugin_version": VERSION,
                },
            )
            self._log("Calibración '{}' guardada en: {}".format(lens_name.strip(), path))
            self._cal_name = lens_name.strip()
            self.calibration["lens_name"] = self._cal_name
            set_last_calibration(self._cal_name)
            QMessageBox.information(
                self, "Calibración guardada",
                "Calibración guardada en:\n" + str(path)
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))
            self._log("Error al guardar calibración: " + str(e), "ERROR")

    def _on_load_calibration(self):
        calibrations = list_calibrations()
        if not calibrations:
            QMessageBox.information(
                self, "Sin calibraciones guardadas",
                "No se encontraron calibraciones guardadas. Calcule y guarde una primero."
            )
            return

        names = [name for name, _ in calibrations]
        name, ok = QInputDialog.getItem(
            self, "Cargar calibración",
            "Seleccione una calibración guardada:",
            names, 0, False,
        )
        if not ok or not name:
            return

        try:
            cal = load_calibration(name)
        except Exception as e:
            QMessageBox.critical(self, "Error al cargar", str(e))
            self._log("Error al cargar calibración '{}': {}".format(name, e), "ERROR")
            return
        self._cal_name = name
        self._autoload_done = True
        self._apply_calibration(cal, name, interactive=True,
                                title="Calibración cargada: {}".format(name))

    def _apply_calibration(self, cal, name, interactive=True, title=None):
        """Aplica una calibración (cargada o conservada) a la foto actual y actualiza los controles."""
        if self.image_array is not None:
            cal = scale_calibration_to_image(
                cal,
                self.image_array.shape[1],
                self.image_array.shape[0],
            )
        center_note = cal.pop("center_note", None)
        if center_note:
            self._log("Calibración «{}»: {}.".format(name, center_note), "WARN")

        self.calibration = cal
        proj = cal.get("projection", "angular")
        # Primero el tipo de lente y después el modelo (v0.14.22). Desde v0.14.26 la lista de modelos
        # depende del tipo de lente: un modelo de ojo de pez se carga como «Ojo de pez» (también las
        # calibraciones antiguas hechas con el círculo D/H y un modelo de ojo de pez).
        self.lens_combo.setCurrentIndex(0 if is_fisheye_projection(proj) else 1)
        self._set_projection_by_code(proj)

        meta = cal.get("calibration_metadata") or {}
        if cal.get("circle_diameter_cm") or meta.get("circle_diameter_cm"):
            self.circle_diameter.setValue(
                float(cal.get("circle_diameter_cm") or meta["circle_diameter_cm"])
            )
        if cal.get("camera_height_cm") or meta.get("camera_height_cm"):
            self.camera_height.setValue(
                float(cal.get("camera_height_cm") or meta["camera_height_cm"])
            )
        if cal.get("pixel_diameter_px") or meta.get("pixel_diameter_px"):
            self.pixel_diameter.setValue(
                float(cal.get("pixel_diameter_px") or meta["pixel_diameter_px"])
            )

        if cal.get("center_xy") is not None:
            self.center_xy = (
                float(cal["center_xy"][0]),
                float(cal["center_xy"][1]),
            )
        elif self.image_array is not None:
            self.center_xy = (
                self.image_array.shape[1] / 2.0,
                self.image_array.shape[0] / 2.0,
            )

        if "measurement" not in cal and isinstance(meta.get("measurement"), dict):
            cal["measurement"] = meta["measurement"]
        self._show_calibration_summary(cal, title or "Calibración cargada: {}".format(name))
        self.save_cal_btn.setEnabled(True)
        if name and name != "sin guardar":
            set_last_calibration(name)
        if interactive:
            self._check_loaded_calibration_aspect(cal, meta, name)
            self._log("Calibración '{}' cargada exitosamente.".format(name))
            QMessageBox.information(
                self, "Calibración cargada",
                "Se cargó '{}'.\nYa puede ejecutar el análisis.".format(name)
            )
        else:
            self._log("{} — R = {:.1f} px.".format(
                title or name, float(cal.get("virtual_radius_px") or 0)))
        self._update_run_button()

    def _check_loaded_calibration_aspect(self, cal, meta, name):
        """
        Avisa si la calibración se midió en una foto de otra proporción de aspecto que la
        foto actual, o si no registra en qué foto se midió (calibraciones de CAnOPY ≤ 0.10).
        Una calibración medida en la foto nativa de 4096 px y aplicada como si fuera de
        2560 px multiplica el radio del hemisferio por 1.6 (caso real detectado en 0.10.0).
        """
        if self.image_array is None:
            return
        h, w = self.image_array.shape[:2]
        meas = cal.get("measurement") or {}
        ref = meas.get("image_size") or meta.get("original_image_size") or meta.get("image_size")
        if not meas or meas.get("mode") == "manual":
            msg = ("La calibración «{}» no registra la foto en la que se midió el círculo "
                   "(guardada con una versión anterior o con el diámetro escrito a mano). "
                   "Verifique que el radio del hemisferio es razonable antes de analizar, o vuelva "
                   "a calibrar y guardar.").format(name)
            self._log(msg, "WARN")
            QMessageBox.warning(self, "Calibración sin trazabilidad", msg)
        if not ref:
            return
        rw, rh = float(ref[0]), float(ref[1])
        a_ref = max(rw, rh) / min(rw, rh)
        a_now = max(w, h) / float(min(w, h))
        if abs(a_ref - a_now) > 0.01 * a_now:
            msg = ("La calibración «{}» se midió en una foto de {:.0f}×{:.0f} px (proporción "
                   "{:.3f}) y la foto actual es de {}×{} px (proporción {:.3f}): el campo de "
                   "visión puede ser distinto. Calibre con una foto de la misma configuración "
                   "de cámara.").format(name, rw, rh, a_ref, w, h, a_now)
            self._log(msg, "WARN")
            QMessageBox.warning(self, "Proporción distinta", msg)

    # ------------------------------------------------------------------
    # Umbral
    # ------------------------------------------------------------------
    def _on_threshold_changed(self, value):
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(value)
        self.threshold_spin.blockSignals(False)
        self._mark_manual_cut(value)

    def _on_threshold_spin_changed(self, value):
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(value)
        self.threshold_slider.blockSignals(False)
        self._mark_manual_cut(value)

    def _set_cut(self, value, method_label):
        """Fija el nivel de corte desde un método automático y registra el método."""
        self._cut_auto = (method_label, int(value))
        self._cut_for = self.image_path
        self.threshold_spin.setValue(int(value))
        self.threshold_slider.setValue(int(value))
        self.cut_method = method_label

    def _mark_manual_cut(self, value, how="manual"):
        """Un cambio a mano del nivel de corte: el método pasa a «manual» (o «ajustado desde …»)."""
        self._cut_for = self.image_path
        if self._cut_auto is not None and int(value) == self._cut_auto[1]:
            self.cut_method = self._cut_auto[0]
        elif self._cut_auto is not None:
            # «manual (ajustado desde X = n)»; «ajustado en la vista previa (desde X = n)»
            self.cut_method = "{} ({} {} = {})".format(
                how, "desde" if how.startswith("ajustado") else "ajustado desde",
                self._cut_auto[0], self._cut_auto[1])
        else:
            self.cut_method = how

    def _on_otsu(self):
        """Nivel de corte automático con el método elegido (Otsu o Mínimo)."""
        self._set_short_help_topic("umbral")
        if self.image_array is None:
            QMessageBox.warning(self, "Sin imagen", "Cargue una imagen primero.")
            return

        method = self.auto_method_combo.currentData() or "otsu"
        label = AUTO_THRESHOLD_LABELS.get(method, method)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.progress.setValue(50)
        self.progress.setFormat("Calculando nivel de corte ({})…".format(label))
        QApplication.processEvents()

        try:
            mode = self._current_channel_mode()
            self.gray_array = extract_channel(self.image_array, mode)
            valid = self._analysis_valid_mask(include_horizon_mask=True)
            t, used, note = compute_auto_threshold(self.gray_array, valid, method)
            self._set_cut(t, "automático: " + AUTO_THRESHOLD_LABELS.get(used, used))
            self._log(
                "Nivel de corte automático ({}): T = {} (canal: {}; área: {}).".format(
                    AUTO_THRESHOLD_LABELS.get(used, used), t, CHANNEL_LABELS.get(mode, mode),
                    "fotograma completo" if valid is None else
                    "{} px válidos".format(fmt_int(int(valid.sum()))),
                )
            )
            if note:
                self._log(note, "WARN")
                QMessageBox.information(self, "Nivel de corte automático", note)
        except Exception as e:
            QMessageBox.critical(self, "Error en el nivel de corte automático", str(e))
            self._log("Error en el nivel de corte automático: " + str(e), "ERROR")
        finally:
            QApplication.restoreOverrideCursor()
            self.progress.setValue(0)
            self.progress.setFormat("%p%")

    def _horizon_mask_arg(self):
        """
        Máscara de horizonte para el motor GLAMA.
        Devuelve (argumento, lista_de_ángulos_o_None). Lanza ValueError si la lista no es válida.
        """
        n_dirs = self.horizon_dirs_combo.currentData() or 1
        if n_dirs <= 1:
            return float(self.zenith_max.value()), None
        text = self.horizon_dirs_edit.text().replace(",", ";")
        parts = [p.strip() for p in text.split(";") if p.strip()]
        try:
            angles = [float(p) for p in parts]
        except ValueError:
            raise ValueError("Ángulos de máscara no numéricos: «{}».".format(text))
        if len(angles) != n_dirs:
            raise ValueError(
                "Se esperaban {} ángulos de máscara (uno por dirección) y se recibieron {}.\n"
                "Ejemplo: {}".format(n_dirs, len(angles), "; ".join(["30"] * n_dirs))
            )
        bad = [a for a in angles if not 0.0 <= a <= 85.0]
        if bad:
            raise ValueError(
                "Ángulos fuera de rango (0–85° sobre el horizonte): {}.".format(bad)
            )
        return ("dirs", angles), angles

    def _on_glama_cut(self):
        """Nivel de corte recomendado con el método GLAMA (pantalla de nivel de corte de la app)."""
        self._set_short_help_topic("umbral")
        if self.image_array is None or self.calibration is None or self.center_xy is None:
            QMessageBox.warning(
                self, "Sin calibrar",
                "Cargue una imagen y calibre el lente: el nivel recomendado (log-normal)\n"
                "usa solo los píxeles no enmascarados del círculo del hemisferio."
            )
            return
        h, w = self.image_array.shape[:2]
        cal = scale_calibration_to_image(self.calibration, w, h)
        r_virt = cal.get("virtual_radius_px")
        if not r_virt:
            QMessageBox.warning(self, "Sin radio", "La calibración no define el radio del hemisferio.")
            return
        mode = self._current_channel_mode()
        gray = extract_channel(self.image_array, mode)
        current = self.threshold_spin.value()
        start = GLAMA_CUT_START
        try:
            zarg, _angles = self._horizon_mask_arg()
        except ValueError as e:
            QMessageBox.warning(self, "Máscara por direcciones", str(e))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # El método de GLAMA busca los dos modos a partir del nivel actual: desde un nivel situado
        # en una cola del histograma (p. ej. 21) devuelve el mismo valor y el botón «no hace nada».
        # Se parte siempre de 128 y se itera hasta estabilizarse (igual que el modo por sitio).
        diag = None
        t = None      # v0.14.23: si glama_cut_iterated falla, «t» quedaba sin definir (UnboundLocalError)
        try:
            t = glama_cut_iterated(gray, self.center_xy, r_virt, zarg, cal,
                                   cal.get("projection", "polar"), start=start)
            # Misma comprobación que el lote (0.14.12): dos modos, un mínimo entre ellos, cielo y
            # dosel presentes y el mismo corte desde otros puntos de partida.
            hist = glama_ring_counts_with_gray(gray, start, self.center_xy, r_virt, zarg,
                                               calibration=cal,
                                               projection=cal.get("projection", "polar"))["histogram"]
            diag = glama_cut_diagnosis(hist, start)
        except Exception as e:      # la comprobación es informativa; no impide usar el corte
            self._log("Comprobación del corte recomendado no disponible: {}".format(e), "WARN")
        finally:
            QApplication.restoreOverrideCursor()
        if t is None:
            QMessageBox.warning(
                self, "Sin recomendación",
                "El histograma no permite estimar el nivel de corte (¿un solo modo?).\n"
                "Use un método automático (Otsu o Mínimo) o ajuste el umbral con la vista previa."
            )
            self._log("Sin nivel recomendado (log-normal; iterado desde {}).".format(start), "WARN")
            return
        checked = diag is not None and diag.get("ok")
        self._set_cut(t, "recomendado (log-normal)" if (checked or diag is None)
                      else "recomendado (log-normal), no comprobado")
        self._log(
            "Nivel de corte recomendado (log-normal) = {} (iterado desde {}; valor anterior {}; canal {}).".format(
                t, start, current, CHANNEL_LABELS.get(mode, mode)
            )
        )
        if diag is not None and not diag.get("ok"):
            reasons = "; ".join(diag.get("reasons") or [])
            sky = diag.get("sky_pct")
            msg = ("El nivel recomendado (log-normal) = {} no pasó la comprobación del método:\n• {}\n\n"
                   "Con este corte el cielo es el {} de los píxeles analizados.\n"
                   "El histograma no muestra dos grupos separados (cielo y dosel), algo común con cielo "
                   "gris o nublado visto entre ramas finas. Compare con los métodos automáticos "
                   "(Mínimo, Otsu) y revise el corte con la vista previa (modos Claro y Oscuro) antes "
                   "de usar el resultado.").format(
                       t, reasons.replace("; ", "\n• "),
                       "—" if sky is None else "{:.1f} %".format(sky))
            self._log("Corte recomendado no comprobado: " + reasons, "WARN")
            QMessageBox.warning(self, "Nivel de corte recomendado no comprobado", msg)
        if t <= 30 or t >= 225:
            self._log("Nivel recomendado extremo ({}): revise la imagen con la vista previa del umbral.".format(t),
                      "WARN")

    def _on_adjust_threshold(self):
        self._set_short_help_topic("umbral")
        if self.image_array is None:
            QMessageBox.warning(self, "Sin imagen", "Cargue una imagen primero.")
            return

        try:
            pil_image = Image.fromarray(self.image_array)
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "No se pudo preparar la imagen para la vista previa:\n" + str(e)
            )
            return

        dlg = ThresholdDialog(
            pil_image,
            gray_array=None,
            initial_threshold=self.threshold_spin.value(),
            initial_sky_bright=self.sky_bright_check.isChecked(),
            initial_cleanup=self.clean_check.isChecked(),
            initial_channel=self._current_channel_mode(),
            parent=self,
            valid_mask=self._analysis_valid_mask(include_horizon_mask=True),
        )
        if _exec_dialog(dlg) == QDialog.DialogCode.Accepted:
            new_threshold = dlg.get_threshold()
            new_sky_bright = dlg.get_sky_bright()
            new_cleanup = dlg.get_cleanup()
            new_channel = dlg.get_channel()

            self.threshold_spin.blockSignals(True)
            self.threshold_spin.setValue(new_threshold)
            self.threshold_spin.blockSignals(False)

            self.threshold_slider.blockSignals(True)
            self.threshold_slider.setValue(new_threshold)
            self.threshold_slider.blockSignals(False)
            # Método: el automático calculado en la vista previa, si se aceptó sin cambios
            pv = getattr(dlg, "last_auto", None)
            if pv is not None and int(pv[1]) == int(new_threshold):
                self._cut_auto = (pv[0], int(pv[1]))
                self.cut_method = pv[0]
                self._cut_for = self.image_path
            else:
                self._mark_manual_cut(new_threshold, "ajustado en la vista previa")

            self.sky_bright_check.setChecked(new_sky_bright)
            self.clean_check.setChecked(new_cleanup)

            for i in range(self.channel_combo.count()):
                if self.channel_combo.itemData(i) == new_channel:
                    self.channel_combo.setCurrentIndex(i)
                    break

            self._log(
                "Umbral ajustado interactivamente: T = {}, canal = {}, limpieza = {}.".format(
                    new_threshold,
                    CHANNEL_LABELS.get(new_channel, new_channel),
                    "Sí" if new_cleanup else "No",
                )
            )

    # ------------------------------------------------------------------
    # Ejecución del análisis
    # ------------------------------------------------------------------
    def _on_run(self):
        self._set_short_help_topic("glama")
        if self.image_array is None:
            QMessageBox.warning(self, "Sin imagen", "Cargue una imagen primero.")
            return
        if self.calibration is None or self.center_xy is None:
            QMessageBox.warning(
                self, "Sin calibrar",
                "Calibre el lente primero."
            )
            return
        try:
            self._horizon_mask_arg()
        except ValueError as e:
            QMessageBox.warning(self, "Máscara por direcciones", str(e))
            self._log("Máscara por direcciones no válida: {}".format(e), "WARN")
            return

        try:
            self.progress.setValue(10)
            QApplication.processEvents()

            h, w = self.image_array.shape[:2]
            cal = scale_calibration_to_image(self.calibration, w, h)
            self.calibration = cal
            if cal.get("center_xy") is not None:
                self.center_xy = (
                    float(cal["center_xy"][0]),
                    float(cal["center_xy"][1]),
                )

            channel_mode = self._current_channel_mode()
            self.gray_array = extract_channel(self.image_array, channel_mode)

            thr = self.threshold_spin.value()
            sky_mask = threshold_image(
                self.gray_array, thr,
                sky_is_bright=self.sky_bright_check.isChecked(),
            )
            self.progress.setValue(30)
            QApplication.processEvents()

            if self.clean_check.isChecked():
                sky_mask = clean_binary_mask(sky_mask, iterations=1)

            # Rejillas de radio y ángulo cenital calculadas una sola vez (float32)
            r_px = compute_radius_grid((h, w), self.center_xy)
            zenith_deg = compute_zenith_grid(r_px, self.calibration)

            # Área válida según la calibración (no según el combo del tipo de lente)
            valid_mask = self._analysis_valid_mask(r_px=r_px)
            if valid_mask is None:
                valid_mask = np.ones((h, w), dtype=bool)

            # Máscara de horizonte (única o por direcciones, como GLAMA)
            glama_zarg, horizon_angles = self._horizon_mask_arg()
            valid_cover = valid_mask
            if horizon_angles is not None:
                yy_c, xx_c = np.ogrid[0:h, 0:w]
                az_grid = np.mod(np.degrees(np.arctan2(
                    xx_c - self.center_xy[0], -(yy_c - self.center_xy[1]))), 360.0)
                valid_cover = valid_mask & (
                    zenith_deg <= horizon_zenith_limit(az_grid, horizon_angles) + 1e-9
                )
                del az_grid

            self.progress.setValue(50)
            QApplication.processEvents()

            half_fov = self.calibration.get("max_zenith_deg", 90.0)
            # Rango analizado = máscara de horizonte, limitado solo por el ángulo cenital
            # máximo presente en la foto (esquina más lejana), no por el semiángulo del lado
            # corto: los anillos parcialmente visibles se analizan con sus píxeles visibles.
            zen_frame_max = float(np.max(zenith_deg[valid_mask])) if valid_mask.any() else half_fov
            mask_zen = (float(self.zenith_max.value()) if horizon_angles is None
                        else 90.0 - float(min(horizon_angles)))
            zen_max = max(0.1, min(mask_zen, zen_frame_max))
            n_rings = self.n_rings.value()

            ring_labels, ring_boundaries = create_zenith_rings(
                (h, w), self.center_xy, self.calibration, zen_max, n_rings,
                r_px=r_px, zenith_deg=zenith_deg,
            )
            self.ring_labels = ring_labels
            self.ring_boundaries = ring_boundaries

            cover = compute_canopy_cover(
                sky_mask, ring_labels, valid_cover,
                calibration=self.calibration, center_xy=self.center_xy,
            )
            self.progress.setValue(75)
            QApplication.processEvents()

            # LAI efectivo sobre su propio rango cenital (independiente de la máscara),
            # limitado al ángulo cenital máximo presente en la foto
            lai_zmax = max(0.1, min(self.lai_zenith_max.value(), zen_frame_max))
            if abs(lai_zmax - zen_max) < 1e-6:
                lai_boundaries = ring_boundaries
                lai_rings = cover["per_ring"]
            else:
                lai_labels, lai_boundaries = create_zenith_rings(
                    (h, w), self.center_xy, self.calibration, lai_zmax, n_rings,
                    r_px=r_px, zenith_deg=zenith_deg,
                )
                lai_rings = compute_canopy_cover(
                    sky_mask, lai_labels, valid_mask,
                    calibration=self.calibration, center_xy=self.center_xy,
                )["per_ring"]
                del lai_labels
            # Fracción de claros por anillo × sector de acimut (sector 1 = arriba, horario)
            n_sectors = int(self.n_sectors_combo.currentData() or 0)
            sectors = []
            if n_sectors > 0:
                az_grid_s = azimuth_grid((h, w), self.center_xy)
                sectors = compute_sector_gap_fractions(
                    sky_mask, valid_cover & (zenith_deg <= zen_max + 1e-6), zenith_deg,
                    az_grid_s, ring_boundaries, n_sectors)
                del az_grid_s
            del r_px, zenith_deg
            lai = compute_effective_lai(lai_rings, lai_boundaries)
            lai["ring_boundaries"] = lai_boundaries
            lai["per_ring_gap_fraction"] = [r.get("gap_fraction") for r in lai_rings]
            if not lai["lai_reliable"]:
                self._log(
                    "LAI calculado en 0–{:.1f}° (< {:.0f}°): valor solo indicativo.".format(
                        lai["lai_zenith_max_deg"], LAI_MIN_RELIABLE_ZENITH_DEG
                    ),
                    "WARN",
                )

            metrics = compute_canopy_metrics(
                cover["per_ring"],
                ring_boundaries,
                cover_summary=cover,
                half_fov_deg=half_fov,
                threshold=thr,
            )

            # Indicadores con el método GLAMA (anillos de 1/90 del
            # radio, misma retícula de muestreo). Sustituyen a los equivalentes lineales.
            glama_zmax = float(self.zenith_max.value())
            horizon_mask_deg = (
                max(0.0, 90.0 - glama_zmax) if horizon_angles is None
                else float(min(horizon_angles))
            )
            r_virt = self.calibration.get("virtual_radius_px")
            metrics["caco_linear_pct"] = metrics["canopy_cover_index_pct"]
            metrics["caco_linear_mod_pct"] = metrics["modified_caco_index_pct"]
            metrics["glama_engine"] = False
            if r_virt:
                counts = glama_ring_counts(
                    sky_mask, self.center_xy, r_virt, glama_zarg,
                    calibration=self.calibration,
                    projection=self.calibration.get("projection", "polar"),
                )
                g_idx = glama_indices(counts, calibration=self.calibration, radius_px=r_virt)
                for key in ("gap_fraction_pct", "canopy_openness_pct", "canopy_closure_pct",
                            "canopy_cover_index_pct", "hemisphere_fraction_pct",
                            "total_pixels_in_circle",
                            "total_pixels_in_frame", "light_pixels", "dark_pixels"):
                    metrics[key] = g_idx[key]
                metrics["canopy_cover_pct"] = g_idx["canopy_cover_index_pct"]
                metrics["spherical_cover_pct"] = g_idx["spherical_cover_pct"]
                metrics["unmasked_cover_pct"] = g_idx["unmasked_cover_pct"]
                metrics["modified_caco_index_pct"] = g_idx["spherical_cover_pct"]
                metrics["glama_engine"] = True
            else:
                self._log(
                    "Calibración sin radio de hemisferio: se usan los índices lineales de las "
                    "versiones ≤ 0.10.",
                    "WARN",
                )

            # Porción visible del círculo de análisis (máscara única; con direcciones se
            # usa el límite cenital mayor)
            report_warnings = []
            if self._cut_for != self.image_path:
                wmsg = ("El nivel de corte ({}) no se calculó ni se ajustó para esta foto (valor por "
                        "defecto o de la foto anterior). Use «Recomendado (log-normal)», «Calcular» o "
                        "la vista previa antes de usar el resultado.").format(thr)
                report_warnings.append(wmsg)
                self._log(wmsg, "WARN")
            try:
                r_mask = float(zenith_to_pixel_radius(mask_zen, self.calibration))
            except (ValueError, KeyError, ZeroDivisionError):
                r_mask = None
            circle_visible_pct = (analysis_circle_visibility((h, w), self.center_xy, r_mask)
                                  if r_mask else 100.0)
            if circle_visible_pct < 99.5:
                wmsg = ("El círculo de análisis (cenit ≤ {:.1f}°) queda parcialmente fuera de la "
                        "foto: visible {:.1f} %. Los píxeles fuera de la foto se excluyen del cálculo "
                        "(ver manual).").format(mask_zen, circle_visible_pct)
                self._log(wmsg, "WARN")

            # Misma cámara/lente que la calibración (la resolución puede diferir)
            photo_cam = self._current_camera()
            cam_ok, cam_why = compare_cameras(self.calibration.get("camera"), photo_cam)
            if cam_ok is False:
                wmsg = ("La foto no es de la cámara/lente de la calibración ({}). La calibración NO es "
                        "válida para esta foto: calibre esta cámara.").format("; ".join(cam_why))
                report_warnings.append(wmsg)
                self._log(wmsg, "WARN")
            elif cam_ok is None:
                self._log("Cámara no verificada: " + "; ".join(cam_why) + ".", "WARN")
            else:
                for note in cam_why:
                    self._log("Cámara: " + note + ".")

            # Modo opcional: geometría de pantalla de GLAMA (solo estudios de transición)
            glama_geometry = None
            if self.glama_geometry_check.isChecked() and (
                    not r_virt or glama_mode(self.calibration.get("projection", "polar")) == "general"):
                wmsg = ("Geometría de pantalla de GLAMA no aplicada: requiere una calibración con los modelos "
                        "de GLAMA, «Lineal (compatible con Polar de GLAMA)» u Ortográfica, o una calibración con "
                        "el radio de GLAMA. Con «Rectilínea» (predeterminado) no se puede reproducir la pantalla "
                        "de GLAMA.")
                report_warnings.append(wmsg)
                self._log(wmsg, "WARN")
            elif self.glama_geometry_check.isChecked():
                r_glama = self.calibration.get("glama_radius_px") or glama_equivalent_radius(
                    self.calibration, w, h)
                view, vcen = glama_view_image(self.image_array, GLAMA_VIEW_W, GLAMA_VIEW_H,
                                              self.glama_dy_spin.value())
                v_gray = extract_channel(view, channel_mode)
                v_sky = threshold_image(v_gray, thr, sky_is_bright=self.sky_bright_check.isChecked())
                proj_g = self.calibration.get("projection", "polar")
                v_counts = glama_ring_counts(v_sky, vcen, r_glama, glama_zarg,
                                             calibration=None, projection=proj_g)
                v_idx = glama_indices(v_counts, radius_px=r_glama)
                glama_geometry = {
                    "glama_radius_px": float(r_glama),
                    "view_w": GLAMA_VIEW_W, "view_h": GLAMA_VIEW_H,
                    "center_dy": float(self.glama_dy_spin.value()),
                    "correct_caco_pct": metrics["canopy_cover_index_pct"],
                    "correct_mod_caco_pct": metrics["modified_caco_index_pct"],
                }
                for key in ("gap_fraction_pct", "canopy_openness_pct", "canopy_closure_pct",
                            "canopy_cover_index_pct", "hemisphere_fraction_pct",
                            "total_pixels_in_circle", "total_pixels_in_frame",
                            "light_pixels", "dark_pixels"):
                    metrics[key] = v_idx[key]
                metrics["canopy_cover_pct"] = v_idx["canopy_cover_index_pct"]
                metrics["spherical_cover_pct"] = v_idx["spherical_cover_pct"]
                metrics["modified_caco_index_pct"] = v_idx["spherical_cover_pct"]
                wmsg = ("Geometría de pantalla de GLAMA activada (radio GLAMA {:.0f} px, centro "
                        "{:+.1f} px): los índices reproducen la app, con sus sesgos; CaCo con la "
                        "geometría correcta = {:.2f} %. No use este modo para el valor oficial.").format(
                            r_glama, glama_geometry["center_dy"], glama_geometry["correct_caco_pct"])
                report_warnings.append(wmsg)
                self._log(wmsg, "WARN")

            self.progress.setValue(100)

            self.sky_mask = sky_mask
            self.last_results = {
                "image_path": self.image_path,
                "original_image_size": self.original_image_size,
                "exif": self.exif_data,
                "calibration": self.calibration,
                "calibration_name": self._cal_name,
                "center_xy": self.center_xy,
                "threshold": thr,
                "cut_method": self.cut_method,
                "analysis_area_mask": self._analysis_valid_mask(include_horizon_mask=True),
                "sky_is_bright": self.sky_bright_check.isChecked(),
                "apply_cleanup": self.clean_check.isChecked(),
                "channel_mode": channel_mode,
                "zenith_max_deg": zen_max,
                "horizon_mask_deg": horizon_mask_deg,
                "n_rings": n_rings,
                "cover": cover,
                "metrics": metrics,
                "lai": lai,
                "ring_boundaries": ring_boundaries,
                "sky_mask": sky_mask,
                "horizon_angles": horizon_angles,
                "zenith_frame_max_deg": zen_frame_max,
                "circle_visible_pct": circle_visible_pct,
                "sectors": sectors,
                "n_sectors": n_sectors,
                "glama_geometry": glama_geometry,
                "glama_equivalent_radius_px": glama_equivalent_radius(self.calibration, w, h),
                "run_warnings": report_warnings,
                "mask_zenith_deg": mask_zen,
                "camera_photo": photo_cam,
                "camera_check": cam_ok,
            }

            self._display_results(self.last_results)
            self.export_btn.setEnabled(True)
            self.html_btn.setEnabled(True)
            self.glama_viz_btn.setEnabled(True)
            self.threshold_viz_btn.setEnabled(True)
            self.image_btn.setEnabled(True)
            self.gps_point_btn.setEnabled(
                bool(self.exif_data and self.exif_data.get("has_gps"))
            )

            self._log(
                "Análisis finalizado para '{}': Píxeles círculo={} (fotograma={}), "
                "Claros={} ({:.2f}%), Oscuros={}, Hemisferio={:.2f}%, Máscara horiz.={:.1f}°, "
                "Umbral={}, Apertura={:.2f}%, Cierre={:.2f}%, CaCo={:.2f}%, Modif.CaCo={:.2f}%, "
                "LAIe={:.3f} (0–{:.1f}°).".format(
                    os.path.basename(self.image_path),
                    fmt_int(metrics["total_pixels_in_circle"]),
                    fmt_int(metrics["total_pixels_in_frame"]),
                    fmt_int(metrics["light_pixels"]),
                    metrics["gap_fraction_pct"],
                    fmt_int(metrics["dark_pixels"]),
                    metrics["hemisphere_fraction_pct"],
                    horizon_mask_deg,
                    thr,
                    metrics["canopy_openness_pct"],
                    metrics["canopy_closure_pct"],
                    metrics["canopy_cover_index_pct"],
                    metrics["modified_caco_index_pct"],
                    lai["lai_effective"],
                    lai["lai_zenith_max_deg"],
                )
            )

        except Exception as e:
            traceback.print_exc()
            self._log("Error durante el análisis: " + str(e), "ERROR")
            QMessageBox.critical(
                self, "Error en el análisis",
                str(e) + "\n\nConsulte la pestaña Registro o la Consola de Python para más detalles."
            )
        finally:
            self.progress.setValue(0)

    def _display_results(self, res):
        cover = res["cover"]
        metrics = res["metrics"]
        lai = res["lai"]
        boundaries = res["ring_boundaries"]
        cal = res["calibration"]
        exif = res["exif"] or {}

        half_fov = cal.get("max_zenith_deg", 90.0)
        zen_max = res.get("zenith_max_deg", half_fov)
        horiz_mask = res.get("horizon_mask_deg", max(0.0, 90.0 - zen_max))
        hemi_frac = metrics.get(
            "hemisphere_fraction_pct",
            compute_hemisphere_fraction(half_fov),
        )
        meas = classify_measurement_type(zen_max)
        channel_mode = res.get("channel_mode", "blue_red")
        channel_label = CHANNEL_LABELS.get(channel_mode, channel_mode)

        lines = []
        lines.append("══════════════════════════════════════════════════════════════════")
        lines.append(" ARCHIVO (FILE): " + os.path.basename(res["image_path"]))
        lines.append(" CobDosel v{} — cobertura del dosel, basado en Tichý (2016,".format(VERSION))
        lines.append(" doi:10.1111/jvs.12350)")
        lines.append("══════════════════════════════════════════════════════════════════")
        lines.append("")
        if res.get("glama_geometry"):
            lines.append("  ⚠ GEOMETRÍA DE PANTALLA DE GLAMA ACTIVADA (estudio de transición):")
            lines.append("    CaCo con la geometría correcta = {:.2f} %  (no use este modo"
                         " para el valor oficial)".format(res["glama_geometry"]["correct_caco_pct"]))
            lines.append("")
        # v0.14.38: la calibración realmente usada, arriba, para ver de inmediato con qué modelo se analizó
        _c = res.get("calibration") or {}
        _dh = (" · D = {:g} cm a H = {:g} cm".format(_c["circle_diameter_cm"], _c["camera_height_cm"])
               if _c.get("circle_diameter_cm") and _c.get("camera_height_cm") else "")
        lines.append("Calibración usada: «{}» · {}{} · R = {:.1f} px".format(
            res.get("calibration_name") or "sin guardar", _proj_label(_c), _dh, float(_c.get("virtual_radius_px") or 0)))
        lines.append("")
        lines.append("── RESULTADOS (basado en Tichý 2016) ─────────────────────────────")
        lines.append(
            "  N.º total de píxeles en el círculo (en fotograma): {} px ({} px)".format(
                fmt_int(metrics["total_pixels_in_circle"]),
                fmt_int(metrics["total_pixels_in_frame"]),
            )
        )
        lines.append(
            "  N.º de píxeles claros / cielo (oscuros / dosel):   {} px ({} px)".format(
                fmt_int(metrics["light_pixels"]),
                fmt_int(metrics["dark_pixels"]),
            )
        )
        lines.append(
            "  Fracción de claros del área seleccionada:          {:6.2f} %".format(
                metrics["gap_fraction_pct"]
            )
        )
        lines.append(
            "  Fracción de claros del área analizada (sin máscara): {:6.2f} %".format(
                metrics.get("gap_fraction_unmasked_pct", metrics["gap_fraction_pct"])
            )
        )
        lines.append(
            "  Fracción del hemisferio captada por la cámara:     {:6.2f} %".format(
                hemi_frac
            )
        )
        lines.append(
            "  Nivel de corte entre píxeles blancos y negros:     {}".format(
                res["threshold"]
            )
        )
        lines.append("  Método del nivel de corte:                         {}".format(
            res.get("cut_method") or "manual"))
        lines.append("  ----------------------------------------------------------------")
        lines.append(
            "  Apertura del dosel (Canopy Openness):              {:6.2f} %".format(
                metrics["canopy_openness_pct"]
            )
        )
        lines.append(
            "  Cierre del dosel (Canopy Closure):                 {:6.2f} %".format(
                metrics["canopy_closure_pct"]
            )
        )
        lines.append(
            "  Apertura del área analizada (0–{:.1f}°):            {:6.2f} %".format(
                zen_max, metrics.get("canopy_openness_analysed_pct", 0.0)
            )
        )
        lines.append(
            "  ▶ Índice de Cobertura del Dosel (CaCo):            {:6.2f} %   ← cobertura del dosel".format(
                metrics["canopy_cover_index_pct"]
            )
        )
        lines.append(
            "  Índice CaCo Modificado (Modif. CaCo):              {:6.2f} %".format(
                metrics.get("spherical_cover_pct", metrics["modified_caco_index_pct"])
            )
        )
        lines.append(
            "  CaCo lineal (cos θ·sin θ, versiones ≤ 0.10):       {:6.2f} %".format(
                metrics.get("caco_linear_pct", metrics["canopy_cover_index_pct"])
            )
        )
        lines.append(
            "  Índice de Área Foliar Efectivo (LAIe Miller):      {:6.3f}  (0–{:.1f}°{})".format(
                lai["lai_effective"],
                lai.get("lai_zenith_max_deg", zen_max),
                "" if lai.get("lai_reliable", True) else ", INDICATIVO",
            )
        )
        lines.append("  Nota: la cobertura del dosel (proyección vertical) corresponde al Índice CaCo;")
        lines.append("  el cierre del dosel NO es cobertura.")
        lines.append("")
        lines.append("── PARÁMETROS DE CALIBRACIÓN Y MÁSCARA DE HORIZONTE ──────────────")
        if exif.get("has_gps"):
            lines.append(
                "  Coordenadas GPS:       {:.6f}, {:.6f}".format(
                    exif["latitude"], exif["longitude"]
                )
            )
        lines.append(
            "  Proyección:            "
            + str(cal.get("projection_label", cal.get("projection", "")))
        )
        if cal.get("circle_diameter_cm") is not None:
            lines.append(
                "  Círculo de referencia: D = {:.2f} cm, H = {:.2f} cm, D_px = {:.1f} px".format(
                    cal["circle_diameter_cm"],
                    cal["camera_height_cm"],
                    cal["pixel_diameter_px"],
                )
            )
        lines.append(
            "  Semiángulo (lado corto): {:.2f}° (esquina: {:.2f}°, f = {:.1f} px)".format(
                half_fov,
                res.get("zenith_frame_max_deg", cal.get("max_zenith_frame_deg", half_fov)) or half_fov,
                cal.get("focal_length_px", 0.0),
            )
        )
        if cal.get("virtual_radius_px"):
            lines.append(
                "  Radio del hemisferio:  R = {:.1f} px".format(cal["virtual_radius_px"]))
        meas_rec = cal.get("measurement") or {}
        if meas_rec.get("summary"):
            lines.append("  Medición del círculo:  " + meas_rec["summary"])
        lines.append("  Cámara calibración:    " + camera_label(cal.get("camera")))
        lines.append("  Cámara de la foto:     {}  [{}]".format(
            camera_label(res.get("camera_photo")),
            {True: "misma lente", False: "OTRA LENTE", None: "no verificada"}.get(res.get("camera_check"))))
        lines.append(
            "  Máscara de horizonte:  {} (anillos 0–{:.1f}°, {} anillos)".format(
                "{:.1f}° sobre el horizonte".format(horiz_mask)
                if not res.get("horizon_angles") else
                "{} direcciones: {}°".format(
                    len(res["horizon_angles"]),
                    "; ".join("{:g}".format(a) for a in res["horizon_angles"])),
                zen_max, res["n_rings"]
            )
        )
        lines.append(
            "  Círculo de análisis visible en la foto: {:.1f} %".format(
                res.get("circle_visible_pct", 100.0)))
        lines.append("  Canal de color:        " + channel_label)
        lines.append("  Clasificación:         " + meas["label"])
        if exif.get("orientation") or exif.get("image_direction_deg") is not None:
            lines.append("  EXIF: orientación {}{}".format(
                exif.get("orientation") or "—",
                "; rumbo {:.0f}° ({})".format(exif["image_direction_deg"],
                                              exif.get("image_direction_ref") or "ref. ?")
                if exif.get("image_direction_deg") is not None else ""))
        for wmsg in res.get("run_warnings") or []:
            lines.append("  ⚠ " + wmsg)
        lines.append("")
        lines.append("── DETALLE POR ANILLOS CENITALES ─────────────────────────────────")
        lines.append(
            "{:<8}{:<15}{:>13}{:>13}{:>13}{:>11}{:>11}".format(
                "Anillo", "Rango cenital", "Píxeles", "Claros", "Oscuros",
                "Cobert. %", "Claros %"
            )
        )

        for i, ring in enumerate(cover["per_ring"]):
            lo, hi = boundaries[i]
            cover_s = (
                "{:.2f}".format(ring["cover_pct"])
                if ring["cover_pct"] is not None else "n/d"
            )
            gap_s = (
                "{:.2f}".format(100.0 * ring["gap_fraction"])
                if ring["gap_fraction"] is not None else "n/d"
            )
            lines.append(
                "{:<8}{:>5.1f}–{:<7.1f}°{:>13}{:>13}{:>13}{:>11}{:>11}".format(
                    ring["ring"],
                    lo,
                    hi,
                    fmt_int(ring.get("n_pixels", 0)),
                    fmt_int(ring.get("n_light_pixels", 0)),
                    fmt_int(ring.get("n_dark_pixels", 0)),
                    cover_s,
                    gap_s,
                )
            )

        sectors = res.get("sectors") or []
        n_sec = int(res.get("n_sectors") or 0)
        if sectors and n_sec > 0:
            lines.append("")
            lines.append("── FRACCIÓN DE CLAROS (%) POR ANILLO × SECTOR (S1 = arriba, horario) ──")
            sec_head = "".join("{:>7}".format("S{}".format(k + 1)) for k in range(n_sec))
            lines.append("{:<16}".format("Anillo") + sec_head)
            for i in range(len(boundaries)):
                row = [sc for sc in sectors if sc["ring"] == i + 1]
                lo, hi = boundaries[i]
                lines.append("{:<16}".format("{} ({:.1f}–{:.1f}°)".format(i + 1, lo, hi)) + "".join(
                    "{:>7}".format("{:.1f}".format(sc["gap_pct"]) if sc["gap_pct"] is not None else "—")
                    for sc in row))
        lines.append("")
        lines.append("── LAI EFECTIVO POR ANILLO ({}) ──".format(lai.get("lai_method", "Miller")))
        lai_bounds = lai.get("ring_boundaries", boundaries)
        lai_gaps = lai.get("per_ring_gap_fraction", [])
        for i, contrib in enumerate(lai.get("lai_per_ring", [])):
            lo, hi = lai_bounds[i] if i < len(lai_bounds) else (0.0, 0.0)
            gf = lai_gaps[i] if i < len(lai_gaps) else None
            lines.append(
                "  Anillo {}  {:>5.1f}–{:<5.1f}°   Claros {:>7}   Contribución LAI {:.3f}".format(
                    i + 1, lo, hi,
                    "{:.2f} %".format(100.0 * gf) if gf is not None else "n/d",
                    contrib,
                )
            )
        if not lai.get("lai_reliable", True):
            lines.append(
                "  ⚠ Rango cenital < {:.0f}°: el LAI depende del supuesto de hojas esféricas;"
                " úselo solo como valor indicativo.".format(LAI_MIN_RELIABLE_ZENITH_DEG)
            )
        lines.append("")
        lines.append(
            "  Nota: {} (ver Ayuda §4).".format(
                "CaCo, apertura y cierre calculados según Tichý (2016) (anillos de 1/90 del radio)"
                if metrics.get("glama_engine") else
                "sin radio de hemisferio: índices lineales de las versiones ≤ 0.10"
            )
        )

        self.results_text.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------
    # Exportación de Informe HTML y CSV
    # ------------------------------------------------------------------
    def _on_export_html(self):
        if not self.last_results:
            return

        base_name = os.path.splitext(
            os.path.basename(self.last_results.get("image_path", "cobdosel"))
        )[0]
        default_name = self._default_output_path("Informe_CobDosel_{}.html".format(base_name))

        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe HTML de CobDosel", default_name,
            "Informe HTML (*.html *.htm)"
        )
        if not path:
            return
        if not path.lower().endswith((".html", ".htm")):
            path += ".html"

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = None
        out_path, report_warnings = None, []
        try:
            out_path = generate_html_report(
                self.last_results, path, include_images=True, log=self._log
            )
            report_warnings = self.last_results.get("report_warnings") or []
        except Exception as e:
            error = e
        finally:
            # Restaurar el cursor ANTES de mostrar cualquier mensaje (una sola vez)
            QApplication.restoreOverrideCursor()

        if error is not None:
            QMessageBox.critical(
                self, "Error al generar HTML",
                "No se pudo generar el informe HTML:\n" + str(error)
            )
            self._log("Error al generar informe HTML: " + str(error), "ERROR")
            return
        self._log("Informe HTML exportado en: " + str(out_path))

        warn_txt = ""
        if report_warnings:
            warn_txt = "\n\nAvisos:\n• " + "\n• ".join(report_warnings)
        reply = QMessageBox.question(
            self,
            "Informe HTML generado",
            "El informe HTML se guardó en:\n{}{}\n\n¿Desea abrirlo ahora en su navegador?".format(
                out_path, warn_txt
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(out_path)):
                try:
                    webbrowser.open("file://" + os.path.abspath(out_path))
                except webbrowser.Error as e:
                    self._log("No se pudo abrir el navegador: {}".format(e), "WARN")

    def _on_export_csv(self):
        if not self.last_results:
            return

        base_name = os.path.splitext(
            os.path.basename(self.last_results.get("image_path", "cobdosel"))
        )[0]
        default_name = self._default_output_path("Resultados_CobDosel_{}.csv".format(base_name))

        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar resultados CSV de CobDosel", default_name, "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        res = self.last_results
        cover = res["cover"]
        metrics = res["metrics"]
        lai = res["lai"]
        exif = res["exif"] or {}
        cal = res["calibration"]

        half_fov = cal.get("max_zenith_deg", 90.0)
        zen_max = res.get("zenith_max_deg", half_fov)
        horiz_mask = res.get("horizon_mask_deg", max(0.0, 90.0 - zen_max))
        hemi_frac = metrics.get(
            "hemisphere_fraction_pct",
            compute_hemisphere_fraction(half_fov),
        )
        meas = classify_measurement_type(zen_max)

        n = len(cover["per_ring"])
        lai_bounds = lai.get("ring_boundaries", res["ring_boundaries"])
        n_lai = len(lai["lai_per_ring"])
        header = (
            [
                "image_id", "latitude", "longitude", "elevation_m",
                "capture_datetime", "projection",
                "circle_diameter_cm", "camera_height_cm", "pixel_diameter_px",
                "focal_length_px", "half_fov_deg", "full_fov_deg",
                "hemisphere_fraction_pct", "horizon_mask_deg",
                "zenith_max_deg", "n_rings", "measurement_type",
                "channel_mode", "cut_level_threshold",
                "total_pixels_in_circle", "total_pixels_in_frame",
                "light_pixels", "dark_pixels",
                "gap_fraction_selected_area_pct", "gap_fraction_unmasked_pct",
                "canopy_openness_pct", "canopy_closure_pct", "canopy_openness_analysed_pct",
                "canopy_cover_caco_index_pct", "modified_caco_index_pct",
                "caco_linear_pct", "glama_engine",
                "lai_effective", "lai_zenith_max_deg", "lai_reliable",
                "sky_is_bright", "apply_cleanup", "calibration_approx_formula",
                "horizon_angles", "plugin", "plugin_version",
                "hemisphere_radius_px",
                "zenith_frame_max_deg", "circle_visible_pct",
                "calibration_method", "measurement_mode", "measurement_file",
                "measurement_image_size", "measurement_diff_pct", "measurement_centre_offset_pct",
                "glama_geometry_mode", "caco_correct_geometry_pct",
                "exif_orientation", "exif_image_direction_deg", "cut_level_method",
            ]
            + ["cover_pct_ring{}".format(i + 1) for i in range(n)]
            + ["gap_fraction_ring{}".format(i + 1) for i in range(n)]
            + ["gap_pct_ring{}_S{}".format(sc["ring"], sc["sector"]) for sc in (res.get("sectors") or [])]
            + [
                "lai_ring{}_{:g}-{:g}deg".format(i + 1, lai_bounds[i][0], lai_bounds[i][1])
                for i in range(n_lai)
            ]
        )

        row = (
            [
                os.path.basename(res["image_path"]),
                exif.get("latitude"),
                exif.get("longitude"),
                exif.get("elevation_m"),
                exif.get("capture_datetime"),
                _proj_label(cal),
                cal.get("circle_diameter_cm"),
                cal.get("camera_height_cm"),
                cal.get("pixel_diameter_px"),
                cal.get("focal_length_px"),
                half_fov,
                cal.get("full_fov_deg", 2.0 * half_fov),
                hemi_frac,
                horiz_mask,
                zen_max,
                res["n_rings"],
                meas["type"],
                res.get("channel_mode", "blue_red"),
                res["threshold"],
                metrics["total_pixels_in_circle"],
                metrics["total_pixels_in_frame"],
                metrics["light_pixels"],
                metrics["dark_pixels"],
                metrics["gap_fraction_pct"],
                metrics.get("gap_fraction_unmasked_pct"),
                metrics["canopy_openness_pct"],
                metrics["canopy_closure_pct"],
                metrics.get("canopy_openness_analysed_pct"),
                metrics["canopy_cover_index_pct"],
                metrics.get("spherical_cover_pct", metrics["modified_caco_index_pct"]),
                metrics.get("caco_linear_pct"),
                metrics.get("glama_engine"),
                lai["lai_effective"],
                lai.get("lai_zenith_max_deg"),
                lai.get("lai_reliable"),
                res.get("sky_is_bright"),
                res.get("apply_cleanup"),
                bool(cal.get("glama_compat", False)),
                ";".join("{:g}".format(a) for a in (res.get("horizon_angles") or [])),
                "CobDosel",
                VERSION,
                cal.get("virtual_radius_px"),
                res.get("zenith_frame_max_deg"),
                res.get("circle_visible_pct"),
                cal.get("calibration_method", "circulo_DH" if cal.get("circle_diameter_cm") else ""),
                (cal.get("measurement") or {}).get("mode"),
                (cal.get("measurement") or {}).get("file"),
                "x".join(str(v) for v in ((cal.get("measurement") or {}).get("image_size") or [])),
                (cal.get("measurement") or {}).get("diff_pct"),
                (cal.get("measurement") or {}).get("centre_offset_pct"),
                bool(res.get("glama_geometry")),
                (res.get("glama_geometry") or {}).get("correct_caco_pct"),
                exif.get("orientation"),
                exif.get("image_direction_deg"),
                res.get("cut_method") or "manual",
            ]
            + [r["cover_pct"] for r in cover["per_ring"]]
            + [r["gap_fraction"] for r in cover["per_ring"]]
            + [sc["gap_pct"] for sc in (res.get("sectors") or [])]
            + list(lai["lai_per_ring"])
        )

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerow(row)
            self._log("Resultados exportados a CSV: " + str(path))
            QMessageBox.information(
                self, "CSV guardado",
                "Resultados guardados en:\n" + str(path)
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar CSV", str(e))
            self._log("Error al exportar CSV: " + str(e), "ERROR")

    # ------------------------------------------------------------------
    # Visualización y Capas en QGIS
    # ------------------------------------------------------------------
    def _add_raster_safely(self, raster_path, layer_name, is_temp=False):
        if is_temp:
            self._temp_files.append(raster_path)

        layer = QgsRasterLayer(raster_path, layer_name)
        if not layer.isValid():
            QMessageBox.warning(
                self, "Error de carga",
                "No se pudo cargar la capa ráster en QGIS."
            )
            return False

        existing_layers = len(QgsProject.instance().mapLayers())
        QgsProject.instance().addMapLayer(layer)
        try:
            if existing_layers == 0:
                self.iface.mapCanvas().setExtent(layer.extent())
            self.iface.mapCanvas().refresh()
        except Exception as e:
            self._log("[lienzo] No se pudo ajustar la extensión: {}".format(e), "DEBUG")
        self._log("Capa ráster añadida a QGIS: '{}'.".format(layer_name))
        return True

    def _on_add_glama_visualization(self):
        if not self.last_results or self.image_path is None:
            QMessageBox.warning(
                self, "Sin resultados",
                "Cargue una imagen y ejecute el análisis primero."
            )
            return

        res = self.last_results
        try:
            out_path = self._render_rings_view(res, max_dim=MAX_ANALYSIS_DIM)
        except Exception as e:
            QMessageBox.critical(
                self, "Error de visualización",
                "No se pudo generar la visualización:\n" + str(e)
            )
            self._log("Error en visualización «Anillos cenitales»: " + str(e), "ERROR")
            return

        if self._add_raster_safely(
            out_path, "CobDosel — Anillos cenitales", is_temp=True
        ):
            QMessageBox.information(
                self, "Visualización añadida",
                "La vista «Anillos cenitales» se añadió al proyecto QGIS."
            )

    def _render_rings_view(self, res, max_dim=1600):
        """Vista «Anillos cenitales» con las opciones de la sección 6."""
        metrics = res["metrics"]
        exif = res.get("exif") or {}
        return render_glama_rings(
            res["image_path"],
            res["calibration"],
            center_xy=res.get("center_xy"),
            zenith_max_deg=float(res.get("mask_zenith_deg", self.zenith_max.value())),
            horizon_angles=res.get("horizon_angles"),
            sky_mask=res.get("sky_mask") if self.viz_show_sky_overlay.isChecked() else None,
            ring_interval_deg=self.viz_ring_interval.currentData(),
            n_sectors=int(res.get("n_sectors") or 0),
            show_sky_overlay=self.viz_show_sky_overlay.isChecked(),
            show_outside_mask=self.viz_outside_mask.isChecked(),
            legend_lines=[
                "Nivel de corte: {} ({})".format(res.get("threshold"), res.get("cut_method") or "manual"),
                "CaCo: {:.2f} %".format(metrics["canopy_cover_index_pct"]),
            ],
            max_dim=max_dim,
            image_direction_deg=exif.get("image_direction_deg"),
        )

    def _on_add_threshold_overlay(self):
        if not self.last_results or self.image_path is None:
            QMessageBox.warning(
                self, "Sin resultados",
                "Cargue una imagen y ejecute el análisis primero."
            )
            return

        res = self.last_results

        try:
            # Se dibuja exactamente la máscara analizada, a la resolución del análisis
            out_path = render_threshold_overlay(
                self.image_path,
                sky_mask=res.get("sky_mask"),
                threshold=None if res.get("sky_mask") is not None else res.get("threshold"),
                sky_is_bright=res.get("sky_is_bright", True),
                apply_cleanup=res.get("apply_cleanup", False),
                channel_mode=res.get("channel_mode", "blue_red"),
                mode="overlay",
                sky_color=(255, 140, 40),
                alpha=0.65,
                max_dim=MAX_ANALYSIS_DIM,
                area_mask=res.get("analysis_area_mask"),
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error en máscara de umbral",
                "No se pudo renderizar la superposición de umbral:\n" + str(e)
            )
            self._log("Error en máscara de umbral: " + str(e), "ERROR")
            return

        if self._add_raster_safely(
            out_path, "CobDosel — Superposición de umbral", is_temp=True
        ):
            QMessageBox.information(
                self, "Máscara añadida",
                "La superposición de la máscara analizada (cielo/dosel) se añadió a QGIS."
            )

    def _on_add_image_raster(self):
        if self.image_path is None:
            QMessageBox.warning(self, "Sin imagen", "Cargue una imagen primero.")
            return

        # v0.14.32: QGIS no aplica la orientación EXIF; se añade una copia orientada como las
        # vistas de CobDosel (antes la foto original se veía girada respecto de los resultados).
        try:
            path, code = oriented_copy_for_qgis(self.image_path)
        except Exception as e:
            self._log("[orientación] No se pudo orientar la copia: {}".format(e), "WARNING")
            path, code = self.image_path, None
        rotated = path != self.image_path
        name = "CobDosel — Imagen original" + (" (orientada)" if rotated else "")
        if self._add_raster_safely(path, name, is_temp=rotated):
            QMessageBox.information(
                self, "Imagen añadida",
                "La imagen original se añadió como capa ráster." + (
                    "\nSe aplicó la orientación EXIF ({}, {}) como en el análisis y las vistas de "
                    "CobDosel; QGIS no la aplica al abrir el JPEG directamente.".format(
                        code, _ORIENTATION_TEXT.get(code, "")) if rotated else "")
            )

    def _on_add_gps_point_layer(self):
        if not self.last_results:
            QMessageBox.warning(
                self, "Sin resultados",
                "Ejecute el análisis primero."
            )
            return

        exif = self.last_results.get("exif") or {}
        if not exif.get("has_gps"):
            QMessageBox.warning(
                self, "Sin coordenadas GPS",
                "Esta fotografía no contiene coordenadas GPS en sus metadatos EXIF."
            )
            return

        lat = float(exif["latitude"])
        lon = float(exif["longitude"])
        res = self.last_results
        metrics = res["metrics"]
        lai = res["lai"]
        cal = res["calibration"]

        layer_name = "Puntos CobDosel (GPS)"
        target_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.name() == layer_name:
                target_layer = lyr
                break

        if target_layer is None:
            target_layer = QgsVectorLayer(
                "Point?crs=EPSG:4326", layer_name, "memory"
            )
            pr = target_layer.dataProvider()
            pr.addAttributes([
                QgsField("imagen", _STR),
                QgsField("fecha", _STR),
                QgsField("latitud", _FLOAT),
                QgsField("longitud", _FLOAT),
                QgsField("altitud_m", _FLOAT),
                QgsField("proyeccion", _STR),
                QgsField("fov_medio", _FLOAT),
                QgsField("masc_horiz", _FLOAT),
                QgsField("hemisf_pct", _FLOAT),
                QgsField("umbral", _INT),
                QgsField("px_circulo", _LONG),
                QgsField("px_claros", _LONG),
                QgsField("px_oscuros", _LONG),
                QgsField("claros_pct", _FLOAT),
                QgsField("apertura", _FLOAT),
                QgsField("cierre", _FLOAT),
                QgsField("caco_idx", _FLOAT),
                QgsField("mod_caco", _FLOAT),
                QgsField("lai_efec", _FLOAT),
                QgsField("lai_rango", _FLOAT),
                QgsField("radio_px", _FLOAT),
                QgsField("circ_vis", _FLOAT),
                QgsField("geom_glama", _INT),
                QgsField("version", _STR),
            ])
            target_layer.updateFields()
            QgsProject.instance().addMapLayer(target_layer)

        feat = QgsFeature(target_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttributes([
            os.path.basename(res["image_path"]),
            str(exif.get("capture_datetime") or ""),
            lat,
            lon,
            float(exif["elevation_m"]) if exif.get("elevation_m") is not None else None,
            _proj_label(cal),
            float(cal.get("max_zenith_deg", 90.0)),
            float(res.get("horizon_mask_deg", 0.0)),
            float(metrics["hemisphere_fraction_pct"]),
            int(res["threshold"]),
            int(metrics["total_pixels_in_circle"]),
            int(metrics["light_pixels"]),
            int(metrics["dark_pixels"]),
            float(metrics["gap_fraction_pct"]),
            float(metrics["canopy_openness_pct"]),
            float(metrics["canopy_closure_pct"]),
            float(metrics["canopy_cover_index_pct"]),
            float(metrics.get("spherical_cover_pct", metrics["modified_caco_index_pct"])),
            float(lai["lai_effective"]),
            float(lai.get("lai_zenith_max_deg", 0.0)),
            float(cal.get("virtual_radius_px") or 0.0),
            float(res.get("circle_visible_pct", 100.0)),
            1 if res.get("glama_geometry") else 0,
            "CobDosel " + VERSION,
        ])
        target_layer.dataProvider().addFeatures([feat])
        target_layer.updateExtents()
        target_layer.triggerRepaint()

        self._log(
            "Punto GPS añadido a la capa '{}': ({:.6f}, {:.6f}).".format(
                layer_name, lat, lon
            )
        )
        QMessageBox.information(
            self, "Punto GPS añadido",
            "Se añadió el punto ({:.6f}, {:.6f}) a la capa '{}'.".format(
                lat, lon, layer_name
            )
        )
