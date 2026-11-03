"""CobDosel 0.15.13: grupos de clases (p. ej. «Vegetación total») con el IC de Wilson de la suma, en la ventana, el CSV
y el informe; ventana «Grupos de clases».

Uso: python3 -I test_suelo_v01513.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.ground_groups_dialog import GroupsDialog, NEW
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases.json")
gc.GROUPS_FILE = os.path.join(OUT, "grupos.json")
for p_ in (gc.CUSTOM_CLASSES_FILE, gc.GROUPS_FILE):
    if os.path.exists(p_):
        os.remove(p_)
cl = gc.class_list(gc.new_custom_class("Vegetación no verde", []))
g = gc.set_group([], "Vegetación total", ["vegetacion_no_verde", "verde", "seca"], cl)
chk("1 grupo: clases en el orden de la lista", g == [{"nombre": "Vegetación total",
                                                     "clases": ["verde", "seca", "vegetacion_no_verde"]}])
a = np.zeros((10, 10, 3), np.uint8)
labels = ["verde"] * 22 + ["vegetacion_no_verde"] * 25 + ["suelo"] * 53
r = gc.summarize(a, labels, classes=cl, groups=g)
d = r["grupos"]["Vegetación total"]
lo, hi = gc.wilson_ci(47, 100)
chk("1 Vegetación total = 22 + 25 = 47 puntos, IC de Wilson de la suma (37,5–56,7 %)", d["puntos"] == 47
    and d["pct"] == 47.0 and (d["ic_inf"], d["ic_sup"]) == (lo, hi) and round(lo, 1) == 37.5 and round(hi, 1) == 56.7, d)
s_lo = r["clases"]["verde"]["ic_inf"] + r["clases"]["vegetacion_no_verde"]["ic_inf"]
chk("1 distinto de sumar los intervalos de las clases", abs(s_lo - lo) > 1, (s_lo, lo))
for args, txt in ((("", ["verde"]), "Escriba el nombre"), (("G", []), "al menos una clase"),
                  (("Hojarasca", ["verde"]), "ya es el nombre de una clase"), (("vegetación total", ["verde"]), "Ya existe")):
    try:
        gc.set_group(g, args[0], args[1], cl); err = ""
    except ValueError as e:
        err = str(e)
    chk("1 error claro: {}".format(txt), txt in err, err)
chk("1 una clase quitada sale del grupo; grupo vacío desaparece",
    gc.groups_for(g, gc.class_list())[0]["clases"] == ["verde", "seca"]
    and gc.groups_for([{"nombre": "X", "clases": ["vegetacion_no_verde"]}], gc.class_list()) == [])
cols = gc.csv_columns(cl, g)
chk("2 CSV: columnas del grupo y definición", "grupo_vegetacion_total_pct" in cols and "grupos" in cols)
paths = gc.write_csvs(r, {"archivo": "f.png"}, [(1, 1)] * 100, labels, [None] * 100, os.path.join(OUT, "r"), "x")
rows = list(csv.reader(open(paths[0], encoding="utf-8-sig")))
h = rows[0]
chk("2 CSV: 47 puntos, 47 % y la definición del grupo", rows[1][h.index("grupo_vegetacion_total_puntos")] == "47"
    and rows[1][h.index("grupos")] == "Vegetación total = Vegetación verde + Vegetación seca + Vegetación no verde")
hp = os.path.join(OUT, "r.html")
gc.write_html(r, {"archivo": "f.png", "modo_area": "Cuadro", "lado_m": 1, "area_m2": 1}, a, [], [], hp, "x")
ht = open(hp, encoding="utf-8").read()
chk("2 informe: sección «Grupos de clases» con el grupo", "<h2>Grupos de clases</h2>" in ht and "Vegetación total" in ht
    and "37,5 – 56,7 %" in ht.replace("37.5", "37,5").replace("56.7", "56,7"))
r0 = gc.summarize(a, labels, classes=cl)
p0 = gc.write_csvs(r0, {"archivo": "f.png"}, [(1, 1)] * 100, labels, [None] * 100, os.path.join(OUT, "r0"), "x")
h0 = list(csv.reader(open(p0[0], encoding="utf-8-sig")))[0]
chk("2 sin grupos: sin columnas de grupo", not any(c.startswith("grupo_") for c in h0))

# ventana de grupos
D = GroupsDialog(cl, [])
chk("3 grupo nuevo: propone «Vegetación total» con verde, seca y las clases «vegetación…»",
    D.combo.currentText() == NEW and D.name.text() == "Vegetación total"
    and [k for k, cb in D.checks.items() if cb.isChecked()] == ["verde", "seca", "vegetacion_no_verde"])
D.save_group("Vegetación total", ["verde", "vegetacion_no_verde"])
chk("3 guardar y editar", D.groups == [{"nombre": "Vegetación total", "clases": ["verde", "vegetacion_no_verde"]}]
    and D.combo.currentText() == "Vegetación total")
D.save_group("Vegetación viva", ["verde", "vegetacion_no_verde"])
chk("3 renombrar el grupo elegido (no duplica)", [x["nombre"] for x in D.groups] == ["Vegetación viva"])
D.delete_group("Vegetación viva")
chk("3 quitar", D.groups == [])

# ventana principal
img = np.zeros((600, 800, 3), np.uint8); img[:, :400] = (40, 150, 40); img[:, 400:] = (150, 110, 80)
png = os.path.join(OUT, "f.png"); Image.fromarray(img).save(png)
W = GroundCoverDialog(None); W.show(); W.load_photo(png)
W.add_class("Vegetación no verde")
for c in ((20, 20), (780, 20), (780, 580), (20, 580)):
    W._on_canvas_click(*c)
W.seed_spin.setValue(5); W.prepare_area(confirm=False)
W.set_groups(gc.set_group([], "Vegetación total", ["verde", "vegetacion_no_verde"], W.classes))
pend = [i for i, x in enumerate(W.labels) if x is None]
for i in pend[:7]:
    W.label_point(i, "vegetacion_no_verde")
n_v = sum(1 for x in W.labels if x == "verde")
chk("4 ventana: resumen con «Grupos de clases» y la suma", "Grupos de clases:" in W.out.toPlainText()
    and W.res["grupos"]["Vegetación total"]["puntos"] == n_v + 7)
chk("4 grupos guardados para las próximas fotos", gc.load_groups()[0]["nombre"] == "Vegetación total"
    and GroundCoverDialog(None).groups[0]["clases"] == ["verde", "vegetacion_no_verde"])
for i in pend[:7]:
    W.labels[i] = None
W.remove_class("vegetacion_no_verde")
chk("4 al quitar la clase, sale del grupo", W.groups == [{"nombre": "Vegetación total", "clases": ["verde"]}]
    and gc.load_groups()[0]["clases"] == ["verde"])
from cobdosel.help_texts import GROUND_HELP_HTML
chk("5 ayuda: grupos de clases", "Grupos de clases" in GROUND_HELP_HTML and "no la suma de los intervalos" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
