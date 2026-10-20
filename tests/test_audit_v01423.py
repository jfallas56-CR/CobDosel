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


import tempfile, math
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra else ""))

from cobdosel.canopy_analysis import minimum_threshold_from_hist as M
x = np.arange(256)
base = 4000*np.exp(-0.5*((x-45)/15)**2) + 2500*np.exp(-0.5*((x-215)/12)**2)
h0 = base.copy(); h0[0] += 60000
chk("Mínimo con dosel saturado en 0 corta entre los modos (no en 1)", M(h0)[0] == M(base)[0] == 140, M(h0))
r2 = np.random.default_rng(1)
uni = np.bincount(np.clip(r2.normal(100, 20, 300000), 0, 255).astype(int), minlength=256)
chk("Mínimo con un solo modo → None (se usa Otsu y se avisa)", M(uni)[0] is None, M(uni))

from cobdosel.circle_measure import measure
for mode, pts in (("cruz", [(10, 10)]*4), ("diametro", [(5, 5)]*2), ("ajuste", [(5, 5)]*6),
                  ("ajuste", [(i, i) for i in range(5)])):
    try:
        r = measure(pts, mode, (4000, 3000)); chk("medición degenerada {} → None".format(mode), r is None, r and r["diameter_px"])
    except Exception as e:
        chk("medición degenerada {} sin excepción".format(mode), False, e)
c8 = [(2000+500*math.cos(math.radians(a)), 1500+500*math.sin(math.radians(a))) for a in range(0, 360, 45)]
chk("medición válida (8 puntos) intacta", abs(measure(c8, "ajuste", (4000, 3000))["diameter_px"] - 1000) < 1e-6)

from cobdosel import batch_core as bc
from cobdosel.lens_calibration import calibrate_fisheye_from_radius
img = (r2.random((600, 800, 3)) * 255).astype(np.uint8)
os.makedirs(OUT, exist_ok=True); pth = os.path.join(OUT, "fe.png"); Image.fromarray(img).save(pth)
fe = calibrate_fisheye_from_radius(260, "equisolid", center_xy=[440, 270], image_width_px=800, image_height_px=600)
from cobdosel.canopy_dialog import CobDoselDialog
d = CobDoselDialog(Iface())
d._load_image_into_dialog(pth)
d.calibration = dict(fe); d.center_xy = tuple(fe["center_xy"]); d.zenith_max.setValue(40.0)
d.threshold_spin.setValue(128); d._set_cut(128, "manual"); d._on_run()
b = bc.analyze_photo(pth, fe, 40.0, d._current_channel_mode(), True, "fixed", 128)
chk("lote = una foto con ojo de pez descentrado", abs(d.last_results["metrics"]["canopy_cover_index_pct"] - b["caco"]) < 1e-9,
    (d.last_results["metrics"]["canopy_cover_index_pct"], b["caco"]))

# Calibración existente: no se sobrescribe sin confirmar
import cobdosel.calibration_store as cs
tmpd = tempfile.mkdtemp()
cs.DEFAULT_DIR = tmpd
import cobdosel.canopy_dialog as cdm
cdm.calibration_path = lambda n, directory=None: cs.calibration_path(n, tmpd)
cdm.save_calibration = lambda n, c, metadata=None, directory=None: cs.save_calibration(n, c, metadata, tmpd)
names = iter(["Pixel 10", "Pixel_10", "Pixel_10"])
QInputDialog.getText = staticmethod(lambda *a, **k: (next(names), True))
d._on_save_calibration()
f = cs.calibration_path("Pixel 10", tmpd); t1 = open(f).read()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
d.calibration["focal_length_px"] = 999.0; d._on_save_calibration()
chk("«Pixel_10» no reemplaza a «Pixel 10» si se responde No", open(f).read() == t1)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
d._on_save_calibration()
chk("se reemplaza si se responde Sí", '"focal_length_px": 999.0' in open(f).read())

print("\nRESULTADO:", "TODAS LAS PRUEBAS PASAN" if ok_all else "HAY FALLOS")
sys.exit(0 if ok_all else 1)
