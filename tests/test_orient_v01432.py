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
    def __init__(s, p, n): s.p = p; s._n = n
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
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
from cobdosel.visualization import oriented_copy_for_qgis, render_threshold_overlay
from cobdosel.exif_gps import load_oriented_rgb_image
# Foto asimétrica (marca roja arriba a la izquierda) guardada con orientación EXIF 3, 6 y 1
base = np.full((300, 400, 3), 200, np.uint8); base[10:60, 10:80] = (255, 0, 0)
for code in (3, 6, 1):
    p = os.path.join(OUT, "o{}.jpg".format(code))
    ex = Image.Exif(); ex[0x0112] = code
    Image.fromarray(base).save(p, exif=ex.tobytes(), quality=95)
    path, c = oriented_copy_for_qgis(p)
    ref = np.asarray(load_oriented_rgb_image(p)[0]).astype(int)
    got = np.asarray(Image.open(path).convert("RGB")).astype(int)
    if code == 1:
        chk("orientación 1: se usa el archivo original", path == p and c == 1)
    else:
        chk("orientación {}: copia orientada = imagen del análisis".format(code),
            path != p and got.shape == ref.shape and np.abs(got - ref).mean() < 1.0, (got.shape, c))
    ov = render_threshold_overlay(p, threshold=128, mode="overlay", max_dim=400)
    ovs = Image.open(ov).size
    chk("orientación {}: superposición con el mismo tamaño/giro que la copia".format(code), ovs == Image.open(path).size, ovs)
# Diálogo: «Añadir imagen original» añade la copia orientada
d = CobDoselDialog(Iface())
d.image_path = os.path.join(OUT, "o3.jpg")
_Proj.instance().layers.clear(); msgs.clear()
d._on_add_image_raster()
lay = list(_Proj.instance().layers.values())
chk("capa añadida es la copia orientada", len(lay) == 1 and lay[0].p != d.image_path and lay[0]._n.endswith("(orientada)"), lay[0]._n if lay else None)
chk("mensaje explica la orientación", msgs and "girada 180°" in msgs[-1][1], msgs[-1][1][:80] if msgs else None)
chk("copia temporal registrada para borrarla", lay and lay[0].p in d._temp_files)
d.image_path = os.path.join(OUT, "o1.jpg"); _Proj.instance().layers.clear()
d._on_add_image_raster()
lay = list(_Proj.instance().layers.values())
chk("orientación 1: se añade la foto original sin copia", lay and lay[0].p == d.image_path and lay[0]._n == "CobDosel — Imagen original")
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
