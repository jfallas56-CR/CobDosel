"""CobDosel 0.15.0: herramienta «Cobertura del suelo» (foto vertical hacia abajo): vegetación verde automática
(Canopeo, comprobada con ExG − ExR), cuadro enderezado o área fija, intercepción de puntos para vegetación seca,
hojarasca y suelo desnudo, CSV e informe HTML; entrada de menú.

Uso: python3 -I test_suelo_v01500.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel import ground_cover as gc
from cobdosel.ground_cover_dialog import GroundCoverDialog

# 1) reglas de vegetación verde
GREEN, SOIL, DRY = (30, 160, 40), (130, 100, 70), (200, 180, 90)
img = np.zeros((100, 100, 3), np.uint8); img[:, :50] = GREEN; img[:, 50:75] = SOIL; img[:, 75:] = DRY
chk("1 Canopeo: verde 50 % (suelo y pasto seco no son verdes)", abs(100 * gc.canopeo_mask(img).mean() - 50) < 1e-9)
chk("1 ExG − ExR: verde 50 %", abs(100 * gc.exg_exr_mask(img).mean() - 50) < 1e-9)
cy = np.zeros((4, 4, 3), np.uint8); cy[:] = (40, 150, 145)        # B/G = 0,97: verde azulado (agua, sombra azul)
chk("1 Canopeo excluye B/G ≥ 0,95 aunque R/G y ExG pasen", gc.canopeo_mask(cy).mean() == 0)
dk = np.zeros((10, 10, 3), np.uint8); dk[:, :5] = (40, 50, 40); dk[:, 5:] = SOIL
r = gc.summarize(dk, [None] * 4)
chk("1 verde oscuro (ExG = 20): Canopeo no, ExG − ExR sí → diferencia 50 puntos, «a revisar»",
    r["verde_canopeo_pct"] == 0 and r["verde_exgexr_pct"] == 50 and r["revisar"], r["diferencia_pct"])
# 2) cuadro en perspectiva enderezado
H, W, n = 1200, 1600, 600
big = np.full((H, W, 3), 210, np.uint8)
sq = np.zeros((n, n, 3), np.uint8); sq[:, :n // 2] = GREEN; sq[:, n // 2:] = SOIL
src = np.array([[300, 200], [1300, 260], [1250, 1100], [350, 1000]], float)
Hm = gc.homography(np.array([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]], float), src)
yy, xx = np.mgrid[0:H, 0:W]
p = np.linalg.inv(Hm) @ np.stack([xx.ravel(), yy.ravel(), np.ones(H * W)])
u, v = p[0] / p[2], p[1] / p[2]; ok = (u >= 0) & (u < n) & (v >= 0) & (v < n)
big.reshape(-1, 3)[ok] = sq[v[ok].astype(int), u[ok].astype(int)]
rect = gc.rectify_quadrat(big, [src[2], src[0], src[3], src[1]])
chk("2 cuadro en perspectiva (esquinas en cualquier orden) → cuadrado de 1000 px con 50 % verde",
    rect.shape == (1000, 1000, 3) and abs(100 * gc.canopeo_mask(rect).mean() - 50) < 0.5, 100 * gc.canopeo_mask(rect).mean())
try:
    gc.rectify_quadrat(big, [(-50, 0), (100, 0), (100, 100), (0, 100)]); raised = False
except ValueError:
    raised = True
chk("2 cuadro fuera de la foto → error claro", raised)
# 3) área fija
chk("3 lado del área fija: 1 m a 1,3 m con f = 2600 px → 2000 px", abs(gc.fixed_area_side_px(2600, 1.3, 1.0) - 2000) < 1e-9)
try:
    gc.crop_fixed_area(np.zeros((1000, 1000, 3), np.uint8), 2600, 1.3, 1.0); raised = False
except ValueError as e:
    raised = "no cabe" in str(e)
chk("3 área fija que no cabe → error claro", raised)
crop, sp = gc.crop_fixed_area(np.zeros((3000, 4000, 3), np.uint8), 2600, 1.3, 1.0)
chk("3 área fija centrada de 2000 × 2000 px", crop.shape[:2] == (2000, 2000))
# 4) cuadrícula, IC
pts, seed = gc.point_grid((1000, 1000), 100, seed=7)
pts2, _ = gc.point_grid((1000, 1000), 100, seed=7)
chk("4 cuadrícula: 100 puntos, reproducible con la semilla", len(pts) == 100 and pts == pts2 and seed == 7)
lo, hi = gc.wilson_ci(30, 100)
chk("4 IC de Wilson 30/100 = 21,9–39,6 %", abs(lo - 21.89) < 0.05 and abs(hi - 39.59) < 0.05, (lo, hi))
# 5) diálogo
jpg = os.path.join(OUT, "suelo.jpg"); Image.fromarray(big).save(jpg, quality=95)
d = GroundCoverDialog(None); d.show(); app.processEvents()
d.load_photo(jpg)
d.site_edit.setText("Prueba"); d.analyst_edit.setText("JF")
for x, y in src:
    d._on_canvas_click(float(x), float(y))
chk("5 cuatro clics marcan el cuadro", len(d.corners) == 4)
d.prepare_area()
chk("5 área preparada: verde ≈ 50 %, puntos verdes marcados solos",
    abs(d.res["verde_canopeo_pct"] - 50) < 1.0 and d.res["clases"]["verde"]["puntos"] > 30 and d.res["sin_clasificar"] > 30,
    (round(d.res["verde_canopeo_pct"], 2), d.res["clases"]["verde"]["puntos"], d.res["sin_clasificar"]))
pend = [i for i, lab in enumerate(d.labels) if lab is None]
for i in pend[:-1]:
    d.label_point(i, "suelo")
d.label_point(pend[-1], "hojarasca")
chk("5 puntos clasificados: completo, suelo + hojarasca + verde = 100",
    d.res["completo"] and d.res["clases"]["suelo"]["puntos"] + d.res["clases"]["hojarasca"]["puntos"]
    + d.res["clases"]["verde"]["puntos"] == d.res["n_puntos"])
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "suelo_res.csv"), ""))
d._on_csv()
rows = list(csv.DictReader(open(os.path.join(OUT, "suelo_res.csv"), encoding="utf-8-sig")))
pr = list(csv.DictReader(open(os.path.join(OUT, "suelo_res_puntos.csv"), encoding="utf-8-sig")))
chk("5 CSV: una fila, modo «Cuadro», altura «No aplica», «Sí»/«No», sin celdas vacías",
    len(rows) == 1 and rows[0]["modo_area"] == "Cuadro" and rows[0]["altura_camara_m"] == "No aplica"
    and rows[0]["completo"] == "Sí" and rows[0]["revisar"] == "No" and all(v.strip() for v in rows[0].values()),
    [k for k, v in rows[0].items() if not v.strip()])
chk("5 CSV: foto sin EXIF → fecha, latitud y longitud «Sin datos»",
    rows[0]["fecha_exif"] == rows[0]["latitud"] == rows[0]["longitud"] == "Sin datos")
chk("5 CSV de puntos: 100 filas con clase y si se corrigió",
    len(pr) == d.res["n_puntos"] and pr[0]["clase"] in [l for _k, l in gc.CLASSES] and pr[0]["corregido"] in ("Sí", "No"))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "suelo_informe.html"), ""))
d._on_html()
ht = open(os.path.join(OUT, "suelo_informe.html"), encoding="utf-8").read()
chk("5 informe: verde, tabla de clases, imagen, pie con autor y contacto",
    "Vegetación verde (píxeles, regla de Canopeo" in ht and "Suelo desnudo" in ht and "data:image/png;base64," in ht
    and "para QGIS · Autor: Jorge Fallas · Contacto:" in ht and "Patrignani y Ochsner (2015)" in ht)
# área fija con calibración rectilínea
calr = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
cs.save_calibration("Pixel_rect", calr, metadata={})
d2 = GroundCoverDialog(None)
d2.load_photo(jpg)
d2.mode_fixed.setChecked(True); d2.cal_combo.setCurrentIndex(d2.cal_combo.findData("Pixel_rect"))
d2.height_spin.setValue(3.0); d2.side_spin.setValue(0.5)
f = scale_calibration_to_image(calr, W, H)["focal_length_px"]
d2.prepare_area()
exp = int(round(0.5 * f / 3.0))
chk("5 área fija: recorte del lado esperado (0,5 m a 3 m)", abs(d2.area.shape[0] - exp) <= 2, (d2.area.shape, exp))
d2.height_spin.setValue(0.3); d2.side_spin.setValue(2.0)
try:
    d2.prepare_area(); raised = False
except ValueError as e:
    raised = "no cabe" in str(e)
chk("5 área fija que no cabe: error claro en el diálogo", raised)
# 6) menú
src_plugin = open(os.path.join(sys.argv[1], "cobdosel", "cobdosel_plugin.py"), encoding="utf-8").read()
chk("6 menú «Cobertura del suelo»", "CobDosel: Cobertura del suelo (foto hacia abajo)" in src_plugin and "def run_ground" in src_plugin)
print("\nRESULTADO:", "OK" if ok_all else "HAY FALLAS")
sys.exit(0 if ok_all else 1)
