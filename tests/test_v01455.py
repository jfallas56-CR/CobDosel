"""CobDosel 0.14.55: parámetros del informe del sitio con nombres legibles, «—» en vez de «None» y fechas sin
microsegundos.

Uso: python3 -I test_v01455.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_from_glama_radius
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
from cobdosel import batch_core as bc
H, W = 1500, 2000
FOT = os.path.join(OUT, "fotos"); shutil.rmtree(FOT, ignore_errors=True); os.makedirs(FOT)
im = np.full((H, W, 3), 50, np.uint8); im[::9] = 220
Image.fromarray(im).save(os.path.join(FOT, "F0.jpg"), quality=92)
cal = scale_calibration_to_image(calibrate_regular_lens(12.1, 39.8, 886.7, 4000, 3000, projection="rectilinear"), W, H)
cal["saved_at"] = "2026-10-23T11:56:50.488047"
b = bc.run_batch(FOT, None, cal, None, photos_per_plot=1)
b["parametros"].update(sitio="Prueba", area_ha=None, analista="JF")
hp = os.path.join(OUT, "s.html"); bc.write_html(b, hp, "x", "Prueba")
ht = open(hp, encoding="utf-8").read()
par = ht.split("<h2>Parámetros</h2>")[1].split("</table>")[0]
chk("1 sin «None» en los parámetros", "None" not in par, re.findall(r"<tr><td>([^<]*)</td><td>None", par))
chk("1 área vacía como «—»", "<tr><td>Área del AOI (ha)</td><td>—</td></tr>" in par)
chk("1 fecha de la calibración sin microsegundos", "<td>Calibración guardada</td><td>2026-10-23 11:56</td>" in par)
chk("1 nombres legibles (no claves con guion bajo)", not re.search(r"<tr><td>[a-z]+_[a-z_]+</td>", par),
    re.findall(r"<tr><td>([a-z]+_[a-z_]+)</td>", par))
paths = bc.write_csvs(b, os.path.join(OUT, "lote"), "x")
site_csv = open(paths[2], encoding="utf-8-sig").read()
chk("2 el CSV del sitio conserva las claves (param_area_ha, param_calibracion_guardada)",
    "param_area_ha" in site_csv and "param_calibracion_guardada" in site_csv)
chk("2 todas las claves posibles tienen nombre legible",
    all(k in bc.PARAM_LABELS for k in b["parametros"]), [k for k in b["parametros"] if k not in bc.PARAM_LABELS])
print("TODO OK" if ok_all else "HAY FALLAS")
