"""CobDosel 0.15.12: modo reglamentario (el verde lo decide la regla), «Cargar área y cuadrícula de un CSV…» y
«Comparar clasificaciones» (acuerdo, kappa de Cohen, tabla de confusión, puntos en desacuerdo).

Uso: python3 -I test_suelo_v01512.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel import ground_compare as gcmp
from cobdosel.ground_compare_dialog import GroundCompareDialog
gc.CUSTOM_CLASSES_FILE = os.path.join(OUT, "clases.json")

# 1) kappa: ejemplo del protocolo (30 puntos no verdes)
pairs = ([("seca", "seca")] * 15 + [("seca", "suelo"), ("seca", "no_id")] + [("suelo", "seca")] + [("suelo", "suelo")] * 8
         + [("no_id", "seca")] + [("no_id", "no_id")] * 3)
po, pe, k = gcmp.cohen_kappa(pairs)
chk("1 ejemplo del protocolo: acuerdo 0,867, esperado 0,429, kappa 0,77", round(po, 3) == 0.867 and round(pe, 3) == 0.429
    and round(k, 2) == 0.77, (po, pe, k))
chk("1 escala de Landis y Koch", gcmp.landis_koch(0.77) == "sustancial" and gcmp.landis_koch(0.85) == "casi perfecto"
    and gcmp.landis_koch(0.5) == "moderado" and gcmp.landis_koch(-0.1) == "pobre")
chk("1 acuerdo perfecto: kappa 1", gcmp.cohen_kappa([("a", "a"), ("b", "b")])[2] == 1.0)

# imagen: mitad izquierda verde, mitad derecha suelo
img = np.zeros((800, 1000, 3), np.uint8); img[:, :500] = (40, 150, 40); img[:, 500:] = (150, 110, 80)
png = os.path.join(OUT, "parcela.png"); Image.fromarray(img).save(png)
CORNERS = [(50, 40), (950, 40), (950, 760), (50, 760)]

msgs.clear()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
A = GroundCoverDialog(None); A.show(); A.load_photo(png)
for c in CORNERS:
    A._on_canvas_click(*c)
A.seed_spin.setValue(4242); A.points_spin.setValue(100); A.prepare_area(confirm=False)
auto_g = [i for i, a in enumerate(A.auto) if a == "verde"]
pend = [i for i, a in enumerate(A.auto) if a is None]
chk("0 área de prueba: verdes automáticos y sin clasificar", len(auto_g) > 30 and len(pend) > 30, (len(auto_g), len(pend)))

# 2) modo reglamentario
A.labels[auto_g[0]] = "seca"; A.labels[pend[0]] = "verde"           # dos violaciones previas (clasificación libre)
A.reg_check.setChecked(True)
chk("2 al activar con violaciones: pregunta y devuelve la clase automática",
    A.regulatory() and A.labels[auto_g[0]] == "verde" and A.labels[pend[0]] is None and not A.violations())
chk("2 verde automático → seca: rechazado", not A.label_point(auto_g[1], "seca") and A.labels[auto_g[1]] == "verde"
    and "Modo reglamentario" in A.progress_lbl.text())
chk("2 verde automático → No identificable: permitido (objeto que no es vegetación)",
    A.label_point(auto_g[1], "no_id") and A.labels[auto_g[1]] == "no_id")
chk("2 sin clasificar → verde a mano: rechazado", not A.label_point(pend[0], "verde") and A.labels[pend[0]] is None)
A.class_group.button(1).setChecked(True)          # verde marcado
A.current_idx = None
first = A.advance(); again = A.advance()
chk("2 «Siguiente» con verde marcado en un punto no verde: no asigna ni avanza", first == again == pend[0]
    and A.labels[pend[0]] is None, (first, again))
A.class_group.button(2).setChecked(True)          # seca
for _ in range(len(pend) + 2):
    if A.advance() is None:
        break
chk("2 «Siguiente» con seca: clasifica todos los no verdes", A.res["sin_clasificar"] == 0)
pA = os.path.join(OUT, "A")
meta_a = A.export_meta()
chk("2 export_meta: modo_reglamentario «Sí»; esquinas registradas", meta_a["modo_reglamentario"] == "Sí"
    and gc.parse_corners(meta_a["esquinas_px"]) == [tuple(map(float, c)) for c in CORNERS], meta_a.get("esquinas_px"))
pathsA = gc.write_csvs(A.res, meta_a, A.points, A.labels, A.auto, pA, VERSION, ";", ",")
rowA = list(csv.reader(open(pathsA[0], encoding="utf-8-sig"), delimiter=";"))
chk("2 CSV de foto: columnas modo_reglamentario y esquinas_px", rowA[1][rowA[0].index("modo_reglamentario")] == "Sí"
    and "|" in rowA[1][rowA[0].index("esquinas_px")])
hA = os.path.join(OUT, "A.html"); gc.write_html(A.res, meta_a, A.area, A.points, A.labels, hA, VERSION)
chk("2 informe: fila «Modo reglamentario»", "Sí: el verde lo decide la regla de Canopeo" in open(hA, encoding="utf-8").read())

# 3) segundo analista con la misma área y cuadrícula
B = GroundCoverDialog(None); B.show(); B.load_photo(png)
B.seed_spin.setValue(1); B.points_spin.setValue(49)
B.load_area_from_csv(pathsA[0], confirm=False)
chk("3 «Cargar área y cuadrícula»: mismas esquinas, semilla, puntos y clase automática",
    B.seed == 4242 and len(B.points) == 100 and B.points == A.points and B.auto == A.auto and B.corners == A.corners)
B.reg_check.setChecked(True)
diff_idx = pend[1:5]
for i in pend:
    B.label_point(i, "suelo" if i in diff_idx else A.labels[i])
B.label_point(auto_g[1], "no_id")
pB = os.path.join(OUT, "B")
pathsB = gc.write_csvs(B.res, B.export_meta(), B.points, B.labels, B.auto, pB, VERSION, ",", ".")
other = os.path.join(OUT, "otra.png"); Image.fromarray(img).save(other)
C = GroundCoverDialog(None); C.load_photo(other)
try:
    C.load_area_from_csv(pathsA[0], confirm=False); err = ""
except ValueError as e:
    err = str(e)
chk("3 CSV de otra foto: error claro", "es de la foto «parcela.png»" in err, err)

# 4) comparar
ra = gcmp.read_points_csv(pathsA[1]); rb = gcmp.read_points_csv(pathsB[1])
chk("4 lee CSV con «;» y coma decimal y con «,» y punto", len(ra) == len(rb) == 100 and abs(ra[0]["x"] - rb[0]["x"]) < 1e-9)
res = gcmp.compare(ra, rb)
pairs = [(a["clase"], b["clase"]) for a, b in zip(ra, rb) if not a["automatica"]]
chk("4 se comparan solo los puntos que la regla dejó sin clasificar", res["n_comparados"] == len(pend) == len(pairs))
chk("4 desacuerdos: los 4 puntos cambiados", sorted(d["punto"] for d in res["desacuerdos"]) == [i + 1 for i in diff_idx])
chk("4 kappa = fórmula de Cohen sobre esos pares", abs(res["kappa"] - gcmp.cohen_kappa(pairs)[2]) < 1e-12
    and res["acuerdo_obs"] == (len(pend) - 4) / float(len(pend)))
chk("4 verde cambiado a No identificable por los dos: registrado como automático cambiado",
    res["automaticos_cambiados"] == [auto_g[1] + 1])
res_all = gcmp.compare(ra, rb, only_unclassified=False)
chk("4 opción «todos los puntos»", res_all["n_comparados"] == 100)
for bad_b, txt in ((rb[:-1], "distinto número de puntos"), ([dict(p, archivo="x.jpg") for p in rb], "fotos distintas"),
                   ([dict(p, x=p["x"] + 5) for p in rb], "otra posición")):
    try:
        gcmp.compare(ra, bad_b); err = ""
    except ValueError as e:
        err = str(e)
    chk("4 error claro: {}".format(txt), txt in err, err)
rb2 = [dict(p, automatica=("Vegetación verde" if p["punto"] == pend[0] + 1 else p["automatica"])) for p in rb]
r2 = gcmp.compare(ra, rb2)
chk("4 clase automática distinta (otra área): no se compara y se avisa", r2["automatica_distinta"] == [pend[0] + 1]
    and any("clase automática difiere" in ln for ln in gcmp.summary_lines(r2)))

# 5) ventana «Comparar clasificaciones»
D = GroundCompareDialog(None, ground_dialog=B)
D.file_a.setText(pathsA[1]); D.file_b.setText(pathsB[1]); D.compare()
chk("5 ventana: resumen, tabla y lista de desacuerdos", "kappa de Cohen" in D.out.toPlainText()
    and "Tabla de confusión" in D.out.toPlainText() and D.dis_list.count() == 4)
ok_go, _m = D.goto_point(diff_idx[0] + 1)
chk("5 ir al punto en «Cobertura del suelo»", ok_go and B.current_idx == diff_idx[0] and B.canvas.current == B.points[diff_idx[0]])
for c in CORNERS:
    C._on_canvas_click(*c)
C.prepare_area(confirm=False)
D2 = GroundCompareDialog(None, ground_dialog=C); D2.file_a.setText(pathsA[1]); D2.file_b.setText(pathsB[1]); D2.compare()
ok2, m2 = D2.goto_point(diff_idx[0] + 1)
chk("5 con otra foto abierta no va al punto y lo explica", not ok2 and "otra foto" in m2, m2)
hp = os.path.join(OUT, "comparacion.html")
gcmp.write_html(D.res, hp, "Ana", "Beto", "A_puntos.csv", "B_puntos.csv", VERSION)
ht = open(hp, encoding="utf-8").read()
chk("5 informe HTML: kappa, tabla, desacuerdos y veredicto", "Kappa de Cohen" in ht and "Tabla de confusión" in ht
    and "Puntos en desacuerdo" in ht and ("Cumple" in ht or "No cumple" in ht) and "Ana: Suelo desnudo" in ht)
chk("5 botón «Comparar clasificaciones…» y «Cargar área…» en la ventana", A.compare_btn.text() == "Comparar clasificaciones…"
    and A.load_area_btn.text() == "Cargar área y cuadrícula de un CSV…")
from cobdosel.help_texts import GROUND_HELP_HTML
chk("6 ayuda: modo reglamentario, doble clasificación y comparar", "Modo reglamentario" in GROUND_HELP_HTML
    and "Comparar clasificaciones" in GROUND_HELP_HTML and "Cargar área y cuadrícula de un CSV" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
