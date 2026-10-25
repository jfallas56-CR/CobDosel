"""CobDosel 0.14.47: informes sin autor, informe de una foto reorganizado, cielo no uniforme junto al resultado del sitio.

Uso: python3 -I test_v01447.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos_cielo] [carpeta_fotos_cielo]
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
os.makedirs(OUT, exist_ok=True)
from cobdosel.html_report import generate_html_report
from cobdosel.lens_calibration import scale_calibration_to_image
# ---- 1) informe de una foto
H, W = 1500, 2000
yy, xx = np.mgrid[0:H, 0:W]
rng = np.random.default_rng(7)
img = np.full((H, W, 3), 45, np.uint8)
gaps = np.kron(rng.random((H // 25, W // 25)) < 0.45, np.ones((25, 25), bool))
img[gaps] = 225
img[gaps & (xx < W // 2)] = 160                         # dos brillos de cielo
p1 = os.path.join(OUT, "foto.jpg"); Image.fromarray(img).save(p1, quality=92)
REAL = len(sys.argv) > 4 and os.path.isfile(os.path.join(sys.argv[4], "f560d4dd-image.jpg"))
pr = os.path.join(sys.argv[4], "f560d4dd-image.jpg") if REAL else p1   # foto real con corte no comprobado
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
d._load_image_into_dialog(pr)
H, W = d.image_array.shape[:2]
cal = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
d.zenith_max.setValue(27.0); d._on_glama_cut(); d._on_run(); app.processEvents()
out = generate_html_report(d.last_results, os.path.join(OUT, "foto.html"), include_images=False)
ht = open(out, encoding="utf-8").read()
chk("1 autor y contacto una sola vez, al final (v0.14.48)", ht.count("Autor:") == 1 and
    ht.index("para QGIS · Autor: Jorge Fallas") > ht.index("<footer>") and "jfallas56@gmail.com" in ht)
chk("1 sin etiquetas en inglés del panel antiguo", not any(t in ht for t in (
    "(Results)", "ARCHIVO (FILE)", "Canopy Openness", "Gap Fraction of Selected Area", "Part of Hemisph.",
    "Cut Level between", "Total No. of Pixels")))
chk("1 grupos: área analizada / hemisferio completo / corte, LAI y píxeles",
    "Índices del área analizada" in ht and "Índices referidos al hemisferio completo" in ht and "Nivel de corte, LAI y píxeles" in ht)
chk("1 «Basado en Tichý (2016)» en el pie", "Basado en Tichý (2016)" in ht and "1. Resultados</h2>" in ht)
if REAL:
    chk("1 corte no comprobado (foto real): el informe dice por qué",
        "no comprobado" in d.cut_method and "Nivel de corte recomendado no comprobado: otro punto de partida" in ht,
        d.cut_method)
chk("1 sin el error «se calculan con el según»", "con el según" not in ht)
# ---- 2) informe del sitio: cielo no uniforme junto al resultado
fold = os.path.join(OUT, "lote"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
for k in range(3):
    Image.fromarray(img).save(os.path.join(fold, "F%d.jpg" % k), quality=92)
calg = calibrate_from_glama_radius(1618, img.shape[1], img.shape[0])
b = bc.run_batch(fold, None, calg, None, photos_per_plot=3)
for r, v in zip(b["fotos"], (80.0, 80.0, 10.0)):
    r["cielo_rango"] = v
hp = os.path.join(OUT, "lote.html"); bc.write_html(b, hp, "0.14.47", "S")
hl = open(hp, encoding="utf-8").read()
head = hl.split("<h2>Parcelas</h2>")[0]
chk("2 encabezado del sitio: «2 de 3 fotos válidas: cielo no uniforme»", "2 de 3 fotos válidas: cielo no uniforme" in head)
chk("2 pie sin autor", "jfallas56" not in hl and "Jorge Fallas" not in hl)
bd = CobDoselBatchDialog(None); bd.batch = b; bd._show()
chk("2 panel: la misma línea arriba", "2 de 3 fotos válidas: cielo no uniforme" in bd.out.toPlainText().split("PARCELAS")[0])
print("TODO OK" if ok_all else "HAY FALLAS")
