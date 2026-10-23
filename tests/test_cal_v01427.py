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
from cobdosel.canopy_dialog import CobDoselDialog
from cobdosel.lens_calibration import calibrate_regular_lens
from cobdosel import batch_core as bc
rng = np.random.default_rng(5)
def img(w, h, name):
    p = os.path.join(OUT, name); Image.fromarray((rng.random((h, w, 3)) * 255).astype(np.uint8)).save(p); return p
os.makedirs(OUT, exist_ok=True)
pA, pB, pC = img(800, 600, "a.png"), img(1200, 900, "b.png"), img(960, 540, "c169.png")
# Sin calibraciones guardadas: valores predeterminados
d = CobDoselDialog(Iface())
chk("máscara predeterminada 63° (cenit 27°)", abs(d.horizon_mask_spin.value() - 63) < 1e-9 and abs(d.zenith_max.value() - 27) < 1e-9,
    (d.horizon_mask_spin.value(), d.zenith_max.value()))
chk("D y H predeterminados 33 y 40 cm", d.circle_diameter.value() == 33.0 and d.camera_height.value() == 40.0)
chk("diámetro en px: «sin medir» al abrir (antes 1975 fijos)", d.pixel_diameter.value() == 0.0 and d.pixel_diameter.text() == "sin medir",
    d.pixel_diameter.text())
chk("al abrir sin calibración, el estado explica qué hacer", "Cargar calibración" in d.calib_result.text())
d._load_image_into_dialog(pA)
msgs.clear(); d._on_calibrate()
chk("calcular sin medir el círculo: aviso y sin calibración", d.calibration is None and any("Mida el círculo" in m[1] for m in msgs))
chk("sin calibración guardada: la foto queda sin calibrar", d.calibration is None and not d.run_btn.isEnabled())
# Calibrar y guardar → queda como última
d.circle_diameter.setValue(33.0); d.camera_height.setValue(40.0); d.pixel_diameter.setValue(400); d._on_calibrate()
QInputDialog.getText = staticmethod(lambda *a, **k: ("Pixel10_1x_H40_D33", True))
d._on_save_calibration()
chk("guardar recuerda la calibración como última", cs.get_last_calibration() == "Pixel10_1x_H40_D33", cs.get_last_calibration())
saved = cs.load_calibration("Pixel10_1x_H40_D33")
chk("el archivo guarda D y H de la calibración", saved["calibration_metadata"]["circle_diameter_cm"] == 33.0
    and saved["calibration_metadata"]["camera_height_cm"] == 40.0)
# Nueva sesión: aviso al abrir y aplicación automática con la primera foto
d2 = CobDoselDialog(Iface())
d2.circle_diameter.setValue(12.2); d2.camera_height.setValue(25.7)
chk("al abrir, el estado nombra la última calibración", "Pixel10_1x_H40_D33" in d2.calib_result.text(), d2.calib_result.text()[:80])
d2._load_image_into_dialog(pB)
chk("primera foto: se aplica la última calibración", d2.calibration is not None and d2._cal_name == "Pixel10_1x_H40_D33" and d2.run_btn.isEnabled())
chk("los campos D y H muestran los de la calibración", d2.circle_diameter.value() == 33.0 and d2.camera_height.value() == 40.0,
    (d2.circle_diameter.value(), d2.camera_height.value()))
chk("calibración reescalada a la foto (1200 px)", d2.calibration["image_width_px"] == 1200)
R1 = d2.calibration["virtual_radius_px"]
# Segunda foto, misma proporción → se mantiene
d2._load_image_into_dialog(pA)
chk("foto siguiente (misma proporción): se mantiene", d2.calibration is not None and d2._cal_name == "Pixel10_1x_H40_D33"
    and abs(d2.calibration["virtual_radius_px"] - R1 * 800 / 1200) < 1e-6)
# Foto 16:9 → no se aplica, aviso
msgs.clear()
d2._load_image_into_dialog(pC)
chk("foto de otra proporción: no se aplica y avisa", d2.calibration is None and not d2.run_btn.isEnabled()
    and any("no corresponde" in m[1] for m in msgs), [m[1][:60] for m in msgs][:1])
# Análisis con la calibración automática
d3 = CobDoselDialog(Iface()); d3._load_image_into_dialog(pA)
d3.threshold_spin.setValue(128); d3._set_cut(128, "manual"); d3._on_run()
chk("análisis con la calibración aplicada automáticamente", d3.last_results is not None and
    abs(d3.last_results["mask_zenith_deg"] - 27.0) < 1e-9)
# Lote: registro de la calibración
rec = bc.calibration_record(saved)
chk("lote: registro con modelo, método, D, H y R", rec["circulo_D_cm"] == 33.0 and rec["altura_H_cm"] == 40.0
    and rec["calibracion_metodo"] == "círculo D/H" and rec["radio_hemisferio_px"] and rec["calibracion_modelo"], rec)
from cobdosel.batch_dialog import CobDoselBatchDialog
b = CobDoselBatchDialog(Iface())
chk("lote: propone la última calibración", b.cal_combo.currentData() == "Pixel10_1x_H40_D33", b.cal_combo.currentData())
print("\nRESULTADO:", "TODAS LAS PRUEBAS PASAN" if ok_all else "HAY FALLOS")
sys.exit(0 if ok_all else 1)
