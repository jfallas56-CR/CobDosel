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
import cobdosel.calibration_store as cs
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
import cobdosel.canopy_dialog as cdm
from cobdosel.canopy_dialog import CobDoselDialog
from cobdosel.measure_circle_dialog import MeasureCircleDialog
from cobdosel.lens_calibration import calibrate_regular_lens
os.makedirs(OUT, exist_ok=True)
jpg = os.path.join(OUT, "cal.png")
Image.fromarray((np.random.default_rng(2).random((3000, 4000, 3)) * 255).astype(np.uint8)).save(jpg)
def circle_pts(cx, cy, r):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 45)]
# Diálogo de medición: D y H precargados y θ
md = MeasureCircleDialog(jpg, max_dim=4096, diameter_cm=12.2, height_cm=40.0)
chk("diálogo de medición: D y H precargados", md.get_diameter_cm() == 12.2 and md.get_height_cm() == 40.0)
chk("diálogo de medición: θ = atan(D/2H) = 8,67°", "8.67°" in md.theta_label.text(), md.theta_label.text()[:40])
# Calibración guardada 12,2 cm (última usada)
cal_old = calibrate_regular_lens(12.2, 40.0, 886.3, 4000, 3000, projection="angular")
cal_old["measurement"] = {"mode": "ajuste", "image_size": [4000, 3000], "summary": "previa"}
cs.save_calibration("Pixel10_D12", cal_old, metadata={"circle_diameter_cm": 12.2, "camera_height_cm": 40.0,
                    "pixel_diameter_px": 886.3, "measurement": cal_old["measurement"]})
cs.set_last_calibration("Pixel10_D12")
# «Medir desde archivo» sin foto cargada: medición del círculo de 20,8 cm
d = CobDoselDialog(Iface())
md2 = MeasureCircleDialog(jpg, max_dim=4096, diameter_cm=12.2, height_cm=40.0)
md2.mode_combo.setCurrentIndex(md2.mode_combo.findData("ajuste"))
md2.canvas.points = circle_pts(2000, 1500, 755.0)
md2._on_points_changed(md2.canvas.points)
md2.d_spin.setValue(20.8); md2.h_spin.setValue(40.0)
_o = (cdm.MeasureCircleDialog, cdm._exec_dialog, cdm.QFileDialog.getOpenFileName)
cdm.MeasureCircleDialog = lambda *a, **k: md2
cdm._exec_dialog = lambda dlg: cdm.QDialog.DialogCode.Accepted
cdm.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (jpg, ""))
d._on_measure_from_file()
chk("medir desde archivo sin foto: la foto se carga", d.image_path == jpg)
chk("D y H del diálogo pasan a la ventana (20,8 / 40), no los de la calibración recordada",
    d.circle_diameter.value() == 20.8 and d.camera_height.value() == 40.0, (d.circle_diameter.value(), d.camera_height.value()))
chk("el diámetro medido (1510 px) no se sobrescribe con el de la calibración recordada (886,3)",
    abs(d.pixel_diameter.value() - 1510.0) < 0.5, d.pixel_diameter.value())
d._on_calibrate()
txt = d.calib_result.text()
chk("calibración nueva con D = 20,8", abs(d.calibration["circle_diameter_cm"] - 20.8) < 1e-9 and abs(d.calibration["pixel_diameter_px"] - 1510) < 0.5)
chk("el resumen muestra D y H", "D = 20.80 cm a H = 40.00 cm" in txt, [l for l in txt.split("\n") if "Círculo de referencia" in l])
# «Medir en imagen» también pasa D y H
md3 = MeasureCircleDialog(jpg, max_dim=4096, diameter_cm=20.8, height_cm=40.0)
md3.mode_combo.setCurrentIndex(md3.mode_combo.findData("ajuste"))
md3.canvas.points = circle_pts(2000, 1500, 443.0); md3._on_points_changed(md3.canvas.points)
md3.d_spin.setValue(12.2)
cdm.MeasureCircleDialog = lambda *a, **k: md3
d._on_measure_in_image()
chk("medir en imagen: D pasa a 12,2 y el diámetro a 886 px", d.circle_diameter.value() == 12.2 and abs(d.pixel_diameter.value() - 886.0) < 0.5,
    (d.circle_diameter.value(), d.pixel_diameter.value()))
cdm.MeasureCircleDialog, cdm._exec_dialog, cdm.QFileDialog.getOpenFileName = _o
print("\nRESULTADO:", "TODAS LAS PRUEBAS PASAN" if ok_all else "HAY FALLOS")
sys.exit(0 if ok_all else 1)
