"""Smoke test headless de CobDosel 0.11.0: diálogo real + stubs de qgis.core.

Uso: python3 -I smoke_dialog_v011.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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




import tempfile, math
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
import cobdosel.canopy_dialog as cdm
cdm.list_calibrations = cs.list_calibrations; cdm.load_calibration = cs.load_calibration
from cobdosel import focal_check as fc
from cobdosel.lens_calibration import calibrate_regular_lens
# --- funciones
cal = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, projection="rectilinear")
chk("f implicada = d·H/D = 2931 px", abs(fc.implied_focal_px(cal) - 886.64 * 40 / 12.1) < 1e-6, round(fc.implied_focal_px(cal), 1))
chk("focal equivalente Pixel 10 = 25.4 mm", abs(fc.calibration_focal_mm(cal) - 25.37) < 0.02, round(fc.calibration_focal_mm(cal), 2))
calL = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, projection="angular")
chk("misma focal con «Lineal» (el modelo no cambia la medición)", abs(fc.calibration_focal_mm(calL) - fc.calibration_focal_mm(cal)) < 1e-9)
r = fc.check_focal(cal, exif_35mm=24)
chk("EXIF 24 mm: +5.7 % → coherente", r["level"] == "ok" and abs(r["diff_pct"] - 5.7) < 0.1, r["text"][:70])
for D, H, exp in ((12.1, 40 * 1.10, "warn"), (12.1, 40 * 0.90, "ok"), (12.1, 40 * 1.03, "note"), (12.1, 25.7, "warn"), (12.1, 40 * 1.25, "warn")):
    c = calibrate_regular_lens(D, H, 886.64, 4000, 3000, projection="rectilinear")
    rr = fc.check_focal(c, exif_35mm=24)
    chk("frente al EXIF (Pixel 10 ya +5.7 %): H = {:.1f} cm → {} ({:+.1f} %)".format(H, exp, rr["diff_pct"]), rr["level"] == exp)
chk("límite 8 %: +7.9 % coherente, +8.1 % nota",
    fc.check_focal(cal, exif_35mm=fc.calibration_focal_mm(cal) / 1.079)["level"] == "ok"
    and fc.check_focal(cal, exif_35mm=fc.calibration_focal_mm(cal) / 1.081)["level"] == "note")
chk("límite 15 %: +14.9 % nota, +15.1 % aviso",
    fc.check_focal(cal, exif_35mm=fc.calibration_focal_mm(cal) / 1.149)["level"] == "note"
    and fc.check_focal(cal, exif_35mm=fc.calibration_focal_mm(cal) / 1.151)["level"] == "warn")
own = fc.check_focal(cal, exif_35mm=24, own_reference=("P10", 25.4 * 1.05))
chk("referencia propia tiene prioridad sobre el EXIF; −4.8 % → nota", own["ref_kind"] == "propia" and own["level"] == "note", own["text"][:80])
chk("sin D/H (radio GLAMA) → sin comprobación", fc.check_focal({"virtual_radius_px": 1618}, exif_35mm=24)["level"] is None)
chk("sin EXIF ni referencia → sin nivel, texto explicativo",
    fc.check_focal(cal)["level"] is None and "sin referencia" in fc.check_focal(cal)["text"])
# --- diálogo
from PIL.TiffImagePlugin import IFDRational as IR
ex = Image.Exif(); ex[0x010F] = "Google"; ex[0x0110] = "Pixel 10"
ifd = ex.get_ifd(0x8769); ifd[0xA405] = 24; ifd[0x920A] = IR(453, 100)
os.makedirs(OUT, exist_ok=True); jp = os.path.join(OUT, "px.jpg")
Image.fromarray((np.random.default_rng(1).random((300, 400, 3)) * 255).astype(np.uint8)).resize((4000, 3000)).save(
    jp, exif=ex.tobytes(), quality=80)
d = CobDoselDialog(Iface()); d._load_image_into_dialog(jp)
chk("modelo predeterminado = Rectilínea", d._current_projection_code() == "rectilinear")
d.circle_diameter.setValue(12.1); d.camera_height.setValue(40.0); d.pixel_diameter.setValue(886.64)
msgs.clear(); d._on_calibrate()
f1 = d.calibration.get("focal_check") or {}
chk("calibración correcta: coherente con EXIF, sin ventana de aviso", f1.get("level") == "ok" and f1.get("ref_kind") == "exif" and not [m for m in msgs if m[0] == "warning"], f1)
chk("resumen muestra la focal equivalente", "Focal equivalente 25.4 mm (EXIF: 24 mm; +5.7 %)" in d.calib_result.text(), [l for l in d.calib_result.text().splitlines() if "Focal" in l])
d.camera_height.setValue(25.7); msgs.clear(); d._on_calibrate()
chk("H mal medida (25.7 cm): aviso en ventana, la calibración igual queda lista",
    d.calibration["focal_check"]["level"] == "warn" and any(m[0] == "warning" and "focal" in m[1].lower() for m in msgs)
    and d.save_cal_btn.isEnabled())
# guardar la buena como referencia propia y recalibrar con otra medición
d.camera_height.setValue(40.0); d._on_calibrate()
cs.save_calibration("Pixel10_1x_H40_D12.1_rect", d.calibration, metadata={})
d.circle_diameter.setValue(23.4); d.pixel_diameter.setValue(1720.73); msgs.clear(); d._on_calibrate()
f2 = d.calibration["focal_check"]
chk("segunda calibración se compara con la propia (+0.35 %) → coherente",
    f2["ref_kind"] == "propia" and f2["ref_name"] == "Pixel10_1x_H40_D12.1_rect" and abs(f2["diff_pct"] - 0.35) < 0.05 and f2["level"] == "ok", f2)
d.camera_height.setValue(42.0); d._on_calibrate()
chk("H 2 cm mayor (+5 %) frente a la propia → nota", d.calibration["focal_check"]["level"] == "note", round(d.calibration["focal_check"]["diff_pct"], 2))
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
