"""CobDosel 0.16.2: Resultados_CobDosel_<foto>.csv transpuesto: una fila por variable (variable, descripcion, valor).

Uso: python3 -I test_v01602.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>

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
from cobdosel import result_columns as rc
from cobdosel.help_texts import FULL_HELP_HTML
rows = list(csv.reader(open(os.path.join(OUT, "res.csv"), encoding="utf-8-sig")))
chk("1 encabezado: variable, descripcion, valor", rows[0] == ["variable", "descripcion", "valor"], rows[0])
keys = [r[0] for r in rows[1:]]
chk("1 una fila por variable, sin repetidas, con la foto primero", len(keys) == len(set(keys)) and keys[0] == "image_id"
    and len(keys) > 50, len(keys))
chk("1 toda variable tiene descripción en español (ninguna repite la clave)",
    all(r[1] != r[0] and r[1] for r in rows[1:]), [r[0] for r in rows[1:] if r[1] == r[0]][:5])
d_ = dict((r[0], r[2]) for r in rows[1:])
chk("1 valores: CaCo numérico, versión del complemento, «Sin datos» y «No aplica»",
    0 <= float(d_["canopy_cover_caco_index_pct"]) <= 100 and d_["plugin_version"] == VERSION
    and d_["latitude"] == "Sin datos" and d_["horizon_angles"] == "No aplica")
chk("1 anillos y sectores descritos por patrón", rc.describe("cover_pct_ring3") == "Cobertura del anillo 3 (%)"
    and rc.describe("gap_pct_ring2_S5") == "Fracción de claros del anillo 2, sector S5 (%)"
    and rc.describe("lai_ring1_0-7.5deg") == "LAI del anillo 1 (0–7.5°)")
rr = rc.read_results_csv(os.path.join(OUT, "res.csv"))
chk("2 read_results_csv: formato transpuesto", rr["measurement_type"] == "caco" and rr["plugin"] == "CobDosel")
wide = os.path.join(OUT, "ancho.csv")
with open(wide, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";"); w.writerow(["image_id", "canopy_cover_caco_index_pct"]); w.writerow(["a.jpg", "71,5"])
rw = rc.read_results_csv(wide)
chk("2 read_results_csv: formato ancho anterior (con «;»)", rw == {"image_id": "a.jpg", "canopy_cover_caco_index_pct": "71,5"}, rw)
chk("3 manual/ayuda: el CSV de una foto se describe como transpuesto", "una fila por variable" in FULL_HELP_HTML)
print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
