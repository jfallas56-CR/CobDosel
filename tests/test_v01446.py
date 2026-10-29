"""CobDosel 0.14.46: avisos comunes con su alcance, etiquetas breves por foto, cielo no uniforme «a revisar».

Uso: python3 -I test_v01446.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos_cielo]
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
from PIL.TiffImagePlugin import IFDRational
from cobdosel.canopy_analysis import sky_uniformity_warning
os.makedirs(OUT, exist_ok=True)
def make_folder(name, make, model, focal, f35, n=4):
    fold = os.path.join(OUT, name); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
    rng = np.random.default_rng(len(name))
    t0 = datetime.datetime(2026, 10, 20, 10, 0, 0)
    for k in range(n):
        img = np.full((960, 1280, 3), 50, np.uint8)
        img[np.kron(rng.random((24, 32)) < 0.4, np.ones((40, 40), bool))] = 215
        im = Image.fromarray(img); ex = im.getexif(); ex[271] = make; ex[272] = model
        ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=60 * k)).strftime("%Y:%m:%d %H:%M:%S"),
                      0x920A: IFDRational(int(focal * 100), 100), 0xA405: f35}
        im.save(os.path.join(fold, "F%02d.jpg" % k), quality=92, exif=ex)
    return fold
fa = make_folder("pixel", "Google", "Pixel 10", 4.53, 24)
fb = make_folder("samsung", "samsung", "Galaxy A14", 3.98, 26, n=6)
calA = calibrate_from_glama_radius(1618, 1280, 960); calA["camera"] = bc._photo_camera(os.path.join(fa, "F00.jpg"))
# ---- 1) todas las fotos de otra cámara: un aviso que lo dice; etiqueta breve por foto; un aviso de parcelas
b = bc.run_batch(fb, None, calA, None, photos_per_plot=1)
cam = [w for w in b["avisos"] if "calibración de otra cámara" in w]
chk("1 «Todas las fotos (6 de 6)» en un solo aviso, con el detalle de la cámara",
    len(cam) == 1 and cam[0].startswith("Todas las fotos (6 de 6)") and "Galaxy A14" in cam[0], cam)
chk("1 cada foto: etiqueta breve", all(r["motivo"] == "calibración de otra cámara/lente (ver avisos)" for r in b["fotos"]))
chk("1 parcelas sin fotos válidas: un solo aviso", sum("sin fotos válidas" in w for w in b["avisos"]) == 0
    and any(w.startswith("Ninguna parcela tiene fotos válidas (6 parcelas)") for w in b["avisos"]), b["avisos"][-2:])
# ---- 2) texto de cielo no uniforme: verificar el corte, no «repita o exclúyala»
full = sky_uniformity_warning(67); short = sky_uniformity_warning(67, short=True)
chk("2 aviso completo: pide verificar el corte; repetir solo si es posible",
    "verifique el corte" in full and "si es posible, repita" in full and "exclúyala" not in full, full)
chk("2 etiqueta breve", short == "cielo no uniforme (rango 67)", short)
# ---- 3) fotos reales (opcional): 7 fotos fuera del protocolo
if len(sys.argv) > 4 and os.path.isdir(sys.argv[4]):
    U = sys.argv[4]
    fold = os.path.join(OUT, "malas"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
    for k in ["10e2cd5d", "f560d4dd", "c26ec4a3", "a7f9f55b", "b4d6ec31", "2317a732", "5ccea996"]:
        shutil.copy(os.path.join(U, k + "-image.jpg"), fold)
    calr = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
    b = bc.run_batch(fold, None, calr, None, photos_per_plot=7)
    sky = [w for w in b["avisos"] if "cielo no uniforme" in w]
    chk("3 «Todas las fotos válidas (7 de 7)»: cielo no uniforme, una vez, con rango y «Revisar cortes…»",
        len(sky) == 1 and sky[0].startswith("Todas las fotos válidas (7 de 7)") and "Revisar cortes" in sky[0]
        and "exclúyala" not in sky[0], sky)
    chk("3 las 7 fotos quedan «a revisar»", all(r.get("revisar") for r in b["fotos"]) and
        b["sitio"]["pendientes_revision"] == 7)
    chk("3 cada foto: etiquetas breves, sin la explicación larga",
        all(len(r["motivo"]) < 140 and "nubes de distinto brillo" not in r["motivo"] for r in b["fotos"]),
        [r["motivo"] for r in b["fotos"]][:2])
    idx = [i for i, w in enumerate(b["avisos"]) if "cielo no uniforme" in w][0]
    chk("3 los avisos comunes van al principio (tras «Resultado provisional»)", idx <= 2, idx)
print("TODO OK" if ok_all else "HAY FALLAS")
