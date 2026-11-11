"""CobDosel 0.14.67: «No aplica» en las celdas sin valor de los CSV; LAI solo con ojo de pez de 180°; sin
glama_engine ni índices lineales antiguos (calibración sin R: no se analiza); measurement_fit_rms_px.

Uso: python3 -I test_v01467.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.canopy_analysis import lai_applies, LAI_NOT_APPLICABLE
from cobdosel.csv_format import csv_cell
from cobdosel.lens_calibration import calibrate_fisheye_from_radius
# 1) «No aplica»
chk("1 csv_cell: None, texto vacío y lista vacía → «No aplica»",
    csv_cell(None) == "No aplica" and csv_cell("  ") == "No aplica" and csv_cell([]) == "No aplica"
    and csv_cell(0) == 0 and csv_cell(False) == "No" and csv_cell(0.0, ",") == "0,0")
# 2) lai_applies
chk("2 LAI: lente regular → no aplica", not lai_applies({"lens_type": "regular"}, 40.6))
chk("2 LAI: ojo de pez que llega a 90° → aplica", lai_applies({"lens_type": "fisheye"}, 90.0))
chk("2 LAI: ojo de pez recortado a 40° → no aplica", not lai_applies({"lens_type": "fisheye"}, 40.0))
# 3) análisis con lente regular
H, W = 1500, 2000
rng = np.random.default_rng(3)
img = np.full((H, W, 3), 45, np.uint8)
img[np.kron(rng.random((H // 25, W // 25)) < 0.3, np.ones((25, 25), bool))] = 225
p1 = os.path.join(OUT, "foto.jpg"); Image.fromarray(img).save(p1, quality=92)
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
d._load_image_into_dialog(p1)
H, W = d.image_array.shape[:2]
cal = calibrate_regular_lens(12.1, 39.8, 567.5, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
d.zenith_max.setValue(27.0); d._on_glama_cut(); d._on_run(); app.processEvents()
res = d.last_results
panel = d.results_text.toPlainText()
chk("3 lente regular: LAI no calculado", res["lai"]["applies"] is False and res["lai"]["lai_effective"] is None)
chk("3 panel: «LAIe Miller …: No aplica (solo con lente ojo de pez de 180°…)»",
    "(LAIe Miller):      No aplica (solo con lente ojo de pez de 180°" in panel)
chk("3 panel sin «CaCo lineal» ni «versiones ≤ 0.10»", "CaCo lineal" not in panel and "≤ 0.10" not in panel)
chk("3 sin bandera glama_engine ni caco_linear en las métricas",
    "glama_engine" not in res["metrics"] and "caco_linear_pct" not in res["metrics"])
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "res.csv"), ""))
d._on_export_csv()
from cobdosel.result_columns import read_results_csv   # v0.16.2: CSV transpuesto
rr = read_results_csv(os.path.join(OUT, "res.csv"))
hdr, row = list(rr.keys()), list(rr.values())
chk("3 CSV sin glama_engine ni caco_linear_pct; con measurement_fit_rms_px",
    "glama_engine" not in hdr and "caco_linear_pct" not in hdr and "measurement_fit_rms_px" in hdr)
chk("3 CSV: ninguna celda vacía", all(c.strip() for c in row), [hdr[i] for i, c in enumerate(row) if not c.strip()])
chk("3 CSV: LAI «No aplica» (efectivo, rango, confiable y por anillo)",
    all(row[hdr.index(k)] == "No aplica" for k in ("lai_effective", "lai_zenith_max_deg", "lai_reliable"))
    and all(row[i] == "No aplica" for i, k in enumerate(hdr) if k.startswith("lai_ring")))
chk("3 CSV: horizon_angles y exif_image_direction_deg «No aplica»",
    row[hdr.index("horizon_angles")] == "No aplica" and row[hdr.index("exif_image_direction_deg")] == "No aplica")
out = generate_html_report(res, os.path.join(OUT, "foto.html"), include_images=False)
ht = " ".join(re.sub(r"<[^>]+>", " ", open(out, encoding="utf-8").read()).split())
chk("3 informe: LAI «No aplica» con el motivo", "Índice de área foliar efectivo (Miller) No aplica" in ht
    and "solo con lente ojo de pez de 180°" in ht)
# 4) ojo de pez de 180°: LAI calculado
calf = calibrate_fisheye_from_radius(min(W, H) / 2.0, projection="polar", center_xy=(W / 2.0, H / 2.0),
                                     image_width_px=W, image_height_px=H)
d.calibration = calf; d.center_xy = (W / 2.0, H / 2.0)
d._on_run(); app.processEvents()
lf = d.last_results["lai"]
chk("4 ojo de pez: LAI calculado", lf.get("applies") is True and lf["lai_effective"] is not None
    and lf["lai_effective"] > 0, lf.get("lai_effective"))
# 5) calibración sin R: no se analiza
d.last_results = None
old = dict(calf); old.pop("virtual_radius_px", None)
d.calibration = old
msgs.clear(); d._on_run()
chk("5 calibración sin radio del hemisferio: no se analiza y pide recalibrar",
    d.last_results is None and any("Recalibre con el círculo D/H" in str(m[1]) for m in msgs), msgs[-1:])
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
