"""CobDosel 0.15.2: «Cobertura del suelo»: «Siguiente sin clasificar» avanza por la cuadrícula y marca el punto actual;
1–5 clasifican el punto actual y pasan al siguiente; zoom con botones y teclas, arrastre para mover la vista; pestaña
«Ayuda»; «Sombrear vegetación verde en magenta (V)».

Uso: python3 -I test_suelo_v01502.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
GREEN, SOIL = (30, 160, 40), (150, 110, 80)
H, W = 1200, 1600
big = np.zeros((H, W, 3), np.uint8); big[:] = SOIL; big[:, : W // 2] = GREEN
png = os.path.join(OUT, "suelo.png"); Image.fromarray(big).save(png)
d = GroundCoverDialog(None); d.resize(1200, 800); d.show(); app.processEvents()
d.load_photo(png)
for x, y in ((200, 150), (1400, 150), (1400, 1050), (200, 1050)):
    d._on_canvas_click(x, y)
d.seed_spin.setValue(77); d.prepare_area()
pend = [i for i, lab in enumerate(d.labels) if lab is None]
a = d.next_unclassified()
chk("1 N: primer punto sin clasificar, marcado como actual (anillo amarillo)", a == pend[0] and d.canvas.current == d.points[a])
b = d.next_unclassified()
chk("1 «Saltar» (S, v0.15.6; antes N) sin clasificar: salta al siguiente (no vuelve al primero)", b == pend[1], (a, b))
d.class_key(4)
chk("2 tecla 4: clasifica el punto actual como suelo y pasa al siguiente sin clasificar",
    d.labels[b] == "suelo" and d.current_idx == pend[2] and d.class_group.checkedId() == 4, (d.labels[b], d.current_idx))
d.auto_next.setChecked(False)
cur = d.current_idx
d.class_key(3)
chk("2 sin «pasar al siguiente»: clasifica y se queda en el punto", d.labels[cur] == "hojarasca" and d.current_idx == cur)
d.auto_next.setChecked(True)
for _ in range(len(pend) + 2):
    if d.current_idx is None:
        break
    d.class_key(4)
chk("2 al terminar la vuelta vuelve al punto saltado y luego no queda ninguno",
    d.res["sin_clasificar"] == 0 and d.current_idx is None and d.labels[a] == "suelo", d.res["sin_clasificar"])
chk("2 «No quedan puntos sin clasificar» en el registro", "No quedan puntos sin clasificar" in d.out.toPlainText()
    or d.next_unclassified() is None)
# clic en un punto: pasa a ser el actual
x0, y0 = d.points[pend[0]]
d.class_group.button(2).setChecked(True)
d._on_canvas_click(x0 + 1, y0 + 1)
chk("3 clic en un punto: lo clasifica con la clase elegida y lo marca como actual",
    d.labels[pend[0]] == "seca" and d.current_idx == pend[0])
# zoom
d.canvas.fit(); d.zoom_in_btn.click()
chk("4 «Acercar»: zoom 1,5", abs(d.canvas.zoom - 1.5) < 1e-9)
d.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Plus, QtCore.Qt.KeyboardModifier.NoModifier))
chk("4 tecla +: acerca", abs(d.canvas.zoom - 2.25) < 1e-9)
d.zoom_out_btn.click()
chk("4 «Alejar»", abs(d.canvas.zoom - 1.5) < 1e-9)
c0 = d.canvas.center
cw = d.canvas


def mev(kind, x, y, button, buttons):
    """Envía un evento de ratón al lienzo (QTest.mouseMove no genera eventos en Qt5 sin pantalla)."""
    t = {"press": QtCore.QEvent.Type.MouseButtonPress, "move": QtCore.QEvent.Type.MouseMove,
         "release": QtCore.QEvent.Type.MouseButtonRelease}[kind]
    lp = QtCore.QPointF(x, y)
    if QT == "PyQt6":
        ev = QtGui.QMouseEvent(t, lp, cw.mapToGlobal(lp), button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    else:
        ev = QtGui.QMouseEvent(t, lp, button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(cw, ev)


# arrastre que empieza y termina sobre el mismo punto de la imagen, ya clasificado (un clic lo reclasificaría con «seca»)
s_, ox_, oy_ = cw._geom()
j = next(i for i, lab in enumerate(d.labels) if lab == "suelo")
ex, ey = ox_ + d.points[j][0] * s_, oy_ + d.points[j][1] * s_
LB, NB = QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton
lab_before = list(d.labels)
# el arrastre mantiene bajo el cursor el mismo punto de la imagen: se suelta sobre el punto j
mev("press", ex, ey, LB, LB)
mev("move", ex + 30, ey + 20, NB, LB)
mev("move", ex + 60, ey + 40, NB, LB)
mev("release", ex + 60, ey + 40, LB, NB)
chk("4 arrastrar mueve la vista y no clasifica", d.canvas.center != c0 and d.labels == lab_before, (c0, d.canvas.center))
# ayuda
chk("5 pestaña «Ayuda» con la ayuda completa", d.tabs.tabText(1) == "Ayuda"
    and "Saltar sin clasificar" in d.help_browser.toPlainText() and "anillo amarillo" in d.help_browser.toPlainText())
chk("5 casilla «Sombrear vegetación verde en magenta (V)»", d.show_green.text() == "Sombrear vegetación verde en magenta (V)")
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
