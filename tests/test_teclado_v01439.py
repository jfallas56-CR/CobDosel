"""Smoke test headless de CobDosel 0.11.0: diálogo real + stubs de qgis.core.

Uso: python3 -I smoke_dialog_v011.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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






import tempfile
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
QtTest = importlib.import_module(QT + ".QtTest")
Qt = QtCore.Qt
opened = []
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (opened.append(1), ("", ""))[1])
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (opened.append(1), ("", ""))[1])
os.makedirs(OUT, exist_ok=True)
jp = os.path.join(OUT, "c.png")
Image.fromarray(np.full((3000, 4000, 3), 120, np.uint8)).save(jp)
from cobdosel.measure_circle_dialog import MeasureCircleDialog
from cobdosel.threshold_dialog import ThresholdDialog

# ---- 1) Intro en la casilla de zoom
md = MeasureCircleDialog(jp); md.resize(1000, 750); md.show(); app.processEvents()
md.zoom_spin.setFocus(); md.zoom_spin.selectAll()
QtTest.QTest.keyClicks(md.zoom_spin, "600"); QtTest.QTest.keyClick(md.zoom_spin, Qt.Key.Key_Return); app.processEvents()
chk("1 medición: Intro tras escribir 600 no abre el selector de archivos", not opened and md.isVisible(), len(opened))
chk("1 medición: el zoom queda en 600 %", abs(md.canvas.display_scale - 6.0) < 1e-6, md.canvas.display_scale)
chk("1 medición: el teclado vuelve a la imagen", md.canvas.hasFocus() or app.focusWidget() is md.canvas)
# ---- 2) flechas mueven la imagen
hb = md.scroll.horizontalScrollBar(); v0 = hb.value()
QtTest.QTest.keyClick(md.canvas, Qt.Key.Key_Right); app.processEvents()
vb = md.scroll.verticalScrollBar(); w0 = vb.value()
QtTest.QTest.keyClick(md.canvas, Qt.Key.Key_Down); app.processEvents()
chk("2 flecha derecha y abajo mueven la imagen", hb.value() > v0 and vb.value() > w0, (v0, hb.value(), w0, vb.value()))
# ---- 3) quitar puntos
cv = md.canvas; md._on_zoom_reset(); app.processEvents(); sc = cv.display_scale
md.mode_combo.setCurrentIndex(md.mode_combo.findData("cruz"))
pts = [(1000, 1500), (3000, 1500), (2000, 500), (2000, 2500)]
for x, y in pts:
    QtTest.QTest.mouseClick(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(int(x * sc), int(y * sc)))
chk("3 cuatro puntos marcados", len(cv.points) == 4)
QtTest.QTest.mousePress(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(int(3000 * sc) + 3, int(1500 * sc)))
QtTest.QTest.mouseRelease(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(int(3000 * sc) + 3, int(1500 * sc)))
chk("3 clic derecho sobre el punto 2 lo quita", len(cv.points) == 3 and all(abs(p[0] - 3000) > 5 or abs(p[1] - 1500) > 5 for p in cv.points))
QtTest.QTest.mouseClick(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(int(2990 * sc), int(1500 * sc)))
chk("3 el punto nuevo ocupa el lugar 2 (se conserva el par E–O)", len(cv.points) == 4 and abs(cv.points[1][0] - 2990) < 3 / sc + 1,
    [tuple(int(v) for v in p) for p in cv.points])
QtTest.QTest.keyClick(cv, Qt.Key.Key_Delete)
chk("3 Supr quita el último punto", len(cv.points) == 3)
md.undo_btn.click()
chk("3 «Quitar último punto»", len(cv.points) == 2)
QtTest.QTest.mousePress(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(5, 5))
QtTest.QTest.mouseRelease(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(5, 5))
chk("3 clic derecho lejos de los puntos no quita nada", len(cv.points) == 2)
# ---- 4) Intro en las otras ventanas
td = ThresholdDialog(Image.open(jp).convert("RGB"), initial_threshold=128); td.show(); app.processEvents()
td.zoom_spin.setFocus(); td.zoom_spin.selectAll(); QtTest.QTest.keyClicks(td.zoom_spin, "200")
QtTest.QTest.keyClick(td.zoom_spin, Qt.Key.Key_Return); app.processEvents()
chk("4 ventana de corte: Intro en el zoom no aplica ni cierra", td.isVisible() and td.result() == 0 and abs(td.canvas.zoom - 2.0) < 1e-6,
    (td.isVisible(), td.result(), td.canvas.zoom))
d = CobDoselDialog(Iface()); d.show(); app.processEvents(); opened.clear()
d.circle_diameter.setFocus(); d.circle_diameter.selectAll(); QtTest.QTest.keyClicks(d.circle_diameter, "20")
QtTest.QTest.keyClick(d.circle_diameter, Qt.Key.Key_Return); app.processEvents()
chk("4 ventana principal: Intro en D no abre ningún selector", not opened and d.isVisible() and abs(d.circle_diameter.value() - 20) < 1e-6)
from qgis.PyQt.QtWidgets import QPushButton
bad = [b.text() for w in (md, td, d) for b in w.findChildren(QPushButton) if b.autoDefault() or b.isDefault()]
chk("4 ningún botón responde a Intro", not bad, bad[:3])
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
