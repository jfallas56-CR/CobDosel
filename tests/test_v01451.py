"""CobDosel 0.14.51: índices de apertura con su referencia real (convención de GLAMA), fracciones del hemisferio
sobre una misma base y una sola nota metodológica (sin «mide directamente la proyección perpendicular»).

Uso: python3 -I test_v01451.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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



import math, re
from cobdosel.html_report import generate_html_report
from cobdosel.canopy_analysis import classify_measurement_type
from cobdosel import batch_core as bc
im = np.full((1500, 2000, 3), 235, np.uint8)            # cielo totalmente abierto
p = os.path.join(OUT, "abierto.jpg"); Image.fromarray(im).save(p, quality=95)
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
d._load_image_into_dialog(p)
cal = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, 2000, 1500); d.center_xy = (1000, 750); d._cal_name = "P10"
f = 750.0 / math.tan(math.radians(d.calibration["max_zenith_deg"]))
a, b = 1000.0, 750.0
omega = 4 * math.asin(a * b / math.sqrt((a * a + f * f) * (b * b + f * f)))   # ángulo sólido del encuadre
frame_pct = 100 * omega / (2 * math.pi)
res = {}
for z in (27.0, 45.0):
    d.zenith_max.setValue(z); d.threshold_spin.setValue(128); d._on_run(); app.processEvents()
    m = dict(d.last_results["metrics"]); res[z] = (m, generate_html_report(d.last_results, os.path.join(OUT, "r%d.html" % z),
                                                                          include_images=False), d.results_text.toPlainText())
m, out, panel = res[27.0]
ht = open(out, encoding="utf-8").read()
chk("1 cielo abierto, máscara 63°: apertura GLAMA = área analizada / referencia (44.5 %)",
    abs(m["canopy_openness_pct"] - 100 * m["analysed_fraction_abs_pct"] / m["reference_fraction_pct"]) < 0.01
    and abs(m["canopy_openness_pct"] - 44.5) < 0.3, round(m["canopy_openness_pct"], 2))
chk("1 área analizada = 1 − cos 27° del hemisferio (10.9 %)",
    abs(m["analysed_fraction_abs_pct"] - 100 * (1 - math.cos(math.radians(27)))) < 0.1, round(m["analysed_fraction_abs_pct"], 2))
chk("1 foto en el hemisferio real = ángulo sólido del encuadre (± 0.3 puntos)",
    abs(m["hemisphere_fraction_abs_pct"] - frame_pct) < 0.3, (round(m["hemisphere_fraction_abs_pct"], 2), round(frame_pct, 2)))
chk("1 referencia hasta la esquina de la foto (40–42°), no 90°", 40.0 <= m["reference_zenith_deg"] <= 42.0, m["reference_zenith_deg"])
m45 = res[45.0][0]
chk("1 máscara 45° (sale de la foto): área analizada ≤ foto (antes 23.85 % > 16 %)",
    m45["analysed_fraction_abs_pct"] <= m45["hemisphere_fraction_abs_pct"] + 1e-6, (m45["analysed_fraction_abs_pct"], m45["hemisphere_fraction_abs_pct"]))
ht45 = " ".join(re.sub("<[^>]+>", " ", open(res[45.0][1], encoding="utf-8").read()).split())
# v0.14.64: el informe ya no tiene el grupo de la convención de GLAMA; da la parte del hemisferio real
chk("1 informe con máscara 45°: el área analizada no supera a la foto",
    "16.4 % del hemisferio (la foto entera: 16.4 %)" in ht45, ht45[ht45.find("Área analizada"):][:80])
txt = " ".join(re.sub("<[^>]+>", " ", ht).split())
chk("2 informe: sin el grupo «Índices referidos al hemisferio» (apertura y cierre de GLAMA solo en el CSV)",
    "Índices referidos al hemisferio" not in ht and "están en el CSV de resultados" in txt and "Convención general" not in ht)
chk("2 informe: una misma base para la foto y el área analizada", "10.9 % del hemisferio (la foto entera: 16." in txt)
nota = re.sub("<[^>]+>", " ", ht.split("Nota metodológica")[1].split("</div>")[0])
nota = " ".join(nota.split())
chk("3 nota metodológica: una sola, sin «mide directamente» ni «semiángulo» ni «densiómetro GRS» como equivalencia",
    "estimada con el Índice CaCo" in nota and "mide directamente" not in nota and "semiángulo" not in nota
    and "Comparable al densiómetro" not in nota and "no es una medición directa" in nota and "máscara de horizonte 63.0°" in nota)
chk("3 la misma nota a 27° y a 33° (antes cambiaba a los 30°)",
    classify_measurement_type(27.0)["label"] == classify_measurement_type(33.0)["label"]
    and classify_measurement_type(27.0)["type"] == "caco")
chk("4 panel: sin apertura/cierre de GLAMA ni referencia (v0.14.64), con hemisferio real",
    "Apertura del dosel (GLAMA" not in panel and "Referencia de GLAMA" not in panel
    and "Hemisferio real en la foto" in panel and "Canopy Openness" not in panel)
# CSV de una foto
_save = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "foto.csv"), ""))
try:
    d._on_export_csv(); app.processEvents()
finally:
    QFileDialog.getSaveFileName = _save
from cobdosel.result_columns import read_results_csv   # v0.16.2: CSV transpuesto
rr = read_results_csv(os.path.join(OUT, "foto.csv"))
chk("5 CSV de una foto: referencia, foto y área analizada en el hemisferio real; measurement_type «caco»",
    all(k in rr for k in ("glama_reference_zenith_deg", "hemisphere_fraction_abs_pct", "analysed_fraction_abs_pct"))
    and rr["measurement_type"] == "caco")
# lote
fold = os.path.join(OUT, "lote"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
Image.fromarray(im).save(os.path.join(fold, "A.jpg"), quality=95)
calg = scale_calibration_to_image(cal, 2000, 1500)
bb = bc.run_batch(fold, None, calg, None, photos_per_plot=1)
r0 = bb["fotos"][0]
chk("5 lote: columna «apertura_ref_cenit» junto a apertura y cierre", "apertura_ref_cenit" in bc.PHOTO_CSV_COLUMNS
    and 40.0 <= r0.get("apertura_ref_cenit", 0) <= 42.0, r0.get("apertura_ref_cenit"))
print("TODO OK" if ok_all else "HAY FALLAS")
