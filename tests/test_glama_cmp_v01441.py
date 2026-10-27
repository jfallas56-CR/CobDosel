"""CobDosel 0.14.41: comparación GLAMA ↔ CobDosel (orden guardado, casillas de giro, tabla).

Uso: python3 -I test_glama_cmp_v01441.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6> [carpeta_fotos]
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
from cobdosel.exif_gps import load_stored_rgb_image, load_oriented_rgb_image
from cobdosel.glama_engine import glama_rotate, glama_screen_indices, glama_boxes_label
from cobdosel import glama_compare as gc
from cobdosel.lens_calibration import calibrate_from_glama_radius, calibrate_regular_lens
from cobdosel.batch_core import analyze_photo

ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
tmpd = tempfile.mkdtemp(); cs.DEFAULT_DIR = tmpd; cs.LEGACY_DIR = os.path.join(tmpd, "legacy")
FOT = os.path.join(OUT, "fotos"); os.makedirs(FOT, exist_ok=True)

# ---------------------------------------------------------------- 1) giros de GLAMA
a = np.zeros((3, 4, 3), np.uint8); a[0, 3] = 255          # esquina superior derecha
chk("1 «90°» = cuarto de vuelta antihorario (sup. derecha → sup. izquierda)",
    glama_rotate(a, rot90=True)[0, 0, 0] == 255 and glama_rotate(a, rot90=True).shape[:2] == (4, 3))
chk("1 «180°» + «90°» = cuarto de vuelta horario (sup. derecha → inf. derecha)",
    glama_rotate(a, True, True)[3, 2, 0] == 255)
chk("1 «Tr.» intercambia filas y columnas", glama_rotate(a, transpose=True)[3, 0, 0] == 255)
chk("1 etiquetas de casillas", glama_boxes_label() == "sin giro" and glama_boxes_label(True, True) == "180° + 90°")

# ---------------------------------------------------------------- 2) foto sintética con EXIF 6
H, W = 3000, 4000
yy, xx = np.mgrid[0:H, 0:W]
img = np.full((H, W, 3), 60, np.uint8)
img[(xx < 1400)] = 230                                     # cielo a la izquierda (orden guardado)
gaps = rng.random((H // 20, W // 20)) < 0.25
img[np.kron(gaps, np.ones((20, 20), bool)) & (xx >= 1400)] = 210
p6 = os.path.join(FOT, "f6.jpg")
im = Image.fromarray(img); ex = im.getexif(); ex[274] = 6; im.save(p6, quality=95, exif=ex)
s_img, _s, s_wh, tag, note = load_stored_rgb_image(p6)
o_img, _s2, o_wh = load_oriented_rgb_image(p6)
chk("2 orden guardado: 4000 × 3000, etiqueta 6", s_wh == (4000, 3000) and tag == 6 and note == "", (s_wh, tag))
chk("2 CobDosel aplica el EXIF: 3000 × 4000", o_wh == (3000, 4000), o_wh)
stored = np.asarray(s_img); oriented = np.asarray(o_img)
chk("2 el orden guardado girado con «180°» + «90°» es la foto en posición normal",
    np.array_equal(glama_rotate(stored, True, True), oriented))

# ---------------------------------------------------------------- 3) el giro cambia GLAMA, no CobDosel
v = [glama_screen_indices(glama_rotate(stored, *bx), 1618, 30.0, 128, "blue_red")["canopy_cover_index_pct"]
     for bx in gc.ROTATION_BOXES]
chk("3 GLAMA: el CaCo cambia con el giro (franja contada como dosel)", max(v) - min(v) > 0.5,
    ["%.2f" % x for x in v])
calg = calibrate_from_glama_radius(1618, 3000, 4000)
p_rot = os.path.join(FOT, "f6_girada.png"); Image.fromarray(np.ascontiguousarray(np.rot90(oriented, 2))).save(p_rot)
c1 = analyze_photo(p6, calg, 30.0, cut_rule="fixed", fixed_cut=128)["caco"]
c2 = analyze_photo(p_rot, calg, 30.0, cut_rule="fixed", fixed_cut=128)["caco"]
chk("3 CobDosel: el mismo CaCo con la foto girada 180°", abs(c1 - c2) < 0.05, "%.3f vs %.3f" % (c1, c2))

# ---------------------------------------------------------------- 4) compare_photo
A_app = glama_screen_indices(stored, 1618, 30.0, 140, "blue_red")["canopy_cover_index_pct"]   # «app» sin casillas
r = gc.compare_photo(p6, calg, 140, 1618, 60.0, caco_glama=A_app)
chk("4 reproducción con el orden guardado: residuo 0", abs(r["residuo_reproduccion"]) < 1e-9, r["residuo_reproduccion"])
A_cob = glama_screen_indices(oriented, 1618, 30.0, 140, "blue_red")["canopy_cover_index_pct"]
chk("4 (mutación) con la foto en posición de CobDosel el valor difiere", abs(A_cob - A_app) > 0.3,
    "%.2f vs %.2f" % (A_cob, A_app))
tot = r["residuo_reproduccion"] + r["efecto_corte"] + r["efecto_geometria"]
chk("4 D − A = residuo + corte + geometría", abs(tot - r["diferencia_total"]) < 1e-9)
r2 = gc.compare_photo(p6, calg, 140, 1618, 60.0, caco_glama=A_app, corte_cobdosel=140)
chk("4 mismo corte en los dos programas → efecto del corte 0", r2["efecto_corte"] == 0.0
    and r2["metodo_corte_cobdosel"] == "fijo (tabla)", r2["efecto_corte"])
r3 = gc.compare_photo(p6, calg, 140, 1618, 60.0, caco_glama=A_app, corte_cobdosel=170)
chk("4 solo cambia el corte: B no cambia y C − B ≠ 0", abs(r3["caco_reproduccion"] - r["caco_reproduccion"]) < 1e-12
    and abs(r3["efecto_corte"]) > 0.1, r3["efecto_corte"])
r4 = gc.compare_photo(p6, calg, 140, 1618, 60.0, caco_glama=A_app, boxes=(False, True, False))
chk("4 casillas equivocadas: aviso y giros que reproducen la app (sin giro; 180° da casi lo mismo aquí)",
    r4["giro_sugerido"].split(" o ")[0] == "sin giro" and "90°" not in r4["giro_sugerido"]
    and "residuo de la reproducción" in r4["avisos"], (r4["giro_sugerido"], r4["residuo_reproduccion"]))
chk("4 orientación EXIF registrada", r["orientacion_exif"].startswith("6"), r["orientacion_exif"])

# ---------------------------------------------------------------- 5) tabla
tp = os.path.join(OUT, "tabla.csv")
with open(tp, "w", newline="", encoding="utf-8") as f:
    f.write("Archivo;Corte GLAMA;CaCo GLAMA;180°;90°;Tr.;Hemisph. radius;corte_cobdosel\n")
    f.write("f6.jpg;140;{};;;;1618;\n".format(("%.4f" % A_app).replace(".", ",")))
    f.write("f6.jpg;140;{};x;sí;0;1618;150\n".format(("%.4f" % A_app).replace(".", ",")))
    f.write("no_existe.jpg;140;;;;;1618;\n")
rows = gc.read_comparison_table(tp)
chk("5 tabla: encabezados alternativos, coma decimal y casillas «x», «sí»",
    len(rows) == 3 and abs(rows[0]["caco_glama"] - A_app) < 1e-3 and rows[1]["giro_180"] and rows[1]["giro_90"]
    and not rows[1]["transponer"] and rows[1]["corte_cobdosel"] == 150 and rows[0]["radio_glama"] == 1618)
bad = os.path.join(OUT, "mala.csv")
open(bad, "w").write("archivo,caco_glama\nf6.jpg,20\n")
try:
    gc.read_comparison_table(bad); err = ""
except ValueError as e:
    err = str(e)
chk("5 sin columna corte_glama → error claro", "corte_glama" in err, err)
open(bad, "w").write("archivo,corte_glama\nf6.jpg,300\n")
try:
    gc.read_comparison_table(bad); err = ""
except ValueError as e:
    err = str(e)
chk("5 corte fuera de 0–255 → error con la fila", "Fila 2" in err, err)
outc = os.path.join(OUT, "cmp.csv")
res, summ, paths = gc.run_comparison(tp, FOT, calg, outc, glama_mask_deg=60.0)
with open(outc, encoding="utf-8-sig") as f:
    rr = list(csv.reader(f))
chk("5 CSV con las columnas de salida y 3 filas", tuple(rr[0]) == gc.OUT_COLUMNS and len(rr) == 4)
chk("5 la foto que falta no detiene la comparación", rr[3][-1].startswith("ERROR") and rr[1][8] != "")
chk("5 punto decimal en el CSV", "," not in rr[1][7] and "." in rr[1][7], rr[1][7])
chk("5 resumen escrito", os.path.isfile(paths[1]) and "Efecto del corte" in open(paths[1], encoding="utf-8").read())
n = gc.write_template(FOT, os.path.join(OUT, "plantilla.csv"))
chk("5 plantilla con las fotos de la carpeta", n == 2, n)

# ---------------------------------------------------------------- 6) ventana principal
d = CobDoselDialog(Iface()); d.show(); app.processEvents()
chk("6 casilla «orden guardado» marcada por defecto; casillas de giro desmarcadas",
    d.glama_stored_check.isChecked() and not (d.glama_rot180_check.isChecked() or d.glama_rot90_check.isChecked()
                                              or d.glama_tr_check.isChecked()))
d._load_image_into_dialog(p6)
d.glama_radius_spin.setValue(1618.0); d._on_calibrate_glama_radius()   # v0.14.53: siempre lado menor
d.zenith_max.setValue(30.0); d.threshold_spin.setValue(140)
d.glama_geometry_check.setChecked(True); d._on_run(); app.processEvents()
g1 = d.last_results["metrics"]["canopy_cover_index_pct"]
chk("6 reproducción en la ventana = app sin casillas (orden guardado)", abs(g1 - A_app) < 1e-9, "%.4f vs %.4f" % (g1, A_app))
chk("6 orientación registrada en el resultado",
    "orden guardado (EXIF 6)" in d.last_results["glama_geometry"]["orientation"],
    d.last_results["glama_geometry"]["orientation"])
d.glama_rot180_check.setChecked(True); d.glama_rot90_check.setChecked(True); d._on_run()
g2 = d.last_results["metrics"]["canopy_cover_index_pct"]
chk("6 con «180°» + «90°» = la foto en posición normal", abs(g2 - A_cob) < 1e-9, "%.4f vs %.4f" % (g2, A_cob))
d.glama_rot180_check.setChecked(False); d.glama_rot90_check.setChecked(False)
d.glama_stored_check.setChecked(False); d._on_run()
g3 = d.last_results["metrics"]["canopy_cover_index_pct"]
chk("6 sin «orden guardado»: posición de CobDosel", abs(g3 - A_cob) < 1e-9)
import cobdosel.glama_compare_dialog as gcd
seen = []
gcd.GlamaCompareDialog.exec = lambda s: seen.append(s) or 0
gcd.GlamaCompareDialog.exec_ = gcd.GlamaCompareDialog.exec
d._on_glama_compare()
chk("6 botón «Comparar con GLAMA (tabla)…» abre la ventana con la calibración activa",
    seen and seen[0].calibration is d.calibration and abs(seen[0].radius_spin.value() - 1618) < 1e-6)

# ---------------------------------------------------------------- 7) ventana de comparación
dl = seen[0]; dl.show(); app.processEvents()
dl.table_edit.setText(tp); dl.folder_edit.setText(FOT); dl.out_edit.setText(os.path.join(OUT, "cmp_dlg.csv"))
QtTest = importlib.import_module(QT + ".QtTest"); Qt = QtCore.Qt
dl.gmask_spin.setFocus(); QtTest.QTest.keyClick(dl.gmask_spin, Qt.Key.Key_Return); app.processEvents()
chk("7 Intro en una casilla no ejecuta ni cierra", dl.isVisible() and not dl.out_paths)
dl.run(); app.processEvents()
chk("7 «Comparar» escribe CSV y resumen", len(dl.out_paths) == 2 and all(os.path.isfile(p) for p in dl.out_paths)
    and dl.open_btn.isEnabled())
chk("7 el resumen se muestra en la ventana", "Efecto del corte" in dl.log_edit.toPlainText())

# ---------------------------------------------------------------- 8) fotos reales (opcional)
if len(sys.argv) > 4:
    U = sys.argv[4]
    pe = os.path.join(U, "675f00d6-image.jpg")
    # Foto del ejemplo verificado («Ejemplo verificado: mismo corte, CaCo distinto»): copia sin EXIF, guardada
    # en vertical; «90°» la devuelve al orden del sensor del original. Valores de la app: radio 1618, máscara 60°.
    if os.path.isfile(pe):
        for cut, app_v in ((135, 24.16), (143, 24.58), (145, 24.63)):
            rr8 = gc.compare_photo(pe, calg, cut, 1618, 60.0, caco_glama=app_v, boxes=(False, True, False))
            chk("8 ejemplo verificado, corte {}: reproducción = app ± 0.1".format(cut),
                abs(rr8["residuo_reproduccion"]) <= 0.1, "%.2f vs %.2f" % (rr8["caco_reproduccion"], app_v))

print("TODO OK" if ok_all else "HAY FALLAS")
