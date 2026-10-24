"""CobDosel 0.14.45: informe del lote (observaciones en segunda fila, parámetros legibles) y revisión guardada visible.

Uso: python3 -I test_v01445.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.lens_calibration import calibrate_regular_lens, calibrate_from_glama_radius
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
fold = os.path.join(OUT, "fotos"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold, exist_ok=True)
rng = np.random.default_rng(5)
t0 = datetime.datetime(2026, 10, 20, 10, 0, 0)
for k in range(4):
    img = np.full((960, 1280, 3), 50, np.uint8)
    img[np.kron(rng.random((24, 32)) < 0.4, np.ones((40, 40), bool))] = 215
    im = Image.fromarray(img); ex = im.getexif()
    ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=60 * k)).strftime("%Y:%m:%d %H:%M:%S")}
    im.save(os.path.join(fold, "F%02d.jpg" % k), quality=92, exif=ex)
calg = calibrate_from_glama_radius(1618, 1280, 960)
b0 = bc.run_batch(fold, None, calg, None, photos_per_plot=2)
cut0 = b0["fotos"][0]["corte"]
bc.save_decisions(fold, {"F00.jpg": {"decision": "aceptado", "corte": cut0, "canal": "blue_red", "operador": "Ana",
                                     "nota": "", "fecha": "2026-10-24T10:41:07"},
                         "F01.jpg": {"decision": "excluido", "corte": None, "canal": "blue_red", "operador": "",
                                     "nota": "tronco", "fecha": "2026-10-24T10:52:30"}}, "t")
b = bc.run_batch(fold, None, calg, None, decisions=bc.load_decisions(fold), photos_per_plot=2)
f0, f1 = b["fotos"][0], b["fotos"][1]
chk("1 foto con decisión guardada: dice cuándo y quién, no «revisada por el operador»",
    "decisión guardada (2026-10-24 10:41, Ana)" in f0["motivo"] and "revisada por el operador" not in f0["motivo"]
    and f0["metodo_corte"] == "revisado (decisión guardada)", f0["motivo"][:80])
chk("1 exclusión guardada: fecha y «operador sin nombre»", "2026-10-24 10:52, operador sin nombre" in f1["motivo"], f1["motivo"])
chk("1 resumen de decisiones", bc.decisions_summary(bc.load_decisions(fold)) ==
    "2 decisión(es) guardada(s) (2026-10-24 10:41 a 10:52; operador: Ana)", bc.decisions_summary(bc.load_decisions(fold)))
chk("2 parámetros con nombres legibles (canal y regla del corte)",
    b["parametros"]["canal"].startswith("Azul + Rojo") and b["parametros"]["regla_corte"].startswith("recomendado (log-normal)"),
    (b["parametros"]["canal"], b["parametros"]["regla_corte"]))
b["parametros"]["operador"] = "Jorge Fallas"
hp = os.path.join(OUT, "lote.html"); bc.write_html(b, hp, "0.14.45", "Prueba")
html = open(hp, encoding="utf-8").read()
chk("3 informe: sin «Basado en Tichý» en el encabezado; operador en el encabezado",
    "Basado en Tichý" not in html and "Operador: Jorge Fallas" in html)
chk("3 informe: observaciones en una segunda fila por foto (lista)", html.count("<tr class='obs") == sum(1 for r in b["fotos"] if r.get("motivo"))
    and "<th>Observaciones</th>" not in html and "<li>decisión guardada (2026-10-24 10:41, Ana)" in html)
from cobdosel.canopy_analysis import sky_uniformity_warning
b["fotos"][2]["motivo"] = "revisar el corte: x; " + sky_uniformity_warning(80)
bc.write_html(b, hp, "0.14.45", "Prueba"); html = open(hp, encoding="utf-8").read()
chk("3 informe: el aviso de cielo es un solo punto de la lista", "<li>repita la foto" not in html
    and "<li>cielo no uniforme (rango de brillo del cielo 80" in html)
chk("3 informe: sin el código «glama» en parámetros", ">glama<" not in html and ">blue_red<" not in html)
paths = bc.write_csvs(b, os.path.join(OUT, "lote"), "0.14.45")
site = open(paths[2], encoding="utf-8-sig").read()
chk("3 CSV del sitio: regla del corte legible", "recomendado (log-normal)" in site and ",glama," not in site)
# ---- ventana: aviso y botón
cs.save_calibration("Prueba_GLAMA", calg)
bd = CobDoselBatchDialog(None); bd.show(); app.processEvents()
bd._refresh_calibrations(); bd.cal_combo.setCurrentIndex(max(0, bd.cal_combo.findData("Prueba_GLAMA")))
bd.site_edit.setText("S"); bd.folder_edit.setText(fold); bd.per_plot_spin.setValue(2)
bd._on_run(); app.processEvents()
txt = bd.out.toPlainText()
chk("4 el registro dice que se aplicó una revisión anterior y cómo quitarla",
    "de una revisión anterior" in txt and "Borrar revisión guardada" in txt and
    any("revisión anterior" in w for w in bd.batch["avisos"]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
bd._on_clear_review(); app.processEvents()
baks = [f for f in os.listdir(fold) if f.startswith("CobDosel_revision_cortes_") and f.endswith(".bak.json")]
chk("4 «Borrar revisión guardada…»: el archivo se guarda como copia y el sitio se recalcula sin decisiones",
    not os.path.exists(os.path.join(fold, bc.DECISIONS_FILE)) and len(baks) == 1
    and all(not r.get("decision") or r["decision"] in ("automático", "pendiente de revisión") for r in bd.batch["fotos"]),
    [r.get("decision") for r in bd.batch["fotos"]])
print("TODO OK" if ok_all else "HAY FALLAS")
