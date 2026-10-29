"""CobDosel 0.14.48: Analista, informe de una foto (sitio, analista, pie), anillos con letra mayor y leyenda arriba,
ventana del lote sin máscara por altura ni «5 = Centro…», informe del sitio (cielo verificado, tabla de parcelas).

Uso: python3 -I test_v01448.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos_cielo] [carpeta_fotos_cielo]
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

from cobdosel.visualization import render_glama_rings
import cobdosel.visualization as viz
# ---- 1) Analista en las ventanas, CSV y JSON compatible
bd = CobDoselBatchDialog(None); bd.show(); app.processEvents()
labels = [w.text() for w in bd.findChildren(QtWidgets.QLabel)]
chk("1 lote: «Analista:» y no «Operador:»", "Analista:" in labels and "Operador:" not in labels)
chk("1 lote: sin modo «Desde la altura del dosel»", not hasattr(bd, "mask_height_radio") and not hasattr(bd, "group_combo")
    and not any("altura del dosel" in w.text() for w in bd.findChildren(QtWidgets.QRadioButton)))
chk("1 lote: «Máscara de horizonte:» con la máscara fija", "Máscara de horizonte:" in labels and bd.fixed_mask_spin.value() == 63.0)
chk("1 lote: sin «5 = Centro, N-O…» en la ventana", "Centro" not in bd.per_plot_spin.toolTip()
    and "protocolo" in bd.per_plot_spin.toolTip())
import inspect
src_bd = inspect.getsource(CobDoselBatchDialog._draft_form)
chk("1 «Crear formulario desde las fotos»: sin «5 = Centro…»", "Centro" not in src_bd and "protocolo del estudio" in src_bd)
src_cr = inspect.getsource(sys.modules["cobdosel.cut_review_dialog"])
chk("1 «Revisar cortes…»: «Analista:» y no «Operador:»", '"Analista:"' in src_cr and '"Operador:"' not in src_cr)
chk("1 CSV de fotos: columna «analista», no «operador»", "analista" in bc.PHOTO_CSV_COLUMNS and "operador" not in bc.PHOTO_CSV_COLUMNS)

# ---- 2) informe del sitio
H, W = 1500, 2000
yy, xx = np.mgrid[0:H, 0:W]
rng = np.random.default_rng(7)
img = np.full((H, W, 3), 45, np.uint8)
gaps = np.kron(rng.random((H // 25, W // 25)) < 0.45, np.ones((25, 25), bool))
img[gaps] = 225
fold = os.path.join(OUT, "lote"); shutil.rmtree(fold, ignore_errors=True); os.makedirs(fold)
for k in range(4):
    Image.fromarray(img).save(os.path.join(fold, "F%d.jpg" % k), quality=92)
fold5 = os.path.join(OUT, "lote5"); shutil.rmtree(fold5, ignore_errors=True); os.makedirs(fold5)
for k in range(5):
    Image.fromarray(img[::4, ::4]).save(os.path.join(fold5, "G%d.jpg" % k), quality=80)
_dp, _n, _w = bc.draft_form_from_photos(fold5, os.path.join(OUT, "borr.csv"), 5)
_rec, _ = bc.read_field_form(_dp)
chk("2 formulario desde las fotos con 5 por parcela: puntos «Foto 1…5», no «Centro»",
    [r["punto_norm"] for r in _rec] == ["Foto %d" % i for i in range(1, 6)], [r["punto_norm"] for r in _rec])
calg = calibrate_from_glama_radius(1618, W, H)
b = bc.run_batch(fold, None, calg, None, photos_per_plot=4)
b["parametros"]["analista"] = "Ana"
for r, v in zip(b["fotos"], (80.0, 10.0, 10.0, 10.0)):
    r["cielo_rango"] = v
hp = os.path.join(OUT, "lote.html"); bc.write_html(b, hp, VERSION, "S")
hl = open(hp, encoding="utf-8").read()
head = hl.split("<h2>Parcelas</h2>")[0]
chk("2 cielo sin decisión: «1 de 4 fotos válidas: cielo no uniforme. Sin verificar…»",
    "1 de 4 fotos válidas: cielo no uniforme (rango de brillo del cielo 80" in head and "Sin verificar" in head,
    head[-300:])   # v0.14.63: la línea incluye el rango (el aviso del cielo dejó de repetirse en «Avisos»)
chk("2 sin «fuera del protocolo de campo» ni «el resultado depende»", "fuera del protocolo" not in hl and "el resultado depende" not in hl)
chk("2 avisos: el aviso de cielo sin «fuera del protocolo de campo»",
    not any("fuera del protocolo" in w for w in bc.summarize_common_warnings(b["fotos"])))
b["fotos"][0]["decision"] = "aceptado"; b["fotos"][0]["analista"] = "Ana"
chk("2 cielo con decisión: «… Verificadas por Ana.»", bc.sky_review_line(b["fotos"], "Ana") ==
    "1 de 4 fotos válidas: cielo no uniforme (rango de brillo del cielo 80, límite 50: nubes de distinto brillo, "
    "cielo azul, sol o resplandor). Verificadas por Ana.", bc.sky_review_line(b["fotos"], "Ana"))
b["fotos"][0]["analista"] = ""
chk("2 decisión sin nombre: se usa el analista de la ventana", bc.sky_review_line(b["fotos"], "Luis").endswith("Verificadas por Luis."))
bc.write_html(b, hp, VERSION, "S"); hl = open(hp, encoding="utf-8").read()
plots = hl.split("<h2>Parcelas</h2>")[1].split("</table>")[0]
chk("2 parcelas: «Fotos válidas» como «4 de 4»", "<td class='c'>4 de 4</td>" in plots, plots[-200:])
chk("2 parcelas sin reemplazos: sin columna «Reemplazo» vacía", "<th>Reemplazo</th>" not in plots)
b["parcelas"].append(dict(b["parcelas"][0], parcela="9", reemplaza_a="3"))
bc.write_html(b, hp, VERSION, "S"); hl = open(hp, encoding="utf-8").read()
plots = hl.split("<h2>Parcelas</h2>")[1].split("</table>")[0]
chk("2 con un reemplazo: columna «Reemplazo» con «reemplaza a 3» y «—» en las demás",
    "<th>Reemplazo</th>" in plots and "reemplaza a 3" in plots and "<td>—</td>" in plots)
chk("2 cabeceras numéricas alineadas como sus datos", "th.n{{" not in hl and "td.n,th.n{" in hl and "td.c,th.c{" in hl)
bd.batch = b; bd._show()
chk("2 panel: la misma línea del cielo", "Verificadas por" in bd.out.toPlainText().split("PARCELAS")[0])

# ---- 3) informe de una foto
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
p1 = os.path.join(fold, "F0.jpg")
d._load_image_into_dialog(p1)
cal = calibrate_regular_lens(20.6, 40.0, 1512.68, 4000, 3000, projection="rectilinear")
d.calibration = scale_calibration_to_image(cal, W, H); d.center_xy = (W / 2.0, H / 2.0); d._cal_name = "Prueba"
d.zenith_max.setValue(27.0); d._on_run(); app.processEvents()
d.site_edit.setText("Sitio Río Frío"); d.analyst_edit.setText("Ana Mora")
_save = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "foto.html"), ""))
d._on_export_html(); app.processEvents()
QFileDialog.getSaveFileName = _save
ht = open(os.path.join(OUT, "foto.html"), encoding="utf-8").read()
hdr = ht.split("1. Resultados")[0]
chk("3 encabezado: Nombre del sitio y Analista", "<strong>Sitio:</strong> Sitio Río Frío · <strong>Analista:</strong> Ana Mora" in hdr)
chk("3 sin «El cierre del dosel no es cobertura»", "El cierre del dosel no es cobertura" not in ht)
chk("3 hemisferio: convención de GLAMA, no «convención de Tichý 2016» (v0.14.51)", "convención de Tichý 2016" not in ht
    and "No es una convención universal" in " ".join(ht.split()))
foot = ht.split("<footer>")[1]
chk("3 pie: «Basado en Tichý (2016)», luego CobDosel para QGIS · Autor · Contacto, al final",
    foot.index("Basado en Tichý (2016)") < foot.index("para QGIS · Autor: Jorge Fallas · Contacto:")
    and "Método de los índices" not in ht and ht.count("Autor:") == 1 and ht.rindex("jfallas56") > ht.index("<footer>"))
# CSV de una foto
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "foto.csv"), ""))
try:
    d._on_export_csv(); app.processEvents()
finally:
    QFileDialog.getSaveFileName = _save
rows = list(csv.reader(open(os.path.join(OUT, "foto.csv"), encoding="utf-8-sig")))
hrow = rows[0]
chk("3 CSV de una foto: site_name y analyst", "site_name" in hrow and rows[1][hrow.index("analyst")] == "Ana Mora"
    and rows[1][hrow.index("site_name")] == "Sitio Río Frío")

# ---- 4) anillos cenitales: letra mayor y leyenda arriba
seen = []
_orig_box = viz._draw_text_box
def _spy(draw, cx, cy, text, font, *a, **k):
    seen.append((text, getattr(font, "size", 0))); return _orig_box(draw, cx, cy, text, font, *a, **k)
viz._draw_text_box = _spy
ph = os.path.join(OUT, "vert.jpg")
Image.fromarray(np.full((1600, 1200, 3), 90, np.uint8)).save(ph)          # foto vertical (teléfono)
calv = {"projection": "rectilinear", "focal_length_px": 2937.0 * 1200 / 3000, "image_width_px": 1200,
        "image_height_px": 1600, "center_xy": [600, 800]}
o1 = render_glama_rings(ph, calv, zenith_max_deg=27.0, n_sectors=8, legend_lines=["Nivel de corte 182", "CaCo 72.35 %"],
                        output_path=os.path.join(OUT, "anillos63.png"))
viz._draw_text_box = _orig_box
s_sizes = [sz for t, sz in seen if t.startswith("S")]
chk("4 etiquetas S1–S8 con letra mayor (≥ lado corto / 32; antes / 60)", len(s_sizes) == 8 and min(s_sizes) >= int(1200 / 32),
    s_sizes[:2])
im1 = np.asarray(Image.open(o1))
chk("4 máscara 63° en foto vertical: la leyenda cabe arriba (no se añade franja)", im1.shape[:2] == (1600, 1200))
band = im1[:120, :, :]
chk("4 la leyenda está en la franja superior libre (texto blanco sobre negro)", (band.max(axis=2) > 200).sum() > 500
    and (band.max(axis=2) < 10).sum() > 5000)
import math
top_circle = 800 - calv["focal_length_px"] * math.tan(math.radians(27.0))
blk = (im1[:700, 20:300].max(axis=2) < 10).mean(axis=1) > 0.6                    # filas de la caja negra
last = int(np.nonzero(blk)[0].max())
chk("4 la caja de la leyenda termina sobre el círculo (no tapa el dosel)", last < top_circle, (last, round(top_circle)))
o2 = render_glama_rings(ph, calv, zenith_max_deg=33.0, n_sectors=8, legend_lines=["Nivel de corte 182", "CaCo 72.35 %"],
                        output_path=os.path.join(OUT, "anillos57.png"))
im2 = Image.open(o2)
chk("4 sin espacio arriba (máscara 57°): franja añadida encima de la foto", im2.size[0] == 1200 and im2.size[1] > 1600, im2.size)
print("TODO OK" if ok_all else "HAY FALLAS")
