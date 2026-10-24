"""CobDosel 0.14.44: comprobación de la cámara antes de procesar el sitio.

Uso: python3 -I test_v01444.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_from_glama_radius
from cobdosel import batch_core as bc
from cobdosel.cut_review_dialog import CutReviewDialog
from cobdosel.batch_dialog import CobDoselBatchDialog

ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
from PIL.TiffImagePlugin import IFDRational
os.makedirs(OUT, exist_ok=True)
def make_folder(name, make, model, focal, f35, n=4):
    fold = os.path.join(OUT, name); os.makedirs(fold, exist_ok=True)
    rng = np.random.default_rng(len(name))
    t0 = datetime.datetime(2026, 10, 20, 10, 0, 0)
    for k in range(n):
        img = np.full((960, 1280, 3), 50, np.uint8)
        img[np.kron(rng.random((24, 32)) < 0.4, np.ones((40, 40), bool))] = 215
        im = Image.fromarray(img); ex = im.getexif()
        ex[271] = make; ex[272] = model
        ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=60 * k)).strftime("%Y:%m:%d %H:%M:%S"),
                      0x920A: IFDRational(int(focal * 100), 100), 0xA405: f35}
        im.save(os.path.join(fold, "F%02d.jpg" % k), quality=92, exif=ex)
    return fold
fa = make_folder("pixel", "Google", "Pixel 10", 4.53, 24)
fb = make_folder("samsung", "samsung", "Galaxy A14", 3.98, 26)
calA = calibrate_from_glama_radius(1618, 1280, 960); calA["camera"] = bc._photo_camera(os.path.join(fa, "F00.jpg"))
calB = calibrate_from_glama_radius(1618, 1280, 960); calB["camera"] = bc._photo_camera(os.path.join(fb, "F00.jpg"))
chk("0 huellas de cámara leídas del EXIF", calA["camera"] and calB["camera"] and calA["camera"].get("model") == "Pixel 10",
    (calA["camera"], calB["camera"]))
# ---- 1) función de comprobación
c = bc.calibration_camera_check(fb, calA, [("A14", calB), ("Pixel", calA)])
chk("1 fotos del A14 con calibración del Pixel: 4 de 4 de otra cámara; propone «A14»",
    c["checked"] and c["mismatch"] == 4 and c["total"] == 4 and c["matches"] == ["A14"], c)
c2 = bc.calibration_camera_check(fa, calA, [("A14", calB)])
chk("1 misma cámara: sin diferencias", c2["mismatch"] == 0)
calN = calibrate_from_glama_radius(1618, 1280, 960)
chk("1 calibración sin cámara registrada: no se comprueba", bc.calibration_camera_check(fb, calN)["checked"] is False)
# ---- 2) ventana
cs.save_calibration("Pixel10_cal", calA); cs.save_calibration("A14_cal", calB)
answers, asked = [], []
def q(*a, **k):
    asked.append((a[2], a[3] if len(a) > 3 else None))
    return answers.pop(0) if answers else QMessageBox.StandardButton.Cancel
QMessageBox.question = staticmethod(q)
SB = QMessageBox.StandardButton
def dialog(folder, calname):
    bd = CobDoselBatchDialog(None); bd.show(); app.processEvents()
    bd._refresh_calibrations(); bd.cal_combo.setCurrentIndex(bd.cal_combo.findData(calname))
    bd.site_edit.setText("S"); bd.folder_edit.setText(folder); bd.per_plot_spin.setValue(2)
    return bd
bd = dialog(fb, "Pixel10_cal"); answers[:] = [SB.Yes]; asked.clear(); bd._on_run(); app.processEvents()
chk("2 fotos de otra cámara → pregunta antes de procesar y nombra la calibración que coincide",
    asked and "A14_cal" in asked[0][0] and "4 de 4" in asked[0][0], asked[0][0][:120] if asked else "")
chk("2 «Sí» → usa «A14_cal», procesa con fotos válidas y lo registra",
    bd.cal_combo.currentData() == "A14_cal" and bd.batch and bd.batch["sitio"]["fotos_validas"] == 4
    and "cambiada a «A14_cal»" in bd.out.toPlainText())
bd = dialog(fb, "Pixel10_cal"); answers[:] = [SB.No]; asked.clear(); bd._on_run(); app.processEvents()
chk("2 «No» → procesa con la calibración elegida; las fotos se excluyen y se avisa",
    bd.cal_combo.currentData() == "Pixel10_cal" and bd.batch and bd.batch["sitio"]["fotos_validas"] == 0
    and "se excluyen" in bd.out.toPlainText())
bd = dialog(fb, "Pixel10_cal"); answers[:] = [SB.Cancel]; asked.clear(); bd._on_run(); app.processEvents()
chk("2 «Cancelar» → no procesa", bd.batch is None)
bd = dialog(fa, "Pixel10_cal"); asked.clear(); bd._on_run(); app.processEvents()
chk("2 misma cámara → no pregunta y procesa", not asked and bd.batch and bd.batch["sitio"]["fotos_validas"] == 4)
os.remove(cs.calibration_path("A14_cal", cs.DEFAULT_DIR))
bd = dialog(fb, "Pixel10_cal"); answers[:] = [SB.No]; asked.clear(); bd._on_run(); app.processEvents()
chk("2 sin calibración de esa cámara: pide calibrarla; sin opción «Sí»",
    asked and "calíbrela" in asked[0][0] and not (asked[0][1] & SB.Yes), asked[0][0][-160:] if asked else "")
print("TODO OK" if ok_all else "HAY FALLAS")
