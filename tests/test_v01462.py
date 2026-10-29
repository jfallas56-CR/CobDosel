"""CobDosel 0.14.62: CaCo de cada foto con 2 decimales; resultado del sitio = media de todas las fotos válidas
(no media de las medias de parcela), con 2 decimales y redondeo a la mitad hacia arriba.

Datos reales de 4 parcelas × 5 fotos (J. Fallas, 2026-10-29).

Uso: python3 -I test_v01462.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, csv
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

from cobdosel import batch_core as bc  # noqa: E402

fails = []


def check(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info) + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


DATA = {"1": [62.45, 80.29, 75.5, 65.35, 85.24], "2": [90.89, 78.32, 71.33, 87.45, 88.57],
        "3": [68.63, 75.27, 84.3, 83.15, 84.32], "4": [65.23, 78.45, 85.49, 84.21, 89.14]}
PTS = ["Centro", "N-O", "N-E", "S-O", "S-E"]


def rows(data, invalid=()):
    out = []
    for p, vals in data.items():
        for k, v in enumerate(vals):
            ok = (p, k) not in invalid
            out.append({"parcela": p, "punto": PTS[k], "archivo": "f{}_{}.jpg".format(p, k), "valida": ok, "emparejado_por": "id",
                        "caco": v if ok else None, "decision": "automático", "reemplaza_a": ""})
    return out


# 1) Datos reales: medias de parcela y del sitio
agg = bc.aggregate(rows(DATA), 4)
pm = {d["parcela"]: d["caco_media"] for d in agg["parcelas"]}
check("medias de parcela 73.77 / 83.31 / 79.13 / 80.50", pm == {"1": 73.77, "2": 83.31, "3": 79.13, "4": 80.50}, pm)
check("sitio = 79.18 (media de las 20 fotos)", agg["sitio"]["caco_sitio"] == 79.18, agg["sitio"]["caco_sitio"])
check("20 fotos válidas", agg["sitio"]["fotos_validas"] == 20)

# 2) Parcela con 3 fotos válidas: el sitio es la media de las 18 fotos, no la media de las medias
inv = {("1", 1), ("1", 4)}            # parcela 1 sin N-O (80.29) ni S-E (85.24)
agg2 = bc.aggregate(rows(DATA, inv), 4)
vals18 = [v for p, vs in DATA.items() for k, v in enumerate(vs) if (p, k) not in inv]
exp18 = bc.mean_pct(vals18)
pm2 = [d["caco_media"] for d in agg2["parcelas"]]
mean_of_means = bc.mean_pct(pm2)
check("parcela 1 con 3 fotos: media 67.77", agg2["parcelas"][0]["caco_media"] == 67.77 and agg2["parcelas"][0]["validas"] == 3,
      agg2["parcelas"][0]["caco_media"])
check("sitio con 18 fotos = media de las 18 (1418.05 / 18 = 78.78)", agg2["sitio"]["caco_sitio"] == exp18 == 78.78, agg2["sitio"]["caco_sitio"])
check("con fotos inválidas difiere de la media de medias (77.68)",
      mean_of_means == 77.68 and agg2["sitio"]["caco_sitio"] != mean_of_means, mean_of_means)

# 3) Quitar las 3 fotos ≥ 88.57 (90.89, 88.57, 89.14): 77.35
inv3 = {("2", 0), ("2", 4), ("4", 4)}
agg3 = bc.aggregate(rows(DATA, inv3), 4)
check("sin las 3 fotos ≥ 88.57: sitio 77.35 (17 fotos)",
      agg3["sitio"]["caco_sitio"] == 77.35 and agg3["sitio"]["fotos_validas"] == 17, agg3["sitio"]["caco_sitio"])

# 4) Redondeo: a la mitad hacia arriba, en decimal exacto (round() de Python da 70.0 con 70.005)
check("round_pct(70.005) = 70.01 (round() da 70.0)", bc.round_pct(70.005) == 70.01 and round(70.005, 2) == 70.0)
check("round_pct(2.675) = 2.68", bc.round_pct(2.675) == 2.68)
check("media de 70.00 y 70.01 = 70.01", bc.mean_pct([70.00, 70.01]) == 70.01)
check("media de 70.00, 70.00, 70.01 = 70.00", bc.mean_pct([70.00, 70.00, 70.01]) == 70.00)
agg4 = bc.aggregate(rows({"1": [70.004, 70.004]}), 1)
check("CaCo de foto sin redondear se redondea antes de promediar (70.004 -> 70.00)",
      agg4["sitio"]["caco_sitio"] == 70.00 and agg4["parcelas"][0]["caco_max"] == 70.00, agg4["sitio"]["caco_sitio"])
check("sin fotos válidas: None", bc.mean_pct([]) is None and bc.round_pct(None) is None)

# 5) Informe y CSV
batch = dict(agg); batch["fotos"] = rows(DATA); batch["parametros"] = {}
hp = os.path.join(OUT, "informe.html")
bc.write_html(batch, hp, "0.14.62", "Prueba")
ht = open(hp, encoding="utf-8").read()
check("HTML: «media de todas las fotos válidas» y regla de cálculo",
      "media de todas las fotos válidas, Índice CaCo" in ht and "redondeada a 2 decimales" in ht
      and "media de las parcelas" not in ht)
check("HTML: valor del sitio 79.18", ">79.18 %<" in ht)
check("HTML sin referencias legales ni umbral", "7575" not in ht and "Ley" not in ht and "70 %" not in ht)
paths = bc.write_csvs(batch, os.path.join(OUT, "CobDosel_Prueba"), "0.14.62")
with open(paths[2], encoding="utf-8-sig") as f:
    site_row = next(csv.DictReader(f))
check("CSV del sitio: caco_sitio = 79.18", site_row["caco_sitio"] == "79.18", site_row["caco_sitio"])
with open(paths[1], encoding="utf-8-sig") as f:
    prow = list(csv.DictReader(f))
check("CSV de parcelas: parcela 4 = 80.5", prow[3]["caco_media"] == "80.5", prow[3]["caco_media"])

# 6) El CaCo de la foto se registra con 2 decimales en el código del lote
src = open(os.path.join(sys.argv[1], "cobdosel", "batch_core.py"), encoding="utf-8").read()
check("CaCo de la foto con round_pct en el lote", '"caco": round_pct(idx["canopy_cover_index_pct"])' in src)
check("sitio con mean_pct(all_valid)", "site_mean = mean_pct(all_valid)" in src)

print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
