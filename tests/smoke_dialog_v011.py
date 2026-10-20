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

# --- Foto de lente regular con GPS: 30 % de cielo en manchas ---
h, w = 3000, 4000
f = ndimage.gaussian_filter(rng.random((h, w)), 8); sky = f > np.quantile(f, 0.70)
arr = np.where(sky[..., None], np.array([200, 215, 240], np.uint8), np.array([40, 70, 35], np.uint8)).astype(np.uint8)
img = Image.fromarray(arr); ex = img.getexif()
ex[0x8825] = {1: "N", 2: (R(10), R(30), R(0)), 3: "W", 4: (R(84), R(15), R(0)), 5: b"\x00", 6: R(1200)}
ex[0x0132] = "2026:10:01 09:30:00"
jpg = os.path.join(OUT, "foto_regular.jpg"); img.save(jpg, exif=ex, quality=100, subsampling=0)


import cobdosel.calibration_store as cs
cs.DEFAULT_DIR = os.path.join(OUT, "cal"); cs.LEGACY_DIR = os.path.join(OUT, "cal_old")
from cobdosel._version import VERSION
from cobdosel.canopy_dialog import CobDoselDialog
import cobdosel.canopy_dialog as cd
from cobdosel.measure_circle_dialog import MeasureCircleDialog
from cobdosel import cobdosel_plugin, classFactory
print("Qt:", QT, "| VERSION:", VERSION, "| tipo campo texto:", cd._STR)
fails = []
def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


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


plug = classFactory(Iface()); plug.initGui()
check("classFactory → CobDosel, menú «&CobDosel»", type(plug).__name__ == "CobDosel" and plug.iface.menu == "&CobDosel")
check("icono cobdosel.svg presente", os.path.isfile(os.path.join(plug.plugin_dir, "cobdosel.svg")))
d = CobDoselDialog(Iface())
check("título CobDosel v" + VERSION, d.windowTitle().startswith("CobDosel v" + VERSION), d.windowTitle()[:60])
check("ayuda sin el nombre antiguo como producto", "CobDosel" in d.full_help_browser.toPlainText()
      and "7575" not in d.full_help_browser.toPlainText() and "70 %" not in d.full_help_browser.toPlainText())

assert d._load_image_into_dialog(jpg)
d.lens_combo.setCurrentIndex(1)

# Medición del círculo: dos diámetros E–O / N–S sobre la propia foto (4000×3000)
md = MeasureCircleDialog(jpg, max_dim=4096)
check("modo de medición por defecto = dos diámetros", md.canvas.mode == "cruz")
md.canvas.points = [(1500.0, 1500.0), (2500.0, 1500.0), (2000.0, 1004.0), (2000.0, 1996.0)]
md._on_points_changed(md.canvas.points)
rec = d._measurement_record(md, jpg, d.original_image_size)
check("medición: diámetro medio 996 px, diferencia 0.80 %", abs(md.get_pixel_diameter() - 996.0) < 0.05
      and abs(rec["diff_pct"] - 0.8032) < 1e-3, rec["summary"])
d.pixel_diameter.setValue(md.get_pixel_diameter()); d.last_measured_pixel_diameter = md.get_pixel_diameter()
d._measure_info = rec
check("tipo de lente por defecto = lente regular", d.lens_combo.currentIndex() == 1 and not d.glama_cal_check.isVisible())
d._on_calibrate()
txtc = d.calib_result.text()
check("calibración muestra R, sin equivalente GLAMA", "Radio del hemisferio" in txtc and "GLAMA" not in txtc, txtc)
check("calibración guarda la medición", d.calibration["measurement"]["mode"] == "cruz")
# Ruta real «Medir en la foto» con un diámetro con más de 2 decimales (el campo redondea)
import cobdosel.canopy_dialog as _cdm
md2 = MeasureCircleDialog(jpg, max_dim=4096)
md2.canvas.points = [(1500.123, 1500.0), (2500.0, 1500.0), (2000.0, 1004.1), (2000.0, 1996.0)]
md2._on_points_changed(md2.canvas.points)
_orig_mcd, _orig_exec = _cdm.MeasureCircleDialog, _cdm._exec_dialog
_cdm.MeasureCircleDialog = lambda *a, **k: md2
_cdm._exec_dialog = lambda dlg: _cdm.QDialog.DialogCode.Accepted
d._on_measure_in_image()
d._on_calibrate()
_cdm.MeasureCircleDialog, _cdm._exec_dialog = _orig_mcd, _orig_exec
check("medición real con diámetro fraccionario (%.4f px) se guarda como medida, no «escrita a mano»"
      % md2.get_pixel_diameter(), d.calibration["measurement"].get("mode") == "cruz"
      and d.calibration["measurement"].get("file") is not None, d.calibration["measurement"].get("summary"))
check("la máscara NO cambia al calibrar", abs(d.horizon_mask_spin.value() - 45.0) < 1e-9, d.horizon_mask_spin.value())

# Máscara que supera el semiángulo del lado corto: anillos hasta la máscara
half = d.calibration["max_zenith_deg"]
d.zenith_max.setValue(round(half + 4.0, 1)); d.threshold_spin.setValue(128); d.n_rings.setValue(4)
d._on_run(); res = d.last_results
check("rango analizado = máscara (%.1f°) > semiángulo del lado corto (%.2f°)" % (d.zenith_max.value(), half),
      abs(res["zenith_max_deg"] - d.zenith_max.value()) < 1e-6 and res["ring_boundaries"][-1][1] > half)
check("círculo de análisis visible < 100 %: informado en el panel, no como aviso del informe",
      res["circle_visible_pct"] < 100 and not any("parcialmente fuera" in w for w in res["run_warnings"])
      and "visible en la foto" in d.results_text.toPlainText(), "%.1f %%" % res["circle_visible_pct"])
txt = d.results_text.toPlainText()
check("encabezado «RESULTADOS (basado en Tichý 2016)», sin «método GLAMA» ni CAnOPY",
      "RESULTADOS (basado en Tichý 2016)" in txt and "método GLAMA" not in txt and "CAnOPY" not in txt
      and "REPORTADOS POR GLAMA" not in txt)
check("CaCo identificado como cobertura del dosel, sin referencias legales", "← cobertura del dosel" in txt
      and "7575" not in txt and "70 %" not in txt)
check("tabla por sectores (8)", "POR ANILLO × SECTOR" in txt and len(res["sectors"]) == 4 * 8)
check("calibración con huella de cámara; panel con cámara de la calibración y de la foto",
      isinstance(d.calibration.get("camera"), dict) and "Cámara calibración:" in txt and "Cámara de la foto:" in txt
      and res.get("camera_check") in (True, None), d.calibration.get("camera"))
check("EXIF y medición en el panel", "Medición del círculo:" in txt)
caco_ok = res["metrics"]["canopy_cover_index_pct"]
print("    CaCo (geometría correcta) = %.2f %%" % caco_ok)

# Otsu limitado al área no enmascarada
d._on_otsu(); print("    Otsu en el área analizada: T =", d.threshold_spin.value())
# 0.14.5: selector de método automático (Otsu / Mínimo) + «Calcular»
t_otsu = d.threshold_spin.value()
codes = [d.auto_method_combo.itemData(i) for i in range(d.auto_method_combo.count())]
d.auto_method_combo.setCurrentIndex(codes.index("minimum")); d._on_otsu(); t_min = d.threshold_spin.value()
check("0.14.5: métodos automáticos Otsu y Mínimo con botón «Calcular» (Otsu %d, Mínimo %d)" % (t_otsu, t_min),
      codes == ["otsu", "minimum"] and d.otsu_btn.text() == "Calcular" and 1 <= t_min <= 254)
d.auto_method_combo.setCurrentIndex(0)
from qgis.PyQt.QtWidgets import QLabel as _QL
_labels = " ".join(w.text() for w in d.findChildren(_QL))
check("0.14.5: sin nombre del autor en la ventana (título, etiquetas, panel de resultados)",
      "Jorge" not in d.windowTitle() and "Jorge" not in _labels and "Jorge" not in d.results_text.toPlainText(),
      d.windowTitle())
# 0.14.5: aviso graduado del desplazamiento del centro y línea de desplazamiento
md3 = MeasureCircleDialog(jpg, max_dim=4096)
md3.canvas.points = [(1580.0, 1500.0), (2580.0, 1500.0), (2080.0, 1000.0), (2080.0, 2000.0)]   # 80 px = 8 %
md3._on_points_changed(md3.canvas.points); md3.canvas._redraw()
q8 = md3.quality_label.text()
md3.canvas.points = [(1700.0, 1500.0), (2700.0, 1500.0), (2200.0, 1000.0), (2200.0, 2000.0)]   # 200 px = 20 %
md3._on_points_changed(md3.canvas.points)
q20 = md3.quality_label.text()
check("0.14.11: desplazamiento 8 % → veredicto «utilizable» con nota; 20 % → «repita la fotografía»",
      "Calibración utilizable" in q8 and "Puede usar la calibración" in q8
      and "No use esta calibración: repita la fotografía" in q20 and "<b>Fotografía:</b>" in q20,
      (q8[:50], q20[:50]))
md3.mode_combo.setCurrentIndex(2)
import math as _m
md3.canvas.points = [(2000 + 500 * _m.cos(_m.radians(a)), 1500 + 500 * _m.sin(_m.radians(a))) for a in (0, 20, 40, 60, 80, 100)]
md3._on_points_changed(md3.canvas.points)
check("0.14.5: ajuste con puntos en un arco de 100° → aviso de distribución",
      "arco de 100°" in md3.quality_label.text() and "arco cubierto" in md3.points_label.text(), md3.points_label.text()[-40:])
d.threshold_spin.setValue(128)
# «Recomendado (GLAMA)»: mismo resultado partiendo de 21 o de 200 (iterado desde 128)
recs = []
for t0 in (21, 200):
    d.threshold_spin.setValue(t0); d._on_glama_cut(); recs.append(d.threshold_spin.value())
check("Recomendado (log-normal) no depende del valor previo (21 → %d, 200 → %d)" % tuple(recs),
      recs[0] == recs[1] and recs[0] != 21)
m_rec = d.cut_method
# 0.14.12: si la comprobación del método falla, aviso y método «no comprobado»
_orig_diag = cd.glama_cut_diagnosis
cd.glama_cut_diagnosis = lambda h, st=None: {"ok": False, "cut": 254, "sky_pct": 0.4,
                                              "reasons": ["el corte no queda entre un modo oscuro y uno claro"]}
_nw = len([1 for k, v in msgs if k == "warning"])
d._on_glama_cut()
_w = [str(v) for k, v in msgs if k == "warning"][_nw:]
check("0.14.12: corte recomendado no comprobado → aviso y método «no comprobado»",
      d.cut_method == "recomendado (log-normal), no comprobado" and any("no pasó la comprobación" in w for w in _w),
      (d.cut_method, [w[:50] for w in _w]))
cd.glama_cut_diagnosis = _orig_diag
d._on_glama_cut()
d.threshold_spin.setValue(128)
m_adj = d.cut_method
d.threshold_spin.setValue(recs[0]); m_back = d.cut_method
d.threshold_spin.setValue(128)
check("0.14.9: método del corte registrado (recomendado → ajustado a mano → vuelve al recomendado)",
      m_rec == "recomendado (log-normal)" and m_adj == "manual (ajustado desde recomendado (log-normal) = %d)" % recs[0]
      and m_back == "recomendado (log-normal)", (m_rec, m_adj, m_back))

check("botón «Recomendado (log-normal)» y ayuda con procedencia, pasos y referencias",
      d.glama_cut_btn.text() == "Recomendado (log-normal)" and "Implementación independiente" in d.full_help_browser.toPlainText() and "Kittler" in d.full_help_browser.toPlainText()
      and "Recomendado (GLAMA)" not in d.full_help_browser.toPlainText())
# Geometría de pantalla de GLAMA
d.glama_geometry_check.setChecked(True); d._on_run(); rg = d.last_results
check("modo geometría GLAMA: conteos en píxeles de la vista 1080×1836",
      rg["glama_geometry"] is not None and rg["metrics"]["total_pixels_in_frame"] <= 1080 * 1836,
      "CaCo GLAMA-geom = %.2f %% vs correcta %.2f %%" % (rg["metrics"]["canopy_cover_index_pct"],
                                                      rg["glama_geometry"]["correct_caco_pct"]))
check("modo geometría GLAMA avisado en el panel", "GEOMETRÍA DE PANTALLA DE GLAMA" in d.results_text.toPlainText())
d.glama_geometry_check.setChecked(False)

# Calibración con el radio de GLAMA
d.glama_radius_spin.setValue(1618.0); d.glama_side_combo.setCurrentIndex(0); d._on_calibrate_glama_radius()
check("radio GLAMA 1618 → R = 1618·3000/1080", abs(d.calibration["virtual_radius_px"] - 1618 * 3000 / 1080) < 1e-6,
      "%.1f" % d.calibration["virtual_radius_px"])
d.zenith_max.setValue(27.0); d._on_run()
check("análisis con calibración GLAMA", d.last_results["metrics"]["glama_engine"])

# Exportaciones
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "res.csv"), ""))
d._on_export_csv()
rows = list(csv.reader(open(os.path.join(OUT, "res.csv"), encoding="utf-8-sig")))
hdr, row = rows[0], rows[1]
need = ["plugin", "plugin_version", "hemisphere_radius_px", "circle_visible_pct",
        "measurement_mode", "glama_geometry_mode", "exif_orientation"]
check("CSV con columnas nuevas, sin radio equivalente GLAMA", all(c in hdr for c in need)
      and "glama_equivalent_radius_px" not in hdr and row[hdr.index("plugin")] == "CobDosel",
      "%d columnas, %d de sectores" % (len(hdr), len([c for c in hdr if "_S" in c])))
_seen_default = {}
def _fake_save(*a, **k):
    _seen_default["path"] = a[2] if len(a) > 2 else k.get("directory", "")
    return (os.path.join(OUT, "rep.html"), "")
QFileDialog.getSaveFileName = staticmethod(_fake_save)
d._on_export_html()
ht = open(os.path.join(OUT, "rep.html"), encoding="utf-8").read()
_cm = d.last_results.get("cut_method")
import numpy as _np2
from cobdosel import visualization as _vz
_am = d.last_results.get("analysis_area_mask")
_pthr = _vz.render_threshold_overlay(d.image_path, threshold=d.last_results["threshold"], area_mask=_am,
                                     output_path=os.path.join(OUT, "thr_area.png"), apply_cleanup=False)
_im = _np2.asarray(__import__("PIL.Image", fromlist=["Image"]).open(_pthr))
check("0.14.15: superposición de umbral con el área analizada (fuera en verde azulado)",
      _am is not None and (~_am).any() and tuple(_im[0, 0]) != tuple(_im[_im.shape[0] // 2, _im.shape[1] // 2]),
      "fuera = %.1f %%" % (100.0 * (~_am).mean() if _am is not None else -1))
check("0.14.9: método del corte en panel, CSV e informe HTML (%s)" % _cm,
      bool(_cm) and row[hdr.index("cut_level_method")] == _cm and "Método del nivel de corte:" in ht
      and "Método del nivel de corte:" in d.results_text.toPlainText())
check("«Exportar HTML» propone la carpeta de la foto", os.path.dirname(_seen_default.get("path", "")) ==
      os.path.dirname(os.path.abspath(d.last_results["image_path"])), _seen_default.get("path"))
check("informe HTML: «basado en Tichý 2016», sin «método GLAMA» ni «antes CAnOPY»",
      "basado en Tichý 2016" in ht and "método GLAMA" not in ht and "CAnOPY" not in ht)
check("HTML: CobDosel, 2 imágenes, CaCo destacado, sectores",
      ("CobDosel v" + VERSION) in ht and ht.count("data:image/png;base64") == 2 and "caco-box" in ht
      and "por anillo × sector" in ht and "REPORTADOS POR GLAMA" not in ht, d.last_results.get("report_warnings"))
check("HTML sin «Radio equivalente en GLAMA», «por defecto en GLAMA» ni aviso de círculo; filas alineadas a la izquierda",
      "Radio equivalente en GLAMA" not in ht and "por defecto en GLAMA" not in ht and "parcialmente fuera" not in ht
      and "justify-content: flex-start" in ht)
d._on_add_gps_point_layer()
lyr = [l for l in _Proj.instance().layers.values() if isinstance(l, QgsVectorLayer)][0]
check("capa GPS «Puntos CobDosel (GPS)»", lyr.name() == "Puntos CobDosel (GPS)" and len(lyr._p.attrs) == len(lyr._p.feats[0].a),
      "%d campos" % len(lyr._p.attrs))
d._on_add_glama_visualization()
ras = [l for l in _Proj.instance().layers.values() if isinstance(l, QgsRasterLayer)]
check("capa «Anillos cenitales» añadida", len(ras) == 1)
import shutil
shutil.copy(ras[0].p, os.path.join(OUT, "anillos_dialogo.png"))

# Guardar / cargar calibración con trazabilidad y aviso de proporción
QInputDialog.getText = staticmethod(lambda *a, **k: ("Mi teléfono", True))
d.pixel_diameter.setValue(996.0); d.last_measured_pixel_diameter = 996.0; d._measure_info = rec
d._on_calibrate(); d._on_save_calibration()
saved = json.load(open(os.path.join(OUT, "cal", "Mi_teléfono.json"), encoding="utf-8"))
check("calibración guardada con la medición y el tamaño de la foto",
      saved["metadata"]["measurement"]["image_size"] == [4000, 3000] and saved["metadata"]["plugin"] == "CobDosel")
sq = os.path.join(OUT, "cuadrada.png"); Image.fromarray(arr[:2000, :2000]).save(sq)
d._load_image_into_dialog(sq)
QInputDialog.getItem = staticmethod(lambda *a, **k: ("Mi teléfono", True))
n_warn = len([1 for k, v in msgs if k == "warning"])
d._on_load_calibration()
w_new = [v for k, v in msgs if k == "warning"][n_warn:]
check("cargar en foto de otra proporción → aviso", any("Proporción distinta" in str(v) or "proporción" in str(v) for v in w_new),
      str(w_new[:1])[:90])
os.makedirs(cs.LEGACY_DIR, exist_ok=True)
json.dump({"lens_name": "Calibra_Polar", "calibration": dict(saved["calibration"], measurement=None),
           "metadata": {"image_size": [2560, 1920]}}, open(os.path.join(cs.LEGACY_DIR, "Calibra_Polar.json"), "w"))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("Calibra_Polar", True))
n_warn = len([1 for k, v in msgs if k == "warning"])
d._load_image_into_dialog(jpg); d._on_load_calibration()
w_new = [v for k, v in msgs if k == "warning"][n_warn:]
check("calibración antigua de CAnOPY sin trazabilidad → aviso", any("no registra" in str(v) for v in w_new))

_td = {}
def _td_exec(self):
    import numpy as _np
    cv = self.canvas
    _td["alpha0"] = cv.overlay_alpha
    cv.set_highlight_sky(True); light = cv.pixmap().toImage()
    cv.set_highlight_sky(False); dark = cv.pixmap().toImage()
    self.alpha_spin.setValue(40)
    _td["alpha1"] = cv.overlay_alpha
    _td["scroll"] = getattr(cv, "scroll_area", None) is self.scroll
    _td["sizes"] = (light.width(), dark.width())
    _td["labels"] = (self.radio_light.text(), self.radio_dark.text())
    _pm = cv.pixmap()
    _ox = max(0, (cv.width() - _pm.width()) // 2); _oy = max(0, (cv.height() - _pm.height()) // 2)
    _txt = cv.inspect_at(_ox + _pm.width() // 2, _oy + _pm.height() // 2)
    _W, _H = cv.original_pil.size
    _rgb = cv.original_pil.getpixel((_W // 2, _H // 2))
    _td["inspect"] = _txt
    _td["inspect_ok"] = bool(_txt) and "valor" in _txt and ("CIELO" in _txt or "DOSEL" in _txt) \
        and "corte {}".format(cv.threshold) in _txt
    _td["inspect_out"] = cv.inspect_at(-50, -50)
    cv.pixelInspected.emit(_txt or ""); _td["label"] = self.pixel_label.text()
    _codes = [self.auto_method_combo.itemData(i) for i in range(self.auto_method_combo.count())]
    self.auto_method_combo.setCurrentIndex(_codes.index("minimum")); self._on_otsu()
    _td["t_min"] = self.threshold_slider.value(); _td["codes"] = _codes
    return 0
cd.ThresholdDialog.exec = _td_exec
cd.ThresholdDialog.exec_ = _td_exec
d._on_adjust_threshold()
check("vista previa: misma opacidad en Light y Dark (65 %), ajustable (40 %), arrastre conectado",
      abs(_td.get("alpha0", 0) - 0.65) < 1e-9 and abs(_td.get("alpha1", 0) - 0.40) < 1e-9 and _td.get("scroll"), _td)
check("0.14.5: vista previa con modos «Claro» y «Oscuro» y métodos Otsu/Mínimo (Mínimo T = %s)" % _td.get("t_min"),
      _td.get("labels", ("", ""))[0].startswith("Claro") and _td["labels"][1].startswith("Oscuro")
      and _td.get("codes") == ["otsu", "minimum"], _td.get("labels"))
# 0.14.13: corte heredado al cargar otra foto
import shutil as _sh
_jpg2 = os.path.join(OUT, "foto_regular_2.jpg"); _sh.copy(jpg, _jpg2)
_t_prev = d.threshold_spin.value()
d._load_image_into_dialog(_jpg2)
_m_inh = d.cut_method
check("0.14.13: al cargar otra foto el corte queda «heredado»", _m_inh.startswith("heredado"), _m_inh)
_logtxt = d.log_text.toPlainText()
check("0.14.13: aviso en el registro del corte heredado", "heredado de la foto anterior" in _logtxt)
d._on_calibrate(); d._on_run()
_rw = (d.last_results or {}).get("run_warnings") or []
check("0.14.13: ejecutar con corte heredado → aviso en el panel/informe",
      any("no se calculó ni se ajustó para esta foto" in w for w in _rw), [w[:60] for w in _rw])
check("0.14.17: inspector de píxeles en la vista previa (valor, corte, cielo/dosel)",
      _td.get("inspect_ok") and _td.get("inspect_out") is None and _td.get("label") == _td.get("inspect"),
      _td.get("inspect"))
print("\nMensajes no informativos:", [(k, str(v)[:60].replace("\n", " ")) for k, v in msgs if k != "information"])
print("\nRESULTADO: %s" % ("TODAS LAS PRUEBAS PASAN" if not fails else "FALLAN: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
