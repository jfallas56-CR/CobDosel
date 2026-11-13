"""CobDosel 1.1.0: detalle por anillos con cobertura llevada a la vertical, peso en el CaCo y aporte al CaCo (texto, informe HTML y CSV).

Uso: python3 -I test_v01700.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>

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
import math
from cobdosel.canopy_analysis import ring_caco_detail
from cobdosel.result_columns import read_results_csv, describe
from cobdosel.help_texts import FULL_HELP_HTML
# 1 cálculo con los anillos de la foto del usuario (0–27°, 4 anillos)
rings = [(16839, 153321), (61077, 477624), (63578, 858856), (125888, 1352196)]
b = [(0, 6.75), (6.75, 13.5), (13.5, 20.25), (20.25, 27.0)]
pr = [{"ring": i + 1, "cover_fraction": 1 - l / n, "gap_fraction": l / n} for i, (l, n) in enumerate(rings)]
dd = ring_caco_detail(pr, b)
chk("1 pesos en el CaCo = ½(sin² θ_sup − sin² θ_inf) normalizados: 6,70 / 19,74 / 31,68 / 41,88 %",
    [round(x["weight_pct"], 2) for x in dd] == [6.70, 19.74, 31.68, 41.88], [round(x["weight_pct"], 2) for x in dd])
chk("1 los pesos suman 100 %", abs(sum(x["weight_pct"] for x in dd) - 100) < 1e-9)
chk("1 cobertura vertical = 1 − P^cos θ̄: 88,93 / 86,75 / 91,68 / 88,60 %",
    [round(x["cover_vertical_pct"], 2) for x in dd] == [88.93, 86.75, 91.68, 88.60], [round(x["cover_vertical_pct"], 2) for x in dd])
chk("1 cos θ̄ del anillo 4 = ∫cos·sin / ∫sin = 0,9146", abs(dd[3]["mean_cos"] - 0.9146) < 5e-5, dd[3]["mean_cos"])
chk("1 aporte = peso × cobertura vertical", all(abs(x["contribution_pct"] - x["weight_pct"] * x["cover_vertical_pct"] / 100) < 1e-9 for x in dd))
chk("1 la vertical nunca supera a la del ángulo; anillo sin claros = 100 %",
    all(x["cover_vertical_pct"] <= 100 * (1 - p["gap_fraction"]) + 1e-9 for x, p in zip(dd, pr))
    and ring_caco_detail([{"cover_fraction": 1.0, "gap_fraction": 0.0}], [(10, 20)])[0]["cover_vertical_pct"] == 100.0)
d2 = ring_caco_detail([{"cover_fraction": None}, pr[1]], [(0, 6.75), (6.75, 13.5)])
chk("1 anillo sin dato: n/d y el peso se reparte entre los demás", d2[0]["weight_pct"] is None and abs(d2[1]["weight_pct"] - 100) < 1e-9)

# 2 en el análisis real: la suma de los aportes se aproxima al CaCo de 90 anillos finos
res = d.last_results
cover, metrics = res["cover"], res["metrics"]
det = res["ring_detail"]
s_ap = sum(x["contribution_pct"] for x in det if x["contribution_pct"] is not None)
chk("2 (1.1.1) Σ aportes = Índice CaCo exactamente (mismos 90 anillos finos)", abs(s_ap - metrics["canopy_cover_index_pct"]) < 1e-9,
    (s_ap, metrics["canopy_cover_index_pct"]))
chk("2 pesos suman 100 y cob. vert. = aporte / peso", abs(sum(x["weight_pct"] for x in det) - 100) < 1e-9
    and all(abs(x["cover_vertical_pct"] - 100 * x["contribution_pct"] / x["weight_pct"]) < 1e-9 for x in det))
apr = ring_caco_detail(cover["per_ring"], res["ring_boundaries"])
chk("2 pesos cercanos a los analíticos ½(sin² θ_sup − sin² θ_inf) (< 0,5 puntos)",
    all(abs(x["weight_pct"] - y["weight_pct"]) < 0.5 for x, y in zip(det, apr)),
    [(round(x["weight_pct"], 2), round(y["weight_pct"], 2)) for x, y in zip(det, apr)])
from cobdosel.glama_engine import glama_ring_counts, glama_indices, glama_ring_detail
cal_ = res["calibration"]; R_ = cal_["virtual_radius_px"]
cnt = glama_ring_counts(res["sky_mask"], res["center_xy"], R_, res["zenith_max_deg"], calibration=cal_,
                        projection=cal_.get("projection", "polar"))
caco = glama_indices(cnt, calibration=cal_, radius_px=R_)["canopy_cover_index_pct"]
ok_b = True
for bb in ([(0, 27.0)], [(0, 5.3), (5.3, 11.1), (11.1, 27.0)], [(i * 2.7, (i + 1) * 2.7) for i in range(10)]):
    dd2 = glama_ring_detail(cnt, bb, calibration=cal_, radius_px=R_)
    ok_b &= abs(sum(x["contribution_pct"] for x in dd2 if x["contribution_pct"] is not None) - caco) < 1e-9
chk("2 Σ aportes = CaCo con 1, 3 y 10 anillos (límites que cortan anillos finos)", ok_b)
tl = [l for l in d.results_text.toPlainText().splitlines() if l.startswith("Total")][0]
chk("2 la fila Total del panel muestra el mismo valor que el CaCo del panel",
    tl.split()[-1] == "{:.2f}".format(metrics["canopy_cover_index_pct"]), tl)
txt = d.results_text.toPlainText()
chk("2 texto: columnas «Cob.vert.%», «Peso CaCo%», «Aporte», fila Total y notas", all(k in txt for k in (
    "Cob.vert.%", "Peso CaCo%", "Aporte", "Total", "la suma de los aportes es el Índice CaCo", "no la promedie")), txt[-600:])
hdr = [l for l in txt.splitlines() if l.startswith("Anillo  Rango")][0]
r1 = [l for l in txt.splitlines() if l.startswith("1 ") and "–" in l][0]
chk("2 texto: filas alineadas con el encabezado", len(r1) == len(hdr), (len(r1), len(hdr)))
rr = read_results_csv(os.path.join(OUT, "res.csv"))
chk("3 CSV: cover_vertical_pct_ringN y caco_weight_pct_ringN con descripción", all(
    "cover_vertical_pct_ring{}".format(i) in rr and "caco_weight_pct_ring{}".format(i) in rr for i in (1, 2, 3, 4))
    and describe("caco_weight_pct_ring2") == "Peso del anillo 2 en el Índice CaCo (%)"
    and describe("cover_vertical_pct_ring1").startswith("Cobertura del anillo 1 llevada a la vertical"))
chk("3 CSV: pesos del CSV iguales a los del cálculo", abs(float(rr["caco_weight_pct_ring4"]) - det[3]["weight_pct"]) < 1e-6)
ht_ = None
hp = os.path.join(OUT, "inf.html")
generate_html_report(res, hp, include_images=False)
ht = open(hp, encoding="utf-8").read()
chk("4 HTML: columnas «Cobertura llevada a la vertical», «Peso en el CaCo», «Aporte» y fila Total",
    all(k in ht for k in ("Cobertura llevada a la vertical (%)", "Peso en el CaCo (%)", "Aporte al CaCo", "<strong>Total</strong>")))
chk("4 HTML: el Total del detalle es el mismo número que el Índice CaCo del informe",
    "<td class='num'><strong>{:.2f}</strong></td></tr>".format(metrics["canopy_cover_index_pct"]) in ht
    and "{:.2f}%".format(metrics["canopy_cover_index_pct"]) in ht)
chk("5 ayuda: peso en el CaCo y cobertura llevada a la vertical", "peso en el caco" in FULL_HELP_HTML.lower()
    and "llevada a la vertical" in FULL_HELP_HTML)
print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
