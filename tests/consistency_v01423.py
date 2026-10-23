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
from cobdosel import batch_core as bc
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_from_glama_radius, calibrate_fisheye_from_radius
UP = sys.argv[4]
photo = os.path.join(UP, "5fc4cb4f-image.jpg")
d = CobDoselDialog(Iface())
d._load_image_into_dialog(photo)
H, W = d.image_array.shape[:2]
print("analysis image", W, H)
cases = []
for proj in ("angular", "rectilinear", "polar", "equisolid", "stereographic", "orthographic"):
    cases.append((proj, calibrate_regular_lens(33.0, 40.0, 0.4*W*2*0.6, W, H, projection=proj)))
cases.append(("glama-ortho", calibrate_from_glama_radius(1100, W, H, glama_projection="angular")))
cases.append(("glama-polar", calibrate_from_glama_radius(1100, W, H, glama_projection="polar")))
fe = calibrate_fisheye_from_radius(0.45*min(W,H), "equisolid", center_xy=[W/2+40, H/2-25], image_width_px=W, image_height_px=H)
cases.append(("fisheye-offcentre", fe))
worst = 0
for name, cal in cases:
    d._load_image_into_dialog(photo)
    d.calibration = dict(cal); d.center_xy = tuple(cal["center_xy"])
    d.zenith_max.setValue(30.0)
    d.threshold_spin.setValue(150); d._set_cut(150, "manual")
    d.n_sectors_combo.setCurrentIndex(0)
    d._on_run()
    m = d.last_results["metrics"]
    b = bc.analyze_photo(photo, cal, 30.0, d._current_channel_mode(), True, "fixed", 150)
    diff = abs(m["canopy_cover_index_pct"] - b["caco"])
    worst = max(worst, diff)
    print("{:18s} dialog {:7.3f}  batch {:7.3f}  diff {:.4f}".format(name, m["canopy_cover_index_pct"], b["caco"], diff))
print("WORST", worst)
from cobdosel.html_report import generate_html_report
from cobdosel import visualization as vz
import inspect
errs = 0
for name, cal in cases:
    for sky_bright, clean, sectors, mask in ((True, False, 8, 30.0), (False, True, 4, 60.0), (True, True, 0, 85.0)):
        try:
            d._load_image_into_dialog(photo)
            d.calibration = dict(cal); d.center_xy = tuple(cal["center_xy"])
            d.zenith_max.setValue(mask); d.sky_bright_check.setChecked(sky_bright); d.clean_check.setChecked(clean)
            d.threshold_spin.setValue(150); d._set_cut(150, "manual")
            d.n_sectors_combo.setCurrentIndex(max(0, d.n_sectors_combo.findData(sectors)))
            d._on_run()
            assert d.last_results is not None, "sin resultados"
            p = os.path.join(OUT, "rep_{}_{}.html".format(name, mask))
            generate_html_report(d.last_results, p, include_images=True, log=None)
            assert os.path.getsize(p) > 20000
            rw = d.last_results.get("report_warnings") or []
            if rw: print("  report warnings", name, mask, rw[:2])
        except Exception as e:
            errs += 1
            import traceback; print("FAIL", name, sky_bright, clean, sectors, mask, type(e).__name__, e); traceback.print_exc(limit=3)
print("REPORT ERRORS", errs)
print("dialog msgs:", [m for m in msgs if m[0] != "information"][:6])

