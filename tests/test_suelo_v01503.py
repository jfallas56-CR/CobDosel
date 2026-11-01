"""CobDosel 0.15.3: calibración con baldosas o un rectángulo conocido (una o dos alturas): focal, altura real del
lente e inclinación; ventana propia, botón en la ventana principal y en «Cobertura del suelo».

Uso: python3 -I test_suelo_v01503.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
GREEN, SOIL = (30, 160, 40), (150, 110, 80)
import math
from cobdosel import tile_calibration as tc
from cobdosel.tile_calibration_dialog import TileCalibrationDialog, build_calibration, DISPLAY_MAX
from cobdosel.ground_cover_dialog import RIGHT
from cobdosel.focal_check import implied_focal_px


def camera(f, Hc, tilt, w=3000, h=4000, off=(10.0, -5.0)):
    """Cámara de prueba: lente rectilínea de focal f a Hc cm del suelo, inclinada tilt° (eje x)."""
    t = math.radians(tilt)
    Rm = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
    K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1]])

    def P(X, Y):
        q = K @ (Rm @ np.array([X - off[0], Y - off[1], Hc]))
        return (q[0] / q[2], q[1] / q[2])
    return P


def block(P, a, b):
    return [P(0, 0), P(a, 0), P(a, b), P(0, b)]


F = 2868.0
P1 = camera(F, 100.0, 4.7)
m1 = dict(corners_px=block(P1, 64, 128), side1_cm=64, side2_cm=128, height_cm=100, width_px=3000, height_px=4000)
r = tc.calibrate_tiles(m1)
chk("1 una foto: f exacta con la cámara inclinada 4.7° (corrige la inclinación)", abs(r["focal_px"] - F) < 0.01,
    r["focal_px"])
chk("1 una foto: inclinación 4.7° y altura del lente 100 cm", abs(r["photos"][0]["tilt_deg"] - 4.7) < 1e-4
    and abs(r["lens_height_cm"] - 100) < 1e-4)
s_plain = tc.center_scale(tc.block_homography(m1["corners_px"], 64, 128), 3000, 4000)[2] * 100
chk("1 sin la corrección de inclinación f quedaría baja (escala·H)", s_plain < F - 5, s_plain)
# el orden de los clics no importa
m1b = dict(m1, corners_px=list(reversed(m1["corners_px"])))
chk("1 esquinas en cualquier orden", abs(tc.calibrate_tiles(m1b)["focal_px"] - F) < 0.01)

# dos alturas: alturas medidas 3 cm por debajo del lente (desde el borde del teléfono)
P2 = camera(F, 150.0, 2.0)
m1o = dict(m1, height_cm=97.0)
m2o = dict(m1, corners_px=block(P2, 64, 128), height_cm=147.0)
r2 = tc.calibrate_tiles(m1o, m2o)
chk("2 dos alturas: f exacta aunque las alturas se midieron 3 cm por debajo del lente",
    abs(r2["focal_px"] - F) < 0.01 and abs(r2["offset_cm"] - 3.0) < 1e-4, (r2["focal_px"], r2["offset_cm"]))
r1o = tc.calibrate_tiles(m1o)
chk("2 con una sola foto ese error de 3 cm da f 3 % baja", abs(r1o["focal_px"] / F - 0.97) < 1e-3, r1o["focal_px"])
chk("2 inclinación de cada foto", abs(r2["photos"][0]["tilt_deg"] - 4.7) < 1e-4
    and abs(r2["photos"][1]["tilt_deg"] - 2.0) < 1e-4)
for bad, txt in ((dict(m2o, height_cm=110.0), "al menos 20 cm"),
                 (dict(m2o, width_px=2000, height_px=1500), "mismo tamaño"),
                 (dict(m2o, height_cm=60.0, corners_px=block(P2, 64, 128)), "más grande")):
    try:
        tc.calibrate_tiles(m1o, bad); err = ""
    except ValueError as e:
        err = str(e)
    chk("2 error claro: «{}»".format(txt), txt in err, err)
lines = tc.summary_lines(r2)
chk("2 resumen: focal equivalente, altura real, distancia lente–punto y aviso de inclinación",
    "equivalente a 24.8 mm" in lines[0] and "lente a 100.0 cm" in lines[1] and "3.0 cm por encima" in lines[3]
    and any(l.startswith("Aviso: la cámara de la foto 1 estaba inclinada 4.7°") for l in lines), lines)

# círculo equivalente: con «Rectilínea» la calibración reproduce f
cal = build_calibration(dict(r2, side1_cm=64, side2_cm=128, files=["a.jpg", "b.jpg"], camera=None, lines=lines))
chk("3 calibración equivalente «Rectilínea»: misma f, método «baldosas»",
    cal["projection"] == "rectilinear" and abs(cal["focal_length_px"] - F) < 0.5
    and abs(implied_focal_px(cal) - F) < 0.5 and cal["calibration_method"] == "baldosas"
    and cal["measurement"]["mode"] == "baldosas", cal["focal_length_px"])
chk("3 registro: rectángulo, fotos, inclinación y distancia del lente",
    "rectángulo de 64 × 128 cm" in cal["measurement"]["summary"] and "lente a +3.0 cm" in cal["measurement"]["summary"])
from cobdosel.ground_cover import fixed_area_side_px
sc = scale_calibration_to_image(cal, 1500, 2000)
chk("3 escalada a 1500×2000 px: área fija de 1 m a 1 m = f/2 px", abs(fixed_area_side_px(sc["focal_length_px"], 1.0,
    1.0) - F / 2) < 0.5)

# ventana
img = np.full((4000, 3000, 3), 180, np.uint8)
p1, p2 = os.path.join(OUT, "b1.jpg"), os.path.join(OUT, "b2.jpg")
Image.fromarray(img).save(p1); Image.fromarray(img).save(p2)
t = TileCalibrationDialog(None); t.show(); app.processEvents()
t.load_photo(0, p1)
sc0 = DISPLAY_MAX / 4000.0
chk("4 foto mostrada reducida y escala registrada", abs(t.photos[0].scale - sc0) < 1e-9 and t.photos[0].native == (3000, 4000))
t.pitch.setValue(32); t.n1.setValue(2); t.n2.setValue(4); t.apply_tiles()
chk("4 «Aplicar»: lados 64 × 128 cm", t.side1.value() == 64 and t.side2.value() == 128)
for x, y in block(P1, 64, 128)[:3]:
    t._on_canvas_click(x * sc0, y * sc0)
t._on_canvas_click(1, 1, RIGHT)
chk("4 clic derecho quita la última esquina", len(t.photos[0].corners) == 2 and "2 de 4" in t.corner_lbls[0].text())
t.set_corners(0, [(x * sc0, y * sc0) for x, y in block(P1, 64, 128)])
t.h_spins[0].setValue(97.0)
t._on_calc()
chk("4 una foto con H = 97: f 3 % baja; «Usar esta calibración» activo",
    abs(t.result["focal_px"] / F - 0.97) < 1e-3 and t.ok_btn.isEnabled(), t.result["focal_px"])
t.load_photo(1, p2)
chk("4 cargar la foto 2 marca «segunda foto» y la muestra", t.two_check.isChecked() and t.active == 1
    and not t.ok_btn.isEnabled())
t.set_corners(1, [(x * sc0, y * sc0) for x, y in block(P2, 64, 128)])
t.h_spins[1].setValue(147.0)
t._on_calc()
chk("4 dos fotos: f exacta (±0.1 %) y lente 3 cm por encima", abs(t.result["focal_px"] / F - 1) < 1e-3
    and abs(t.result["offset_cm"] - 3) < 0.2, (t.result["focal_px"], t.result["offset_cm"]))
chk("4 texto del resultado en la ventana", "Focal f =" in t.out.toPlainText())
t.set_corners(1, t.photos[1].corners[:3]); t._on_calc()
chk("4 faltan esquinas: aviso y sin resultado", t.result is None and msgs and "3 de 4" in msgs[-1][1], msgs[-1:])
t.set_corners(1, [(x * sc0, y * sc0) for x, y in block(P2, 64, 128)]); t._on_calc()
res_win = t.result

# ventana principal
d = CobDoselDialog(Iface())
d._load_image_into_dialog(p1)
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))     # v0.15.5: pide el nombre; aquí se cancela
d.apply_tile_calibration(res_win)
c = d.calibration
chk("5 ventana principal: calibración «Rectilínea» con la focal de las baldosas (escalada a la foto de análisis)",
    c is not None and c["projection"] == "rectilinear" and d._current_projection_code() == "rectilinear"
    and abs(c["focal_length_px"] * 4000.0 / c["image_height_px"] - res_win["focal_px"]) < 0.5,
    (c or {}).get("focal_length_px"))
chk("5 campos D y H: lado y altura real del lente; medición «baldosas»",
    abs(d.circle_diameter.value() - 64) < 1e-9 and abs(d.camera_height.value() - 100.0) < 0.2
    and c["measurement"]["mode"] == "baldosas" and c["calibration_method"] == "baldosas")
src = open(os.path.join(sys.argv[1], "cobdosel", "canopy_dialog.py"), encoding="utf-8").read()
chk("5 botón «Calibrar con baldosas…» en la calibración (desactivado con ojo de pez)",
    d.tiles_btn.isEnabled() and "self.tiles_btn.setEnabled(not is_fisheye)" in src)

# cobertura del suelo: guarda y elige la calibración
g = GroundCoverDialog(None)
path = g.save_tile_calibration(res_win, "Pixel prueba baldosas")
chk("6 «Cobertura del suelo»: calibración guardada y elegida para el área fija",
    os.path.isfile(path) and g.cal_combo.currentText() == "Pixel prueba baldosas")
saved = cs.load_calibration("Pixel prueba baldosas")
chk("6 calibración guardada: «Rectilínea», 3000×4000, f de las baldosas",
    saved["projection"] == "rectilinear" and saved["image_width_px"] == 3000
    and abs(saved["focal_length_px"] - res_win["focal_px"]) < 0.5)
from cobdosel.help_texts import GROUND_HELP_HTML, SHORT_HELP_TOPICS, FULL_HELP_HTML
chk("7 ayuda: calibración con baldosas en la ventana principal y en «Cobertura del suelo»",
    "Calibración con baldosas o un rectángulo conocido" in SHORT_HELP_TOPICS["calibracion"] and "Calibración con baldosas o un rectángulo conocido" in FULL_HELP_HTML
    and "Calibrar con baldosas o un rectángulo conocido…" in GROUND_HELP_HTML)

print("\nTodo OK" if ok_all else "\nHAY FALLAS")
sys.exit(0 if ok_all else 1)
