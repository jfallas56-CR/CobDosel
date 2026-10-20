"""Smoke test headless del lote de CobDosel 0.12.0: diálogo real + stubs de qgis.core.

Uso: python3 -I smoke_batch_v012.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
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
class _Crs:
    def authid(s): return "EPSG:5367"
class _Fld:
    def __init__(s, n): s._n = n
    def name(s): return s._n
class QgsVectorLayer:
    src_feats = []
    def __init__(s, uri, name, prov): s._n = name; s._p = _Prov(); s._src = []
    def crs(s): return _Crs()
    def getFeatures(s): return iter(s._src)
    def name(s): return s._n
    def source(s): return "memory"
    def dataProvider(s): return s._p
    def updateFields(s): pass
    def fields(s): return s._p.attrs if s._p.attrs else [_Fld("id_parc"), _Fld("orden")]
    def updateExtents(s): pass
    def triggerRepaint(s): pass
class QgsFeature:
    def __init__(s, f=None, vals=None): s.fields = f; s._v = vals or {}
    def __getitem__(s, k): return s._v[k]
    def geometry(s): return "geom"
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


import json, csv, shutil
import cobdosel.calibration_store as cs
OUTD = OUT
cs.DEFAULT_DIR = os.path.join(OUTD, "cal"); cs.LEGACY_DIR = os.path.join(OUTD, "cal_old")
from cobdosel import lens_calibration as lc
from cobdosel._version import VERSION
from cobdosel import classFactory
import cobdosel.batch_dialog as bd
fails = []
def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)

class Iface:
    def mainWindow(s): return None
    def addToolBarIcon(s, a): pass
    def addPluginToMenu(s, m, a): s.menus = getattr(s, "menus", []) + [a.text()]
    def removePluginMenu(s, m, a): pass
    def removeToolBarIcon(s, a): pass
iface = Iface()
plug = classFactory(iface); plug.initGui()
check("menú con «Procesamiento por sitio (lote)»", any("lote" in t for t in iface.menus), iface.menus)
cal = lc.calibrate_from_glama_radius(1618, 2560, 1920, scale_side="long")
cal["measurement"] = {"mode": "glama_radius", "image_size": [2560, 1920]}
cs.save_calibration("Pixel10_GLAMA", cal, metadata={"measurement": cal["measurement"]})
# capa de parcelas en el proyecto
src = QgsVectorLayer("Point", "parcelas_hex", "memory")
src._src = [QgsFeature(None, {"id_parc": pid}) for pid in ("1", "2", "4", "5", "9")]
_Proj.instance().addMapLayer(src)
d = bd.CobDoselBatchDialog(iface)
check("título v" + VERSION, d.windowTitle().startswith("CobDosel v" + VERSION))
check("calibración guardada listada", d.cal_combo.findData("Pixel10_GLAMA") >= 0)
check("capa de parcelas listada", d.layer_combo.count() == 2)
d.layer_combo.setCurrentIndex(1)
check("campos de la capa", [d.field_combo.itemText(i) for i in range(d.field_combo.count())] == ["id_parc", "orden"])
check("por defecto: máscara fija 60°", d.mask_fixed_radio.isChecked() and d.fixed_mask_spin.value() == 60.0
      and not d.height_spin.isEnabled())
d.mask_height_radio.setChecked(True)
check("grupo 4 (dosel principal) → 22.5 m", d.group_combo.currentData() == 4 and d.height_spin.value() == 22.5
      and d.height_spin.isReadOnly(), d.mask_info.text())
d.group_combo.setCurrentIndex(d.group_combo.findData(5))
check("grupo 5 (emergentes) → 30 m", d.height_spin.value() == 30.0)
d.group_combo.setCurrentIndex(0)
d.height_spin.setValue(21.3)
check("altura a mano 21.3 m → máscara 72.5°", "72.5" in d.mask_info.text() and not d.height_spin.isReadOnly(),
      d.mask_info.text())
d.site_edit.setText("Sitio prueba")
shutil.copytree(os.path.join(sys.argv[4], "fotos"), os.path.join(OUTD, "fotos_sitio"))
d.folder_edit.setText(os.path.join(OUTD, "fotos_sitio")); d.form_edit.setText(os.path.join(sys.argv[4], "formulario.xlsx"))
d._on_run()
check("sin parcelas planificadas → aviso y no procesa", d.batch is None and msgs and "planificadas" in str(msgs[-1][1]))
d.planned_spin.setValue(4)
d.cal_combo.setCurrentIndex(d.cal_combo.findData("Pixel10_GLAMA"))
d.channel_combo.setCurrentIndex(d.channel_combo.findData("blue_red"))
d._on_run()
b = d.batch
check("lote procesado desde el diálogo", b is not None and b["sitio"]["parcelas_con_resultado"] == 4,
      "CaCo sitio %.2f %%" % b["sitio"]["caco_sitio"])
txt = d.out.toPlainText()
check("panel: media del sitio, criterio, parcelas y avisos", "Cobertura del dosel del sitio" in txt and
      "Criterio de cobertura" not in txt and "70 %" not in txt and "reemplazo de 3" in txt and "AVISOS" in txt)
check("información de la calibración visible", "R = " in d.cal_info.text() and "cámara" in d.cal_info.text(),
      d.cal_info.text())
# ---- Revisión visual de cortes ----
check("botón «Revisar cortes…» habilitado tras procesar", d.review_btn.isEnabled())
pend_before = b["sitio"]["pendientes_revision"]
print("    pendientes antes de revisar:", pend_before, "|", b["sitio"]["revision"])
import cobdosel.cut_review_dialog as crd
seen = {}
def _fake_exec(dlg):
    seen["n_items"] = len(dlg.items)
    seen["pending0"] = dlg.pending_count()
    dlg._load(0)
    seen["pix"] = dlg.view._item is not None and not dlg.view._item.pixmap().isNull()
    seen["caco_txt"] = dlg.caco_label.text()
    seen["auto0"] = dlg.items[0].get("corte_auto")
    dlg.spin.setValue(int(dlg.spin.value()) + 15); dlg._render()
    seen["arch_adj"] = dlg.items[dlg.idx]["archivo"]; dlg.note_edit.setText("ajuste visual")
    dlg.operator_edit.setText("JF")
    dlg._on_accept()
    seen["arch_exc"] = dlg.items[dlg.idx]["archivo"]
    dlg.note_edit.setText("tronco cercano"); dlg._on_exclude()
    for i, it in enumerate(dlg.items):
        if dlg._pending(it):
            dlg._load(i); dlg._on_accept()
    dlg._on_accept_all()
    seen["pending_end"] = dlg.pending_count()
    seen["dec"] = dlg.get_decisions()
    return 1
crd.CutReviewDialog.exec = _fake_exec
crd.CutReviewDialog.exec_ = _fake_exec
d._on_review()
check("ventana de revisión: fotos cargadas, imagen y CaCo en vivo", seen.get("n_items", 0) >= 15 and seen.get("pix")
      and "CaCo de esta foto" in seen.get("caco_txt", ""), seen.get("caco_txt"))
check("decisiones registradas: ajustado (+15), excluido, pendientes decididas",
      seen["dec"][seen["arch_adj"]]["decision"] == "ajustado" and seen["dec"][seen["arch_exc"]]["decision"] == "excluido"
      and seen["pending_end"] == 0 and seen["dec"][seen["arch_adj"]]["operador"] == "JF", seen["dec"].get(seen["arch_adj"]))
jf = os.path.join(OUTD, "fotos_sitio", "CobDosel_revision_cortes.json")
check("decisiones guardadas junto a las fotos", os.path.isfile(jf) and len(json.load(open(jf, encoding="utf-8"))["fotos"]) == len(seen["dec"]))
b2 = d.batch
by2 = {r["archivo"]: r for r in b2["fotos"] if r.get("archivo")}
check("lote recalculado con las decisiones: ajustada, excluida, sin pendientes",
      by2[seen["arch_adj"]]["decision"].startswith("ajustado") and not by2[seen["arch_exc"]]["valida"]
      and b2["sitio"]["pendientes_revision"] == 0, b2["sitio"]["revision"])
check("panel con el resumen del nivel de corte", "Nivel de corte: " in d.out.toPlainText() and "ajustada" in d.out.toPlainText())
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUTD, "lote.csv"), ""))
d._on_csv()
check("CSV del lote", all(os.path.isfile(os.path.join(OUTD, "lote_" + x + ".csv")) for x in ("fotos", "parcelas", "sitio")))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUTD, "lote.html"), ""))
d._on_html()
check("HTML del lote", os.path.isfile(os.path.join(OUTD, "lote.html")))
htxt = open(os.path.join(OUTD, "lote.html"), encoding="utf-8").read()
check("HTML del lote sin umbral ni referencias legales", "70 %" not in htxt and "7575" not in htxt and "Cumple" not in htxt)
QInputDialog.getInt = staticmethod(lambda *a, **k: (5, True))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUTD, "prellenado.xlsx"), ""))
_prev_form = d.form_edit.text()
d._draft_form()
check("«Crear formulario desde las fotos…» crea el archivo y lo selecciona",
      os.path.isfile(os.path.join(OUTD, "prellenado.xlsx")) and d.form_edit.text().endswith("prellenado.xlsx"))
d.form_edit.setText(_prev_form)
check("salidas por defecto en la carpeta de fotos", d._default_output(".html") == os.path.join(
      d.folder_edit.text(), "CobDosel_Sitio_prueba_sitio.html"), d._default_output(".html"))
# Registrar cámara en una calibración sin huella
from PIL import Image as _Im
camdir = os.path.join(OUTD, "fotos_cam"); os.makedirs(camdir, exist_ok=True)
for i in range(2):
    im = _Im.new("RGB", (640, 480), (120, 140, 200)); e = im.getexif()
    e[0x010F] = "Google"; e[0x0110] = "Pixel 10"; e[0x920A] = 4.53
    im.save(os.path.join(camdir, "GLAMA_%d.jpg" % i), exif=e)
_prev_folder = d.folder_edit.text(); d.folder_edit.setText(camdir)
d.cal_combo.setCurrentIndex(d.cal_combo.findData("Pixel10_GLAMA"))
check("calibración sin cámara → «Registrar cámara…» habilitado", d.cam_btn.isEnabled())
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
d._register_camera()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
calr = cs.load_calibration("Pixel10_GLAMA")
check("cámara registrada en la calibración (Pixel 10, 4.53 mm, tamaño de la calibración)",
      calr.get("camera", {}).get("model") == "Pixel 10" and calr["camera"]["size"] == [2560, 1920]
      and not d.cam_btn.isEnabled(), d.cal_info.text())
d.folder_edit.setText(_prev_folder)
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUTD, "plantilla.xlsx"), ""))
d._save_template()
check("plantilla del Formulario 8 guardada", os.path.isfile(os.path.join(OUTD, "plantilla.xlsx")))
d.field_combo.setCurrentIndex(0)
d._on_layer()
outl = [l for l in _Proj.instance().layers.values() if isinstance(l, QgsVectorLayer) and l.name().startswith("CobDosel")]
check("capa de parcelas unida por ID (4 de 4; P9 sin datos)", len(outl) == 1 and len(outl[0]._p.feats) == 4
      and "4 parcelas unidas" in str(msgs[-1][1]), str(msgs[-1][1]))
plug.unload()
print("\nRESULTADO: %s" % ("TODAS LAS PRUEBAS PASAN" if not fails else "FALLAN: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
