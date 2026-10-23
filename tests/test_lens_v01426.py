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



import math
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra else ""))
from cobdosel.canopy_dialog import CobDoselDialog
from cobdosel import canopy_dialog as cd
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_fisheye_from_radius
img = (np.random.default_rng(3).random((600, 800, 3)) * 255).astype(np.uint8)
os.makedirs(OUT, exist_ok=True); pth = os.path.join(OUT, "p.png"); Image.fromarray(img).save(pth)
d = CobDoselDialog(Iface()); d._load_image_into_dialog(pth)
items = lambda: [d.projection_combo.itemData(i) for i in range(d.projection_combo.count())]
chk("inicio: lente regular → solo Rectilínea y Lineal, Rectilínea elegida (0.14.33)",
    d.lens_combo.currentIndex() == 1 and items() == ["rectilinear", "angular"] and d._current_projection_code() == "rectilinear", items())
d.lens_combo.setCurrentIndex(0)
chk("ojo de pez → Polar, Equisólida, Ortográfica, Estereográfica; Polar elegido",
    items() == ["polar", "equisolid", "orthographic", "stereographic"] and d._current_projection_code() == "polar", items())
chk("ojo de pez: tooltip solo con modelos de ojo de pez", "Lineal" not in d.projection_combo.toolTip())
d.lens_combo.setCurrentIndex(1)
chk("de vuelta a lente regular → Rectilínea", items() == ["rectilinear", "angular"] and d._current_projection_code() == "rectilinear")
chk("lente regular: tooltip sin modelos de ojo de pez", "Equisólida" not in d.projection_combo.toolTip())
# Calibración por círculo con Rectilínea
d._set_projection_by_code("rectilinear"); d.pixel_diameter.setValue(300); d._on_calibrate()
chk("calibrar con Rectilínea (lente regular)", d.calibration and d.calibration["projection"] == "rectilinear")
# Carga de calibraciones guardadas
QInputDialog.getItem = staticmethod(lambda *a, **k: ("x", True))
cd.list_calibrations = lambda: [("x", None)]
def load(cal):
    cd.load_calibration = lambda n: cal
    d._on_load_calibration()
for lens0, cal, exp_lens, exp_proj in (
        (0, calibrate_regular_lens(33, 40, 300, 800, 600, projection="rectilinear"), 1, "rectilinear"),
        (0, calibrate_regular_lens(33, 40, 300, 800, 600, projection="angular"), 1, "angular"),
        (1, calibrate_fisheye_from_radius(280, "equisolid", image_width_px=800, image_height_px=600), 0, "equisolid"),
        (1, calibrate_regular_lens(33, 40, 300, 800, 600, projection="stereographic"), 0, "stereographic")):
    d.lens_combo.setCurrentIndex(lens0); load(cal)
    chk("cargar {} (desde lente {}) → lente {}, modelo {}".format(cal["projection"], lens0, exp_lens, exp_proj),
        d.lens_combo.currentIndex() == exp_lens and d._current_projection_code() == exp_proj and d.calibration["projection"] == exp_proj,
        (d.lens_combo.currentIndex(), d._current_projection_code()))
# Radio GLAMA
d.lens_combo.setCurrentIndex(0); d._set_projection_by_code("orthographic"); d.glama_radius_spin.setValue(500); d._on_calibrate_glama_radius()
chk("radio GLAMA «Angular» (ojo de pez + Ortográfica) → Ortográfica, lente ojo de pez",
    d.calibration["projection"] == "orthographic" and d.lens_combo.currentIndex() == 0 and d._current_projection_code() == "orthographic")
d.lens_combo.setCurrentIndex(1); d._on_calibrate_glama_radius()
chk("radio GLAMA «Polar» (lente regular) → Lineal, lente regular",
    d.calibration["projection"] == "angular" and d.lens_combo.currentIndex() == 1 and d._current_projection_code() == "angular")
d.zenith_max.setValue(30.0); d.threshold_spin.setValue(128); d._set_cut(128, "manual"); d._on_run()
chk("análisis tras los cambios", d.last_results is not None)
from cobdosel.glama_engine import glama_ring_counts
skyr = np.random.default_rng(0).random((600, 800)) > 0.5
okR = True
for Rr in (278.0, 277.78, 278.3, 278.5, 278.9):
    try:
        glama_ring_counts(skyr, (400, 300), Rr, 30.0, projection="polar")
    except Exception as e:
        okR = False; print("   R", Rr, e)
chk("motor: círculo entero dentro de la foto con R no entero (antes «math domain error»)", okR)
print("\nRESULTADO:", "TODAS LAS PRUEBAS PASAN" if ok_all else "HAY FALLOS")
sys.exit(0 if ok_all else 1)
