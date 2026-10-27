"""CobDosel 0.14.53: radio de GLAMA solo por el lado menor; nota de geometría real en el resumen de la calibración
(cenit real analizado y máscara equivalente); aviso para calibraciones guardadas con el lado mayor.

Uso: python3 -I test_v01453.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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



import math, re
from cobdosel.lens_calibration import (calibrate_from_glama_radius, true_zenith_of, calibration_zenith_for_true,
                                       zenith_to_pixel_radius)
from cobdosel.camera_check import camera_fingerprint
from cobdosel import batch_core as bc
from cobdosel.batch_dialog import CobDoselBatchDialog
W, H = 1920, 2560
try:
    calibrate_from_glama_radius(1618, W, H, scale_side="long"); raised = False
except ValueError as e:
    raised = "lado mayor" in str(e)
chk("1 «lado mayor» ya no se puede crear", raised)
B = calibrate_from_glama_radius(1618, W, H)
chk("1 lado menor: R = 1618 × 1920 / 1080 = 2876.4 px", abs(B["virtual_radius_px"] - 2876.44) < 0.05, B["virtual_radius_px"])
# geometría real: f del Pixel 10 de la calibración por círculo del usuario (12.1 cm a 39.8 cm, 567.5 px en 1920 px)
A = calibrate_regular_lens(12.1, 39.8, 567.5, W, H, projection="rectilinear")
fA = A["focal_length_px"]
chk("2 B con máscara 63°: analiza 0–24.8° reales", abs(true_zenith_of(B, 27.0, fA) - 24.81) < 0.05, true_zenith_of(B, 27.0, fA))
m_eq = 90 - calibration_zenith_for_true(B, 27.0, fA)
chk("2 máscara de B que cubre 0–27° reales ≈ 60.2°", 60.0 < m_eq < 60.4, m_eq)
r1 = float(zenith_to_pixel_radius(90 - m_eq, B)); r2 = fA * math.tan(math.radians(27.0))
chk("2 con esa máscara el círculo de B coincide con el de A (± 0.5 px)", abs(r1 - r2) < 0.5, (r1, r2))
# ventana principal
exif = {"camera_make": "Google", "camera_model": "Pixel 10", "focal_length_mm": 4.53, "focal_length_35mm": 24}
cam = camera_fingerprint(exif, W, H)
A["camera"] = cam; A["measurement"] = {"mode": "fit", "summary": "prueba"}
cs.save_calibration("P10_circulo", A, metadata={"measurement": A["measurement"]})
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
chk("3 ventana principal: sin elección de lado; dice «lado menor»", not hasattr(d, "glama_side_combo")
    and any("lado menor" in w.text() for w in d.findChildren(QtWidgets.QLabel)))
im = np.full((H, W, 3), 120, np.uint8); p = os.path.join(OUT, "f.jpg"); Image.fromarray(im).save(p)
d._load_image_into_dialog(p); d.exif_data = dict(exif)
d.glama_radius_spin.setValue(1618.0); d._on_calibrate_glama_radius(); app.processEvents()
txt = d.calib_result.text()
print("   ", [l for l in txt.splitlines() if "Geometría real" in l])
chk("3 resumen: cenit real con la calibración propia de la misma cámara",
    "Geometría real (calibración «P10_circulo»)" in txt and "analiza 0–24.8° reales" in txt
    and "use máscara de 60.2°" in txt, txt[-300:])
cs.delete_calibration("P10_circulo") if hasattr(cs, "delete_calibration") else os.remove(dict(cs.list_calibrations())["P10_circulo"])
d._on_calibrate_glama_radius(); app.processEvents()
txt2 = d.calib_result.text()
line = [l for l in txt2.splitlines() if "Geometría real" in l]
print("   ", line)
chk("3 sin calibración propia: usa el EXIF y lo dice (aproximado)", bool(line) and "EXIF 24 mm eq., aproximado" in line[0])
d.exif_data = {}; B2 = dict(B); B2["camera"] = None
chk("3 sin focal de referencia: nota sin números", any("Guarde una calibración por círculo" in l for l in d._glama_radius_notes(B2)))
# calibración guardada con el lado mayor (versiones anteriores)
L = dict(B); L["glama_scale_side"] = "long"; L["virtual_radius_px"] = 1618 * 2560 / 1080.0
chk("4 calibración guardada con «lado mayor»: aviso en el resumen", any("lado mayor" in l and "ya no se ofrece" in l
    for l in d._glama_radius_notes(L)))
fold = os.path.join(OUT, "lote"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
Image.fromarray(im).save(os.path.join(fold, "A.jpg"))
bb = bc.run_batch(fold, None, L, None, photos_per_plot=1)
chk("4 lote con esa calibración: aviso en los avisos del sitio", bc.LONG_SIDE_WARNING in bb["avisos"])
bb2 = bc.run_batch(fold, None, B, None, photos_per_plot=1)
chk("4 con el lado menor no hay aviso", bc.LONG_SIDE_WARNING not in bb2["avisos"])
cs.save_calibration("Larga", L, metadata={})
bd = CobDoselBatchDialog(None); bd._refresh_calibrations(); bd.cal_combo.setCurrentIndex(bd.cal_combo.findData("Larga")); app.processEvents()
chk("4 ventana del lote: el aviso aparece al elegirla", "ya no se ofrece" in bd.cal_info.text())
print("TODO OK" if ok_all else "HAY FALLAS")
