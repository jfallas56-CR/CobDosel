"""CobDosel 0.14.49: «Recomendado (log-normal)» en la vista previa del nivel de corte (a resolución completa,
igual que el botón principal) y CaCo descrito como estimación de la proyección vertical.

Uso: python3 -I test_v01449.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos_cielo]
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


import glob
from cobdosel.canopy_analysis import compute_auto_threshold, compute_recommended_threshold, extract_channel
import cobdosel.threshold_dialog as tdm
from cobdosel.html_report import generate_html_report
fotos = sorted(glob.glob(os.path.join(sys.argv[4], "*.jpg"))) if len(sys.argv) > 4 else []
if fotos:
    photos = fotos[:3]
else:                                       # foto sintética de dos modos
    H0, W0 = 1500, 2000
    r0 = np.random.default_rng(3)
    im = np.full((H0, W0, 3), 50, np.uint8)
    g0 = np.kron(r0.random((H0 // 25, W0 // 25)) < 0.4, np.ones((25, 25), bool))
    im[g0] = 220
    im = np.clip(im.astype(int) + r0.normal(0, 8, im.shape), 0, 255).astype(np.uint8)
    photos = [os.path.join(OUT, "sint.jpg")]; Image.fromarray(im).save(photos[0], quality=92)
print("  fotos:", len(photos), "reales" if fotos else "sintética")

d = CobDoselDialog(Iface()); d.show(); app.processEvents()
main_codes = [d.auto_method_combo.itemData(i) for i in range(d.auto_method_combo.count())]
chk("1 ventana principal: el combo no repite «Recomendado» (tiene su botón)", main_codes == ["otsu", "minimum"]
    and d.glama_cut_btn.text() == "Recomendado (log-normal)", main_codes)
cal = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
seen = {}
def _td_exec(self):
    codes = [self.auto_method_combo.itemData(i) for i in range(self.auto_method_combo.count())]
    seen["codes"] = codes; seen["default"] = self.auto_method_combo.currentData()
    self.auto_method_combo.setCurrentIndex(codes.index("recommended")); self._on_otsu()
    seen["t"] = self.threshold_slider.value(); seen["last"] = self.last_auto
    seen["preview_shape"] = self.canvas.gray_array.shape
    return QtWidgets.QDialog.DialogCode.Accepted
tdm.ThresholdDialog.exec = _td_exec; tdm.ThresholdDialog.exec_ = _td_exec
import cobdosel.canopy_dialog as cdm
cdm.ThresholdDialog.exec = _td_exec; cdm.ThresholdDialog.exec_ = _td_exec
same = []
for ph in photos:
    d._load_image_into_dialog(ph)
    H, W = d.image_array.shape[:2]
    d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
    d.zenith_max.setValue(27.0)
    d._on_glama_cut(); app.processEvents(); t_main = d.threshold_spin.value(); m_main = d.cut_method
    d.threshold_spin.setValue(128); d._cut_check = None     # lo que quede debe venir de la vista previa
    d._on_adjust_threshold(); app.processEvents()
    same.append((os.path.basename(ph), t_main, seen["t"], m_main, d.cut_method))
print("  (foto, botón principal, vista previa, método principal, método tras la vista previa):")
for x in same: print("   ", x)
chk("2 vista previa: «Recomendado (log-normal)» primero y elegido por defecto",
    seen["codes"] == ["recommended", "otsu", "minimum"] and seen["default"] == "recommended", seen["codes"])
chk("2 mismo corte que el botón «Recomendado (log-normal)» de la ventana principal (± 1)",
    all(abs(a - b) <= 1 for _, a, b, _m, _n in same), same)
chk("2 al aceptar, el método queda «recomendado (log-normal)…» igual que con el botón",
    all(n.split(",")[0] == "recomendado (log-normal)" and n == m for _, _a, _b, m, n in same), same)
chk("2 la vista previa está reducida (≤ 1400 px) pero el corte se calcula a resolución completa",
    max(seen["preview_shape"]) <= 1400 and max(d.image_array.shape[:2]) > 1400, seen["preview_shape"])
# motivos de la comprobación → informe
d._on_run(); app.processEvents()
out = generate_html_report(d.last_results, os.path.join(OUT, "foto.html"), include_images=False)
ht = open(out, encoding="utf-8").read()
cc = getattr(d, "_cut_check", None)
chk("2 la comprobación del corte de la vista previa queda para el informe",
    cc is not None and cc[1] == d.threshold_spin.value() and (("no comprobado" in d.cut_method) == bool(cc[2])), cc)
# método sobre un histograma sin dos modos → Otsu con nota
flat = np.full((200, 200), 120, np.uint8)
t, used, note = compute_auto_threshold(flat, None, "recommended")
chk("3 sin recomendación (un solo modo): usa Otsu y lo dice", used == "otsu" and "se usó Otsu" in note, (t, used))
g = extract_channel(np.array(Image.open(photos[0]).convert("RGB")), "blue_red")
diag = compute_recommended_threshold(g, None)
t2, used2, note2 = compute_auto_threshold(g, None, "recommended")
chk("3 compute_auto_threshold «recommended» = glama_cut_diagnosis del histograma completo",
    used2 == "recommended" and t2 == diag["cut"] and (note2 == "") == bool(diag["ok"]), (t2, diag["cut"], diag["ok"]))
# texto del CaCo
note_box = ht.split('class="caco-note">')[1].split("</div>")[0]
chk("4 informe: el CaCo es una estimación de la proyección vertical, no una medición directa",
    "Estimación de la cobertura del dosel (proyección vertical de las copas)" in note_box
    and "densiómetro vertical" in note_box and not note_box.strip().startswith("Proyección vertical"))
print("TODO OK" if ok_all else "HAY FALLAS")
