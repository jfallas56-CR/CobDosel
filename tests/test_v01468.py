"""CobDosel 0.14.68: nota «se registra como copa o cielo», sin «Informe la máscara usada»; valores de la sección 2
del informe alineados a la derecha; GNSS en lugar de GPS; latitud, longitud y altitud sin dato → «Sin datos».

Uso: python3 -I test_v01468.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.canopy_analysis import classify_measurement_type
note = classify_measurement_type(27.0, 63.0)["note"]
chk("1 nota: «se registra como copa o cielo», sin «dice»", "se registra como copa o cielo" in note and "solo dice" not in note)
chk("1 nota sin «Informe la máscara usada» (la nota ya da la máscara)",
    "Informe la máscara usada" not in note and "máscara de horizonte 63.0°" in note)
H, W = 1500, 2000
rng = np.random.default_rng(5)
img = np.full((H, W, 3), 45, np.uint8)
img[np.kron(rng.random((H // 25, W // 25)) < 0.3, np.ones((25, 25), bool))] = 225
p1 = os.path.join(OUT, "foto.jpg"); Image.fromarray(img).save(p1, quality=92)     # sin EXIF ni coordenadas
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
d._load_image_into_dialog(p1)
H, W = d.image_array.shape[:2]
cal = calibrate_regular_lens(12.1, 39.8, 567.5, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
d.zenith_max.setValue(27.0); d._on_glama_cut(); d._on_run(); app.processEvents()
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "res.csv"), ""))
d._on_export_csv()
from cobdosel.result_columns import read_results_csv   # v0.16.2: CSV transpuesto
rr = read_results_csv(os.path.join(OUT, "res.csv"))
chk("2 CSV: latitud, longitud y altitud sin dato → «Sin datos»",
    all(rr[k] == "Sin datos" for k in ("latitude", "longitude", "elevation_m")),
    [rr[k] for k in ("latitude", "longitude", "elevation_m")])
chk("2 CSV: lo que no aplica sigue «No aplica»", rr["horizon_angles"] == "No aplica")
out = generate_html_report(d.last_results, os.path.join(OUT, "foto.html"), include_images=False)
raw = open(out, encoding="utf-8").read()
chk("3 informe: «Coordenadas GNSS (WGS84)», sin «GPS» visible", "Coordenadas GNSS (WGS84):" in raw
    and "GPS" not in re.sub(r"<[^>]+>", " ", raw))
chk("3 informe: valores de la sección 2 alineados a la derecha",
    re.search(r"\.kv-row span\.val \{\s*font-weight: 600;\s*text-align: right;", raw) is not None
    and re.search(r"\.kv-row \{\s*display: flex;\s*justify-content: space-between;", raw) is not None)
panel = d.results_text.toPlainText()
chk("4 ventana: botón «Añadir punto GNSS al mapa»; panel sin «GPS»",
    d.gps_point_btn.text() == "Añadir punto GNSS al mapa" and "GPS" not in panel)
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
