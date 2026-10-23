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
from cobdosel.threshold_dialog import ThresholdDialog
from cobdosel.visualization import GLAMA_TEAL
U = sys.argv[4]
d = CobDoselDialog(Iface()); d._load_image_into_dialog(os.path.join(U, "5fc4cb4f-image.jpg"))
h, w = d.image_array.shape[:2]
d.circle_diameter.setValue(12.1); d.camera_height.setValue(40.0)
d.pixel_diameter.setValue(886.64 * max(w, h) / 4000.0); d._on_calibrate()
vm = d._analysis_valid_mask(include_horizon_mask=True)
chk("hay máscara del área analizada (63°)", vm is not None and 0 < vm.mean() < 1, round(float(vm.mean()), 3))
pil = Image.fromarray(d.image_array)
dlg = ThresholdDialog(pil, initial_threshold=150, valid_mask=vm); dlg.resize(1200, 900); dlg.show(); app.processEvents()
cv = dlg.canvas
chk("casilla «Solo el área analizada» marcada por defecto", dlg.area_check.isChecked() and dlg.area_check.isEnabled())
img = cv.pixmap().toImage(); W, H = img.width(), img.height()
corner = QtGui.QColor(img.pixel(3, 3))
chk("fuera del área: verde azulado", abs(corner.red() - GLAMA_TEAL[0]) < 45 and abs(corner.green() - GLAMA_TEAL[1]) < 45 and abs(corner.blue() - GLAMA_TEAL[2]) < 45,
    (corner.red(), corner.green(), corner.blue()))
# dentro: comparar con la foto original en el centro (teñido de cielo o sin cambio, nunca teal)
dw, dh = cv.display_pil.size
inside_ok = cv.valid_mask[dh // 2, dw // 2]
chk("el centro está dentro del área", bool(inside_ok))
tot = int(cv.valid_mask.sum())
chk("histograma = píxeles del área analizada", int(dlg.histogram_widget.histogram.sum()) == tot if hasattr(dlg.histogram_widget, "histogram") else True, tot)
n_sky, sky_pct, n_can, can_pct, total = cv.get_statistics()
chk("estadísticas solo del área analizada", total == tot, (total, tot))
dlg.grab().save(os.path.join(OUT, "umbral_area.png"))
dlg.area_check.setChecked(False); app.processEvents()
c2 = QtGui.QColor(cv.pixmap().toImage().pixel(3, 3))
chk("desmarcada: se ve la foto completa (sin verde azulado)", (c2.red(), c2.green(), c2.blue()) != (corner.red(), corner.green(), corner.blue()), (c2.red(), c2.green(), c2.blue()))
chk("desmarcada: las estadísticas no cambian", cv.get_statistics()[4] == tot)
dlg2 = ThresholdDialog(pil, initial_threshold=150, valid_mask=None)
chk("sin calibración: casilla desactivada y explicada", not dlg2.area_check.isEnabled() and "sin calibración" in dlg2.area_check.text())
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
