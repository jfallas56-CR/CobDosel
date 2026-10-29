"""CobDosel 0.14.52: sin limpieza morfológica (ventana principal, vista previa, análisis, informe, CSV); sin scipy.

Uso: python3 -I test_v01452.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
sys.modules["scipy"] = None; sys.modules["scipy.ndimage"] = None   # el complemento no debe necesitar scipy
from PIL import Image
from PIL.TiffImagePlugin import IFDRational as R
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

import tempfile, csv
import json, shutil, datetime
from cobdosel.canopy_analysis import (sky_uniformity_range, sky_uniformity_warning, SKY_UNIFORMITY_LIMIT, extract_channel)
from cobdosel.glama_engine import glama_cut_diagnosis
from cobdosel.lens_calibration import calibrate_regular_lens
from tests._cal_fixtures import calibrate_from_glama_radius
from cobdosel import batch_core as bc
from cobdosel.cut_review_dialog import CutReviewDialog
from cobdosel.batch_dialog import CobDoselBatchDialog

ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
os.makedirs(OUT, exist_ok=True)
from cobdosel.html_report import generate_html_report
from cobdosel.lens_calibration import scale_calibration_to_image



import subprocess, inspect
from cobdosel.html_report import generate_html_report
from cobdosel.threshold_dialog import ThresholdDialog
from cobdosel import glama_engine as ge, batch_core as bc
from cobdosel.canopy_analysis import extract_channel, threshold_image
chk("1 el complemento se importa sin scipy", "cobdosel.canopy_analysis" in sys.modules and sys.modules.get("scipy") is None)
# foto con claros finos de 1 px (los que la limpieza borraba)
r = np.random.default_rng(5)
H, W = 1500, 2000
im = np.full((H, W, 3), 40, np.uint8)
big = np.kron(r.random((H // 25, W // 25)) < 0.3, np.ones((25, 25), bool))
fine = r.random((H, W)) < 0.04
im[big | fine] = 230
p = os.path.join(OUT, "fino.jpg"); Image.fromarray(im).save(p, quality=97)
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
texts = [w.text() for w in d.findChildren(QtWidgets.QCheckBox)]
chk("2 ventana principal: sin casilla de limpieza", not hasattr(d, "clean_check")
    and not any("limpieza" in t.lower() for t in texts), texts)
d._load_image_into_dialog(p)
cal = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "P"
d.zenith_max.setValue(27.0); d.threshold_spin.setValue(128); d._on_run(); app.processEvents()
res = d.last_results
g = extract_channel(d.image_array, "blue_red"); raw = threshold_image(g, 128, sky_is_bright=True)
R = d.calibration["virtual_radius_px"]
ca = ge.glama_indices(ge.glama_ring_counts(raw, d.center_xy, R, 27.0, calibration=d.calibration,
                                           projection=d.calibration["projection"]),
                      calibration=d.calibration, radius_px=R)["canopy_cover_index_pct"]
chk("3 CaCo de una foto = máscara sin limpiar (claros de 1 px incluidos)",
    abs(res["metrics"]["canopy_cover_index_pct"] - ca) < 1e-9, (res["metrics"]["canopy_cover_index_pct"], ca))
chk("3 resultados sin «apply_cleanup»", "apply_cleanup" not in res)
fold = os.path.join(OUT, "lote"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
shutil.copy(p, os.path.join(fold, "A.jpg"))
bb = bc.run_batch(fold, None, d.calibration, None, photos_per_plot=1, cut_rule="fixed", fixed_cut=128)
chk("3 mismo CaCo en una foto y en el lote (antes podía diferir si se activaba la limpieza)",
    abs(bb["fotos"][0]["caco"] - bc.round_pct(ca)) < 1e-9, (bb["fotos"][0]["caco"], ca))  # v0.14.62: lote con 2 decimales
out = generate_html_report(res, os.path.join(OUT, "r.html"), include_images=True)
ht = open(out, encoding="utf-8").read()
chk("4 informe sin «Limpieza morfológica»", "Limpieza morfológica" not in ht and "limpieza" not in ht.lower())
_save = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "f.csv"), ""))
try:
    d._on_export_csv(); app.processEvents()
finally:
    QFileDialog.getSaveFileName = _save
hdr = list(csv.reader(open(os.path.join(OUT, "f.csv"), encoding="utf-8-sig")))[0]
chk("4 CSV sin columna «apply_cleanup»", "apply_cleanup" not in hdr)
td = ThresholdDialog(Image.fromarray(im), initial_threshold=128); td.show(); app.processEvents()
tt = [w.text() for w in td.findChildren(QtWidgets.QCheckBox)]
chk("5 vista previa: sin casilla de limpieza", not hasattr(td, "cleanup_check") and not any("limpieza" in t.lower() for t in tt), tt)
n_sky_prev = int(threshold_image(td.canvas.gray_array, 128, sky_is_bright=True)[td.canvas.valid_mask if td.canvas.valid_mask is not None else slice(None)].sum())
chk("5 vista previa: las estadísticas cuentan la máscara sin limpiar", td.canvas.get_statistics()[0] == n_sky_prev,
    (td.canvas.get_statistics()[0], n_sky_prev))
src = "".join(open(os.path.join(sys.argv[1], "cobdosel", f), encoding="utf-8").read()
              for f in os.listdir(os.path.join(sys.argv[1], "cobdosel")) if f.endswith(".py"))
chk("6 sin restos en el código (clean_binary_mask, ndimage, apply_cleanup)",
    not any(t in src for t in ("clean_binary_mask", "ndimage.", "apply_cleanup", "cleanup_check")))
print("TODO OK" if ok_all else "HAY FALLAS")
