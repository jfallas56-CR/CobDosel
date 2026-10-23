"""Prueba headless v0.14.31: zoom por rectángulo, zoom escrito, Ctrl+rueda y memoria.

Uso: python3 -I test_zoom_v01431.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, types, os, importlib, resource
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1]); OUT = sys.argv[2]; QT = sys.argv[3]
os.makedirs(OUT, exist_ok=True)
QtCore = importlib.import_module(QT + ".QtCore"); QtGui = importlib.import_module(QT + ".QtGui")
QtWidgets = importlib.import_module(QT + ".QtWidgets"); QtTest = importlib.import_module(QT + ".QtTest")
q = types.ModuleType("qgis"); qp = types.ModuleType("qgis.PyQt")
sys.modules.update({"qgis": q, "qgis.PyQt": qp, "qgis.PyQt.QtCore": QtCore,
                    "qgis.PyQt.QtGui": QtGui, "qgis.PyQt.QtWidgets": QtWidgets})
core = types.ModuleType("qgis.core")
for n in ("QgsProject", "QgsVectorLayer", "QgsRasterLayer", "QgsMessageLog", "Qgis", "QgsField",
          "QgsFeature", "QgsGeometry", "QgsPointXY"):
    setattr(core, n, type(n, (), {}))
sys.modules["qgis.core"] = core
from PIL import Image, ImageDraw
import numpy as np
Qt = QtCore.Qt
app = QtWidgets.QApplication([])
from cobdosel.measure_circle_dialog import MeasureCircleDialog, MAX_SCALE, MIN_SCALE
from cobdosel import threshold_dialog as TD

ok = []
def check(name, cond, info=""):
    ok.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name + ("  " + str(info) if info else ""))

# Foto sintética 4000x3000 con un círculo y un punto rojo marcador en (3000, 700)
img = Image.new("RGB", (4000, 3000), (240, 240, 240))
d = ImageDraw.Draw(img)
d.ellipse((1000, 500, 3000, 2500), outline=(0, 0, 0), width=6)
d.rectangle((2995, 695, 3005, 705), fill=(255, 0, 0))
path = os.path.join(OUT, "sint.jpg"); img.save(path, quality=95)

dlg = MeasureCircleDialog(path); dlg.resize(1000, 750); dlg.show(); app.processEvents()
cv = dlg.canvas
check("1 abre ajustado a ventana", cv.fit_mode and cv.display_scale < 0.3, round(cv.display_scale, 3))
check("2 caja de zoom muestra el % ajustado", dlg.zoom_spin.value() == round(cv.display_scale * 100), dlg.zoom_spin.value())

# Zoom escrito: 150 %
dlg.zoom_spin.setValue(150); app.processEvents()
check("3 zoom escrito 150 % aplicado", abs(cv.display_scale - 1.5) < 1e-6 and not cv.fit_mode, cv.display_scale)
check("4 lienzo = 6000x4500 px", (cv.width(), cv.height()) == (6000, 4500), (cv.width(), cv.height()))
cx, cy = cv.view_center()
check("5 zoom escrito mantiene el centro", abs(cx - 2000) < 30 and abs(cy - 1500) < 30, (round(cx), round(cy)))
dlg.zoom_spin.setValue(5000)
check("6 límite máximo {} %".format(int(MAX_SCALE * 100)), dlg.zoom_spin.value() == int(MAX_SCALE * 100))
app.processEvents()
check("7 escala máxima = 8.0", abs(cv.display_scale - MAX_SCALE) < 1e-6, cv.display_scale)

# Memoria: a 800 % no se crea una copia gigante (32000x24000)
check("8 sin caché a >100 %", cv._cache_pix is None)
rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
cv.repaint(); app.processEvents()
rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
check("9 repintar a 800 % sin pico de memoria (< 100 MB)", (rss1 - rss0) / 1024 < 100, "{:.0f} MB".format((rss1 - rss0) / 1024))

# Ajustar y luego rectángulo con botón derecho alrededor del punto rojo
dlg._on_zoom_reset(); app.processEvents()
s = cv.display_scale
x0, y0 = int(2900 * s), int(600 * s); x1, y1 = int(3100 * s), int(800 * s)
QtTest.QTest.mousePress(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(x0, y0))
ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(x1, y1), QtCore.QPointF(x1, y1),
                       Qt.MouseButton.NoButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
app.sendEvent(cv, ev)
QtTest.QTest.mouseRelease(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(x1, y1))
app.processEvents()
vp = dlg.scroll.viewport()
exp = min((vp.width() - 4) / ((x1 - x0 + 1) / s), (vp.height() - 4) / ((y1 - y0 + 1) / s))   # QRect incluye ambos extremos
check("10 rectángulo (botón derecho) amplía", abs(cv.display_scale - min(exp, MAX_SCALE)) < 0.02, (round(cv.display_scale, 2), round(exp, 2), vp.width(), vp.height(), dlg.scroll.verticalScrollBar().isVisible()))
cx, cy = cv.view_center()
check("11 rectángulo queda centrado", abs(cx - 3000) < 15 and abs(cy - 700) < 15, (round(cx), round(cy)))
check("12 no añadió puntos", cv.points == [])
check("13 caja de zoom actualizada", dlg.zoom_spin.value() == round(cv.display_scale * 100), dlg.zoom_spin.value())
# El punto rojo se ve en el centro de la ventana
grab = dlg.scroll.viewport().grab().toImage()
c = QtGui.QColor(grab.pixel(vp.width() // 2, vp.height() // 2))
check("14 punto rojo visible en el centro", c.red() > 200 and c.green() < 80, (c.red(), c.green(), c.blue()))
grab.save(os.path.join(OUT, "zoom_rect.png"))

# Clic izquierdo tras el zoom: coordenadas correctas en la foto
QtTest.QTest.mouseClick(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                        QtCore.QPoint(int(3000 * cv.display_scale), int(700 * cv.display_scale)))
check("15 clic tras zoom marca (3000, 700)", len(cv.points) == 1 and abs(cv.points[0][0] - 3000) < 1 and abs(cv.points[0][1] - 700) < 1, cv.points)

# Mayús + izquierdo también hace rectángulo y no añade punto
dlg._on_zoom_reset(); app.processEvents(); s = cv.display_scale
QtTest.QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QtCore.QPoint(int(1000 * s), int(500 * s)))
QtTest.QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QtCore.QPoint(int(1400 * s), int(800 * s)))
app.processEvents()
vp = dlg.scroll.viewport()
_w = (int(1400 * s) - int(1000 * s) + 1) / s; _h = (int(800 * s) - int(500 * s) + 1) / s     # QRect incluye ambos extremos
exp16 = min((vp.width() - 4) / _w, (vp.height() - 4) / _h)
check("16 Mayús + arrastrar amplía sin marcar punto", abs(cv.display_scale - exp16) < 0.02 and len(cv.points) == 1, (round(cv.display_scale, 2), round(exp16, 2)))
# Rectángulo minúsculo (clic accidental) se ignora
sc_before = cv.display_scale
QtTest.QTest.mousePress(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(50, 50))
QtTest.QTest.mouseRelease(cv, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(52, 52))
check("17 clic derecho sin arrastrar no cambia el zoom", cv.display_scale == sc_before)

# Ajustar a ventana sigue el tamaño de la ventana; zoom fijo no
dlg._on_zoom_reset(); app.processEvents(); f1 = cv.display_scale
dlg.resize(1400, 1000); app.processEvents()
check("18 ajustado sigue a la ventana", cv.display_scale > f1, (round(f1, 3), round(cv.display_scale, 3)))
dlg.zoom_spin.setValue(100); app.processEvents(); dlg.resize(900, 700); app.processEvents()
check("19 zoom fijo se conserva al redimensionar", abs(cv.display_scale - 1.0) < 1e-6)

# Medición sin cambios a distinto zoom (4 puntos de la cruz)
cv.points = []
for sc in (0.2, 2.0):
    cv.points = []; dlg._set_zoom_pct(int(sc * 100)); app.processEvents()
    for (x, y) in ((1003, 1500), (2997, 1500), (2000, 503), (2000, 2497)):
        cv.points.append((x, y))
    dlg._on_points_changed(cv.points)
    check("20 diámetro igual a {} %".format(int(sc * 100)), dlg.get_pixel_diameter() is not None and abs(dlg.get_pixel_diameter() - 1994) < 1, dlg.get_pixel_diameter())

# Ctrl + rueda centrada en el puntero
dlg._set_zoom_pct(100); app.processEvents()
cv.center_on(2000, 1500); app.processEvents()
p = QtCore.QPointF(2000 + 100, 1500 + 50)  # punto (2100, 1550) de la foto
old_vx = p.x() + cv.x()
we = QtGui.QWheelEvent(p, QtCore.QPointF(cv.mapToGlobal(p.toPoint())), QtCore.QPoint(0, 0), QtCore.QPoint(0, 120), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
app.sendEvent(cv, we); app.processEvents()
new_vx = 2100 * cv.display_scale + cv.x()
check("21 Ctrl+rueda acerca y mantiene el punto bajo el puntero", cv.display_scale > 1.1 and abs(new_vx - old_vx) < 2, (round(cv.display_scale, 3), round(old_vx), round(new_vx)))

# ---- Ventana de umbral: caja de zoom y rectángulo
td_ok = hasattr(TD, "ThresholdPreviewCanvas")
cvT = TD.ThresholdPreviewCanvas(); area = QtWidgets.QScrollArea(); area.setWidgetResizable(True)
area.setWidget(cvT); cvT.scroll_area = area; area.resize(800, 600); area.show()
arr = np.array(img)
cvT.set_image(img, valid_mask=None); app.processEvents()
cvT.fit_to_viewport(area.viewport().width(), area.viewport().height()); app.processEvents()
z0 = cvT.zoom; dw, dh = cvT.display_pil.size
k = dw / 4000.0
x0, y0, x1, y1 = [int(v * k * z0) for v in (2900, 600, 3100, 800)]
QtTest.QTest.mousePress(cvT, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(x0 + cvT._offset()[0], y0 + cvT._offset()[1]))
QtTest.QTest.mouseRelease(cvT, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QtCore.QPoint(x1 + cvT._offset()[0], y1 + cvT._offset()[1]))
app.processEvents()
check("22 umbral: rectángulo amplía", cvT.zoom > z0 * 2, (round(z0, 3), round(cvT.zoom, 3)))
cxT = (area.horizontalScrollBar().value() + area.viewport().width() / 2.0 - cvT._offset()[0]) / cvT.zoom / k
cyT = (area.verticalScrollBar().value() + area.viewport().height() / 2.0 - cvT._offset()[1]) / cvT.zoom / k
check("23 umbral: rectángulo centrado", abs(cxT - 3000) < 40 and abs(cyT - 700) < 40, (round(cxT), round(cyT)))

n = sum(ok); print("\n{}/{} comprobaciones correctas ({})".format(n, len(ok), QT))
sys.exit(0 if n == len(ok) else 1)
