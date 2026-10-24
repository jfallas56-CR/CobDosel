"""CobDosel 0.14.42: uniformidad del cielo, motivo del corte, formulario y parcelas opcionales, ventana de revisión.

Uso: python3 -I test_v01442.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos_v01442]
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

# ---------------------------------------------------------------- 1) uniformidad del cielo (sintético)
H, W = 1500, 2000
yy, xx = np.mgrid[0:H, 0:W]
area = np.ones((H, W), bool)
leaves = (np.sin(xx / 7.0) * np.cos(yy / 9.0) > 0.6)            # hojas finas: muchos bordes
g_uni = np.where(leaves, 40, 200).astype(np.uint8)
edge = np.zeros_like(leaves)
edge[1:-1, 1:-1] = leaves[1:-1, 1:-1] != leaves[:-2, 1:-1]
g_uni[edge] = 120                                                  # píxeles mixtos en los bordes
v_uni = sky_uniformity_range(g_uni, g_uni >= 100, area)
chk("1 cielo uniforme con bordes mixtos: rango pequeño (los bordes se descartan)", v_uni is not None and v_uni <= 10, v_uni)
g_two = g_uni.copy(); g_two[(~leaves) & (xx < W // 2)] = 140      # dos brillos de cielo
v_two = sky_uniformity_range(g_two, g_two >= 100, area)
chk("1 cielo con dos brillos: rango > límite", v_two is not None and v_two > SKY_UNIFORMITY_LIMIT, v_two)
g_closed = np.full((H, W), 40, np.uint8); g_closed[::50, ::50] = 220
chk("1 dosel cerrado sin núcleo de cielo: no se calcula", sky_uniformity_range(g_closed, g_closed >= 100, area) is None)
chk("1 aviso solo por encima del límite", sky_uniformity_warning(SKY_UNIFORMITY_LIMIT) == "" and
    "cielo no uniforme" in sky_uniformity_warning(SKY_UNIFORMITY_LIMIT + 1) and sky_uniformity_warning(None) == "")

# ---------------------------------------------------------------- 2) motivo específico de la comprobación
xg = np.arange(256)
gau = lambda m, s_, a: a * np.exp(-0.5 * ((xg - m) / s_) ** 2)
d = glama_cut_diagnosis(gau(40, 10, 1500) + gau(165, 8, 6000) + gau(240, 6, 5000) + 5)   # dosel, nube gris, nube blanca
txt = "; ".join(d["reasons"])
chk("2 otro corte dentro del cielo: sigue «a revisar» y lo dice", not d["ok"] and "separa dos brillos del cielo" in txt, txt)
d = glama_cut_diagnosis(gau(60, 10, 5000) + gau(110, 6, 3000) + gau(230, 6, 5000) + 5)   # otro corte por debajo
txt = "; ".join(d["reasons"])
chk("2 otro corte por debajo del corte: mensaje general (posible corte alto)", not d["ok"]
    and "otro punto de partida da otro corte (96→91)" in txt and "separa dos brillos" not in txt, txt)

# ---------------------------------------------------------------- 3) lote sin formulario y sin número de parcelas
fold = os.path.join(OUT, "fotos_lote"); os.makedirs(fold, exist_ok=True)
rng = np.random.default_rng(1)
t0 = datetime.datetime(2026, 10, 20, 10, 0, 0)
for k in range(7):
    img = np.full((1920, 2560, 3), 50, np.uint8)
    gaps = np.kron(rng.random((48, 64)) < 0.4, np.ones((40, 40), bool))
    img[gaps] = 215
    im = Image.fromarray(img); ex = im.getexif(); ex[0x8769] = {0x9003: (t0 + datetime.timedelta(seconds=60 * k)).strftime("%Y:%m:%d %H:%M:%S")}
    im.save(os.path.join(fold, "F%02d.jpg" % k), quality=92, exif=ex)
calg = calibrate_from_glama_radius(1618, 2560, 1920)
b = bc.run_batch(fold, None, calg, None, photos_per_plot=5)
chk("3 sin formulario: 7 fotos → parcelas 1 (5 fotos) y 2 (2 fotos)",
    [p["fotos"] for p in b["parcelas"]] == [5, 2], [p["fotos"] for p in b["parcelas"]])
chk("3 aviso de asignación por orden de hora", any(w.startswith("Sin formulario de fotos") for w in b["avisos"]))
chk("3 sin número de parcelas: sin aviso «de N» y sitio sin total", b["sitio"]["parcelas_planificadas"] is None
    and not any("Parcelas con resultado" in w for w in b["avisos"]))
chk("3 parámetro «formulario» registra la asignación automática", "orden de hora" in b["parametros"]["formulario"])
pre, _p = os.path.join(OUT, "lote"), None
paths = bc.write_csvs(b, pre, "0.14.42")
with open(paths[0], encoding="utf-8-sig") as f:
    hdr = next(csv.reader(f))
chk("3 CSV de fotos con la columna cielo_rango", "cielo_rango" in hdr)
html_p = os.path.join(OUT, "lote.html"); bc.write_html(b, html_p, "0.14.42", "Prueba")
chk("3 informe sin «de None»", "de None" not in open(html_p, encoding="utf-8").read())

# ---------------------------------------------------------------- 4) fotos reales (opcional)
calr = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
if len(sys.argv) > 4 and os.path.isdir(sys.argv[4]):
    U = sys.argv[4]
    bad = ["10e2cd5d", "f560d4dd", "c26ec4a3", "a7f9f55b", "b4d6ec31", "2317a732", "5ccea996"]
    good = ["35dec954", "1a810e38", "0e902c8a", "b665cf25", "2b52da53", "c2de8bbf", "58dcb9f1"]
    vals = {}
    for k in bad + good:
        p = os.path.join(U, k + "-image.jpg")
        if os.path.isfile(p):
            r = bc.analyze_photo(p, calr, 27.0)
            vals[k] = (r["cielo_rango"], any("cielo no uniforme" in a for a in r["avisos"]), r)
    if len(vals) == 14:
        chk("4 las 7 fotos fuera del protocolo: cielo no uniforme",
            all(vals[k][1] for k in bad), {k: vals[k][0] for k in bad})
        chk("4 las 7 fotos aceptables: sin aviso de cielo", not any(vals[k][1] for k in good),
            {k: vals[k][0] for k in good})
        flagged = [k for k in bad if vals[k][2]["revisar"]]
        chk("4 las fotos «a revisar» por el corte dicen que el otro corte separa brillos del cielo",
            flagged and all("separa dos brillos del cielo" in vals[k][2]["motivo_revision"] for k in flagged),
            len(flagged))
        # revisión: motivo original conservado
        fl = os.path.join(OUT, "fotos_reales"); os.makedirs(fl, exist_ok=True)
        k0 = flagged[0]
        shutil.copy(os.path.join(U, k0 + "-image.jpg"), os.path.join(fl, "A.jpg"))
        bc.save_decisions(fl, {"A.jpg": {"decision": "aceptado", "corte": vals[k0][2]["corte"],
                                         "canal": "blue_red", "operador": "x", "nota": ""}}, "t")
        bb = bc.run_batch(fl, None, calr, None, decisions=bc.load_decisions(fl), photos_per_plot=1)
        chk("4 tras la revisión se conserva el motivo original en «Observaciones»",
            "motivo original" in bb["fotos"][0]["motivo"], bb["fotos"][0]["motivo"][:90])
    else:
        print("  (fotos reales incompletas: %d de 14)" % len(vals))

# ---------------------------------------------------------------- 5) ventana del lote
bd = CobDoselBatchDialog(None); bd.show(); app.processEvents()
QLabel = QtWidgets.QLabel
labels = [w.text() for w in bd.findChildren(QLabel)]
chk("5 «Nombre del sitio», «Número de parcelas», «Formulario de fotos (opcional)»",
    "Nombre del sitio:" in labels and "Número de parcelas:" in labels and "Formulario de fotos (opcional):" in labels, labels[:6])
chk("5 «(opcional)» en número de parcelas; sin «planificadas»", bd.planned_spin.specialValueText() == "(opcional)"
    and not any("planificadas" in t for t in labels))
chk("5 se conservan los botones del formulario", any(b_.text() == "Crear formulario desde las fotos…"
                                                    for b_ in bd.findChildren(QtWidgets.QPushButton)))
bd.resize(500, 380); app.processEvents()
chk("5 la ventana se achica en ambos sentidos (área desplazable y divisor)",
    bd.width() <= 520 and bd.height() <= 400 and bd.findChildren(QtWidgets.QScrollArea) and bd.splitter.count() == 2,
    (bd.width(), bd.height()))
bd.folder_edit.setText(fold); bd.form_edit.setText(""); bd.planned_spin.setValue(0)
cs.save_calibration("Prueba_GLAMA", calg) if hasattr(cs, "save_calibration") else None
bd._refresh_calibrations(); bd.cal_combo.setCurrentIndex(max(0, bd.cal_combo.findData("Prueba_GLAMA")))
bd._on_run(); app.processEvents()
chk("5 procesa sin formulario ni número de parcelas", bd.batch is not None and len(bd.batch["fotos"]) == 7,
    [m for m in msgs[-2:]])

# ---------------------------------------------------------------- 6) ventana de revisión
items = []
for k in range(3):
    r = bc.analyze_photo(os.path.join(fold, "F%02d.jpg" % k), calg, 30.0)
    it = dict(r); it.update(corte_auto=r["corte"], archivo="F%02d.jpg" % k, parcela="1", punto="C", cenit_max=30.0,
                            revisar=True, motivo_revision="prueba")
    items.append(it)
dec_file = os.path.join(fold, bc.DECISIONS_FILE)
if os.path.exists(dec_file):
    os.remove(dec_file)
dlg = CutReviewDialog(items, fold, calg, "blue_red"); dlg.show(); app.processEvents()
answers = []
QMessageBox.question = staticmethod(lambda *a, **k: answers.pop(0) if answers else QMessageBox.StandardButton.No)
i0 = dlg.idx
dlg.spin.setValue(dlg.spin.value() - 20); app.processEvents()
answers.append(QMessageBox.StandardButton.Cancel); dlg._move(1)
chk("6 corte cambiado sin aceptar + «Siguiente» → pregunta; «Cancelar» se queda en la foto",
    dlg.idx == i0 and dlg._has_unaccepted())
answers.append(QMessageBox.StandardButton.Discard); dlg._move(1)
chk("6 «Descartar» pasa a la siguiente sin registrar", dlg.idx != i0 and items[i0]["archivo"] not in dlg.decisions)
dlg._load(i0); cut_new = dlg.spin.value() - 15; dlg.spin.setValue(cut_new)
answers.append(QMessageBox.StandardButton.Save); dlg._move(1)
dsav = json.load(open(dec_file, encoding="utf-8")) if os.path.exists(dec_file) else {}
saved = dsav.get("fotos", {}).get(items[i0]["archivo"], {})
chk("6 «Guardar» acepta el corte y lo escribe en el archivo al momento",
    dlg.decisions.get(items[i0]["archivo"], {}).get("corte") == cut_new and saved.get("corte") == cut_new,
    (dlg.decisions.get(items[i0]["archivo"]), list(dsav)[:3] if isinstance(dsav, dict) else dsav))
dlg._load(1); dlg._on_accept()
chk("6 «Aceptar corte» guarda al momento", items[1]["archivo"] in bc.load_decisions(fold) and dlg.changed)
k0 = dlg.view._item.pixmap().cacheKey()
dlg.opacity_spin.setValue(100); app.processEvents(); import time; time.sleep(0.25); app.processEvents()
chk("6 opacidad: cambia la vista", dlg.view._item.pixmap().cacheKey() != k0)
dlg._load(2); dlg.spin.setValue(dlg.spin.value() + 7)
answers.append(QMessageBox.StandardButton.Cancel); dlg.reject(); app.processEvents()
chk("6 cerrar con un corte sin aceptar → pregunta; «Cancelar» no cierra", dlg.isVisible())
answers.append(QMessageBox.StandardButton.Discard); dlg.reject(); app.processEvents()
chk("6 «Descartar» cierra; las decisiones aceptadas siguen en el archivo",
    not dlg.isVisible() and len(bc.load_decisions(fold)) == 2)
chk("6 ventana redimensionable (mínimo ≤ 560 × 480)", dlg.minimumWidth() <= 560 and dlg.minimumHeight() <= 480)

print("TODO OK" if ok_all else "HAY FALLAS")
