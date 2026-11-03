"""CobDosel 0.15.7: cobertura del suelo: (1) «Diferencias entre las reglas» (C): cian donde solo ExG − ExR ve verde,
naranja donde solo Canopeo, en la vista y en el informe HTML; (2) clases nuevas del usuario (guardadas; teclas 1–9),
en el resumen, el CSV y el informe; (3) aviso «a revisar» que explica que no es un error e incluye la vegetación
amarillenta.

Uso: python3 -I test_suelo_v01507.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
Qt = QtCore.Qt
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases_suelo.json")
if os.path.exists(gc.CUSTOM_CLASSES_FILE):
    os.remove(gc.CUSTOM_CLASSES_FILE)
# imagen: verde claro (ambas reglas), amarillo verdoso (solo ExG − ExR), suelo
img = np.zeros((600, 600, 3), np.uint8)
img[:, :300] = (40, 150, 40)          # verde: las dos
img[:, 300:420] = (128, 132, 60)      # amarillento: R/G = 0.97 → no Canopeo; ExG − ExR > 0
img[:, 420:] = (160, 120, 90)         # suelo
c = gc.canopeo_mask(img); x = gc.exg_exr_mask(img)
chk("0 imagen de prueba: el amarillento es verde solo para ExG − ExR", (~c[:, 300:420]).all() and x[:, 300:420].all()
    and c[:, :300].all() and not x[:, 420:].any())
ox, oc = gc.disagreement_masks(img)
chk("1 disagreement_masks: cian = franja amarillenta (20 % del área), naranja vacío",
    abs(100 * ox.mean() - 20) < 1e-9 and not oc.any())
sh = gc.shade(img, c & ~oc, ox, oc)
chk("1 shade: cian opaco en la franja; magenta en el verde", tuple(sh[10, 350]) == gc.ONLY_EXGEXR_COLOR
    and tuple(sh[10, 10]) != tuple(img[10, 10]) and tuple(sh[10, 500]) == tuple(img[10, 500]))
res0 = gc.summarize(img, [None] * 4)
chk("1 resumen: solo_exgexr_pct 20, solo_canopeo_pct 0, «a revisar»", abs(res0["solo_exgexr_pct"] - 20) < 1e-9
    and res0["solo_canopeo_pct"] == 0 and res0["revisar"])
note = gc.agreement_note(res0)
chk("2 aviso: no es un error, explica la parte dudosa (bordes de hoja, tejido amarillento; texto de v0.15.17)",
    "difieren 20.0 puntos" in note and "No es un error de la foto ni de la clasificación" in note
    and "borde entre hojas verdes y material seco" in note and "tejido amarillento" in note and "cian" in note, note)
chk("2 sin «a revisar», sin aviso", gc.agreement_note(dict(res0, revisar=False)) == "")

# clases nuevas (núcleo)
cu = gc.new_custom_class("Vegetación amarillenta", [])
chk("3 clase nueva: clave sin tildes, color de la paleta", cu[0]["clave"] == "vegetacion_amarillenta"
    and cu[0]["color"] == gc.CUSTOM_PALETTE[0])
for bad, txt in (("vegetación seca", "Ya existe"), ("  ", "Escriba")):
    try:
        gc.new_custom_class(bad, cu); err = ""
    except ValueError as e:
        err = str(e)
    chk("3 error: «{}»".format(txt), txt in err, err)
many = cu
for k in range(3):
    many = gc.new_custom_class("Clase {}".format(k), many)
try:
    gc.new_custom_class("Otra", many); err = ""
except ValueError as e:
    err = str(e)
chk("3 hasta 9 clases (teclas 1–9)", "hasta 9" in err and len(gc.class_list(many)) == 9, err)
chk("3 clave única si el nombre se repite sin tildes", gc.class_key_for("Clase 0", ["clase_0"]) == "clase_0_2")

# ventana
d = GroundCoverDialog(None); d.resize(1200, 800); d.show(); app.processEvents()
png = os.path.join(OUT, "f.png"); Image.fromarray(img).save(png)
d.load_photo(png)
for p in ((5, 5), (595, 5), (595, 595), (5, 595)):
    d._on_canvas_click(*p)
d.seed_spin.setValue(3); d.points_spin.setValue(36); d.prepare_area()
chk("4 ventana: resumen con el aviso nuevo", "No es un error de la foto ni de la clasificación" in d.out.toPlainText())
QtTest.QTest.keyClick(d.canvas, Qt.Key.Key_C); app.processEvents()
img_view = d.canvas.pix.toImage()
xc = int(0.6 * img_view.width()); yc = int(0.5 * img_view.height())     # franja amarillenta: 300–420 px de 600 en la foto
px = QtGui.QColor(img_view.pixel(xc, yc))
chk("4 tecla C: activa «Diferencias» y la vista muestra cian en la franja amarillenta",
    d.show_diff.isChecked() and (px.red(), px.green(), px.blue()) == gc.ONLY_EXGEXR_COLOR, (px.red(), px.green(), px.blue()))
QInputDialog.getText = staticmethod(lambda *a, **k: (a[4], True))      # acepta el nombre propuesto
d._on_new_class()
chk("5 «Nueva clase…» propone «Vegetación amarillenta», la agrega como tecla 6 y la deja marcada",
    [l for _k, l, _c in d.classes][-1] == "Vegetación amarillenta" and d.current_class == "vegetacion_amarillenta"
    and d.class_group.checkedId() == 6 and "teclas 1–6" in d.g3.title())
chk("5 queda guardada para las próximas fotos", gc.load_custom_classes()[0]["nombre"] == "Vegetación amarillenta"
    and [l for _k, l, _c in GroundCoverDialog(None).classes][-1] == "Vegetación amarillenta")
pend = [i for i, lab in enumerate(d.labels) if lab is None]
d.advance(); i0 = d.current_idx
QtTest.QTest.keyClick(d.canvas, Qt.Key.Key_6); app.processEvents()
chk("6 tecla 6 asigna la clase nueva al punto actual", d.labels[i0] == "vegetacion_amarillenta")
chk("6 resumen con la clase nueva", "Vegetación amarillenta" in d.out.toPlainText()
    and d.res["clases"]["vegetacion_amarillenta"]["puntos"] == 1)
try:
    d.remove_class("vegetacion_amarillenta"); err = ""
except ValueError as e:
    err = str(e)
chk("6 no se quita una clase que tiene puntos", "Hay puntos" in err)
try:
    d.remove_class("seca"); err = ""
except ValueError as e:
    err = str(e)
chk("6 las 5 fijas no se quitan", "Solo se pueden quitar" in err)
for i in range(len(d.labels)):
    if d.labels[i] is None:
        d.labels[i] = "suelo"
d._refresh()
paths = gc.write_csvs(d.res, dict(d.meta, archivo="f.png"), d.points, d.labels, d.auto, os.path.join(OUT, "r"), "x")
rows = list(csv.reader(open(paths[0], encoding="utf-8-sig")))
h = rows[0]
chk("7 CSV: columnas de la clase nueva, clases_nuevas y diferencias por regla",
    "vegetacion_amarillenta_puntos" in h and rows[1][h.index("vegetacion_amarillenta_puntos")] == "1"
    and rows[1][h.index("clases_nuevas")] == "Vegetación amarillenta" and "solo_exgexr_pct" in h
    and abs(float(rows[1][h.index("solo_exgexr_pct")]) - d.res["solo_exgexr_pct"]) < 1e-6
    and 19 < d.res["solo_exgexr_pct"] < 21.5, (rows[1][h.index("vegetacion_amarillenta_puntos")],
                                               rows[1][h.index("clases_nuevas")], d.res["solo_exgexr_pct"]))
pts = list(csv.reader(open(paths[1], encoding="utf-8-sig")))
chk("7 CSV de puntos: nombre de la clase nueva", any(r[4] == "Vegetación amarillenta" for r in pts[1:]))
from cobdosel._version import fmt_num  # noqa: E402
hp = os.path.join(OUT, "r.html")
gc.write_html(d.res, dict(d.meta, archivo="f.png"), d.area, d.points, d.labels, hp, "x")
ht = open(hp, encoding="utf-8").read()
chk("8 informe: sección «Dónde difieren Canopeo y ExG − ExR» con su imagen y los %",
    "Dónde difieren Canopeo y ExG − ExR" in ht and ht.count("data:image/png;base64,") == 2
    and "({} % del área)".format(fmt_num(d.res["solo_exgexr_pct"], 2)) in ht)
import base64, io as _io  # noqa: E402
b64 = ht.split("data:image/png;base64,")[2].split('"')[0]
im2 = np.asarray(Image.open(_io.BytesIO(base64.b64decode(b64))).convert("RGB"))
cyan = (im2 == np.array(gc.ONLY_EXGEXR_COLOR)).all(axis=-1).mean()
chk("8 informe: la imagen de diferencias tiene cian en ≈ 20 % de su área", 0.17 < cyan < 0.23, cyan)
chk("8 informe: aviso nuevo y fila de la clase nueva", "No es un error de la foto ni de la clasificación" in ht
    and "Vegetación amarillenta</td>" in ht)
d.labels = [None if lab == "vegetacion_amarillenta" else lab for lab in d.labels]
d.remove_class("vegetacion_amarillenta")
chk("9 «Quitar clase nueva…»: sin puntos, se quita y se guarda", len(d.classes) == 5 and gc.load_custom_classes() == []
    and "teclas 1–5" in d.g3.title())
from cobdosel.help_texts import GROUND_HELP_HTML
chk("10 ayuda: diferencias (C), «no indica un error», clases nuevas",
    "Diferencias entre las reglas (C)" in GROUND_HELP_HTML and "no indica un error de la foto ni de la" in GROUND_HELP_HTML
    and "Clases nuevas:" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
