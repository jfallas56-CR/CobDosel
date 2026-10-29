"""CobDosel 0.14.43: operador en el lote y puntos «Foto N» sin avisos falsos.

Uso: python3 -I test_v01443.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
fold = os.path.join(OUT, "fotos"); os.makedirs(fold, exist_ok=True)
rng = np.random.default_rng(2)
t0 = datetime.datetime(2026, 10, 20, 10, 0, 0)
for k in range(6):
    img = np.full((960, 1280, 3), 50, np.uint8)
    img[np.kron(rng.random((24, 32)) < 0.4, np.ones((40, 40), bool))] = 215
    im = Image.fromarray(img); ex = im.getexif()
    ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=60 * k)).strftime("%Y:%m:%d %H:%M:%S")}
    im.save(os.path.join(fold, "F%02d.jpg" % k), quality=92, exif=ex)
calg = calibrate_from_glama_radius(1618, 1280, 960)
for n in (1, 3, 5):
    b = bc.run_batch(fold, None, calg, None, photos_per_plot=n)
    bad = [w for w in b["avisos"] if "no reconocido" in w]
    chk("1 sin formulario, {} foto(s) por parcela: sin avisos «punto no reconocido»".format(n), not bad, bad[:2])
    pts = sorted({r["punto"] for r in b["fotos"]})
    if n == 3:
        chk("1 los puntos «Foto N» se conservan", pts == ["Foto 1", "Foto 2", "Foto 3"], pts)
fp = os.path.join(OUT, "form.csv")
with open(fp, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(bc.FORM_COLUMNS)
    w.writerow(["1", "", "Foto 2", "", "F00", "", "OK", ""]); w.writerow(["1", "", "Esquina", "", "F01", "", "OK", ""])
rows, warns = bc.read_field_form(fp)
chk("1 formulario: «Foto 2» válido; un punto realmente desconocido sigue avisándose",
    rows[0]["punto_norm"] == "Foto 2" and any("Esquina" in w for w in warns) and not any("Foto 2" in w for w in warns), warns)
# ---- ventana del lote: operador
bd = CobDoselBatchDialog(None); bd.show(); app.processEvents()
labels = [w.text() for w in bd.findChildren(QtWidgets.QLabel)]
chk("2 campo «Analista» en «1. Datos del sitio» (v0.14.48)", "Analista:" in labels and hasattr(bd, "operator_edit"))
cs.save_calibration("Prueba_GLAMA", calg)
bd._refresh_calibrations(); bd.cal_combo.setCurrentIndex(max(0, bd.cal_combo.findData("Prueba_GLAMA")))
bd.site_edit.setText("Sitio X"); bd.operator_edit.setText("J. Fallas"); bd.folder_edit.setText(fold)
bd.per_plot_spin.setValue(3); bd._on_run(); app.processEvents()
chk("2 analista registrado en los parámetros del sitio y en el panel",
    bd.batch and bd.batch["parametros"].get("analista") == "J. Fallas" and "ANALISTA: J. Fallas" in bd.out.toPlainText())
paths = bc.write_csvs(bd.batch, os.path.join(OUT, "lote"), "0.14.43")
chk("2 operador en el CSV del sitio", "J. Fallas" in open(paths[2], encoding="utf-8-sig").read())
import cobdosel.cut_review_dialog as crd
seen = []
orig_init = crd.CutReviewDialog.__init__
def spy(self, *a, **k):
    seen.append(k.get("operator")); orig_init(self, *a, **k)
crd.CutReviewDialog.__init__ = spy
crd.CutReviewDialog.exec = lambda s: 0
crd.CutReviewDialog.exec_ = crd.CutReviewDialog.exec
bd._on_review()
chk("2 «Revisar cortes…» propone el operador de la ventana", seen == ["J. Fallas"], seen)
print("TODO OK" if ok_all else "HAY FALLAS")
