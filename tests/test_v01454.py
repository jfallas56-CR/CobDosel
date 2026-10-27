"""CobDosel 0.14.54: «Comparar con GLAMA (tabla)»: filas sin corte de GLAMA se omiten con aviso (antes detenían todo
con una traza), mensaje claro si la tabla no tiene ningún corte, plantilla con «;» donde la coma es decimal.

Uso: python3 -I test_v01454.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.html_report import generate_html_report
from cobdosel.lens_calibration import scale_calibration_to_image



from cobdosel import glama_compare as gc
import cobdosel.glama_compare_dialog as gcd
H, W = 1500, 2000
FOT = os.path.join(OUT, "fotos"); shutil.rmtree(FOT, ignore_errors=True); os.makedirs(FOT)
r = np.random.default_rng(2)
for k in range(3):
    im = np.full((H, W, 3), 50, np.uint8)
    im[np.kron(r.random((H // 25, W // 25)) < 0.4, np.ones((25, 25), bool))] = 220
    Image.fromarray(im).save(os.path.join(FOT, "F%d.jpg" % k), quality=92)
calg = calibrate_from_glama_radius(1618, W, H)
tp = os.path.join(OUT, "plantilla.csv")
n = gc.write_template(FOT, tp)
try:
    gc.read_comparison_table(tp); err = ""
except ValueError as e:
    err = str(e)
chk("1 plantilla sin llenar: mensaje claro (no «Fila 2: sin corte»)", "no tiene ningún corte de GLAMA (3 fotos sin corte)" in err
    and "Fila 2" not in err, err)
rows = list(csv.reader(open(tp, encoding="utf-8-sig")))
rows[1][1] = "150"; rows[1][2] = "45,5"; rows[3][1] = "abc"
with open(tp, "w", newline="", encoding="utf-8-sig") as f:
    csv.writer(f).writerows(rows)
got, skipped = gc.read_comparison_table_ex(tp)
chk("2 tabla a medias: se usa la fila llena y se omiten las demás con su motivo",
    [g["archivo"] for g in got] == ["F0.jpg"] and [s[1] for s in skipped] == ["F1.jpg", "F2.jpg"]
    and skipped[0][2] == "sin corte de GLAMA" and "no numérico" in skipped[1][2], skipped)
chk("2 read_comparison_table (compatibilidad) devuelve solo las filas", len(gc.read_comparison_table(tp)) == 1)
logs = []
res, summ, paths = gc.run_comparison(tp, FOT, calg, os.path.join(OUT, "cmp.csv"), glama_radius_px=1618, glama_mask_deg=60.0,
                                     log=lambda m, l="INFO": logs.append((l, m)))
chk("2 la comparación corre con la fila llena y avisa de las omitidas", len(res) == 1 and not res[0].get("error")
    and any(l == "WARN" and "2 foto(s) de la tabla sin corte de GLAMA" in m for l, m in logs), (res, logs))
tp2 = os.path.join(OUT, "plantilla_pc.csv")
gc.write_template(FOT, tp2, delimiter=";")
first = open(tp2, encoding="utf-8-sig").readline()
chk("3 plantilla con «;» (coma decimal)", first.startswith("archivo;corte_glama;"), first)
txt = open(tp2, encoding="utf-8-sig").read().replace("F0.jpg;;;", "F0.jpg;150;45,5;", 1)
open(tp2, "w", encoding="utf-8-sig").write(txt)
g2, _s = gc.read_comparison_table_ex(tp2)
chk("3 la tabla con «;» y coma decimal se lee igual", len(g2) == 1 and g2[0]["corte_glama"] == 150
    and abs(g2[0]["caco_glama"] - 45.5) < 1e-9)
# ventana: tabla sin llenar → aviso, sin traza
msgs.clear()
dl = gcd.GlamaCompareDialog(calg, None) if True else None
dl.show(); app.processEvents()
gc.write_template(FOT, tp)
dl.table_edit.setText(tp); dl.folder_edit.setText(FOT); dl.out_edit.setText(os.path.join(OUT, "cmp_dlg.csv"))
dl.run(); app.processEvents()
log = dl.log_edit.toPlainText()
chk("4 ventana: tabla sin llenar → aviso claro, sin traza de Python", any(k == "warning" for k, _ in msgs)
    and "Traceback" not in log and "no tiene ningún corte de GLAMA" in log, (msgs, log[-200:]))
print("TODO OK" if ok_all else "HAY FALLAS")
