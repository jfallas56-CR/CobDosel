"""CobDosel 0.15.1: «Cobertura del suelo»: vegetación verde sombreada solo si se pide (V), puntos como anillos con cruz,
zoom y «Siguiente sin clasificar» (N), semilla visible que se conserva, aviso antes de descartar clases, «Nueva
cuadrícula», campos del modo que no se usa desactivados, contador de esquinas y clic derecho para quitar la última.

Uso: python3 -I test_suelo_v01501.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel import ground_cover as gc
from cobdosel.ground_cover_dialog import GroundCoverDialog, RIGHT
GREEN, SOIL = (30, 160, 40), (150, 110, 80)
H, W = 1200, 1600
big = np.zeros((H, W, 3), np.uint8); big[:] = SOIL
big[:, : W // 2] = GREEN
jpg = os.path.join(OUT, "suelo.png"); Image.fromarray(big).save(jpg)
d = GroundCoverDialog(None); d.resize(1200, 800); d.show(); app.processEvents()
d.load_photo(jpg)
# modo y esquinas
chk("1 modo cuadro: altura y calibración desactivadas; contador de esquinas activo",
    not d.height_spin.isEnabled() and not d.cal_combo.isEnabled() and d.corner_lbl.isEnabled())
for x, y in ((200, 150), (1400, 150), (1400, 1050)):
    d._on_canvas_click(x, y)
chk("1 contador: «Esquinas: 3 de 4»", d.corner_lbl.text().startswith("Esquinas: 3 de 4"))
d._on_canvas_click(1000, 600, RIGHT)
chk("1 clic derecho quita la última esquina", len(d.corners) == 2 and d.corner_lbl.text().startswith("Esquinas: 2 de 4"))
d.mode_fixed.setChecked(True); app.processEvents()
chk("1 modo área fija: altura y calibración activas; esquinas borradas", d.height_spin.isEnabled()
    and d.cal_combo.isEnabled() and not d.corner_lbl.isEnabled() and d.corners == [])
d.mode_quad.setChecked(True)
for x, y in ((200, 150), (1400, 150), (1400, 1050), (200, 1050)):
    d._on_canvas_click(x, y)
# semilla
d.seed_spin.setValue(1234)
d.prepare_area()
pts1 = list(d.points)
chk("2 la cuadrícula usa la semilla del campo y la registra", d.seed == 1234 and d.meta["semilla"] == 1234)
d.prepare_area()
chk("2 misma semilla → misma cuadrícula", d.points == pts1)
# vegetación verde oculta por defecto; V la muestra
img = d.canvas.pix.toImage()
x0, y0 = int(d.points[0][0]), int(d.points[0][1])
gx = int(d.area.shape[1] * 0.25); gy = int(d.area.shape[0] / 2)
c = img.pixelColor(gx, gy)
chk("3 «Mostrar vegetación verde» desactivado: se ven los colores reales", not d.show_green.isChecked()
    and (c.red(), c.green(), c.blue()) == GREEN, (c.red(), c.green(), c.blue()))
d.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_V, QtCore.Qt.KeyboardModifier.NoModifier))
c = d.canvas.pix.toImage().pixelColor(gx, gy)
chk("3 tecla V: vegetación verde sombreada en magenta", d.show_green.isChecked() and c.red() > 100 and c.blue() > 100,
    (c.red(), c.green(), c.blue()))
d.show_green.setChecked(False)
# anillos con cruz: se ve la imagen dentro del anillo
app.processEvents()
shot = d.canvas.grab().toImage()
s, ox, oy = d.canvas._geom()
i_soil = next(i for i, lab in enumerate(d.labels) if lab is None)
px, py = d.points[i_soil]
cx, cy = ox + px * s, oy + py * s
rad = max(6.0, min(14.0, 6.0 * d.canvas.zoom))
q = shot.pixelColor(int(cx + 0.35 * rad), int(cy + 0.35 * rad))
chk("4 punto como anillo con cruz: dentro del anillo se ve el suelo", abs(q.red() - SOIL[0]) < 25 and abs(q.green() - SOIL[1]) < 25,
    (q.red(), q.green(), q.blue()))
# siguiente sin clasificar
i = d.next_unclassified()
chk("5 «Siguiente sin clasificar» centra la vista con zoom en el primer punto sin clase",
    i == i_soil and d.canvas.center == (float(px), float(py)) and d.canvas.zoom >= 4.0)
d.canvas.fit()
chk("5 «Ajustar vista»", d.canvas.zoom == 1.0)
# aviso antes de descartar
d.label_point(i_soil, "suelo")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
ok_prep = d.prepare_area()
chk("6 con puntos clasificados a mano, «Preparar área» pregunta; «No» los conserva",
    ok_prep is False and d.labels[i_soil] == "suelo")
ok_new = d.new_grid()
chk("6 «Nueva cuadrícula» también pregunta; «No» conserva la cuadrícula", ok_new is False and d.seed == 1234)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
ok_new = d.new_grid()
chk("6 «Sí»: otra semilla, otra cuadrícula, sin clases manuales",
    ok_new and d.seed != 1234 and d.seed_spin.value() == d.seed and d.points != pts1 and d._manual_labels() == 0)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
