"""CobDosel 0.14.60: aviso de cielo no uniforme que dice si los cortes ya se verificaron; plantilla del formulario con
instrucciones actuales (máscara 63°, sin altura del dosel, puntos según el protocolo).

Uso: python3 -I test_v01460.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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





import openpyxl
from cobdosel import batch_core as bc
def rec(i, rango, decision="", analista=""):
    return {"parcela": str(i), "archivo": "F%d.jpg" % i, "valida": True, "cielo_rango": rango, "decision": decision, "analista": analista,
            "motivo": "", "motivo_revision": ""}
# v0.14.63: el cielo no uniforme ya no va en los avisos; sky_review_line (junto al resultado) dice lo mismo
allv = [rec(1, 67, "aceptado", "JF"), rec(2, 10, "automático")]
chk("1 sin aviso de cielo en los avisos (lo dice la línea junto al resultado)",
    not [x for x in bc.summarize_common_warnings(allv) if "cielo no uniforme" in x])
w = bc.sky_review_line(allv, "JF")
chk("1 cortes del cielo no uniforme ya verificados: la línea lo dice y no pide verificar",
    w.endswith("Verificadas por JF.") and "revise" not in w, w)
part = [rec(1, 67, "aceptado", "JF"), rec(2, 80, "pendiente de revisión"), rec(3, 10)]
w = bc.sky_review_line(part, "JF")
chk("1 verificados a medias: cuántos y que verifique los demás", "Verificadas por JF: 1; sin verificar: 1" in w, w)
none = [rec(1, 67, "pendiente de revisión"), rec(2, 10)]
w = bc.sky_review_line(none, "JF")
chk("1 sin verificar: pide verificar en «Revisar cortes…»", "Sin verificar: revise sus cortes" in w, w)
tpl = os.path.join(sys.argv[1], "cobdosel", "plantillas", "Formulario_fotos_CobDosel.xlsx")
wb = openpyxl.load_workbook(tpl)
ins = " ".join(str(c.value) for c in wb["Instrucciones"]["A"] if c.value)
chk("2 instrucciones sin máscara de 60° ni grupo de dosel; con 63°", "60°" not in ins and "grupo de dosel" not in ins
    and "63°" in ins, ins[:200])
chk("2 instrucciones: punto según el protocolo, no una lista fija", "según el protocolo del estudio" in ins
    and "punto: Centro, N-O (315°)" not in ins)
ws = wb.worksheets[0]
chk("2 una sola fila de ejemplo, con punto «Foto 1» y sin distancia fija", ws["C3"].value == "Foto 1" and ws["D3"].value is None
    and ws["C4"].value is None and ws["D4"].value is None)
FOT = os.path.join(OUT, "fotos"); shutil.rmtree(FOT, ignore_errors=True); os.makedirs(FOT)
Image.fromarray(np.full((300, 400, 3), 90, np.uint8)).save(os.path.join(FOT, "A.jpg"))
p, n, _w = bc.draft_form_from_photos(FOT, os.path.join(OUT, "borr.xlsx"), 2)
ins2 = " ".join(str(c.value) for c in openpyxl.load_workbook(p)["Instrucciones"]["A"] if c.value)
chk("3 el formulario creado desde las fotos lleva las instrucciones nuevas", ins2 == ins)
csvt = open(os.path.join(sys.argv[1], "cobdosel", "plantillas", "Formulario_fotos_CobDosel.csv"), encoding="utf-8-sig").read()
chk("3 plantilla CSV sin «Centro»/«8.9»", "Centro" not in csvt and "8.9" not in csvt)
print("TODO OK" if ok_all else "HAY FALLAS")
