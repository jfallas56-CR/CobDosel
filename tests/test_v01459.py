"""CobDosel 0.14.59: una exportación por clic en el lote (clics repetidos o en cola se descartan) y el mensaje
«CSV guardados» con la carpeta una sola vez.

Uso: python3 -I test_v01459.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.html_report import generate_html_report
from cobdosel.lens_calibration import scale_calibration_to_image





from cobdosel import batch_core as bc
from cobdosel.batch_dialog import CobDoselBatchDialog, saved_files_text
H, W = 1500, 2000
FOT = os.path.join(OUT, "fotos"); shutil.rmtree(FOT, ignore_errors=True); os.makedirs(FOT)
im = np.full((H, W, 3), 50, np.uint8); im[::9] = 220
Image.fromarray(im).save(os.path.join(FOT, "F0.jpg"), quality=92)
cal = scale_calibration_to_image(calibrate_regular_lens(12.1, 39.8, 886.7, 4000, 3000, projection="rectilinear"), W, H)
d = CobDoselBatchDialog(None); d.show(); app.processEvents()
d.batch = bc.run_batch(FOT, None, cal, None, photos_per_plot=1); d.site_edit.setText("Prueba")
d.csv_btn.setEnabled(True); d.html_btn.setEnabled(True)
calls = []
def fake_save(*a, **k):
    calls.append(1)
    # simula el doble clic y la barra espaciadora mientras el diálogo de guardar está abierto
    d.csv_btn.click(); d._on_csv()
    QtTest.QTest.keyClick(d.csv_btn, QtCore.Qt.Key.Key_Space)
    return (os.path.join(FOT, "CobDosel_Prueba"), "")
QtTest = importlib.import_module(QT + ".QtTest")
QFileDialog.getSaveFileName = staticmethod(fake_save)
msgs.clear()
d.csv_btn.click(); app.processEvents()
chk("1 un clic (con clics repetidos durante la exportación): un solo diálogo y un solo mensaje",
    len(calls) == 1 and sum(1 for k, _ in msgs if k == "information") == 1, (len(calls), msgs))
chk("1 el botón vuelve a quedar activo después", d.csv_btn.isEnabled() and not d._exporting)
txt = [m for k, m in msgs if k == "information"][0]
chk("2 mensaje: la carpeta una vez y los tres nombres", txt.count(FOT) == 1 and txt.startswith("Carpeta: ")
    and all("• CobDosel_Prueba_{}.csv".format(x) in txt for x in ("fotos", "parcelas", "sitio")), txt)
chk("2 con carpetas distintas, rutas completas", saved_files_text(["/a/x.csv", "/b/y.csv"]) == "/a/x.csv\n/b/y.csv")
calls.clear(); msgs.clear()
d.csv_btn.click(); app.processEvents()
chk("3 un segundo clic, ya terminada la exportación, sí exporta otra vez", len(calls) == 1)
hcalls = []
def fake_html(*a, **k):
    hcalls.append(1); d.html_btn.click(); d._on_html()
    return (os.path.join(FOT, "CobDosel_Prueba_informe.html"), "")
QFileDialog.getSaveFileName = staticmethod(fake_html)
QMessageBox.question = staticmethod(lambda *a, **k: (msgs.append(("question", a[2])), QMessageBox.StandardButton.No)[1])
msgs.clear(); d.html_btn.click(); app.processEvents()
chk("4 informe HTML: también un solo diálogo y una sola pregunta", len(hcalls) == 1
    and sum(1 for k, _ in msgs if k == "question") == 1 and "Carpeta: " in [m for k, m in msgs if k == "question"][0])
print("TODO OK" if ok_all else "HAY FALLAS")
