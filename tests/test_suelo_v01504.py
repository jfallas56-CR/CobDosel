"""CobDosel 0.15.4: las flechas del teclado mueven la vista (Mayús: paso mayor) en «Cobertura del suelo» y en
«Calibrar con baldosas»; el lienzo toma el foco al cargar la foto.

Uso: python3 -I test_suelo_v01504.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.tile_calibration_dialog import TileCalibrationDialog
Qt = QtCore.Qt
img = np.full((1200, 1600, 3), 120, np.uint8); img[:, :800] = (30, 160, 40)
png = os.path.join(OUT, "suelo.png"); Image.fromarray(img).save(png)


def press(w, key, shift=False):
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    QtTest.QTest.keyClick(w, key, mod)
    app.processEvents()


for name, dlg, load in (("Cobertura del suelo", GroundCoverDialog(None), lambda d: d.load_photo(png)),
                        ("Calibrar con baldosas", TileCalibrationDialog(None), lambda d: d.load_photo(0, png))):
    dlg.resize(1200, 800); dlg.show(); app.processEvents()
    load(dlg); app.processEvents()
    cv = dlg.canvas
    chk(name + ": el lienzo tiene el foco al cargar la foto", cv.hasFocus() or app.focusWidget() is cv,
        type(app.focusWidget()).__name__)
    cv.setFocus(); app.processEvents()
    cv.zoom_by(4.0)
    c0 = cv.center
    s, _a, _b = cv._geom()
    press(cv, Qt.Key.Key_Right)
    dx = cv.center[0] - c0[0]
    chk(name + ": → mueve la vista a la derecha 10 % del ancho visible", abs(dx - 0.1 * cv.width() / s) < 1e-6,
        (dx, 0.1 * cv.width() / s))
    press(cv, Qt.Key.Key_Left)
    chk(name + ": ← vuelve", abs(cv.center[0] - c0[0]) < 1e-6)
    press(cv, Qt.Key.Key_Down, shift=True)
    chk(name + ": Mayús + ↓ baja 50 % del alto visible", abs(cv.center[1] - c0[1] - 0.5 * cv.height() / s) < 1e-6)
    press(cv, Qt.Key.Key_Up, shift=True)
    chk(name + ": Mayús + ↑ vuelve", abs(cv.center[1] - c0[1]) < 1e-6)
    for _ in range(40):
        press(cv, Qt.Key.Key_Left, shift=True)
    chk(name + ": el centro no sale de la imagen", cv.center[0] == 0.0)
    cv.fit(); cv.zoom_by(4.0)
    z = cv.zoom
    press(cv, Qt.Key.Key_Plus)
    chk(name + ": con el foco en el lienzo, + sigue acercando (pasa a la ventana)", cv.zoom > z, (z, cv.zoom))
    # flechas recibidas por la ventana (foco en otro control que no las usa)
    c1 = cv.center
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    dlg.keyPressEvent(ev)
    chk(name + ": la ventana también pasa las flechas al lienzo", cv.center[1] > c1[1])

g = GroundCoverDialog(None); g.show(); g.load_photo(png)
for x, y in ((200, 150), (1400, 150), (1400, 1050), (200, 1050)):
    g._on_canvas_click(x, y)
g.seed_spin.setValue(5); g.prepare_area()
g.canvas.setFocus(); g.next_unclassified(); app.processEvents()
i0 = g.current_idx
press(g.canvas, Qt.Key.Key_4)
chk("Cobertura del suelo: con el foco en el lienzo, 4 sigue clasificando el punto actual", g.labels[i0] == "suelo")
src = open(os.path.join(sys.argv[1], "cobdosel", "help_texts.py"), encoding="utf-8").read()
chk("Ayuda: flechas en la ayuda completa", "las <b>flechas</b> del teclado para mover la vista" in src)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
