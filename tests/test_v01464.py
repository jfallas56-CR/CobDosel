"""CobDosel 0.14.64: referencia, apertura y cierre de GLAMA solo en el CSV (no en el panel ni en el informe de una
foto); sin «el cierre del dosel NO es cobertura»; nota del densiómetro con el porqué de muchos puntos; tiempo de
procesamiento del lote en el informe, el panel y el registro.

Uso: python3 -I test_v01464.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, glob, re
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PKG = os.path.join(sys.argv[1], "cobdosel")

from cobdosel import batch_core as bc  # noqa: E402
from cobdosel.canopy_analysis import classify_measurement_type  # noqa: E402

fails = []


def chk(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info)[:300] + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


src = {os.path.basename(p): open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(PKG, "*.py"))}
dlg, rep, hlp = src["canopy_dialog.py"], src["html_report.py"], src["help_texts.py"]

# 1) Convención de GLAMA solo en el CSV
chk("1 panel sin «Referencia de GLAMA dentro de la foto»", "Referencia de GLAMA dentro de la foto (0–" not in dlg)
chk("1 panel sin apertura ni cierre de GLAMA", "Apertura del dosel (GLAMA, referida" not in dlg
    and "Cierre del dosel (GLAMA):" not in dlg)
chk("1 informe de una foto sin el grupo de la convención de GLAMA",
    "Índices referidos al hemisferio (convención de GLAMA)" not in rep and "Referencia dentro de la foto" not in rep
    and "están en el CSV de resultados" in rep)
chk("1 CSV de una foto conserva apertura, cierre y referencia",
    all(k in dlg for k in ('"canopy_openness_pct", "canopy_closure_pct"', '"hemisphere_fraction_pct"',
                           '"glama_reference_zenith_deg"')))
chk("1 informe: parte del hemisferio real del área analizada y de la foto", "la foto entera:" in rep)

# 2) Sin «el cierre del dosel NO es cobertura»
chk("2 sin «NO es cobertura» en el panel ni en la ayuda", "NO es cobertura" not in dlg
    and "El <i>cierre</i> del dosel no es cobertura" not in hlp)

# 3) Nota del densiómetro: por qué muchos puntos
note = classify_measurement_type(27.0, 63.0)["note"]
chk("3 nota: cada lectura es copa o cielo; 100 puntos con 80 % → ±8 puntos al 95 %",
    "solo dice copa o cielo" in note and "±8 puntos al 95 %" in note, note)
# comprobación del número: 1.96·√(0.8·0.2/100) = 0.0784
chk("3 el ±8 es el binomial: 1.96·√(0.8·0.2/100) = 7.8 puntos",
    abs(196 * (0.8 * 0.2 / 100) ** 0.5 - 7.84) < 0.01)

# 4) Tiempo de procesamiento del lote
chk("4 duration_text: segundos, minutos, horas",
    bc.duration_text(4.25) == "4.2 s" or bc.duration_text(4.25) == "4.3 s", bc.duration_text(4.25))
chk("4 duration_text: 42 s; 3 min 05 s; 1 h 02 min",
    bc.duration_text(42.4) == "42 s" and bc.duration_text(185) == "3 min 05 s" and bc.duration_text(3725) == "1 h 02 min",
    (bc.duration_text(42.4), bc.duration_text(185), bc.duration_text(3725)))
chk("4 duration_text con fotos: «(22 fotos; 1.9 s por foto)»",
    bc.duration_text(42.0, 22) == "42 s (22 fotos; 1.9 s por foto)" and bc.duration_text(3.0, 1).endswith("(1 foto; 3.0 s por foto)"),
    bc.duration_text(42.0, 22))
chk("4 duration_text sin dato: «—»", bc.duration_text(None) == "—")
core = src["batch_core.py"]
chk("4 run_batch mide su duración en sitio[«tiempo_proceso_s»]",
    '_t0 = _time.perf_counter()' in core and 'summary["sitio"]["tiempo_proceso_s"] = round(_time.perf_counter() - _t0, 1)' in core)
fotos = [{"parcela": "1", "punto": "C", "archivo": "a.jpg", "valida": True, "emparejado_por": "id", "caco": 80.0,
          "decision": "automático", "reemplaza_a": ""}]
agg = bc.aggregate(fotos, 1)
agg["sitio"]["tiempo_proceso_s"] = 125.0
batch = dict(agg); batch["fotos"] = fotos; batch["parametros"] = {}
hp = os.path.join(OUT, "lote.html")
bc.write_html(batch, hp, "0.14.64", "Prueba")
ht = " ".join(re.sub(r"<[^>]+>", " ", open(hp, encoding="utf-8").read()).split())
chk("4 informe del sitio: «Tiempo de procesamiento: 2 min 05 s (1 foto; 125.0 s por foto)»",
    "Tiempo de procesamiento: 2 min 05 s (1 foto; 125.0 s por foto)" in ht)
bd = src["batch_dialog.py"]
chk("4 panel y registro del lote con el tiempo", '"Tiempo de procesamiento: " + bc.duration_text(' in bd
    and '"Procesamiento terminado en " + bc.duration_text(' in bd)

print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
