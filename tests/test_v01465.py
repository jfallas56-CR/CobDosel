"""CobDosel 0.14.65: el informe HTML de una foto incluye todo lo de «Calibración y máscara» del panel (cámara de la
calibración y de la foto con la comprobación de lente, n.º de anillos, además de lo que ya tenía).

Uso: python3 -I test_v01465.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
H, W = 1500, 2000
rng = np.random.default_rng(7)
img = np.full((H, W, 3), 45, np.uint8)
img[np.kron(rng.random((H // 25, W // 25)) < 0.45, np.ones((25, 25), bool))] = 225
p1 = os.path.join(OUT, "foto.jpg"); Image.fromarray(img).save(p1, quality=92)
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
d._load_image_into_dialog(p1)
H, W = d.image_array.shape[:2]
cal = calibrate_regular_lens(12.1, 39.8, 567.5 * 4000 / 4000, 4000, 3000, projection="rectilinear")
cal["camera"] = d._current_camera()
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
d.zenith_max.setValue(27.0); d._on_glama_cut(); d._on_run(); app.processEvents()
res = d.last_results
out = generate_html_report(res, os.path.join(OUT, "foto.html"), include_images=False)
ht = " ".join(re.sub(r"<[^>]+>", " ", open(out, encoding="utf-8").read()).split())
c = res["calibration"]
fmt = lambda v, n=2: ("{:.%df}" % n).format(float(v))
items = {
    "D": fmt(c["circle_diameter_cm"]) + " cm", "H": fmt(c["camera_height_cm"]) + " cm",
    "D_px": fmt(c["pixel_diameter_px"]) + " px",
    "semiángulo lado corto": fmt(c["max_zenith_deg"]) + "°",
    "esquina": fmt(res.get("zenith_frame_max_deg") or c["max_zenith_frame_deg"]) + "°",
    "f": fmt(c["focal_length_px"], 1), "R": fmt(c["virtual_radius_px"], 1),
    "medición": (c.get("measurement") or {}).get("summary") or "—",
    "cámara de la calibración": "Cámara de la calibración:",
    # foto sintética sin EXIF: la comprobación de lente queda «no verificada» (con EXIF: «misma lente…»)
    "cámara de la foto y lente": "Cámara: cámara desconocida, 2000×1500 [no verificada]",   # v0.14.69: «Cámara»
    "máscara y anillos": "63.0° sobre el horizonte (cenit 0–27.0°), {} anillos".format(res["n_rings"]),
    "círculo visible": "{:.1f} %".format(res["circle_visible_pct"]),
    "canal": "Azul + Rojo", "clasificación": "Cobertura del dosel estimada con el Índice CaCo (Tichý 2016)",
    "orientación EXIF": "Orientación / rumbo EXIF:",
}
missing = [k for k, v in items.items() if v not in ht]
chk("1 todo lo del panel («Calibración y máscara») está en el informe", not missing, missing)
panel = d.results_text.toPlainText()
chk("1 el panel muestra lo mismo (cámara de la foto con la comprobación de lente)",
    "[no verificada]" in panel and "{} anillos".format(res["n_rings"]) in panel)
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
