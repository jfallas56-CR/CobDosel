"""CobDosel 0.16.3: CSV de foto de «Cobertura del suelo» transpuesto (variable, descripcion, valor) y lector de los dos
formatos; «¿Desea abrirlo ahora en Excel?» tras guardar CSV (dosel, lote, suelo, sitio); contador de puntos a verificar;
nota del informe del sitio sobre Wilson y t de Student.

Uso: python3 -I test_suelo_v01603.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
Qt = QtCore.Qt

from cobdosel import ground_batch as gb
from cobdosel import open_files as of
from cobdosel.ground_batch_dialog import GroundBatchDialog
for p_ in (gc.CUSTOM_CLASSES_FILE, gc.GROUPS_FILE):
    if os.path.exists(p_):
        os.remove(p_)

# 1 «¿Desea abrirlo ahora en Excel?»: la pregunta y la apertura, con QMessageBox y QDesktopServices simulados
asked, opened = [], []
of.QMessageBox.question = staticmethod(lambda parent, title, text, *a, **k: (asked.append(text), of.QMessageBox.StandardButton.Yes)[1])
of.QDesktopServices.openUrl = staticmethod(lambda url: (opened.append(url.toLocalFile()), True)[1])
chk("1 un archivo: «¿Desea abrirlo ahora en Excel?» y se abre", of.ask_open_csv(None, ["/x/a.csv"]) is True
    and of.OPEN_ONE in asked[-1] and of.OPEN_NOTE in asked[-1] and opened[-1].endswith("a.csv"))
chk("1 varios: «¿Desea abrir los archivos ahora en Excel?», carpeta una vez y los dos se abren",
    of.ask_open_csv(None, ["/x/a.csv", "/x/b.csv"]) and of.OPEN_MANY in asked[-1] and asked[-1].count("/x") == 1
    and opened[-2:] == ["/x/a.csv", "/x/b.csv"])
of.QMessageBox.question = staticmethod(lambda *a, **k: of.QMessageBox.StandardButton.No)
n0 = len(opened)
chk("1 «No»: no se abre nada; sin rutas no pregunta", of.ask_open_csv(None, ["/x/a.csv"]) is False and len(opened) == n0
    and of.ask_open_csv(None, []) is False)
of.QMessageBox.question = staticmethod(lambda parent, title, text, *a, **k: (asked.append(text), of.QMessageBox.StandardButton.Yes)[1])

# 2 CSV de foto transpuesto
d = GroundCoverDialog(None); d.show(); d.mode_quad.setChecked(True)
im = np.zeros((300, 400, 3), np.uint8); im[:] = (160, 120, 90); im[:, :200] = (40, 150, 40)
ph = os.path.join(OUT, "foto.png"); Image.fromarray(im).save(ph)
d.load_photo(ph)
for c in ((2, 2), (397, 2), (397, 297), (2, 297)):
    d._on_canvas_click(*c)
d.prepare_area(confirm=False)
for i in range(len(d.labels)):
    if d.labels[i] is None:
        d.labels[i] = "suelo"
d._refresh()
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "suelo_t.csv"), ""))
opened.clear()
d._on_csv()
chk("2 tras «Exportar CSV…» se pregunta y se abren los dos CSV", of.OPEN_MANY in asked[-1]
    and [os.path.basename(p) for p in opened] == ["suelo_t.csv", "suelo_t_puntos.csv"], opened)
rows = list(csv.reader(open(os.path.join(OUT, "suelo_t.csv"), encoding="utf-8-sig")))
chk("2 encabezado variable, descripcion, valor; una fila por variable; archivo primero", rows[0] == ["variable", "descripcion", "valor"]
    and rows[1][0] == "archivo" and len(rows) > 40 and len({r[0] for r in rows[1:]}) == len(rows) - 1)
chk("2 descripciones en español para todas las variables (ninguna repite la clave)",
    all(r[1] and r[1] != r[0] for r in rows[1:]), [r[0] for r in rows[1:] if r[1] == r[0]])
dd = {r[0]: r[1] for r in rows[1:]}
chk("2 clases con su nombre y el IC de Wilson", dd["suelo_pct"] == "Clase «Suelo desnudo»: cobertura (%)"
    and "Wilson" in dd["suelo_ic95_inf"] and dd["verde_canopeo_pct"].startswith("Vegetación verde"), dd.get("suelo_pct"))
rr = gc.read_photo_csv(os.path.join(OUT, "suelo_t.csv"))
chk("2 read_photo_csv lee el transpuesto: modo, semilla, completo", rr["modo_area"] == "Cuadro" and rr["semilla"] == str(d.seed_spin.value())
    and rr["completo"] == "Sí")
wide = os.path.join(OUT, "ancho.csv")
with open(wide, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";"); w.writerow(["archivo", "modo_area", "semilla"]); w.writerow(["a.jpg", "Cuadro", "7"])
chk("2 read_photo_csv lee el formato ancho anterior (con «;»)", gc.read_photo_csv(wide) == {"archivo": "a.jpg", "modo_area": "Cuadro", "semilla": "7"})
d2 = GroundCoverDialog(None); d2.show(); d2.mode_quad.setChecked(True); d2.load_photo(ph)
d2.load_classification_from_csv(os.path.join(OUT, "suelo_t_puntos.csv"), confirm=False)
chk("2 «Cargar clasificación» recupera el área y las clases desde el CSV transpuesto",
    len(d2.points) == len(d.points) and d2.labels == d.labels)

# 3 contador de puntos a verificar
d3 = GroundCoverDialog(None); d3.show(); d3.mode_quad.setChecked(True)
im3 = np.zeros((300, 400, 3), np.uint8); im3[:] = (160, 120, 90)
im3[:, :200] = (120, 130, 60)        # verde cerca de los umbrales de Canopeo: dudoso por cercanía (como en test_suelo_v01517)
ph3 = os.path.join(OUT, "rayas.png"); Image.fromarray(im3).save(ph3); d3.load_photo(ph3)
for c in ((2, 2), (397, 2), (397, 297), (2, 297)):
    d3._on_canvas_click(*c)
d3.prepare_area(confirm=False)
tot = len(d3.doubt_order)
chk("3 hay verdes dudosos y el botón muestra «a verificar N, restantes N»", tot > 0
    and d3.doubt_btn.text() == "Siguiente verde dudoso (D) — a verificar {}, restantes {}".format(tot, tot), d3.doubt_btn.text())
chk("3 el resumen muestra el total y los restantes", "Total de puntos a verificar: {} · verificados: 0 · restantes: {}".format(tot, tot)
    in d3.out.toPlainText(), d3.out.toPlainText()[:300])
d3.next_doubtful()
chk("3 tras verificar un punto: restantes N − 1 en el botón y en el registro", "restantes {}".format(tot - 1) in d3.doubt_btn.text()
    and "Puntos a verificar restantes: {} de {}".format(tot - 1, tot) in d3.out.toPlainText(), d3.out.toPlainText()[-200:])
for _ in range(tot - 1):
    d3.next_doubtful()
chk("3 todos verificados: restantes 0 y aviso", "restantes 0" in d3.doubt_btn.text() and "no quedan puntos por verificar" in d3.out.toPlainText())

# 4 resumen del sitio: nota de Wilson y t, y pregunta por los CSV
site = os.path.join(OUT, "sitio"); out = os.path.join(OUT, "res")
for d_ in (site, out):
    shutil.rmtree(d_, ignore_errors=True); os.makedirs(d_)
for nm, fr_ in (("F01.png", 0.25), ("F02.png", 0.5)):
    i_ = np.zeros((300, 400, 3), np.uint8); i_[:] = (160, 120, 90); i_[:, :int(400 * fr_)] = (40, 150, 40)
    Image.fromarray(i_).save(os.path.join(site, nm))
d4 = GroundCoverDialog(None); d4.show(); d4.mode_quad.setChecked(True)
bd = GroundBatchDialog(None, ground_dialog=d4); bd.folder.setText(site); bd.out_dir.setText(out); bd.site.setText("ka")
bd.start()
for _ in range(2):
    for c in ((2, 2), (397, 2), (397, 297), (2, 297)):
        d4._on_canvas_click(*c)
    d4.prepare_area(confirm=False)
    for i in range(len(d4.labels)):
        if d4.labels[i] is None:
            d4.labels[i] = "suelo"
    d4._refresh(); d4.batch_next()
import cobdosel.ground_batch_dialog as gbd
gbd.QMessageBox.question = staticmethod(lambda parent, title, text, *a, **k: (asked.append(text), gbd.QMessageBox.StandardButton.Yes)[1])
opened.clear()
bd._on_summary()
chk("4 tras «Resumen del sitio»: informe abierto y pregunta por los CSV del sitio (sitio y fotos)",
    any(p.endswith("_informe.html") for p in opened) and of.OPEN_MANY in asked[-1]
    and sorted(os.path.basename(p) for p in opened if p.endswith(".csv")) == ["CobDosel_suelo_sitio_ka.csv", "CobDosel_suelo_sitio_ka_fotos.csv"], opened)
ht = open(os.path.join(out, "CobDosel_suelo_sitio_ka_informe.html"), encoding="utf-8").read()
chk("4 informe del sitio: nota «Por qué dos intervalos distintos» (Wilson por foto, t por sitio)",
    "Por qué dos intervalos distintos" in ht and "Wilson" in ht and "t de Student" in ht)

# 5 dosel: «Exportar resultados a CSV…» y el lote preguntan
chk("5 canopy_dialog y batch_dialog usan ask_open_csv", "ask_open_csv(self, [path], \"Resultados exportados\")" in
    open(os.path.join(sys.argv[1], "cobdosel", "canopy_dialog.py"), encoding="utf-8").read()
    and "ask_open_csv(self, paths)" in open(os.path.join(sys.argv[1], "cobdosel", "batch_dialog.py"), encoding="utf-8").read())
print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
