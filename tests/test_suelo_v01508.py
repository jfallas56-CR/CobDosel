"""CobDosel 0.15.8: cursor en cruz y líneas guía por el cursor mientras se marcan esquinas («Cobertura del suelo» y
«Calibrar con baldosas»); ayuda con buenas prácticas y fotos que conviene evitar.

Uso: python3 -I test_suelo_v01508.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
import cobdosel.ground_cover_dialog as gcd
Qt = QtCore.Qt
img = np.full((900, 1200, 3), 120, np.uint8)
png = os.path.join(OUT, "f.png"); Image.fromarray(img).save(png)


def move(cv, x, y):
    lp = QtCore.QPointF(x, y)
    NB = Qt.MouseButton.NoButton
    if QT == "PyQt6":
        ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, lp, cv.mapToGlobal(lp), NB, NB,
                               Qt.KeyboardModifier.NoModifier)
    else:
        ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, lp, NB, NB, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(cv, ev)
    app.processEvents()


def pixel(cv, x, y):
    im = cv.grab().toImage()
    c = QtGui.QColor(im.pixel(int(x * im.width() / cv.width()), int(y * im.height() / cv.height())))
    return (c.red(), c.green(), c.blue())


for name, dlg, load, corners in (
        ("Cobertura del suelo", GroundCoverDialog(None), lambda d: d.load_photo(png),
         lambda d, pts: [d._on_canvas_click(*p) for p in pts]),
        ("Calibrar con baldosas", TileCalibrationDialog(None), lambda d: d.load_photo(0, png),
         lambda d, pts: d.set_corners(0, pts))):
    dlg.resize(1200, 800); dlg.show(); app.processEvents()
    load(dlg); app.processEvents()
    cv = dlg.canvas
    chk(name + ": cursor en cruz", cv.cursor().shape() == Qt.CursorShape.CrossCursor)
    s, ox, oy = cv._geom()
    hx, hy = ox + 600 * s, oy + 450 * s
    move(cv, hx, hy)
    far_y = oy + 50 * s
    chk(name + ": marcando esquinas, línea guía vertical por el cursor (blanca sobre la foto gris)",
        cv.guides_on() and pixel(cv, hx, far_y) == (255, 255, 255), pixel(cv, hx, far_y))
    chk(name + ": y línea horizontal", pixel(cv, ox + 50 * s, hy) == (255, 255, 255))
    chk(name + ": fuera de las líneas, la foto", pixel(cv, hx + 40, far_y) == (120, 120, 120), pixel(cv, hx + 40, far_y))
    corners(dlg, [(100, 100), (1100, 100), (1100, 800), (100, 800)])
    move(cv, hx, hy)
    chk(name + ": con las 4 esquinas, sin líneas guía", not cv.guides_on()
        and pixel(cv, hx, far_y) == (120, 120, 120), pixel(cv, hx, far_y))
    cv.leaveEvent(None)
    chk(name + ": al salir el cursor del lienzo se borra la posición", cv.hover is None)

g = GroundCoverDialog(None); g.show(); g.load_photo(png); g.mode_fixed.setChecked(True); app.processEvents()
chk("Cobertura del suelo: modo «Área fija» (sin esquinas) no dibuja líneas guía", not g.canvas.guides_on())
# arrastre: vuelve el cursor en cruz
cv = g.canvas
LB, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
for kind, x, b, bs in (("press", 300, LB, LB), ("move", 360, NB, LB), ("release", 360, LB, NB)):
    t = {"press": QtCore.QEvent.Type.MouseButtonPress, "move": QtCore.QEvent.Type.MouseMove,
         "release": QtCore.QEvent.Type.MouseButtonRelease}[kind]
    lp = QtCore.QPointF(x, 300)
    ev = (QtGui.QMouseEvent(t, lp, cv.mapToGlobal(lp), b, bs, Qt.KeyboardModifier.NoModifier) if QT == "PyQt6"
          else QtGui.QMouseEvent(t, lp, b, bs, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(cv, ev)
chk("después de arrastrar, el cursor vuelve a ser la cruz", cv.cursor().shape() == Qt.CursorShape.CrossCursor)
from cobdosel.help_texts import GROUND_HELP_HTML
chk("ayuda completa: buenas prácticas y fotos que conviene evitar",
    "1. Foto: buenas prácticas" in GROUND_HELP_HTML and "Fotos que conviene evitar" in GROUND_HELP_HTML
    and "Follaje que no es verde" in GROUND_HELP_HTML and "Plantas altas o a distintas alturas" in GROUND_HELP_HTML
    and "Cursor y líneas guía" in GROUND_HELP_HTML)
chk("ayuda corta: buenas prácticas y fotos a evitar", "<b>Evite:</b> sol directo" in gcd.HELP
    and "follaje morado o plateado" in gcd.HELP)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
