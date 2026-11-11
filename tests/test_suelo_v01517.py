"""CobDosel 0.15.17: verdes automáticos dudosos (puntaje: zona naranja, cercanía a los umbrales, borde de hoja);
«Siguiente verde dudoso» (D) recorre solo esos, del más al menos dudoso; columna duda_verde; conteo en el informe.

Uso: python3 -I test_suelo_v01517.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases.json"); gc.GROUPS_FILE = os.path.join(OUT, "grupos.json")
Qt = QtCore.Qt
CLEAR, NEAR, ORANGE, SOIL = (40, 150, 40), (120, 130, 60), (94, 100, 80), (160, 120, 90)
chk("0 colores de prueba: los tres verdes para Canopeo; ORANGE no verde para ExG − ExR",
    all(gc.canopeo_mask(np.full((1, 1, 3), c, np.uint8))[0, 0] for c in (CLEAR, NEAR, ORANGE))
    and not gc.exg_exr_mask(np.full((1, 1, 3), ORANGE, np.uint8))[0, 0]
    and gc.exg_exr_mask(np.full((1, 1, 3), NEAR, np.uint8))[0, 0])
img = np.zeros((100, 400, 3), np.uint8)
img[:, :100] = CLEAR; img[:, 100:200] = NEAR; img[:, 200:300] = ORANGE; img[:, 300:] = SOIL
img[:, 46:49] = SOIL; img[:, 51:54] = SOIL   # hoja delgada (2 px, x = 49–50) entre suelo: el punto x = 50 es de borde
pts = [(20, 50), (50, 50), (150, 50), (250, 50), (350, 50)]   # claro, borde, umbral, naranja, suelo
dd = gc.green_doubt(img, pts)
chk("1 verde claro: puntaje bajo, sin motivos", dd[0][0] < 0.1 and dd[0][1] == [], dd[0])
chk("1 borde de hoja: motivo «borde»", "borde" in dd[1][1] and dd[1][0] >= 0.5, dd[1])
chk("1 cerca del umbral (R/G 0,92): motivo «umbral»", dd[2][1] == ["umbral"] and 0.5 <= dd[2][0] < 1, dd[2])
chk("1 zona naranja: puntaje 1, motivo «naranja»", dd[3][0] == 1.0 and "naranja" in dd[3][1], dd[3])
chk("1 punto no verde: sin puntaje", dd[4] is None)
chk("1 orden de duda: naranja, luego borde/umbral; el claro no entra",
    gc.doubtful_order(dd)[0] == 3 and set(gc.doubtful_order(dd)) == {1, 2, 3}, gc.doubtful_order(dd))

# ventana: recorrido de D
big = np.zeros((600, 900, 3), np.uint8)
big[:, :300] = CLEAR; big[:, 300:600] = NEAR; big[:, 600:] = ORANGE
png = os.path.join(OUT, "f.png"); Image.fromarray(big).save(png)
d = GroundCoverDialog(None); d.show(); d.load_photo(png)
for c in ((2, 2), (897, 2), (897, 597), (2, 597)):
    d._on_canvas_click(*c)
d.seed_spin.setValue(9); d.points_spin.setValue(196); d.prepare_area(confirm=False)
n_auto = sum(1 for x in d.doubt if x is not None)
order = d.doubt_order
chk("2 todos verdes; solo las franjas dudosas entran (no la clara)", n_auto == 196 and 0 < len(order) < n_auto
    and all(d.points[i][0] > 300 for i in order), (len(order), n_auto))
txt = d.out.toPlainText()
chk("2 resumen: «Verdes automáticos dudosos: k de n verdes. Total de puntos a verificar: k …» (texto de 0.16.3)",
    "Verdes automáticos dudosos: {} de {} verdes. Total de puntos a verificar: {} · verificados: 0 · restantes: {}".format(
        len(order), n_auto, len(order), len(order)) in txt)
d.current_idx = None
seen = [d.next_doubtful() for _ in range(len(order))]
chk("3 D recorre solo los dudosos, en orden de duda, sin repetir", seen == order)
chk("3 la etiqueta explica por qué es dudoso", "Verde dudoso" in d.progress_lbl.text())
chk("3 revisados = todos; el resumen lo dice", "verificados: {} · restantes: 0".format(len(order)) in d.out.toPlainText())
QtTest.QTest.keyClick(d.canvas, Qt.Key.Key_D); app.processEvents()
chk("3 tecla D: vuelve al primero (cíclico)", d.current_idx == order[0])
pth = gc.write_csvs(d.res, d.export_meta(), d.points, d.labels, d.auto, os.path.join(OUT, "r"), VERSION,
                    zones=d.zones, doubt=d.doubt)
rows = list(csv.reader(open(pth[1], encoding="utf-8-sig")))
idd = rows[0].index("duda_verde")
chk("4 CSV de puntos: columna duda_verde con el puntaje", all(rows[1 + i][idd] != "No aplica" for i in range(len(d.points))))
hp = os.path.join(OUT, "r.html")
gc.write_html(d.res, d.export_meta(), d.area, d.points, d.labels, hp, VERSION)
chk("4 informe: verdes automáticos dudosos k de n", "Verdes automáticos dudosos (revisados por el analista): {} de {}".format(
    len(order), n_auto) in open(hp, encoding="utf-8").read())
d.new_grid(confirm=False)
chk("5 «Nueva cuadrícula»: recalcula los dudosos y reinicia los revisados", d.reviewed == set() and len(d.doubt) == len(d.points))
from cobdosel.help_texts import GROUND_HELP_HTML
chk("6 ayuda: puntaje de duda y «Siguiente verde dudoso» (D)", "puntaje de duda" in GROUND_HELP_HTML
    and "Siguiente verde dudoso" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
