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






import tempfile, math, csv as _csv
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
cs.get_last_calibration = lambda *a, **k: None
import cobdosel.canopy_dialog as cdm
cdm.get_last_calibration = cs.get_last_calibration
from cobdosel.cut_review_dialog import CutReviewDialog
from cobdosel.lens_calibration import calibrate_fisheye_from_radius, scale_calibration_to_image, calibrate_regular_lens
from cobdosel import batch_core as bc
from cobdosel.measure_circle_dialog import MeasureCircleDialog
os.makedirs(OUT, exist_ok=True)

# ---- #2 «Revisar cortes…» usa el centro de la calibración (ojo de pez descentrado)
fold = os.path.join(OUT, "fotos"); os.makedirs(fold, exist_ok=True)
yy, xx = np.mgrid[0:1500, 0:2000]
rr = np.hypot(xx - 1100, yy - 700)
rng = np.random.default_rng(3)
img = np.zeros((1500, 2000, 3), np.uint8)
inside = rr < 600
blocks = rng.random((60, 80)) > 0.5                       # bloques de 25 px: resisten el reescalado
sky = inside & np.kron(blocks, np.ones((25, 25), bool)).astype(bool) & (xx > 1100)
img[inside] = [30, 60, 30]; img[sky] = [210, 220, 250]
for k in range(3):
    Image.fromarray(img).save(os.path.join(fold, "f%d.jpg" % k), quality=95)
calf = calibrate_fisheye_from_radius(600, "polar", center_xy=(1100, 700), image_width_px=2000, image_height_px=1500)
items = []
for k in range(3):
    res = bc.analyze_photo(os.path.join(fold, "f%d.jpg" % k), calf, 45.0)
    it = dict(res); it.update(corte_auto=res["corte"], archivo="f%d.jpg" % k, parcela="1", punto="C", cenit_max=45.0, revisar=False)
    items.append(it)
dlg = CutReviewDialog(items, fold, calf, "blue_red")
cen = dlg._cache["c"]; k = dlg._cache["arr"].shape[1] / 2000.0     # la vista se reduce a ≤ 1600 px
chk("#2 revisión: centro = centro de la calibración (1100, 700) a la escala de la vista",
    abs(cen[0] - 1100 * k) < 1 and abs(cen[1] - 700 * k) < 1, (cen, k))
import re as _re
mm = _re.search(r"≈ ([0-9.]+) %", dlg.caco_label.text())
rev = float(mm.group(1)) if mm else None
chk("#2 CaCo de la revisión ≈ CaCo del lote (mismo corte)", rev is not None and abs(rev - items[0]["caco"]) < 1.5,
    (rev, round(items[0]["caco"], 2)))
# ---- #5 «Aceptar todas»: la nota de la foto en pantalla no se copia
dlg.note_edit.setText("tronco cercano (solo f0)")
dlg._on_accept_all()
notas = {k: v["nota"] for k, v in dlg.get_decisions().items()}
chk("#5 aceptar todas: ninguna foto recibe la nota de otra", all("tronco" not in n for n in notas.values()) and len(notas) == 3, notas)

# ---- #6 filtro de calidad por valor completo
ok6 = all(not bc.quality_excludes(v) for v in ("sin sol", "nublado, sin sol directo", "Soleado parcial", "no movida",
                                                "buena (no repetir)", "buena", "")) and \
      all(bc.quality_excludes(v) for v in ("sol directo", "Sol", "movida", "Repetir", "mala", "sol directo; movida"))
chk("#6 calidad: «sin sol», «no movida», «buena (no repetir)» no excluyen; «sol directo», «movida», «repetir» sí", ok6)

# ---- #3 «Medir en imagen…» con otra foto cargada dentro de la ventana
A = os.path.join(OUT, "A_4000x3000.png"); B = os.path.join(OUT, "B_2000x1500.png")
Image.fromarray(np.full((3000, 4000, 3), 90, np.uint8)).save(A)
Image.fromarray(np.full((1500, 2000, 3), 90, np.uint8)).save(B)
class FakeMeasure(MeasureCircleDialog):
    def exec(self):
        self.load_image(B)
        self.canvas.mode = "diametro"; self.canvas.points = [(500.0, 750.0), (1500.0, 750.0)]   # 1000 px en B
        return QtWidgets.QDialog.DialogCode.Accepted
    exec_ = exec
_orig_md, _orig_exec = cdm.MeasureCircleDialog, cdm._exec_dialog
cdm.MeasureCircleDialog = FakeMeasure
cdm._exec_dialog = lambda dlg: dlg.exec()
d = CobDoselDialog(Iface()); d._load_image_into_dialog(A)
d.circle_diameter.setValue(20); d.camera_height.setValue(40)
d._on_measure_in_image(); d._on_calibrate()
exp = calibrate_regular_lens(20, 40, 2000.0, 4000, 3000, "rectilinear")["virtual_radius_px"]
chk("#3 medición en otra foto: se registra esa foto y se reescala (R = el de 2000 px en A)",
    d._measure_info.get("file") == "B_2000x1500.png" and abs(d.calibration["virtual_radius_px"] - exp) < 1,
    (d._measure_info.get("file"), round(d.calibration["virtual_radius_px"], 1), round(exp, 1)))
cdm.MeasureCircleDialog, cdm._exec_dialog = _orig_md, _orig_exec

# ---- #7 sin calibración y lente regular: toda la foto
rng = np.random.default_rng(1)
img = np.full((1500, 2000, 3), 200, np.uint8)
can = rng.random((1500, 2000)) < 0.6
img[can] = [20, 30, 20]
img[(rng.random((1500, 2000)) < 0.15) & can] = [3, 5, 2]
pn = os.path.join(OUT, "nocal.png"); Image.fromarray(img).save(pn)
d2 = CobDoselDialog(Iface()); d2._load_image_into_dialog(pn)
chk("#7 sin calibración, lente regular: el histograma usa toda la foto (sin excluir sombra)",
    d2.calibration is None and d2._analysis_valid_mask(include_horizon_mask=True) is None)
d2.lens_combo.setCurrentIndex(0)
vm = d2._analysis_valid_mask(include_horizon_mask=True)
chk("#7 sin calibración, ojo de pez: se excluyen los píxeles negros (esquinas)", vm is not None and 0 < vm.mean() < 1)

# ---- #8 el CSV de una foto y el registro muestran el nombre del modelo, no el código
d3 = CobDoselDialog(Iface()); d3._load_image_into_dialog(A)
d3.circle_diameter.setValue(12.1); d3.camera_height.setValue(40.0); d3.pixel_diameter.setValue(886.64)
d3._on_calibrate(); d3._set_projection_by_code("angular")
d3._set_cut(128, "manual"); d3._on_run()
outcsv = os.path.join(OUT, "r.csv")
try:
    d3._write_csv(outcsv) if hasattr(d3, "_write_csv") else None
except Exception as e:
    print("   (csv)", e)
from cobdosel.canopy_dialog import _proj_label
chk("#8 nombre del modelo para el usuario", _proj_label(d3.calibration) == "Lineal (compatible con Polar de GLAMA)",
    _proj_label(d3.calibration))

# ---- #10 calibración Lineal imposible (> 90° en el lado corto) se rechaza
try:
    calibrate_regular_lens(100, 40, 400, 4000, 3000, "angular"); r10 = False
except ValueError as e:
    r10 = "más de 90°" in str(e)
chk("#10 Lineal con borde del lado corto > 90°: error claro en lugar de un ángulo falso", r10)
ok_norm = abs(calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, "angular")["virtual_radius_px"] - 4639.0) < 0.5
chk("#10 calibración normal sin cambios (R = 4639 px)", ok_norm)

# ---- #4 foto girada con centro desplazado: centro de la imagen y aviso (no un centro mal trasladado)
calo = calibrate_fisheye_from_radius(1400, "polar", center_xy=(2100, 1450), image_width_px=4000, image_height_px=3000)
sc = scale_calibration_to_image(calo, 3000, 4000)
chk("#4 foto girada: centro de la imagen y nota", sc["center_xy"] == [1500.0, 2000.0] and "girada" in sc.get("center_note", ""),
    sc["center_xy"])
sc2 = scale_calibration_to_image(calo, 2000, 1500)
chk("#4 misma orientación a otra resolución: centro escalado (1050, 725)", sc2["center_xy"] == [1050.0, 725.0], sc2["center_xy"])
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
