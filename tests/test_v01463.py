"""CobDosel 0.14.63: (1) se retiran la calibración con el radio de GLAMA, la geometría de pantalla de GLAMA y
«Comparar con GLAMA (tabla)»; (2) CSV con «;» y coma decimal donde la coma es decimal; (3) informe del sitio
sin el cielo no uniforme ni «Resultado provisional» repetidos en «Avisos», pie con contacto; (4) sin «⚠».

Uso: python3 -I test_v01463.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, csv, glob, re
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PKG = os.path.join(sys.argv[1], "cobdosel")

from cobdosel import batch_core as bc, lens_calibration as lc, glama_engine as ge, exif_gps  # noqa: E402
from cobdosel.csv_format import csv_cell, csv_row, csv_style  # noqa: E402
import tests._cal_fixtures as _fx  # noqa: E402

fails = []


def chk(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info)[:300] + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


src = {os.path.basename(p): open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(PKG, "*.py"))}

# 1) Funciones retiradas
chk("1 sin glama_compare.py ni glama_compare_dialog.py",
    "glama_compare.py" not in src and "glama_compare_dialog.py" not in src)
chk("1 lens_calibration sin calibración con radio de GLAMA ni cenit real",
    not any(hasattr(lc, a) for a in ("calibrate_from_glama_radius", "glama_equivalent_radius", "GLAMA_VIEW_WIDTH_PX",
                                     "true_zenith_of", "calibration_zenith_for_true")))
chk("1 glama_engine sin vista de pantalla de GLAMA",
    not any(hasattr(ge, a) for a in ("glama_view_image", "glama_rotate", "glama_boxes_label", "glama_screen_indices",
                                     "GLAMA_VIEW_W", "GLAMA_CENTER_DY")))
chk("1 exif_gps sin carga en orden guardado", not hasattr(exif_gps, "load_stored_rgb_image"))
dlg = src["canopy_dialog.py"]
chk("1 ventana principal sin los controles retirados",
    not any(k in dlg for k in ('QPushButton("Calibrar con radio GLAMA")', "Opcional — radio de la app GLAMA",
                               "Reproducir la geometría de pantalla", 'QPushButton("Comparar con GLAMA (tabla)…")',
                               "glama_geometry_check", "glama_radius_spin", "glama_stored_check", "GlamaCompareDialog")))
chk("1 CSV de una foto y capa sin columnas de la geometría de GLAMA",
    "glama_geometry_mode" not in dlg and "caco_correct_geometry_pct" not in dlg and '"geom_glama"' not in dlg)
helps = src["help_texts.py"]
chk("1 ayuda sin las funciones retiradas",
    "Comparar con GLAMA (tabla)" not in helps and "Geometría de pantalla de GLAMA:" not in helps
    and "<b>Radio de GLAMA:</b>" not in helps, "")
chk("1 informe de una foto sin banda de geometría de GLAMA", "geometry_banner" not in src["html_report.py"])

# Calibración antigua con el radio de GLAMA: se lee, con aviso en el lote
legacy = _fx.lineal_cal(1618, 2560, 1920, legacy=True)
chk("1 aviso de calibración retirada definido", "función retirada" in bc.GLAMA_RADIUS_WARNING
    and "círculo D/H" in bc.GLAMA_RADIUS_WARNING and not hasattr(bc, "LONG_SIDE_WARNING"))
chk("1 lote: aviso solo con calibration_method = glama_radius",
    'if calibration.get("calibration_method") == "glama_radius":' in src["batch_core.py"]
    and legacy["calibration_method"] == "glama_radius")
chk("1 resumen de la calibración antigua en la ventana: aviso", "función retirada en v0.14.63" in dlg)

# 2) CSV para Excel
chk("2 csv_cell: real con coma decimal", csv_cell(79.18, ",") == "79,18" and csv_cell(79.18, ".") == "79.18")
chk("2 csv_cell: enteros, booleanos, None y texto sin cambio",
    csv_cell(5, ",") == 5 and csv_cell(True, ",") is True and csv_cell(None, ",") == "No aplica"
    and csv_cell("0.14.63", ",") == "0.14.63")
import numpy as np  # noqa: E402
chk("2 csv_cell: numpy float y int", csv_cell(np.float64(70.01), ",") == "70,01" and csv_cell(np.int64(3), ",") == 3)
chk("2 csv_style sin Qt: formato internacional", csv_style() in ((",", "."), (";", ",")), csv_style())

DATA = {"1": [62.45, 80.29, 75.5, 65.35, 85.24], "2": [90.89, 78.32, 71.33, 87.45, 88.57]}
fotos = []
for p, vals in DATA.items():
    for k, v in enumerate(vals):
        fotos.append({"parcela": p, "punto": "P%d" % k, "archivo": "f%s_%d.jpg" % (p, k), "valida": True,
                      "emparejado_por": "id", "caco": v, "decision": "automático", "reemplaza_a": "",
                      "motivo": "a; b", "cielo_rango": 3.0})
agg = bc.aggregate(fotos, 2)
batch = dict(agg); batch["fotos"] = fotos; batch["parametros"] = {"mascara": 63.0, "sitio": "Prueba", "analista": "JF"}
paths = bc.write_csvs(batch, os.path.join(OUT, "es"), "0.14.63", delimiter=";", decimal=",")
rows = list(csv.reader(open(paths[0], encoding="utf-8-sig"), delimiter=";"))
h = rows[0]
chk("2 _fotos.csv con «;»: mismas columnas que antes", h == list(bc.PHOTO_CSV_COLUMNS), len(h))
chk("2 _fotos.csv: CaCo con coma decimal", rows[1][h.index("caco")] == "62,45", rows[1][h.index("caco")])
chk("2 _fotos.csv: texto con «;» entre comillas, leído entero", rows[1][h.index("motivo")] == "a; b")
site = list(csv.reader(open(paths[2], encoding="utf-8-sig"), delimiter=";"))
sh = site[0]
chk("2 _sitio.csv: caco_sitio 78,54 (785,39 / 10) y versión intacta",
    site[1][sh.index("caco_sitio")] == "78,54" and site[1][sh.index("plugin_version")] == "0.14.63",
    (site[1][sh.index("caco_sitio")], site[1][sh.index("plugin_version")]))
chk("2 _sitio.csv: parámetro real con coma (63,0)", site[1][sh.index("param_mascara")] == "63,0")
paths2 = bc.write_csvs(batch, os.path.join(OUT, "en"), "0.14.63")
chk("2 por defecto: «,» y punto (sin cambio para otros programas)",
    open(paths2[1], encoding="utf-8-sig").read().splitlines()[1].startswith("1,No aplica,5,5,73.77"),
    open(paths2[1], encoding="utf-8-sig").read().splitlines()[1])
chk("2 ventana del lote y de una foto usan csv_style",
    "delimiter=sep, decimal=dec" in src["batch_dialog.py"] and "w.writerow(csv_row(row, dec))" in dlg
    and "draft_form_from_photos(folder, dst, n, delimiter=csv_style()[0])" in src["batch_dialog.py"])
from PIL import Image  # noqa: E402
pf = os.path.join(OUT, "fotos"); os.makedirs(pf, exist_ok=True)
for k in range(3):
    Image.new("RGB", (64, 48), (90, 120, 200)).save(os.path.join(pf, "F%02d.jpg" % k))
dp = os.path.join(OUT, "form.csv")
_out, _n, _w = bc.draft_form_from_photos(pf, dp, 5, delimiter=";")
recs, _ww = bc.read_field_form(dp)
chk("2 formulario CSV con «;» se vuelve a leer", open(dp, encoding="utf-8-sig").readline().count(";") >= 5
    and len(recs) == 3, len(recs))

# 3) Avisos sin repeticiones; pie con contacto
fotos[0]["cielo_rango"] = 67.0; fotos[0]["decision"] = "aceptado"; fotos[0]["analista"] = "JF"
fotos[1]["revisar"] = True; fotos[1]["decision"] = "pendiente de revisión"
agg = bc.aggregate(fotos, 2)
common = bc.summarize_common_warnings(fotos)
chk("3 el cielo no uniforme no está en los avisos", not [w for w in common if "cielo no uniforme" in w], common)
chk("3 «Resultado provisional» no está en los avisos", not [w for w in agg["avisos"] if "provisional" in w.lower()],
    agg["avisos"])
batch = dict(agg); batch["fotos"] = fotos; batch["parametros"] = {"analista": "JF"}
batch["avisos"] = common + agg["avisos"]
hp = os.path.join(OUT, "informe.html")
bc.write_html(batch, hp, "0.14.63", "Prueba")
ht = open(hp, encoding="utf-8").read()
txt = re.sub(r"<[^>]+>", " ", ht)
chk("3 cielo no uniforme: una sola vez, con el rango", txt.count("cielo no uniforme (rango de brillo del cielo 67") == 1,
    txt.count("cielo no uniforme"))
chk("3 «Resultado provisional»: una sola vez, en singular", txt.count("Resultado provisional") == 1
    and "1 foto pendiente de revisión" in txt and "foto(s)" not in txt)
chk("3 pie con contacto (v0.14.69: igual al de una foto)",
    "<strong>CobDosel v0.14.63</strong> para QGIS · Autor: Jorge Fallas · Contacto:" in ht and 'mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></footer>' in ht)
lis = re.findall(r"<li>(.*?)</li>", ht.split("<h2>Avisos</h2>")[1].split("</section>")[0])
chk("3 avisos sin textos duplicados", len(lis) == len(set(lis)), lis)

# 4) Sin «⚠» en textos del complemento (solo en un comentario que explica por qué no se usa)
hits = []
for name, s in src.items():
    for i, line in enumerate(s.splitlines(), 1):
        if "⚠" in line and not line.strip().startswith("#"):
            hits.append("%s:%d" % (name, i))
chk("4 sin «⚠» en el complemento", not hits, hits)
chk("4 sin «⚠» en el informe del sitio", "⚠" not in ht)

print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
