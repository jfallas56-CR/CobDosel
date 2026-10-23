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






import tempfile
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
from cobdosel.lens_calibration import calibrate_fisheye_from_radius
def coherent(d):
    """Invariante: sin calibración activa, o la lista muestra el modelo que usa el análisis."""
    return d.calibration is None or d._current_projection_code() == d.calibration.get("projection")
os.makedirs(OUT, exist_ok=True); jp = os.path.join(OUT, "p.jpg")
yy, xx = np.mgrid[0:3000, 0:4000]
img = np.where(((xx - 2000) ** 2 + (yy - 1500) ** 2 < 900 ** 2)[..., None], [200, 220, 250], [30, 60, 30]).astype(np.uint8)
img[(np.random.default_rng(0).random((3000, 4000)) > 0.7)] = [30, 60, 30]
Image.fromarray(img).save(jp, quality=90)
d = CobDoselDialog(Iface()); d._load_image_into_dialog(jp)
d.circle_diameter.setValue(12.1); d.camera_height.setValue(40.0); d.pixel_diameter.setValue(886.64)
d._on_calibrate(); R0 = d.calibration["virtual_radius_px"]
# A) cambiar a ojo de pez con una calibración D/H rectilínea activa
d.lens_combo.setCurrentIndex(0)
chk("A) lente → ojo de pez: la calibración D/H queda en espera (no se usa) y la lista es coherente",
    d.calibration is None and coherent(d) and not d.run_btn.isEnabled() and "queda en espera" in d.calib_result.text(),
    (d.calibration, d._current_projection_code()))
d.lens_combo.setCurrentIndex(1)
chk("A) de vuelta a lente regular: se recupera la misma calibración y modelo",
    d.calibration is not None and d.calibration["virtual_radius_px"] == R0 and coherent(d) and d.run_btn.isEnabled())
# D) notas no se repiten
for _ in range(3):
    d.lens_combo.setCurrentIndex(0); d.lens_combo.setCurrentIndex(1)
chk("D) alternar el tipo de lente no repite notas", d.calib_result.text().count("queda en espera") == 0
    and d.calib_result.text().count("Calibración recuperada") == 1, d.calib_result.text().count("recuperada"))
# B) radio de GLAMA: elegir Rectilínea no cambia la calibración y la lista vuelve a su modelo
d._on_calibrate_glama_radius(); g = d.calibration["projection"]
d._set_projection_by_code("rectilinear" if g != "rectilinear" else "angular")
chk("B) radio de GLAMA + otro modelo: la calibración de GLAMA queda en espera y la lista es coherente",
    coherent(d) and d.calibration is None and "conserva el modelo de GLAMA" in d.calib_result.text())
d._on_calibrate()
chk("B) el modelo elegido se aplica a la nueva calibración con el círculo", d.calibration is not None
    and d.calibration["projection"] == d._current_projection_code() != g)
d._on_calibrate_glama_radius(); d._set_projection_by_code("rectilinear" if g != "rectilinear" else "angular")
d._set_projection_by_code(g)
chk("B) volver al modelo de GLAMA recupera la calibración de GLAMA", d.calibration is not None
    and d.calibration.get("glama_radius_px") and coherent(d) and d.calib_result.text().count("conserva el modelo") == 0)
# C) con ojo de pez, elegir Equisólida no convierte una calibración D/H
d._on_calibrate(); d.lens_combo.setCurrentIndex(0)
d._set_projection_by_code("equisolid")
chk("C) ojo de pez + Equisólida sin calibración de ojo de pez: nada se convierte", d.calibration is None and coherent(d))
# E) calibración ojo de pez detectada: cambiar de modelo la recalcula con el mismo radio y centro
cal_f = calibrate_fisheye_from_radius(1400, projection="polar", center_xy=(2050, 1480), image_width_px=4000, image_height_px=3000)
d._apply_calibration(cal_f, "fe", interactive=False)
d._set_projection_by_code("equisolid")
chk("E) ojo de pez detectado → Equisólida: recalculada con el mismo radio y centro",
    d.calibration["projection"] == "equisolid" and d.calibration["r_image_half_px"] == 1400
    and list(d.calibration["center_xy"]) == [2050, 1480] and coherent(d))
# F) el análisis usa el modelo que muestra la lista (invariante tras cada paso)
d.lens_combo.setCurrentIndex(1)       # la de ojo de pez queda en espera; no hay calibración regular
chk("F) sin calibración regular, el análisis no se puede ejecutar", d.calibration is None and not d.run_btn.isEnabled())
d._on_calibrate(); d._set_projection_by_code("angular")
d._set_cut(128, "manual"); d._on_run()
chk("F) el análisis usa el modelo de la lista", d.last_results["calibration"]["projection"] == d._current_projection_code(),
    (d.last_results["calibration"]["projection"], d._current_projection_code()))
# G) corte automático desactualizado tras cambiar máscara, canal o calibración
d._set_cut(140, "recomendado (log-normal)")
d.zenith_max.setValue(30.0)
chk("G) cambiar la máscara marca el corte como calculado antes", "antes de cambiar la máscara" in d.cut_method, d.cut_method)
d._set_cut(141, "recomendado (log-normal)")
d.channel_combo.setCurrentIndex((d.channel_combo.currentIndex() + 1) % d.channel_combo.count())
chk("G) cambiar el canal también", "antes de cambiar el canal" in d.cut_method, d.cut_method)
d._set_cut(142, "recomendado (log-normal)"); d._set_projection_by_code("rectilinear")
chk("G) cambiar el modelo (recalcula la calibración) también", "antes de cambiar la calibración" in d.cut_method, d.cut_method)
d._set_cut(143, "recomendado (log-normal)")
chk("G) recalcular el corte limpia la marca", d.cut_method == "recomendado (log-normal)")
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
