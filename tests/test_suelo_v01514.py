"""CobDosel 0.15.14: «Cargar clasificación de un CSV…»: vuelve a cargar las clases de un _puntos.csv (con el área del
CSV de foto si hace falta), crea las clases propias que falten y comprueba foto, puntos, clase automática y modo
reglamentario.

Uso: python3 -I test_suelo_v01514.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
import re
QtTest = importlib.import_module(QT + ".QtTest")
from cobdosel import ground_cover as gc
from cobdosel.ground_cover_dialog import GroundCoverDialog
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases.json")
gc.GROUPS_FILE = os.path.join(OUT, "grupos.json")
for p_ in (gc.CUSTOM_CLASSES_FILE, gc.GROUPS_FILE):
    if os.path.exists(p_):
        os.remove(p_)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
img = np.zeros((600, 800, 3), np.uint8); img[:, :400] = (40, 150, 40); img[:, 400:] = (150, 110, 80)
png = os.path.join(OUT, "jardin.png"); Image.fromarray(img).save(png)
CORNERS = [(20, 20), (780, 20), (780, 580), (20, 580)]

A = GroundCoverDialog(None); A.show(); A.load_photo(png)
A.add_class("Vegetacion no verde"); A.add_class("Rocas")
for c in CORNERS:
    A._on_canvas_click(*c)
A.seed_spin.setValue(632781); A.prepare_area(confirm=False)
pend = [i for i, x in enumerate(A.labels) if x is None]
for j, i in enumerate(pend):
    A.label_point(i, ("vegetacion_no_verde", "rocas", "no_id")[j % 3])
prefix = os.path.join(OUT, "CobDosel_suelo_jardin")
paths = gc.write_csvs(A.res, A.export_meta(), A.points, A.labels, A.auto, prefix, VERSION, ";", ",")
want = list(A.labels)

# otra computadora: sin las clases propias, sin área preparada
os.remove(gc.CUSTOM_CLASSES_FILE)
B = GroundCoverDialog(None); B.show(); B.load_photo(png)
chk("0 sin clases propias guardadas", len(B.classes) == 5)
n = B.load_classification_from_csv(paths[1], confirm=False)
chk("1 sin área preparada: la toma del CSV de foto del mismo prefijo (esquinas y semilla)",
    B.seed == 632781 and B.corners == A.corners and B.points == A.points)
chk("1 crea las clases propias que faltan", [l for _k, l, _c in B.classes][-2:] == ["Vegetacion no verde", "Rocas"])
chk("1 todas las clases cargadas", B.labels == want and n == 100 and B.res["sin_clasificar"] == 0, n)
chk("1 la clase marcada no cambia al cargar", B.current_class == "seca")
B.set_groups(gc.set_group([], "Vegetación total", ["verde", "vegetacion_no_verde"], B.classes))
nv = sum(1 for x in want if x in ("verde", "vegetacion_no_verde"))
chk("2 con la clasificación cargada, el grupo da la suma", B.res["grupos"]["Vegetación total"]["puntos"] == nv)

# clasificación a medias: continuar
half = os.path.join(OUT, "CobDosel_suelo_jardin_medias")
part = [lab if (i not in pend or k < 10) else None for i, lab in enumerate(want) for k in [pend.index(i) if i in pend else 0]]
gc.write_csvs(gc.summarize(A.area, part, classes=A.classes), A.export_meta(), A.points, part, A.auto, half, VERSION)
B.load_classification_from_csv(half + "_puntos.csv", confirm=False)
chk("3 clasificación a medias: carga y deja el resto sin clasificar", B.res["sin_clasificar"] == len(pend) - 10)
nxt = B.advance()
chk("3 «Siguiente» sigue con el primer punto sin clasificar", nxt == pend[10], (nxt, pend[10]))

# errores
other = os.path.join(OUT, "otra.png"); Image.fromarray(img).save(other)
C = GroundCoverDialog(None); C.load_photo(other)
for path, txt in ((paths[1], "es de la foto «jardin.png»"),):
    try:
        C.load_classification_from_csv(path, confirm=False); err = ""
    except ValueError as e:
        err = str(e)
    chk("4 error claro: otra foto", txt in err, err)
lone = os.path.join(OUT, "suelto_puntos.csv")
import shutil
shutil.copy(paths[1], lone)
D = GroundCoverDialog(None); D.load_photo(png)
try:
    D.load_classification_from_csv(lone, confirm=False); err = ""
except ValueError as e:
    err = str(e)
chk("4 sin área ni CSV de foto: error claro", "no se encontró el CSV de foto" in err, err)
rows = open(paths[1], encoding="utf-8-sig").read().splitlines()
hdr = rows[0].split(";"); ia = hdr.index("clase_automatica")
bad_rows = [rows[0]] + [";".join(c if j != ia else ("No aplica" if c != "No aplica" else c) for j, c in enumerate(r.split(";")))
                        for r in rows[1:]]
badp = os.path.join(OUT, "CobDosel_suelo_jardin_mal_puntos.csv")
open(badp, "w", encoding="utf-8-sig").write("\n".join(bad_rows) + "\n")
try:
    B.load_classification_from_csv(badp, confirm=False); err = ""
except ValueError as e:
    err = str(e)
chk("4 clase automática distinta: no se carga", "clase automática" in err and B.labels != [None] * 100, err)
# modo reglamentario
viol = list(want); viol[pend[0]] = "verde"
vp = os.path.join(OUT, "CobDosel_suelo_jardin_viol")
gc.write_csvs(gc.summarize(A.area, viol, classes=A.classes), A.export_meta(), A.points, viol, A.auto, vp, VERSION)
B.reg_check.setChecked(True)
try:
    B.load_classification_from_csv(vp + "_puntos.csv", confirm=False); err = ""
except ValueError as e:
    err = str(e)
chk("5 modo reglamentario: no carga una clasificación que no lo cumple", "no cumplen el modo reglamentario" in err, err)
B.reg_check.setChecked(False)
chk("5 sin el modo, sí la carga (para revisarla)", B.load_classification_from_csv(vp + "_puntos.csv", confirm=False) == 100
    and B.labels[pend[0]] == "verde")
chk("6 botón y ayuda", B.load_cls_btn.text() == "Cargar clasificación de un CSV…")
from cobdosel.help_texts import GROUND_HELP_HTML
chk("6 ayuda: retomar o revisar", "Cargar clasificación de un CSV" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
