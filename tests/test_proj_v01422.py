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


from cobdosel.canopy_dialog import CobDoselDialog
from cobdosel import canopy_dialog as cd
img = (rng.random((600, 800, 3))*255).astype('uint8'); p = os.path.join(OUT, "probe.jpg"); os.makedirs(OUT, exist_ok=True)
Image.fromarray(img).save(p)
d = CobDoselDialog(Iface())
d._load_image_into_dialog(p)
print("start lens", d.lens_combo.currentIndex(), "proj", d._current_projection_code())
# Lente regular + Equisólida por círculo
d.lens_combo.setCurrentIndex(1)
for code in ("rectilinear", "equisolid", "polar"):
    d._set_projection_by_code(code)
    d.pixel_diameter.setValue(300)
    try:
        d._on_calibrate()
    except Exception as e:
        print("calib err", e)
    print(code, "-> cal proj", d.calibration and d.calibration.get("projection"), "| combo", d._current_projection_code(),
          "| lens", d.lens_combo.currentIndex(), "| calibrate_btn", d.calibrate_btn.isEnabled())
    d.lens_combo.setCurrentIndex(1)
# carga simulada de calibración rectilínea con lente ojo de pez seleccionado
d.lens_combo.setCurrentIndex(0)
from cobdosel.lens_calibration import calibrate_regular_lens
cal = calibrate_regular_lens(33, 40, 1500, 800, 600, projection="rectilinear")
cd.load_calibration = lambda n: cal
cd.list_calibrations = lambda: [("x", None)]
QInputDialog.getItem = staticmethod(lambda *a, **k: ("x", True))
for nm in dir(d):
    if nm.startswith("_on_load_cal"): getattr(d, nm)()
print("loaded rect: cal", d.calibration.get("projection"), "combo", d._current_projection_code(), "lens", d.lens_combo.currentIndex())
cal = calibrate_regular_lens(33, 40, 1500, 800, 600, projection="equisolid")
for nm in dir(d):
    if nm.startswith("_on_load_cal"): getattr(d, nm)()
print("loaded equisolid: cal", d.calibration.get("projection"), "combo", d._current_projection_code(), "lens", d.lens_combo.currentIndex())
print([m for m in msgs][-3:])
from cobdosel.lens_calibration import calibrate_fisheye_from_radius
cal = calibrate_fisheye_from_radius(280, projection="equisolid", image_width_px=800, image_height_px=600)
d.lens_combo.setCurrentIndex(1)
for nm in dir(d):
    if nm.startswith("_on_load_cal"): getattr(d, nm)()
print("loaded fisheye-detect equisolid: cal", d.calibration.get("projection"), "combo", d._current_projection_code(), "lens", d.lens_combo.currentIndex())
d.lens_combo.setCurrentIndex(0); d._set_projection_by_code("orthographic")
d.glama_radius_spin.setValue(500); d._on_calibrate_glama_radius()
print("glama ortho from fisheye: cal", d.calibration.get("projection"), "combo", d._current_projection_code(), "lens", d.lens_combo.currentIndex())
