"""CobDosel 0.16.0: cobertura del suelo — procesamiento por sitio. Fotos del sitio (con o sin formulario de fotos),
semilla = base + número de la foto, «Guardar y foto siguiente», continuar donde quedó, estado de cada foto, resumen del
sitio por fotos o por parcelas con media e IC 95 % (t de Student), CSV e informe del sitio.

Uso: python3 -I test_suelo_v01600.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.ground_batch_dialog import GroundBatchDialog
from cobdosel.csv_format import csv_row
for p_ in (gc.CUSTOM_CLASSES_FILE, gc.GROUPS_FILE):
    if os.path.exists(p_):
        os.remove(p_)

# 1 t de Student exacta, sin scipy (tablas de 4 decimales: 0,975 → 12,7062; 4,3027; 3,1824; 2,7764; 2,2622; 2,0452; 1,9799)
tq = {d: gb.t_quantile(0.975, d) for d in (1, 2, 3, 4, 9, 29, 120)}
ref = {1: 12.7062, 2: 4.3027, 3: 3.1824, 4: 2.7764, 9: 2.2622, 29: 2.0452, 120: 1.9799}
chk("1 cuantiles t (0,975) iguales a las tablas (4 decimales)", all(abs(tq[d] - ref[d]) < 0.00006 for d in ref),
    {d: round(v, 4) for d, v in tq.items()})
chk("1 otros niveles: t(0,995; 4) = 4,6041; t(0,95; 7) = 1,8946",
    abs(gb.t_quantile(0.995, 4) - 4.6041) < 0.00006 and abs(gb.t_quantile(0.95, 7) - 1.8946) < 0.00006)
n, m, sd, se, t, lo, hi = gb.mean_ci([70, 72, 68, 75, 71])
chk("1 media e IC 95 %: n 5, media 71,2, DE 2,588; IC = media ± t·DE/√n",
    n == 5 and abs(m - 71.2) < 1e-9 and abs(sd - 2.5884) < 1e-3 and abs(hi - (71.2 + t * sd / 5 ** 0.5)) < 1e-9
    and abs(t - 2.7764) < 0.0001)
chk("1 una sola unidad: sin IC", gb.mean_ci([40])[5] is None)

# 2 fotos del sitio: carpeta con 4 fotos (dos franjas: verde y suelo, distinta proporción)
site = os.path.join(OUT, "sitio"); out = os.path.join(OUT, "res")
for d_ in (site, out):
    shutil.rmtree(d_, ignore_errors=True); os.makedirs(d_)
fr = {"F01.png": 0.25, "F02.png": 0.50, "F03.png": 0.75, "F04.png": 0.40}
for nm, f in fr.items():
    im = np.zeros((300, 400, 3), np.uint8); im[:] = SOIL = (160, 120, 90)
    im[:, :int(400 * f)] = (40, 150, 40)
    Image.fromarray(im).save(os.path.join(site, nm))
ph, w = gb.site_photos(site)
chk("2 sin formulario: todas las fotos por nombre, numeradas 1…4", [p["nombre"] for p in ph] == sorted(fr)
    and [p["numero"] for p in ph] == [1, 2, 3, 4] and all(p["parcela"] is None for p in ph))
form = os.path.join(OUT, "formulario.csv")
with open(form, "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["parcela", "punto", "id_foto", "calidad"])
    wr.writerow(["P1", "Foto 1", "F03", ""]); wr.writerow(["", "Foto 2", "F01", ""])
    wr.writerow(["P2", "Foto 1", "F02", ""]); wr.writerow(["", "Foto 2", "F04", "descartar"])
phf, wf = gb.site_photos(site, form)
chk("2 con formulario: orden del formulario, parcela heredada, la de calidad «descartar» se omite con aviso",
    [p["nombre"] for p in phf] == ["F03.png", "F01.png", "F02.png"] and [p["parcela"] for p in phf] == ["P1", "P1", "P2"]
    and any("F04" in x for x in wf), (phf, wf))
chk("2 semilla = base + número", gb.photo_seed(1000, 3) == 1003)
chk("2 estado inicial: pendiente", all(gb.photo_status(out, p["nombre"]) == "pendiente" for p in phf))

# 3 procesamiento guiado en «Cobertura del suelo» (modo cuadro: las esquinas en cada foto)
d = GroundCoverDialog(None); d.show()
d.mode_quad.setChecked(True); d.n_spin.setValue(25) if hasattr(d, "n_spin") else None
bd = GroundBatchDialog(None, ground_dialog=d)
bd.folder.setText(site); bd.form.setText(form); bd.unit.setCurrentIndex(1); bd.base_seed.setValue(500)
bd.site.setText("Finca Prueba"); bd.analyst.setText("JF")
chk("3 la carpeta de resultados toma la de fotos por omisión", bd.out_dir.text() == site)
bd.out_dir.setText(out)
idx = bd.start()
chk("3 empieza en la primera foto pendiente; semilla fija y bloqueada; barra visible",
    idx == 0 and os.path.basename(d.photo_path) == "F03.png" and d.seed_spin.value() == 501
    and not d.seed_spin.isEnabled() and d.batch_box.isVisibleTo(d))
chk("3 la barra dice foto, parcela, semilla y completas", "Foto 1 de 3" in d.batch_lbl.text()
    and "parcela P1" in d.batch_lbl.text() and "semilla 501" in d.batch_lbl.text() and "completas 0 de 3" in d.batch_lbl.text(),
    d.batch_lbl.text())
chk("3 «Nueva cuadrícula» no cambia la semilla durante el lote", d.new_grid(confirm=False) is False)

def corners_and_classify(dlg, leave=0):
    for c in ((2, 2), (397, 2), (397, 297), (2, 297)):
        dlg._on_canvas_click(*c)
    dlg.prepare_area(confirm=False)
    k = 0
    for i in range(len(dlg.labels)):
        if dlg.labels[i] is None:
            if k < leave:
                k += 1; continue
            dlg.labels[i] = "suelo" if "suelo" in [c[0] for c in dlg.classes] else dlg.classes[-1][0]
    dlg._refresh()

corners_and_classify(d)
meta = d.export_meta()
chk("3 metadatos de la foto: número, parcela y punto", meta.get("numero_foto") == 1 and meta.get("parcela") == "P1"
    and meta.get("punto"), {k: meta.get(k) for k in ("numero_foto", "parcela", "punto")})
pts1 = list(d.points)
i2 = d.batch_next()
chk("3 «Guardar y foto siguiente»: la 1 queda completa y se abre la 2 con su semilla",
    i2 == 1 and gb.photo_status(out, "F03.png") == "completa" and os.path.basename(d.photo_path) == "F01.png"
    and d.seed_spin.value() == 502)
rows = list(csv.reader(open(gb.output_prefix(out, "F03.png") + ".csv", encoding="utf-8-sig"), delimiter=","))
hdr = rows[0]
chk("3 CSV de foto: columnas numero_foto, parcela y punto tras analista", hdr[hdr.index("analista") + 1:hdr.index("analista") + 4]
    == ["numero_foto", "parcela", "punto"] and rows[1][hdr.index("parcela")] == "P1", hdr[:12])
chk("3 informe HTML de la foto guardado", os.path.isfile(gb.output_prefix(out, "F03.png") + "_informe.html"))
corners_and_classify(d, leave=2)
d.batch_save()
chk("3 foto con puntos sin clasificar: «incompleta»", gb.photo_status(out, "F01.png") == "incompleta")

# 4 continuar: nueva ventana, empieza en la primera no completa y recupera su clasificación
d.end_batch()
chk("4 «Terminar»: la semilla vuelve a estar libre y la barra se oculta", d.seed_spin.isEnabled() and not d.batch_box.isVisibleTo(d))
d2 = GroundCoverDialog(None); d2.show(); d2.mode_quad.setChecked(True)
bd2 = GroundBatchDialog(None, ground_dialog=d2)
bd2.folder.setText(site); bd2.out_dir.setText(out); bd2.form.setText(form); bd2.base_seed.setValue(500)
bd2.unit.setCurrentIndex(1); bd2.site.setText("Finca Prueba")
idx = bd2.start()
pend = sum(1 for x in d2.labels if x is None)
chk("4 continúa en la foto 2 (incompleta) con su clasificación cargada (2 puntos pendientes)",
    idx == 1 and os.path.basename(d2.photo_path) == "F01.png" and pend == 2 and len(d2.points) > 0, (idx, pend))
chk("4 la lista de la ventana del sitio muestra el estado", "completa" in bd2.lst.item(0).text()
    and "incompleta" in bd2.lst.item(1).text() and "pendiente" in bd2.lst.item(2).text())
for i in range(len(d2.labels)):
    if d2.labels[i] is None:
        d2.labels[i] = d2.classes[-1][0]
d2._refresh()
d2.batch_next()
corners_and_classify(d2)
d2.batch_save()
d2.batch_prev(); d2.batch_open(0)
chk("4 volver a la foto 1: la misma cuadrícula (misma semilla) y sus clases", len(d2.points) == len(pts1) and all(
    abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6 for a, b in zip(d2.points, pts1))
    and all(x is not None for x in d2.labels))

# 5 resumen del sitio
paths, summ = bd2.summary()
sv = {s["columna"]: s for s in summ}
recs, variables, _w = gb.site_records(phf, out)
plots = {}
for r in recs:
    plots.setdefault(r["parcela"], []).append(r["valores"]["verde_canopeo_pct"])
pm = [sum(v) / len(v) for v in plots.values()]
s = sv["verde_canopeo_pct"]
chk("5 por parcelas: n = 2 parcelas; media de las medias de parcela", s["n"] == 2 and abs(s["media"] - sum(pm) / 2) < 1e-9
    and s["unidad"] == "parcela", (s["n"], s["media"], pm))
chk("5 verde por píxeles cerca de lo dibujado (F03 75 %, F01 25 %, F02 50 %)", abs(plots["P1"][0] - 75) < 2
    and abs(plots["P1"][1] - 25) < 2 and abs(plots["P2"][0] - 50) < 2, plots)
chk("5 IC recortado a 0–100 %", all((x["ic_inf"] is None) or (0 <= x["ic_inf"] <= x["media"] <= x["ic_sup"] <= 100)
                                    for x in summ))
names = [os.path.basename(p) for p in paths]
chk("5 archivos del sitio: resumen, fotos, parcelas e informe", names == ["CobDosel_suelo_sitio_finca_prueba.csv",
    "CobDosel_suelo_sitio_finca_prueba_fotos.csv", "CobDosel_suelo_sitio_finca_prueba_parcelas.csv",
    "CobDosel_suelo_sitio_finca_prueba_informe.html"], names)
rf = list(csv.reader(open(paths[1], encoding="utf-8-sig")))
chk("5 CSV de fotos: 3 fotos completas con parcela y semilla", len(rf) == 4 and [r[2] for r in rf[1:]] == ["P1", "P1", "P2"]
    and [r[4] for r in rf[1:]] == ["501", "502", "503"], rf[1:])
ht = open(paths[3], encoding="utf-8").read()
chk("5 informe: unidad, t de Student y Canopeo", "parcela" in ht.lower() and "t de Student" in ht and "Canopeo" in ht)
bd2.unit.setCurrentIndex(0)
paths2, summ2 = bd2.summary()
chk("5 por fotos: n = 3 y sin CSV de parcelas", {x["columna"]: x for x in summ2}["verde_canopeo_pct"]["n"] == 3
    and not any(p.endswith("_parcelas.csv") for p in paths2))
bd2.form.setText(""); bd2.unit.setCurrentIndex(1)
try:
    bd2.load_photos(); err = ""
except ValueError as e:
    err = str(e)
chk("5 «Parcelas» sin formulario: error claro", "necesita el formulario" in err, err)

# 6 menú del complemento
pl = classFactory(Iface()); pl.initGui()
chk("6 menú: «Cobertura del suelo — procesamiento por sitio»", pl.ground_batch_action is not None
    and "procesamiento por sitio" in pl.ground_batch_action.text())
pl.unload()
chk("6 descarga: acción liberada", pl.ground_batch_action is None)
print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
