"""CobDosel 0.15.9: área fija: qué cuadrado cabe (ground_cover.fixed_area_fit y fit_table); la ventana lo indica al
escribir la altura y el lado; tablas en la ayuda.

Uso: python3 -I test_suelo_v01509.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
from cobdosel.lens_calibration import calibrate_regular_lens
from cobdosel.help_texts import GROUND_HELP_HTML
F = 2917.2
r = gc.fixed_area_fit(F, 3000, 1.0, 1.0)
chk("1 Pixel 10 a 1 m: lado máximo 1.03 m (0.98 con margen); 1 m cabe sin margen",
    abs(r["max_side_m"] - 3000 / F) < 1e-12 and round(r["max_side_margin_m"], 2) == 0.98 and r["fits"]
    and not r["fits_margin"], r)
chk("1 altura mínima para 1 m: 0.97 m (1.02 con margen)", round(r["min_height_m"], 2) == 0.97
    and round(r["min_height_margin_m"], 2) == 1.02)
chk("1 coherente con crop_fixed_area: el lado máximo exacto ocupa el lado corto",
    abs(gc.fixed_area_side_px(F, 1.0, r["max_side_m"]) - 3000) < 1e-6)
chk("1 independiente de la resolución (foto reducida a la mitad)",
    abs(gc.fixed_area_fit(F / 2, 1500, 1.0, 1.0)["max_side_m"] - r["max_side_m"]) < 1e-12)
a, b = gc.fit_table(F, 3000)
fmt = lambda v: "{:.2f}".format(v).replace(".", ",")
ok_t = all("<td>{} m</td><td>{} m</td></tr>".format(fmt(m), fmt(mm)) in GROUND_HELP_HTML for _h, m, mm in a)
chk("2 tabla de la ayuda (altura → cuadrado máximo) = fit_table", ok_t)
ok_f = all(fmt(h * 4000 / F) + " × " + fmt(h * 3000 / F) + " m" in GROUND_HELP_HTML for h, _m, _mm in a)
chk("2 tabla de la ayuda: suelo que cubre la foto", ok_f)
for Fe, q1, q2 in ((23, "1,07", "0,93"), (24, "1,03", "0,97"), (26, "0,95", "1,05"), (28, "0,88", "1,14")):
    fpx = Fe * 5 / (43.27 * 3) * 3000
    t = gc.fit_table(fpx, 3000, heights=(1.0,), sides=(1.0,))
    chk("2 tabla de focales equivalentes, {} mm".format(Fe), fmt(t[0][0][2]) == q1 and fmt(t[1][0][2]) == q2
        and "<td>{} mm</td><td>{}</td><td>{}</td>".format(Fe, q1, q2) in GROUND_HELP_HTML)
for bad in ((0, 3000, 1, 1), (F, 3000, 0, 1)):
    try:
        gc.fixed_area_fit(*bad); err = ""
    except ValueError as e:
        err = str(e)
    chk("3 error claro con valores no positivos {}".format(bad[:3]), "positivos" in err)

# ventana
tmpd2 = os.path.join(OUT, "cal"); os.makedirs(tmpd2, exist_ok=True); cs.DEFAULT_DIR = tmpd2
cal = calibrate_regular_lens(64.0, 81.5, F * 64.0 / 81.5, 4000, 3000, projection="rectilinear")
cs.save_calibration("Pixel10_baldosas", cal)
cal_l = calibrate_regular_lens(33.0, 40.0, 2000.0, 4000, 3000, projection="angular")
cs.save_calibration("Lineal_vieja", cal_l)
d = GroundCoverDialog(None); d.show(); app.processEvents()
d.mode_fixed.setChecked(True)
d.cal_combo.setCurrentIndex(d.cal_combo.findData("Pixel10_baldosas"))
d.height_spin.setValue(1.3); d.side_spin.setValue(1.0); app.processEvents()
t = d.fit_lbl.text()
chk("4 ventana sin foto (usa el tamaño de la calibración): a 1.30 m cabe hasta 1.34 m (1.27 con margen)",
    "A 1.30 m de altura cabe un cuadrado de hasta 1.34 m (1.27 m con 5 % de margen)" in t
    and "altura mínima 0.97 m (1.02 m con margen)" in t and "No cabe" not in t, t)
d.height_spin.setValue(1.0); app.processEvents()
chk("4 a 1.00 m y lado 1 m: «Cabe sin margen»", "Cabe sin margen" in d.fit_lbl.text(), d.fit_lbl.text())
d.height_spin.setValue(0.9); app.processEvents()
chk("4 a 0.90 m: «No cabe»", d.fit_lbl.text().startswith("<b>No cabe.</b>"), d.fit_lbl.text())
png = os.path.join(OUT, "f169.png"); Image.fromarray(np.full((2250, 4000, 3), 90, np.uint8)).save(png)
d.load_photo(png); d.height_spin.setValue(1.3); app.processEvents()
chk("4 foto 16:9 con calibración 4:3: «No se puede usar» (antes se reescalaba por el lado corto, focal 25 % baja)",
    d.fit_lbl.text().startswith("<b>No se puede usar:</b>") and "distinta proporción" in d.fit_lbl.text(),
    d.fit_lbl.text())
try:
    d.prepare_area(confirm=False); err = ""
except ValueError as e:
    err = str(e)
chk("4 «Preparar área» con foto 16:9 y calibración 4:3: error claro", "distinta proporción" in err, err)
png43 = os.path.join(OUT, "f43.png"); Image.fromarray(np.full((1500, 2000, 3), 90, np.uint8)).save(png43)
d.load_photo(png43); app.processEvents()
chk("4 foto 4:3 reducida (2000×1500): usa su lado corto, mismo resultado", "A 1.30 m de altura cabe un cuadrado de "
    "hasta 1.34 m" in d.fit_lbl.text(), d.fit_lbl.text())
d.cal_combo.setCurrentIndex(d.cal_combo.findData("Lineal_vieja")); app.processEvents()
chk("4 calibración no rectilínea: lo dice", "no es «Rectilínea»" in d.fit_lbl.text(), d.fit_lbl.text())
d.mode_quad.setChecked(True); app.processEvents()
chk("4 modo cuadro: sin texto", d.fit_lbl.text() == "")
chk("5 ayuda: fórmulas, margen y regla práctica", "lado máximo = <i>H</i> × lado corto (px) / f" in GROUND_HELP_HTML
    and "5 % de margen" in GROUND_HELP_HTML and "≥ 1,05 × lado del cuadrado" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
