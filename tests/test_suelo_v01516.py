"""CobDosel 0.15.16: opción A: la ventana y el informe muestran Canopeo; ExG − ExR solo con «a revisar» (comprobación
interna; sigue en el CSV). Puntos dudosos: zona cian o naranja de cada punto, «Siguiente punto dudoso» (D), columna
zona_reglas del CSV de puntos y conteo en el informe.

Uso: python3 -I test_suelo_v01516.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
QtTest = importlib.import_module(QT + ".QtTest")
from cobdosel import ground_cover as gc
from cobdosel.ground_cover_dialog import GroundCoverDialog
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases.json"); gc.GROUPS_FILE = os.path.join(OUT, "grupos.json")
for p_ in (gc.CUSTOM_CLASSES_FILE, gc.GROUPS_FILE):
    if os.path.exists(p_):
        os.remove(p_)
Qt = QtCore.Qt
# franjas: verde (las dos reglas), amarillento (solo ExG − ExR), suelo
img = np.zeros((600, 900, 3), np.uint8)
img[:, :300] = (40, 150, 40); img[:, 300:450] = (128, 132, 60); img[:, 450:] = (160, 120, 90)
png = os.path.join(OUT, "f.png"); Image.fromarray(img).save(png)
d = GroundCoverDialog(None); d.show(); d.load_photo(png)
for c in ((5, 5), (895, 5), (895, 595), (5, 595)):
    d._on_canvas_click(*c)
d.seed_spin.setValue(3); d.prepare_area(confirm=False)
z = d.zones
chk("1 zonas por punto: cian en la franja amarillenta, ninguna naranja", z.count("cian") > 5 and z.count("naranja") == 0
    and all((zz == "cian") == bool(d.only_x[int(round(y)), int(round(x))]) for zz, (x, y) in zip(z, d.points)), z.count("cian"))
txt = d.out.toPlainText()
chk("2 ventana: primera línea solo Canopeo", txt.splitlines()[0].startswith("Vegetación verde (Canopeo):")
    and "ExG − ExR:" not in txt.splitlines()[0], txt.splitlines()[0])
chk("2 con «a revisar», el aviso da ExG − ExR", d.res["revisar"] and "A revisar: Las dos reglas del verde" in txt)
chk("2 conteo de puntos sin clasificar en zona cian", "Puntos sin clasificar en zona cian (borde entre hoja verde y material "
    "seco, tejido amarillento u hoja en sombra): {}".format(z.count("cian")) in txt)
first_c = z.index("cian")
d.goto_point(first_c)
chk("3 punto sin clasificar en zona cian: la etiqueta lo explica (v0.15.17: D recorre solo los verdes dudosos)",
    "Zona cian" in d.progress_lbl.text() and "borde entre una hoja verde y material seco" in d.progress_lbl.text())
for k in range(len(d.labels)):
    if d.labels[k] is None:
        d.labels[k] = "seca"
d._refresh()
pth = gc.write_csvs(d.res, d.export_meta(), d.points, d.labels, d.auto, os.path.join(OUT, "r"), VERSION, zones=d.zones)
rows = list(csv.reader(open(pth[1], encoding="utf-8-sig")))
iz = rows[0].index("zona_reglas")
chk("4 CSV de puntos: columna zona_reglas", [r[iz] for r in rows[1:]].count("cian") == z.count("cian")
    and [r[iz] for r in rows[1:]].count("No aplica") == len(z) - z.count("cian"))
from cobdosel import ground_compare as gcmp
chk("4 «Comparar» y «Cargar clasificación» siguen leyendo el CSV", len(gcmp.read_points_csv(pth[1])) == len(z))
rows1 = list(csv.reader(open(pth[0], encoding="utf-8-sig")))
chk("4 CSV de foto: ExG − ExR y la diferencia siguen (auditoría)", "verde_exgexr_pct" in rows1[0] and "diferencia_pct" in rows1[0])
hp = os.path.join(OUT, "r.html")
gc.write_html(d.res, d.export_meta(), d.area, d.points, d.labels, hp, VERSION)
ht = open(hp, encoding="utf-8").read()
chk("5 informe con «a revisar»: sección de diferencias con el conteo de puntos",
    "Dónde difieren Canopeo y ExG − ExR" in ht and "{} en cian y 0 en naranja".format(z.count("cian")) in ht)
chk("5 informe: Canopeo con su referencia; sin la línea fija de ExG − ExR", "regla de Canopeo; Patrignani y Ochsner 2015" in ht
    and "ExG − ExR (comprobación):" not in ht)
img2 = np.zeros((600, 900, 3), np.uint8); img2[:, :450] = (40, 150, 40); img2[:, 450:] = (160, 120, 90)
r2 = gc.summarize(img2, [None] * 4)
hp2 = os.path.join(OUT, "r2.html")
gc.write_html(r2, {"archivo": "g.png", "modo_area": "Cuadro", "lado_m": 1, "area_m2": 1}, img2, [], [], hp2, VERSION)
ht2 = open(hp2, encoding="utf-8").read()
chk("5 informe sin «a revisar»: solo una nota de que la comprobación coincide, sin sección ni imagen de diferencias",
    not r2["revisar"] and "las dos reglas coinciden dentro de 5 puntos" in ht2 and "Dónde difieren" not in ht2
    and ht2.count("data:image/png;base64,") == 1)
from cobdosel.help_texts import GROUND_HELP_HTML
chk("6 ayuda: qué puntos revisar", "Siguiente verde dudoso" in GROUND_HELP_HTML and "zona_reglas" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
