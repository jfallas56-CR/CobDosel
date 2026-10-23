"""Pruebas sin QGIS del procesamiento por lotes de CobDosel 0.12.0.

Uso: python3 -I test_batch_v012.py <carpeta_padre_del_paquete_cobdosel> <dir_salida>
"""
import sys, os, shutil, datetime, csv, time
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
import numpy as np
from PIL import Image
from scipy import ndimage
import openpyxl
from cobdosel import batch_core as bc, lens_calibration as lc, glama_engine as ge, canopy_analysis as ca
from cobdosel._version import VERSION

fails = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


print("CobDosel", VERSION)
print("\n=== 1. Fechas y puntos ===")
check("«17/10/2026 / 19:49:43»", bc.parse_datetime("17/10/2026 / 19:49:43") == datetime.datetime(2026, 10, 17, 19, 49, 43))
check("día primero: 05/10/2026 = 5 de octubre", bc.parse_datetime("05/10/2026 08:00").month == 10)
check("ISO con T", bc.parse_datetime("2026-06-28T11:02:05") == datetime.datetime(2026, 6, 28, 11, 2, 5))
check("EXIF «2026:06:28 11:02:05»", bc.parse_datetime("2026:06:28 11:02:05").hour == 11)
check("sin segundos", bc.parse_datetime("17/10/2026 19:49").minute == 49)
check("texto inválido → None", bc.parse_datetime("ayer") is None)
pts = {"Centro": "Centro", "C": "Centro", "N-O (315°)": "N-O", "NE": "N-E", "nw": "N-O", "S-E (135°)": "S-E",
       "225": "S-O", "so": "S-O"}
check("puntos del Formulario 8 normalizados", all(bc.normalize_point(k) == v for k, v in pts.items()),
      {k: bc.normalize_point(k) for k in pts})
z = bc.zenith_from_height(21.3, 1.3, 6.31)
check("máscara desde la altura: h=21.3, cámara 1.3, huella 6.31 → cenit 17.5°", abs(z - 17.51) < 0.02, "%.2f°" % z)
check("grupos de dosel 3/4/5 → 10 / 22.5 / 30 m", [bc.canopy_group_height(g) for g in (3, 4, 5)] == [10.0, 22.5, 30.0])
check("máscara por defecto 63° (estándar de CobDosel)", bc.DEFAULT_MASK_DEG == 63.0)
check("formulario sin columna de altura", "altura_dosel_m" not in bc.FORM_COLUMNS, bc.FORM_COLUMNS)

print("\n=== 2. Sitio sintético: 4 parcelas × 5 fotos ===")
W, H = 1280, 960
rng = np.random.default_rng(11)
photo_dir = os.path.join(OUT, "fotos")
os.makedirs(photo_dir)
t0 = datetime.datetime(2026, 10, 17, 9, 0, 0)
true_gap = {}
rows = []
k = 0
plots = [("1", "", 22.0, 0.30), ("2", "", 22.0, 0.20), ("5", "3", 25.0, 0.40), ("4", "", None, 0.25)]
points = [("Centro", 0.0), ("N-O (315°)", 8.9), ("N-E (45°)", 8.9), ("S-E (135°)", 8.9), ("S-O (225°)", 8.9)]
for pid, repl, hgt, gap in plots:
    for j, (pt, dist) in enumerate(points):
        f = ndimage.gaussian_filter(rng.random((H, W)), 5)
        g = gap + rng.normal(0, 0.03)
        sky = f > np.quantile(f, 1 - g)
        noise = rng.normal(0, 8, (H, W, 1))
        arr = np.where(sky[..., None], np.array([195, 210, 238]), np.array([45, 70, 38])) + noise
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        when = t0 + datetime.timedelta(minutes=4 * k)
        name = "GLAMA_{}".format(when.strftime("%Y%m%d_%H%M%S"))
        ex = img.getexif()
        ex[0x0132] = when.strftime("%Y:%m:%d %H:%M:%S")
        img.save(os.path.join(photo_dir, name + ".jpg"), exif=ex, quality=95)
        true_gap[name] = sky.mean()
        idf = name
        hora = when.strftime("%d/%m/%Y / %H:%M:%S")
        calidad = "OK"
        if pid == "2" and pt == "S-O (225°)":
            calidad = "sol directo"                       # excluida por calidad
        if pid == "4" and pt.startswith("N-E"):
            idf = ""                                      # solo por hora
        if pid == "4" and pt.startswith("S-E"):
            idf = "GLAMA_MAL_ESCRITO"                     # ID inexistente → hora
        if pid == "1" and pt.startswith("S-O"):
            hora = (when + datetime.timedelta(seconds=300)).strftime("%d/%m/%Y / %H:%M:%S")  # hora discrepante
        rows.append([pid if j == 0 else "", repl if j == 0 else "", pt, dist,
                     idf, hora, calidad, ""])
        k += 1
# Una foto extra sin fila y una fila sin foto
Image.new("RGB", (W, H), (120, 120, 120)).save(os.path.join(photo_dir, "IMG_extra.jpg"))
os.remove(os.path.join(photo_dir, rows[19][4] + ".jpg"))          # parcela 4, S-O: foto borrada
wb = openpyxl.load_workbook(os.path.join(sys.argv[1], "cobdosel", "plantillas", "Formulario_fotos_CobDosel.xlsx"))
ws = wb.worksheets[0]
ws.delete_rows(3, ws.max_row)
for r in rows:
    ws.append(r)
form = os.path.join(OUT, "formulario.xlsx")
wb.save(form)

recs, warns = bc.read_field_form(form)
check("formulario leído: 20 filas (fila descriptiva omitida)", len(recs) == 20, len(recs))
check("parcela heredada en filas sin ID de parcela", [r["parcela"] for r in recs[:5]] == ["1"] * 5)
check("reemplaza_a heredado solo dentro de la parcela 5", [r["reemplaza_a"] for r in recs[10:16]] ==
      ["3", "3", "3", "3", "3", None], [r["reemplaza_a"] for r in recs[10:16]])
# Formulario de 0.12.0 con columna de altura: se lee y la columna se ignora
old = os.path.join(OUT, "formulario_v0120.csv")
with open(old, "w", encoding="utf-8") as fo:
    fo.write("parcela;reemplaza_a;altura_dosel_m;punto;distancia_m;id_foto;hora_captura;calidad;observaciones\n")
    for r in rows:
        fo.write(";".join(str(x) for x in (r[:2] + ["22"] + r[2:])) + "\n")
recs_old, _w = bc.read_field_form(old)
check("formulario de 0.12.0 (con altura) aceptado; altura ignorada",
      len(recs_old) == 20 and "altura_dosel_m" not in recs_old[0], len(recs_old))
check("calidad «sol directo» excluye la foto", recs[9]["excluida_por_calidad"])

photos = bc.scan_photos(photo_dir)
pairs, mw = bc.match_photos(recs, photos, 60.0)
meth = [p[2] for p in pairs]
check("emparejamiento: 17 por ID, 2 por hora, 1 sin foto",
      meth.count("id") == 17 and meth.count("hora") == 2 and meth.count("sin foto") == 1, meth)
check("aviso: hora discrepante con ID coincidente (EXIF − formulario = −300 s)", any("difiere -300 s" in w for w in mw))
check("aviso: foto sin fila", any("IMG_extra.jpg" in w for w in mw))
check("aviso: ID no encontrado → por hora", any("GLAMA_MAL_ESCRITO" in w for w in mw))

cal = lc.calibrate_from_glama_radius(1618, 2560, 1920, scale_side="long")
cal["measurement"] = {"mode": "glama_radius", "image_size": [2560, 1920]}
t1 = time.time()
batch = bc.run_batch(photo_dir, form, cal, planned_plots=4, channel_mode="blue_red")
print("    lote procesado en %.1f s" % (time.time() - t1))
fotos = batch["fotos"]
check("por defecto: máscara fija 63° en todas las fotos válidas",
      all(abs(r["mascara_horizonte"] - 63.0) < 1e-9 for r in fotos if r["valida"]) and
      batch["parametros"]["mascara_modo"] == "fija" and batch["parametros"]["mascara_horizonte_deg"] == 63.0)
vis_def = [r["visible_pct"] for r in fotos if r["valida"]]
print("    visible con máscara 63° (cenit 27°): %.1f %%" % min(vis_def))
try:
    bc.run_batch(photo_dir, form, cal, planned_plots=4, mask_mode="height")
    check("modo altura sin altura → error", False)
except ValueError as e:
    check("modo altura sin altura del sitio → ValueError", "altura" in str(e), str(e))
batch = bc.run_batch(photo_dir, form, cal, planned_plots=4, mask_mode="height", canopy_height_m=21.3,
                     camera_height_m=1.3, footprint_radius_m=6.31, channel_mode="blue_red", canopy_group=None)
fotos, parc, site = batch["fotos"], batch["parcelas"], batch["sitio"]
valid = [r for r in fotos if r["valida"]]
check("18 fotos válidas (1 excluida por calidad, 1 sin foto)", len(valid) == 18, len(valid))
check("máscara del sitio: 72.5° (cenit 17.5°)", all(abs(r["mascara_horizonte"] - 72.49) < 0.02 for r in valid))
check("corte recomendado (log-normal) en todas", all(r["metodo_corte"] == "recomendado (log-normal)" for r in valid),
      sorted({r["corte"] for r in valid}))
# CaCo coherente con el motor GLAMA directo (misma foto, mismo corte)
r0 = valid[0]
img = np.asarray(Image.open(os.path.join(photo_dir, r0["archivo"])).convert("RGB"))
c2 = lc.scale_calibration_to_image(cal, W, H)
sky = ca.threshold_image(ca.extract_channel(img, "blue_red"), r0["corte"])
g = ge.glama_indices(ge.glama_ring_counts(sky, (W / 2, H / 2), c2["virtual_radius_px"], r0["cenit_max"],
                                          calibration=c2, projection=c2["projection"]),
                     calibration=c2, radius_px=c2["virtual_radius_px"])
check("CaCo del lote = motor GLAMA directo", abs(g["canopy_cover_index_pct"] - r0["caco"]) < 1e-9,
      "%.3f" % r0["caco"])
mean_p = {p["parcela"]: p for p in parc}
check("parcela 2: media de 4 fotos válidas", mean_p["2"]["validas"] == 4 and mean_p["2"]["fotos"] == 5)
check("parcela 4: media de 4 fotos (foto borrada)", mean_p["4"]["validas"] == 4)
check("parcela 5 marcada como reemplazo de 3", mean_p["5"]["reemplaza_a"] == "3")
exp_site = np.mean([p["caco_media"] for p in parc])
check("media del sitio = media de las medias de parcela", abs(site["caco_sitio"] - exp_site) < 1e-9,
      "%.2f %%" % site["caco_sitio"])
check("sin umbral ni veredicto (herramienta general)", "cumple_umbral" not in site and "umbral_pct" not in site
      and not hasattr(bc, "LEGAL_THRESHOLD_PCT"))
# Formulario prellenado desde las fotos
dpath, nph, dw = bc.draft_form_from_photos(photo_dir, os.path.join(OUT, "borrador.xlsx"), 5)
drec, _w = bc.read_field_form(dpath)
check("formulario prellenado: una fila por foto, ordenado por hora, 5 por parcela",
      nph == 20 and len(drec) == 20 and drec[0]["punto_norm"] == "Centro" and drec[5]["parcela"] == "2"
      and drec[5]["punto_norm"] == "Centro" and drec[4]["punto_norm"] == "S-O", (nph, len(drec), dw))
dpairs, dmw = bc.match_photos(drec, bc.scan_photos(photo_dir), 60.0)
check("prellenado: todas las fotos emparejadas por ID", [p[2] for p in dpairs].count("id") == 20)
dcsv, n2, dw2 = bc.draft_form_from_photos(photo_dir, os.path.join(OUT, "borrador.csv"), 3)
check("prellenado CSV con 3 fotos por parcela (20 fotos → aviso de parcela incompleta)",
      len(bc.read_field_form(dcsv)[0]) == n2 and any("múltiplo" in w for w in dw2), dw2)
check("4 de 4 parcelas, completo", site["parcelas_con_resultado"] == 4 and site["completo"])
order = [p["caco_media"] for p in parc]
check("orden de cobertura según la fracción de cielo simulada (2 > 4 > 1 > 5)",
      mean_p["2"]["caco_media"] > mean_p["4"]["caco_media"] > mean_p["1"]["caco_media"] > mean_p["5"]["caco_media"],
      ["%.1f" % v for v in order])
b6 = bc.run_batch(photo_dir, form, cal, planned_plots=6, mask_mode="fixed", fixed_mask_deg=72.5)
check("planificadas 6 → aviso «4 de 6»", any("4 de 6" in w for w in b6["avisos"]) and not b6["sitio"]["completo"])
check("máscara fija 72.5° ≈ máscara por altura", abs(b6["sitio"]["caco_sitio"] - site["caco_sitio"]) < 0.2,
      "%.2f vs %.2f" % (b6["sitio"]["caco_sitio"], site["caco_sitio"]))

print("\n=== 3. Salidas ===")
paths = bc.write_csvs(batch, os.path.join(OUT, "sitio"), VERSION)
rows_f = list(csv.reader(open(paths[0], encoding="utf-8-sig")))
check("CSV de fotos: 20 filas + encabezado", len(rows_f) == 21)
rows_s = list(csv.DictReader(open(paths[2], encoding="utf-8-sig")))
check("CSV del sitio con media, criterio y parámetros", rows_s[0]["caco_sitio"] and rows_s[0]["plugin"] == "CobDosel"
      and rows_s[0]["param_radio_huella_m"] == "6.31")
hp = bc.write_html(batch, os.path.join(OUT, "sitio.html"), VERSION, "Sitio prueba")
ht = open(hp, encoding="utf-8").read()
check("HTML: sin umbral ni veredicto; reemplazo y avisos",
      "criterio de cobertura" not in ht and "70 %" not in ht and "7575" not in ht and "reemplazo de 3" in ht
      and "IMG_extra.jpg" in ht)
csvform = os.path.join(OUT, "formulario.csv")
with open(csvform, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(bc.FORM_COLUMNS)
    for r in rows:
        w.writerow(r)
rc, _ = bc.read_field_form(csvform)
check("formulario CSV con «;» leído igual que Excel", len(rc) == 20 and [r["punto_norm"] for r in rc[:5]] ==
      ["Centro", "N-O", "N-E", "S-E", "S-O"])

print("\nRESULTADO: %s" % ("TODAS LAS PRUEBAS PASAN" if not fails else "FALLAN: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
