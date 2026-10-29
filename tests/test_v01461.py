"""CobDosel 0.14.61: formulario desde las fotos con la nota solo en las parcelas que abarcan más de 20 min; «1 decisión
guardada» / «N decisiones guardadas».

Uso: python3 -I test_v01461.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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





import openpyxl, datetime
from cobdosel import batch_core as bc
FOT = os.path.join(OUT, "fotos"); shutil.rmtree(FOT, ignore_errors=True); os.makedirs(FOT)
t0 = datetime.datetime(2026, 6, 28, 10, 59, 33)
offs = [0, 15, 60, 75, 120, 3600 + 120]          # parcelas de 2: 1 y 2 juntas; 3 abarca > 20 min
for k, dt in enumerate(offs):
    im = Image.fromarray(np.full((300, 400, 3), 90, np.uint8)); ex = im.getexif()
    ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=dt)).strftime("%Y:%m:%d %H:%M:%S")}
    im.save(os.path.join(FOT, "G%02d.jpg" % k), exif=ex)
p, n, warns = bc.draft_form_from_photos(FOT, os.path.join(OUT, "f.xlsx"), 2)
ws = openpyxl.load_workbook(p).worksheets[0]
obs = {}
for r in ws.iter_rows(min_row=3, values_only=True):
    if r[4]:
        obs.setdefault(r[0], set()).add(r[7] or "")
chk("1 sin nota en las parcelas bien formadas (1 y 2)", obs.get("1") == {""} and obs.get("2") == {""}, obs)
chk("1 nota solo en la parcela que abarca más de 20 min (3)", obs.get("3") == {"revise: fotos con más de 20 min de diferencia"}, obs)
chk("1 el aviso del diálogo sigue señalando la parcela 3", any("Parcela 3" in w for w in warns), warns)
pc = os.path.join(OUT, "f.csv"); bc.draft_form_from_photos(FOT, pc, 2)
txt = open(pc, encoding="utf-8-sig").read()
chk("1 también en CSV: ninguna fila con «asignación automática: verificar»", "asignación automática" not in txt
    and txt.count("revise: fotos con más de 20 min") == 2)
one = {"a.jpg": {"fecha": "2026-10-27T21:14:54", "operador": "JF"}}
two = dict(one, **{"b.jpg": {"fecha": "2026-10-27T21:16:00", "operador": "JF"}})
chk("2 singular: «1 decisión guardada»", bc.decisions_summary(one) == "1 decisión guardada (2026-10-27 21:14; analista: JF)",
    bc.decisions_summary(one))
chk("2 plural: «2 decisiones guardadas»", bc.decisions_summary(two).startswith("2 decisiones guardadas ("))
chk("2 «Se aplicó» / «Se aplicaron»", bc.applied_text(one).startswith("Se aplicó 1 decisión guardada")
    and bc.applied_text(two).startswith("Se aplicaron 2 decisiones guardadas"))
src = open(os.path.join(sys.argv[1], "cobdosel", "batch_core.py"), encoding="utf-8").read() + \
      open(os.path.join(sys.argv[1], "cobdosel", "batch_dialog.py"), encoding="utf-8").read()
chk("2 sin «decisión(es) guardada(s)» en el código", "decisión(es)" not in src)
print("TODO OK" if ok_all else "HAY FALLAS")
