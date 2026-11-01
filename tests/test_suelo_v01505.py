"""CobDosel 0.15.5: la calibración con baldosas se guarda en el mismo paso: «Usar y guardar esta calibración…» pide el
nombre con uno propuesto (modelo_1x_baldosas_H<altura>), en la ventana principal y en «Cobertura del suelo»; la ventana
de baldosas indica el siguiente paso.

Uso: python3 -I test_suelo_v01505.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
import math
import cobdosel.tile_calibration_dialog as tcd
from cobdosel import tile_calibration as tc
from cobdosel.tile_calibration_dialog import TileCalibrationDialog, DISPLAY_MAX, default_name

F = 2917.2


def P(X, Y, Hc=81.5, w=4000, h=3000):
    return (F * X / Hc + w / 2.0, F * Y / Hc + h / 2.0)


corners = [P(-32, -32), P(32, -32), P(32, 32), P(-32, 32)]
exif = {"Make": "Google", "Model": "Pixel 10", "FocalLength": R(453, 100), "FocalLengthIn35mmFilm": 24}
img = Image.fromarray(np.full((3000, 4000, 3), 170, np.uint8))
ex = Image.Exif()
ex[0x010F] = "Google"; ex[0x0110] = "Pixel 10"
pth = os.path.join(OUT, "baldosas.jpg"); img.save(pth, exif=ex)

t = TileCalibrationDialog(None); t.show(); app.processEvents()
t.load_photo(0, pth)
sc = t.photos[0].scale
t.set_corners(0, [(x * sc, y * sc) for x, y in corners])
t.h_spins[0].setValue(81.5)
t._on_calc()
res = t.result
chk("1 botón «Usar y guardar esta calibración…»", t.ok_btn.text() == "Usar y guardar esta calibración…"
    and t.ok_btn.isEnabled())
name = default_name(res)
chk("1 nombre propuesto con el modelo, 1x, método y altura", name == "Pixel 10_1x_baldosas_H82", name)
chk("1 la ventana indica el siguiente paso con el nombre propuesto",
    "Siguiente paso: pulse «Usar y guardar esta calibración…»" in t.out.toPlainText() and name in t.out.toPlainText())
chk("1 f recuperada (4000×3000, H = 81.5 cm)", abs(res["focal_px"] - F) < 1.0, res["focal_px"])
chk("1 sin modelo en el EXIF: «camara_1x_baldosas_H…»",
    default_name(dict(res, camera=None)) == "camara_1x_baldosas_H82")

# ventana principal: pide el nombre en seguida, con el propuesto
asked = []
QInputDialog.getText = staticmethod(lambda *a, **k: (asked.append(a), (a[4], True))[1])
d = CobDoselDialog(Iface())
d._load_image_into_dialog(pth)
d.apply_tile_calibration(res)
chk("2 ventana principal: pide el nombre al usar la calibración, con el propuesto", asked and asked[-1][4] == name,
    asked[-1][4] if asked else None)
chk("2 calibración guardada con ese nombre y activa", d._cal_name == name and os.path.isfile(cs.calibration_path(name)))
saved = cs.load_calibration(name)
chk("2 guardada como «Rectilínea», método «baldosas»", saved["projection"] == "rectilinear"
    and saved.get("calibration_method") == "baldosas" and saved["measurement"]["mode"] == "baldosas")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
d2 = CobDoselDialog(Iface()); d2._load_image_into_dialog(pth)
d2.apply_tile_calibration(res)
logtxt = d2.log_text.toPlainText() if hasattr(d2, "log_text") else ""
chk("2 si se cancela el nombre: calibración activa sin guardar y aviso «Guardar calibración…» en el registro",
    d2.calibration is not None and d2._cal_name is None
    and "use «Guardar calibración…» para guardarla" in d2.log_text.toPlainText())
chk("2 el botón «Guardar calibración…» sigue funcionando (señal clicked con argumento)",
    d2.save_cal_btn.isEnabled())
QInputDialog.getText = staticmethod(lambda *a, **k: ("Desde boton", True))
d2.save_cal_btn.click(); app.processEvents()
chk("2 «Guardar calibración…» guarda", d2._cal_name == "Desde boton")


# cobertura del suelo: _on_tiles propone el nombre y guarda
class FakeTile:
    def __init__(self, *a, **k):
        self.result = res
    def exec(self):
        return QtWidgets.QDialog.DialogCode.Accepted
    exec_ = exec


tcd.TileCalibrationDialog = FakeTile
asked.clear()
QInputDialog.getText = staticmethod(lambda *a, **k: (asked.append(a), (a[4], True))[1])
g = GroundCoverDialog(None)
g._on_tiles()
chk("3 «Cobertura del suelo»: propone el mismo nombre, guarda y lo elige", asked and asked[-1][4] == name
    and g.cal_combo.currentText() == name, g.cal_combo.currentText())

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
