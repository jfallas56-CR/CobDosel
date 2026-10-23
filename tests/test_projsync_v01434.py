"""Smoke test headless de CobDosel 0.11.0: diálogo real + stubs de qgis.core.

Uso: python3 -I smoke_dialog_v011.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, types, os, csv, importlib, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
QT = sys.argv[3]
os.makedirs(OUT, exist_ok=True)

QtCore = importlib.import_module(QT + ".QtCore")
QtGui = importlib.import_module(QT + ".QtGui")
QtWidgets = importlib.import_module(QT + ".QtWidgets")
q = types.ModuleType("qgis"); qp = types.ModuleType("qgis.PyQt")
sys.modules.update({"qgis": q, "qgis.PyQt": qp, "qgis.PyQt.QtCore": QtCore,
                    "qgis.PyQt.QtGui": QtGui, "qgis.PyQt.QtWidgets": QtWidgets})
core = types.ModuleType("qgis.core")


class Qgis:
    QGIS_VERSION_INT = 40000 if QT == "PyQt6" else 32800


class _Proj:
    _i = None
    def __init__(s): s.layers = {}
    @classmethod
    def instance(c):
        c._i = c._i or c(); return c._i
    def mapLayers(s): return s.layers
    def addMapLayer(s, l): s.layers[id(l)] = l; return l
class QgsPointXY:
    def __init__(s, x, y): s.x, s.y = x, y
class QgsGeometry:
    @staticmethod
    def fromPointXY(p): return p
class QgsField:
    def __init__(s, n, t): s.n, s.t = n, t
class _Prov:
    def __init__(s): s.attrs = []; s.feats = []
    def addAttributes(s, a): s.attrs += a
    def addFeatures(s, f): s.feats += f; return True
class QgsVectorLayer:
    def __init__(s, uri, name, prov): s._n = name; s._p = _Prov()
    def name(s): return s._n
    def source(s): return "memory"
    def dataProvider(s): return s._p
    def updateFields(s): pass
    def fields(s): return s._p.attrs
    def updateExtents(s): pass
    def triggerRepaint(s): pass
class QgsFeature:
    def __init__(s, f=None): s.fields = f
    def setGeometry(s, g): s.g = g
    def setAttributes(s, a): s.a = a
class QgsRasterLayer:
    def __init__(s, p, n): s.p = p
    def isValid(s): return os.path.isfile(s.p)
    def source(s): return s.p
    def extent(s): return None
for c in (Qgis, QgsPointXY, QgsGeometry, QgsField, QgsVectorLayer, QgsFeature, QgsRasterLayer):
    setattr(core, c.__name__, c)
core.QgsProject = _Proj; sys.modules["qgis.core"] = core

QApplication = QtWidgets.QApplication; QMessageBox = QtWidgets.QMessageBox
QFileDialog = QtWidgets.QFileDialog; QInputDialog = QtWidgets.QInputDialog
app = QApplication([])
msgs = []
for name in ("information", "warning", "critical"):
    setattr(QMessageBox, name, staticmethod(lambda *a, _n=name, **k: msgs.append((_n, a[2] if len(a) > 2 else ""))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)

import numpy as np
from PIL import Image
from PIL.TiffImagePlugin import IFDRational as R
from scipy import ndimage
rng = np.random.default_rng(0)
import cobdosel.calibration_store as cs
from cobdosel._version import VERSION
from cobdosel.canopy_dialog import CobDoselDialog
import cobdosel.canopy_dialog as cd
from cobdosel.measure_circle_dialog import MeasureCircleDialog
from cobdosel import cobdosel_plugin, classFactory
class Iface:
    def mainWindow(s): return None
    def mapCanvas(s):
        class C:
            def setExtent(s, e): pass
            def refresh(s): pass
        return C()
    def addToolBarIcon(s, a): pass
    def addPluginToMenu(s, m, a): s.menu = m
    def removePluginMenu(s, m, a): pass
    def removeToolBarIcon(s, a): pass





import tempfile, math
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
import cobdosel.canopy_dialog as cdm
cdm.list_calibrations = cs.list_calibrations; cdm.load_calibration = cs.load_calibration
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_from_glama_radius
os.makedirs(OUT, exist_ok=True); jp = os.path.join(OUT, "p.jpg")
yy, xx = np.mgrid[0:3000, 0:4000]
img = np.where(((xx - 2000) ** 2 + (yy - 1500) ** 2 < 900 ** 2)[..., None], [200, 220, 250], [30, 60, 30]).astype(np.uint8)
img[(np.random.default_rng(0).random((3000, 4000)) > 0.7)] = [30, 60, 30]
Image.fromarray(img).save(jp, quality=90)
d = CobDoselDialog(Iface()); d._load_image_into_dialog(jp)
d.circle_diameter.setValue(12.1); d.camera_height.setValue(40.0); d.pixel_diameter.setValue(886.64)
d._on_calibrate()
R_rect = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, projection="rectilinear")["virtual_radius_px"]
R_lin = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, projection="angular")["virtual_radius_px"]
chk("calibración inicial con el modelo predeterminado (Rectilínea)", d.calibration["projection"] == "rectilinear" and abs(d.calibration["virtual_radius_px"] - R_rect) < 1e-6)
d.zenith_max.setValue(27.0); d._set_cut(128, "manual"); d._on_run(); caco_rect = d.last_results["metrics"]["canopy_cover_index_pct"]
# Caso del usuario: cambiar el modelo después de calibrar
d._set_projection_by_code("angular")
chk("cambiar a Lineal recalcula la calibración activa", d.calibration["projection"] == "angular" and abs(d.calibration["virtual_radius_px"] - R_lin) < 1e-6,
    (round(d.calibration["virtual_radius_px"], 1), round(R_lin, 1)))
chk("mismos D, H y diámetro; medición y cámara conservadas",
    (d.calibration["circle_diameter_cm"], d.calibration["camera_height_cm"], d.calibration["pixel_diameter_px"]) == (12.1, 40.0, 886.64)
    and d.calibration.get("measurement") is not None)
chk("resumen indica el recálculo y avisa que los resultados son del modelo anterior",
    "recalculada con el modelo «Lineal (compatible con Polar de GLAMA)»" in d.calib_result.text() and "Ejecute de nuevo el análisis" in d.calib_result.text())
chk("queda «sin guardar»", d._cal_name is None and d.save_cal_btn.isEnabled())
d._on_run(); caco_lin = d.last_results["metrics"]["canopy_cover_index_pct"]
chk("el análisis usa el modelo nuevo (CaCo distinto con el mismo corte)", abs(caco_lin - caco_rect) > 0.01, (round(caco_rect, 2), round(caco_lin, 2)))
d._set_projection_by_code("rectilinear"); d._on_run()
chk("volver a Rectilínea restablece R y CaCo", abs(d.calibration["virtual_radius_px"] - R_rect) < 1e-6
    and abs(d.last_results["metrics"]["canopy_cover_index_pct"] - caco_rect) < 1e-9)
# Cargar una calibración guardada con otro modelo: no se recalcula
cal_saved = calibrate_regular_lens(23.4, 40, 1720.73, 4000, 3000, projection="angular")
cs.save_calibration("P10_lineal", cal_saved, metadata={})
d._apply_calibration(cs.load_calibration("P10_lineal"), "P10_lineal", interactive=False)
chk("cargar calibración Lineal: se aplica tal cual, sin recalcular", d.calibration["projection"] == "angular"
    and d._current_projection_code() == "angular" and abs(d.calibration["virtual_radius_px"] - cal_saved["virtual_radius_px"]) < 1e-6
    , (d.calibration["projection"], d._current_projection_code(),
    round(d.calibration["virtual_radius_px"], 1), round(cal_saved["virtual_radius_px"], 1), d._cal_name))
# Calibración con el radio de GLAMA: no se recalcula, se explica
d._on_calibrate_glama_radius(); g_R = d.calibration["virtual_radius_px"]; g_proj = d.calibration["projection"]
d._set_projection_by_code("rectilinear" if g_proj != "rectilinear" else "angular")
chk("radio de GLAMA: el cambio de modelo no la modifica y se explica", d.calibration["virtual_radius_px"] == g_R
    and d.calibration["projection"] == g_proj and "conserva el modelo de GLAMA" in d.calib_result.text())
# Cambio de tipo de lente con una calibración D/H activa
d.circle_diameter.setValue(12.1); d.pixel_diameter.setValue(886.64); d._set_projection_by_code("rectilinear"); d._on_calibrate()
d.lens_combo.setCurrentIndex(0)
chk("lente ojo de pez con calibración D/H activa: no cambia y se advierte", d.calibration["projection"] == "rectilinear"
    and "no corresponde a este tipo de lente" in d.calib_result.text())
d.lens_combo.setCurrentIndex(1)
chk("de vuelta a lente regular: la lista muestra el modelo de la calibración activa", d._current_projection_code() == "rectilinear")
d._set_projection_by_code("angular"); d._on_calibrate(); d.lens_combo.setCurrentIndex(0); d.lens_combo.setCurrentIndex(1)
chk("con calibración Lineal activa, volver a lente regular muestra Lineal (no el predeterminado)", d._current_projection_code() == "angular"
    and d.calibration["projection"] == "angular")
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
