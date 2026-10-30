"""CobDosel 0.14.70: sin Índice CaCo modificado en las salidas; «Sí»/«No» en los CSV; cielo_rango sin medir →
«Sin cielo suficiente»; nota «cielo fragmentado» cuando hay cielo pero no núcleo para medir su uniformidad.

Uso: python3 -I test_v01470.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, csv, glob
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
import numpy as np  # noqa: E402
from cobdosel import batch_core as bc  # noqa: E402
from cobdosel.csv_format import csv_cell  # noqa: E402
from cobdosel.canopy_analysis import sky_fragmented, sky_uniformity_range, SKY_NOT_MEASURED  # noqa: E402

fails = []


def chk(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info)[:300] + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


PKG = os.path.join(sys.argv[1], "cobdosel")
src = {os.path.basename(p): open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(PKG, "*.py"))}
# 1) sin CaCo modificado en las salidas
chk("1 panel, informe, CSV de una foto y capa sin CaCo modificado",
    "Índice CaCo Modificado" not in src["canopy_dialog.py"] and "modified_caco_index_pct\"," not in src["canopy_dialog.py"]
    and 'QgsField("mod_caco"' not in src["canopy_dialog.py"] and "Índice CaCo modificado" not in src["html_report.py"]
    and "Modif.CaCo" not in src["canopy_dialog.py"])
chk("1 lote: sin modif_caco en el CSV de fotos", "modif_caco" not in bc.PHOTO_CSV_COLUMNS)
chk("1 ayuda sin el índice modificado", "Modificado" not in src["help_texts.py"])
# 2) Sí / No
chk("2 csv_cell: True → «Sí», False → «No», numpy bool también",
    csv_cell(True) == "Sí" and csv_cell(False) == "No" and csv_cell(np.bool_(True)) == "Sí" and csv_cell(1) == 1)
# 3) cielo sin medir y cielo fragmentado
chk("3 sky_fragmented: sin rango y 30 % de cielo → True", sky_fragmented(None, 300, 1000))
chk("3 sky_fragmented: sin rango y 3 % de cielo (dosel cerrado) → False", not sky_fragmented(None, 30, 1000))
chk("3 sky_fragmented: con rango → False", not sky_fragmented(12.0, 300, 1000))
# cielo de claros pequeños repartidos: mucho cielo, sin núcleo (en la primera versión de la prueba, 8 % de cielo)
g = np.full((400, 400), 60, np.uint8); m = np.zeros((400, 400), bool)
m[::4, ::4] = True
m = m | np.roll(m, 1, 0)
m = m | np.roll(m, 1, 1)                     # claros de 2×2 px cada 4 px: 25 % de cielo, sin núcleo
g[m] = 220
area = np.ones_like(m)
r = sky_uniformity_range(g, m, area)
chk("3 claros de 2 px: rango sin medir y cielo fragmentado", r is None and sky_fragmented(r, m.sum(), area.sum()),
    (r, round(100.0 * m.sum() / area.sum(), 1)))
fotos = [{"parcela": "1", "punto": "x", "archivo": "a.jpg", "valida": True, "emparejado_por": "id", "caco": 56.47,
          "cielo_rango": None, "decision": "automático", "reemplaza_a": ""},
         {"parcela": "1", "punto": "y", "archivo": "b.jpg", "valida": True, "emparejado_por": "id", "caco": 80.0,
          "cielo_rango": 12.0, "decision": "automático", "reemplaza_a": ""},
         {"parcela": "2", "punto": "z", "archivo": "", "valida": False, "emparejado_por": "", "caco": None,
          "cielo_rango": None, "decision": "", "reemplaza_a": ""}]
agg = bc.aggregate(fotos, 2)
batch = dict(agg); batch["fotos"] = fotos; batch["parametros"] = {"sitio": "Prueba"}
paths = bc.write_csvs(batch, os.path.join(OUT, "P"), "0.14.70")
rows = list(csv.DictReader(open(paths[0], encoding="utf-8-sig")))
chk("3 CSV: cielo_rango sin medir → «Sin cielo suficiente»; medido → número; sin foto → «No aplica»",
    rows[0]["cielo_rango"] == SKY_NOT_MEASURED and rows[1]["cielo_rango"] == "12.0" and rows[2]["cielo_rango"] == "No aplica",
    [r["cielo_rango"] for r in rows])
chk("2 CSV de fotos: valida «Sí»/«No»", rows[0]["valida"] == "Sí" and rows[2]["valida"] == "No", [r["valida"] for r in rows])
site = list(csv.DictReader(open(paths[2], encoding="utf-8-sig")))[0]
chk("2 CSV del sitio: completo «Sí»/«No»", site["completo"] in ("Sí", "No"), site["completo"])
core = src["batch_core.py"]
chk("3 lote: nota de cielo fragmentado en la foto (sin dejarla «a revisar»)",
    "warns.append(SKY_FRAGMENTED_NOTE)" in core and "sky_fragmented(sky_range" in core)
chk("3 una foto: aviso de cielo fragmentado en el panel y el informe", "elif sky_frag:" in src["canopy_dialog.py"])
print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
