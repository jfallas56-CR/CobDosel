"""CobDosel 0.15.6: «Siguiente» (N) asigna la clase marcada al punto actual y pasa al siguiente (la primera vez solo
muestra el primer punto); «Saltar sin clasificar» (S); contador «Sin clasificar: k de n puntos» y número del punto.

Uso: python3 -I test_suelo_v01506.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
Qt = QtCore.Qt
img = np.full((1200, 1600, 3), (150, 110, 80), np.uint8); img[:, :400] = (30, 160, 40)   # 1/4 verde a la izquierda
png = os.path.join(OUT, "suelo.png"); Image.fromarray(img).save(png)
d = GroundCoverDialog(None); d.resize(1200, 800); d.show(); app.processEvents()
d.load_photo(png)
chk("0 antes de preparar: indica que se prepare el área", "Prepare el área" in d.progress_lbl.text())
for x, y in ((100, 100), (1500, 100), (1500, 1100), (100, 1100)):
    d._on_canvas_click(x, y)
d.seed_spin.setValue(11); d.prepare_area()
n = len(d.labels)
pend = [i for i, lab in enumerate(d.labels) if lab is None]
txt = d.progress_lbl.text()
chk("1 contador «Sin clasificar: k de n puntos» tras preparar", "Sin clasificar: {} de {} puntos".format(len(pend), n)
    in txt and "pulse «Siguiente» (N) para ir al primero" in txt, txt)
d.class_group.button(2).setChecked(True)          # vegetación seca
a = d.advance()
chk("2 primera vez «Siguiente»: muestra el primer punto sin clasificar, sin asignarle clase",
    a == pend[0] and d.labels[a] is None and d.canvas.current == d.points[a], (a, pend[0]))
chk("2 contador con el número del punto actual", "punto actual: n.º {} (sin clasificar)".format(a + 1)
    in d.progress_lbl.text(), d.progress_lbl.text())
b = d.advance()
chk("3 «Siguiente»: asigna la clase marcada (vegetación seca) al punto actual y pasa al siguiente",
    d.labels[a] == "seca" and b == pend[1], (d.labels[a], b))
chk("3 contador baja en 1", "Sin clasificar: {} de {}".format(len(pend) - 1, n) in d.progress_lbl.text())
c = d.advance()
chk("4 la clase marcada se mantiene: el segundo punto también queda como vegetación seca",
    d.labels[b] == "seca" and c == pend[2])
d.class_group.button(4).setChecked(True)          # el usuario elige otra clase y luego «Siguiente»
e = d.advance()
chk("5 otra clase marcada antes de «Siguiente»: se asigna esa (suelo)", d.labels[c] == "suelo" and e == pend[3])
f = d.next_unclassified()
chk("6 «Saltar» (S): no clasifica y pasa al siguiente", d.labels[e] is None and f == pend[4])
d.next_btn.click()
chk("7 el botón «Siguiente (N): asigna la clase marcada» hace lo mismo",
    d.next_btn.text() == "Siguiente (N): asigna la clase marcada" and d.labels[f] == "suelo")
QtTest.QTest.keyClick(d.canvas, Qt.Key.Key_N); app.processEvents()
chk("7 tecla N con el foco en el lienzo: asigna y pasa", d.labels[pend[5]] == "suelo", d.labels[pend[5]])
cur = d.current_idx
QtTest.QTest.keyClick(d.canvas, Qt.Key.Key_S); app.processEvents()
chk("7 tecla S: salta", d.labels[cur] is None and d.current_idx != cur)
# un punto ya clasificado (por clic) no se reclasifica con «Siguiente»
d.class_group.button(3).setChecked(True)
x0, y0 = d.points[pend[0]]
d._on_canvas_click(x0, y0)
chk("8 clic en un punto: lo clasifica con la clase marcada y lo hace actual",
    d.labels[pend[0]] == "hojarasca" and d.current_idx == pend[0])
d.class_group.button(5).setChecked(True)
d.advance()
chk("8 «Siguiente» desde un punto ya clasificado no lo cambia", d.labels[pend[0]] == "hojarasca")
for _ in range(n + 2):
    if d.advance() is None:
        break
chk("9 al terminar: 0 sin clasificar, «todos clasificados»",
    d.res["sin_clasificar"] == 0 and "todos clasificados" in d.progress_lbl.text(), d.progress_lbl.text())
chk("9 el punto saltado se clasificó al volver a él (vuelta completa)", d.labels[e] == "no_id")
from cobdosel.help_texts import GROUND_HELP_HTML
chk("10 ayuda: «Siguiente» asigna la clase marcada; «Saltar» (S); contador",
    "asigna la <b>clase marcada</b>" in GROUND_HELP_HTML and "Saltar sin clasificar» (S)" in GROUND_HELP_HTML
    and "Sin clasificar: 37 de 100 puntos" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
